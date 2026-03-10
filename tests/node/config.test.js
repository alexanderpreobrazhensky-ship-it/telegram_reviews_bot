const test = require('node:test');
const assert = require('node:assert/strict');
const { loadConfig } = require('../../src/infrastructure/config');

test('config loads defaults', () => {
  const config = loadConfig();
  assert.equal(typeof config.port, 'number');
  assert.equal(typeof config.dbUrl, 'string');
  assert.equal(Object.hasOwn(config, 'telegramClientBotToken'), true);
});
