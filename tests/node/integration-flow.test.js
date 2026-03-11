const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');
const { integrationService } = require('../../src/core/application');

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

test('integration event flow processes email and stores result', async () => {
  await withServer(async (base) => {
    const response = await fetch(`${base}/api/integrations/email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: 'user@example.com',
        subject: 'Нужна запись на сервис',
        body: 'Имя: Петров Петр\nТелефон: +79995554433\nVIN: XTAZZZ12345678901\nНужна диагностика',
        receivedAt: new Date().toISOString(),
        attachments: [{ name: 'photo.jpg' }],
        threadId: 'thr-1'
      })
    });

    assert.equal(response.status, 201);
    const event = await response.json();
    assert.equal(event.processingStatus, 'processed');
    assert.equal(event.eventType, integrationService.INTEGRATION_EVENT_TYPES.EMAIL_REQUEST_RECEIVED);

    const state = db.readStore();
    assert.equal(state.integrationEvents.length, 1);
    assert.equal(state.requests.length, 1);
    assert.equal(state.communicationEvents.length, 1);
    assert.equal(state.clients[0].sourceSystem, 'email');
    assert.equal(Boolean(state.clients[0].externalIds.email_thread), true);
    assert.equal(state.requests[0].sourceChannel, 'email');
  });
});

test('integration fail + retry flow works', async () => {
  db.resetStore();
  const event = db.createIntegrationEvent({
    sourceSystem: 'email',
    eventType: 'email_request_received',
    rawPayload: { from: 'bad@example.com', subject: 'x', body: null }
  });
  db.updateIntegrationEvent(event.id, { processingStatus: 'failed', lastError: 'test_error' }, 'forced fail');

  const retried = integrationService.retryIntegrationEvent(event.id);
  assert.equal(retried.processingAttemptCount >= 1, true);
  assert.equal(['processed', 'failed'].includes(retried.processingStatus), true);
});

test('manual and one_c imports are accepted with skeleton behavior', async () => {
  await withServer(async (base) => {
    const manualResponse = await fetch(`${base}/api/integrations/manual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceSystem: 'manual_import',
        eventType: 'manual_request_import',
        rawPayload: {
          from: 'manual@example.com',
          subject: 'manual import service',
          body: 'Имя: Сидоров\nТелефон: +79991112233\nservice'
        }
      })
    });
    assert.equal(manualResponse.status, 201);

    const oneCResponse = await fetch(`${base}/api/integrations/one-c/client`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ externalId: '1c-client-1', fullName: 'Иван', phone: '+79990001122' })
    });
    assert.equal(oneCResponse.status, 201);
    const onecEvent = await oneCResponse.json();
    assert.equal(['ignored', 'normalized', 'processed'].includes(onecEvent.processingStatus), true);
  });
});
