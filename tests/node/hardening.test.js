const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const db = require('../../src/infrastructure/db');
const { createScheduler } = require('../../src/infrastructure/scheduler');
const { createServer, normalizePhone10, validateClientRequestPayload } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const { ensureReferenceDatasetRuntime } = require('../../src/infrastructure/referenceDatasetRuntime');

async function withServer(run) {
  db.resetStore();
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const port = server.address().port;
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test('client request route rejects invalid json and required fields', async () => {
  await withServer(async (base) => {
    const invalid = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{broken'
    });
    assert.equal(invalid.status, 400);

    const missingFields = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: 'x' })
    });
    assert.equal(missingFields.status, 400);

    const ok = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fullName: 'Иван', phone: '9990000000', wasClientBefore: 'yes', brand: 'Lada', model: 'Granta', year: '2019', vin: 'VIN-H', description: 'ok' })
    });
    assert.equal(ok.status, 201);

    const invalidPhone = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fullName: 'Иван', phone: '12345', wasClientBefore: 'yes', brand: 'Lada', model: 'Granta', year: '2019', vin: 'VIN-H', description: 'bad phone' })
    });
    assert.equal(invalidPhone.status, 400);

    const invalidLookup = await fetch(`${base}/api/client/requests?phone=12345`);
    assert.equal(invalidLookup.status, 400);
  });
});

test('webhooks reject invalid json payload', async () => {
  await withServer(async (base) => {
    const response = await fetch(`${base}/telegram/client_bot/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{broken'
    });
    assert.equal(response.status, 400);
  });
});

test('scheduler prevents double run and recovers stuck tasks', async () => {
  db.resetStore();
  const dueTask = db.createTask({ taskType: 'feedback_request', dueAt: new Date(Date.now() - 5000).toISOString(), payload: {} });

  let executions = 0;
  const scheduler = createScheduler({
    db,
    logger: { warn() {}, error() {} },
    handlers: {
      async feedback_request() {
        executions += 1;
      }
    },
    batchSize: 1,
    maxAttempts: 2,
    stuckTimeoutMs: 100
  });

  const [first, second] = await Promise.all([scheduler.runOnce(), scheduler.runOnce()]);
  assert.equal(first.processed + second.processed, 1);
  assert.equal(executions, 1);

  const stuckStore = db.readStore();
  const task = stuckStore.tasks.find((item) => item.id === dueTask.id);
  task.status = 'processing';
  task.attemptCount = 0;
  task.processingStartedAt = new Date(Date.now() - 1000).toISOString();
  task.dueAt = new Date(Date.now() - 1000).toISOString();
  db.replaceStore(stuckStore);

  const recovered = db.claimDueTasks({ limit: 10, stuckTimeoutMs: 100 });
  assert.equal(recovered.some((item) => item.id === dueTask.id), true);
});

test('normalizePhone10 and server validation keep only 10-digit phones', () => {
  assert.equal(normalizePhone10('+79991112233'), '9991112233');
  assert.equal(normalizePhone10('8 (999) 111-22-33'), '9991112233');
  assert.equal(normalizePhone10('7 999 111 22 33'), '9991112233');
  assert.equal(normalizePhone10('9991112233'), '9991112233');
  assert.equal(normalizePhone10('12345'), '12345');
  assert.equal(normalizePhone10('123456789012345'), '123456789012345');
  assert.equal(normalizePhone10('мусор +7 (999) 111-22-33'), '9991112233');
  assert.deepEqual(validateClientRequestPayload({ fullName: 'Иван', phone: '9991112233', wasClientBefore: 'yes' }, 'data_change_request'), ['changeDetails is required']);
  assert.ok(validateClientRequestPayload({ phone: '12345' }, 'service_request').includes('phone must contain exactly 10 digits'));
});

test('db path follows env and initializes missing sqlite store explicitly', () => {
  const originalFile = process.env.DB_FILE_PATH;
  const originalSqlite = process.env.DB_SQLITE_PATH;
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'telegram-reviews-bot-'));
  const tempPath = path.join(tempDir, 'nested', 'db.sqlite');
  process.env.DB_SQLITE_PATH = tempPath;
  delete process.env.DB_FILE_PATH;

  try {
    db.shutdown();
    const infoBefore = db.getDbRuntimeInfo();
    assert.equal(infoBefore.path, tempPath);
    assert.equal(infoBefore.exists, false);
    db.resetStore();
    const infoAfter = db.getDbRuntimeInfo();
    assert.equal(infoAfter.path, tempPath);
    assert.equal(infoAfter.exists, true);
    assert.ok(db.listTables().includes('clients'));
    assert.ok(db.listTables().includes('analytics_events'));
  } finally {
    db.shutdown();
    if (originalSqlite === undefined) delete process.env.DB_SQLITE_PATH;
    else process.env.DB_SQLITE_PATH = originalSqlite;
    if (originalFile === undefined) delete process.env.DB_FILE_PATH;
    else process.env.DB_FILE_PATH = originalFile;
  }
});

test('reference dataset runtime self-check restores expected path from embedded seed', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'reference-runtime-seed-'));
  const expectedPath = path.join(tmpDir, 'data', 'reference', 'client_vehicle_bridge', 'lira_normalized_database.sqlite');
  const seedPath = path.join(tmpDir, 'seed', 'lira.sqlite');
  fs.mkdirSync(path.dirname(seedPath), { recursive: true });
  fs.writeFileSync(seedPath, Buffer.from('seed-reference-sqlite-payload'));

  const prevSeedPath = process.env.REFERENCE_CLIENT_LOOKUP_EMBEDDED_DATASET_PATH;
  process.env.REFERENCE_CLIENT_LOOKUP_EMBEDDED_DATASET_PATH = seedPath;
  try {
    const result = ensureReferenceDatasetRuntime({
      logger: { info() {}, warn() {} },
      expectedPath
    });
    assert.equal(result.datasetExists, true);
    assert.equal(result.datasetReadable, true);
    assert.equal(result.copied, true);
    assert.equal(result.copiedFrom, seedPath);
    assert.equal(fs.existsSync(expectedPath), true);
    assert.equal(fs.readFileSync(expectedPath).toString('utf8'), 'seed-reference-sqlite-payload');
  } finally {
    if (prevSeedPath === undefined) delete process.env.REFERENCE_CLIENT_LOOKUP_EMBEDDED_DATASET_PATH;
    else process.env.REFERENCE_CLIENT_LOOKUP_EMBEDDED_DATASET_PATH = prevSeedPath;
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
