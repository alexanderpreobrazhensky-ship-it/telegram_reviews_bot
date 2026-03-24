function normalizeProvider(value) {
  return String(value || '').trim().toLowerCase();
}

function normalizeModel(value) {
  return String(value || '').trim();
}

function inferModelProvider(model) {
  const normalized = normalizeModel(model).toLowerCase();
  if (!normalized) return '';
  if (normalized.startsWith('deepseek')) return 'deepseek';
  if (
    normalized.startsWith('gpt-')
    || normalized.startsWith('o1')
    || normalized.startsWith('o3')
    || normalized.startsWith('o4')
  ) return 'openai';
  return '';
}

function isProviderModelCompatible(provider, model) {
  const providerName = normalizeProvider(provider);
  const inferred = inferModelProvider(model);
  if (!providerName || !normalizeModel(model)) return false;
  if (providerName === 'proxy') return true;
  if (!inferred) return true;
  return inferred === providerName;
}

function isFallbackConfigured(fallbackProvider, fallbackModel) {
  const providerName = normalizeProvider(fallbackProvider);
  const modelName = normalizeModel(fallbackModel);
  if (!providerName && !modelName) return false;
  return Boolean(providerName && modelName);
}

function validateProviderModelPair(provider, model, { context = 'PRIMARY' } = {}) {
  const providerName = normalizeProvider(provider);
  const modelName = normalizeModel(model);
  if (!providerName) return { ok: false, error: `AI_${context}_PROVIDER_REQUIRED` };
  if (!modelName) return { ok: false, error: `AI_${context}_MODEL_REQUIRED` };
  if (!isProviderModelCompatible(providerName, modelName)) {
    return {
      ok: false,
      error: `AI_${context}_PROVIDER_MODEL_MISMATCH`,
      provider: providerName,
      model: modelName,
      inferredProvider: inferModelProvider(modelName) || ''
    };
  }
  return { ok: true };
}

module.exports = {
  normalizeProvider,
  normalizeModel,
  inferModelProvider,
  isProviderModelCompatible,
  isFallbackConfigured,
  validateProviderModelPair
};
