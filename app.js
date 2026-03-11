const { createServer } = require('./src/server');
const { loadConfig } = require('./src/infrastructure/config');
const logger = require('./src/infrastructure/logging/logger');
const db = require('./src/infrastructure/db');
const { createScheduler } = require('./src/infrastructure/scheduler');

async function sendTelegramMessage(token, chatId, text, extra = {}) {
  if (!token || !chatId) return false;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, ...extra })
  }).catch(() => {});
  return true;
}

function bootstrap() {
  const config = loadConfig();
  const server = createServer({ config, logger });

  if (!config.telegramClientBotToken) {
    logger.warn('TELEGRAM_CLIENT_BOT_TOKEN is missing: outgoing bot notifications are disabled');
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
        if (!client || !client.telegramId) {
          throw new Error('CLIENT_CHANNEL_UNAVAILABLE');
        }
        const request = task.payload?.requestId ? db.findRequestById(task.payload.requestId) : null;
        await sendTelegramMessage(
          config.telegramClientBotToken,
          Number(client.telegramId),
          `Оцените, пожалуйста, качество обслуживания по заявке ${request?.id || '-'}: отправьте число от 1 до 5 и при желании комментарий. Пример: 5 Всё отлично`
        );
        db.createCommunicationEvent({
          clientId: client.id,
          requestId: request?.id || null,
          source: 'system',
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
    logger.info(`Platform skeleton server listening on port ${runtimePort}`);
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
