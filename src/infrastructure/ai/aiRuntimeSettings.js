const DEFAULT_RUNTIME_KEY = 'ai_runtime_settings';
const DEFAULT_DIAGNOSTICS_KEY = 'ai_diagnostics_state';

function nowIso() {
  return new Date().toISOString();
}

function normalizeProviders(value = []) {
  const list = Array.isArray(value) ? value : String(value || '').split(',');
  return list.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean);
}

function buildDefaults(configAi = {}) {
  return {
    activeProvider: configAi.provider || 'proxy',
    activeModel: configAi.model || 'deepseek-chat',
    activeFallbackProvider: configAi.fallbackProvider || 'openai',
    activeFallbackModel: configAi.fallbackModel || 'gpt-4o-mini',
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
    if (!allowed.includes(merged.activeFallbackProvider)) merged.activeFallbackProvider = defaults.activeFallbackProvider;

    return {
      ...merged,
      allowedProviders: allowed
    };
  }

  function validate(next) {
    const allowed = getAllowedProviders();
    if (!allowed.includes(next.activeProvider)) return { ok: false, error: 'ACTIVE_PROVIDER_NOT_ALLOWED' };
    if (!allowed.includes(next.activeFallbackProvider)) return { ok: false, error: 'FALLBACK_PROVIDER_NOT_ALLOWED' };
    if (!next.activeModel) return { ok: false, error: 'ACTIVE_MODEL_REQUIRED' };
    if (!next.activeFallbackModel) return { ok: false, error: 'FALLBACK_MODEL_REQUIRED' };
    return { ok: true };
  }

  function update(patch = {}) {
    const current = get();
    const next = { ...current, ...(patch || {}) };
    const check = validate(next);
    if (!check.ok) return { ok: false, error: check.error, current };

    db.setMetaValue(DEFAULT_RUNTIME_KEY, {
      activeProvider: next.activeProvider,
      activeModel: next.activeModel,
      activeFallbackProvider: next.activeFallbackProvider,
      activeFallbackModel: next.activeFallbackModel,
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
      fallbackUsed: Boolean(state.fallbackUsed),
      errorCode: state.errorCode || ''
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
