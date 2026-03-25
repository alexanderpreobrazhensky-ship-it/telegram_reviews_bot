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
  const ext = path.extname(datasetPath).toLowerCase();
  if (ext === '.sqlite' || ext === '.db') return 'sqlite';
  if (ext === '.xlsx' || ext === '.xls') return 'xlsx';
  return 'unknown';
}

function candidateDatasetPaths(explicitPath = '') {
  if (explicitPath) return [explicitPath];
  if (process.env.REFERENCE_CLIENT_LOOKUP_DATASET_PATH) return [process.env.REFERENCE_CLIENT_LOOKUP_DATASET_PATH];
  if (process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH) return [process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH];
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
  const resolved = resolveDatasetPath({ logger, explicitPath: datasetPath });
  const state = {
    enabled,
    configured: Boolean(resolved.configured),
    datasetPath: resolved.resolvedPath,
    datasetExists: Boolean(resolved.exists),
    datasetReadable: Boolean(resolved.readable),
    datasetType: detectDatasetType(resolved.resolvedPath),
    pathCandidates: resolved.candidates || [],
    available: false,
    loaderStatus: 'not_initialized',
    source: 'reference_dataset',
    tableName: 'clients',
    totalClientRows: 0,
    phoneIndexBuilt: false,
    lastLookupStatus: 'not_attempted',
    lastLookupAttemptedAt: null,
    lastLookupResult: null,
    lastLookupTargetPhone: null,
    lastLookupMatchCount: 0,
    lastError: null,
    clientIdColumn: null,
    clientNameColumn: null,
    normalizedNameColumn: null,
    phoneColumn: null,
    sourceColumn: null,
    db: null,
    queryByPhone: null
  };

  if (!enabled) {
    state.lastLookupStatus = 'disabled';
    state.loaderStatus = 'disabled';
    return {
      getDiagnostics: () => ({ ...state }),
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
      state.loaderStatus = 'dataset_missing';
      state.lastError = `Dataset file does not exist: ${state.datasetPath}`;
      return {
        getDiagnostics: () => ({ ...state }),
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
      state.loaderStatus = 'dataset_not_readable';
      state.lastError = `Dataset file is not readable: ${state.datasetPath}`;
      return {
        getDiagnostics: () => ({ ...state }),
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
    const columns = state.db.prepare('PRAGMA table_info(clients)').all().map((row) => row.name);
    state.clientIdColumn = findColumn(columns, ['client_code', 'client_external_id', 'id']);
    state.clientNameColumn = findColumn(columns, ['client_name', 'full_name', 'name']);
    state.normalizedNameColumn = findColumn(columns, ['client_name_norm', 'full_name_norm', 'normalized_full_name']);
    state.phoneColumn = findColumn(columns, ['phone_norm', 'normalized_phone', 'phone']);
    state.sourceColumn = findColumn(columns, ['source_system', 'source']);

    if (!state.phoneColumn || !state.clientNameColumn) {
      state.lastLookupStatus = 'schema_unsupported';
      state.loaderStatus = 'schema_unsupported';
      state.lastError = 'Required clients columns are missing';
      state.db.close();
      state.db = null;
      return {
        getDiagnostics: () => ({ ...state }),
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
    state.loaderStatus = 'ready';
    logger.info?.('reference dataset bootstrap completed', {
      datasetPath: state.datasetPath,
      totalClientRows: state.totalClientRows,
      phoneIndexBuilt: state.phoneIndexBuilt
    });
  } catch (error) {
    state.lastLookupStatus = 'init_failed';
    state.loaderStatus = 'init_failed';
    state.lastError = String(error.message || error);
    state.available = false;
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

    const candidates = state.queryByPhone.all(normalizedPhone);
    state.lastLookupMatchCount = candidates.length;
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

  return {
    getDiagnostics: () => ({
      enabled: state.enabled,
      configured: state.configured,
      datasetPath: state.datasetPath,
      source: state.source,
      tableName: state.tableName,
      datasetExists: state.datasetExists,
      datasetReadable: state.datasetReadable,
      datasetType: state.datasetType,
      totalClientRows: state.totalClientRows,
      phoneIndexBuilt: state.phoneIndexBuilt,
      available: state.available,
      loaderStatus: state.loaderStatus,
      lastLookupStatus: state.lastLookupStatus,
      lastLookupAttemptedAt: state.lastLookupAttemptedAt,
      lastLookupResult: state.lastLookupResult,
      lastLookupTargetPhone: state.lastLookupTargetPhone,
      lastLookupMatchCount: state.lastLookupMatchCount,
      cacheStatus: 'sqlite_direct_no_cache',
      pathCandidates: state.pathCandidates,
      lastError: state.lastError
    }),
    lookupByPhoneAndFio
  };
}

module.exports = {
  createReferenceClientLookup,
  normalizeFio,
  normalizePhoneForLookup,
  DEFAULT_REFERENCE_DATASET_PATH
};
