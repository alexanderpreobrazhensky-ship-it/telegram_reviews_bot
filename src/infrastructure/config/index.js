function loadConfig() {
  return {
    nodeEnv: process.env.NODE_ENV || 'development',
    port: Number(process.env.PORT || 3000),
    telegramClientBotToken: process.env.TELEGRAM_CLIENT_BOT_TOKEN || '',
    telegramMasterBotToken: process.env.TELEGRAM_MASTER_BOT_TOKEN || '',
    telegramIntegrationBotToken: process.env.TELEGRAM_INTEGRATION_BOT_TOKEN || '',
    dbUrl: process.env.DB_URL || 'postgres://localhost:5432/telegram_reviews',
    queueDriver: process.env.QUEUE_DRIVER || 'memory',
    oneCWebhookSecret: process.env.ONE_C_WEBHOOK_SECRET || '',
    enableIntegrationWorker: String(process.env.ENABLE_INTEGRATION_WORKER || 'true') === 'true',
    integrationRetryMax: Number(process.env.INTEGRATION_RETRY_MAX || 3),
    integrationRetryDelaySeconds: Number(process.env.INTEGRATION_RETRY_DELAY_SECONDS || 60),
    oneCSyncEnabled: String(process.env.ONE_C_SYNC_ENABLED || 'false') === 'true',
    emailImportEnabled: String(process.env.EMAIL_IMPORT_ENABLED || 'true') === 'true',
    webAppUrl: process.env.WEBAPP_URL || 'https://example.com',
    feedbackRequestDelayMinutes: Number(process.env.FEEDBACK_REQUEST_DELAY_MINUTES || 5),
    schedulerIntervalMs: Number(process.env.SCHEDULER_INTERVAL_MS || 15000)
  };
}

module.exports = { loadConfig };
