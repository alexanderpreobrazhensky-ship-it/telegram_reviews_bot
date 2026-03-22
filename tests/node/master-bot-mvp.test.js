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
    const req = await createClientRequest(base, { fullName: 'Иван Петров', phone: '0000000001', wasClientBefore: 'yes', brand: 'Lada', model: 'Vesta', year: '2019', vin: 'VIN-M1', plateNumber: 'A111AA', description: 'Шум в подвеске' });

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
    const reqA = await createClientRequest(base, { fullName: 'Тест A', phone: '0000000002', wasClientBefore: 'no', brand: 'Skoda', model: 'Rapid', year: '2020', vin: 'VINA', description: 'A' });
    const reqB = await createClientRequest(base, { fullName: 'Тест B', phone: '0000000003', wasClientBefore: 'yes', brand: 'VW', model: 'Polo', year: '2021', vin: 'VINB', description: 'B' });

    const assigned = await sendMaster(base, `/set_status ${reqA.id} assigned`);
    assert.equal(assigned.ok, true);
    assert.equal(assigned.request.status, 'in_progress');

    const waiting = await sendMaster(base, `/set_status ${reqA.id} processed waiting_decision`);
    assert.equal(waiting.ok, true);
    assert.equal(waiting.request.status, 'processed');
    assert.equal(waiting.request.substatus, 'waiting_decision');

    const inProgressAgain = await sendMaster(base, `/set_status ${reqA.id} in_progress`);
    assert.equal(inProgressAgain.ok, true);

    const inService = await sendMaster(base, `/set_status ${reqA.id} in_service`);
    assert.equal(inService.ok, true);

    const done = await sendMaster(base, `/set_status ${reqA.id} done`);
    assert.equal(done.ok, true);
    assert.equal(done.request.status, 'completed');

    const assignedB = await sendMaster(base, `/set_status ${reqB.id} assigned`);
    assert.equal(assignedB.ok, true);
    const cancelledInvalid = await sendMaster(base, `/set_status ${reqB.id} processed rejected`);
    assert.equal(cancelledInvalid.ok, false);
    assert.equal(cancelledInvalid.error, 'COMMENT_REQUIRED');

    const cancelledValid = await sendMaster(base, `/set_status ${reqB.id} processed rejected клиент не ответил`);
    assert.equal(cancelledValid.ok, true);
    assert.equal(cancelledValid.request.status, 'processed');
    assert.equal(cancelledValid.request.substatus, 'rejected');
  });
});

test('master bot inline flow supports assignment archive and protected transitions', async () => {
  await withServer(async (base) => {
    const req = await createClientRequest(base, { fullName: 'Архив Тест', phone: '0000000012', wasClientBefore: 'yes', brand: 'BMW', model: 'X1', year: '2023', vin: 'VIN-ARCHIVE', description: 'archive' });

    const take = await fetch(`${base}/telegram/master_bot/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ callback_query: { id: 'cb-1', from: { id: 5001, first_name: 'Admin' }, message: { chat: { id: 5001 } }, data: `req:${req.id}:in_progress` } })
    }).then((res) => res.json());
    assert.equal(take.ok, true);
    assert.equal(take.request.status, 'in_progress');

    const doneFromNewReq = await createClientRequest(base, { fullName: 'Нельзя завершить', phone: '0000000013', wasClientBefore: 'no', brand: 'Audi', model: 'A4', year: '2024', vin: 'VIN-NEW', description: 'new' });
    const invalid = await sendMaster(base, `/set_status ${doneFromNewReq.id} completed`);
    assert.equal(invalid.ok, false);
    assert.equal(invalid.error, 'INVALID_TRANSITION');

    const rejected = await sendMaster(base, `/set_status ${req.id} processed rejected дорого`);
    assert.equal(rejected.ok, true);
    assert.equal(rejected.request.archived, true);
    assert.equal(rejected.request.rejectionComment, 'дорого');

    const archivedList = await sendMaster(base, 'Архив');
    assert.equal(archivedList.items.some((item) => item.id === req.id), true);

    const invalidArchivedMove = await sendMaster(base, `/set_status ${req.id} in_service`);
    assert.equal(invalidArchivedMove.ok, false);
    assert.equal(invalidArchivedMove.error, 'ARCHIVED_IMMUTABLE');
  });
});

test('request data routing prefers source channel and falls back only to confirmed identity', async () => {
  db.resetStore();
  const { createMasterService } = require('../../src/core/application/masterService');

  const telegramClient = db.upsertClient({ fullName: 'TG Client', phone: '0000000014', telegramId: '10014', preferredChannel: 'telegram' });
  const maxClient = db.upsertClient({ fullName: 'MAX Client', phone: '0000000015', maxId: 'mx-15', preferredChannel: 'max' });
  const mixedClient = db.upsertClient({ fullName: 'Mixed Client', phone: '0000000016', telegramId: '10016', maxId: 'mx-16' });
  const unknownClient = db.upsertClient({ fullName: 'Unknown Client', phone: '0000000017' });

  const telegramRequest = db.createRequest({ clientId: telegramClient.id, requestType: 'service_request', description: 'tg', sourceChannel: 'telegram_chat' });
  const maxRequest = db.createRequest({ clientId: maxClient.id, requestType: 'service_request', description: 'max', sourceChannel: 'max_chat' });
  const mixedRequest = db.createRequest({ clientId: mixedClient.id, requestType: 'service_request', description: 'mixed', sourceChannel: 'webapp' });
  const unknownRequest = db.createRequest({ clientId: unknownClient.id, requestType: 'service_request', description: 'unknown', sourceChannel: 'webapp' });

  const attempts = [];
  const service = createMasterService({
    db,
    actorChannel: 'telegram',
    sendClientMessage: async ({ channel, recipientId }) => {
      attempts.push({ channel, recipientId });
      if (channel === 'telegram' && recipientId === Number(telegramClient.telegramId)) return true;
      if (channel === 'max' && recipientId === maxClient.maxId) return true;
      if (channel === 'max' && recipientId === mixedClient.maxId) return false;
      if (channel === 'telegram' && recipientId === Number(mixedClient.telegramId)) return true;
      return false;
    }
  });

  const tgResult = await service.requestClientClarification({ requestId: telegramRequest.id, actorId: 'm1', actorRole: 'master', text: 'ping', telegramClientBotToken: 'tg-token', maxClientBotToken: 'max-token' });
  assert.equal(tgResult.ok, true);
  assert.equal(tgResult.channel, 'telegram');

  const maxResult = await service.requestClientClarification({ requestId: maxRequest.id, actorId: 'm1', actorRole: 'master', text: 'ping', telegramClientBotToken: 'tg-token', maxClientBotToken: 'max-token' });
  assert.equal(maxResult.ok, true);
  assert.equal(maxResult.channel, 'max');

  const mixedResult = await service.requestClientClarification({ requestId: mixedRequest.id, actorId: 'm1', actorRole: 'master', text: 'ping', telegramClientBotToken: 'tg-token', maxClientBotToken: 'max-token' });
  assert.equal(mixedResult.ok, true);
  assert.equal(mixedResult.channel, 'telegram');
  assert.deepEqual(attempts.slice(-2).map((item) => item.channel), ['max', 'telegram']);

  const unknownResult = await service.requestClientClarification({ requestId: unknownRequest.id, actorId: 'm1', actorRole: 'master', text: 'ping', telegramClientBotToken: 'tg-token', maxClientBotToken: 'max-token' });
  assert.equal(unknownResult.ok, false);
  assert.equal(unknownResult.error, 'CLIENT_CHANNEL_UNRESOLVED');
  const erroredRequest = db.findRequestById(unknownRequest.id);
  assert.equal(erroredRequest.status, 'error');
  assert.equal(Boolean(erroredRequest.lastOutboundError), true);
});

test('diagnostics and logs are available only for admin and do not expose raw secrets', async () => {
  process.env.TELEGRAM_CLIENT_BOT_TOKEN = '123456:ABCDEF_SECRET';
  process.env.TELEGRAM_MASTER_BOT_TOKEN = '123456:MASTER_SECRET';
  await withServer(async (base) => {
    const adminDiag = await sendMaster(base, '/diagnostics');
    assert.equal(adminDiag.ok, true);
    assert.match(adminDiag.text, /TELEGRAM_CLIENT_BOT_TOKEN: configured/i);
    assert.doesNotMatch(adminDiag.text, /ABCDEF_SECRET/);

    const adminLogs = await sendMaster(base, '/logs request:none');
    assert.equal(adminLogs.ok, true);
    assert.match(adminLogs.text, /Логи/i);

    const denied = await sendMaster(base, '/logs', 7001);
    assert.equal(denied.ok, false);
    assert.match(`${denied.text || denied.error || ''}`, /ACCESS_DENIED|Доступ запрещён|Недостаточно прав/i);
  });
  delete process.env.TELEGRAM_CLIENT_BOT_TOKEN;
  delete process.env.TELEGRAM_MASTER_BOT_TOKEN;
});

test('persistence stores status history internal comments and assignment', async () => {
  await withServer(async (base) => {
    const req = await createClientRequest(base, { fullName: 'Сохранение', phone: '0000000004', wasClientBefore: 'yes', brand: 'Toyota', model: 'Corolla', year: '2022', vin: 'VINP', description: 'persist' });

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
    const req = await createClientRequest(base, { fullName: 'Карточка Клиента', phone: '0000000005', wasClientBefore: 'no', brand: 'Kia', model: 'Rio', year: '2018', vin: 'VIN-CARD', plateNumber: 'C500CC', description: 'card' });
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
