const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const db = require('../../src/infrastructure/db');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');

function withTempDb(run) {
  const originalSqlite = process.env.DB_SQLITE_PATH;
  const originalFile = process.env.DB_FILE_PATH;
  const originalImport = process.env.DB_JSON_IMPORT_PATH;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'telegram-reviews-sqlite-'));
  process.env.DB_SQLITE_PATH = path.join(dir, 'data.sqlite');
  process.env.DB_FILE_PATH = path.join(dir, 'legacy-db.json');
  process.env.DB_JSON_IMPORT_PATH = process.env.DB_FILE_PATH;
  db.shutdown();

  const restore = () => {
    db.shutdown();
    if (originalSqlite === undefined) delete process.env.DB_SQLITE_PATH;
    else process.env.DB_SQLITE_PATH = originalSqlite;
    if (originalFile === undefined) delete process.env.DB_FILE_PATH;
    else process.env.DB_FILE_PATH = originalFile;
    if (originalImport === undefined) delete process.env.DB_JSON_IMPORT_PATH;
    else process.env.DB_JSON_IMPORT_PATH = originalImport;
  };

  try {
    const result = run({ dir, sqlitePath: process.env.DB_SQLITE_PATH, jsonPath: process.env.DB_JSON_IMPORT_PATH });
    if (result && typeof result.then === 'function') {
      return result.finally(restore);
    }
    restore();
    return result;
  } catch (error) {
    restore();
    throw error;
  }
}

test('sqlite init creates database file and required tables', () => withTempDb(({ sqlitePath }) => {
  assert.equal(fs.existsSync(sqlitePath), false);
  const info = db.initializeStore();
  assert.equal(info.type, 'sqlite');
  assert.equal(fs.existsSync(sqlitePath), true);
  assert.equal(db.listTables().includes('clients'), true);
  assert.equal(db.listTables().includes('requests'), true);
  assert.equal(db.listTables().includes('analytics_events'), true);
}));

test('sqlite persistence can create, read, and update clients and requests', () => withTempDb(() => {
  db.resetStore();
  const client = db.upsertClient({ fullName: 'Иван Петров', phone: '+7 (999) 123-45-67', telegramId: '42' });
  assert.equal(client.phone, '9991234567');

  const updatedClient = db.upsertClient({ fullName: 'Иван Петров Обновленный', phone: '8 999 123 45 67', telegramId: '42' });
  assert.equal(updatedClient.fullName, 'Иван Петров Обновленный');
  assert.equal(updatedClient.phone, '9991234567');

  const vehicle = db.upsertVehicle({ clientId: client.id, brand: 'Lada', model: 'Vesta', year: '2024', vin: 'VIN-SQL-1' });
  const request = db.createRequest({
    clientId: client.id,
    vehicleId: vehicle.id,
    requestType: 'service_request',
    description: 'Нужна диагностика',
    sourceChannel: 'webapp'
  });

  const progress = db.updateRequestStatus({ requestId: request.id, toStatus: 'assigned', actorId: 'master-1', actorRole: 'master' });
  assert.equal(progress.request.status, 'assigned');

  const stored = db.readStore();
  assert.equal(stored.clients.length, 1);
  assert.equal(stored.requests.length, 1);
  assert.equal(stored.requestStatusHistory.length, 2);
  assert.equal(stored.clients[0].phone, '9991234567');
  assert.equal(stored.requests[0].status, 'assigned');
  assert.equal(stored.requestEvents.filter((item) => item.requestId === request.id && item.eventType === 'request_status_changed').length, 2);
  const statusEvent = stored.requestStatusHistory.find((item) => item.requestId === request.id && item.newStatus === 'assigned');
  assert.equal(statusEvent.oldStatus, 'new');
  assert.equal(statusEvent.actor, 'master-1');
}));

test('sqlite migration imports legacy JSON store on init', () => withTempDb(({ jsonPath, sqlitePath }) => {
  fs.mkdirSync(path.dirname(jsonPath), { recursive: true });
  fs.writeFileSync(jsonPath, JSON.stringify({
    clients: [{ id: 'c1', fullName: 'Legacy Client', phone: '9991112233', telegramId: '5', maxId: null, preferredChannel: 'telegram', createdAt: '2026-01-01T00:00:00.000Z' }],
    vehicles: [{ id: 'v1', clientId: 'c1', brand: 'Kia', model: 'Rio', year: '2020', vin: 'VIN-LEGACY', plateNumber: 'A123AA', createdAt: '2026-01-01T00:00:00.000Z' }],
    requests: [{ id: 'r1', clientId: 'c1', vehicleId: 'v1', requestType: 'service_request', status: 'new', description: 'Legacy request', sourceChannel: 'webapp', assignedMasterId: null, lostReason: null, createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z', payload: {} }],
    communicationEvents: [{ id: 'ce1', clientId: 'c1', requestId: 'r1', source: 'webapp', channel: 'webapp', direction: 'inbound', payload: { action: 'request_created' }, createdAt: '2026-01-01T00:00:00.000Z' }],
    integrationEvents: [{ id: 'ie1', sourceSystem: 'email', eventType: 'email_request_received', rawPayload: { body: 'x' }, normalizedPayload: null, processingStatus: 'processed', processingAttemptCount: 1, lastError: null, createdAt: '2026-01-01T00:00:00.000Z', processedAt: '2026-01-01T00:00:01.000Z', relatedEntityType: 'request', relatedEntityId: 'r1', dedupeKey: 'd1' }],
    integrationEventLogs: [{ id: 'iel1', eventId: 'ie1', status: 'processed', message: 'ok', createdAt: '2026-01-01T00:00:01.000Z' }],
    recommendations: [],
    recommendationSync: { lastSyncAt: null, source: null },
    staffUsers: [],
    requestStatusHistory: [{ id: 'h1', requestId: 'r1', fromStatus: null, toStatus: 'new', changedBy: 'system', changedByRole: 'system', reason: null, createdAt: '2026-01-01T00:00:00.000Z' }],
    requestInternalComments: [],
    clientInternalNotes: [],
    masterActions: [],
    qualityCases: [],
    qualityCaseComments: [],
    feedback: [],
    tasks: [],
    reportSnapshots: []
  }, null, 2));

  const info = db.initializeStore();
  assert.equal(info.initStatus, 'migrated_from_json');
  assert.equal(fs.existsSync(sqlitePath), true);

  const state = db.readStore();
  assert.equal(state.clients.length, 1);
  assert.equal(state.requests.length, 1);
  assert.equal(state.communicationEvents.length, 1);
  assert.equal(state.integrationEvents.length, 1);
  assert.equal(state.integrationEventLogs.length, 1);
  assert.equal(state.clients[0].fullName, 'Legacy Client');
}));

test('integration flow survives restart with sqlite persistence', async () => withTempDb(async () => {
  db.resetStore();
  const serverA = createServer({ config: loadConfig(), logger });
  await new Promise((resolve) => serverA.listen(0, resolve));
  const base = `http://127.0.0.1:${serverA.address().port}`;

  const response = await fetch(`${base}/api/client/requests/service`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fullName: 'Рестарт Клиент',
      phone: '9990000009',
      wasClientBefore: 'yes',
      brand: 'Toyota',
      model: 'Camry',
      year: '2022',
      vin: 'VIN-RESTART-1',
      description: 'Проверка после рестарта'
    })
  });
  assert.equal(response.status, 201);
  const created = await response.json();

  await new Promise((resolve) => serverA.close(resolve));
  db.shutdown();

  const serverB = createServer({ config: loadConfig(), logger });
  await new Promise((resolve) => serverB.listen(0, resolve));
  try {
    const persisted = db.findRequestById(created.id);
    assert.ok(persisted);
    assert.equal(persisted.description, 'Проверка после рестарта');

    const state = db.readStore();
    assert.equal(state.requests.length, 1);
    assert.equal(state.clients.length, 1);
    assert.equal(state.clients[0].phone, '9990000009');
  } finally {
    await new Promise((resolve) => serverB.close(resolve));
  }
}));
