const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const Database = require('better-sqlite3');
const {
  validateAssignment,
  validateRequestStatus,
  validateRequestSubstatus,
  normalizeRequestStatus,
  normalizeLegacyRequestState,
  canTransitionRequest,
  isArchivedStatus
} = require('../../core/shared/requestValidation');

const DEFAULT_SQLITE_PATH = path.join(process.cwd(), 'data', 'db.sqlite');
const DEFAULT_LEGACY_JSON_PATH = path.join(process.cwd(), 'data', 'db.json');

const runtimeState = {
  dbPath: null,
  connection: null,
  initializedPaths: new Set(),
  lastInitStatus: 'not_initialized',
  lastMigration: null
};

function nowIso() {
  return new Date().toISOString();
}

function normalizePhone10(raw) {
  const digits = String(raw || '').replace(/\D/g, '');
  if (!digits) return null;
  if (digits.length === 10) return digits;
  if (digits.length === 11 && (digits.startsWith('7') || digits.startsWith('8'))) return digits.slice(1);
  return null;
}

function getConfiguredDbPath() {
  return process.env.DB_SQLITE_PATH || process.env.DB_FILE_PATH || DEFAULT_SQLITE_PATH;
}

function getDbPath() {
  const configuredPath = getConfiguredDbPath();
  if (/\.json$/i.test(configuredPath)) {
    return configuredPath.replace(/\.json$/i, '.sqlite');
  }
  return configuredPath;
}

function getLegacyJsonPath() {
  if (process.env.DB_JSON_IMPORT_PATH) return process.env.DB_JSON_IMPORT_PATH;
  const configuredPath = getConfiguredDbPath();
  if (/\.json$/i.test(configuredPath)) return configuredPath;
  return DEFAULT_LEGACY_JSON_PATH;
}

function logDb(level, message, meta = {}) {
  const payload = { dbType: 'sqlite', dbPath: getDbPath(), ...meta };
  const method = level === 'error' ? console.error : (level === 'warn' ? console.warn : console.log);
  method(`[DB:${level.toUpperCase()}] ${message}`, payload);
}

function makeInitialStore() {
  return {
    clients: [],
    vehicles: [],
    visits: [],
    requests: [],
    communicationEvents: [],
    integrationEvents: [],
    integrationEventLogs: [],
    recommendations: [],
    recommendationSync: { lastSyncAt: null, source: null },
    staffUsers: [],
    requestEvents: [],
    requestStatusHistory: [],
    requestInternalComments: [],
    clientInternalNotes: [],
    masterActions: [],
    qualityCases: [],
    qualityCaseComments: [],
    feedback: [],
    tasks: [],
    reportSnapshots: []
  };
}

function clone(value) {
  return value === undefined ? null : JSON.parse(JSON.stringify(value));
}

function parseJson(value, fallback) {
  if (!value) return clone(fallback);
  try {
    return JSON.parse(value);
  } catch {
    return clone(fallback);
  }
}

function serializeEntity(entity) {
  return JSON.stringify(entity || {});
}

function openConnection() {
  const dbPath = getDbPath();
  if (runtimeState.connection && runtimeState.dbPath === dbPath) {
    return runtimeState.connection;
  }
  if (runtimeState.connection) {
    runtimeState.connection.close();
  }

  const dbDir = path.dirname(dbPath);
  if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
    logDb('info', 'Created DB directory', { dbDir });
  }

  const connection = new Database(dbPath);
  connection.pragma('journal_mode = WAL');
  connection.pragma('synchronous = NORMAL');
  connection.pragma('foreign_keys = ON');

  runtimeState.connection = connection;
  runtimeState.dbPath = dbPath;
  return connection;
}

function getDb() {
  return openConnection();
}

const schemaStatements = [
  `CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    full_name TEXT,
    phone TEXT,
    telegram_id TEXT,
    max_id TEXT,
    preferred_channel TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    data TEXT NOT NULL,
    CHECK (phone IS NULL OR length(phone) = 10)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)`,
  `CREATE INDEX IF NOT EXISTS idx_clients_telegram_id ON clients(telegram_id)`,
  `CREATE INDEX IF NOT EXISTS idx_clients_max_id ON clients(max_id)`,
  `CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    vin TEXT,
    plate_number TEXT,
    brand TEXT,
    model TEXT,
    year TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_vehicles_client_id ON vehicles(client_id)`,
  `CREATE INDEX IF NOT EXISTS idx_vehicles_vin ON vehicles(vin)`,
  `CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    vehicle_id TEXT,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    description TEXT,
    source_channel TEXT,
    assigned_master_id TEXT,
    assigned_to TEXT,
    assigned_at TEXT,
    assigned_by TEXT,
    substatus TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    last_followup_at TEXT,
    lost_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_requests_client_id ON requests(client_id)`,
  `CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)`,
  `CREATE TABLE IF NOT EXISTS request_events (
    id TEXT PRIMARY KEY,
    event_scope TEXT NOT NULL,
    event_type TEXT NOT NULL,
    request_id TEXT,
    client_id TEXT,
    quality_case_id TEXT,
    actor_id TEXT,
    actor_role TEXT,
    old_value TEXT,
    new_value TEXT,
    actor_type TEXT,
    comment TEXT,
    type TEXT,
    payload TEXT,
    meta_json TEXT,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL,
    parent_event_id TEXT
  )`,
  `CREATE INDEX IF NOT EXISTS idx_request_events_request_id ON request_events(request_id)`,
  `CREATE INDEX IF NOT EXISTS idx_request_events_client_id ON request_events(client_id)`,
  `CREATE INDEX IF NOT EXISTS idx_request_events_quality_case_id ON request_events(quality_case_id)`,
  `CREATE TABLE IF NOT EXISTS communications (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    request_id TEXT,
    source TEXT,
    channel TEXT,
    direction TEXT,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_communications_client_id ON communications(client_id)`,
  `CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    due_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    processing_started_at TEXT,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_tasks_status_due_at ON tasks(status, due_at)`,
  `CREATE TABLE IF NOT EXISTS staff_users (
    id TEXT PRIMARY KEY,
    telegram_id TEXT,
    max_id TEXT,
    full_name TEXT,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_staff_users_telegram_id ON staff_users(telegram_id)`,
  `CREATE INDEX IF NOT EXISTS idx_staff_users_max_id ON staff_users(max_id)`,
  `CREATE TABLE IF NOT EXISTS quality_cases (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    feedback_id TEXT,
    request_id TEXT,
    visit_id TEXT,
    status TEXT NOT NULL,
    assigned_to TEXT,
    reason_category TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_quality_cases_request_id ON quality_cases(request_id)`,
  `CREATE INDEX IF NOT EXISTS idx_quality_cases_status ON quality_cases(status)`,
  `CREATE TABLE IF NOT EXISTS analytics_events (
    id TEXT PRIMARY KEY,
    parent_event_id TEXT,
    event_type TEXT NOT NULL,
    channel TEXT,
    platform TEXT,
    request_type TEXT,
    request_id TEXT,
    client_id TEXT,
    status TEXT,
    meta_json TEXT,
    source_system TEXT,
    processing_status TEXT,
    related_entity_type TEXT,
    related_entity_id TEXT,
    dedupe_key TEXT,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    data TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type)`,
  `CREATE INDEX IF NOT EXISTS idx_analytics_events_parent ON analytics_events(parent_event_id)`,
  `CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    visit_id TEXT,
    status TEXT,
    severity TEXT,
    interested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    request_id TEXT,
    visit_id TEXT,
    rating INTEGER NOT NULL,
    source_channel TEXT,
    created_by TEXT,
    status TEXT,
    quality_case_id TEXT,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS report_snapshots (
    id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    period_type TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generated_by TEXT,
    source_data_version TEXT,
    data TEXT NOT NULL
  )`
];

function ensureSchema() {
  const db = getDb();
  const createSchema = db.transaction(() => {
    for (const statement of schemaStatements) {
      db.prepare(statement).run();
    }
  });
  createSchema();
  ensureOptionalColumns();
}

function tableColumns(tableName) {
  return new Set(getDb().prepare(`PRAGMA table_info(${tableName})`).all().map((row) => row.name));
}

function ensureColumn(tableName, columnName, definition) {
  const columns = tableColumns(tableName);
  if (!columns.has(columnName)) {
    getDb().prepare(`ALTER TABLE ${tableName} ADD COLUMN ${columnName} ${definition}`).run();
  }
}

function ensureOptionalColumns() {
  ensureColumn('requests', 'assigned_to', 'TEXT');
  ensureColumn('requests', 'assigned_at', 'TEXT');
  ensureColumn('requests', 'assigned_by', 'TEXT');
  ensureColumn('requests', 'substatus', 'TEXT');
  ensureColumn('requests', 'archived', 'INTEGER NOT NULL DEFAULT 0');
  ensureColumn('requests', 'last_followup_at', 'TEXT');
  ensureColumn('request_events', 'old_value', 'TEXT');
  ensureColumn('request_events', 'new_value', 'TEXT');
  ensureColumn('request_events', 'actor_type', 'TEXT');
  ensureColumn('request_events', 'comment', 'TEXT');
  ensureColumn('request_events', 'type', 'TEXT');
  ensureColumn('request_events', 'payload', 'TEXT');
  ensureColumn('request_events', 'meta_json', 'TEXT');
  ensureColumn('analytics_events', 'channel', 'TEXT');
  ensureColumn('analytics_events', 'platform', 'TEXT');
  ensureColumn('analytics_events', 'request_type', 'TEXT');
  ensureColumn('analytics_events', 'request_id', 'TEXT');
  ensureColumn('analytics_events', 'client_id', 'TEXT');
  ensureColumn('analytics_events', 'status', 'TEXT');
  ensureColumn('analytics_events', 'meta_json', 'TEXT');
}

function normalizeExistingRequestStatuses() {
  const rows = getDb().prepare('SELECT * FROM requests').all();
  const tx = getDb().transaction(() => {
    for (const row of rows) {
      const entity = requestRowToEntity(row);
      insertOrReplaceRequest(entity);
    }
  });
  tx();
}

function tableCount(tableName) {
  return getDb().prepare(`SELECT COUNT(*) AS total FROM ${tableName}`).get().total;
}

function getMetaValue(key, fallback = null) {
  const row = getDb().prepare('SELECT value FROM meta WHERE key = ?').get(key);
  if (!row) return clone(fallback);
  return parseJson(row.value, fallback);
}

function setMetaValue(key, value) {
  getDb().prepare(`
    INSERT INTO meta (key, value)
    VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
  `).run(key, JSON.stringify(value));
}

function legacyJsonStoreExists() {
  const legacyPath = getLegacyJsonPath();
  return fs.existsSync(legacyPath);
}

function safeReadLegacyStore(jsonPath = getLegacyJsonPath()) {
  try {
    return JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      logDb('error', 'Failed to read legacy JSON store', {
        legacyJsonPath: jsonPath,
        errorCode: error?.code || 'LEGACY_JSON_READ_ERROR',
        errorMessage: error?.message || 'read_failed'
      });
    }
    return makeInitialStore();
  }
}

function clientRowToEntity(row) {
  const entity = parseJson(row.data, {});
  entity.id = row.id;
  entity.fullName = row.full_name;
  entity.phone = row.phone;
  entity.telegramId = row.telegram_id;
  entity.maxId = row.max_id;
  entity.preferredChannel = row.preferred_channel;
  entity.createdAt = row.created_at;
  if (row.updated_at) entity.updatedAt = row.updated_at;
  return entity;
}

function vehicleRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    clientId: row.client_id,
    vin: row.vin,
    plateNumber: row.plate_number,
    brand: row.brand,
    model: row.model,
    year: row.year,
    createdAt: row.created_at
  });
  if (row.updated_at) entity.updatedAt = row.updated_at;
  return entity;
}

function requestRowToEntity(row) {
  const entity = parseJson(row.data, {});
  const normalized = normalizeLegacyRequestState({
    status: row.status || entity.status,
    substatus: row.substatus || entity.substatus || null,
    comment: row.lost_reason || entity.lostReason || null,
    archived: Boolean(row.archived || entity.archived)
  });
  Object.assign(entity, {
    id: row.id,
    clientId: row.client_id,
    vehicleId: row.vehicle_id,
    requestType: row.request_type,
    status: normalized.status,
    substatus: normalized.substatus,
    description: row.description,
    sourceChannel: row.source_channel,
    assignedMasterId: row.assigned_master_id,
    assignedTo: row.assigned_to || row.assigned_master_id || entity.assignedTo || entity.assignedMasterId || null,
    assignedAt: row.assigned_at || entity.assignedAt || null,
    assignedBy: row.assigned_by || entity.assignedBy || null,
    archived: isArchivedStatus({ status: normalized.status, substatus: normalized.substatus, archived: Boolean(row.archived || entity.archived) }),
    lastFollowupAt: row.last_followup_at || entity.lastFollowupAt || null,
    lostReason: row.lost_reason || normalized.comment,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  });
  if (!entity.assignedMasterId && entity.assignedTo) entity.assignedMasterId = entity.assignedTo;
  return entity;
}

function requestEventRowToEntity(row) {
  const payload = parseJson(row.payload, {});
  const data = { ...parseJson(row.data, {}), ...payload };
  const canonicalEventType = row.event_type === 'request_status_changed' ? 'status_changed' : row.event_type;
  const oldStatus = normalizeRequestStatus(data.oldStatus ?? data.fromStatus ?? row.old_value ?? null) || null;
  const newStatus = normalizeRequestStatus(data.newStatus ?? data.toStatus ?? row.new_value ?? null) || null;
  const actor = data.actor ?? data.changedBy ?? row.actor_id ?? null;
  const comment = data.comment ?? data.reason ?? data.text ?? null;
  return {
    ...data,
    id: row.id,
    eventScope: row.event_scope,
    storageEventType: row.event_type,
    canonicalEventType,
    eventType: canonicalEventType === 'status_changed' ? 'request_status_changed' : canonicalEventType,
    requestId: row.request_id,
    clientId: row.client_id,
    qualityCaseId: row.quality_case_id,
    actorId: row.actor_id,
    actorRole: row.actor_role,
    actorType: row.actor_type || data.actorType || row.actor_role || null,
    actor,
    oldValue: row.old_value || data.oldValue || null,
    newValue: row.new_value || data.newValue || null,
    comment: row.comment || data.comment || comment,
    type: row.type || row.event_type,
    payload: payload,
    metaJson: parseJson(row.meta_json, data.metaJson || {}),
    oldStatus,
    newStatus,
    createdAt: row.created_at,
    parentEventId: row.parent_event_id,
    fromStatus: oldStatus,
    toStatus: newStatus
  };
}

function communicationRowToEntity(row) {
  const data = parseJson(row.data, {});
  return {
    id: row.id,
    clientId: row.client_id,
    requestId: row.request_id,
    source: row.source,
    channel: row.channel,
    direction: row.direction,
    createdAt: row.created_at,
    ...data
  };
}

function taskRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    taskType: row.task_type,
    status: row.status,
    dueAt: row.due_at,
    createdAt: row.created_at,
    processedAt: row.processed_at,
    attemptCount: row.attempt_count,
    lastError: row.last_error,
    processingStartedAt: row.processing_started_at,
    updatedAt: row.updated_at,
    payload: parseJson(row.payload, {})
  });
  return entity;
}

function staffUserRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    telegramId: row.telegram_id,
    maxId: row.max_id,
    fullName: row.full_name,
    role: row.role,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  });
  return entity;
}

function qualityCaseRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    clientId: row.client_id,
    feedbackId: row.feedback_id,
    requestId: row.request_id,
    visitId: row.visit_id,
    status: row.status,
    assignedTo: row.assigned_to,
    reasonCategory: row.reason_category,
    summary: row.summary,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  });
  return entity;
}

function analyticsEventRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    parentEventId: row.parent_event_id,
    storageEventType: row.event_type,
    channel: row.channel || entity.channel || null,
    platform: row.platform || entity.platform || null,
    requestType: row.request_type || entity.requestType || null,
    requestId: row.request_id || entity.requestId || null,
    clientId: row.client_id || entity.clientId || null,
    status: row.status || entity.status || null,
    metaJson: parseJson(row.meta_json, entity.metaJson || {}),
    sourceSystem: row.source_system,
    processingStatus: row.processing_status,
    relatedEntityType: row.related_entity_type,
    relatedEntityId: row.related_entity_id,
    dedupeKey: row.dedupe_key,
    createdAt: row.created_at,
    processedAt: row.processed_at
  });
  entity.eventType = row.event_type === 'integration_event' && entity.integrationEventType ? entity.integrationEventType : row.event_type;
  return entity;
}

function recommendationRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    clientId: row.client_id,
    visitId: row.visit_id,
    status: row.status,
    severity: row.severity,
    interested: Boolean(row.interested),
    createdAt: row.created_at,
    updatedAt: row.updated_at
  });
  return entity;
}

function feedbackRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    clientId: row.client_id,
    requestId: row.request_id,
    visitId: row.visit_id,
    rating: row.rating,
    sourceChannel: row.source_channel,
    createdBy: row.created_by,
    status: row.status,
    qualityCaseId: row.quality_case_id,
    createdAt: row.created_at
  });
  return entity;
}

function reportSnapshotRowToEntity(row) {
  const entity = parseJson(row.data, {});
  Object.assign(entity, {
    id: row.id,
    reportType: row.report_type,
    periodType: row.period_type,
    periodStart: row.period_start,
    periodEnd: row.period_end,
    generatedAt: row.generated_at,
    generatedBy: row.generated_by,
    sourceDataVersion: row.source_data_version
  });
  return entity;
}

function listRows(tableName, orderBy = 'created_at ASC') {
  return getDb().prepare(`SELECT * FROM ${tableName} ORDER BY ${orderBy}`).all();
}

function readStore() {
  initializeStore();
  const requestEvents = listRows('request_events');
  const analyticsEvents = listRows('analytics_events');
  return {
    clients: listRows('clients').map(clientRowToEntity),
    vehicles: listRows('vehicles').map(vehicleRowToEntity),
    visits: [],
    requests: listRows('requests').map(requestRowToEntity),
    communicationEvents: listRows('communications').map(communicationRowToEntity),
    integrationEvents: analyticsEvents.filter((item) => item.event_type === 'integration_event').map(analyticsEventRowToEntity),
    integrationEventLogs: analyticsEvents.filter((item) => item.event_type === 'integration_event_log').map(analyticsEventRowToEntity),
    analyticsEvents: analyticsEvents
      .filter((item) => !['integration_event', 'integration_event_log'].includes(item.event_type))
      .map(analyticsEventRowToEntity),
    recommendations: listRows('recommendations').map(recommendationRowToEntity),
    recommendationSync: getMetaValue('recommendation_sync', { lastSyncAt: null, source: null }),
    staffUsers: listRows('staff_users').map(staffUserRowToEntity),
    requestEvents: requestEvents.map(requestEventRowToEntity),
    requestStatusHistory: requestEvents.filter((item) => ['request_status_changed', 'status_changed'].includes(item.event_type)).map(requestEventRowToEntity),
    requestInternalComments: requestEvents.filter((item) => ['request_internal_comment', 'comment_added'].includes(item.event_type)).map(requestEventRowToEntity),
    clientInternalNotes: requestEvents.filter((item) => item.event_type === 'client_internal_note').map(requestEventRowToEntity),
    masterActions: requestEvents.filter((item) => item.event_type === 'master_action').map(requestEventRowToEntity),
    qualityCases: listRows('quality_cases').map(qualityCaseRowToEntity),
    qualityCaseComments: requestEvents.filter((item) => item.event_type === 'quality_case_comment').map(requestEventRowToEntity),
    feedback: listRows('feedback').map(feedbackRowToEntity),
    tasks: listRows('tasks').map(taskRowToEntity),
    reportSnapshots: listRows('report_snapshots', 'generated_at ASC').map(reportSnapshotRowToEntity)
  };
}

function insertOrReplaceClient(client) {
  const normalizedPhone = client.phone ? normalizePhone10(client.phone) : null;
  const entity = {
    externalIds: {},
    sourceSystem: 'system',
    sourceOfTruth: 'local',
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
    ...client,
    phone: normalizedPhone,
    telegramId: client.telegramId ? String(client.telegramId) : null,
    maxId: client.maxId ? String(client.maxId) : null,
    preferredChannel: client.preferredChannel || (client.maxId ? 'max' : 'telegram')
  };
  getDb().prepare(`
    INSERT OR REPLACE INTO clients (id, full_name, phone, telegram_id, max_id, preferred_channel, created_at, updated_at, data)
    VALUES (@id, @full_name, @phone, @telegram_id, @max_id, @preferred_channel, @created_at, @updated_at, @data)
  `).run({
    id: entity.id,
    full_name: entity.fullName || null,
    phone: entity.phone,
    telegram_id: entity.telegramId,
    max_id: entity.maxId,
    preferred_channel: entity.preferredChannel,
    created_at: entity.createdAt || nowIso(),
    updated_at: entity.updatedAt || null,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceVehicle(vehicle) {
  const entity = {
    externalIds: {},
    sourceSystem: 'system',
    sourceOfTruth: 'local',
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
    ...vehicle
  };
  getDb().prepare(`
    INSERT OR REPLACE INTO vehicles (id, client_id, vin, plate_number, brand, model, year, created_at, updated_at, data)
    VALUES (@id, @client_id, @vin, @plate_number, @brand, @model, @year, @created_at, @updated_at, @data)
  `).run({
    id: entity.id,
    client_id: entity.clientId || null,
    vin: entity.vin || '',
    plate_number: entity.plateNumber || '',
    brand: entity.brand || '',
    model: entity.model || '',
    year: entity.year || '',
    created_at: entity.createdAt || nowIso(),
    updated_at: entity.updatedAt || null,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceRequest(request) {
  const entity = {
    payload: {},
    externalIds: {},
    sourceSystem: request.sourceChannel || 'system',
    sourceOfTruth: 'local',
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
    ...request
  };
  getDb().prepare(`
    INSERT OR REPLACE INTO requests (
      id, client_id, vehicle_id, request_type, status, description, source_channel,
      assigned_master_id, assigned_to, assigned_at, assigned_by, substatus, archived, last_followup_at, lost_reason, created_at, updated_at, data
    ) VALUES (
      @id, @client_id, @vehicle_id, @request_type, @status, @description, @source_channel,
      @assigned_master_id, @assigned_to, @assigned_at, @assigned_by, @substatus, @archived, @last_followup_at, @lost_reason, @created_at, @updated_at, @data
    )
  `).run({
    id: entity.id,
    client_id: entity.clientId,
    vehicle_id: entity.vehicleId || null,
    request_type: entity.requestType,
    status: entity.status,
    description: entity.description || '',
    source_channel: entity.sourceChannel || null,
    assigned_master_id: entity.assignedMasterId || null,
    assigned_to: entity.assignedTo || entity.assignedMasterId || null,
    assigned_at: entity.assignedAt || null,
    assigned_by: entity.assignedBy || null,
    substatus: entity.substatus || null,
    archived: entity.archived ? 1 : 0,
    last_followup_at: entity.lastFollowupAt || null,
    lost_reason: entity.lostReason || null,
    created_at: entity.createdAt,
    updated_at: entity.updatedAt,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertRequestEvent(event) {
  const entity = { ...event };
  getDb().prepare(`
    INSERT OR REPLACE INTO request_events (
      id, event_scope, event_type, request_id, client_id, quality_case_id,
      actor_id, actor_role, old_value, new_value, actor_type, comment, type, payload, meta_json, created_at, data, parent_event_id
    ) VALUES (
      @id, @event_scope, @event_type, @request_id, @client_id, @quality_case_id,
      @actor_id, @actor_role, @old_value, @new_value, @actor_type, @comment, @type, @payload, @meta_json, @created_at, @data, @parent_event_id
    )
  `).run({
    id: entity.id,
    event_scope: entity.eventScope,
    event_type: entity.eventType,
    request_id: entity.requestId || null,
    client_id: entity.clientId || null,
    quality_case_id: entity.qualityCaseId || null,
    actor_id: entity.actorId || null,
    actor_role: entity.actorRole || null,
    old_value: entity.oldValue ?? null,
    new_value: entity.newValue ?? null,
    actor_type: entity.actorType || entity.actorRole || null,
    comment: entity.comment ?? null,
    type: entity.type || entity.eventType,
    payload: JSON.stringify(entity.payload || entity.metaJson || {}),
    meta_json: JSON.stringify(entity.metaJson || {}),
    created_at: entity.createdAt || nowIso(),
    data: serializeEntity(entity),
    parent_event_id: entity.parentEventId || null
  });
  return entity;
}

function insertCommunication(event) {
  const entity = { ...event };
  getDb().prepare(`
    INSERT OR REPLACE INTO communications (id, client_id, request_id, source, channel, direction, created_at, data)
    VALUES (@id, @client_id, @request_id, @source, @channel, @direction, @created_at, @data)
  `).run({
    id: entity.id,
    client_id: entity.clientId || null,
    request_id: entity.requestId || null,
    source: entity.source || null,
    channel: entity.channel || null,
    direction: entity.direction || null,
    created_at: entity.createdAt || nowIso(),
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceTask(task) {
  const entity = { payload: {}, ...task };
  getDb().prepare(`
    INSERT OR REPLACE INTO tasks (
      id, task_type, status, due_at, created_at, processed_at,
      attempt_count, last_error, processing_started_at, updated_at, payload, data
    ) VALUES (
      @id, @task_type, @status, @due_at, @created_at, @processed_at,
      @attempt_count, @last_error, @processing_started_at, @updated_at, @payload, @data
    )
  `).run({
    id: entity.id,
    task_type: entity.taskType,
    status: entity.status,
    due_at: entity.dueAt,
    created_at: entity.createdAt,
    processed_at: entity.processedAt || null,
    attempt_count: entity.attemptCount || 0,
    last_error: entity.lastError || null,
    processing_started_at: entity.processingStartedAt || null,
    updated_at: entity.updatedAt,
    payload: JSON.stringify(entity.payload || {}),
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceStaffUser(user) {
  const entity = { ...user, telegramId: user.telegramId ? String(user.telegramId) : null, maxId: user.maxId ? String(user.maxId) : null };
  getDb().prepare(`
    INSERT OR REPLACE INTO staff_users (id, telegram_id, max_id, full_name, role, created_at, updated_at, data)
    VALUES (@id, @telegram_id, @max_id, @full_name, @role, @created_at, @updated_at, @data)
  `).run({
    id: entity.id,
    telegram_id: entity.telegramId,
    max_id: entity.maxId,
    full_name: entity.fullName || null,
    role: entity.role,
    created_at: entity.createdAt,
    updated_at: entity.updatedAt,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceQualityCase(item) {
  const entity = { ...item };
  getDb().prepare(`
    INSERT OR REPLACE INTO quality_cases (
      id, client_id, feedback_id, request_id, visit_id, status,
      assigned_to, reason_category, summary, created_at, updated_at, data
    ) VALUES (
      @id, @client_id, @feedback_id, @request_id, @visit_id, @status,
      @assigned_to, @reason_category, @summary, @created_at, @updated_at, @data
    )
  `).run({
    id: entity.id,
    client_id: entity.clientId || null,
    feedback_id: entity.feedbackId || null,
    request_id: entity.requestId || null,
    visit_id: entity.visitId || null,
    status: entity.status,
    assigned_to: entity.assignedTo || null,
    reason_category: entity.reasonCategory || null,
    summary: entity.summary || null,
    created_at: entity.createdAt,
    updated_at: entity.updatedAt,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceAnalyticsEvent(item) {
  const entity = { ...item };
  getDb().prepare(`
    INSERT OR REPLACE INTO analytics_events (
      id, parent_event_id, event_type, channel, platform, request_type, request_id, client_id, status, meta_json,
      source_system, processing_status, related_entity_type, related_entity_id, dedupe_key, created_at, processed_at, data
    ) VALUES (
      @id, @parent_event_id, @event_type, @channel, @platform, @request_type, @request_id, @client_id, @status, @meta_json,
      @source_system, @processing_status, @related_entity_type, @related_entity_id, @dedupe_key, @created_at, @processed_at, @data
    )
  `).run({
    id: entity.id,
    parent_event_id: entity.parentEventId || null,
    event_type: entity.eventType,
    channel: entity.channel || null,
    platform: entity.platform || null,
    request_type: entity.requestType || null,
    request_id: entity.requestId || null,
    client_id: entity.clientId || null,
    status: entity.status || null,
    meta_json: JSON.stringify(entity.metaJson || {}),
    source_system: entity.sourceSystem || null,
    processing_status: entity.processingStatus || null,
    related_entity_type: entity.relatedEntityType || null,
    related_entity_id: entity.relatedEntityId || null,
    dedupe_key: entity.dedupeKey || null,
    created_at: entity.createdAt,
    processed_at: entity.processedAt || null,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceRecommendation(item) {
  const entity = { interested: false, ...item };
  getDb().prepare(`
    INSERT OR REPLACE INTO recommendations (id, client_id, visit_id, status, severity, interested, created_at, updated_at, data)
    VALUES (@id, @client_id, @visit_id, @status, @severity, @interested, @created_at, @updated_at, @data)
  `).run({
    id: entity.id,
    client_id: entity.clientId || null,
    visit_id: entity.visitId || null,
    status: entity.status || null,
    severity: entity.severity || null,
    interested: entity.interested ? 1 : 0,
    created_at: entity.createdAt,
    updated_at: entity.updatedAt,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceFeedback(item) {
  const entity = { ...item };
  getDb().prepare(`
    INSERT OR REPLACE INTO feedback (
      id, client_id, request_id, visit_id, rating, source_channel,
      created_by, status, quality_case_id, created_at, data
    ) VALUES (
      @id, @client_id, @request_id, @visit_id, @rating, @source_channel,
      @created_by, @status, @quality_case_id, @created_at, @data
    )
  `).run({
    id: entity.id,
    client_id: entity.clientId,
    request_id: entity.requestId || null,
    visit_id: entity.visitId || null,
    rating: entity.rating,
    source_channel: entity.sourceChannel || null,
    created_by: entity.createdBy || null,
    status: entity.status || null,
    quality_case_id: entity.qualityCaseId || null,
    created_at: entity.createdAt,
    data: serializeEntity(entity)
  });
  return entity;
}

function insertOrReplaceReportSnapshot(item) {
  const entity = { ...item };
  getDb().prepare(`
    INSERT OR REPLACE INTO report_snapshots (
      id, report_type, period_type, period_start, period_end, generated_at,
      generated_by, source_data_version, data
    ) VALUES (
      @id, @report_type, @period_type, @period_start, @period_end, @generated_at,
      @generated_by, @source_data_version, @data
    )
  `).run({
    id: entity.id,
    report_type: entity.reportType,
    period_type: entity.periodType,
    period_start: entity.periodStart,
    period_end: entity.periodEnd,
    generated_at: entity.generatedAt,
    generated_by: entity.generatedBy || null,
    source_data_version: entity.sourceDataVersion || null,
    data: serializeEntity(entity)
  });
  return entity;
}

function importLegacyJsonToSqlite(jsonPath = getLegacyJsonPath()) {
  ensureSchema();
  normalizeExistingRequestStatuses();
  const legacyStore = safeReadLegacyStore(jsonPath);
  const db = getDb();
  const migrate = db.transaction(() => {
    const initial = makeInitialStore();
    for (const table of ['clients', 'vehicles', 'requests', 'request_events', 'communications', 'tasks', 'staff_users', 'quality_cases', 'analytics_events', 'recommendations', 'feedback', 'report_snapshots']) {
      db.prepare(`DELETE FROM ${table}`).run();
    }
    db.prepare('DELETE FROM meta').run();

    for (const item of legacyStore.clients || initial.clients) insertOrReplaceClient(item);
    for (const item of legacyStore.vehicles || initial.vehicles) insertOrReplaceVehicle(item);
    for (const item of legacyStore.requests || initial.requests) insertOrReplaceRequest(item);
    for (const item of legacyStore.communicationEvents || initial.communicationEvents) insertCommunication(item);
    for (const item of legacyStore.tasks || initial.tasks) insertOrReplaceTask(item);
    for (const item of legacyStore.staffUsers || initial.staffUsers) insertOrReplaceStaffUser(item);
    for (const item of legacyStore.qualityCases || initial.qualityCases) insertOrReplaceQualityCase(item);
    for (const item of legacyStore.integrationEvents || initial.integrationEvents) {
      insertOrReplaceAnalyticsEvent({ ...item, eventType: 'integration_event' });
    }
    for (const item of legacyStore.integrationEventLogs || initial.integrationEventLogs) {
      insertOrReplaceAnalyticsEvent({ ...item, parentEventId: item.eventId || item.parentEventId || null, eventType: 'integration_event_log' });
    }
    for (const item of legacyStore.recommendations || initial.recommendations) insertOrReplaceRecommendation(item);
    for (const item of legacyStore.feedback || initial.feedback) insertOrReplaceFeedback(item);
    for (const item of legacyStore.reportSnapshots || initial.reportSnapshots) insertOrReplaceReportSnapshot(item);

    for (const item of legacyStore.requestStatusHistory || initial.requestStatusHistory) {
      insertRequestEvent({ ...item, eventScope: 'request', eventType: 'request_status_changed' });
    }
    for (const item of legacyStore.requestInternalComments || initial.requestInternalComments) {
      insertRequestEvent({ ...item, eventScope: 'request', eventType: 'request_internal_comment' });
    }
    for (const item of legacyStore.clientInternalNotes || initial.clientInternalNotes) {
      insertRequestEvent({ ...item, eventScope: 'client', eventType: 'client_internal_note' });
    }
    for (const item of legacyStore.masterActions || initial.masterActions) {
      insertRequestEvent({ ...item, eventScope: 'master_action', eventType: 'master_action' });
    }
    for (const item of legacyStore.qualityCaseComments || initial.qualityCaseComments) {
      insertRequestEvent({ ...item, eventScope: 'quality_case', eventType: 'quality_case_comment' });
    }

    setMetaValue('recommendation_sync', legacyStore.recommendationSync || initial.recommendationSync);
    setMetaValue('migration', {
      importedFrom: jsonPath,
      importedAt: nowIso(),
      sourceFormat: 'json',
      tableCounts: {
        clients: (legacyStore.clients || []).length,
        requests: (legacyStore.requests || []).length,
        tasks: (legacyStore.tasks || []).length,
        analyticsEvents: (legacyStore.integrationEvents || []).length
      }
    });
  });
  migrate();
  runtimeState.lastMigration = getMetaValue('migration', null);
  return runtimeState.lastMigration;
}

function initializeStore() {
  const dbPath = getDbPath();
  const fileExisted = fs.existsSync(dbPath);
  ensureSchema();

  let initStatus = fileExisted ? 'opened_existing_sqlite' : 'created_sqlite';
  let migratedFromJson = false;
  if (tableCount('clients') === 0 && tableCount('requests') === 0 && legacyJsonStoreExists()) {
    importLegacyJsonToSqlite();
    initStatus = 'migrated_from_json';
    migratedFromJson = true;
  }
  runtimeState.lastInitStatus = initStatus;

  if (!runtimeState.initializedPaths.has(dbPath)) {
    runtimeState.initializedPaths.add(dbPath);
    logDb('info', 'SQLite store initialized', {
      initStatus,
      migratedFromJson,
      legacyJsonPath: getLegacyJsonPath(),
      schemaReady: true
    });
  }

  return getDbRuntimeInfo();
}

function getDbRuntimeInfo() {
  return {
    type: 'sqlite',
    path: getDbPath(),
    dir: path.dirname(getDbPath()),
    exists: fs.existsSync(getDbPath()),
    configuredPath: getConfiguredDbPath(),
    legacyJsonPath: getLegacyJsonPath(),
    initStatus: runtimeState.lastInitStatus,
    migration: runtimeState.lastMigration
  };
}

function shutdown() {
  if (runtimeState.connection) {
    runtimeState.connection.close();
    runtimeState.connection = null;
    runtimeState.dbPath = null;
  }
}

function findClientRowByIdentity({ phone, telegramId, maxId }) {
  if (telegramId) {
    return getDb().prepare('SELECT * FROM clients WHERE telegram_id = ? LIMIT 1').get(String(telegramId));
  }
  if (maxId) {
    return getDb().prepare('SELECT * FROM clients WHERE max_id = ? LIMIT 1').get(String(maxId));
  }
  if (phone) {
    return getDb().prepare('SELECT * FROM clients WHERE phone = ? LIMIT 1').get(phone);
  }
  return null;
}

function upsertClient({ fullName, phone, telegramId, maxId = null, preferredChannel = null }) {
  initializeStore();
  const normalizedPhone = phone ? normalizePhone10(phone) : null;
  const existingRow = findClientRowByIdentity({ phone: normalizedPhone, telegramId, maxId });
  const existing = existingRow ? clientRowToEntity(existingRow) : null;
  const client = existing ? {
    ...existing,
    fullName: fullName || existing.fullName,
    phone: normalizedPhone || existing.phone || null,
    telegramId: telegramId ? String(telegramId) : existing.telegramId || null,
    maxId: maxId ? String(maxId) : existing.maxId || null,
    preferredChannel: preferredChannel || existing.preferredChannel || (maxId ? 'max' : 'telegram'),
    updatedAt: nowIso()
  } : {
    id: crypto.randomUUID(),
    fullName,
    phone: normalizedPhone,
    telegramId: telegramId ? String(telegramId) : null,
    maxId: maxId ? String(maxId) : null,
    preferredChannel: preferredChannel || (maxId ? 'max' : 'telegram'),
    externalIds: {},
    sourceSystem: 'system',
    sourceOfTruth: 'local',
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
    createdAt: nowIso()
  };
  insertOrReplaceClient(client);
  return client;
}

function upsertVehicle({ clientId, brand, model, year, vin, plateNumber }) {
  initializeStore();
  if (!brand && !model && !year && !vin && !plateNumber) return null;
  const row = getDb().prepare(`
    SELECT * FROM vehicles
    WHERE client_id = ? AND ((? <> '' AND vin = ?) OR (? <> '' AND plate_number = ?))
    LIMIT 1
  `).get(clientId, vin || '', vin || '', plateNumber || '', plateNumber || '');
  const existing = row ? vehicleRowToEntity(row) : null;
  const vehicle = existing ? {
    ...existing,
    brand: brand || existing.brand,
    model: model || existing.model,
    year: year || existing.year,
    vin: vin || existing.vin,
    plateNumber: plateNumber || existing.plateNumber,
    updatedAt: nowIso()
  } : {
    id: crypto.randomUUID(),
    clientId,
    brand: brand || '',
    model: model || '',
    year: year || '',
    vin: vin || '',
    plateNumber: plateNumber || '',
    externalIds: {},
    sourceSystem: 'system',
    sourceOfTruth: 'local',
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
    createdAt: nowIso()
  };
  insertOrReplaceVehicle(vehicle);
  return vehicle;
}

function createRequest({ clientId, vehicleId, requestType, description, sourceChannel, payload = {}, status = 'new' }) {
  initializeStore();
  const normalizedStatus = validateRequestStatus(status) || 'new';
  const createdAt = nowIso();
  const request = {
    id: crypto.randomUUID(),
    clientId,
    vehicleId: vehicleId || null,
    requestType,
    status: normalizedStatus,
    sourceChannel,
    description: description || '',
    payload: payload || {},
    assignedMasterId: null,
    assignedTo: null,
    assignedAt: null,
    assignedBy: null,
    substatus: null,
    archived: false,
    lastFollowupAt: null,
    lostReason: null,
    externalIds: {},
    sourceSystem: sourceChannel || 'system',
    sourceOfTruth: 'local',
    integrationSync: { pending: true, target: 'one_c', eventType: 'request.created' },
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
    createdAt,
    updatedAt: createdAt
  };
  const tx = getDb().transaction(() => {
    insertOrReplaceRequest(request);
    insertRequestEvent({
      id: crypto.randomUUID(),
      eventScope: 'request',
      eventType: 'created',
      requestId: request.id,
      clientId: request.clientId,
      actorId: 'system',
      actorRole: 'system',
      actorType: 'system',
      oldValue: null,
      newValue: normalizedStatus,
      payload: { requestType, sourceChannel },
      metaJson: { requestType, sourceChannel },
      createdAt
    });
    insertRequestEvent({
      id: crypto.randomUUID(),
      eventScope: 'request',
      eventType: 'status_changed',
      requestId: request.id,
      clientId: request.clientId,
      oldStatus: null,
      newStatus: normalizedStatus,
      fromStatus: null,
      toStatus: normalizedStatus,
      changedBy: 'system',
      changedByRole: 'system',
      actor: 'system',
      actorId: 'system',
      actorRole: 'system',
      actorType: 'system',
      oldValue: null,
      newValue: normalizedStatus,
      payload: { requestType, sourceChannel },
      payload: { requestType, sourceChannel },
      metaJson: { requestType, sourceChannel },
      comment: null,
      reason: null,
      createdAt
    });
    insertRequestEvent({
      id: crypto.randomUUID(),
      eventScope: 'integration',
      eventType: 'integration_sync_pending',
      requestId: request.id,
      clientId: request.clientId,
      actorId: 'system',
      actorRole: 'system',
      actorType: 'system',
      oldValue: null,
      newValue: 'one_c_pending',
      metaJson: { target: 'one_c', mappingVersion: 1 },
      createdAt
    });
    insertOrReplaceAnalyticsEvent({
      id: crypto.randomUUID(),
      eventType: 'request_created',
      channel: String(sourceChannel || '').startsWith('max') ? 'max' : 'telegram',
      platform: String(sourceChannel || '').startsWith('max') ? 'max' : 'telegram',
      requestType,
      requestId: request.id,
      clientId: request.clientId,
      status: normalizedStatus,
      metaJson: { sourceChannel },
      createdAt
    });
  });
  tx();
  return request;
}

function markRequestDuplicate({ requestId, duplicateOfRequestId, actorId = 'system', actorRole = 'system', metaJson = {} }) {
  initializeStore();
  const request = findRequestById(requestId);
  if (!request) return null;
  const updated = {
    ...request,
    payload: {
      ...(request.payload || {}),
      duplicate: true,
      duplicateOfRequestId
    },
    updatedAt: nowIso()
  };
  const event = {
    id: crypto.randomUUID(),
    eventScope: 'request',
    eventType: 'duplicate_detected',
    requestId,
    clientId: request.clientId,
    actorId,
    actorRole,
    actorType: actorRole,
    oldValue: null,
    newValue: duplicateOfRequestId || null,
    metaJson: { duplicateOfRequestId, ...(metaJson || {}) },
    createdAt: nowIso()
  };
  const tx = getDb().transaction(() => {
    insertOrReplaceRequest(updated);
    insertRequestEvent(event);
  });
  tx();
  return { request: updated, event };
}

function createAnalyticsEvent({
  eventType,
  channel = null,
  platform = null,
  requestType = null,
  requestId = null,
  clientId = null,
  status = null,
  metaJson = {},
  sourceSystem = null,
  processingStatus = null,
  relatedEntityType = null,
  relatedEntityId = null,
  dedupeKey = null,
  parentEventId = null,
  processedAt = null
}) {
  initializeStore();
  const event = {
    id: crypto.randomUUID(),
    parentEventId,
    eventType,
    channel,
    platform,
    requestType,
    requestId,
    clientId,
    status,
    metaJson,
    sourceSystem,
    processingStatus,
    relatedEntityType,
    relatedEntityId,
    dedupeKey,
    createdAt: nowIso(),
    processedAt
  };
  insertOrReplaceAnalyticsEvent(event);
  return event;
}

function createCommunicationEvent({ clientId, requestId, source, payload, channel = null, direction = null }) {
  initializeStore();
  const event = {
    id: crypto.randomUUID(),
    clientId: clientId || null,
    requestId: requestId || null,
    source,
    channel: channel || source || null,
    direction: direction || null,
    payload,
    createdAt: nowIso()
  };
  insertCommunication(event);
  return event;
}

function recordMasterAction({ actorId, role, action, requestId = null, clientId = null, payload = {} }) {
  initializeStore();
  const item = {
    id: crypto.randomUUID(),
    eventScope: 'master_action',
    eventType: 'master_action',
    actorId,
    actorRole: role,
    action,
    requestId,
    clientId,
    payload,
    createdAt: nowIso()
  };
  insertRequestEvent(item);
  return item;
}

function recordRequestEvent({
  requestId = null,
  clientId = null,
  eventType,
  oldValue = null,
  newValue = null,
  actorId = null,
  actorRole = null,
  actorType = null,
  metaJson = {},
  comment = null
}) {
  initializeStore();
  const item = {
    id: crypto.randomUUID(),
    eventScope: 'request',
    eventType,
    requestId,
    clientId,
    actorId,
    actorRole,
    actorType,
    oldValue,
    newValue,
    metaJson,
    comment,
    createdAt: nowIso()
  };
  insertRequestEvent(item);
  return item;
}

function resolveStaffUser({ channel = 'telegram', channelUserId = '', telegramId, maxId, fullName, adminIds = [], adminTelegramIds = [] }) {
  initializeStore();
  const resolvedChannel = channel === 'max' ? 'max' : 'telegram';
  const externalId = String(channelUserId || (resolvedChannel === 'max' ? maxId : telegramId) || '').trim();
  if (!externalId) return null;
  const adminSet = new Set([...(adminIds || []), ...(resolvedChannel === 'telegram' ? adminTelegramIds : [])].map((id) => String(id).trim()).filter(Boolean));
  const isEnvAdmin = adminSet.has(externalId);
  const field = resolvedChannel === 'max' ? 'maxId' : 'telegramId';
  const row = getDb().prepare(`SELECT * FROM staff_users WHERE ${resolvedChannel === 'max' ? 'max_id' : 'telegram_id'} = ? LIMIT 1`).get(externalId);
  let user = row ? staffUserRowToEntity(row) : null;

  if (isEnvAdmin) {
    if (!user) {
      user = {
        id: crypto.randomUUID(),
        telegramId: resolvedChannel === 'telegram' ? externalId : null,
        maxId: resolvedChannel === 'max' ? externalId : null,
        fullName: fullName || `admin_${externalId}`,
        role: 'admin',
        createdAt: nowIso(),
        updatedAt: nowIso()
      };
    } else {
      user.role = 'admin';
      user[field] = externalId;
      if (fullName) user.fullName = fullName;
      user.updatedAt = nowIso();
    }
    insertOrReplaceStaffUser(user);
    return user;
  }

  if (!user) return null;
  if (user[field] !== externalId || (fullName && fullName !== user.fullName)) {
    user[field] = externalId;
    user.fullName = fullName || user.fullName;
    user.updatedAt = nowIso();
    insertOrReplaceStaffUser(user);
  }
  return user;
}

function listStaffUsers() {
  initializeStore();
  return listRows('staff_users').map(staffUserRowToEntity)
    .sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
}

function createStaffUser({ channel = 'telegram', channelUserId = '', telegramId, maxId, fullName, role, actorId = null, actorRole = null }) {
  initializeStore();
  const allowedRoles = new Set(['master', 'manager']);
  if (!allowedRoles.has(role)) return { error: 'INVALID_ROLE' };
  const resolvedChannel = channel === 'max' ? 'max' : 'telegram';
  const externalId = String(channelUserId || (resolvedChannel === 'max' ? maxId : telegramId) || '').trim();
  if (!externalId) return { error: resolvedChannel === 'max' ? 'MAX_ID_REQUIRED' : 'TELEGRAM_ID_REQUIRED' };

  const row = getDb().prepare(`SELECT * FROM staff_users WHERE ${resolvedChannel === 'max' ? 'max_id' : 'telegram_id'} = ? LIMIT 1`).get(externalId);
  let user = row ? staffUserRowToEntity(row) : null;
  if (user) {
    if (user.role === 'admin') return { error: 'ADMIN_ROLE_IMMUTABLE' };
    user.role = role;
    user[resolvedChannel === 'max' ? 'maxId' : 'telegramId'] = externalId;
    user.fullName = fullName || user.fullName || `staff_${externalId}`;
    user.updatedAt = nowIso();
  } else {
    user = {
      id: crypto.randomUUID(),
      telegramId: resolvedChannel === 'telegram' ? externalId : null,
      maxId: resolvedChannel === 'max' ? externalId : null,
      fullName: fullName || `staff_${externalId}`,
      role,
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
  }
  insertOrReplaceStaffUser(user);
  recordMasterAction({ actorId, role: actorRole, action: 'staff_user_upserted', payload: { staffUserId: user.id, channel: resolvedChannel, channelUserId: externalId, role } });
  return { user };
}

function revokeStaffUser({ channel = 'telegram', channelUserId = '', telegramId, maxId, actorId = null, actorRole = null }) {
  initializeStore();
  const resolvedChannel = channel === 'max' ? 'max' : 'telegram';
  const externalId = String(channelUserId || (resolvedChannel === 'max' ? maxId : telegramId) || '').trim();
  if (!externalId) return { error: resolvedChannel === 'max' ? 'MAX_ID_REQUIRED' : 'TELEGRAM_ID_REQUIRED' };
  const column = resolvedChannel === 'max' ? 'max_id' : 'telegram_id';
  const row = getDb().prepare(`SELECT * FROM staff_users WHERE ${column} = ? LIMIT 1`).get(externalId);
  if (!row) return { error: 'STAFF_USER_NOT_FOUND' };
  const user = staffUserRowToEntity(row);
  if (user.role === 'admin') return { error: 'ADMIN_ROLE_IMMUTABLE' };
  getDb().prepare(`DELETE FROM staff_users WHERE ${column} = ?`).run(externalId);
  recordMasterAction({ actorId, role: actorRole, action: 'staff_user_revoked', payload: { staffUserId: user.id, channel: resolvedChannel, channelUserId: externalId } });
  return { user };
}

function listRequests({ phone, telegramId, maxId, statuses, channel, requestType }) {
  initializeStore();
  let clientId = null;
  if (phone || telegramId || maxId) {
    const row = findClientRowByIdentity({ phone, telegramId, maxId });
    if (!row) return [];
    clientId = row.id;
  }
  let sql = 'SELECT * FROM requests';
  const params = [];
  const where = [];
  if (clientId) {
    where.push('client_id = ?');
    params.push(clientId);
  }
  if (statuses?.length) {
    const expandedStatuses = expandRequestStatuses(statuses);
    where.push(`status IN (${expandedStatuses.map(() => '?').join(',')})`);
    params.push(...expandedStatuses);
  }
  if (channel) {
    where.push('source_channel = ?');
    params.push(channel);
  }
  if (requestType) {
    where.push('request_type = ?');
    params.push(requestType);
  }
  if (where.length) sql += ` WHERE ${where.join(' AND ')}`;
  sql += ' ORDER BY created_at ASC';
  return getDb().prepare(sql).all(...params).map(requestRowToEntity).map((item) => ({ ...item, summary: String(item.description || '').slice(0, 120) }));
}

function listRecommendations({ phone, telegramId, maxId, clientId = null, includeHistory = false, requireSynced = false }) {
  initializeStore();
  const recommendationSync = getMetaValue('recommendation_sync', { lastSyncAt: null, source: null });
  if (requireSynced && !recommendationSync?.lastSyncAt) return [];
  let resolvedClientId = clientId;
  if (!resolvedClientId && (phone || telegramId || maxId)) {
    const row = findClientRowByIdentity({ phone, telegramId, maxId });
    resolvedClientId = row?.id || null;
  }
  return listRows('recommendations').map(recommendationRowToEntity).filter((item) => {
    if (!includeHistory && item.status !== 'actual') return false;
    if (!item.clientId) return true;
    return resolvedClientId && item.clientId === resolvedClientId;
  });
}

function markRecommendationInterest(id) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM recommendations WHERE id = ? LIMIT 1').get(id);
  if (!row) return null;
  const item = recommendationRowToEntity(row);
  item.interested = true;
  item.updatedAt = nowIso();
  insertOrReplaceRecommendation(item);
  return item;
}

function upsertRecommendationFromSync({ externalId = null, clientId = null, text = '', severity = 'normal', status = 'actual' }) {
  initializeStore();
  const all = listRows('recommendations').map(recommendationRowToEntity);
  let item = externalId ? (all.find((r) => r.externalIds?.one_c === String(externalId)) || null) : null;
  if (!item) {
    item = {
      id: crypto.randomUUID(),
      clientId: clientId || null,
      text: String(text || '').trim(),
      severity,
      status,
      interested: false,
      externalIds: externalId ? { one_c: String(externalId) } : {},
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
  } else {
    item.clientId = clientId || item.clientId || null;
    item.text = String(text || item.text || '').trim();
    item.severity = severity || item.severity || 'normal';
    item.status = status || item.status || 'actual';
    item.updatedAt = nowIso();
  }
  insertOrReplaceRecommendation(item);
  setMetaValue('recommendation_sync', { lastSyncAt: nowIso(), source: 'one_c' });
  return item;
}


const REQUEST_STATUS_COMPATIBILITY = {
  new: ['new'],
  in_progress: ['in_progress', 'assigned'],
  processed: ['processed', 'scheduled'],
  in_service: ['in_service'],
  completed: ['completed', 'done', 'cancelled', 'lost', 'archived'],
  error: ['error', 'awaiting_client', 'waiting_data']
};

function expandRequestStatuses(statuses = []) {
  const result = new Set();
  for (const status of statuses || []) {
    const normalized = validateRequestStatus(status);
    if (!normalized) continue;
    result.add(normalized);
    for (const alias of REQUEST_STATUS_COMPATIBILITY[normalized] || []) result.add(alias);
  }
  return [...result];
}

function createRequestStatusHistoryEvent({ request, fromStatus, toStatus, fromSubstatus = null, toSubstatus = null, actorId, actorRole, comment = null, eventType = 'status_changed', metaJson = {} }) {
  return {
    id: crypto.randomUUID(),
    eventScope: 'request',
    eventType,
    requestId: request.id,
    clientId: request.clientId,
    oldStatus: fromStatus,
    newStatus: toStatus,
    fromStatus,
    toStatus,
    fromSubstatus,
    toSubstatus,
    changedBy: actorId,
    changedByRole: actorRole,
    actor: actorId,
    actorId,
    actorRole,
    actorType: actorRole || 'system',
    oldValue: fromStatus,
    newValue: toStatus,
    payload: { fromStatus, toStatus, fromSubstatus, toSubstatus, comment, ...metaJson },
    metaJson: { fromStatus, toStatus, fromSubstatus, toSubstatus, comment, ...metaJson },
    comment,
    reason: comment,
    createdAt: nowIso()
  };
}

function maybeScheduleWaitingDecisionFollowup(request) {
  if (request.status !== 'processed' || request.substatus !== 'waiting_decision') return null;
  const existingTask = getDb().prepare(`
    SELECT id FROM tasks
    WHERE task_type = 'waiting_decision_followup' AND status IN ('scheduled', 'processing')
      AND json_extract(payload, '$.requestId') = ?
    LIMIT 1
  `).get(request.id);
  if (existingTask) return null;
  const dueAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
  insertOrReplaceTask({
    id: crypto.randomUUID(),
    taskType: 'waiting_decision_followup',
    status: 'scheduled',
    dueAt,
    createdAt: nowIso(),
    processedAt: null,
    attemptCount: 0,
    lastError: null,
    processingStartedAt: null,
    updatedAt: nowIso(),
    payload: { requestId: request.id, assignedTo: request.assignedTo || null }
  });
  return dueAt;
}

function updateRequestStatus({ requestId, toStatus, substatus = null, actorId, actorRole, lostReason = null, comment = null, followupAt = null }) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM requests WHERE id = ? LIMIT 1').get(requestId);
  if (!row) return { error: 'REQUEST_NOT_FOUND' };
  const request = requestRowToEntity(row);
  const fromStatus = request.status;
  const fromSubstatus = request.substatus || null;
  const nextStatus = validateRequestStatus(toStatus);
  const nextSubstatus = validateRequestSubstatus(substatus) || null;
  const statusComment = String(comment || lostReason || '').trim() || null;
  const transition = canTransitionRequest({ fromStatus, fromSubstatus, toStatus: nextStatus, toSubstatus: nextSubstatus });

  if (!nextStatus) return { error: 'INVALID_STATUS' };
  if (!transition.ok) return { error: transition.error, fromStatus, toStatus: nextStatus, fromSubstatus, toSubstatus: nextSubstatus };
  if (transition.noop) return { request, history: null };
  if (nextStatus === 'processed' && !nextSubstatus) return { error: 'SUBSTATUS_REQUIRED' };
  if (nextSubstatus === 'rejected' && !statusComment) return { error: 'COMMENT_REQUIRED' };

  request.status = nextStatus;
  request.substatus = nextStatus === 'processed' ? nextSubstatus : null;
  request.archived = isArchivedStatus({ status: request.status, substatus: request.substatus, archived: false });
  request.updatedAt = nowIso();
  request.lastFollowupAt = followupAt || request.lastFollowupAt || null;
  request.lostReason = request.substatus === 'rejected' ? statusComment : null;
  if (!request.assignedMasterId && actorId) request.assignedMasterId = actorId;

  const history = createRequestStatusHistoryEvent({
    request,
    fromStatus,
    toStatus: request.status,
    fromSubstatus,
    toSubstatus: request.substatus,
    actorId,
    actorRole,
    comment: statusComment,
    metaJson: { archived: request.archived, lostReason: request.lostReason }
  });

  const tx = getDb().transaction(() => {
    insertOrReplaceRequest(request);
    insertRequestEvent(history);
    insertCommunication({
      id: crypto.randomUUID(),
      clientId: request.clientId,
      requestId,
      source: 'master_bot',
      channel: 'master_bot',
      direction: 'internal',
      payload: { action: 'request_status_changed', fromStatus, toStatus: request.status, fromSubstatus, toSubstatus: request.substatus, actorId, actorRole, comment: statusComment },
      createdAt: nowIso()
    });
    insertRequestEvent({
      id: crypto.randomUUID(),
      eventScope: 'master_action',
      eventType: 'master_action',
      actorId,
      actorRole,
      action: 'request_status_changed',
      requestId,
      clientId: request.clientId,
      payload: { fromStatus, toStatus: request.status, fromSubstatus, toSubstatus: request.substatus, comment: statusComment },
      createdAt: nowIso()
    });
    insertOrReplaceAnalyticsEvent({
      id: crypto.randomUUID(),
      eventType: 'status_changed',
      channel: String(request.sourceChannel || '').startsWith('max') ? 'max' : 'telegram',
      platform: String(request.sourceChannel || '').startsWith('max') ? 'max' : 'telegram',
      requestType: request.requestType,
      requestId,
      clientId: request.clientId,
      status: request.status,
      metaJson: { fromStatus, toStatus: request.status, fromSubstatus, toSubstatus: request.substatus, actorId, actorRole, comment: statusComment, archived: request.archived },
      createdAt: nowIso()
    });

    if (request.status === 'processed' && request.substatus === 'waiting_decision') {
      const dueAt = maybeScheduleWaitingDecisionFollowup(request);
      insertRequestEvent({
        id: crypto.randomUUID(),
        eventScope: 'request',
        eventType: 'followup_scheduled',
        requestId,
        clientId: request.clientId,
        actorId,
        actorRole,
        actorType: actorRole || 'system',
        comment: dueAt ? `followup_due:${dueAt}` : 'followup_already_scheduled',
        payload: { dueAt },
        metaJson: { dueAt },
        createdAt: nowIso()
      });
    }

    if (request.status === 'completed') {
      const existingTask = getDb().prepare(`
        SELECT id FROM tasks
        WHERE task_type = 'feedback_request' AND status <> 'cancelled' AND json_extract(payload, '$.requestId') = ?
        LIMIT 1
      `).get(requestId);
      if (!existingTask) {
        const delayMinutes = Number(process.env.FEEDBACK_REQUEST_DELAY_MINUTES || 5);
        insertOrReplaceTask({
          id: crypto.randomUUID(),
          taskType: 'feedback_request',
          status: 'scheduled',
          dueAt: new Date(Date.now() + Math.max(0, delayMinutes) * 60 * 1000).toISOString(),
          createdAt: nowIso(),
          processedAt: null,
          attemptCount: 0,
          lastError: null,
          processingStartedAt: null,
          updatedAt: nowIso(),
          payload: {
            clientId: request.clientId,
            requestId,
            assignedMasterId: request.assignedMasterId || null
          }
        });
      }
    }
  });
  tx();
  return { request, history };
}

function reactivateWaitingDecisionRequest({ requestId, actorId = 'system', actorRole = 'system' }) {
  initializeStore();
  const request = findRequestById(requestId);
  if (!request || request.status !== 'processed' || request.substatus !== 'waiting_decision') return null;
  request.status = 'in_progress';
  request.substatus = null;
  request.archived = false;
  request.lastFollowupAt = nowIso();
  request.updatedAt = request.lastFollowupAt;
  const history = createRequestStatusHistoryEvent({
    request,
    fromStatus: 'processed',
    toStatus: 'in_progress',
    fromSubstatus: 'waiting_decision',
    toSubstatus: null,
    actorId,
    actorRole,
    comment: 'scheduler_followup_reactivated',
    eventType: 'followup_reactivated',
    metaJson: { scheduler: true, lastFollowupAt: request.lastFollowupAt }
  });
  const tx = getDb().transaction(() => {
    insertOrReplaceRequest(request);
    insertRequestEvent(history);
    insertRequestEvent({
      id: crypto.randomUUID(),
      eventScope: 'master_action',
      eventType: 'master_action',
      actorId,
      actorRole,
      action: 'request_followup_reactivated',
      requestId,
      clientId: request.clientId,
      payload: { requestId, assignedTo: request.assignedTo || null },
      createdAt: nowIso()
    });
  });
  tx();
  return { request, history };
}

function updateRequestAssignment({ requestId, assignedTo, assignedBy = null, actorId = null, actorRole = null, actorType = null, metaJson = {} }) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM requests WHERE id = ? LIMIT 1').get(requestId);
  if (!row) return { error: 'REQUEST_NOT_FOUND' };
  const request = requestRowToEntity(row);
  const assignmentValidation = validateAssignment(assignedTo);
  if (!assignmentValidation.ok) return { error: assignmentValidation.error };
  const normalizedAssignedTo = assignmentValidation.value;

  const oldValue = request.assignedTo || null;
  request.assignedTo = normalizedAssignedTo;
  request.assignedMasterId = normalizedAssignedTo;
  request.assignedBy = normalizedAssignedTo ? (assignedBy || actorId || actorRole || 'system') : null;
  request.assignedAt = normalizedAssignedTo ? nowIso() : null;
  request.updatedAt = nowIso();

  const event = {
    id: crypto.randomUUID(),
    eventScope: 'request',
    eventType: 'assigned',
    requestId,
    clientId: request.clientId,
    actorId: actorId || assignedBy || null,
    actorRole: actorRole || null,
    actorType: actorType || actorRole || 'system',
    oldValue,
    newValue: normalizedAssignedTo,
    comment: normalizedAssignedTo ? null : 'assignment_cleared',
    metaJson: {
      assignedAt: request.assignedAt,
      assignedBy: request.assignedBy,
      ...metaJson
    },
    createdAt: nowIso()
  };

  const tx = getDb().transaction(() => {
    insertOrReplaceRequest(request);
    insertRequestEvent(event);
    insertRequestEvent({
      id: crypto.randomUUID(),
      eventScope: 'master_action',
      eventType: 'master_action',
      actorId: actorId || assignedBy || null,
      actorRole: actorRole || null,
      action: 'request_assigned',
      requestId,
      clientId: request.clientId,
      payload: { oldValue, assignedTo: normalizedAssignedTo, assignedBy: request.assignedBy },
      createdAt: nowIso()
    });
    insertOrReplaceAnalyticsEvent({
      id: crypto.randomUUID(),
      eventType: 'assignment_changed',
      channel: String(request.sourceChannel || '').startsWith('max') ? 'max' : 'telegram',
      platform: String(request.sourceChannel || '').startsWith('max') ? 'max' : 'telegram',
      requestType: request.requestType,
      requestId,
      clientId: request.clientId,
      status: request.status,
      metaJson: { oldValue, newValue: normalizedAssignedTo, assignedBy: request.assignedBy, assignedAt: request.assignedAt },
      createdAt: nowIso()
    });
  });
  tx();
  return { request, event };
}

function addInternalComment({ requestId, actorId, actorRole, text }) {
  initializeStore();
  const request = findRequestById(requestId);
  if (!request) return null;
  const comment = {
    id: crypto.randomUUID(),
    eventScope: 'request',
    eventType: 'comment_added',
    requestId,
    clientId: request.clientId,
    actorId,
    actorRole,
    actorType: actorRole || 'system',
    comment: text,
    text,
    createdAt: nowIso()
  };
  insertRequestEvent(comment);
  insertRequestEvent({
    id: crypto.randomUUID(),
    eventScope: 'master_action',
    eventType: 'master_action',
    actorId,
    actorRole,
    action: 'request_internal_comment_added',
    requestId,
    clientId: request.clientId,
    payload: { commentId: comment.id },
    createdAt: nowIso()
  });
  return comment;
}

function addClientNote({ clientId, actorId, actorRole, text }) {
  initializeStore();
  const client = getDb().prepare('SELECT id FROM clients WHERE id = ? LIMIT 1').get(clientId);
  if (!client) return null;
  const note = {
    id: crypto.randomUUID(),
    eventScope: 'client',
    eventType: 'client_internal_note',
    clientId,
    actorId,
    actorRole,
    text,
    createdAt: nowIso()
  };
  insertRequestEvent(note);
  insertRequestEvent({
    id: crypto.randomUUID(),
    eventScope: 'master_action',
    eventType: 'master_action',
    actorId,
    actorRole,
    action: 'client_note_added',
    clientId,
    payload: { noteId: note.id },
    createdAt: nowIso()
  });
  return note;
}

function searchCRM(query) {
  initializeStore();
  const q = String(query || '').trim().toLowerCase();
  if (!q) return { clients: [], requests: [] };
  const vehicles = listRows('vehicles').map(vehicleRowToEntity);
  const requests = listRows('requests').map(requestRowToEntity);
  const clients = listRows('clients').map(clientRowToEntity);
  const matchedVehicles = vehicles.filter((v) => [v.vin, v.plateNumber].some((value) => String(value || '').toLowerCase().includes(q)));
  const vehicleIds = new Set(matchedVehicles.map((v) => v.id));
  const clientIdsFromVehicle = new Set(matchedVehicles.map((v) => v.clientId));
  const matchedClients = clients.filter((c) => String(c.fullName || '').toLowerCase().includes(q) || String(c.phone || '').includes(q) || clientIdsFromVehicle.has(c.id));
  const clientIds = new Set(matchedClients.map((c) => c.id));
  return {
    clients: matchedClients,
    requests: requests.filter((r) => clientIds.has(r.clientId) || vehicleIds.has(r.vehicleId))
  };
}

function getClientCard(clientId) {
  initializeStore();
  const store = readStore();
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return null;
  return {
    client,
    telegramBinding: client.telegramId || null,
    maxBinding: client.maxId || null,
    vehicles: store.vehicles.filter((item) => item.clientId === clientId),
    requests: store.requests.filter((item) => item.clientId === clientId),
    recommendations: store.recommendations.filter((item) => !item.clientId || item.clientId === clientId),
    internalNotes: store.clientInternalNotes.filter((item) => item.clientId === clientId)
  };
}

function getRequestCard(requestId) {
  initializeStore();
  const store = readStore();
  const request = store.requests.find((item) => item.id === requestId);
  if (!request) return null;
  return {
    request,
    client: store.clients.find((item) => item.id === request.clientId) || null,
    vehicle: store.vehicles.find((item) => item.id === request.vehicleId) || null,
    assignedMaster: store.staffUsers.find((item) => item.id === request.assignedMasterId) || null,
    requestEvents: store.requestEvents.filter((item) => item.requestId === requestId),
    statusHistory: store.requestStatusHistory.filter((item) => item.requestId === requestId),
    internalComments: store.requestInternalComments.filter((item) => item.requestId === requestId)
  };
}

function listQualityCases(statuses = []) {
  initializeStore();
  const all = listRows('quality_cases').map(qualityCaseRowToEntity);
  return statuses.length ? all.filter((item) => statuses.includes(item.status)) : all;
}

function createQualityCase({ requestId, status = 'new', assignedTo = null, summary = 'Manual quality case' }) {
  initializeStore();
  const request = requestId ? findRequestById(requestId) : null;
  const qualityCase = {
    id: crypto.randomUUID(),
    requestId,
    clientId: request?.clientId || null,
    feedbackId: null,
    status,
    assignedTo,
    reasonCategory: null,
    summary,
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
  insertOrReplaceQualityCase(qualityCase);
  return qualityCase;
}

function findClientByTelegramId(telegramId) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM clients WHERE telegram_id = ? LIMIT 1').get(String(telegramId || ''));
  return row ? clientRowToEntity(row) : null;
}

function findClientByMaxId(maxId) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM clients WHERE max_id = ? LIMIT 1').get(String(maxId || ''));
  return row ? clientRowToEntity(row) : null;
}

function findRequestById(requestId) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM requests WHERE id = ? LIMIT 1').get(requestId);
  return row ? requestRowToEntity(row) : null;
}

function findRecentDuplicateRequest({ requestType, phone, vin, text, withinMs = 45000 }) {
  initializeStore();
  const normalizedPhone = String(phone || '').trim();
  if (!normalizedPhone) return null;
  const normalizedVin = String(vin || '').trim().toUpperCase();
  const normalizedText = String(text || '').trim().toLowerCase();
  const now = Date.now();
  const windowMs = Math.max(1000, Number(withinMs) || 45000);
  const requests = listRows('requests', 'created_at DESC').map(requestRowToEntity);
  const vehicles = new Map(listRows('vehicles').map((row) => { const entity = vehicleRowToEntity(row); return [entity.id, entity]; }));
  const clients = new Map(listRows('clients').map((row) => { const entity = clientRowToEntity(row); return [entity.id, entity]; }));
  for (const request of requests) {
    const createdAtMs = Date.parse(request.createdAt || '');
    if (!Number.isFinite(createdAtMs) || now - createdAtMs > windowMs) continue;
    const client = clients.get(request.clientId);
    if (!client || String(client.phone || '') !== normalizedPhone) continue;
    if (requestType && request.requestType !== requestType) continue;
    const vehicle = request.vehicleId ? vehicles.get(request.vehicleId) || null : null;
    if (normalizedVin && String(vehicle?.vin || '').trim().toUpperCase() !== normalizedVin) continue;
    if (normalizedText && String(request.description || '').trim().toLowerCase() !== normalizedText) {
      // phone + close time is enough for the default duplicate heuristic; text mismatch is advisory only
    }
    return request;
  }
  return null;
}

function createFeedback({ clientId, requestId = null, visitId = null, rating, comment = '', sourceChannel = 'telegram', createdBy = 'client' }) {
  initializeStore();
  const request = requestId ? findRequestById(requestId) : null;
  const feedback = {
    id: crypto.randomUUID(),
    clientId,
    requestId,
    visitId,
    rating,
    comment,
    sourceChannel,
    createdAt: nowIso(),
    createdBy,
    status: 'received',
    qualityCaseId: null
  };
  let qualityCase = null;
  const tx = getDb().transaction(() => {
    insertOrReplaceFeedback(feedback);
    insertCommunication({
      id: crypto.randomUUID(),
      clientId,
      requestId,
      source: sourceChannel,
      channel: sourceChannel,
      direction: 'inbound',
      payload: { action: 'feedback_received', feedbackId: feedback.id, rating, comment },
      createdAt: nowIso()
    });
    if (rating < 3) {
      qualityCase = {
        id: crypto.randomUUID(),
        clientId,
        feedbackId: feedback.id,
        requestId,
        status: 'new',
        assignedTo: request?.assignedMasterId || null,
        reasonCategory: 'low_rating',
        summary: `Автокейс по низкой оценке (${rating}/5)`,
        createdAt: nowIso(),
        updatedAt: nowIso()
      };
      insertOrReplaceQualityCase(qualityCase);
      feedback.qualityCaseId = qualityCase.id;
      feedback.status = 'escalated';
      insertOrReplaceFeedback(feedback);
      insertCommunication({
        id: crypto.randomUUID(),
        clientId,
        requestId,
        source: 'system',
        channel: 'system',
        direction: 'internal',
        payload: {
          action: 'quality_case_created_from_feedback',
          qualityCaseId: qualityCase.id,
          feedbackId: feedback.id,
          duplicateForRole: 'manager'
        },
        createdAt: nowIso()
      });
      insertRequestEvent({
        id: crypto.randomUUID(),
        eventScope: 'master_action',
        eventType: 'master_action',
        actorId: 'system',
        actorRole: 'system',
        action: 'quality_case_auto_created_from_feedback',
        requestId,
        clientId,
        payload: { qualityCaseId: qualityCase.id, feedbackId: feedback.id, assignedTo: qualityCase.assignedTo, duplicateForRole: 'manager' },
        createdAt: nowIso()
      });
    }
  });
  tx();
  return { feedback, qualityCase };
}

function createTask({ taskType, dueAt, payload = {} }) {
  initializeStore();
  const task = {
    id: crypto.randomUUID(),
    taskType,
    status: 'scheduled',
    dueAt: dueAt || nowIso(),
    createdAt: nowIso(),
    processedAt: null,
    attemptCount: 0,
    lastError: null,
    processingStartedAt: null,
    updatedAt: nowIso(),
    payload
  };
  insertOrReplaceTask(task);
  return task;
}

function listTasks(statuses = []) {
  initializeStore();
  const all = listRows('tasks').map(taskRowToEntity);
  return statuses.length ? all.filter((item) => statuses.includes(item.status)) : all;
}

function claimDueTasks({ now = new Date().toISOString(), limit = 10, stuckTimeoutMs = 300000 } = {}) {
  initializeStore();
  const nowMs = Date.parse(now);
  const allTasks = listRows('tasks').map(taskRowToEntity);
  const tx = getDb().transaction(() => {
    for (const task of allTasks) {
      if (task.status !== 'processing') continue;
      const startedAtMs = Date.parse(task.processingStartedAt || task.updatedAt || task.createdAt || now);
      if (!Number.isFinite(startedAtMs)) continue;
      if (nowMs - startedAtMs >= Math.max(1000, Number(stuckTimeoutMs) || 300000)) {
        task.status = 'scheduled';
        task.lastError = task.lastError || 'PROCESSING_RECOVERED_AS_STUCK';
        task.processingStartedAt = null;
        task.updatedAt = nowIso();
        insertOrReplaceTask(task);
      }
    }
  });
  tx();

  const due = listRows('tasks').map(taskRowToEntity)
    .filter((task) => task.status === 'scheduled' && task.dueAt <= now)
    .sort((a, b) => String(a.dueAt).localeCompare(String(b.dueAt)))
    .slice(0, limit);

  const claimTx = getDb().transaction(() => {
    due.forEach((task) => {
      task.status = 'processing';
      task.attemptCount += 1;
      task.lastError = null;
      task.processingStartedAt = nowIso();
      task.updatedAt = nowIso();
      insertOrReplaceTask(task);
    });
  });
  claimTx();
  return due;
}

function completeTask(taskId) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM tasks WHERE id = ? LIMIT 1').get(taskId);
  if (!row) return null;
  const task = taskRowToEntity(row);
  task.status = 'completed';
  task.processedAt = nowIso();
  task.processingStartedAt = null;
  task.updatedAt = nowIso();
  insertOrReplaceTask(task);
  return task;
}

function failTask(taskId, error, maxAttempts = 3) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM tasks WHERE id = ? LIMIT 1').get(taskId);
  if (!row) return null;
  const task = taskRowToEntity(row);
  task.lastError = String(error || 'unknown_error');
  task.status = task.attemptCount >= maxAttempts ? 'failed' : 'scheduled';
  task.processingStartedAt = null;
  if (task.status === 'scheduled') {
    task.dueAt = new Date(Date.now() + Math.min(task.attemptCount, 5) * 60 * 1000).toISOString();
  } else {
    task.processedAt = nowIso();
  }
  task.updatedAt = nowIso();
  insertOrReplaceTask(task);
  return task;
}

function updateQualityCaseStatus({ qualityCaseId, status, actorId, actorRole }) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM quality_cases WHERE id = ? LIMIT 1').get(qualityCaseId);
  if (!row) return null;
  const qualityCase = qualityCaseRowToEntity(row);
  qualityCase.status = status;
  qualityCase.updatedAt = nowIso();
  insertOrReplaceQualityCase(qualityCase);
  insertRequestEvent({
    id: crypto.randomUUID(),
    eventScope: 'master_action',
    eventType: 'master_action',
    actorId,
    actorRole,
    action: 'quality_case_status_changed',
    requestId: qualityCase.requestId,
    payload: { qualityCaseId, status },
    createdAt: nowIso()
  });
  return qualityCase;
}

function addQualityCaseComment({ qualityCaseId, actorId, actorRole, text }) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM quality_cases WHERE id = ? LIMIT 1').get(qualityCaseId);
  if (!row) return null;
  const qualityCase = qualityCaseRowToEntity(row);
  const comment = {
    id: crypto.randomUUID(),
    eventScope: 'quality_case',
    eventType: 'quality_case_comment',
    qualityCaseId,
    requestId: qualityCase.requestId,
    actorId,
    actorRole,
    text,
    createdAt: nowIso()
  };
  insertRequestEvent(comment);
  insertRequestEvent({
    id: crypto.randomUUID(),
    eventScope: 'master_action',
    eventType: 'master_action',
    actorId,
    actorRole,
    action: 'quality_case_comment_added',
    requestId: qualityCase.requestId,
    payload: { qualityCaseId, commentId: comment.id },
    createdAt: nowIso()
  });
  return comment;
}

function getQualityCaseCard(qualityCaseId) {
  initializeStore();
  const store = readStore();
  const qualityCase = store.qualityCases.find((item) => item.id === qualityCaseId);
  if (!qualityCase) return null;
  return {
    qualityCase,
    request: store.requests.find((item) => item.id === qualityCase.requestId) || null,
    comments: store.qualityCaseComments.filter((item) => item.qualityCaseId === qualityCaseId)
  };
}

function createReportSnapshot({ reportType, periodType, periodStart, periodEnd, metrics, summaryText, generatedBy = 'manual', sourceDataVersion = null, notes = null }) {
  initializeStore();
  const snapshot = {
    id: crypto.randomUUID(),
    reportType,
    periodType,
    periodStart,
    periodEnd,
    generatedAt: nowIso(),
    metrics,
    summaryText,
    generatedBy,
    sourceDataVersion,
    notes
  };
  insertOrReplaceReportSnapshot(snapshot);
  return snapshot;
}

function listReportSnapshots({ limit = 50 } = {}) {
  initializeStore();
  return listRows('report_snapshots', 'generated_at DESC').map(reportSnapshotRowToEntity).slice(0, limit);
}

function getReportSnapshotById(id) {
  initializeStore();
  const row = getDb().prepare('SELECT * FROM report_snapshots WHERE id = ? LIMIT 1').get(id);
  return row ? reportSnapshotRowToEntity(row) : null;
}

function resetStore() {
  shutdown();
  const dbPath = getDbPath();
  for (const candidate of [dbPath, `${dbPath}-wal`, `${dbPath}-shm`]) {
    if (fs.existsSync(candidate)) fs.unlinkSync(candidate);
  }
  runtimeState.initializedPaths.delete(dbPath);
  runtimeState.lastInitStatus = 'not_initialized';
  runtimeState.lastMigration = null;
  initializeStore();
}

function createIntegrationEvent({ sourceSystem, eventType, rawPayload, dedupeKey = null }) {
  initializeStore();
  const event = {
    id: crypto.randomUUID(),
    eventType: 'integration_event',
    sourceSystem,
    integrationEventType: eventType,
    rawPayload,
    normalizedPayload: null,
    processingStatus: 'received',
    processingAttemptCount: 0,
    lastError: null,
    createdAt: nowIso(),
    processedAt: null,
    relatedEntityType: null,
    relatedEntityId: null,
    dedupeKey
  };
  insertOrReplaceAnalyticsEvent(event);
  insertOrReplaceAnalyticsEvent({
    id: crypto.randomUUID(),
    parentEventId: event.id,
    eventType: 'integration_event_log',
    sourceSystem,
    processingStatus: 'received',
    message: 'Event received',
    createdAt: nowIso(),
    processedAt: null,
    eventId: event.id
  });
  return analyticsEventRowToEntity(getDb().prepare('SELECT * FROM analytics_events WHERE id = ?').get(event.id));
}

function updateIntegrationEvent(eventId, patch = {}, logMessage = null) {
  initializeStore();
  const row = getDb().prepare(`SELECT * FROM analytics_events WHERE id = ? AND event_type = 'integration_event' LIMIT 1`).get(eventId);
  if (!row) return null;
  const event = analyticsEventRowToEntity(row);
  Object.assign(event, patch);
  if (patch.eventType && patch.eventType !== 'integration_event') delete event.eventType;
  if (patch.processingStatus === 'processed' || patch.processingStatus === 'failed' || patch.processingStatus === 'ignored') {
    event.processedAt = event.processedAt || nowIso();
  }
  event.eventType = 'integration_event';
  insertOrReplaceAnalyticsEvent(event);
  if (logMessage || patch.processingStatus) {
    insertOrReplaceAnalyticsEvent({
      id: crypto.randomUUID(),
      parentEventId: eventId,
      eventType: 'integration_event_log',
      sourceSystem: event.sourceSystem,
      processingStatus: patch.processingStatus || event.processingStatus,
      message: logMessage || null,
      createdAt: nowIso(),
      processedAt: null,
      eventId
    });
  }
  return analyticsEventRowToEntity(getDb().prepare('SELECT * FROM analytics_events WHERE id = ?').get(eventId));
}

function getIntegrationEventById(eventId) {
  initializeStore();
  const row = getDb().prepare(`SELECT * FROM analytics_events WHERE id = ? AND event_type = 'integration_event' LIMIT 1`).get(eventId);
  return row ? analyticsEventRowToEntity(row) : null;
}

function listIntegrationEvents({ status, sourceSystem, limit = 20 } = {}) {
  initializeStore();
  let sql = `SELECT * FROM analytics_events WHERE event_type = 'integration_event'`;
  const params = [];
  if (status) {
    sql += ' AND processing_status = ?';
    params.push(status);
  }
  if (sourceSystem) {
    sql += ' AND source_system = ?';
    params.push(sourceSystem);
  }
  sql += ' ORDER BY created_at DESC LIMIT ?';
  params.push(limit);
  return getDb().prepare(sql).all(...params).map(analyticsEventRowToEntity);
}

function getIntegrationEventCard(eventId) {
  initializeStore();
  const event = getIntegrationEventById(eventId);
  if (!event) return null;
  const logs = getDb().prepare(`
    SELECT * FROM analytics_events
    WHERE event_type = 'integration_event_log' AND parent_event_id = ?
    ORDER BY created_at ASC
  `).all(eventId).map(analyticsEventRowToEntity);
  return { event, logs };
}

function applyEntitySyncMetadata({ collection, entityId, metadata = {} }) {
  initializeStore();
  const tableMap = {
    clients: { table: 'clients', rowToEntity: clientRowToEntity, writer: insertOrReplaceClient },
    vehicles: { table: 'vehicles', rowToEntity: vehicleRowToEntity, writer: insertOrReplaceVehicle },
    requests: { table: 'requests', rowToEntity: requestRowToEntity, writer: insertOrReplaceRequest },
    recommendations: { table: 'recommendations', rowToEntity: recommendationRowToEntity, writer: insertOrReplaceRecommendation }
  };
  const mapping = tableMap[collection];
  if (!mapping) return null;
  const row = getDb().prepare(`SELECT * FROM ${mapping.table} WHERE id = ? LIMIT 1`).get(entityId);
  if (!row) return null;
  const entity = mapping.rowToEntity(row);
  entity.externalIds = { ...(entity.externalIds || {}), ...(metadata.externalIds || {}) };
  if (metadata.sourceSystem) entity.sourceSystem = metadata.sourceSystem;
  if (metadata.sourceOfTruth) entity.sourceOfTruth = metadata.sourceOfTruth;
  if (Object.hasOwn(metadata, 'lastSyncedAt')) entity.lastSyncedAt = metadata.lastSyncedAt;
  if (Object.hasOwn(metadata, 'localPendingChanges')) entity.localPendingChanges = metadata.localPendingChanges;
  if (Object.hasOwn(metadata, 'needsManualReview')) entity.needsManualReview = metadata.needsManualReview;
  entity.updatedAt = nowIso();
  mapping.writer(entity);
  return entity;
}



function listRequestEvents({ requestId = null, since = null, until = null, eventType = null, actorId = null, limit = 100 } = {}) {
  initializeStore();
  return listRows('request_events', 'created_at DESC')
    .map(requestEventRowToEntity)
    .filter((item) => {
      const createdAt = Date.parse(item.createdAt || '');
      if (requestId && item.requestId !== requestId) return false;
      if (eventType && item.canonicalEventType !== eventType && item.eventType !== eventType && item.type !== eventType) return false;
      if (actorId && item.actorId !== actorId) return false;
      if (since && (!Number.isFinite(createdAt) || createdAt < Date.parse(since))) return false;
      if (until && (!Number.isFinite(createdAt) || createdAt > Date.parse(until))) return false;
      return true;
    })
    .slice(0, limit);
}

function listOperationalLogs({ requestId = null, since = null, eventType = null, bot = null, limit = 100 } = {}) {
  initializeStore();
  const events = listRequestEvents({ requestId, since, eventType, limit });
  const communications = listRows('communications', 'created_at DESC').map(communicationRowToEntity)
    .filter((item) => {
      if (requestId && item.requestId !== requestId) return false;
      if (since && Date.parse(item.createdAt || '') < Date.parse(since)) return false;
      if (bot && String(item.source || item.channel || '').indexOf(bot) === -1) return false;
      return true;
    })
    .slice(0, limit);
  const integration = listRows('analytics_events', 'created_at DESC').map(analyticsEventRowToEntity)
    .filter((item) => {
      if (requestId && item.requestId !== requestId) return false;
      if (since && Date.parse(item.createdAt || '') < Date.parse(since)) return false;
      if (bot && String(item.channel || item.platform || item.sourceSystem || '').indexOf(bot) === -1) return false;
      if (eventType && item.eventType !== eventType) return false;
      return item.eventType.includes('webhook') || item.eventType.includes('integration') || item.status === 'error' || item.processingStatus === 'failed';
    })
    .slice(0, limit);
  return { events, communications, integration };
}

function replaceStore(store) {
  const tempDir = fs.mkdtempSync(path.join(path.dirname(getDbPath()), 'sqlite-import-'));
  const tempJsonPath = path.join(tempDir, 'import.json');
  fs.writeFileSync(tempJsonPath, JSON.stringify(store, null, 2));
  try {
    importLegacyJsonToSqlite(tempJsonPath);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
  return readStore();
}

function listTables() {
  initializeStore();
  return getDb().prepare(`SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC`).all().map((row) => row.name);
}

const api = {
  get DB_PATH() {
    return getDbPath();
  },
  getDbPath,
  getLegacyJsonPath,
  getDbRuntimeInfo,
  initializeStore,
  importLegacyJsonToSqlite,
  upsertClient,
  upsertVehicle,
  createRequest,
  createAnalyticsEvent,
  createCommunicationEvent,
  listRequests,
  listRecommendations,
  markRecommendationInterest,
  upsertRecommendationFromSync,
  resolveStaffUser,
  listStaffUsers,
  createStaffUser,
  revokeStaffUser,
  recordMasterAction,
  recordRequestEvent,
  updateRequestStatus,
  updateRequestAssignment,
  addInternalComment,
  addClientNote,
  searchCRM,
  getClientCard,
  getRequestCard,
  listQualityCases,
  createQualityCase,
  updateQualityCaseStatus,
  addQualityCaseComment,
  getQualityCaseCard,
  findClientByTelegramId,
  findClientByMaxId,
  findRequestById,
  findRecentDuplicateRequest,
  markRequestDuplicate,
  createFeedback,
  createTask,
  listTasks,
  claimDueTasks,
  completeTask,
  failTask,
  createReportSnapshot,
  listReportSnapshots,
  getReportSnapshotById,
  resetStore,
  readStore,
  createIntegrationEvent,
  updateIntegrationEvent,
  getIntegrationEventById,
  listIntegrationEvents,
  getIntegrationEventCard,
  listRequestEvents,
  listOperationalLogs,
  applyEntitySyncMetadata,
  listTables,
  replaceStore,
  shutdown,
  normalizePhone10,
  reactivateWaitingDecisionRequest
};

module.exports = api;
