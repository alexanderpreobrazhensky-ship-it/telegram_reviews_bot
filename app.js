const { createServer } = require('./src/server');
const { loadConfig } = require('./src/infrastructure/config');
const logger = require('./src/infrastructure/logging/logger');
const db = require('./src/infrastructure/db');
const { createScheduler } = require('./src/infrastructure/scheduler');
const { sendChannelMessage } = require('./src/infrastructure/messaging');

function bootstrap() {
  const config = loadConfig();
  const dbRuntime = db.getDbRuntimeInfo();
  logger.info('DB runtime configured', {
    dbType: dbRuntime.type,
    dbPath: dbRuntime.path,
    dbDirectory: dbRuntime.dir,
    dbFileExistsAtBoot: dbRuntime.exists,
    configuredDbPath: dbRuntime.configuredPath,
    legacyJsonPath: dbRuntime.legacyJsonPath
  });
  const initializedDb = db.initializeStore();
  logger.info('DB startup init complete', {
    dbType: initializedDb.type,
    dbPath: initializedDb.path,
    initStatus: initializedDb.initStatus,
    migration: initializedDb.migration
  });
  const server = createServer({ config, logger });

  if (!config.telegramClientBotToken) {
    logger.warn('TELEGRAM_CLIENT_BOT_TOKEN is missing: outgoing bot notifications are disabled');
  }
  if (config.maxEnabled && !config.maxWebhookSecret) {
    logger.warn('MAX is enabled but MAX_WEBHOOK_SECRET is missing: MAX webhooks will be rejected');
  }
  if (config.maxEnabled && !config.maxClientBotToken) {
    logger.warn('MAX is enabled but MAX_CLIENT_BOT_TOKEN is missing: MAX client webhook replies will be rejected');
  }
  if (config.maxEnabled && !config.maxMasterBotToken) {
    logger.warn('MAX is enabled but MAX_MASTER_BOT_TOKEN is missing: MAX master webhook replies will be rejected');
  }

  const scheduler = createScheduler({
    db,
    logger,
    intervalMs: config.schedulerIntervalMs,
    batchSize: config.schedulerBatchSize,
    maxAttempts: config.schedulerMaxAttempts,
    stuckTimeoutMs: config.schedulerStuckTimeoutMs,
    handlers: {
      async feedback_request(task) {
        const client = task.payload?.clientId ? db.getClientCard(task.payload.clientId)?.client : null;
        const channel = client?.preferredChannel === 'max' ? 'max' : 'telegram';
        const recipientId = channel === 'max' ? client?.maxId : client?.telegramId;
        const token = channel === 'max' ? config.maxClientBotToken : config.telegramClientBotToken;
        if (!client || !recipientId) {
          throw new Error('CLIENT_CHANNEL_UNAVAILABLE');
        }
        const request = task.payload?.requestId ? db.findRequestById(task.payload.requestId) : null;
        await sendChannelMessage({
          channel,
          token,
          recipientId: channel === 'telegram' ? Number(recipientId) : recipientId,
          text: `Оцените, пожалуйста, качество обслуживания по заявке ${request?.id || '-'}: отправьте число от 1 до 5 и при желании комментарий. Пример: 5 Всё отлично`
        });
        db.createCommunicationEvent({
          clientId: client.id,
          requestId: request?.id || null,
          source: 'system',
          channel,
          direction: 'outbound',
          payload: { action: 'feedback_request_sent', taskId: task.id }
        });
      },
      async quality_followup() {},
      async recommendation_reminder() {},
      async maintenance_reminder() {}
    }
  });

  server.listen(config.port, () => {
    const address = server.address();
    const runtimePort = address && typeof address === 'object' ? address.port : config.port;
    logger.info(
      `Platform skeleton server listening on port ${runtimePort} (env PORT=${process.env.PORT || 'not-set'}, fallback=3000)`
    );
    scheduler.start();
  });

  server.on('close', () => {
    scheduler.stop();
  });

  return server;
}

if (require.main === module) {
  bootstrap();
}

module.exports = { bootstrap };
