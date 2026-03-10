const test = require('node:test');
const assert = require('node:assert/strict');

const clientBot = require('../../src/interfaces/client_bot');
const masterBot = require('../../src/interfaces/master_bot');
const integrationBot = require('../../src/interfaces/integration_bot');
const webapp = require('../../src/interfaces/webapp');
const application = require('../../src/core/application');

test('main modules export expected APIs', () => {
  assert.equal(typeof clientBot.registerClientBotRoutes, 'function');
  assert.equal(typeof masterBot.registerMasterBotRoutes, 'function');
  assert.equal(typeof integrationBot.registerIntegrationBotRoutes, 'function');
  assert.equal(typeof webapp.webappRoutes, 'function');
  assert.equal(typeof application.createRequestUseCase, 'function');
});
