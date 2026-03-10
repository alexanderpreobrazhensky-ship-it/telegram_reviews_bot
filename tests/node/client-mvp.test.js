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

const webRoutes = ['/', '/requests', '/recommendations', '/forms/service-request', '/forms/parts-request', '/forms/consultation', '/forms/warranty-request', '/forms/data-change-request'];

test('health and webapp pages are available', async () => {
  await withServer(async (base) => {
    const health = await fetch(`${base}/health`);
    assert.equal(health.status, 200);
    for (const route of webRoutes) {
      const response = await fetch(`${base}${route}`);
      assert.equal(response.status, 200, route);
    }
  });
});

const requestCases = [
  ['/api/client/requests/service', 'service_request', { fullName: 'Иван Иванов', phone: '+79990000001', brand: 'Lada', model: 'Vesta', year: '2020', vin: 'VIN001', plateNumber: 'A111AA', description: 'Стучит подвеска' }],
  ['/api/client/requests/parts', 'parts_request', { fullName: 'Иван Иванов', phone: '+79990000002', brand: 'Kia', model: 'Rio', year: '2018', vin: 'VIN002', plateNumber: 'B222BB', description: 'Нужен фильтр' }],
  ['/api/client/requests/consultation', 'consultation_request', { fullName: 'Иван Иванов', phone: '+79990000003', question: 'Когда менять масло?' }],
  ['/api/client/requests/warranty', 'warranty_request', { fullName: 'Иван Иванов', phone: '+79990000004', brand: 'VW', model: 'Polo', vin: 'VIN004', plateNumber: 'C333CC', description: 'Повторилась неисправность' }],
  ['/api/client/requests/data-change', 'data_change_request', { fullName: 'Иван Иванов', phone: '+79990000005', changeDetails: 'Сменил номер телефона' }]
];

test('api creates all mandatory request types', async () => {
  await withServer(async (base) => {
    for (const [endpoint, type, body] of requestCases) {
      const response = await fetch(`${base}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await response.json();
      assert.equal(response.status, 201);
      assert.equal(data.requestType, type);
      assert.equal(data.status, 'new');
    }
  });
});

test('client bot /start and quick request flow works', async () => {
  await withServer(async (base) => {
    const start = await fetch(`${base}/telegram/client_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 1 }, from: { id: 10 } } }) });
    assert.equal(start.status, 200);

    await fetch(`${base}/telegram/client_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: 'Нужна запись / сервис', chat: { id: 1 }, from: { id: 10 } } }) });
    await fetch(`${base}/telegram/client_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: 'Петров Петр', chat: { id: 1 }, from: { id: 10 } } }) });
    await fetch(`${base}/telegram/client_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '+79990000006', chat: { id: 1 }, from: { id: 10 } } }) });

    const requests = await fetch(`${base}/api/client/requests?phone=%2B79990000006`);
    const data = await requests.json();
    assert.equal(data.items.length, 1);
    assert.equal(data.items[0].requestType, 'service_request');
    assert.equal(data.items[0].sourceChannel, 'telegram_chat');
  });
});

test('persistence stores client vehicle request and communication events', async () => {
  await withServer(async (base) => {
    await fetch(`${base}/api/client/requests/service`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fullName: 'Сидоров Сидор', phone: '+79990000007', brand: 'Renault', model: 'Logan', year: '2019', vin: 'VIN007', plateNumber: 'T777TT', description: 'Проверка' }) });
    const state = db.readStore();
    assert.equal(state.clients.length, 1);
    assert.equal(state.vehicles.length, 1);
    assert.equal(state.requests.length, 1);
    assert.equal(state.communicationEvents.length, 1);
    assert.equal(state.requests[0].clientId, state.clients[0].id);
    assert.equal(state.requests[0].vehicleId, state.vehicles[0].id);
  });
});
