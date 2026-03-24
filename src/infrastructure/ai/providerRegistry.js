const { createProxyProvider } = require('./providers/proxyProvider');
const { createDeepseekProvider } = require('./providers/deepseekProvider');
const { createOpenAiProvider } = require('./providers/openaiProvider');

function createProviderRegistry({ config }) {
  const providers = new Map();
  const proxyProvider = createProxyProvider({ config });
  const openaiProvider = createOpenAiProvider({ config });
  const deepseekProvider = createDeepseekProvider({ config });

  providers.set('proxy', proxyProvider);
  providers.set('openai', openaiProvider);
  providers.set('deepseek', deepseekProvider);

  return {
    has(provider) {
      return providers.has(String(provider || '').toLowerCase());
    },
    get(provider) {
      return providers.get(String(provider || '').toLowerCase()) || null;
    },
    list() {
      return Array.from(providers.keys());
    },
    getPrimaryDefault() {
      return proxyProvider;
    }
  };
}

module.exports = { createProviderRegistry };
