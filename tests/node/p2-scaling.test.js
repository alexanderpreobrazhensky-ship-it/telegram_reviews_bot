const test = require('node:test');
const assert = require('node:assert/strict');
const db = require('../../src/infrastructure/db');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const { withRetry } = require('../../src/infrastructure/retry');
const { serializeCsv } = require('../../src/infrastructure/export');

async function withServer(run, env = {}) {
  const previous = new Map(Object.keys(env).map((key) => [key, process.env[key]]));
  for (const [key, value] of Object.entries(env)) process.env[key] = value;
  db.resetStore();
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run({ base, config });
  } finally {
    await new Promise((resolve) => server.close(resolve));
    for (const [key, value] of previous.entries()) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('p2 export endpoint returns csv for authorized admin with filters', async () => {
  await withServer(async ({ base }) => {
    const client = db.upsertClient({ fullName: 'Export Client', phone: '9991230001', telegramId: '501' });
    const request = db.createRequest({
      clientId: client.id,
      vehicleId: null,
      requestType: 'service_request',
      description: 'Export me',
      sourceChannel: 'webapp'
    });
    db.updateRequestAssignment({ requestId: request.id, assignedTo: 'master-77', assignedBy: 'admin-1', actorId: 'admin-1', actorRole: 'admin' });

    const response = await fetch(`${base}/internal/export?admin_id=admin-1&status=new&format=csv`);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type') || '', /text\/csv/);
    const body = await response.text();
    assert.match(body, /id,created_at,status,channel,request_type,phone,assigned_to/);
    assert.match(body, /9991230001/);
    assert.match(body, /master-77/);
  }, { INTERNAL_ADMIN_WHITELIST: 'admin-1' });
});

test('p2 duplicate detection keeps UX working and marks the second request', async () => {
  await withServer(async ({ base }) => {
    const payload = {
      fullName: 'Duplicate Client',
      phone: '9990000012',
      wasClientBefore: 'yes',
      brand: 'VW',
      model: 'Polo',
      year: '2020',
      vin: 'VIN-DUP-001',
      description: 'Duplicate request test'
    };

    const first = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    assert.equal(first.status, 201);
    const createdA = await first.json();

    const second = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    assert.equal(second.status, 201);
    const createdB = await second.json();
    assert.equal(createdB.deduplicated, true);
    assert.notEqual(createdB.id, createdA.id);
    assert.equal(createdB.duplicateOfRequestId, createdA.id);

    const store = db.readStore();
    assert.ok(store.requestEvents.some((event) => event.requestId === createdB.id && event.canonicalEventType === 'duplicate_detected'));
    assert.ok(store.analyticsEvents.some((event) => event.eventType === 'request_duplicate_detected' && event.requestId === createdB.id));
  });
});

test('p2 native contact payload is accepted by request endpoint', async () => {
  await withServer(async ({ base }) => {
    const response = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fullName: 'Native Contact Client',
        phone: '',
        nativeContact: { phoneNumber: '+7 (999) 555-44-33', source: 'max_webapp_requestContact' },
        wasClientBefore: 'yes',
        brand: 'Kia',
        model: 'Rio',
        year: '2022',
        vin: 'VIN-NATIVE-1',
        description: 'Use native contact',
        sourceChannel: 'max_webapp'
      })
    });
    assert.equal(response.status, 201);
    const created = await response.json();
    const card = db.getRequestCard(created.id);
    assert.equal(card.client.phone, '9995554433');
    assert.equal(card.request.payload.contactSource, 'max_webapp_requestContact');
  });
});

test('p2 client bot accepts telegram request_contact payload', async () => {
  await withServer(async ({ base }) => {
    const start = await fetch(`${base}/telegram/client_bot/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: { message_id: 1, text: 'Нужна запись на сервис', chat: { id: 77 }, from: { id: 77, first_name: 'Иван' } } })
    });
    assert.equal(start.status, 200);

    const name = await fetch(`${base}/telegram/client_bot/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: { message_id: 2, text: 'Иван Петров', chat: { id: 77 }, from: { id: 77, first_name: 'Иван' } } })
    });
    assert.equal(name.status, 200);

    const contact = await fetch(`${base}/telegram/client_bot/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: { message_id: 3, chat: { id: 77 }, from: { id: 77, first_name: 'Иван' }, contact: { phone_number: '+7 (999) 123-45-67', user_id: 77, first_name: 'Иван' } } })
    });
    assert.equal(contact.status, 200);

    const store = db.readStore();
    assert.equal(store.requests.length, 1);
    assert.equal(store.clients[0].phone, '9991234567');
    assert.equal(store.requests[0].payload.contactSource, 'telegram_native_contact');
  });
});

test('p2 rate limiting protects client submit endpoint', async () => {
  await withServer(async ({ base }) => {
    const payload = {
      fullName: 'Rate Limited',
      phone: '9990000099',
      wasClientBefore: 'yes',
      brand: 'Lada',
      model: 'Granta',
      year: '2021',
      vin: 'VIN-RATE-1',
      description: 'Rate me'
    };
    const first = await fetch(`${base}/api/client/requests/service`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const second = await fetch(`${base}/api/client/requests/service`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, vin: 'VIN-RATE-2' }) });
    const third = await fetch(`${base}/api/client/requests/service`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, vin: 'VIN-RATE-3' }) });
    assert.equal(first.status, 201);
    assert.equal(second.status, 201);
    assert.equal(third.status, 429);
    const body = await third.json();
    assert.equal(body.error, 'RATE_LIMITED');
  }, { WEBAPP_RATE_LIMIT_MAX: '2', WEBAPP_RATE_LIMIT_WINDOW_MS: '60000' });
});

test('p2 retry helper retries transient failures', async () => {
  let attempts = 0;
  const result = await withRetry(async () => {
    attempts += 1;
    if (attempts < 3) throw new Error('SQLITE_BUSY');
    return 'ok';
  }, { attempts: 3, delayMs: 1, operation: 'test.retry' });
  assert.equal(result, 'ok');
  assert.equal(attempts, 3);
});

test('p2 csv serializer keeps export schema stable', () => {
  const csv = serializeCsv([{ id: 'r1', created_at: '2026-01-01T00:00:00.000Z', status: 'new', channel: 'webapp', request_type: 'service_request', phone: '9990000001', assigned_to: 'master-1' }]);
  assert.match(csv, /^id,created_at,status,channel,request_type,phone,assigned_to/m);
  assert.match(csv, /master-1/);
});
