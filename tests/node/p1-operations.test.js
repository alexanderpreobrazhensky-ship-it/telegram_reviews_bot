const test = require('node:test');
const assert = require('node:assert/strict');
const db = require('../../src/infrastructure/db');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');

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

test('p1 flow: create request, assign, change status, and persist request/analytics events', async () => {
  db.resetStore();
  const client = db.upsertClient({ fullName: 'Dispatcher', phone: '9991234567', telegramId: '101' });
  const request = db.createRequest({
    clientId: client.id,
    vehicleId: null,
    requestType: 'service_request',
    description: 'Need assignment',
    sourceChannel: 'webapp'
  });

  const assignment = db.updateRequestAssignment({
    requestId: request.id,
    assignedTo: 'manager-1',
    assignedBy: 'admin-1',
    actorId: 'admin-1',
    actorRole: 'admin',
    actorType: 'admin'
  });
  assert.equal(assignment.request.assignedTo, 'manager-1');
  assert.ok(assignment.request.assignedAt);
  assert.equal(assignment.request.assignedBy, 'admin-1');

  const status = db.updateRequestStatus({
    requestId: request.id,
    toStatus: 'assigned',
    actorId: 'manager-1',
    actorRole: 'manager'
  });
  assert.equal(status.request.status, 'assigned');

  db.createAnalyticsEvent({
    eventType: 'request_created',
    channel: 'telegram',
    platform: 'telegram',
    requestType: 'service_request',
    requestId: request.id,
    clientId: client.id,
    status: 'assigned'
  });

  const store = db.readStore();
  const requestEvents = store.requestEvents.filter((event) => event.requestId === request.id);
  assert.ok(requestEvents.some((event) => event.canonicalEventType === 'created'));
  assert.ok(requestEvents.some((event) => event.canonicalEventType === 'assigned'));
  assert.ok(requestEvents.some((event) => event.canonicalEventType === 'status_changed' && event.newStatus === 'assigned'));
  assert.ok(store.analyticsEvents.some((event) => event.eventType === 'request_created' && event.requestId === request.id));
});

test('p1 server: internal UI, health endpoints, analytics endpoint, and assignment/status APIs work', async () => {
  await withServer(async ({ base }) => {
    const createdResponse = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fullName: 'Internal UI Client',
        phone: '+7 (999) 000-00-11',
        wasClientBefore: 'yes',
        brand: 'Skoda',
        model: 'Octavia',
        year: '2021',
        vin: 'VIN-P1-001',
        description: 'Need operational workflow'
      })
    });
    assert.equal(createdResponse.status, 201);
    const created = await createdResponse.json();

    const assignResponse = await fetch(`${base}/api/requests/${created.id}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignedTo: 'manager-22', assignedBy: 'admin-77', actorId: 'admin-77', actorRole: 'admin', actorType: 'admin' })
    });
    assert.equal(assignResponse.status, 200);
    const assignment = await assignResponse.json();
    assert.equal(assignment.request.assignedTo, 'manager-22');

    const statusResponse = await fetch(`${base}/api/requests/${created.id}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'assigned', actorId: 'manager-22', actorRole: 'manager' })
    });
    assert.equal(statusResponse.status, 200);

    const analyticsResponse = await fetch(`${base}/api/analytics/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ eventType: 'form_started', channel: 'telegram', platform: 'telegram', requestType: 'service_request', status: 'started', metaJson: { path: '/forms/service-request' } })
    });
    assert.equal(analyticsResponse.status, 201);

    const health = await fetch(`${base}/health`);
    const healthDb = await fetch(`${base}/health/db`);
    const healthMax = await fetch(`${base}/health/max`);
    assert.equal(health.status, 200);
    assert.equal(healthDb.status, 200);
    assert.equal(healthMax.status, 200);
    assert.equal((await healthDb.json()).db.tables.includes('requests'), true);

    const internal = await fetch(`${base}/internal/requests?admin_id=admin-77&status=assigned`);
    assert.equal(internal.status, 200);
    const html = await internal.text();
    assert.match(html, /Internal Requests/);
    assert.match(html, /manager-22/);
    assert.match(html, /Events/);

    const store = db.readStore();
    assert.ok(store.analyticsEvents.some((event) => event.eventType === 'form_started'));
    assert.ok(store.requestEvents.some((event) => event.requestId === created.id && event.canonicalEventType === 'assigned'));
  }, { INTERNAL_ADMIN_WHITELIST: 'admin-77' });
});

test('p1 duplicate detection keeps request creation working and records duplicate markers', async () => {
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
    const created = await first.json();

    const second = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    assert.equal(second.status, 201);
    const deduped = await second.json();
    assert.equal(deduped.deduplicated, true);
    assert.notEqual(deduped.id, created.id);
    assert.equal(deduped.duplicateOfRequestId, created.id);

    const store = db.readStore();
    assert.ok(store.requestEvents.some((event) => event.requestId === deduped.id && event.canonicalEventType === 'duplicate_detected'));
    assert.ok(store.analyticsEvents.some((event) => event.eventType === 'request_duplicate_detected' && event.requestId === deduped.id));
  });
});
