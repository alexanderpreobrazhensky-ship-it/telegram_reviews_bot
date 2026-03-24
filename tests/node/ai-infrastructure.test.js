const test = require('node:test');
const assert = require('node:assert/strict');
const db = require('../../src/infrastructure/db');
const { loadConfig } = require('../../src/infrastructure/config');
const { createAiRuntimeSettings } = require('../../src/infrastructure/ai/aiRuntimeSettings');
const { createAiService } = require('../../src/infrastructure/ai/aiService');
const { runAiDiagnostics } = require('../../src/infrastructure/ai/aiDiagnostics');
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
    AI_ALLOWED_PROVIDERS: process.env.AI_ALLOWED_PROVIDERS,
    AI_TIMEOUT_MS: process.env.AI_TIMEOUT_MS,
    AI_TIMEOUT_SECONDS: process.env.AI_TIMEOUT_SECONDS,
    DEEPSEEK_MODEL: process.env.DEEPSEEK_MODEL,
    CLIENT_DEEPSEEK_MODEL: process.env.CLIENT_DEEPSEEK_MODEL
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

test('ai config does not auto-enable fallback when fallback env is empty', () => {
  const snapshot = {
    AI_PROVIDER: process.env.AI_PROVIDER,
    AI_MODEL: process.env.AI_MODEL,
    AI_FALLBACK_PROVIDER: process.env.AI_FALLBACK_PROVIDER,
    AI_FALLBACK_MODEL: process.env.AI_FALLBACK_MODEL
  };

  process.env.AI_PROVIDER = 'proxy';
  process.env.AI_MODEL = 'deepseek-chat';
  delete process.env.AI_FALLBACK_PROVIDER;
  delete process.env.AI_FALLBACK_MODEL;

  const config = loadConfig();
  assert.equal(config.ai.fallbackProvider, '');
  assert.equal(config.ai.fallbackModel, '');
  assert.equal(config.ai.fallbackConfigured, false);

  restoreEnv(snapshot);
});



test('ai config supports legacy railway mapping with canonical priority and explicit legacy ignore list', () => {
  const snapshot = {
    AI_PROVIDER: process.env.AI_PROVIDER,
    AI_ENGINE: process.env.AI_ENGINE,
    AI_MODEL: process.env.AI_MODEL,
    AI_PROXY_URL: process.env.AI_PROXY_URL,
    AI_PROXY_TOKEN: process.env.AI_PROXY_TOKEN,
    DEEPSEEK_MODEL: process.env.DEEPSEEK_MODEL,
    CLIENT_DEEPSEEK_MODEL: process.env.CLIENT_DEEPSEEK_MODEL,
    AI_TIMEOUT_MS: process.env.AI_TIMEOUT_MS,
    AI_TIMEOUT_SECONDS: process.env.AI_TIMEOUT_SECONDS,
    CLIENT_AI_TIMEOUT_SECONDS: process.env.CLIENT_AI_TIMEOUT_SECONDS,
    DEEPSEEK_API_KEY: process.env.DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL: process.env.DEEPSEEK_BASE_URL,
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
    GEMINI_API_KEY: process.env.GEMINI_API_KEY,
    CLIENT_FORCE_FALLBACK: process.env.CLIENT_FORCE_FALLBACK,
    FORCT_FALLBACK: process.env.FORCT_FALLBACK
  };

  process.env.AI_ENGINE = 'deepseek';
  process.env.DEEPSEEK_MODEL = 'deepseek-legacy';
  process.env.CLIENT_DEEPSEEK_MODEL = 'deepseek-client';
  process.env.AI_TIMEOUT_SECONDS = '9';
  process.env.CLIENT_AI_TIMEOUT_SECONDS = '11';
  process.env.DEEPSEEK_API_KEY = 'legacy-deepseek-key';
  process.env.DEEPSEEK_BASE_URL = 'https://legacy.deepseek.local/chat/completions';
  process.env.OPENAI_API_KEY = 'legacy-openai-key';
  process.env.GEMINI_API_KEY = 'legacy-gemini-key';
  process.env.CLIENT_FORCE_FALLBACK = 'true';
  process.env.FORCT_FALLBACK = 'true';

  delete process.env.AI_PROVIDER;
  delete process.env.AI_MODEL;
  delete process.env.AI_TIMEOUT_MS;

  let config = loadConfig();
  assert.equal(config.ai.provider, 'deepseek');
  assert.equal(config.ai.model, 'deepseek-legacy');
  assert.equal(config.ai.timeoutMs, 9000);
  assert.equal(config.ai.proxyToken, 'legacy-deepseek-key');
  assert.equal(config.ai.proxyUrl, 'https://legacy.deepseek.local/chat/completions');
  assert.equal(config.ai.openaiApiKey, 'legacy-openai-key');
  assert.equal(config.ai.geminiApiKey, 'legacy-gemini-key');
  assert.equal(config.ai.legacyForceFallbackRequested, false);
  assert.equal(config.ai.sources.AI_PROVIDER.source, 'AI_ENGINE');
  assert.equal(config.ai.sources.AI_MODEL.source, 'DEEPSEEK_MODEL');
  assert.equal(config.ai.sources.AI_TIMEOUT_MS.source, 'AI_TIMEOUT_SECONDS');
  assert.equal(config.ai.legacyUsed.includes('AI_ENGINE'), true);
  assert.equal(config.ai.legacyIgnored.includes('CLIENT_DEEPSEEK_MODEL'), true);
  assert.equal(config.ai.legacyIgnored.includes('CLIENT_FORCE_FALLBACK'), true);

  process.env.AI_PROVIDER = 'proxy';
  process.env.AI_MODEL = 'deepseek-chat';
  process.env.AI_TIMEOUT_MS = '7000';
  process.env.AI_PROXY_URL = 'https://proxy.canonical.local';
  process.env.AI_PROXY_TOKEN = 'proxy-canonical-token';

  config = loadConfig();
  assert.equal(config.ai.provider, 'proxy');
  assert.equal(config.ai.model, 'deepseek-chat');
  assert.equal(config.ai.timeoutMs, 7000);
  assert.equal(config.ai.proxyUrl, 'https://proxy.canonical.local');
  assert.equal(config.ai.proxyToken, 'proxy-canonical-token');
  assert.equal(config.ai.sources.AI_PROVIDER.source, 'AI_PROVIDER');
  assert.equal(config.ai.sources.AI_MODEL.source, 'AI_MODEL');
  assert.equal(config.ai.sources.AI_TIMEOUT_MS.source, 'AI_TIMEOUT_MS');
  assert.equal(config.ai.legacyUsed.includes('AI_ENGINE'), false);
  assert.equal(config.ai.legacyIgnored.includes('AI_ENGINE'), true);
  assert.equal(config.ai.legacyIgnored.includes('DEEPSEEK_MODEL'), true);
  assert.equal(config.ai.legacyIgnored.includes('DEEPSEEK_BASE_URL'), true);
  assert.equal(config.ai.legacyIgnored.includes('DEEPSEEK_API_KEY'), true);
  assert.equal(config.ai.legacyIgnored.includes('CLIENT_FORCE_FALLBACK'), true);
  assert.equal(config.ai.legacyIgnored.includes('FORCT_FALLBACK'), true);

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
      fallbackProvider: '',
      fallbackModel: '',
      allowedProviders: ['proxy', 'openai', 'deepseek']
    }
  });

  const initial = runtime.get();
  assert.equal(initial.activeProvider, 'proxy');
  assert.equal(initial.activeModel, 'deepseek-chat');
  assert.equal(initial.fallbackConfigured, false);

  const updated = runtime.update({ activeProvider: 'openai', activeModel: 'gpt-4o-mini' });
  assert.equal(updated.ok, true);
  assert.equal(updated.runtime.activeProvider, 'openai');

  const invalid = runtime.update({ activeProvider: 'anthropic' });
  assert.equal(invalid.ok, false);
  assert.equal(invalid.error, 'ACTIVE_PROVIDER_NOT_ALLOWED');

  const invalidPair = runtime.update({ activeProvider: 'deepseek', activeModel: 'gpt-4o-mini' });
  assert.equal(invalidPair.ok, false);
  assert.equal(invalidPair.error, 'AI_PRIMARY_PROVIDER_MODEL_MISMATCH');
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
    has(name) {
      return ['proxy', 'openai', 'deepseek'].includes(name);
    },
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
    configAi: { enabled: true, timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
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

test('ai diagnostics in proxy-only mode do not require direct deepseek config', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'proxy',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: '',
        activeFallbackModel: '',
        fallbackConfigured: false,
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
  const aiService = {
    async runHealthCheck() {
      return {
        ok: true,
        probe: {
          ok: true,
          provider: 'proxy',
          model: 'deepseek-chat',
          fallbackUsed: false,
          fallbackConfigured: false,
          targetProvider: 'proxy',
          targetModel: 'deepseek-chat'
        }
      };
    }
  };
  const providerRegistry = {
    list() { return ['proxy', 'openai', 'deepseek']; },
    has(provider) { return ['proxy', 'openai', 'deepseek'].includes(provider); }
  };

  const result = await runAiDiagnostics({
    aiService,
    runtimeSettings,
    configAi: {
      enabled: true,
      provider: 'proxy',
      model: 'deepseek-chat',
      fallbackProvider: '',
      fallbackModel: '',
      timeoutMs: 8000,
      proxyUrl: 'https://proxy.local/ai',
      proxyToken: 'proxy-token',
      deepseekApiKey: '',
      openaiApiKey: '',
      geminiApiKey: '',
      sources: { AI_PROVIDER: { source: 'AI_PROVIDER' }, AI_MODEL: { source: 'AI_MODEL' } },
      legacyUsed: []
    },
    providerRegistry
  });

  assert.equal(result.ok, true);
  assert.equal(result.checks.fallbackConfigured, false);
  assert.equal(result.checks.runtimeConfigValid, true);
  assert.equal(result.checks.resolvedConfig.diagnosticsTargetProvider, 'proxy');
});

test('ai service rejects invalid provider/model pair and skips implicit fallback path', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'deepseek',
        activeModel: 'gpt-4o-mini',
        activeFallbackProvider: '',
        activeFallbackModel: '',
        fallbackConfigured: false,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) {
      return state;
    },
    getDiagnosticsState() {
      return null;
    }
  };

  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000 },
    runtimeSettings,
    providerRegistry: { get() { return null; } },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });

  const result = await aiService.classifyIntent({ text: 'hello' });
  assert.equal(result.ok, false);
  assert.equal(result.error, 'AI_PRIMARY_PROVIDER_MODEL_MISMATCH');
  assert.equal(result.fallbackConfigured, false);
});

test('ai diagnostics stages: proxy-only valid config', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'proxy',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: '',
        activeFallbackModel: '',
        fallbackConfigured: false,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) { return state; },
    getDiagnosticsState() { return null; }
  };
  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
    runtimeSettings,
    providerRegistry: {
      has(name) { return ['proxy', 'openai', 'deepseek'].includes(name); },
      get() { return { async invoke() { return { provider: 'proxy', model: 'deepseek-chat', output: 'OK' }; } }; }
    },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });
  const result = await aiService.runHealthCheck();
  assert.equal(result.ok, true);
  assert.equal(result.state.finalDiagnosticsStatus, 'DIAGNOSTICS_OK');
  assert.equal(result.state.fallbackConfigured, false);
  assert.equal(result.state.fallbackStatus, 'not configured');
  assert.equal(result.state.primaryTestAttempted, true);
});

test('ai diagnostics stages: invalid provider/model pair is CONFIG_INVALID and primary not tested', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'deepseek',
        activeModel: 'gpt-4o-mini',
        activeFallbackProvider: '',
        activeFallbackModel: '',
        fallbackConfigured: false,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) { return state; },
    getDiagnosticsState() { return null; }
  };
  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000, deepseekApiKey: 'x' },
    runtimeSettings,
    providerRegistry: { has() { return true; }, get() { return { async invoke() { return { provider: 'deepseek', model: 'deepseek-chat', output: 'OK' }; } }; } },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });
  const result = await aiService.runHealthCheck();
  assert.equal(result.ok, false);
  assert.equal(result.state.finalDiagnosticsStatus, 'CONFIG_INVALID');
  assert.equal(result.state.primaryTestAttempted, false);
  assert.equal(result.state.primaryStatus, 'not tested');
});

test('ai diagnostics stages: invalid runtime override reports CONFIG_INVALID', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'openai',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: '',
        activeFallbackModel: '',
        fallbackConfigured: false,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) { return state; },
    getDiagnosticsState() { return null; }
  };
  const aiService = createAiService({
    configAi: { enabled: true, provider: 'proxy', model: 'deepseek-chat', timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
    runtimeSettings,
    providerRegistry: { has() { return true; }, get() { return { async invoke() { return { provider: 'openai', model: 'gpt-4o-mini', output: 'OK' }; } }; } },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });
  const result = await aiService.runHealthCheck();
  assert.equal(result.ok, false);
  assert.equal(result.state.finalDiagnosticsStatus, 'CONFIG_INVALID');
  assert.equal(result.state.runtimeOverridePresent, true);
  assert.equal(result.state.runtimeOverrideValid, false);
});

test('ai diagnostics stages: primary timeout/auth/network errors are PRIMARY_PROVIDER_FAILED', async () => {
  db.resetStore();
  const scenarios = [
    { code: 'AI_TIMEOUT', expected: 'PRIMARY_TIMEOUT' },
    { code: 'AI_AUTH_ERROR', expected: 'PRIMARY_AUTH_ERROR' },
    { code: 'AI_NETWORK_ERROR', expected: 'PRIMARY_NETWORK_ERROR' }
  ];
  for (const scenario of scenarios) {
    const runtimeSettings = {
      get() {
        return {
          activeProvider: 'proxy',
          activeModel: 'deepseek-chat',
          activeFallbackProvider: '',
          activeFallbackModel: '',
          fallbackConfigured: false,
          aiEnabledRuntime: true,
          aiBusinessUsageEnabledRuntime: true
        };
      },
      setDiagnosticsState(state) { return state; },
      getDiagnosticsState() { return null; }
    };
    const aiService = createAiService({
      configAi: { enabled: true, timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
      runtimeSettings,
      providerRegistry: {
        has() { return true; },
        get() {
          return {
            async invoke() {
              const error = new Error('primary error');
              error.code = scenario.code;
              throw error;
            }
          };
        }
      },
      db,
      logger: { info() {}, warn() {}, error() {} }
    });
    const result = await aiService.runHealthCheck();
    assert.equal(result.ok, false);
    assert.equal(result.state.finalDiagnosticsStatus, 'PRIMARY_PROVIDER_FAILED');
    assert.equal(result.state.primaryTestResult, scenario.expected);
  }
});

test('ai diagnostics stages: primary failed + fallback success', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'proxy',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: 'openai',
        activeFallbackModel: 'gpt-4o-mini',
        fallbackConfigured: true,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) { return state; },
    getDiagnosticsState() { return null; }
  };
  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
    runtimeSettings,
    providerRegistry: {
      has() { return true; },
      get(name) {
        if (name === 'proxy') return { async invoke() { const error = new Error('down'); error.code = 'AI_TIMEOUT'; throw error; } };
        return { async invoke() { return { provider: 'openai', model: 'gpt-4o-mini', output: 'OK' }; } };
      }
    },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });
  const result = await aiService.runHealthCheck();
  assert.equal(result.ok, true);
  assert.equal(result.state.finalDiagnosticsStatus, 'DIAGNOSTICS_OK');
  assert.equal(result.state.primaryTestResult, 'PRIMARY_TIMEOUT');
  assert.equal(result.state.fallbackTestResult, 'DIAGNOSTICS_OK');
});

test('ai diagnostics stages: primary failed + fallback failed', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'proxy',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: 'openai',
        activeFallbackModel: 'gpt-4o-mini',
        fallbackConfigured: true,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) { return state; },
    getDiagnosticsState() { return null; }
  };
  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
    runtimeSettings,
    providerRegistry: {
      has() { return true; },
      get(name) {
        if (name === 'proxy') return { async invoke() { const error = new Error('down'); error.code = 'AI_AUTH_ERROR'; throw error; } };
        return { async invoke() { const error = new Error('down2'); error.code = 'AI_NETWORK_ERROR'; throw error; } };
      }
    },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });
  const result = await aiService.runHealthCheck();
  assert.equal(result.ok, false);
  assert.equal(result.state.finalDiagnosticsStatus, 'FALLBACK_PROVIDER_FAILED');
  assert.equal(result.state.primaryTestResult, 'PRIMARY_AUTH_ERROR');
  assert.equal(result.state.fallbackTestResult, 'FALLBACK_NETWORK_ERROR');
});

test('ai diagnostics stages: no fallback configured keeps fallback status not configured', async () => {
  db.resetStore();
  const runtimeSettings = {
    get() {
      return {
        activeProvider: 'proxy',
        activeModel: 'deepseek-chat',
        activeFallbackProvider: '',
        activeFallbackModel: '',
        fallbackConfigured: false,
        aiEnabledRuntime: true,
        aiBusinessUsageEnabledRuntime: true
      };
    },
    setDiagnosticsState(state) { return state; },
    getDiagnosticsState() { return null; }
  };
  const aiService = createAiService({
    configAi: { enabled: true, timeoutMs: 1000, proxyUrl: 'https://proxy.local', proxyToken: 'token' },
    runtimeSettings,
    providerRegistry: {
      has() { return true; },
      get() { return { async invoke() { const error = new Error('down'); error.code = 'AI_TIMEOUT'; throw error; } }; }
    },
    db,
    logger: { info() {}, warn() {}, error() {} }
  });
  const result = await aiService.runHealthCheck();
  assert.equal(result.ok, false);
  assert.equal(result.state.finalDiagnosticsStatus, 'PRIMARY_PROVIDER_FAILED');
  assert.equal(result.state.fallbackConfigured, false);
  assert.equal(result.state.fallbackStatus, 'not configured');
});

test('master bot AI control plane commands are admin-only and usable', async () => {
  db.resetStore();
  process.env.MASTER_BOT_ADMIN_IDS = '8001';
  const config = loadConfig();

  const aiInfrastructure = {
    runtimeSettings: {
      lastPatch: null,
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
      update(patch) { this.lastPatch = patch; return { ok: true, runtime: this.get() }; }
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

  const clearFallback = await handleMasterWebhook({
    body: { message: { text: '/ai_switch provider:proxy model:deepseek-chat fallbackProvider:- fallbackModel:-', chat: { id: 8001 }, from: { id: 8001, first_name: 'Admin' } } },
    config,
    aiInfrastructure
  });
  assert.equal(clearFallback.ok, true);
  assert.equal(aiInfrastructure.runtimeSettings.lastPatch.activeFallbackProvider, '');
  assert.equal(aiInfrastructure.runtimeSettings.lastPatch.activeFallbackModel, '');

  const navMenu = await handleMasterWebhook({
    body: { callback_query: { id: 'cb-nav', from: { id: 8001, first_name: 'Admin' }, message: { chat: { id: 8001 } }, data: 'nav:menu' } },
    config,
    aiInfrastructure
  });
  assert.equal(navMenu.ok, true);
  assert.match(navMenu.text, /Главное меню/i);

  delete process.env.MASTER_BOT_ADMIN_IDS;
});
