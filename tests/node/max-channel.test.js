const test = require('node:test');
const assert = require('node:assert/strict');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const db = require('../../src/infrastructure/db');
const { handleClientWebhook } = require('../../src/interfaces/client_bot');
const { handleMasterWebhook } = require('../../src/interfaces/master_bot');

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

async function withMockedFetch(run) {
  const calls = [];
  const originalFetch = global.fetch;
  global.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    return {
      ok: true,
      status: 200,
      text: async () => '',
      json: async () => ({ ok: true })
    };
  };
  try {
    await run(calls);
  } finally {
    global.fetch = originalFetch;
  }
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
  }, { MAX_ENABLED: 'true', MAX_CLIENT_BOT_TOKEN: 'max-client-token', MAX_WEBHOOK_SECRET: 'secret-max' });
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
      phone: '9990000067',
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
    assert.equal(ask.data.error, 'CLIENT_MESSAGE_DELIVERY_FAILED');

    const state = db.readStore();
    assert.equal(state.staffUsers.some((item) => item.maxId === 'mx-master-2' && item.role === 'master'), true);
    assert.equal(state.communicationEvents.some((item) => item.payload?.action === 'client_clarification_requested' && item.channel === 'max' && item.direction === 'outbound'), true);
    assert.equal(state.requests.some((item) => item.id === list.data.items[0].id && item.status === 'error'), true);
  }, { MAX_ENABLED: 'true', MAX_CLIENT_BOT_TOKEN: 'max-client-token', MAX_MASTER_BOT_TOKEN: 'max-master-token', MAX_WEBHOOK_SECRET: 'secret-max', MAX_MASTER_BOT_ADMIN_IDS: 'mx-admin-1' });
});


test('MAX client webhook parses message_created payload when webhook body is nested directly under payload', async () => {
  await withMockedFetch(async () => {
    const config = loadConfig();
    config.maxEnabled = true;
    config.maxWebhookSecret = 'secret-max';
    config.maxClientBotToken = 'max-client-token';

    const start = await handleClientWebhook({
      body: {
        update_type: 'message_created',
        payload: {
          sender: { user_id: 'mx-client-payload', first_name: 'Payload' },
          recipient: { chat_id: 'chat-payload' },
          body: { text: '/start form_service' }
        }
      },
      config,
      headers: { 'X-Max-Bot-Api-Secret': 'secret-max' },
      rawHeaders: ['X-Max-Bot-Api-Secret', 'secret-max'],
      pathname: '/max/client_bot/webhook',
      method: 'POST',
      channel: 'max'
    });
    assert.equal(start.ok, true);
    assert.equal(start.action, 'start');
    assert.equal(start.deeplink.payload, 'form_service');

    const help = await handleClientWebhook({
      body: {
        update_type: 'message_created',
        payload: {
          sender: { user_id: 'mx-client-payload', first_name: 'Payload' },
          recipient: { chat_id: 'chat-payload' },
          body: { text: '/help' }
        }
      },
      config,
      headers: { 'X-Max-Bot-Api-Secret': 'secret-max' },
      rawHeaders: ['X-Max-Bot-Api-Secret', 'secret-max'],
      pathname: '/max/client_bot/webhook',
      method: 'POST',
      channel: 'max'
    });
    assert.equal(help.ok, true);
    assert.equal(help.action, 'help');
  });
});

test('MAX webhook secret check reads env secret and accepts header name casing from runtime', async () => {
  await withMockedFetch(async () => {
    const config = loadConfig();
    config.maxEnabled = true;
    config.maxWebhookSecret = 'secret-max';
    config.maxClientBotToken = 'max-client-token';
    config.maxMasterBotToken = 'max-master-token';

    const clientResult = await handleClientWebhook({
      body: { message: { body: { text: '/help' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } },
      config,
      headers: { 'X-Max-Bot-Api-Secret': 'secret-max' },
      rawHeaders: ['X-Max-Bot-Api-Secret', 'secret-max'],
      pathname: '/max/client_bot/webhook',
      method: 'POST',
      channel: 'max'
    });
    assert.equal(clientResult.ok, true);
    assert.equal(clientResult.action, 'help');

    const masterResult = await handleMasterWebhook({
      body: { message: { body: { text: '/whoami' }, chat_id: 'chat-2', from: { user_id: 'mx-master-1', first_name: 'Master' } } },
      config,
      headers: { 'X-Max-Bot-Api-Secret': 'secret-max' },
      rawHeaders: ['X-Max-Bot-Api-Secret', 'secret-max'],
      pathname: '/max/master_bot/webhook',
      method: 'POST',
      channel: 'max'
    });
    assert.equal(masterResult.ok, true);
    assert.equal(masterResult.action, 'whoami');
    assert.equal(masterResult.channelUserId, 'mx-master-1');
  });
});

test('MAX webhook rejects missing secret, invalid payload and disabled runtime', async () => {
  await withServer(async (base) => {
    const noSecret = await post(base, '/max/client_bot/webhook', { message: { body: { text: '/help' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } });
    assert.equal(noSecret.response.status, 403);
    assert.equal(noSecret.data.error, 'INVALID_WEBHOOK_SECRET');
  }, { MAX_ENABLED: 'true', MAX_CLIENT_BOT_TOKEN: 'max-client-token', MAX_WEBHOOK_SECRET: 'secret-max' });

  await withServer(async (base) => {
    const invalidPayload = await post(base, '/max/client_bot/webhook', null, { 'x-max-bot-api-secret': 'secret-max' });
    assert.equal(invalidPayload.response.status, 400);
    assert.equal(invalidPayload.data.error, 'INVALID_MAX_PAYLOAD');
  }, { MAX_ENABLED: 'true', MAX_CLIENT_BOT_TOKEN: 'max-client-token', MAX_WEBHOOK_SECRET: 'secret-max' });

  await withServer(async (base) => {
    const secretMissing = await post(base, '/max/client_bot/webhook', { message: { body: { text: '/help' }, chat_id: 'chat-1', from: { user_id: 'mx-client-1', first_name: 'Max' } } }, { 'x-max-bot-api-secret': 'secret-max' });
    assert.equal(secretMissing.response.status, 503);
    assert.equal(secretMissing.data.error, 'MAX_WEBHOOK_SECRET_MISSING');
  }, { MAX_ENABLED: 'true', MAX_CLIENT_BOT_TOKEN: 'max-client-token' });

  await withServer(async (base) => {
    const disabled = await post(base, '/max/master_bot/webhook', { message: { body: { text: '/whoami' }, chat_id: 'chat-2', from: { user_id: 'mx-master-1', first_name: 'Master' } } }, { 'x-max-bot-api-secret': 'secret-max' });
    assert.equal(disabled.response.status, 503);
    assert.equal(disabled.data.error, 'MAX_DISABLED');
  }, { MAX_MASTER_BOT_TOKEN: 'max-master-token', MAX_WEBHOOK_SECRET: 'secret-max' });
});

test('MAX outbound replies target user_id instead of chat_id for client and master bots', async () => {
  await withMockedFetch(async (calls) => {
    const config = {
      maxEnabled: true,
      maxWebhookSecret: 'secret-max',
      maxClientBotToken: 'max-client-token',
      maxMasterBotToken: 'max-master-token',
      maxMasterBotAdminIds: ['mx-admin-1'],
      masterBotAdminIds: [],
      webAppUrl: 'https://example.com',
      maxWebAppUrl: 'https://example.com/max',
      maxBotName: 'test_bot',
      maxDeepLinkBaseUrl: 'https://max.ru/test_bot'
    };

    const clientResult = await handleClientWebhook({
      body: { message: { body: { text: '/start' }, chat_id: 'chat-123', from: { user_id: 'mx-client-42', first_name: 'Client' } } },
      config,
      headers: { 'x-max-bot-api-secret': 'secret-max' },
      rawHeaders: ['x-max-bot-api-secret', 'secret-max'],
      pathname: '/max/client_bot/webhook',
      method: 'POST',
      channel: 'max'
    });
    assert.equal(clientResult.action, 'start');

    const masterResult = await handleMasterWebhook({
      body: { message: { body: { text: '/whoami' }, chat_id: 'chat-999', from: { user_id: 'mx-admin-1', first_name: 'Admin' } } },
      config,
      headers: { 'x-max-bot-api-secret': 'secret-max' },
      rawHeaders: ['x-max-bot-api-secret', 'secret-max'],
      pathname: '/max/master_bot/webhook',
      method: 'POST',
      channel: 'max'
    });
    assert.equal(masterResult.action, 'whoami');

    const messageUrls = calls.map((item) => item.url).filter((value) => value.includes('/messages?user_id='));
    assert.equal(messageUrls.length >= 2, true);
    assert.equal(messageUrls.some((value) => value.includes('user_id=mx-client-42')), true);
    assert.equal(messageUrls.some((value) => value.includes('user_id=mx-admin-1')), true);
    assert.equal(messageUrls.some((value) => value.includes('user_id=chat-123')), false);
    assert.equal(messageUrls.some((value) => value.includes('user_id=chat-999')), false);
  });
});
