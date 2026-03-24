const test = require('node:test');
const assert = require('node:assert/strict');
const db = require('../../src/infrastructure/db');
const { loadConfig } = require('../../src/infrastructure/config');
const { createAiRuntimeSettings } = require('../../src/infrastructure/ai/aiRuntimeSettings');
const { createAiService } = require('../../src/infrastructure/ai/aiService');
const { handleMasterWebhook } = require('../../src/interfaces/master_bot');

function restoreEnv(snapshot) {
  for (const [key, value] of Object.entries(snapshot)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

test('ai config defaults and env contract are parsed', () => {
  const snapshot = {
    AI_ENABLED: process.env.AI_ENABLED,
    AI_BUSINESS_USAGE_ENABLED: process.env.AI_BUSINESS_USAGE_ENABLED,
    AI_PROVIDER: process.env.AI_PROVIDER,
    AI_MODEL: process.env.AI_MODEL,
    AI_FALLBACK_PROVIDER: process.env.AI_FALLBACK_PROVIDER,
    AI_FALLBACK_MODEL: process.env.AI_FALLBACK_MODEL,
    AI_ALLOWED_PROVIDERS: process.env.AI_ALLOWED_PROVIDERS
  };

  process.env.AI_ENABLED = 'true';
  process.env.AI_BUSINESS_USAGE_ENABLED = 'false';
  process.env.AI_PROVIDER = 'proxy';
  process.env.AI_MODEL = 'deepseek-chat';
  process.env.AI_FALLBACK_PROVIDER = 'openai';
  process.env.AI_FALLBACK_MODEL = 'gpt-4o-mini';
  process.env.AI_ALLOWED_PROVIDERS = 'proxy,openai,deepseek';

  const config = loadConfig();
  assert.equal(config.ai.enabled, true);
  assert.equal(config.ai.businessUsageEnabled, false);
  assert.equal(config.ai.provider, 'proxy');
  assert.equal(config.ai.model, 'deepseek-chat');
  assert.equal(config.ai.fallbackProvider, 'openai');
  assert.equal(config.ai.fallbackModel, 'gpt-4o-mini');
  assert.deepEqual(config.ai.allowedProviders, ['proxy', 'openai', 'deepseek']);

  restoreEnv(snapshot);
});

test('ai runtime settings bootstrap from env and allow runtime override', () => {
  db.resetStore();
  const runtime = createAiRuntimeSettings({
    db,
    configAi: {
      enabled: true,
      businessUsageEnabled: false,
      provider: 'proxy',
      model: 'deepseek-chat',
      fallbackProvider: 'openai',
      fallbackModel: 'gpt-4o-mini',
      allowedProviders: ['proxy', 'openai', 'deepseek']
    }
  });

  const initial = runtime.get();
  assert.equal(initial.activeProvider, 'proxy');
  assert.equal(initial.activeModel, 'deepseek-chat');

  const updated = runtime.update({ activeProvider: 'openai', activeModel: 'gpt-4o-mini' });
  assert.equal(updated.ok, true);
  assert.equal(updated.runtime.activeProvider, 'openai');

  const invalid = runtime.update({ activeProvider: 'anthropic' });
  assert.equal(invalid.ok, false);
  assert.equal(invalid.error, 'ACTIVE_PROVIDER_NOT_ALLOWED');
});

test('ai service supports business-disabled mode and fallback', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'proxy',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: 'openai',
        activeFallbackModel: 'gpt-4o-mini',
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: false
      };
    },
    setDiagnosticsState(state) {
      return state;
    },
    getDiagnosticsState() {
      return null;
    }
  };

  const providerRegistry = {
    get(name) {
      if (name === 'proxy') {
        return {
          async invoke() {
            const error = new Error('proxy down');
            error.code = 'AI_PROVIDER_HTTP_ERROR';
            throw error;
          }
        };
      }
      if (name === 'openai') {
        return {
          async invoke() {
            return { provider: 'openai', model: 'gpt-4o-mini', output: 'OK' };
          }
        };
      }
      return null;
    }
  };

  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000 },
    runtimeSettings,
    providerRegistry,
    db,
    logger: { info() {}, warn() {}, error() {} }
  });

  const disabled = await aiService.classifyIntent({ text: 'hello' });
  assert.equal(disabled.ok, false);
  assert.equal(disabled.error, 'AI_BUSINESS_USAGE_DISABLED');

  const diag = await aiService.runHealthCheck();
  assert.equal(diag.ok, true);
  assert.equal(diag.probe.fallbackUsed, true);
});

test('master bot AI control plane commands are admin-only and usable', async () => {
  db.resetStore();
  process.env.MASTER_BOT_ADMIN_IDS = '8001';
  const config = loadConfig();

  const aiInfrastructure = {
    runtimeSettings: {
      get() {
        return {
          activeProvider: 'proxy',
          activeModel: 'deepseek-chat',
          activeFallbackProvider: 'openai',
          activeFallbackModel: 'gpt-4o-mini',
          aiEnabledRuntime: true,
          aiBusinessUsageEnabledRuntime: false,
          allowedProviders: ['proxy', 'openai', 'deepseek'],
          lastAiDiagnosticsStatus: 'never',
          lastAiDiagnosticsAt: null,
          lastAiDiagnosticsSummary: ''
        };
      },
      getDiagnosticsState() { return null; },
      update() { return { ok: true, runtime: this.get() }; }
    },
    async runDiagnostics() {
      return { ok: true, probe: { summary: 'AI diagnostics OK', state: { provider: 'proxy', model: 'deepseek-chat', fallbackUsed: false, durationMs: 10 } } };
    },
    listLogs() {
      return [{ timestamp: new Date().toISOString(), taskType: 'runHealthCheck', provider: 'proxy', model: 'deepseek-chat', durationMs: 12, success: true, fallbackUsed: false, errorCode: '', errorSummary: '' }];
    }
  };

  const denied = await handleMasterWebhook({
    body: { message: { text: '/ai_status', chat: { id: 9001 }, from: { id: 9001, first_name: 'User' } } },
    config,
    aiInfrastructure
  });
  assert.equal(denied.ok, false);

  const allowed = await handleMasterWebhook({
    body: { message: { text: '/ai_status', chat: { id: 8001 }, from: { id: 8001, first_name: 'Admin' } } },
    config,
    aiInfrastructure
  });
  assert.equal(allowed.ok, true);
  assert.match(allowed.text, /AI статус/i);

  const logs = await handleMasterWebhook({
    body: { message: { text: '/ai_logs status:success', chat: { id: 8001 }, from: { id: 8001, first_name: 'Admin' } } },
    config,
    aiInfrastructure
  });
  assert.equal(logs.ok, true);
  assert.match(logs.text, /AI логи/i);

  delete process.env.MASTER_BOT_ADMIN_IDS;
});
