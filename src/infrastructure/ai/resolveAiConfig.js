const { normalizeProvider, normalizeModel, isFallbackConfigured, validateProviderModelPair } = require('./providerModelRules');

function detectResolutionSource(meta = {}) {
  if (!meta || typeof meta !== 'object') return 'default';
  if (meta.tier === 'legacy_shared' || meta.tier === 'legacy_client') return 'legacy_alias';
  if (meta.tier === 'canonical') return 'env';
  return 'default';
}

function resolveAiConfig({ configAi = {}, runtime = {}, diagnostics = null }) {
  const configuredProvider = normalizeProvider(configAi.provider || 'proxy');
  const configuredModel = normalizeModel(configAi.model || 'deepseek-chat');
  const configuredFallbackProvider = normalizeProvider(configAi.fallbackProvider || '');
  const configuredFallbackModel = normalizeModel(configAi.fallbackModel || '');
  const configuredFallbackEnabled = isFallbackConfigured(configuredFallbackProvider, configuredFallbackModel);

  const effectiveProvider = normalizeProvider(runtime.activeProvider || configuredProvider || 'proxy');
  const effectiveModel = normalizeModel(runtime.activeModel || configuredModel || 'deepseek-chat');
  const effectiveFallbackProvider = normalizeProvider(runtime.activeFallbackProvider || configuredFallbackProvider || '');
  const effectiveFallbackModel = normalizeModel(runtime.activeFallbackModel || configuredFallbackModel || '');
  const effectiveFallbackEnabled = isFallbackConfigured(effectiveFallbackProvider, effectiveFallbackModel);

  const primaryPair = validateProviderModelPair(effectiveProvider, effectiveModel, { context: 'PRIMARY' });
  const fallbackPair = effectiveFallbackEnabled
    ? validateProviderModelPair(effectiveFallbackProvider, effectiveFallbackModel, { context: 'FALLBACK' })
    : { ok: true };

  const diagnosticsTargetProvider = normalizeProvider(diagnostics?.targetProvider || effectiveProvider);
  const diagnosticsTargetModel = normalizeModel(diagnostics?.targetModel || effectiveModel);
  const runtimeOverridePresent = Boolean(
    normalizeProvider(runtime.activeProvider) && normalizeProvider(runtime.activeProvider) !== configuredProvider
    || normalizeModel(runtime.activeModel) && normalizeModel(runtime.activeModel) !== configuredModel
    || normalizeProvider(runtime.activeFallbackProvider) && normalizeProvider(runtime.activeFallbackProvider) !== configuredFallbackProvider
    || normalizeModel(runtime.activeFallbackModel) && normalizeModel(runtime.activeFallbackModel) !== configuredFallbackModel
  );
  const runtimeOverrideValid = pairChecksValid({
    primary: validateProviderModelPair(effectiveProvider, effectiveModel, { context: 'PRIMARY' }),
    fallbackEnabled: effectiveFallbackEnabled,
    fallbackProvider: effectiveFallbackProvider,
    fallbackModel: effectiveFallbackModel
  });

  return {
    configuredProvider,
    configuredModel,
    configuredFallbackProvider: configuredFallbackEnabled ? configuredFallbackProvider : '',
    configuredFallbackModel: configuredFallbackEnabled ? configuredFallbackModel : '',
    configuredFallbackEnabled,
    effectiveProvider,
    effectiveModel,
    effectiveFallbackProvider: effectiveFallbackEnabled ? effectiveFallbackProvider : '',
    effectiveFallbackModel: effectiveFallbackEnabled ? effectiveFallbackModel : '',
    effectiveFallbackEnabled,
    diagnosticsTargetProvider,
    diagnosticsTargetModel,
    runtimeOverridePresent,
    runtimeOverrideValid,
    pairChecks: {
      primary: primaryPair,
      fallback: fallbackPair
    },
    sources: {
      provider: detectResolutionSource(configAi.sources?.AI_PROVIDER),
      model: detectResolutionSource(configAi.sources?.AI_MODEL),
      fallbackProvider: detectResolutionSource(configAi.sources?.AI_FALLBACK_PROVIDER),
      fallbackModel: detectResolutionSource(configAi.sources?.AI_FALLBACK_MODEL)
    },
    legacyDetected: configAi.legacyDetected || [],
    legacyIgnored: configAi.legacyIgnored || [],
    legacyUsed: configAi.legacyUsed || []
  };
}

function pairChecksValid({ primary, fallbackEnabled, fallbackProvider, fallbackModel }) {
  if (!primary.ok) return false;
  if (!fallbackEnabled) return true;
  return validateProviderModelPair(fallbackProvider, fallbackModel, { context: 'FALLBACK' }).ok;
}

module.exports = { resolveAiConfig };
