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

async function sendIntegration(base, text, fromId = 9001) {
  const response = await fetch(`${base}/telegram/integration_bot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: { text, chat: { id: fromId }, from: { id: fromId } } })
  });
  return response.json();
}

test('integration bot supports start list failed and retry commands', async () => {
  await withServer(async (base) => {
    const start = await sendIntegration(base, '/start');
    assert.equal(start.action, 'start');

    const created = await fetch(`${base}/api/integrations/manual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceSystem: 'manual_import',
        eventType: 'manual_request_import',
        rawPayload: { from: 'x@y.com', subject: 'service', body: 'Телефон: +78889990000' }
      })
    }).then((res) => res.json());

    db.updateIntegrationEvent(created.id, { processingStatus: 'failed', lastError: 'forced' }, 'forced fail');

    const events = await sendIntegration(base, '/events');
    assert.equal(events.action, 'events');
    assert.equal(events.items.length > 0, true);

    const failed = await sendIntegration(base, '/failed');
    assert.equal(failed.action, 'failed');
    assert.equal(failed.items.length > 0, true);

    const card = await sendIntegration(base, `/event ${created.id}`);
    assert.equal(card.action, 'event_card');

    const retry = await sendIntegration(base, `/retry ${created.id}`);
    assert.equal(retry.ok, true);

    const stats = await sendIntegration(base, '/stats');
    assert.equal(stats.action, 'stats');
    assert.equal(Object.hasOwn(stats, 'failed'), true);
  });
});
