const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');

async function withServer(run) {
  db.resetStore();
  process.env.MASTER_BOT_ADMIN_IDS = '5001';
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const port = server.address().port;
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.MASTER_BOT_ADMIN_IDS;
  }
}

async function sendMaster(base, text, fromId = 5001) {
  const response = await fetch(`${base}/telegram/master_bot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: { text, chat: { id: fromId }, from: { id: fromId, first_name: 'Master' } } })
  });
  return response.json();
}

async function createClientRequest(base, payload) {
  const response = await fetch(`${base}/api/client/requests/service`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return response.json();
}

test('master bot /start menu list and search work', async () => {
  await withServer(async (base) => {
    const req = await createClientRequest(base, { fullName: 'Иван Петров', phone: '+70000000001', wasClientBefore: 'yes', brand: 'Lada', model: 'Vesta', year: '2019', vin: 'VIN-M1', plateNumber: 'A111AA', description: 'Шум в подвеске' });

    const start = await sendMaster(base, '/start');
    assert.equal(start.action, 'start');

    const menu = await sendMaster(base, 'Новые заявки');
    assert.equal(menu.items.length, 1);
    assert.equal(menu.items[0].id, req.id);

    await sendMaster(base, 'Поиск');
    const byName = await sendMaster(base, 'Иван Петров');
    assert.equal(byName.ok, true);
    assert.equal(byName.card.request.id, req.id);

    const byPhone = await sendMaster(base, '/search 0000000001');
    assert.equal(byPhone.clients.length, 1);

    const byVin = await sendMaster(base, '/search VIN-M1');
    assert.equal(byVin.clients.length, 1);

    const byPlate = await sendMaster(base, '/search A111AA');
    assert.equal(byPlate.clients.length, 1);
  });
});

test('status transitions and lost reason validation work', async () => {
  await withServer(async (base) => {
    const reqA = await createClientRequest(base, { fullName: 'Тест A', phone: '+70000000002', wasClientBefore: 'no', brand: 'Skoda', model: 'Rapid', year: '2020', vin: 'VINA', description: 'A' });
    const reqB = await createClientRequest(base, { fullName: 'Тест B', phone: '+70000000003', wasClientBefore: 'yes', brand: 'VW', model: 'Polo', year: '2021', vin: 'VINB', description: 'B' });

    const assigned = await sendMaster(base, `/set_status ${reqA.id} assigned`);
    assert.equal(assigned.ok, true);
    assert.equal(assigned.request.status, 'assigned');

    const waiting = await sendMaster(base, `/set_status ${reqA.id} awaiting_client`);
    assert.equal(waiting.ok, true);
    assert.equal(waiting.request.status, 'awaiting_client');

    const inService = await sendMaster(base, `/set_status ${reqA.id} in_service`);
    assert.equal(inService.ok, true);

    const done = await sendMaster(base, `/set_status ${reqA.id} done`);
    assert.equal(done.ok, true);
    assert.equal(done.request.status, 'done');

    const assignedB = await sendMaster(base, `/set_status ${reqB.id} assigned`);
    assert.equal(assignedB.ok, true);
    const cancelledInvalid = await sendMaster(base, `/set_status ${reqB.id} cancelled`);
    assert.equal(cancelledInvalid.ok, false);
    assert.equal(cancelledInvalid.error, 'CANCELLATION_COMMENT_REQUIRED');

    const cancelledValid = await sendMaster(base, `/set_status ${reqB.id} cancelled клиент не ответил`);
    assert.equal(cancelledValid.ok, true);
    assert.equal(cancelledValid.request.status, 'cancelled');
  });
});

test('persistence stores status history internal comments and assignment', async () => {
  await withServer(async (base) => {
    const req = await createClientRequest(base, { fullName: 'Сохранение', phone: '+70000000004', wasClientBefore: 'yes', brand: 'Toyota', model: 'Corolla', year: '2022', vin: 'VINP', description: 'persist' });

    await sendMaster(base, `/set_status ${req.id} assigned`);
    await sendMaster(base, `/comment ${req.id} проверили ошибки`);

    const state = db.readStore();
    const request = state.requests.find((item) => item.id === req.id);
    const comments = state.requestInternalComments.filter((item) => item.requestId === req.id);
    const history = state.requestStatusHistory.filter((item) => item.requestId === req.id);

    assert.equal(Boolean(request.assignedMasterId), true);
    assert.equal(comments.length, 1);
    assert.equal(comments[0].text, 'проверили ошибки');
    assert.equal(history.length >= 2, true);
  });
});

test('client card request card recommendations and quality case skeleton work', async () => {
  await withServer(async (base) => {
    const req = await createClientRequest(base, { fullName: 'Карточка Клиента', phone: '+70000000005', wasClientBefore: 'no', brand: 'Kia', model: 'Rio', year: '2018', vin: 'VIN-CARD', plateNumber: 'C500CC', description: 'card' });
    const state = db.readStore();
    const client = state.clients[0];

    const clientCard = await sendMaster(base, `/client ${client.id}`);
    assert.equal(clientCard.ok, true);
    assert.equal(clientCard.card.client.id, client.id);
    assert.equal(Array.isArray(clientCard.card.recommendations), true);
    assert.equal(clientCard.card.recommendations.length >= 0, true);

    const requestCard = await sendMaster(base, `/request ${req.id}`);
    assert.equal(requestCard.ok, true);
    assert.equal(requestCard.card.request.id, req.id);

    const qc = db.createQualityCase({ requestId: req.id, status: 'new', summary: 'Проверить качество' });
    const qualityCases = await sendMaster(base, '/quality_cases');
    assert.equal(qualityCases.items.length, 1);

    const qualityCard = await sendMaster(base, `/quality_case ${qc.id}`);
    assert.equal(qualityCard.ok, true);

    const qualityStatus = await sendMaster(base, `/quality_status ${qc.id} in_progress`);
    assert.equal(qualityStatus.ok, true);

    const qualityComment = await sendMaster(base, `/quality_comment ${qc.id} назначили разбор`);
    assert.equal(qualityComment.ok, true);
  });
});
