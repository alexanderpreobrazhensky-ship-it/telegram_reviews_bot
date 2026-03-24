const fs = require('node:fs');
const path = require('node:path');
const Database = require('better-sqlite3');
const { normalizePhone10 } = require('../core/shared/phone');

const DEFAULT_REFERENCE_DATASET_PATH = path.join(process.cwd(), 'data', 'reference', 'client_vehicle_bridge', 'lira_normalized_database.sqlite');

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

function createReferenceClientLookup({ logger = console, datasetPath = process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH || DEFAULT_REFERENCE_DATASET_PATH } = {}) {
  const enabled = boolEnv('WEBAPP_EXISTING_CLIENT_LOOKUP_ENABLED', true);
  const state = {
    enabled,
    datasetPath,
    available: false,
    lastLookupStatus: 'not_attempted',
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
    if (!fs.existsSync(datasetPath)) {
      state.lastLookupStatus = 'dataset_missing';
      return {
        getDiagnostics: () => ({ ...state }),
        lookupByPhoneAndFio: ({ phone, fullName } = {}) => ({
          existingClient: false,
          needsReview: false,
          clientMatchBasis: 'reference_dataset_unavailable',
          matchedReferenceClientId: null,
          matchedReferenceSource: null,
          matchedReferenceSnapshot: null,
          lookupStatus: 'dataset_missing',
          normalizedPhone: normalizePhoneForLookup(phone),
          normalizedFio: normalizeFio(fullName)
        })
      };
    }

    state.db = new Database(datasetPath, { readonly: true, fileMustExist: true });
    const columns = state.db.prepare('PRAGMA table_info(clients)').all().map((row) => row.name);
    state.clientIdColumn = findColumn(columns, ['client_code', 'client_external_id', 'id']);
    state.clientNameColumn = findColumn(columns, ['client_name', 'full_name', 'name']);
    state.normalizedNameColumn = findColumn(columns, ['client_name_norm', 'full_name_norm', 'normalized_full_name']);
    state.phoneColumn = findColumn(columns, ['phone_norm', 'normalized_phone', 'phone']);
    state.sourceColumn = findColumn(columns, ['source_system', 'source']);

    if (!state.phoneColumn || !state.clientNameColumn) {
      state.lastLookupStatus = 'schema_unsupported';
      state.lastError = 'Required clients columns are missing';
      state.db.close();
      state.db = null;
      return {
        getDiagnostics: () => ({ ...state }),
        lookupByPhoneAndFio: ({ phone, fullName } = {}) => ({
          existingClient: false,
          needsReview: false,
          clientMatchBasis: 'reference_dataset_unavailable',
          matchedReferenceClientId: null,
          matchedReferenceSource: null,
          matchedReferenceSnapshot: null,
          lookupStatus: 'schema_unsupported',
          normalizedPhone: normalizePhoneForLookup(phone),
          normalizedFio: normalizeFio(fullName)
        })
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
    state.available = true;
    state.lastLookupStatus = 'ready';
  } catch (error) {
    state.lastLookupStatus = 'init_failed';
    state.lastError = String(error.message || error);
    state.available = false;
    state.db = null;
  }

  function lookupByPhoneAndFio({ phone, fullName } = {}) {
    const normalizedPhone = normalizePhoneForLookup(phone);
    const normalizedFio = normalizeFio(fullName);

    logger.info?.('webapp existing client lookup attempted', {
      datasetPath: state.datasetPath,
      available: state.available,
      normalizedPhone,
      normalizedFio
    });

    if (!state.available || !state.queryByPhone) {
      state.lastLookupStatus = 'lookup_unavailable';
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

    if (!normalizedPhone || !normalizedFio) {
      state.lastLookupStatus = 'no_match';
      return {
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'phone_fio_not_provided',
        matchedReferenceClientId: null,
        matchedReferenceSource: null,
        matchedReferenceSnapshot: null,
        lookupStatus: 'no_match',
        normalizedPhone,
        normalizedFio
      };
    }

    const candidates = state.queryByPhone.all(normalizedPhone).filter((row) => {
      const normalizedCandidate = normalizeFio(row.normalized_name || row.full_name);
      return normalizedCandidate === normalizedFio;
    });

    if (!candidates.length) {
      state.lastLookupStatus = 'no_match';
      return {
        existingClient: false,
        needsReview: false,
        clientMatchBasis: 'phone_fio_no_match',
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
      return {
        existingClient: false,
        needsReview: true,
        clientMatchBasis: 'conflict_multiple_matches',
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
    state.lastLookupStatus = 'exact_match';
    return {
      existingClient: true,
      needsReview: false,
      clientMatchBasis: 'phone_fio',
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
      datasetPath: state.datasetPath,
      available: state.available,
      lastLookupStatus: state.lastLookupStatus,
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
