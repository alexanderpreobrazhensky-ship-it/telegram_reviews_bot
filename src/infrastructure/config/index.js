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

function loadConfig() {
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
    envAudit: {
      requiredMissing: [
        !process.env.WEBAPP_URL ? 'WEBAPP_URL' : null,
        !process.env.DB_SQLITE_PATH && !process.env.DB_FILE_PATH ? 'DB_SQLITE_PATH/DB_FILE_PATH' : null
      ].filter(Boolean),
      deprecatedConfigured: [
        process.env.DB_FILE_PATH ? 'DB_FILE_PATH' : null,
        process.env.INTERNAL_ADMIN_WHITELIST_IDS ? 'INTERNAL_ADMIN_WHITELIST_IDS' : null,
        process.env.WEBAPP_TELEGRAM_CHANNEL_LINK ? 'WEBAPP_TELEGRAM_CHANNEL_LINK' : null
      ].filter(Boolean)
    }
  };

  if (!config.dbSqlitePath) {
    throw new Error('DB_SQLITE_PATH (or legacy DB_FILE_PATH) is required');
  }

  return config;
}

module.exports = { loadConfig };
