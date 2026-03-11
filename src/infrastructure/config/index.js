function parseBoolean(value, fallback = false) {
  if (value === undefined || value === null || value === '') return fallback;
  return String(value).toLowerCase() === 'true';
}

function parseNumber(value, fallback, { min = Number.NEGATIVE_INFINITY, max = Number.POSITIVE_INFINITY } = {}) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
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

  return {
    nodeEnv: process.env.NODE_ENV || 'development',
    port,
    telegramClientBotToken: process.env.TELEGRAM_CLIENT_BOT_TOKEN || '',
    telegramMasterBotToken: process.env.TELEGRAM_MASTER_BOT_TOKEN || '',
    telegramIntegrationBotToken: process.env.TELEGRAM_INTEGRATION_BOT_TOKEN || '',
    dbUrl: process.env.DB_URL || 'postgres://localhost:5432/telegram_reviews',
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
    schedulerStuckTimeoutMs
  };
}

module.exports = { loadConfig };
