const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');

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

test('regression: health and all telegram webhooks remain alive', async () => {
  await withServer(async (base) => {
    const health = await fetch(`${base}/health`);
    assert.equal(health.status, 200);

    const client = await fetch(`${base}/telegram/client_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 1 }, from: { id: 1 } } }) });
    const master = await fetch(`${base}/telegram/master_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 2 }, from: { id: 2 } } }) });
    const integration = await fetch(`${base}/telegram/integration_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 3 }, from: { id: 3 } } }) });

    assert.equal(client.status, 200);
    assert.equal(master.status, 200);
    assert.equal(integration.status, 200);
  });
});
