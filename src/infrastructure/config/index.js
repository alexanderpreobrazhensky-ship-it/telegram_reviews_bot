function parseBoolean(value, fallback = false) {
  if (value === undefined || value === null || value === '') return fallback;
  return String(value).toLowerCase() === 'true';
}

function parseNumber(value, fallback, { min = Number.NEGATIVE_INFINITY, max = Number.POSITIVE_INFINITY } = {}) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}

function parseList(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function hasExplicitEnv(key) {
  return process.env[key] !== undefined && process.env[key] !== null && String(process.env[key]).trim() !== '';
}

function envHasValue(key) {
  return process.env[key] !== undefined && process.env[key] !== '';
}

const LEGACY_AI_ENV_KEYS = [
  'AI_ENGINE',
  'AI_TIMEOUT_SECONDS',
  'CLIENT_AI_TIMEOUT_SECONDS',
  'DEEPSEEK_API_KEY',
  'DEEPSEEK_BASE_URL',
  'DEEPSEEK_MODEL',
  'CLIENT_DEEPSEEK_API_KEY',
  'CLIENT_DEEPSEEK_BASE_URL',
  'CLIENT_DEEPSEEK_MODEL',
  'CLIENT_FORCE_FALLBACK',
  'FORCT_FALLBACK',
  'OPENAI_API_KEY',
  'GEMINI_API_KEY',
  'DEEPSEEK_ALLOW_REQUESTS_FALLBACK',
  'AI_API_KEY'
];

function resolveEnv({ canonical = null, sharedLegacy = [], clientLegacy = [], transform = (value) => value, defaultValue = '' }) {
  if (canonical && process.env[canonical] !== undefined && process.env[canonical] !== '') {
    return { value: transform(process.env[canonical]), source: canonical, tier: 'canonical' };
  }

  for (const key of sharedLegacy) {
    if (process.env[key] !== undefined && process.env[key] !== '') {
      return { value: transform(process.env[key]), source: key, tier: 'legacy_shared' };
    }
  }

  for (const key of clientLegacy) {
    if (process.env[key] !== undefined && process.env[key] !== '') {
      return { value: transform(process.env[key]), source: key, tier: 'legacy_client' };
    }
  }

  return { value: defaultValue, source: 'default', tier: 'default' };
}

function resolveAiEnv() {
  const timeoutFromSeconds = (value) => {
    const seconds = parseNumber(value, 8, { min: 1, max: 120 });
    return seconds * 1000;
  };
  const legacyDetectedSet = new Set(LEGACY_AI_ENV_KEYS.filter((key) => envHasValue(key)));
  const legacyUsedSet = new Set();
  const legacyIgnoredSet = new Set();
  const registerResolution = (meta, aliases = []) => {
    const configuredAliases = aliases.filter((key) => envHasValue(key));
    if (!configuredAliases.length) return;

    if (String(meta?.tier || '').startsWith('legacy') && meta?.source) {
      legacyUsedSet.add(meta.source);
      configuredAliases
        .filter((key) => key !== meta.source)
        .forEach((key) => legacyIgnoredSet.add(key));
      return;
    }

    configuredAliases.forEach((key) => legacyIgnoredSet.add(key));
  };

  const enabled = resolveEnv({ canonical: 'AI_ENABLED', defaultValue: true, transform: (value) => parseBoolean(value, true) });
  const businessUsageEnabled = resolveEnv({ canonical: 'AI_BUSINESS_USAGE_ENABLED', defaultValue: false, transform: (value) => parseBoolean(value, false) });
  const provider = resolveEnv({
    canonical: 'AI_PROVIDER',
    sharedLegacy: ['AI_ENGINE'],
    defaultValue: 'proxy',
    transform: (value) => String(value || '').trim().toLowerCase() || 'proxy'
  });
  const model = resolveEnv({
    canonical: 'AI_MODEL',
    sharedLegacy: ['DEEPSEEK_MODEL'],
    clientLegacy: ['CLIENT_DEEPSEEK_MODEL'],
    defaultValue: 'deepseek-chat'
  });
  const proxyUrl = resolveEnv({
    canonical: 'AI_PROXY_URL',
    sharedLegacy: ['DEEPSEEK_BASE_URL'],
    clientLegacy: ['CLIENT_DEEPSEEK_BASE_URL'],
    defaultValue: ''
  });
  const proxyToken = resolveEnv({
    canonical: 'AI_PROXY_TOKEN',
    sharedLegacy: ['DEEPSEEK_API_KEY'],
    clientLegacy: ['CLIENT_DEEPSEEK_API_KEY'],
    defaultValue: ''
  });
  const timeoutMs = resolveEnv({
    canonical: 'AI_TIMEOUT_MS',
    sharedLegacy: ['AI_TIMEOUT_SECONDS'],
    clientLegacy: ['CLIENT_AI_TIMEOUT_SECONDS'],
    defaultValue: 8000,
    transform: (value) => {
      if (process.env.AI_TIMEOUT_MS !== undefined && process.env.AI_TIMEOUT_MS !== '') {
        return parseNumber(value, 8000, { min: 1000, max: 60000 });
      }
      return parseNumber(timeoutFromSeconds(value), 8000, { min: 1000, max: 60000 });
    }
  });
  const allowedProviders = resolveEnv({
    canonical: 'AI_ALLOWED_PROVIDERS',
    defaultValue: ['proxy', 'deepseek'],
    transform: (value) => parseList(value).map((item) => item.toLowerCase())
  });
  const diagnosticsEnabled = resolveEnv({ canonical: 'AI_DIAGNOSTICS_ENABLED', defaultValue: true, transform: (value) => parseBoolean(value, true) });

  const fallbackFlags = ['DEEPSEEK_ALLOW_REQUESTS_FALLBACK', 'CLIENT_FORCE_FALLBACK', 'FORCT_FALLBACK'];
  const enabledFallbackFlags = fallbackFlags.filter((key) => parseBoolean(process.env[key], false));

  const fallbackProvider = resolveEnv({ canonical: 'AI_FALLBACK_PROVIDER', defaultValue: '', transform: (value) => String(value || '').trim().toLowerCase() });
  const fallbackModel = resolveEnv({ canonical: 'AI_FALLBACK_MODEL', defaultValue: '' });
  const fallbackConfigured = hasExplicitEnv('AI_FALLBACK_PROVIDER') && hasExplicitEnv('AI_FALLBACK_MODEL');

  const openaiApiKey = resolveEnv({ canonical: 'AI_OPENAI_API_KEY', sharedLegacy: ['OPENAI_API_KEY', 'AI_API_KEY'], defaultValue: '' });
  const deepseekApiKey = resolveEnv({ canonical: 'AI_DEEPSEEK_API_KEY', sharedLegacy: ['DEEPSEEK_API_KEY'], clientLegacy: ['CLIENT_DEEPSEEK_API_KEY'], defaultValue: '' });
  const deepseekBaseUrl = resolveEnv({ canonical: 'AI_DEEPSEEK_BASE_URL', sharedLegacy: ['DEEPSEEK_BASE_URL'], clientLegacy: ['CLIENT_DEEPSEEK_BASE_URL'], defaultValue: 'https://api.deepseek.com/chat/completions' });
  const geminiApiKey = resolveEnv({ canonical: 'AI_GEMINI_API_KEY', sharedLegacy: ['GEMINI_API_KEY'], defaultValue: '' });

  registerResolution(provider, ['AI_ENGINE']);
  registerResolution(model, ['DEEPSEEK_MODEL', 'CLIENT_DEEPSEEK_MODEL']);
  registerResolution(proxyUrl, ['DEEPSEEK_BASE_URL', 'CLIENT_DEEPSEEK_BASE_URL']);
  registerResolution(proxyToken, ['DEEPSEEK_API_KEY', 'CLIENT_DEEPSEEK_API_KEY']);
  registerResolution(timeoutMs, ['AI_TIMEOUT_SECONDS', 'CLIENT_AI_TIMEOUT_SECONDS']);
  registerResolution(openaiApiKey, ['OPENAI_API_KEY', 'AI_API_KEY']);
  registerResolution(deepseekApiKey, ['DEEPSEEK_API_KEY', 'CLIENT_DEEPSEEK_API_KEY']);
  registerResolution(deepseekBaseUrl, ['DEEPSEEK_BASE_URL', 'CLIENT_DEEPSEEK_BASE_URL']);
  registerResolution(geminiApiKey, ['GEMINI_API_KEY']);
  ['CLIENT_FORCE_FALLBACK', 'FORCT_FALLBACK', 'DEEPSEEK_ALLOW_REQUESTS_FALLBACK'].forEach((key) => {
    if (envHasValue(key)) legacyIgnoredSet.add(key);
  });

  const sources = {
    AI_ENABLED: enabled,
    AI_BUSINESS_USAGE_ENABLED: businessUsageEnabled,
    AI_PROVIDER: provider,
    AI_MODEL: model,
    AI_PROXY_URL: proxyUrl,
    AI_PROXY_TOKEN: proxyToken,
    AI_TIMEOUT_MS: timeoutMs,
    AI_ALLOWED_PROVIDERS: allowedProviders,
    AI_DIAGNOSTICS_ENABLED: diagnosticsEnabled,
    AI_FALLBACK_PROVIDER: fallbackProvider,
    AI_FALLBACK_MODEL: fallbackModel,
    AI_OPENAI_API_KEY: openaiApiKey,
    AI_DEEPSEEK_API_KEY: deepseekApiKey,
    AI_DEEPSEEK_BASE_URL: deepseekBaseUrl,
    AI_GEMINI_API_KEY: geminiApiKey
  };

  const legacyUsed = Array.from(legacyUsedSet).sort();
  const legacyIgnored = Array.from(legacyIgnoredSet).sort();
  const legacyDetected = Array.from(new Set([...legacyDetectedSet, ...legacyUsed, ...legacyIgnored])).sort();

  return {
    enabled: enabled.value,
    businessUsageEnabled: businessUsageEnabled.value,
    provider: provider.value,
    model: model.value,
    fallbackProvider: fallbackProvider.value,
    fallbackModel: fallbackModel.value,
    fallbackConfigured,
    proxyUrl: proxyUrl.value,
    proxyToken: proxyToken.value,
    openaiApiKey: openaiApiKey.value,
    deepseekApiKey: deepseekApiKey.value,
    deepseekUrl: deepseekBaseUrl.value,
    geminiApiKey: geminiApiKey.value,
    allowedProviders: Array.isArray(allowedProviders.value) && allowedProviders.value.length ? allowedProviders.value : ['proxy', 'deepseek'],
    diagnosticsEnabled: diagnosticsEnabled.value,
    timeoutMs: timeoutMs.value,
    legacyForceFallbackRequested: false,
    legacyForceFallbackFlags: enabledFallbackFlags,
    sources,
    legacyUsed,
    legacyIgnored,
    legacyDetected
  };
}

function loadConfig() {
  const strictConfig = parseBoolean(process.env.CONFIG_STRICT, String(process.env.NODE_ENV || '').toLowerCase() === 'production');
  const port = parseNumber(process.env.PORT, 3000, { min: 1, max: 65535 });
  const integrationRetryMax = parseNumber(process.env.INTEGRATION_RETRY_MAX, 3, { min: 1, max: 20 });
  const integrationRetryDelaySeconds = parseNumber(process.env.INTEGRATION_RETRY_DELAY_SECONDS, 60, { min: 1, max: 3600 });
  const feedbackRequestDelayMinutes = parseNumber(process.env.FEEDBACK_REQUEST_DELAY_MINUTES, 5, { min: 0, max: 1440 });
  const schedulerIntervalMs = parseNumber(process.env.SCHEDULER_INTERVAL_MS, 15000, { min: 1000, max: 3600000 });
  const schedulerBatchSize = parseNumber(process.env.SCHEDULER_BATCH_SIZE, 10, { min: 1, max: 100 });
  const schedulerMaxAttempts = parseNumber(process.env.SCHEDULER_MAX_ATTEMPTS, 3, { min: 1, max: 10 });
  const schedulerStuckTimeoutMs = parseNumber(process.env.SCHEDULER_STUCK_TIMEOUT_MS, 300000, { min: 1000, max: 86400000 });
  const webappDedupeWindowMs = parseNumber(process.env.WEBAPP_DEDUPE_WINDOW_MS, 45000, { min: 5000, max: 600000 });
  const webappRateLimitWindowMs = parseNumber(process.env.WEBAPP_RATE_LIMIT_WINDOW_MS, 15000, { min: 1000, max: 300000 });
  const webappRateLimitMax = parseNumber(process.env.WEBAPP_RATE_LIMIT_MAX, 5, { min: 1, max: 100 });
  const webhookRateLimitWindowMs = parseNumber(process.env.WEBHOOK_RATE_LIMIT_WINDOW_MS, 10000, { min: 1000, max: 300000 });
  const webhookRateLimitMax = parseNumber(process.env.WEBHOOK_RATE_LIMIT_MAX, 30, { min: 1, max: 500 });

  const masterBotAdminIds = parseList(process.env.MASTER_BOT_ADMIN_IDS);
  const maxMasterBotAdminIds = parseList(process.env.MAX_MASTER_BOT_ADMIN_IDS);
  const internalAdminWhitelist = parseList(process.env.INTERNAL_ADMIN_WHITELIST || process.env.INTERNAL_ADMIN_WHITELIST_IDS);
  const resolvedAiConfig = resolveAiEnv();

  const requiredEnv = ['WEBAPP_URL', 'DB_SQLITE_PATH'];
  const optionalEnv = [
    'TELEGRAM_CLIENT_BOT_TOKEN',
    'TELEGRAM_MASTER_BOT_TOKEN',
    'TELEGRAM_INTEGRATION_BOT_TOKEN',
    'MASTER_BOT_ADMIN_IDS',
    'INTERNAL_ADMIN_WHITELIST',
    'MAX_ENABLED',
    'MAX_CLIENT_BOT_TOKEN',
    'MAX_MASTER_BOT_TOKEN',
    'MAX_WEBHOOK_SECRET',
    'MAX_MASTER_BOT_ADMIN_IDS',
    'MAX_WEBAPP_URL',
    'MAX_BOT_NAME',
    'MAX_WEBHOOK_BASE_URL',
    'MAX_DEEPLINK_BASE_URL',
    'TELEGRAM_MASTERS_CHAT_ID',
    'TELEGRAM_DEBUG_CHAT_ID',
    'TELEGRAM_CHANNEL_URL',
    'WEBAPP_DEDUPE_WINDOW_MS',
    'WEBAPP_RATE_LIMIT_WINDOW_MS',
    'WEBAPP_RATE_LIMIT_MAX',
    'WEBHOOK_RATE_LIMIT_WINDOW_MS',
    'WEBHOOK_RATE_LIMIT_MAX',
    'SCHEDULER_INTERVAL_MS',
    'SCHEDULER_BATCH_SIZE',
    'SCHEDULER_MAX_ATTEMPTS',
    'SCHEDULER_STUCK_TIMEOUT_MS',
    'FEEDBACK_REQUEST_DELAY_MINUTES',
    'AI_ENABLED',
    'AI_BUSINESS_USAGE_ENABLED',
    'AI_PROVIDER',
    'AI_MODEL',
    'AI_FALLBACK_PROVIDER',
    'AI_FALLBACK_MODEL',
    'AI_PROXY_URL',
    'AI_PROXY_TOKEN',
    'AI_OPENAI_API_KEY',
    'AI_DEEPSEEK_API_KEY',
    'AI_DEEPSEEK_BASE_URL',
    'AI_GEMINI_API_KEY',
    'AI_ALLOWED_PROVIDERS',
    'AI_DIAGNOSTICS_ENABLED',
    'AI_TIMEOUT_MS',
    'EMAIL_INTAKE_ENABLED',
    'EMAIL_INTAKE_PROVIDER',
    'EMAIL_IMAP_HOST',
    'EMAIL_IMAP_PORT',
    'EMAIL_IMAP_SECURE',
    'EMAIL_IMAP_USER',
    'EMAIL_IMAP_PASSWORD',
    'EMAIL_IMAP_FOLDER',
    'EMAIL_POLL_INTERVAL_SECONDS',
    'EMAIL_SOURCE_TBUSINESS_ENABLED',
    'EMAIL_SOURCE_TBUSINESS_PRIORITY',
    'EMAIL_ALLOW_ATTACHMENTS',
    'EMAIL_PDF_PARSE_ENABLED',
    'EMAIL_IDEMPOTENCY_ENABLED',
    'EMAIL_MATCH_PHONE_ENABLED',
    'EMAIL_MATCH_FIO_ENABLED',
    'EMAIL_MATCH_VIN_ENABLED',
    'EMAIL_MATCH_EMAIL_ENABLED',
    'EMAIL_NEEDS_REVIEW_ON_UNCERTAIN_MATCH',
    'EMAIL_AUTO_CREATE_CLIENT_IF_NO_MATCH',
    'EMAIL_SAVE_RAW_MESSAGE',
    'EMAIL_SAVE_ATTACHMENTS_METADATA',
    'EMAIL_SAVE_PARSED_TEXT',
    'EMAIL_AI_ENRICHMENT_ENABLED',
    'EMAIL_AI_SUMMARY_ENABLED',
    'EMAIL_AI_CLASSIFICATION_ENABLED',
    'EMAIL_AI_BUSINESS_USAGE_SCOPE'
  ];
  const legacyEnv = [
    'DB_FILE_PATH',
    'INTERNAL_ADMIN_WHITELIST_IDS',
    'WEBAPP_TELEGRAM_CHANNEL_LINK',
    'AI_API_KEY',
    'AI_ENGINE',
    'AI_TIMEOUT_SECONDS',
    'CLIENT_AI_TIMEOUT_SECONDS',
    'DEEPSEEK_API_KEY',
    'DEEPSEEK_BASE_URL',
    'DEEPSEEK_MODEL',
    'DEEPSEEK_ALLOW_REQUESTS_FALLBACK',
    'CLIENT_DEEPSEEK_API_KEY',
    'CLIENT_DEEPSEEK_BASE_URL',
    'CLIENT_DEEPSEEK_MODEL',
    'CLIENT_FORCE_FALLBACK',
    'FORCT_FALLBACK',
    'OPENAI_API_KEY',
    'GEMINI_API_KEY'
  ];
  const knownEnv = new Set([...requiredEnv, ...optionalEnv, ...legacyEnv, 'PORT', 'NODE_ENV', 'DB_DRIVER', 'DB_URL', 'QUEUE_DRIVER', 'ONE_C_WEBHOOK_SECRET', 'ENABLE_INTEGRATION_WORKER', 'INTEGRATION_RETRY_MAX', 'INTEGRATION_RETRY_DELAY_SECONDS', 'ONE_C_SYNC_ENABLED', 'EMAIL_IMPORT_ENABLED', 'MAX_DIAGNOSTICS_ENABLED']);

  const config = {
    nodeEnv: process.env.NODE_ENV || 'development',
    port,
    telegramClientBotToken: process.env.TELEGRAM_CLIENT_BOT_TOKEN || '',
    telegramMasterBotToken: process.env.TELEGRAM_MASTER_BOT_TOKEN || '',
    telegramIntegrationBotToken: process.env.TELEGRAM_INTEGRATION_BOT_TOKEN || '',
    masterBotAdminIds,
    maxEnabled: parseBoolean(process.env.MAX_ENABLED, false),
    maxClientBotToken: process.env.MAX_CLIENT_BOT_TOKEN || '',
    maxMasterBotToken: process.env.MAX_MASTER_BOT_TOKEN || '',
    maxWebhookSecret: process.env.MAX_WEBHOOK_SECRET || '',
    maxWebAppUrl: process.env.MAX_WEBAPP_URL || process.env.WEBAPP_URL || 'https://example.com',
    maxBotName: process.env.MAX_BOT_NAME || '',
    maxWebhookBaseUrl: process.env.MAX_WEBHOOK_BASE_URL || '',
    maxDeepLinkBaseUrl: process.env.MAX_DEEPLINK_BASE_URL || '',
    maxMasterBotAdminIds,
    dbDriver: process.env.DB_DRIVER || 'sqlite',
    dbUrl: process.env.DB_URL || '',
    dbSqlitePath: process.env.DB_SQLITE_PATH || process.env.DB_FILE_PATH || 'data/db.sqlite',
    queueDriver: process.env.QUEUE_DRIVER || 'memory',
    oneCWebhookSecret: process.env.ONE_C_WEBHOOK_SECRET || '',
    enableIntegrationWorker: parseBoolean(process.env.ENABLE_INTEGRATION_WORKER, true),
    integrationRetryMax,
    integrationRetryDelaySeconds,
    oneCSyncEnabled: parseBoolean(process.env.ONE_C_SYNC_ENABLED, false),
    emailImportEnabled: parseBoolean(process.env.EMAIL_IMPORT_ENABLED, true),
    emailIntake: {
      enabled: parseBoolean(process.env.EMAIL_INTAKE_ENABLED, false),
      provider: process.env.EMAIL_INTAKE_PROVIDER || 'imap',
      pollIntervalSeconds: parseNumber(process.env.EMAIL_POLL_INTERVAL_SECONDS, 60, { min: 5, max: 3600 }),
      sourceTBusinessEnabled: parseBoolean(process.env.EMAIL_SOURCE_TBUSINESS_ENABLED, true),
      sourceTBusinessPriority: process.env.EMAIL_SOURCE_TBUSINESS_PRIORITY || 'high',
      allowAttachments: parseBoolean(process.env.EMAIL_ALLOW_ATTACHMENTS, true),
      pdfParseEnabled: parseBoolean(process.env.EMAIL_PDF_PARSE_ENABLED, true),
      idempotencyEnabled: parseBoolean(process.env.EMAIL_IDEMPOTENCY_ENABLED, true),
      matchPhoneEnabled: parseBoolean(process.env.EMAIL_MATCH_PHONE_ENABLED, true),
      matchFioEnabled: parseBoolean(process.env.EMAIL_MATCH_FIO_ENABLED, true),
      matchVinEnabled: parseBoolean(process.env.EMAIL_MATCH_VIN_ENABLED, true),
      matchEmailEnabled: parseBoolean(process.env.EMAIL_MATCH_EMAIL_ENABLED, false),
      needsReviewOnUncertainMatch: parseBoolean(process.env.EMAIL_NEEDS_REVIEW_ON_UNCERTAIN_MATCH, true),
      autoCreateClientIfNoMatch: parseBoolean(process.env.EMAIL_AUTO_CREATE_CLIENT_IF_NO_MATCH, true),
      saveRawMessage: parseBoolean(process.env.EMAIL_SAVE_RAW_MESSAGE, true),
      saveAttachmentsMetadata: parseBoolean(process.env.EMAIL_SAVE_ATTACHMENTS_METADATA, true),
      saveParsedText: parseBoolean(process.env.EMAIL_SAVE_PARSED_TEXT, true),
      aiEnrichmentEnabled: parseBoolean(process.env.EMAIL_AI_ENRICHMENT_ENABLED, false),
      aiSummaryEnabled: parseBoolean(process.env.EMAIL_AI_SUMMARY_ENABLED, true),
      aiClassificationEnabled: parseBoolean(process.env.EMAIL_AI_CLASSIFICATION_ENABLED, true),
      aiBusinessUsageScope: process.env.EMAIL_AI_BUSINESS_USAGE_SCOPE || '',
      imap: {
        host: process.env.EMAIL_IMAP_HOST || '',
        port: parseNumber(process.env.EMAIL_IMAP_PORT, 993, { min: 1, max: 65535 }),
        secure: parseBoolean(process.env.EMAIL_IMAP_SECURE, true),
        user: process.env.EMAIL_IMAP_USER || '',
        password: process.env.EMAIL_IMAP_PASSWORD || '',
        folder: process.env.EMAIL_IMAP_FOLDER || 'INBOX'
      }
    },
    webAppUrl: process.env.WEBAPP_URL || 'https://example.com',
    feedbackRequestDelayMinutes,
    schedulerIntervalMs,
    schedulerBatchSize,
    schedulerMaxAttempts,
    schedulerStuckTimeoutMs,
    webappDedupeWindowMs,
    webappRateLimitWindowMs,
    webappRateLimitMax,
    webhookRateLimitWindowMs,
    webhookRateLimitMax,
    telegramMastersChatId: process.env.TELEGRAM_MASTERS_CHAT_ID || '',
    telegramDebugChatId: process.env.TELEGRAM_DEBUG_CHAT_ID || '',
    webappTelegramChannelLink: process.env.TELEGRAM_CHANNEL_URL || process.env.WEBAPP_TELEGRAM_CHANNEL_LINK || '',
    internalAdminWhitelist,
    maxDiagnosticsEnabled: parseBoolean(process.env.MAX_DIAGNOSTICS_ENABLED, true),
    ai: resolvedAiConfig,
    envAudit: {
      required: requiredEnv,
      optional: optionalEnv,
      legacyAccepted: legacyEnv,
      requiredMissing: [
        !process.env.WEBAPP_URL ? 'WEBAPP_URL' : null,
        !process.env.DB_SQLITE_PATH && !process.env.DB_FILE_PATH ? 'DB_SQLITE_PATH/DB_FILE_PATH' : null
      ].filter(Boolean),
      deprecatedConfigured: [
        process.env.DB_FILE_PATH ? 'DB_FILE_PATH' : null,
        process.env.INTERNAL_ADMIN_WHITELIST_IDS ? 'INTERNAL_ADMIN_WHITELIST_IDS' : null,
        process.env.WEBAPP_TELEGRAM_CHANNEL_LINK ? 'WEBAPP_TELEGRAM_CHANNEL_LINK' : null,
        process.env.AI_API_KEY ? 'AI_API_KEY' : null,
        process.env.FORCT_FALLBACK ? 'FORCT_FALLBACK (legacy typo)' : null
      ].filter(Boolean),
      aiResolution: {
        provider: resolvedAiConfig.provider,
        model: resolvedAiConfig.model,
        sourceProvider: resolvedAiConfig.sources?.AI_PROVIDER?.source || 'default',
        sourceModel: resolvedAiConfig.sources?.AI_MODEL?.source || 'default',
        sourceTimeoutMs: resolvedAiConfig.sources?.AI_TIMEOUT_MS?.source || 'default'
      },
      legacyAiDetected: resolvedAiConfig.legacyDetected || [],
      legacyAiIgnored: resolvedAiConfig.legacyIgnored || [],
      legacyAiConfigured: resolvedAiConfig.legacyUsed,
      unknownConfigured: Object.keys(process.env).filter((key) => /^(TELEGRAM|MAX|WEBAPP|DB_|QUEUE_|ONE_C_|INTEGRATION_|MASTER_BOT_|INTERNAL_ADMIN_|SCHEDULER_|FEEDBACK_|PORT|NODE_ENV|AI_|DEEPSEEK_|CLIENT_|OPENAI_|GEMINI_|FORCT_|EMAIL_)/.test(key) && !knownEnv.has(key)).sort()
    }
  };

  if (strictConfig && config.envAudit.requiredMissing.length) {
    throw new Error(`Missing required env: ${config.envAudit.requiredMissing.join(', ')}`);
  }

  return config;
}

module.exports = { loadConfig };
