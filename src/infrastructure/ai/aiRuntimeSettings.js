const DEFAULT_RUNTIME_KEY = 'ai_runtime_settings';
const DEFAULT_DIAGNOSTICS_KEY = 'ai_diagnostics_state';
const {
  normalizeProvider,
  normalizeModel,
  isFallbackConfigured,
  validateProviderModelPair
} = require('./providerModelRules');

function nowIso() {
  return new Date().toISOString();
}

function normalizeProviders(value = []) {
  const list = Array.isArray(value) ? value : String(value || '').split(',');
  return list.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean);
}

function buildDefaults(configAi = {}) {
  const fallbackConfigured = isFallbackConfigured(configAi.fallbackProvider, configAi.fallbackModel);
  return {
    activeProvider: configAi.provider || 'proxy',
    activeModel: configAi.model || 'deepseek-chat',
    activeFallbackProvider: fallbackConfigured ? normalizeProvider(configAi.fallbackProvider) : '',
    activeFallbackModel: fallbackConfigured ? normalizeModel(configAi.fallbackModel) : '',
    fallbackConfigured,
    aiEnabledRuntime: configAi.enabled !== false,
    aiBusinessUsageEnabledRuntime: Boolean(configAi.businessUsageEnabled),
    lastAiDiagnosticsAt: null,
    lastAiDiagnosticsStatus: 'never',
    lastAiDiagnosticsSummary: ''
  };
}

function createAiRuntimeSettings({ db, configAi }) {
  function getAllowedProviders() {
    return normalizeProviders(configAi.allowedProviders || ['proxy', 'openai', 'deepseek']);
  }

  function get() {
    const defaults = buildDefaults(configAi);
    const stored = db.getMetaValue(DEFAULT_RUNTIME_KEY, {});
    const merged = { ...defaults, ...(stored || {}) };
    const allowed = getAllowedProviders();

    if (!allowed.includes(merged.activeProvider)) merged.activeProvider = defaults.activeProvider;

    merged.fallbackConfigured = isFallbackConfigured(merged.activeFallbackProvider, merged.activeFallbackModel);
    if (merged.fallbackConfigured && !allowed.includes(merged.activeFallbackProvider)) {
      merged.activeFallbackProvider = defaults.activeFallbackProvider;
      merged.activeFallbackModel = defaults.activeFallbackModel;
      merged.fallbackConfigured = isFallbackConfigured(merged.activeFallbackProvider, merged.activeFallbackModel);
    }

    return {
      ...merged,
      allowedProviders: allowed
    };
  }

  function validate(next) {
    const allowed = getAllowedProviders();
    const primaryProvider = normalizeProvider(next.activeProvider);
    const primaryModel = normalizeModel(next.activeModel);
    if (!allowed.includes(primaryProvider)) return { ok: false, error: 'ACTIVE_PROVIDER_NOT_ALLOWED' };
    const primaryPair = validateProviderModelPair(primaryProvider, primaryModel, { context: 'PRIMARY' });
    if (!primaryPair.ok) return primaryPair;

    const fallbackConfigured = isFallbackConfigured(next.activeFallbackProvider, next.activeFallbackModel);
    if (!fallbackConfigured && (normalizeProvider(next.activeFallbackProvider) || normalizeModel(next.activeFallbackModel))) {
      return { ok: false, error: 'FALLBACK_PROVIDER_MODEL_INCOMPLETE' };
    }
    if (fallbackConfigured) {
      const fallbackProvider = normalizeProvider(next.activeFallbackProvider);
      const fallbackModel = normalizeModel(next.activeFallbackModel);
      if (!allowed.includes(fallbackProvider)) return { ok: false, error: 'FALLBACK_PROVIDER_NOT_ALLOWED' };
      const fallbackPair = validateProviderModelPair(fallbackProvider, fallbackModel, { context: 'FALLBACK' });
      if (!fallbackPair.ok) return fallbackPair;
    }
    return { ok: true };
  }

  function update(patch = {}) {
    const current = get();
    const next = {
      ...current,
      ...(patch || {}),
      activeProvider: normalizeProvider((patch || {}).activeProvider !== undefined ? patch.activeProvider : current.activeProvider),
      activeModel: normalizeModel((patch || {}).activeModel !== undefined ? patch.activeModel : current.activeModel),
      activeFallbackProvider: normalizeProvider((patch || {}).activeFallbackProvider !== undefined ? patch.activeFallbackProvider : current.activeFallbackProvider),
      activeFallbackModel: normalizeModel((patch || {}).activeFallbackModel !== undefined ? patch.activeFallbackModel : current.activeFallbackModel)
    };
    const check = validate(next);
    if (!check.ok) return { ok: false, error: check.error, current };

    db.setMetaValue(DEFAULT_RUNTIME_KEY, {
      activeProvider: next.activeProvider,
      activeModel: next.activeModel,
      activeFallbackProvider: next.activeFallbackProvider,
      activeFallbackModel: next.activeFallbackModel,
      fallbackConfigured: isFallbackConfigured(next.activeFallbackProvider, next.activeFallbackModel),
      aiEnabledRuntime: Boolean(next.aiEnabledRuntime),
      aiBusinessUsageEnabledRuntime: Boolean(next.aiBusinessUsageEnabledRuntime),
      lastAiDiagnosticsAt: next.lastAiDiagnosticsAt || null,
      lastAiDiagnosticsStatus: next.lastAiDiagnosticsStatus || 'never',
      lastAiDiagnosticsSummary: next.lastAiDiagnosticsSummary || ''
    });

    return { ok: true, runtime: get() };
  }

  function setDiagnosticsState(state = {}) {
    const payload = {
      status: state.status || 'unknown',
      summary: String(state.summary || '').slice(0, 1000),
      at: state.at || nowIso(),
      durationMs: Number(state.durationMs) || 0,
      provider: state.provider || '',
      model: state.model || '',
      targetProvider: state.targetProvider || '',
      targetModel: state.targetModel || '',
      fallbackUsed: Boolean(state.fallbackUsed),
      fallbackConfigured: Boolean(state.fallbackConfigured),
      errorCode: state.errorCode || '',
      errorDetail: state.errorDetail || '',
      configStatus: state.configStatus || 'invalid',
      primaryStatus: state.primaryStatus || 'not tested',
      fallbackStatus: state.fallbackStatus || 'not configured',
      configuredProvider: state.configuredProvider || '',
      configuredModel: state.configuredModel || '',
      effectiveProvider: state.effectiveProvider || '',
      effectiveModel: state.effectiveModel || '',
      runtimeOverridePresent: Boolean(state.runtimeOverridePresent),
      runtimeOverrideValid: Boolean(state.runtimeOverrideValid),
      primaryTestAttempted: Boolean(state.primaryTestAttempted),
      primaryTestResult: state.primaryTestResult || 'NOT_TESTED',
      fallbackTestAttempted: Boolean(state.fallbackTestAttempted),
      fallbackTestResult: state.fallbackTestResult || 'FALLBACK_NOT_CONFIGURED',
      finalDiagnosticsStatus: state.finalDiagnosticsStatus || state.status || 'unknown'
    };
    db.setMetaValue(DEFAULT_DIAGNOSTICS_KEY, payload);
    update({
      lastAiDiagnosticsAt: payload.at,
      lastAiDiagnosticsStatus: payload.status,
      lastAiDiagnosticsSummary: payload.summary
    });
    return payload;
  }

  function getDiagnosticsState() {
    return db.getMetaValue(DEFAULT_DIAGNOSTICS_KEY, null);
  }

  return { get, update, validate, setDiagnosticsState, getDiagnosticsState };
}

module.exports = { createAiRuntimeSettings, buildDefaults };
