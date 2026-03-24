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

function mapProviderFailureCode(errorCode, scope = 'PRIMARY') {
  const prefix = scope === 'FALLBACK' ? 'FALLBACK' : 'PRIMARY';
  if (errorCode === 'AI_TIMEOUT') return `${prefix}_TIMEOUT`;
  if (errorCode === 'AI_AUTH_ERROR') return `${prefix}_AUTH_ERROR`;
  if (errorCode === 'AI_NETWORK_ERROR') return `${prefix}_NETWORK_ERROR`;
  return `${prefix}_PROVIDER_ERROR`;
}

function buildDiagnosticsConfigValidation({ resolved, providerRegistry, runtime }) {
  if (!providerRegistry.has(resolved.effectiveProvider)) {
    return { ok: false, reason: 'CONFIG_PROVIDER_NOT_ALLOWED', detail: 'Configured provider is not available in registry' };
  }
  if (!resolved.pairChecks.primary.ok) {
    return { ok: false, reason: 'CONFIG_PROVIDER_MODEL_MISMATCH', detail: resolved.pairChecks.primary.error };
  }
  if (resolved.runtimeOverridePresent && !resolved.runtimeOverrideValid) {
    return { ok: false, reason: 'CONFIG_RUNTIME_OVERRIDE_INVALID', detail: 'Runtime override provider/model is invalid' };
  }
  if (resolved.effectiveFallbackEnabled) {
    if (!providerRegistry.has(resolved.effectiveFallbackProvider)) {
      return { ok: false, reason: 'CONFIG_PROVIDER_NOT_ALLOWED', detail: 'Fallback provider is not available in registry' };
    }
    if (!resolved.pairChecks.fallback.ok) {
      return { ok: false, reason: 'CONFIG_PROVIDER_MODEL_MISMATCH', detail: resolved.pairChecks.fallback.error };
    }
  }
  if (resolved.effectiveProvider === 'proxy' && !(runtime.proxyConfigured || resolved.configuredProvider !== 'proxy')) {
    return { ok: false, reason: 'CONFIG_PROXY_NOT_CONFIGURED', detail: 'Proxy provider selected but proxy URL/token are missing' };
  }
  return { ok: true, reason: 'CONFIG_VALID', detail: '' };
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
    const resolved = resolveAiConfig({ configAi, runtime, diagnostics: runtimeSettings.getDiagnosticsState() });
    const timeoutMs = options.timeoutMs || configAi.timeoutMs;
    const prompt = options.prompt || 'Respond strictly with: OK';
    const diagnostics = {
      configuredProvider: resolved.configuredProvider || '',
      configuredModel: resolved.configuredModel || '',
      effectiveProvider: resolved.effectiveProvider || '',
      effectiveModel: resolved.effectiveModel || '',
      runtimeOverridePresent: Boolean(resolved.runtimeOverridePresent),
      runtimeOverrideValid: Boolean(resolved.runtimeOverrideValid),
      fallbackConfigured: Boolean(resolved.effectiveFallbackEnabled),
      diagnosticsTargetProvider: resolved.diagnosticsTargetProvider || resolved.effectiveProvider,
      diagnosticsTargetModel: resolved.diagnosticsTargetModel || resolved.effectiveModel,
      configStatus: 'valid',
      primaryStatus: 'not tested',
      fallbackStatus: resolved.effectiveFallbackEnabled ? 'not tested' : 'not configured',
      primaryTestAttempted: false,
      primaryTestResult: 'NOT_TESTED',
      fallbackTestAttempted: false,
      fallbackTestResult: resolved.effectiveFallbackEnabled ? 'NOT_TESTED' : 'FALLBACK_NOT_CONFIGURED'
    };

    const configValidation = buildDiagnosticsConfigValidation({ resolved, providerRegistry, runtime: { proxyConfigured: Boolean(configAi.proxyUrl && configAi.proxyToken) } });
    db.createAiEvent({
      taskType: 'runHealthCheck',
      provider: resolved.effectiveProvider,
      model: resolved.effectiveModel,
      success: configValidation.ok,
      fallbackUsed: false,
      errorCode: configValidation.ok ? '' : configValidation.reason,
      errorSummary: configValidation.detail || 'CONFIG_VALID',
      status: configValidation.ok ? 'success' : 'fail',
      metaJson: { stage: 'config_validation_result', configValidationResult: configValidation.ok ? 'valid' : 'invalid' }
    });

    let probe;
    if (!configValidation.ok) {
      diagnostics.configStatus = 'invalid';
      probe = {
        ok: false,
        error: 'CONFIG_INVALID',
        errorDetail: configValidation.reason,
        errorMessage: configValidation.detail,
        diagnosticsStatus: 'CONFIG_INVALID',
        ...diagnostics
      };
    } else {
      const primaryProviderName = resolved.effectiveProvider;
      const primaryModel = resolved.effectiveModel;
      const primaryProvider = providerRegistry.get(primaryProviderName);
      diagnostics.primaryTestAttempted = true;
      db.createAiEvent({
        taskType: 'runHealthCheck',
        provider: primaryProviderName,
        model: primaryModel,
        success: true,
        fallbackUsed: false,
        status: 'success',
        metaJson: { stage: 'primary_provider_attempt', primaryProviderAttempt: 'yes' }
      });

      try {
        const response = await primaryProvider.invoke({ model: primaryModel, prompt, timeoutMs });
        diagnostics.primaryStatus = 'ok';
        diagnostics.primaryTestResult = 'PRIMARY_PROVIDER_OK';
        probe = {
          ok: true,
          output: response.output,
          provider: response.provider || primaryProviderName,
          model: response.model || primaryModel,
          fallbackUsed: false,
          fallbackConfigured: diagnostics.fallbackConfigured,
          targetProvider: primaryProviderName,
          targetModel: primaryModel,
          diagnosticsStatus: 'DIAGNOSTICS_OK',
          ...diagnostics
        };
        db.createAiEvent({
          taskType: 'runHealthCheck',
          provider: primaryProviderName,
          model: primaryModel,
          success: true,
          fallbackUsed: false,
          status: 'success',
          metaJson: { stage: 'primary_provider_result', primaryProviderResult: 'ok' }
        });
      } catch (primaryError) {
        const normalizedPrimaryError = normalizeError(primaryError);
        diagnostics.primaryStatus = 'failed';
        diagnostics.primaryTestResult = mapProviderFailureCode(normalizedPrimaryError.code, 'PRIMARY');
        db.createAiEvent({
          taskType: 'runHealthCheck',
          provider: primaryProviderName,
          model: primaryModel,
          success: false,
          fallbackUsed: false,
          errorCode: normalizedPrimaryError.code,
          errorSummary: normalizedPrimaryError.message,
          status: 'fail',
          metaJson: { stage: 'primary_provider_result', primaryProviderResult: diagnostics.primaryTestResult }
        });

        if (!resolved.effectiveFallbackEnabled) {
          probe = {
            ok: false,
            error: 'PRIMARY_PROVIDER_FAILED',
            errorDetail: diagnostics.primaryTestResult,
            errorMessage: normalizedPrimaryError.message,
            provider: primaryProviderName,
            model: primaryModel,
            fallbackUsed: false,
            fallbackConfigured: false,
            targetProvider: primaryProviderName,
            targetModel: primaryModel,
            diagnosticsStatus: 'PRIMARY_PROVIDER_FAILED',
            ...diagnostics
          };
        } else {
          const fallbackProviderName = resolved.effectiveFallbackProvider;
          const fallbackModel = resolved.effectiveFallbackModel;
          const fallbackProvider = providerRegistry.get(fallbackProviderName);
          diagnostics.fallbackTestAttempted = true;
          db.createAiEvent({
            taskType: 'runHealthCheck',
            provider: fallbackProviderName,
            model: fallbackModel,
            success: true,
            fallbackUsed: true,
            status: 'success',
            metaJson: { stage: 'fallback_provider_attempt', fallbackProviderAttempt: 'yes' }
          });
          try {
            const fallbackResponse = await fallbackProvider.invoke({ model: fallbackModel, prompt, timeoutMs });
            diagnostics.fallbackStatus = 'ok';
            diagnostics.fallbackTestResult = 'DIAGNOSTICS_OK';
            probe = {
              ok: true,
              output: fallbackResponse.output,
              provider: fallbackResponse.provider || fallbackProviderName,
              model: fallbackResponse.model || fallbackModel,
              fallbackUsed: true,
              fallbackConfigured: true,
              targetProvider: primaryProviderName,
              targetModel: primaryModel,
              primaryError: diagnostics.primaryTestResult,
              diagnosticsStatus: 'DIAGNOSTICS_OK',
              ...diagnostics
            };
            db.createAiEvent({
              taskType: 'runHealthCheck',
              provider: fallbackProviderName,
              model: fallbackModel,
              success: true,
              fallbackUsed: true,
              status: 'success',
              metaJson: { stage: 'fallback_provider_result', fallbackProviderResult: 'ok' }
            });
          } catch (fallbackError) {
            const normalizedFallbackError = normalizeError(fallbackError);
            diagnostics.fallbackStatus = 'failed';
            diagnostics.fallbackTestResult = mapProviderFailureCode(normalizedFallbackError.code, 'FALLBACK');
            probe = {
              ok: false,
              error: 'FALLBACK_PROVIDER_FAILED',
              errorDetail: diagnostics.fallbackTestResult,
              errorMessage: normalizedFallbackError.message,
              provider: fallbackProviderName,
              model: fallbackModel,
              fallbackUsed: true,
              fallbackConfigured: true,
              targetProvider: primaryProviderName,
              targetModel: primaryModel,
              primaryError: diagnostics.primaryTestResult,
              diagnosticsStatus: 'FALLBACK_PROVIDER_FAILED',
              ...diagnostics
            };
            db.createAiEvent({
              taskType: 'runHealthCheck',
              provider: fallbackProviderName,
              model: fallbackModel,
              success: false,
              fallbackUsed: true,
              errorCode: normalizedFallbackError.code,
              errorSummary: normalizedFallbackError.message,
              status: 'fail',
              metaJson: { stage: 'fallback_provider_result', fallbackProviderResult: diagnostics.fallbackTestResult }
            });
          }
        }
      }
    }

    const finalStatus = probe.ok ? 'DIAGNOSTICS_OK' : (probe.diagnosticsStatus || probe.error || 'UNKNOWN');
    const summary = probe.ok
      ? 'AI diagnostics OK'
      : `AI diagnostics failed: ${finalStatus}`;
    db.createAiEvent({
      taskType: 'runHealthCheck',
      provider: probe.provider || resolved.effectiveProvider,
      model: probe.model || resolved.effectiveModel,
      success: probe.ok,
      fallbackUsed: Boolean(probe.fallbackUsed),
      errorCode: probe.error || '',
      errorSummary: probe.errorMessage || summary,
      status: probe.ok ? 'success' : 'fail',
      metaJson: { stage: 'final_diagnostics_status', finalDiagnosticsStatus: finalStatus }
    });
    const state = runtimeSettings.setDiagnosticsState({
      status: finalStatus,
      summary,
      at: new Date().toISOString(),
      durationMs: Date.now() - startedAt,
      provider: probe.provider || runtime.activeProvider,
      model: probe.model || runtime.activeModel,
      fallbackUsed: probe.fallbackUsed,
      errorCode: probe.error || '',
      errorDetail: probe.errorDetail || '',
      configStatus: probe.configStatus || 'invalid',
      primaryStatus: probe.primaryStatus || 'not tested',
      fallbackStatus: probe.fallbackStatus || 'not configured',
      configuredProvider: probe.configuredProvider || resolved.configuredProvider || '',
      configuredModel: probe.configuredModel || resolved.configuredModel || '',
      effectiveProvider: probe.effectiveProvider || resolved.effectiveProvider || '',
      effectiveModel: probe.effectiveModel || resolved.effectiveModel || '',
      runtimeOverridePresent: Boolean(probe.runtimeOverridePresent),
      runtimeOverrideValid: Boolean(probe.runtimeOverrideValid),
      primaryTestAttempted: Boolean(probe.primaryTestAttempted),
      primaryTestResult: probe.primaryTestResult || 'NOT_TESTED',
      fallbackTestAttempted: Boolean(probe.fallbackTestAttempted),
      fallbackTestResult: probe.fallbackTestResult || (probe.fallbackConfigured ? 'NOT_TESTED' : 'FALLBACK_NOT_CONFIGURED'),
      targetProvider: probe.targetProvider || runtime.activeProvider,
      targetModel: probe.targetModel || runtime.activeModel,
      fallbackConfigured: Boolean(probe.fallbackConfigured),
      finalDiagnosticsStatus: finalStatus
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
