const { resolveAiConfig } = require('./resolveAiConfig');

function maskSecret(value) {
  if (!value) return 'missing';
  const raw = String(value);
  if (raw.length <= 6) return 'configured';
  return `${raw.slice(0, 2)}***${raw.slice(-2)}`;
}

async function runAiDiagnostics({ aiService, runtimeSettings, configAi, providerRegistry }) {
  const runtime = runtimeSettings.get();
  const providers = providerRegistry.list();
  const diagnosticsState = runtimeSettings.getDiagnosticsState();
  const resolved = resolveAiConfig({ configAi, runtime, diagnostics: diagnosticsState });
  const result = await aiService.runHealthCheck({ diagnosticsMode: true });

  return {
    ok: result.ok,
    checks: {
      infraEnabled: Boolean(configAi.enabled),
      runtimeEnabled: Boolean(runtime.aiEnabledRuntime),
      runtimeConfigValid: providers.includes(resolved.effectiveProvider)
        && resolved.pairChecks.primary.ok
        && (!resolved.effectiveFallbackEnabled || (providers.includes(resolved.effectiveFallbackProvider) && resolved.pairChecks.fallback.ok)),
      activeProviderAvailable: providerRegistry.has(resolved.effectiveProvider),
      fallbackProviderAvailable: resolved.effectiveFallbackEnabled ? providerRegistry.has(resolved.effectiveFallbackProvider) : true,
      fallbackConfigured: resolved.effectiveFallbackEnabled,
      providerModelPairValid: resolved.pairChecks.primary.ok,
      fallbackProviderModelPairValid: resolved.pairChecks.fallback.ok,
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
        effectiveProvider: resolved.effectiveProvider,
        effectiveModel: resolved.effectiveModel,
        diagnosticsTargetProvider: result.probe?.targetProvider || resolved.diagnosticsTargetProvider,
        diagnosticsTargetModel: result.probe?.targetModel || resolved.diagnosticsTargetModel,
        fallbackConfigured: resolved.effectiveFallbackEnabled,
        fallbackProvider: resolved.effectiveFallbackEnabled ? resolved.effectiveFallbackProvider : '',
        fallbackModel: resolved.effectiveFallbackEnabled ? resolved.effectiveFallbackModel : '',
        timeoutMs: configAi.timeoutMs,
        sourceProvider: resolved.sources.provider,
        sourceModel: resolved.sources.model,
        sourceFallbackProvider: resolved.sources.fallbackProvider,
        sourceFallbackModel: resolved.sources.fallbackModel,
        sourceTimeoutMs: configAi.sources?.AI_TIMEOUT_MS?.source || 'default',
        legacyDetected: configAi.legacyDetected || [],
        legacyIgnored: configAi.legacyIgnored || [],
        legacyUsed: resolved.legacyUsed || []
      }
    },
    last: diagnosticsState,
    probe: result
  };
}

module.exports = { runAiDiagnostics, maskSecret };
