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
    const req = await createClientRequest(base, { fullName: 'Иван Петров', phone: '+70000000001', year: '2019', vin: 'VIN-M1', plateNumber: 'A111AA', description: 'Шум в подвеске' });

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
    const reqA = await createClientRequest(base, { fullName: 'Тест A', phone: '+70000000002', year: '2020', vin: 'VINA', description: 'A' });
    const reqB = await createClientRequest(base, { fullName: 'Тест B', phone: '+70000000003', year: '2021', vin: 'VINB', description: 'B' });

    const waiting = await sendMaster(base, `/set_status ${reqA.id} waiting_data`);
    assert.equal(waiting.ok, true);
    assert.equal(waiting.request.status, 'waiting_data');

    const inProgress = await sendMaster(base, `/set_status ${reqA.id} in_progress`);
    assert.equal(inProgress.ok, true);

    const processed = await sendMaster(base, `/set_status ${reqA.id} processed`);
    assert.equal(processed.ok, true);
    assert.equal(processed.request.status, 'processed');

    const lostWithoutReason = await sendMaster(base, `/set_status ${reqB.id} in_progress`);
    assert.equal(lostWithoutReason.ok, true);
    const lostInvalid = await sendMaster(base, `/set_status ${reqB.id} lost`);
    assert.equal(lostInvalid.ok, false);
    assert.equal(lostInvalid.error, 'LOST_REASON_REQUIRED');

    const lostValid = await sendMaster(base, `/set_status ${reqB.id} lost клиент не ответил`);
    assert.equal(lostValid.ok, true);
    assert.equal(lostValid.request.status, 'lost');
  });
});

test('persistence stores status history internal comments and assignment', async () => {
  await withServer(async (base) => {
    const req = await createClientRequest(base, { fullName: 'Сохранение', phone: '+70000000004', year: '2022', vin: 'VINP', description: 'persist' });

    await sendMaster(base, `/set_status ${req.id} in_progress`);
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
    const req = await createClientRequest(base, { fullName: 'Карточка Клиента', phone: '+70000000005', year: '2018', vin: 'VIN-CARD', plateNumber: 'C500CC', description: 'card' });
    const state = db.readStore();
    const client = state.clients[0];

    const clientCard = await sendMaster(base, `/client ${client.id}`);
    assert.equal(clientCard.ok, true);
    assert.equal(clientCard.card.client.id, client.id);
    assert.equal(Array.isArray(clientCard.card.recommendations), true);
    assert.equal(clientCard.card.recommendations.length > 0, true);

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
