const test = require('node:test');
const assert = require('node:assert/strict');

const { handleClientWebhook } = require('../../src/interfaces/client_bot');

test('client bot /start reply keyboard Mini App button uses WEBAPP_URL', async () => {
  const calls = [];
  const originalFetch = global.fetch;
  global.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  };

  try {
    const config = {
      telegramClientBotToken: 'test-token',
      webAppUrl: 'https://lirabotv3.bothost.ru/'
    };

    const result = await handleClientWebhook({
      body: { message: { text: '/start', chat: { id: 1 }, from: { id: 10 } } },
      config
    });

    assert.equal(result.action, 'start');
    assert.equal(calls.length, 1);

    const payload = JSON.parse(calls[0].options.body);
    const miniAppButton = payload.reply_markup.keyboard[0][0];
    assert.equal(miniAppButton.text, 'Мини-приложение');
    assert.equal(miniAppButton.web_app.url, config.webAppUrl);
  } finally {
    global.fetch = originalFetch;
  }
});
