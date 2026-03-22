function createAiService({ config = {} } = {}) {
  const aiConfig = {
    enabled: Boolean(config.enabled),
    provider: config.provider || 'openai',
    model: config.model || '',
    timeoutMs: Number(config.timeoutMs) || 5000
  };

  function disabled(operation) {
    return {
      ok: false,
      enabled: aiConfig.enabled,
      provider: aiConfig.provider,
      model: aiConfig.model,
      error: 'AI_DISABLED',
      operation
    };
  }

  return {
    getConfig() {
      return { ...aiConfig, apiKeyConfigured: Boolean(config.apiKey) };
    },
    async processMessage(input) {
      return { ...disabled('processMessage'), input };
    },
    async suggestReply(request) {
      return { ...disabled('suggestReply'), request, text: '' };
    },
    async classifyRequest(data) {
      return { ...disabled('classifyRequest'), data, label: '' };
    }
  };
}

module.exports = { createAiService };
