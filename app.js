const { createServer } = require('./src/server');
const { loadConfig } = require('./src/infrastructure/config');
const logger = require('./src/infrastructure/logging/logger');
const db = require('./src/infrastructure/db');
const { createScheduler } = require('./src/infrastructure/scheduler');
const { sendChannelMessage } = require('./src/infrastructure/messaging');
const { reconcileMaxWebhookSubscriptions } = require('./src/infrastructure/max/subscriptions');
const { createEmailIntakePoller } = require('./src/integrations/email/intakePoller');
const { integrationService } = require('./src/core/application');
const { getBuildInfo } = require('./src/infrastructure/buildInfo');
const { ensureReferenceDatasetRuntime } = require('./src/infrastructure/referenceDatasetRuntime');

function bootstrap() {
  const config = loadConfig();
  const buildInfo = getBuildInfo();
  logger.info('App build metadata', {
    appBuildCommit: buildInfo.commitHash,
    appBuildBranch: buildInfo.branch,
    appBuildTimestamp: buildInfo.buildTimestamp
  });
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
  const referenceDatasetRuntime = ensureReferenceDatasetRuntime({ logger });
  logger.info('Reference dataset runtime self-check', referenceDatasetRuntime);
  const server = createServer({ config, logger });
  const aiInfrastructure = require('./src/infrastructure/ai').initializeAiInfrastructure({ config, db, logger });
  integrationService.configureIntegrationRuntime({
    aiService: aiInfrastructure.aiService,
    logger,
    masterNotifier: async ({ requestId, requestPayload }) => {
      if (!config.telegramMasterBotToken || !config.telegramMastersChatId) return { ok: false, reason: 'MASTER_CHAT_NOT_CONFIGURED' };
      const text = [
        '🔥 T-Бизнес заявка (high)',
        `ID: ${requestId}`,
        `Источник: ${requestPayload?.source_provider || 'email'}`,
        `Клиент: ${requestPayload?.existing_client ? 'действующий' : (requestPayload?.needs_review ? 'needs_review' : 'новый')}`,
        `Основание матча: ${requestPayload?.match_basis || 'none'} (${requestPayload?.match_confidence || 0})`,
        `ФИО: ${requestPayload?.parsed_fields?.fullName || '-'}`,
        `Телефон: ${requestPayload?.parsed_fields?.phone || '-'}`,
        `Марка/модель: ${requestPayload?.parsed_fields?.brandModel || '-'}`,
        `Госномер: ${requestPayload?.parsed_fields?.plateNumber || '-'}`,
        `VIN: ${requestPayload?.parsed_fields?.vin || '-'}`,
        `Направление: ${requestPayload?.direction_number || '-'}`,
        `Убыток: ${requestPayload?.claim_number || '-'}`,
        `Email клиента: ${requestPayload?.parsed_fields?.email || '-'}`,
        `Год выпуска: ${requestPayload?.parsed_fields?.year || '-'}`,
        `AI summary: ${String(requestPayload?.ai_summary || '-').slice(0, 600)}`,
        `Спецусловия: ${requestPayload?.parsed_fields?.specialConditions || '-'}`
      ].join('\n');
      const ok = await sendChannelMessage({
        channel: 'telegram',
        token: config.telegramMasterBotToken,
        recipientId: Number(config.telegramMastersChatId),
        text
      });
      return { ok };
    }
  });
  const emailIntakePoller = createEmailIntakePoller({ config, logger });

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
      async waiting_decision_followup(task) {
        const requestId = task.payload?.requestId;
        if (!requestId) throw new Error('REQUEST_ID_REQUIRED');
        const result = db.reactivateWaitingDecisionRequest({ requestId, actorId: 'scheduler', actorRole: 'system' });
        if (!result?.request) throw new Error('REQUEST_NOT_WAITING_DECISION');
        const requestCard = db.getRequestCard(requestId);
        const master = requestCard?.assignedMaster;
        if (master?.telegramId && config.telegramMasterBotToken) {
          await sendChannelMessage({
            channel: 'telegram',
            token: config.telegramMasterBotToken,
            recipientId: Number(master.telegramId),
            text: `Заявка ${requestId} возвращена в работу после статуса ждём решения.`
          });
        } else if (master?.maxId && config.maxMasterBotToken) {
          await sendChannelMessage({
            channel: 'max',
            token: config.maxMasterBotToken,
            recipientId: master.maxId,
            text: `Заявка ${requestId} возвращена в работу после статуса ждём решения.`
          });
        }
      },
      async consulted_followup(task) {
        const requestId = task.payload?.requestId;
        if (!requestId) throw new Error('REQUEST_ID_REQUIRED');
        const result = db.registerConsultedFollowup({ requestId, actorId: 'scheduler', actorRole: 'system' });
        if (!result?.request) throw new Error('REQUEST_NOT_CONSULTED');
        const requestCard = db.getRequestCard(requestId);
        const master = requestCard?.assignedMaster;
        if (master?.telegramId && config.telegramMasterBotToken) {
          await sendChannelMessage({
            channel: 'telegram',
            token: config.telegramMasterBotToken,
            recipientId: Number(master.telegramId),
            text: `Напоминание: свяжитесь с клиентом повторно по заявке ${requestId} (подстатус: проконсультирован).`
          });
        } else if (master?.maxId && config.maxMasterBotToken) {
          await sendChannelMessage({
            channel: 'max',
            token: config.maxMasterBotToken,
            recipientId: master.maxId,
            text: `Напоминание: свяжитесь с клиентом повторно по заявке ${requestId} (подстатус: проконсультирован).`
          });
        }
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
    emailIntakePoller.start();
    emailIntakePoller.runOnce().catch((error) => logger.error('email intake initial poll failed', { error: String(error?.message || error) }));
    reconcileMaxWebhookSubscriptions({ config, logger })
      .then((result) => {
        logger.info('MAX subscription reconciliation finished', result);
      })
      .catch((error) => {
        logger.error('MAX subscription reconciliation failed', { error: String(error?.message || error) });
      });
  });

  server.on('close', () => {
    scheduler.stop();
    emailIntakePoller.stop();
  });

  return server;
}

if (require.main === module) {
  bootstrap();
}

module.exports = { bootstrap };
