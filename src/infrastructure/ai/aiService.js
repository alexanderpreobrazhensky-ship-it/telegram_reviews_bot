const { resolveTaskPolicy } = require('./taskRouter');
const { validateProviderModelPair } = require('./providerModelRules');
const { resolveAiConfig } = require('./resolveAiConfig');

function buildBusinessDisabled(taskType) {
  return {
    ok: false,
    error: 'AI_BUSINESS_USAGE_DISABLED',
    taskType
  };
}

function normalizeError(error) {
  const code = error?.code || 'AI_PROVIDER_ERROR';
  return {
    code,
    message: String(error?.message || 'AI provider call failed').slice(0, 500)
  };
}

function createAiService({ configAi, runtimeSettings, providerRegistry, db, logger }) {
  async function executeTask(taskType, input, options = {}) {
    const startedAt = Date.now();
    const runtime = runtimeSettings.get();
    const diagnosticsMode = Boolean(options.diagnosticsMode);

    if (!runtime.aiEnabledRuntime || !configAi.enabled) {
      return {
        ok: false,
        error: 'AI_DISABLED',
        taskType,
        provider: runtime.activeProvider,
        model: runtime.activeModel
      };
    }

    if (!diagnosticsMode && !runtime.aiBusinessUsageEnabledRuntime) {
      return buildBusinessDisabled(taskType);
    }

    const policy = resolveTaskPolicy(taskType, options);
    const resolved = resolveAiConfig({ configAi, runtime, diagnostics: runtimeSettings.getDiagnosticsState() });
    const providerName = options.provider || resolved.effectiveProvider;
    const model = options.model || resolved.effectiveModel;
    const fallbackProviderName = resolved.effectiveFallbackProvider;
    const fallbackModel = resolved.effectiveFallbackModel;
    const fallbackConfigured = resolved.effectiveFallbackEnabled;

    const primaryPairCheck = (options.provider || options.model)
      ? validateProviderModelPair(providerName, model, { context: 'PRIMARY' })
      : resolved.pairChecks.primary;
    if (!primaryPairCheck.ok) {
      return { ok: false, error: primaryPairCheck.error, taskType, provider: providerName, model, fallbackUsed: false, fallbackConfigured };
    }
    if (fallbackConfigured) {
      const fallbackPairCheck = resolved.pairChecks.fallback;
      if (!fallbackPairCheck.ok) {
        return { ok: false, error: fallbackPairCheck.error, taskType, provider: fallbackProviderName, model: fallbackModel, fallbackUsed: false, fallbackConfigured };
      }
    }

    const primaryProvider = providerRegistry.get(providerName);
    const fallbackProvider = fallbackConfigured ? providerRegistry.get(fallbackProviderName) : null;

    if (!primaryProvider) {
      return { ok: false, error: 'AI_INVALID_PROVIDER', taskType, provider: providerName };
    }

    const baseEvent = {
      taskType,
      policy,
      provider: providerName,
      model,
      fallbackProvider: fallbackProviderName,
      fallbackModel,
      fallbackConfigured
    };

    try {
      const response = await primaryProvider.invoke({
        model,
        prompt: typeof input === 'string' ? input : JSON.stringify(input || {}),
        timeoutMs: options.timeoutMs || configAi.timeoutMs
      });
      const durationMs = Date.now() - startedAt;
      db.createAiEvent({ ...baseEvent, durationMs, success: true, fallbackUsed: false });
      logger.info('ai task completed', { ...baseEvent, durationMs, success: true, fallbackUsed: false });
      return {
        ok: true,
        output: response.output,
        provider: response.provider,
        model: response.model || model,
        durationMs,
        fallbackUsed: false,
        fallbackConfigured,
        targetProvider: providerName,
        targetModel: model
      };
    } catch (primaryError) {
      const normalizedPrimaryError = normalizeError(primaryError);
      if (!fallbackConfigured || !fallbackProvider || fallbackProviderName === providerName) {
        const durationMs = Date.now() - startedAt;
        db.createAiEvent({ ...baseEvent, durationMs, success: false, fallbackUsed: false, errorCode: normalizedPrimaryError.code, errorSummary: normalizedPrimaryError.message });
        logger.warn('ai task failed without fallback', { ...baseEvent, durationMs, errorCode: normalizedPrimaryError.code });
        return {
          ok: false,
          error: normalizedPrimaryError.code,
          errorMessage: normalizedPrimaryError.message,
          provider: providerName,
          model,
          durationMs,
          fallbackUsed: false,
          fallbackConfigured,
          targetProvider: providerName,
          targetModel: model
        };
      }

      try {
        const response = await fallbackProvider.invoke({
          model: fallbackModel,
          prompt: typeof input === 'string' ? input : JSON.stringify(input || {}),
          timeoutMs: options.timeoutMs || configAi.timeoutMs
        });
        const durationMs = Date.now() - startedAt;
        db.createAiEvent({ ...baseEvent, provider: fallbackProviderName, model: fallbackModel, durationMs, success: true, fallbackUsed: true });
        logger.warn('ai task fallback success', { ...baseEvent, durationMs, fallbackUsed: true, fallbackProvider: fallbackProviderName });
        return {
          ok: true,
          output: response.output,
          provider: response.provider,
          model: response.model || fallbackModel,
          durationMs,
          fallbackUsed: true,
          fallbackConfigured,
          targetProvider: providerName,
          targetModel: model,
          primaryError: normalizedPrimaryError.code
        };
      } catch (fallbackError) {
        const normalizedFallbackError = normalizeError(fallbackError);
        const durationMs = Date.now() - startedAt;
        db.createAiEvent({ ...baseEvent, durationMs, success: false, fallbackUsed: true, errorCode: normalizedFallbackError.code, errorSummary: normalizedFallbackError.message });
        logger.error('ai task failed with fallback', { ...baseEvent, durationMs, primaryError: normalizedPrimaryError.code, fallbackError: normalizedFallbackError.code });
        return {
          ok: false,
          error: normalizedFallbackError.code,
          errorMessage: normalizedFallbackError.message,
          provider: fallbackProviderName,
          model: fallbackModel,
          durationMs,
          fallbackUsed: true,
          fallbackConfigured,
          targetProvider: providerName,
          targetModel: model,
          primaryError: normalizedPrimaryError.code
        };
      }
    }
  }

  async function classifyIntent(input, options = {}) { return executeTask('classifyIntent', input, options); }
  async function summarizeRequest(input, options = {}) { return executeTask('summarizeRequest', input, options); }
  async function generateReply(input, options = {}) { return executeTask('generateReply', input, options); }
  async function analyzeFeedback(input, options = {}) { return executeTask('analyzeFeedback', input, options); }
  async function explainIntegrationError(input, options = {}) { return executeTask('explainIntegrationError', input, options); }

  async function runHealthCheck(options = {}) {
    const startedAt = Date.now();
    const runtime = runtimeSettings.get();
    const probe = await executeTask('runHealthCheck', options.prompt || 'Respond strictly with: OK', { diagnosticsMode: true, ...options });
    const summary = probe.ok
      ? `AI diagnostics OK via ${probe.provider}/${probe.model}`
      : `AI diagnostics failed: ${probe.error || 'UNKNOWN'}`;
    const state = runtimeSettings.setDiagnosticsState({
      status: probe.ok ? 'success' : 'fail',
      summary,
      at: new Date().toISOString(),
      durationMs: Date.now() - startedAt,
      provider: probe.provider || runtime.activeProvider,
      model: probe.model || runtime.activeModel,
      fallbackUsed: probe.fallbackUsed,
      errorCode: probe.error || '',
      targetProvider: probe.targetProvider || runtime.activeProvider,
      targetModel: probe.targetModel || runtime.activeModel,
      fallbackConfigured: Boolean(probe.fallbackConfigured)
    });
    return { ok: probe.ok, probe, summary, state };
  }

  return {
    classifyIntent,
    summarizeRequest,
    generateReply,
    analyzeFeedback,
    explainIntegrationError,
    runHealthCheck
  };
}

module.exports = { createAiService };
