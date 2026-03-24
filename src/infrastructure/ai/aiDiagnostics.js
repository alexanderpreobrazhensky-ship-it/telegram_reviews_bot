function maskSecret(value) {
  if (!value) return 'missing';
  const raw = String(value);
  if (raw.length <= 6) return 'configured';
  return `${raw.slice(0, 2)}***${raw.slice(-2)}`;
}

async function runAiDiagnostics({ aiService, runtimeSettings, configAi, providerRegistry }) {
  const runtime = runtimeSettings.get();
  const providers = providerRegistry.list();
  const result = await aiService.runHealthCheck({ diagnosticsMode: true });

  return {
    ok: result.ok,
    checks: {
      infraEnabled: Boolean(configAi.enabled),
      runtimeEnabled: Boolean(runtime.aiEnabledRuntime),
      runtimeConfigValid: providers.includes(runtime.activeProvider) && providers.includes(runtime.activeFallbackProvider),
      activeProviderAvailable: providerRegistry.has(runtime.activeProvider),
      fallbackProviderAvailable: providerRegistry.has(runtime.activeFallbackProvider),
      proxyConfigured: Boolean(configAi.proxyUrl && configAi.proxyToken),
      authConfigured: {
        proxyToken: maskSecret(configAi.proxyToken),
        openaiApiKey: maskSecret(configAi.openaiApiKey),
        deepseekApiKey: maskSecret(configAi.deepseekApiKey)
      }
    },
    last: runtimeSettings.getDiagnosticsState(),
    probe: result
  };
}

module.exports = { runAiDiagnostics, maskSecret };
