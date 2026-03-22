const test = require('node:test');
const assert = require('node:assert/strict');
const { loadConfig } = require('../../src/infrastructure/config');

test('config loads defaults', () => {
  const config = loadConfig();
  assert.equal(typeof config.port, 'number');
  assert.equal(typeof config.dbUrl, 'string');
  assert.equal(Object.hasOwn(config, 'telegramClientBotToken'), true);

  assert.equal(Object.hasOwn(config, 'enableIntegrationWorker'), true);
  assert.equal(Object.hasOwn(config, 'integrationRetryMax'), true);
  assert.equal(Object.hasOwn(config, 'oneCSyncEnabled'), true);
  assert.equal(Object.hasOwn(config, 'emailImportEnabled'), true);
  assert.equal(Object.hasOwn(config, 'maxEnabled'), true);
  assert.equal(Object.hasOwn(config, 'maxClientBotToken'), true);
  assert.equal(Object.hasOwn(config, 'maxMasterBotAdminIds'), true);
  assert.equal(Object.hasOwn(config, 'ai'), true);
  assert.equal(Array.isArray(config.envAudit.required), true);
  assert.equal(Array.isArray(config.envAudit.optional), true);
  assert.equal(Array.isArray(config.envAudit.legacyAccepted), true);
});


test('config sanitizes invalid numeric env values', () => {
  const original = {
    PORT: process.env.PORT,
    SCHEDULER_INTERVAL_MS: process.env.SCHEDULER_INTERVAL_MS,
    INTEGRATION_RETRY_MAX: process.env.INTEGRATION_RETRY_MAX
  };

  process.env.PORT = 'invalid';
  process.env.SCHEDULER_INTERVAL_MS = '0';
  process.env.INTEGRATION_RETRY_MAX = '-5';

  const config = loadConfig();
  assert.equal(config.port, 3000);
  assert.equal(config.schedulerIntervalMs, 1000);
  assert.equal(config.integrationRetryMax, 1);

  for (const [key, value] of Object.entries(original)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

test('config reads MAX and DB path related env values', () => {
  const original = {
    MAX_ENABLED: process.env.MAX_ENABLED,
    DB_FILE_PATH: process.env.DB_FILE_PATH
  };

  process.env.MAX_ENABLED = 'TRUE';
  process.env.DB_FILE_PATH = '/tmp/telegram-reviews-bot/db.json';

  const config = loadConfig();
  assert.equal(config.maxEnabled, true);
  assert.equal(process.env.DB_FILE_PATH, '/tmp/telegram-reviews-bot/db.json');

  for (const [key, value] of Object.entries(original)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

test('config fails fast when required env is missing', () => {
  const original = {
    CONFIG_STRICT: process.env.CONFIG_STRICT,
    WEBAPP_URL: process.env.WEBAPP_URL,
    DB_SQLITE_PATH: process.env.DB_SQLITE_PATH,
    DB_FILE_PATH: process.env.DB_FILE_PATH
  };

  process.env.CONFIG_STRICT = 'true';
  delete process.env.WEBAPP_URL;
  delete process.env.DB_SQLITE_PATH;
  delete process.env.DB_FILE_PATH;

  assert.throws(() => loadConfig(), /Missing required env/);

  for (const [key, value] of Object.entries(original)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});
