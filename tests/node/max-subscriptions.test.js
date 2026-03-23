const test = require('node:test');
const assert = require('node:assert/strict');
const {
  DEFAULT_UPDATE_TYPES,
  buildWebhookUrl,
  reconcileMaxWebhookSubscriptions,
  resolveWebhookBaseUrl
} = require('../../src/infrastructure/max/subscriptions');
const { handleClientWebhook } = require('../../src/interfaces/client_bot');

function createLogger() {
  return {
    info() {},
    warn() {},
    error() {}
  };
}

async function withMockedFetch(run) {
  const calls = [];
  const originalFetch = global.fetch;
  global.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    const method = String(options.method || 'GET').toUpperCase();
    if (method === 'GET') {
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({
          subscriptions: [
            { url: 'https://old.example.com/max/client_bot/webhook', secret: 'old-secret', update_types: ['message_callback'] },
            { url: 'https://old.example.com/max/master_bot/webhook', secret: 'old-secret', update_types: ['message_callback'] }
          ]
        })
      };
    }
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ success: true })
    };
  };
  try {
    await run(calls);
  } finally {
    global.fetch = originalFetch;
  }
}

test('MAX subscription reconciliation rebuilds stale webhook URLs, secrets and update types', async () => {
  await withMockedFetch(async (calls) => {
    const result = await reconcileMaxWebhookSubscriptions({
      config: {
        maxEnabled: true,
        maxClientBotToken: 'client-token',
        maxMasterBotToken: 'master-token',
        maxWebhookSecret: 'secret-max',
        webAppUrl: 'https://prod.example.com/app',
        maxWebAppUrl: 'https://prod.example.com/max-app'
      },
      logger: createLogger()
    });

    assert.equal(result.ok, true);
    assert.equal(resolveWebhookBaseUrl({ webAppUrl: 'https://prod.example.com/app' }), 'https://prod.example.com');
    assert.equal(buildWebhookUrl('https://prod.example.com', '/max/client_bot/webhook'), 'https://prod.example.com/max/client_bot/webhook');

    const createCalls = calls.filter((item) => String(item.options.method || 'GET').toUpperCase() === 'POST');
    assert.equal(createCalls.length, 2);

    const clientCreateBody = JSON.parse(createCalls[0].options.body);
    const masterCreateBody = JSON.parse(createCalls[1].options.body);
    assert.deepEqual(clientCreateBody.update_types, [...DEFAULT_UPDATE_TYPES].sort());
    assert.deepEqual(masterCreateBody.update_types, [...DEFAULT_UPDATE_TYPES].sort());
    assert.equal(clientCreateBody.url, 'https://prod.example.com/max/client_bot/webhook');
    assert.equal(masterCreateBody.url, 'https://prod.example.com/max/master_bot/webhook');
    assert.equal(clientCreateBody.secret, 'secret-max');
    assert.equal(masterCreateBody.secret, 'secret-max');

    const deleteCalls = calls.filter((item) => String(item.options.method || 'GET').toUpperCase() === 'DELETE');
    assert.equal(deleteCalls.length, 4);
    assert.equal(deleteCalls.some((item) => item.url.includes(encodeURIComponent('https://old.example.com/max/client_bot/webhook'))), true);
    assert.equal(deleteCalls.some((item) => item.url.includes(encodeURIComponent('https://old.example.com/max/master_bot/webhook'))), true);
  });
});

test('MAX client webhook accepts bot_started event as /start command', async () => {
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
    const result = await handleClientWebhook({
      body: {
        update_type: 'bot_started',
        chat_id: 'chat-77',
        user: { user_id: 'mx-client-77', first_name: 'Max' },
        start_payload: 'form_parts'
      },
      config: {
        maxEnabled: true,
        maxWebhookSecret: 'secret-max',
        maxClientBotToken: 'client-token',
        webAppUrl: 'https://prod.example.com/app',
        maxWebAppUrl: 'https://prod.example.com/max-app',
        maxBotName: 'prod_bot',
        maxDeepLinkBaseUrl: 'https://max.ru/prod_bot'
      },
      headers: { 'x-max-bot-api-secret': 'secret-max' },
      rawHeaders: ['x-max-bot-api-secret', 'secret-max'],
      pathname: '/max/client_bot/webhook',
      method: 'POST',
      channel: 'max'
    });

    assert.equal(result.ok, true);
    assert.equal(result.action, 'start');
    assert.equal(result.deeplink.payload, 'form_parts');
    assert.equal(calls.some((item) => item.url.includes('/messages?user_id=mx-client-77')), true);
  } finally {
    global.fetch = originalFetch;
  }
});
