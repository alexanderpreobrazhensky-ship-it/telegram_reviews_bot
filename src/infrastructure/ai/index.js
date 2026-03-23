const PROVIDERS = Object.freeze({
  openai: 'openai',
  anthropic: 'anthropic',
  none: 'none'
});

function normalizeProvider(provider = '') {
  const value = String(provider || '').trim().toLowerCase();
  return Object.values(PROVIDERS).includes(value) ? value : (value || PROVIDERS.none);
}

function buildDisabledResult(aiConfig, operation, payloadKey, payload) {
  return {
    ok: false,
    enabled: aiConfig.enabled,
    provider: aiConfig.provider,
    model: aiConfig.model,
    error: 'AI_DISABLED',
    operation,
    [payloadKey]: payload
  };
}

function createDisabledProvider(aiConfig) {
  return {
    async processMessage(input) {
      return buildDisabledResult(aiConfig, 'processMessage', 'input', input);
    },
    async suggestReply(request) {
      return { ...buildDisabledResult(aiConfig, 'suggestReply', 'request', request), text: '' };
    },
    async classifyRequest(data) {
      return { ...buildDisabledResult(aiConfig, 'classifyRequest', 'data', data), label: '' };
    }
  };
}

function createProviderRegistry(aiConfig) {
  const disabledProvider = createDisabledProvider(aiConfig);
  return {
    getSelectedProvider() {
      return aiConfig.enabled ? aiConfig.provider : PROVIDERS.none;
    },
    has(provider) {
      return Object.values(PROVIDERS).includes(normalizeProvider(provider));
    },
    get(provider = aiConfig.provider) {
      const normalized = normalizeProvider(provider);
      if (!aiConfig.enabled || normalized === PROVIDERS.none) return disabledProvider;
      return disabledProvider;
    }
  };
}

function createAiService({ config = {} } = {}) {
  const aiConfig = {
    enabled: Boolean(config.enabled),
    provider: normalizeProvider(config.provider || PROVIDERS.openai),
    model: config.model || '',
    timeoutMs: Number(config.timeoutMs) || 5000,
    apiKeyConfigured: Boolean(config.apiKey)
  };
  const registry = createProviderRegistry(aiConfig);

  return {
    getConfig() {
      return { ...aiConfig, selectedProvider: registry.getSelectedProvider(), availableProviders: Object.values(PROVIDERS) };
    },
    getProviderRegistry() {
      return registry;
    },
    async processMessage(input) {
      return registry.get().processMessage(input);
    },
    async suggestReply(request) {
      return registry.get().suggestReply(request);
    },
    async classifyRequest(data) {
      return registry.get().classifyRequest(data);
    }
  };
}

module.exports = { createAiService, createProviderRegistry, PROVIDERS };
