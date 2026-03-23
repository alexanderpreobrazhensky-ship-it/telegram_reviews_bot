const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');
const { MAIN_MENU_LABELS, buildHelpText, buildSelfcheck } = require('../../src/interfaces/integration_bot');

async function withServer(run) {
  db.resetStore();
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const port = server.address().port;
  try {
    await run(`http://127.0.0.1:${port}`, config);
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

async function sendIntegrationCallback(base, callbackData, fromId = 9001) {
  const response = await fetch(`${base}/telegram/integration_bot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      callback_query: {
        id: `cb-${fromId}`,
        data: callbackData,
        from: { id: fromId },
        message: { text: 'callback', chat: { id: fromId } }
      }
    })
  });
  return response.json();
}

test('integration bot supports start help selfcheck list failed pending stats and retry/ignore flows', async () => {
  await withServer(async (base) => {
    const start = await sendIntegration(base, '/start@integration_bot');
    assert.equal(start.action, 'start');
    assert.deepEqual(start.buttons, Object.values(MAIN_MENU_LABELS));

    const help = await sendIntegration(base, '/help');
    assert.equal(help.action, 'help');
    assert.match(help.text, /Integration Bot/i);
    assert.match(help.text, /Самодиагностика/i);

    const selfcheck = await sendIntegration(base, '/selfcheck');
    assert.equal(selfcheck.action, 'selfcheck');
    assert.equal(typeof selfcheck.overallStatus, 'string');
    assert.equal(Array.isArray(selfcheck.checks), true);
    assert.equal(Object.hasOwn(selfcheck.stats, 'pending'), true);

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
    const pendingEvent = db.createIntegrationEvent({
      sourceSystem: 'manual_import',
      eventType: 'manual_request_import',
      rawPayload: { subject: 'pending case', body: 'Телефон: +78889990001' }
    });

    const events = await sendIntegration(base, '/events');
    assert.equal(events.action, 'events');
    assert.equal(events.items.length >= 2, true);

    const failed = await sendIntegration(base, '/failed');
    assert.equal(failed.action, 'failed');
    assert.equal(failed.items.some((item) => item.id === created.id), true);

    const pending = await sendIntegration(base, '/pending');
    assert.equal(pending.action, 'pending');
    assert.equal(pending.items.some((item) => item.id === pendingEvent.id), true);

    const card = await sendIntegration(base, `/event ${created.id}`);
    assert.equal(card.action, 'event_card');
    assert.equal(card.event.id, created.id);

    const retry = await sendIntegration(base, `/retry ${created.id}`);
    assert.equal(retry.ok, true);

    const ignored = await sendIntegration(base, `/ignore ${created.id}`);
    assert.equal(ignored.ok, true);

    const stats = await sendIntegration(base, '/stats');
    assert.equal(stats.action, 'stats');
    assert.equal(typeof stats.total, 'number');
    assert.equal(Object.hasOwn(stats, 'failed'), true);
    assert.equal(Object.hasOwn(stats, 'pending'), true);
  });
});

test('integration bot supports button text and inline callbacks for main scenario', async () => {
  await withServer(async (base) => {
    const created = db.createIntegrationEvent({
      sourceSystem: 'manual_import',
      eventType: 'manual_request_import',
      rawPayload: { subject: 'manual', body: 'Телефон: +78889990000' }
    });
    db.updateIntegrationEvent(created.id, { processingStatus: 'failed', lastError: 'forced callback fail' }, 'forced fail');

    const instruction = await sendIntegration(base, MAIN_MENU_LABELS.help);
    assert.equal(instruction.action, 'help');

    const diag = await sendIntegration(base, MAIN_MENU_LABELS.selfcheck);
    assert.equal(diag.action, 'selfcheck');

    const allEvents = await sendIntegration(base, MAIN_MENU_LABELS.events);
    assert.equal(allEvents.action, 'events');

    const failed = await sendIntegration(base, MAIN_MENU_LABELS.failed);
    assert.equal(failed.action, 'failed');

    const pending = await sendIntegration(base, MAIN_MENU_LABELS.pending);
    assert.equal(pending.action, 'pending');

    const stats = await sendIntegration(base, MAIN_MENU_LABELS.stats);
    assert.equal(stats.action, 'stats');

    const details = await sendIntegrationCallback(base, `int:event:${created.id}`);
    assert.equal(details.action, 'event_card');
    assert.equal(details.event.id, created.id);

    db.updateIntegrationEvent(created.id, { processingStatus: 'failed', lastError: 'forced callback fail again' }, 'forced fail again');
    const retry = await sendIntegrationCallback(base, `int:retry:${created.id}`);
    assert.equal(retry.action, 'retry');
    assert.equal(retry.ok, true);

    const ignore = await sendIntegrationCallback(base, `int:ignore:${created.id}`);
    assert.equal(ignore.action, 'ignored');
    assert.equal(ignore.ok, true);
  });
});

test('integration bot returns clear messages for empty data and invalid command arguments', async () => {
  await withServer(async (base) => {
    const events = await sendIntegration(base, '/events');
    assert.equal(events.action, 'events');
    assert.equal(events.items.length, 0);
    assert.match(events.text, /Нет событий интеграции/i);

    const failed = await sendIntegration(base, '/failed');
    assert.equal(failed.action, 'failed');
    assert.equal(failed.items.length, 0);
    assert.match(failed.text, /Нет ошибок интеграции/i);

    const pending = await sendIntegration(base, '/pending');
    assert.equal(pending.action, 'pending');
    assert.equal(pending.items.length, 0);
    assert.match(pending.text, /Нет pending событий/i);

    const stats = await sendIntegration(base, '/stats');
    assert.equal(stats.action, 'stats');
    assert.match(stats.text, /пока пуста/i);

    const eventWithoutId = await sendIntegration(base, '/event');
    assert.equal(eventWithoutId.ok, false);
    assert.equal(eventWithoutId.error, 'EVENT_ID_REQUIRED');

    const retryWithoutId = await sendIntegration(base, '/retry');
    assert.equal(retryWithoutId.ok, false);
    assert.equal(retryWithoutId.error, 'EVENT_ID_REQUIRED');

    const ignoreWithoutId = await sendIntegration(base, '/ignore');
    assert.equal(ignoreWithoutId.ok, false);
    assert.equal(ignoreWithoutId.error, 'EVENT_ID_REQUIRED');

    const unknown = await sendIntegration(base, '/unknown');
    assert.equal(unknown.action, 'unknown');
    assert.match(unknown.text, /Неизвестная команда/i);
  });
});

test('integration bot helper texts stay aligned with implemented functionality', () => {
  const helpText = buildHelpText();
  assert.match(helpText, /\/selfcheck или \/diag/);
  assert.match(helpText, /Повторить/);
  assert.match(helpText, /Игнорировать/);

  const payload = buildSelfcheck({ config: loadConfig() });
  assert.equal(typeof payload.text, 'string');
  assert.equal(Array.isArray(payload.checks), true);
  assert.equal(Object.hasOwn(payload.stats, 'total'), true);
});
