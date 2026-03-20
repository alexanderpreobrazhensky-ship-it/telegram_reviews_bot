const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');

async function withServer(run, env = {}) {
  db.resetStore();
  const previous = {};
  for (const [key, value] of Object.entries(env)) {
    previous[key] = process.env[key];
    process.env[key] = value;
  }
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const port = server.address().port;
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

async function post(base, path, body, headers = {}) {
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body)
  });
  return { response, data: await response.json() };
}

test('MAX client bot supports start help quick flow and stores max_chat source', async () => {
  await withServer(async (base) => {
    const webhookHeaders = { 'x-max-bot-api-secret': 'secret-max' };

    const start = await post(base, '/max/client_bot/webhook', { message: { body: { text: '/start form_service' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } }, webhookHeaders);
    assert.equal(start.response.status, 200);
    assert.equal(start.data.action, 'start');
    assert.equal(start.data.deeplink.payload, 'form_service');

    const help = await post(base, '/max/client_bot/webhook', { message: { body: { text: '/help' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } }, webhookHeaders);
    assert.equal(help.data.action, 'help');

    await post(base, '/max/client_bot/webhook', { callback: { callback_id: 'cb-1', payload: 'quick:service', message: { chat_id: 'chat-1' }, from: { user_id: 'mx-client-1', first_name: 'Max' } } }, webhookHeaders);
    await post(base, '/max/client_bot/webhook', { message: { body: { text: 'Макс Клиент' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } }, webhookHeaders);
    await post(base, '/max/client_bot/webhook', { message: { body: { text: '+79990000066' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } }, webhookHeaders);

    const state = db.readStore();
    assert.equal(state.requests.length, 1);
    assert.equal(state.requests[0].sourceChannel, 'max_chat');
    assert.equal(state.clients[0].maxId, 'mx-client-1');
    assert.equal(state.clients[0].preferredChannel, 'max');

    const unknown = await post(base, '/max/client_bot/webhook', { event_id: 'evt-1', payload: { unsupported: true } }, webhookHeaders);
    assert.equal(unknown.response.status, 200);
    assert.equal(unknown.data.action, 'ignored_unknown_update');
  }, { MAX_WEBHOOK_SECRET: 'secret-max' });
});

test('MAX master bot enforces access, works with roles and sends clarification foundation to MAX', async () => {
  await withServer(async (base) => {
    const webhookHeaders = { 'x-max-bot-api-secret': 'secret-max' };
    const denied = await post(base, '/max/master_bot/webhook', { message: { body: { text: '/start' }, chat_id: 'staff-chat', from: { user_id: 'unknown-max', first_name: 'NoAccess' } } }, webhookHeaders);
    assert.equal(denied.data.error, 'ACCESS_DENIED');
    assert.equal(denied.data.reason, 'ACTOR_NOT_FOUND_OR_NOT_ALLOWED');

    const whoami = await post(base, '/max/master_bot/webhook', { message: { body: { text: '/whoami' }, chat_id: 'staff-chat', from: { user_id: 'unknown-max', first_name: 'NoAccess' } } }, webhookHeaders);
    assert.equal(whoami.data.action, 'whoami');
    assert.equal(whoami.data.channelUserId, 'unknown-max');

    const grant = await post(base, '/max/master_bot/webhook', { message: { body: { text: '/access_grant mx-master-2 master Макс Мастер' }, chat_id: 'admin-chat', from: { user_id: 'mx-admin-1', first_name: 'Admin' } } }, webhookHeaders);
    assert.equal(grant.data.ok, true);

    await post(base, '/api/client/requests/service', {
      fullName: 'Клиент MAX WebApp',
      phone: '+79990000067',
      wasClientBefore: 'yes',
      brand: 'Lada',
      model: 'Vesta',
      year: '2024',
      vin: 'MAXVIN67',
      description: 'MAX webapp request',
      sourceChannel: 'max_webapp',
      maxId: 'mx-client-web-1'
    });

    const start = await post(base, '/max/master_bot/webhook', { message: { body: { text: '/start' }, chat_id: 'staff-chat-2', from: { user_id: 'mx-master-2', first_name: 'Master' } } }, webhookHeaders);
    assert.equal(start.data.action, 'start');

    const list = await post(base, '/max/master_bot/webhook', { message: { body: { text: 'Новые заявки' }, chat_id: 'staff-chat-2', from: { user_id: 'mx-master-2', first_name: 'Master' } } }, webhookHeaders);
    assert.equal(list.data.items.length, 1);

    const ask = await post(base, '/max/master_bot/webhook', { message: { body: { text: `/ask_client ${list.data.items[0].id} Уточните VIN` }, chat_id: 'staff-chat-2', from: { user_id: 'mx-master-2', first_name: 'Master' } } }, webhookHeaders);
    assert.equal(ask.data.ok, true);
    assert.equal(ask.data.channel, 'max');

    const state = db.readStore();
    assert.equal(state.staffUsers.some((item) => item.maxId === 'mx-master-2' && item.role === 'master'), true);
    assert.equal(state.communicationEvents.some((item) => item.payload?.action === 'client_clarification_requested' && item.channel === 'max' && item.direction === 'outbound'), true);
  }, { MAX_WEBHOOK_SECRET: 'secret-max', MAX_MASTER_BOT_ADMIN_IDS: 'mx-admin-1' });
});
