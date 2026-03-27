const fs = require('node:fs');
const path = require('node:path');
const Database = require('better-sqlite3');
const { normalizePhone10 } = require('../core/shared/phone');

const REFERENCE_DATASET_RELATIVE_PATH = path.join('data', 'reference', 'client_vehicle_bridge', 'lira_normalized_database.sqlite');
const DEFAULT_REFERENCE_DATASET_PATH = path.resolve(__dirname, '..', '..', REFERENCE_DATASET_RELATIVE_PATH);

function normalizeFio(raw) {
  return String(raw || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/ё/g, 'е');
}

function normalizePhoneForLookup(raw) {
  const phone10 = normalizePhone10(raw);
  return /^\d{10}$/.test(phone10) ? phone10 : null;
}

function boolEnv(name, fallback = false) {
  const raw = process.env[name];
  if (raw === undefined || raw === null || raw === '') return fallback;
  return String(raw).toLowerCase() === 'true';
}

function findColumn(columns, preferred = [], fallback = []) {
  for (const name of preferred) {
    if (columns.includes(name)) return name;
  }
  for (const name of fallback) {
    if (columns.includes(name)) return name;
  }
  return null;
}

function canReadFile(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

function detectDatasetType(datasetPath) {
  if (!datasetPath) return 'unknown';
  if (datasetPath === 'runtime_cache') return 'runtime cache';
  const ext = path.extname(datasetPath).toLowerCase();
  if (ext === '.sqlite' || ext === '.db') return 'sqlite';
  if (ext === '.xlsx' || ext === '.xls') return 'xlsx';
  return 'unknown';
}

function candidateDatasetPaths(explicitPath = '') {
  if (explicitPath) return [explicitPath];
  const configuredEnvPath = process.env.REFERENCE_CLIENT_LOOKUP_DATASET_PATH || process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH || '';
  if (configuredEnvPath) return [configuredEnvPath];
  const fromMainModule = path.join(path.dirname(require.main?.filename || process.cwd()), REFERENCE_DATASET_RELATIVE_PATH);
  return [
    DEFAULT_REFERENCE_DATASET_PATH,
    path.resolve(process.cwd(), REFERENCE_DATASET_RELATIVE_PATH),
    path.resolve(fromMainModule),
    path.join('/app', REFERENCE_DATASET_RELATIVE_PATH)
  ].filter(Boolean);
}

function resolveDatasetPath({ logger = console, explicitPath = '' } = {}) {
  const seen = new Set();
  const candidates = candidateDatasetPaths(explicitPath).filter((item) => {
    const normalized = path.resolve(item);
    if (seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
  logger.info?.('reference dataset path resolution start', { candidates });
  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    const exists = fs.existsSync(resolved);
    const readable = exists ? canReadFile(resolved) : false;
    logger.info?.('reference dataset candidate checked', { candidate: resolved, exists, readable });
    if (exists && readable) {
      logger.info?.('reference dataset path resolution result', { resolvedPath: resolved, exists, readable });
      return { resolvedPath: resolved, exists, readable, configured: true, candidates };
    }
  }
  const preferred = explicitPath || process.env.REFERENCE_CLIENT_LOOKUP_DATASET_PATH || process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH || DEFAULT_REFERENCE_DATASET_PATH;
  const resolvedPreferred = path.resolve(preferred);
  const preferredExists = fs.existsSync(resolvedPreferred);
  const preferredReadable = preferredExists ? canReadFile(resolvedPreferred) : false;
  logger.warn?.('reference dataset path resolution failed', { resolvedPath: resolvedPreferred, exists: preferredExists, readable: preferredReadable, candidates });
  return {
    resolvedPath: resolvedPreferred,
    exists: preferredExists,
    readable: preferredReadable,
    configured: Boolean(preferred),
    candidates
  };
}

function createReferenceClientLookup({ logger = console, datasetPath = '' } = {}) {
  const enabled = boolEnv('WEBAPP_EXISTING_CLIENT_LOOKUP_ENABLED', true);
  const required = boolEnv('REFERENCE_LOOKUP_REQUIRED', false);
  const resolved = resolveDatasetPath({ logger, explicitPath: datasetPath });
  const state = {
    enabled,
    required,
    lookupEnabled: enabled,
    exactPhoneMatchActive: enabled,
    configured: Boolean(resolved.configured),
    datasetPathResolved: Boolean(resolved.resolvedPath),
    datasetPath: resolved.resolvedPath,
    datasetExists: Boolean(resolved.exists),
    datasetReadable: Boolean(resolved.readable),
    datasetType: detectDatasetType(resolved.resolvedPath),
    pathCandidates: resolved.candidates || [],
    available: false,
    loaderStatus: 'not_started',
    loaderFailureReason: null,
    source: 'reference_dataset',
    tableName: 'clients',
    totalClientRows: 0,
    phoneIndexBuilt: false,
    lastLookupStatus: 'not_attempted',
    lastLookupAttemptedAt: null,
    lastLookupResult: null,
    lastLookupRawPhone: null,
    lastLookupTargetPhone: null,
    lastLookupMatchCount: 0,
    lastLookupMatchedClientIds: [],
    lastLookupError: null,
    lastError: null,
    clientIdColumn: null,
    clientNameColumn: null,
    normalizedNameColumn: null,
    phoneColumn: null,
    sourceColumn: null,
    datasetOpenOk: false,
    datasetOpenError: null,
    db: null,
    queryByPhone: null
  };
  const toDiagnostics = () => ({
    ...state,
    criticalDegradation: Boolean(state.required && state.enabled && (!state.available || !state.phoneIndexBuilt))
  });

  if (!enabled) {
    state.lastLookupStatus = 'disabled';
    state.loaderStatus = 'not_started';
    return {
      getDiagnostics: toDiagnostics,
      runLookupDiagnostics: ({ phone, fullName } = {}) => ({
        rawPhone: phone || null,
        normalizedPhone: normalizePhoneForLookup(phone),
        normalizedFio: normalizeFio(fullName),
        datasetAvailable: false,
        lookupAttempted: false,
        lookupEnabled: false,
        matchCount: 0,
        matchedClientIds: [],
        matchedClientNames: [],
        matchBasis: 'lookup_disabled',
        result: 'lookup_disabled',
        diagnosticStatus: 'LOOKUP_DISABLED',
        lookupStatus: 'lookup_disabled',
        error: null
      }),
      lookupByPhoneAndFio: () => ({
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'lookup_disabled',
        matchedReferenceClientId: null,
        matchedReferenceSource: null,
        matchedReferenceSnapshot: null,
        lookupStatus: 'lookup_disabled',
        normalizedPhone: null,
        normalizedFio: null
      })
    };
  }

  try {
    logger.info?.('reference dataset bootstrap start', {
      configured: state.configured,
      datasetPath: state.datasetPath,
      datasetExists: state.datasetExists,
      datasetReadable: state.datasetReadable,
      datasetType: state.datasetType
    });

    if (!state.datasetExists) {
      state.lastLookupStatus = 'dataset_missing';
      state.loaderStatus = 'failed';
      state.loaderFailureReason = 'DATASET_FILE_MISSING';
      state.lastError = `Dataset file does not exist: ${state.datasetPath}`;
      return {
        getDiagnostics: toDiagnostics,
        runLookupDiagnostics: ({ phone, fullName } = {}) => ({
          rawPhone: phone || null,
          normalizedPhone: normalizePhoneForLookup(phone),
          normalizedFio: normalizeFio(fullName),
          datasetAvailable: false,
          lookupAttempted: false,
          lookupEnabled: true,
          matchCount: 0,
          matchedClientIds: [],
          matchedClientNames: [],
          matchBasis: 'reference_dataset_unavailable',
          result: 'dataset_missing',
          diagnosticStatus: 'DATASET_FILE_MISSING',
          lookupStatus: 'dataset_missing',
          error: state.lastError
        }),
        lookupByPhoneAndFio: ({ phone, fullName } = {}) => {
          const normalizedPhone = normalizePhoneForLookup(phone);
          state.lastLookupTargetPhone = normalizedPhone;
          state.lastLookupMatchCount = 0;
          return {
            existingClient: false,
            needsReview: false,
            clientMatchBasis: 'reference_dataset_unavailable',
            matchedReferenceClientId: null,
            matchedReferenceSource: null,
            matchedReferenceSnapshot: null,
            lookupStatus: 'dataset_missing',
            normalizedPhone,
            normalizedFio: normalizeFio(fullName)
          };
        }
      };
    }

    if (!state.datasetReadable) {
      state.lastLookupStatus = 'dataset_not_readable';
      state.loaderStatus = 'failed';
      state.loaderFailureReason = 'DATASET_UNREADABLE';
      state.lastError = `Dataset file is not readable: ${state.datasetPath}`;
      return {
        getDiagnostics: toDiagnostics,
        runLookupDiagnostics: ({ phone, fullName } = {}) => ({
          rawPhone: phone || null,
          normalizedPhone: normalizePhoneForLookup(phone),
          normalizedFio: normalizeFio(fullName),
          datasetAvailable: false,
          lookupAttempted: false,
          lookupEnabled: true,
          matchCount: 0,
          matchedClientIds: [],
          matchedClientNames: [],
          matchBasis: 'reference_dataset_unavailable',
          result: 'dataset_not_readable',
          diagnosticStatus: 'DATASET_UNREADABLE',
          lookupStatus: 'dataset_not_readable',
          error: state.lastError
        }),
        lookupByPhoneAndFio: ({ phone, fullName } = {}) => {
          const normalizedPhone = normalizePhoneForLookup(phone);
          state.lastLookupTargetPhone = normalizedPhone;
          state.lastLookupMatchCount = 0;
          return {
            existingClient: false,
            needsReview: false,
            clientMatchBasis: 'reference_dataset_unavailable',
            matchedReferenceClientId: null,
            matchedReferenceSource: null,
            matchedReferenceSnapshot: null,
            lookupStatus: 'dataset_not_readable',
            normalizedPhone,
            normalizedFio: normalizeFio(fullName)
          };
        }
      };
    }

    state.db = new Database(state.datasetPath, { readonly: true, fileMustExist: true });
    state.datasetOpenOk = true;
    state.datasetOpenError = null;
    const columns = state.db.prepare('PRAGMA table_info(clients)').all().map((row) => row.name);
    state.clientIdColumn = findColumn(columns, ['client_code', 'client_external_id', 'id']);
    state.clientNameColumn = findColumn(columns, ['client_name', 'full_name', 'name']);
    state.normalizedNameColumn = findColumn(columns, ['client_name_norm', 'full_name_norm', 'normalized_full_name']);
    state.phoneColumn = findColumn(columns, ['phone_norm', 'normalized_phone', 'phone']);
    state.sourceColumn = findColumn(columns, ['source_system', 'source']);

    if (!state.phoneColumn || !state.clientNameColumn) {
      state.lastLookupStatus = 'schema_unsupported';
      state.loaderStatus = 'failed';
      state.loaderFailureReason = 'DATASET_LOAD_FAILED';
      state.lastError = 'Required clients columns are missing';
      state.db.close();
      state.db = null;
      return {
        getDiagnostics: toDiagnostics,
        runLookupDiagnostics: ({ phone, fullName } = {}) => ({
          rawPhone: phone || null,
          normalizedPhone: normalizePhoneForLookup(phone),
          normalizedFio: normalizeFio(fullName),
          datasetAvailable: false,
          lookupAttempted: false,
          lookupEnabled: true,
          matchCount: 0,
          matchedClientIds: [],
          matchedClientNames: [],
          matchBasis: 'reference_dataset_unavailable',
          result: 'schema_unsupported',
          diagnosticStatus: 'DATASET_LOAD_FAILED',
          lookupStatus: 'schema_unsupported',
          error: state.lastError
        }),
        lookupByPhoneAndFio: ({ phone, fullName } = {}) => {
          const normalizedPhone = normalizePhoneForLookup(phone);
          state.lastLookupTargetPhone = normalizedPhone;
          state.lastLookupMatchCount = 0;
          return {
            existingClient: false,
            needsReview: false,
            clientMatchBasis: 'reference_dataset_unavailable',
            matchedReferenceClientId: null,
            matchedReferenceSource: null,
            matchedReferenceSnapshot: null,
            lookupStatus: 'schema_unsupported',
            normalizedPhone,
            normalizedFio: normalizeFio(fullName)
          };
        }
      };
    }

    const selectColumns = [
      `${state.clientIdColumn} AS client_id`,
      `${state.clientNameColumn} AS full_name`,
      `${state.phoneColumn} AS normalized_phone`,
      state.normalizedNameColumn ? `${state.normalizedNameColumn} AS normalized_name` : 'NULL AS normalized_name',
      state.sourceColumn ? `${state.sourceColumn} AS source_system` : `'reference_bridge_sqlite' AS source_system`
    ];

    state.queryByPhone = state.db.prepare(`SELECT ${selectColumns.join(', ')} FROM clients WHERE ${state.phoneColumn} = ?`);
    state.totalClientRows = state.db.prepare('SELECT COUNT(*) AS total FROM clients').get()?.total || 0;
    state.available = true;
    state.phoneIndexBuilt = true;
    state.lastLookupStatus = 'ready';
    state.loaderStatus = 'loaded';
    logger.info?.('reference dataset bootstrap completed', {
      datasetPath: state.datasetPath,
      totalClientRows: state.totalClientRows,
      phoneIndexBuilt: state.phoneIndexBuilt
    });
  } catch (error) {
    state.lastLookupStatus = 'init_failed';
    state.loaderStatus = 'failed';
    state.loaderFailureReason = 'DATASET_LOAD_FAILED';
    state.lastError = String(error.message || error);
    state.available = false;
    state.datasetOpenOk = false;
    state.datasetOpenError = state.lastError;
    state.db = null;
    logger.error?.('reference dataset bootstrap failed', {
      datasetPath: state.datasetPath,
      error: state.lastError
    });
  }

  function lookupByPhoneAndFio({ phone, fullName } = {}) {
    const normalizedPhone = normalizePhoneForLookup(phone);
    const normalizedFio = normalizeFio(fullName);
    state.lastLookupAttemptedAt = new Date().toISOString();
    state.lastLookupMatchedClientIds = [];
    state.lastLookupError = null;

    state.lastLookupRawPhone = phone || null;
    state.lastLookupTargetPhone = normalizedPhone;
    logger.info?.('reference lookup phone normalization result', { inputPhone: phone || null, normalizedPhone });
    logger.info?.('reference lookup attempted', { datasetPath: state.datasetPath, available: state.available, normalizedPhone, normalizedFio });

    if (!state.available || !state.queryByPhone) {
      state.lastLookupStatus = 'lookup_unavailable';
      state.lastLookupResult = 'reference_dataset_unavailable';
      state.lastLookupMatchCount = 0;
      logger.warn?.('reference lookup unavailable', { loaderStatus: state.loaderStatus, datasetPath: state.datasetPath, lastError: state.lastError });
      return {
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'reference_dataset_unavailable',
        matchedReferenceClientId: null,
        matchedReferenceSource: null,
        matchedReferenceSnapshot: null,
        lookupStatus: 'lookup_unavailable',
        normalizedPhone,
        normalizedFio
      };
    }

    if (!normalizedPhone) {
      state.lastLookupResult = 'no_match';
      state.lastLookupStatus = 'no_match';
      state.lastLookupMatchCount = 0;
      return {
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'phone_not_provided',
        matchedReferenceClientId: null,
        matchedReferenceSource: null,
        matchedReferenceSnapshot: null,
        lookupStatus: 'no_match',
        normalizedPhone,
        normalizedFio
      };
    }

    let candidates = [];
    try {
      candidates = state.queryByPhone.all(normalizedPhone);
    } catch (error) {
      state.lastLookupStatus = 'lookup_failed';
      state.lastLookupResult = 'lookup_failed';
      state.lastLookupError = String(error.message || error);
      state.lastLookupMatchCount = 0;
      logger.error?.('reference lookup execution failed', { normalizedPhone, error: state.lastLookupError });
      return {
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'lookup_failed',
        matchedReferenceClientId: null,
        matchedReferenceSource: null,
        matchedReferenceSnapshot: null,
        lookupStatus: 'lookup_failed',
        normalizedPhone,
        normalizedFio
      };
    }
    state.lastLookupMatchCount = candidates.length;
    state.lastLookupMatchedClientIds = candidates.map((item) => item.client_id || null).filter(Boolean).slice(0, 10);
    logger.info?.('reference lookup match count', { normalizedPhone, matchCount: candidates.length });

    if (!candidates.length) {
      state.lastLookupStatus = 'no_match';
      state.lastLookupResult = 'no_match';
      return {
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'no_match',
        matchedReferenceClientId: null,
        matchedReferenceSource: null,
        matchedReferenceSnapshot: null,
        lookupStatus: 'no_match',
        normalizedPhone,
        normalizedFio
      };
    }

    if (candidates.length > 1) {
      state.lastLookupStatus = 'multiple_matches';
      state.lastLookupResult = 'multiple_phone_matches';
      return {
        existingClient: false,
        needsReview: true,
        clientMatchBasis: 'multiple_phone_matches',
        matchedReferenceClientId: null,
        matchedReferenceSource: state.datasetPath,
        matchedReferenceSnapshot: {
          candidates: candidates.slice(0, 5).map((item) => ({
            id: item.client_id || null,
            fullName: item.full_name || null,
            normalizedPhone: item.normalized_phone || null,
            sourceSystem: item.source_system || null
          }))
        },
        lookupStatus: 'multiple_matches',
        normalizedPhone,
        normalizedFio
      };
    }

    const matched = candidates[0];
    logger.info?.('reference lookup matched client', { normalizedPhone, matchedReferenceClientId: matched.client_id || null });
    state.lastLookupStatus = 'exact_match';
    state.lastLookupResult = 'exact_phone_match';
    return {
      existingClient: true,
      needsReview: false,
      clientMatchBasis: 'phone',
      matchedReferenceClientId: matched.client_id || null,
      matchedReferenceSource: matched.source_system || 'reference_bridge_sqlite',
      matchedReferenceSnapshot: {
        fullName: matched.full_name || null,
        normalizedPhone: matched.normalized_phone || null
      },
      lookupStatus: 'exact_match',
      normalizedPhone,
      normalizedFio
    };
  }

  function runLookupDiagnostics({ phone, fullName } = {}) {
    const rawPhone = phone || null;
    logger.info?.('reference dataset diagnostics lookup started', { rawPhone, fullName: fullName || null });
    const result = lookupByPhoneAndFio({ phone, fullName });
    const matchedClientIds = result.lookupStatus === 'multiple_matches'
      ? (result.matchedReferenceSnapshot?.candidates || []).map((item) => item.id).filter(Boolean)
      : (result.matchedReferenceClientId ? [result.matchedReferenceClientId] : []);
    const matchedClientNames = result.lookupStatus === 'multiple_matches'
      ? (result.matchedReferenceSnapshot?.candidates || []).map((item) => item.fullName).filter(Boolean)
      : (result.matchedReferenceSnapshot?.fullName ? [result.matchedReferenceSnapshot.fullName] : []);
    let diagnosticStatus = 'LOOKUP_FAILED';
    if (!enabled) diagnosticStatus = 'LOOKUP_DISABLED';
    else if (!state.configured) diagnosticStatus = 'DATASET_NOT_CONFIGURED';
    else if (!state.datasetPathResolved) diagnosticStatus = 'DATASET_PATH_UNRESOLVED';
    else if (!state.datasetExists) diagnosticStatus = 'DATASET_FILE_MISSING';
    else if (!state.datasetReadable) diagnosticStatus = 'DATASET_UNREADABLE';
    else if (state.loaderStatus === 'failed') diagnosticStatus = state.loaderFailureReason || 'DATASET_LOAD_FAILED';
    else if (result.lookupStatus === 'no_match') diagnosticStatus = 'LOOKUP_OK_NO_MATCH';
    else if (result.lookupStatus === 'exact_match') diagnosticStatus = 'LOOKUP_OK_EXACT_MATCH';
    else if (result.lookupStatus === 'multiple_matches') diagnosticStatus = 'LOOKUP_OK_MULTIPLE_MATCHES';
    else if (result.lookupStatus === 'lookup_unavailable') diagnosticStatus = 'REFERENCE_DATASET_UNAVAILABLE';
    else if (result.lookupStatus === 'lookup_disabled') diagnosticStatus = 'LOOKUP_DISABLED';
    const payload = {
      rawPhone,
      normalizedPhone: result.normalizedPhone || null,
      normalizedFio: result.normalizedFio || null,
      datasetAvailable: Boolean(state.available),
      lookupAttempted: Boolean(result.normalizedPhone),
      lookupEnabled: Boolean(enabled),
      matchCount: state.lastLookupMatchCount,
      matchedClientIds,
      matchedClientNames,
      matchBasis: result.clientMatchBasis || null,
      result: result.lookupStatus || 'lookup_failed',
      diagnosticStatus,
      lookupStatus: result.lookupStatus || 'lookup_failed',
      error: state.lastLookupError || state.lastError || null
    };
    logger.info?.('reference dataset diagnostics lookup finished', payload);
    return payload;
  }

  return {
    getDiagnostics: () => ({
      enabled: state.enabled,
      required: state.required,
      configured: state.configured,
      datasetPath: state.datasetPath,
      source: state.source,
      tableName: state.tableName,
      datasetExists: state.datasetExists,
      datasetReadable: state.datasetReadable,
      datasetType: state.datasetType,
      datasetPathResolved: state.datasetPathResolved,
      resolvedDatasetPath: state.datasetPath,
      totalClientRows: state.totalClientRows,
      phoneIndexBuilt: state.phoneIndexBuilt,
      datasetOpenOk: state.datasetOpenOk,
      datasetOpenError: state.datasetOpenError,
      available: state.available,
      loaderStatus: state.loaderStatus,
      loaderFailureReason: state.loaderFailureReason,
      lookupEnabled: state.lookupEnabled,
      exactPhoneMatchActive: state.exactPhoneMatchActive,
      lastLookupStatus: state.lastLookupStatus,
      lastLookupAttemptedAt: state.lastLookupAttemptedAt,
      lastLookupResult: state.lastLookupResult,
      lastLookupRawPhone: state.lastLookupRawPhone,
      lastLookupTargetPhone: state.lastLookupTargetPhone,
      lastLookupMatchCount: state.lastLookupMatchCount,
      lastLookupMatchedClientIds: state.lastLookupMatchedClientIds,
      lastLookupError: state.lastLookupError,
      cacheStatus: 'sqlite_direct_no_cache',
      pathCandidates: state.pathCandidates,
      lastError: state.lastError,
      criticalDegradation: Boolean(state.required && state.enabled && (!state.available || !state.phoneIndexBuilt))
    }),
    runLookupDiagnostics,
    lookupByPhoneAndFio
  };
}

module.exports = {
  createReferenceClientLookup,
  normalizeFio,
  normalizePhoneForLookup,
  DEFAULT_REFERENCE_DATASET_PATH
};
