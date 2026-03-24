const { validateProviderModelPair, isFallbackConfigured } = require('./providerModelRules');

function maskSecret(value) {
  if (!value) return 'missing';
  const raw = String(value);
  if (raw.length <= 6) return 'configured';
  return `${raw.slice(0, 2)}***${raw.slice(-2)}`;
}

async function runAiDiagnostics({ aiService, runtimeSettings, configAi, providerRegistry }) {
  const runtime = runtimeSettings.get();
  const providers = providerRegistry.list();
  const fallbackConfigured = isFallbackConfigured(runtime.activeFallbackProvider, runtime.activeFallbackModel);
  const primaryPair = validateProviderModelPair(runtime.activeProvider, runtime.activeModel, { context: 'PRIMARY' });
  const fallbackPair = fallbackConfigured
    ? validateProviderModelPair(runtime.activeFallbackProvider, runtime.activeFallbackModel, { context: 'FALLBACK' })
    : { ok: true };
  const result = await aiService.runHealthCheck({ diagnosticsMode: true });

  return {
    ok: result.ok,
    checks: {
      infraEnabled: Boolean(configAi.enabled),
      runtimeEnabled: Boolean(runtime.aiEnabledRuntime),
      runtimeConfigValid: providers.includes(runtime.activeProvider)
        && primaryPair.ok
        && (!fallbackConfigured || (providers.includes(runtime.activeFallbackProvider) && fallbackPair.ok)),
      activeProviderAvailable: providerRegistry.has(runtime.activeProvider),
      fallbackProviderAvailable: fallbackConfigured ? providerRegistry.has(runtime.activeFallbackProvider) : true,
      fallbackConfigured,
      providerModelPairValid: primaryPair.ok,
      fallbackProviderModelPairValid: fallbackPair.ok,
      proxyConfigured: Boolean(configAi.proxyUrl && configAi.proxyToken),
      authConfigured: {
        proxyToken: maskSecret(configAi.proxyToken),
        openaiApiKey: maskSecret(configAi.openaiApiKey),
        deepseekApiKey: maskSecret(configAi.deepseekApiKey),
        geminiApiKey: maskSecret(configAi.geminiApiKey)
      },
      resolvedConfig: {
        configuredProvider: configAi.provider,
        configuredModel: configAi.model,
        effectiveProvider: runtime.activeProvider,
        effectiveModel: runtime.activeModel,
        diagnosticsTargetProvider: result.probe?.targetProvider || runtime.activeProvider,
        diagnosticsTargetModel: result.probe?.targetModel || runtime.activeModel,
        fallbackConfigured,
        fallbackProvider: fallbackConfigured ? runtime.activeFallbackProvider : '',
        fallbackModel: fallbackConfigured ? runtime.activeFallbackModel : '',
        timeoutMs: configAi.timeoutMs,
        sourceProvider: configAi.sources?.AI_PROVIDER?.source || 'default',
        sourceModel: configAi.sources?.AI_MODEL?.source || 'default',
        sourceFallbackProvider: configAi.sources?.AI_FALLBACK_PROVIDER?.source || 'default',
        sourceFallbackModel: configAi.sources?.AI_FALLBACK_MODEL?.source || 'default',
        sourceTimeoutMs: configAi.sources?.AI_TIMEOUT_MS?.source || 'default',
        legacyUsed: configAi.legacyUsed || []
      }
    },
    last: runtimeSettings.getDiagnosticsState(),
    probe: result
  };
}

module.exports = { runAiDiagnostics, maskSecret };
