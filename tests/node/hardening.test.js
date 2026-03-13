const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const db = require('../../src/infrastructure/db');
const { createScheduler } = require('../../src/infrastructure/scheduler');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');

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
      body: JSON.stringify({ fullName: 'Иван', phone: '+79990000000', wasClientBefore: 'yes', brand: 'Lada', model: 'Granta', year: '2019', vin: 'VIN-H', description: 'ok' })
    });
    assert.equal(ok.status, 201);
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

  const store = db.readStore();
  const task = store.tasks.find((item) => item.id === dueTask.id);
  task.status = 'processing';
  task.attemptCount = 0;
  task.processingStartedAt = new Date(Date.now() - 1000).toISOString();
  task.dueAt = new Date(Date.now() - 1000).toISOString();
  fs.writeFileSync(db.DB_PATH, JSON.stringify(store, null, 2));

  const recovered = db.claimDueTasks({ limit: 10, stuckTimeoutMs: 100 });
  assert.equal(recovered.some((item) => item.id === dueTask.id), true);
});
