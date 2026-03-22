const db = require('../../infrastructure/db');
const { createMasterService, createReportingService } = require('../../core/application');
const logger = require('../../infrastructure/logging/logger');
const { sendChannelMessage, answerChannelCallback } = require('../../infrastructure/messaging');
const { extractIncomingEvent } = require('../shared/channelAdapters');
const { validateMaxWebhookRequest } = require('../shared/maxSecurity');
const { REQUEST_STATUSES, REQUEST_SUBSTATUSES } = require('../../core/shared/requestValidation');

const sessions = new Map();
const STATUS_LABELS = {
  new: 'Новая',
  in_progress: 'В работе',
  processed: 'Обработана',
  in_service: 'В сервисе',
  completed: 'Завершена',
  error: 'Ошибка отправки'
};
const PROCESSED_SUBSTATUS_LABELS = {
  recorded: 'записан',
  consulted: 'проконсультирован',
  spam: 'спам',
  waiting_decision: 'ждём решения',
  rejected: 'отказ'
};

function canUseReports(actor) {
  return actor?.role === 'manager' || actor?.role === 'admin';
}
function canManageAccess(actor) {
  return actor?.role === 'manager' || actor?.role === 'admin';
}
function isAdmin(actor) {
  return actor?.role === 'admin';
}

function formatRequestLine(request) {
  return `${request.id} | ${request.requestType} | ${STATUS_LABELS[request.status] || request.status}${request.substatus ? `/${PROCESSED_SUBSTATUS_LABELS[request.substatus] || request.substatus}` : ''} | ${request.description || '-'}`;
}

function buildProcessedSubstatusKeyboard(requestId) {
  return {
    inline_keyboard: [
      [{ text: 'записан', callback_data: `req:${requestId}:processed:recorded` }],
      [{ text: 'проконсультирован', callback_data: `req:${requestId}:processed:consulted` }],
      [{ text: 'спам', callback_data: `req:${requestId}:processed:spam` }],
      [{ text: 'ждём решения', callback_data: `req:${requestId}:processed:waiting_decision` }],
      [{ text: 'отказ', callback_data: `req:${requestId}:processed:rejected` }]
    ]
  };
}

function buildAdminKeyboard(requestId) {
  return [{ text: 'Подробнее', callback_data: `card:${requestId}` }];
}

function buildRequestActionsKeyboard(requestId, card = null) {
  const request = card?.request || {};
  const archived = Boolean(request.archived);
  const completed = request.status === 'completed';
  if (archived || completed) {
    return {
      inline_keyboard: [
        [{ text: 'Подробнее', callback_data: `card:${requestId}` }]
      ]
    };
  }
  return {
    inline_keyboard: [
      [
        { text: 'Взять в работу', callback_data: `req:${requestId}:in_progress` },
        { text: 'Запросить данные', callback_data: `req:${requestId}:ask_client` }
      ],
      [
        { text: 'Обработана', callback_data: `req:${requestId}:processed_menu` },
        { text: 'В сервисе', callback_data: `req:${requestId}:in_service` }
      ],
      [
        { text: 'Завершить', callback_data: `req:${requestId}:completed` },
        { text: 'Подробнее', callback_data: `card:${requestId}` }
      ]
    ]
  };
}

function buildRequestCardText(card) {
  const r = card.request;
  const client = card.client || {};
  const vehicle = card.vehicle || {};
  const executor = card.assignedMaster?.fullName || r.assignedTo || r.assignedMasterId || '-';
  const history = (card.requestEvents || [])
    .slice(-10)
    .map((event) => `${event.createdAt}: ${event.canonicalEventType || event.eventType} ${event.oldValue || event.oldStatus || '-'} -> ${event.newValue || event.newStatus || '-'}${event.comment ? ` (${event.comment})` : ''}`)
    .join('\n') || 'Нет истории';
  return [
    `ID: ${r.id}`,
    `Тип: ${r.requestType}`,
    `Статус: ${STATUS_LABELS[r.status] || r.status}`,
    `Подстатус: ${r.substatus ? PROCESSED_SUBSTATUS_LABELS[r.substatus] || r.substatus : '-'}`,
    `Архив: ${r.archived ? 'да' : 'нет'}`,
    `ФИО: ${client.fullName || '-'}`,
    `Телефон: ${client.phone || '-'}`,
    `Telegram ID: ${client.telegramId || '-'}`,
    `MAX ID: ${client.maxId || '-'}`,
    `VIN: ${vehicle.vin || '-'}`,
    `Марка/модель: ${vehicle.brand || '-'} / ${vehicle.model || '-'}`,
    `Описание: ${r.description || '-'}`,
    `Источник: ${r.sourceChannel || '-'}`,
    `Исполнитель: ${executor}`,
    `Назначил: ${r.assignedBy || '-'}`,
    `Когда назначено: ${r.assignedAt || '-'}`,
    `Последнее повторное касание: ${r.lastFollowupAt || '-'}`,
    `Завершена: ${r.completedAt || '-'}`,
    `Ошибка отправки: ${r.lastOutboundError || '-'}`,
    `Комментарий отказа: ${r.rejectionComment || '-'}`,
    `Создано: ${r.createdAt || '-'}`,
    `История:\n${history}`
  ].join('\n');
}

function qualityCasesText(items) {
  return items.map((item) => `${item.id} | ${item.status} | ${item.summary || '-'}`).join('\n') || 'Нет quality cases';
}

function staffIdentity(user) {
  return user.maxId ? `max:${user.maxId}` : `telegram:${user.telegramId}`;
}

function helpText(channel) {
  return [
    'Инструкция по заявкам:',
    'Статусы:',
    '- Новая (new): заявка только пришла, ещё никем не взята.',
    '- В работе (in_progress): мастер взял заявку в обработку и отвечает за следующий шаг.',
    '- Обработана (processed): заявка обработана, но обязательно с подстатусом.',
    '- В сервисе (in_service): клиент уже приехал/машина в работе сервиса.',
    '- Завершена (completed): финальное закрытие, заявка уходит в архив.',
    '- Ошибка отправки (error): не удалось отправить сообщение клиенту в исходный канал.',
    '',
    'Подстатусы processed:',
    '- записан: клиент записан, можно двигать дальше в «В сервисе» или «Завершить».',
    '- проконсультирован: заявку не архивируем, через scheduler придёт напоминание о повторном контакте.',
    '- спам: заявка архивируется и больше не участвует в работе.',
    '- ждём решения: заявка остаётся активной, через 7 дней scheduler вернёт её в «В работе».',
    '- отказ: заявка архивируется, комментарий обязателен и хранится как причина отказа.',
    '',
    'Кнопки:',
    '- «Взять в работу»: назначает мастера и переводит заявку в «В работе». Свободную заявку может взять мастер, переназначение — только админ.',
    '- «Запросить данные»: открывает режим ввода текста и отправляет сообщение клиенту в исходный подтверждённый канал.',
    '- «Обработана»: показывает выбор подстатуса.',
    '- «В сервисе»: переводит заявку в этап выполнения работ.',
    '- «Завершить»: финально закрывает заявку и архивирует её.',
    '- «Подробнее»: полная карточка заявки с историей.',
    '',
    'Как обрабатывать заявку:',
    '1) Нажмите «Взять в работу».',
    '2) Если данных мало — «Запросить данные».',
    '3) После общения — «Обработана» и выберите подстатус.',
    '4) Когда клиент приехал — «В сервисе».',
    '5) После завершения — «Завершить».',
    '',
    'Запрос данных:',
    '- Telegram-заявки получают ответ в Telegram.',
    '- MAX-заявки получают ответ в MAX.',
    '- Для остальных источников сначала пробуем MAX, затем Telegram, но только при наличии подтверждённых maxId/telegramId.',
    '- Email как канал ответа не используем.',
    '- При ошибке отправки заявка получает статус error, подробности смотрите в логах.',
    '',
    'Повторные касания:',
    '- «Ждём решения»: каждые 7 дней возврат в «В работе» + уведомление мастеру.',
    '- «Проконсультирован»: каждые 7 дней напоминание мастеру о повторном контакте без автоархивации.',
    '',
    'Архив и аналитика:',
    '- В архив автоматически попадают spam, rejected и completed.',
    '- Отказ и спам считаются отдельно для аналитики.',
    '- Причина отказа хранится в карточке и логах.',
    '',
    'Права:',
    '- Админ: всё, включая диагностику, логи и переназначение.',
    '- Мастер/менеджер: работа с заявками в рамках access flow.',
    '- Инструкция доступна всем пользователям master-бота.',
    '',
    'Команды:',
    '/start',
    '/help',
    '/whoami',
    '/search <query>',
    '/request <id>',
    `/set_status <requestId> <${REQUEST_STATUSES.join('|')}> [substatus] [comment]`,
    '/comment <requestId> <text>',
    '/ask_client <requestId> <text>',
    `/access_grant <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager> [ФИО]`,
    `/access_revoke <${channel === 'max' ? 'maxId' : 'telegramId'}>`,
    '/diagnostics',
    '/logs [request:<id>] [type:<type>] [bot:<bot>] [since:YYYY-MM-DD]'
  ].join('\n');
}

function masterToken(config, channel) {
  return channel === 'max' ? config.maxMasterBotToken : config.telegramMasterBotToken;
}
function adminIds(config, channel) {
  return channel === 'max' ? config.maxMasterBotAdminIds : config.masterBotAdminIds;
}
function buildSenderSnapshot({ body, event }) {
  return event.callback
    ? {
        callbackUser: body?.callback?.from || body?.callback?.sender || body?.callback?.user || body?.message_callback?.from || body?.message_callback?.sender || null,
        callbackMessage: body?.callback?.message || body?.message_callback?.message || null
      }
    : event.message?.from || event.message?.sender || body?.sender || body?.user || null;
}
function resolveRecipientId(channel, primaryId, fallbackId) {
  if (channel === 'max') return primaryId || fallbackId || null;
  return fallbackId || primaryId || null;
}
function registerMasterBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/master_bot/webhook', handler: (ctx) => handleMasterWebhook({ ...ctx, channel: 'telegram' }) });
  router.push({ method: 'POST', path: '/max/master_bot/webhook', handler: (ctx) => handleMasterWebhook({ ...ctx, channel: 'max' }) });
}
async function respondWithMessage({ channel, token, recipientId, text, payload = {}, extra = {} }) {
  if (text) {
    const delivered = await sendChannelMessage({ channel, token, recipientId, text, extra });
    if (!delivered) logger.error('master_bot outbound sendMessage failed', { channel, recipientId, textPreview: String(text || '').slice(0, 200) });
  }
  return text ? { ...payload, text } : payload;
}

function parseLogsFilter(text = '') {
  return String(text || '').split(/\s+/).reduce((acc, part) => {
    const [key, ...rest] = part.split(':');
    if (!rest.length) return acc;
    acc[key] = rest.join(':');
    return acc;
  }, {});
}

function maskConfigValue(value) {
  if (!value) return 'missing';
  const raw = String(value);
  if (raw.length <= 6) return 'configured';
  return `${raw.slice(0, 2)}***${raw.slice(-2)}`;
}

function buildDiagnosticsText({ config, actor, channel, detailed = false }) {
  const runtime = db.getDbRuntimeInfo();
  const followupTasks = db.listTasks(['scheduled', 'processing', 'failed']).filter((item) => ['waiting_decision_followup', 'consulted_followup'].includes(item.taskType));
  const writable = require('node:fs').existsSync(runtime.dir || '.');
  const base = [
    'Диагностика:',
    `DB: ok (${runtime.type})`,
    `SQLite path: ${runtime.path}`,
    `DB path writable: ${writable ? 'yes' : 'no'}`,
    `WEBAPP_URL: ${config.webAppUrl ? 'configured' : 'missing'}`,
    `TELEGRAM_CLIENT_BOT_TOKEN: ${config.telegramClientBotToken ? 'configured' : 'missing'}`,
    `TELEGRAM_MASTER_BOT_TOKEN: ${config.telegramMasterBotToken ? 'configured' : 'missing'}`,
    `TELEGRAM_INTEGRATION_BOT_TOKEN: ${config.telegramIntegrationBotToken ? 'configured' : 'missing'}`,
    `MASTER_BOT_ADMIN_IDS: ${(config.masterBotAdminIds || []).length}`,
    `MAX_ENABLED: ${config.maxEnabled ? 'enabled' : 'disabled'}`,
    `MAX_CLIENT_BOT_TOKEN: ${config.maxClientBotToken ? 'configured' : 'missing'}`,
    `MAX_MASTER_BOT_TOKEN: ${config.maxMasterBotToken ? 'configured' : 'missing'}`,
    `MAX_WEBHOOK_SECRET: ${config.maxWebhookSecret ? 'configured' : 'missing'}`,
    `MAX_MASTER_BOT_ADMIN_IDS: ${(config.maxMasterBotAdminIds || []).length}`,
    `MAX_WEBAPP_URL: ${config.maxWebAppUrl ? 'configured' : 'missing'}`,
    `Health endpoints: /health, /health/db, /health/max`,
    `Scheduler follow-up tasks: ${followupTasks.length}`,
    `Webhook routes: /${channel}/master_bot/webhook, /telegram/client_bot/webhook, /max/client_bot/webhook, /telegram/integration_bot/webhook`,
    `Internal routes: /internal/requests, /internal/export, /internal/diagnostics, /internal/logs`,
    `Bots availability: master=${Boolean(masterToken(config, channel))}, client=${Boolean(config.telegramClientBotToken || config.maxClientBotToken)}, integration=${Boolean(config.telegramIntegrationBotToken)}, max=${config.maxEnabled ? Boolean(config.maxClientBotToken && config.maxMasterBotToken) : 'disabled'}`,
    `Actor: ${actor.id} (${actor.role})`
  ];
  if (!detailed) return base.join('\n');
  return [
    ...base,
    '',
    'Masked values:',
    `telegram client token: ${maskConfigValue(config.telegramClientBotToken)}`,
    `telegram master token: ${maskConfigValue(config.telegramMasterBotToken)}`,
    `telegram integration token: ${maskConfigValue(config.telegramIntegrationBotToken)}`,
    `max client token: ${maskConfigValue(config.maxClientBotToken)}`,
    `max master token: ${maskConfigValue(config.maxMasterBotToken)}`,
    `max webhook secret: ${maskConfigValue(config.maxWebhookSecret)}`
  ].join('\n');
}

function buildLogsText(filters = {}, detailed = false) {
  const logs = db.listOperationalLogs({
    requestId: filters.request,
    since: filters.since,
    eventType: filters.type,
    bot: filters.bot,
    channel: filters.channel,
    user: filters.user,
    limit: detailed ? 50 : 20
  });
  const sections = [];
  sections.push(`Логи (${detailed ? 'подробно' : 'кратко'}):`);
  sections.push(`Фильтры: request=${filters.request || '-'} type=${filters.type || '-'} bot=${filters.bot || '-'} since=${filters.since || '-'} channel=${filters.channel || '-'} user=${filters.user || '-'}`);
  sections.push('Errors / events:');
  sections.push((logs.events || []).slice(0, detailed ? 20 : 10).map((item) => detailed
    ? `${item.createdAt} | ${item.canonicalEventType || item.eventType} | req=${item.requestId || '-'} | actor=${item.actorId || '-'} | comment=${item.comment || '-'} | meta=${JSON.stringify(item.metaJson || {})}`
    : `${item.createdAt} | ${item.canonicalEventType || item.eventType} | ${item.requestId || '-'} | ${item.comment || '-'}`).join('\n') || 'Нет request_events');
  sections.push('Communications:');
  sections.push((logs.communications || []).slice(0, detailed ? 20 : 10).map((item) => detailed
    ? `${item.createdAt} | ${item.source || item.channel} | req=${item.requestId || '-'} | dir=${item.direction || '-'} | payload=${JSON.stringify(item.payload || {})}`
    : `${item.createdAt} | ${item.source || item.channel} | ${item.requestId || '-'} | ${item.direction || '-'}`).join('\n') || 'Нет communications');
  sections.push('Integration/webhook:');
  sections.push((logs.integration || []).slice(0, detailed ? 20 : 10).map((item) => detailed
    ? `${item.createdAt} | ${item.eventType} | status=${item.status || item.processingStatus || '-'} | req=${item.requestId || '-'} | meta=${JSON.stringify(item.metaJson || {})}`
    : `${item.createdAt} | ${item.eventType} | ${item.status || item.processingStatus || '-'} | ${item.requestId || '-'}`).join('\n') || 'Нет analytics/integration ошибок');
  return sections.join('\n\n');
}

async function handleMasterWebhook({ body, config, headers = {}, rawHeaders = [], pathname = '', method = 'POST', channel = 'telegram' }) {
  if (channel === 'max') {
    db.createAnalyticsEvent({ eventType: 'max_webhook_received', channel: 'max', platform: 'max', status: 'received', metaJson: { route: 'master_bot', pathname, method } });
    const validation = validateMaxWebhookRequest({ config, headers, rawHeaders, pathname, method, logger, routeLabel: 'master_bot', token: masterToken(config, channel), body });
    if (!validation.ok) {
      db.createAnalyticsEvent({ eventType: 'max_webhook_rejected', channel: 'max', platform: 'max', status: validation.error, metaJson: { route: 'master_bot', pathname, method, statusCode: validation.statusCode } });
      return { ok: false, error: validation.error, statusCode: validation.statusCode };
    }
  }

  try {
    const event = extractIncomingEvent({ body, channel });
    const updateType = event.callback ? 'callback' : (event.message ? 'message' : 'unknown');
    const senderBlock = buildSenderSnapshot({ body, event });
    logger.info('master_bot webhook parsed update', { channel, pathname, method, updateType, senderBlock, text: String(event.callback ? event.callback.data || '' : event.text || '').slice(0, 500) });
    if (!event.message && !event.callback) return { ok: true, action: 'ignored_unknown_update', updateType };

    const token = masterToken(config, channel);
    const masterService = createMasterService({ db, sendClientMessage: sendChannelMessage, adminIds: adminIds(config, channel), actorChannel: channel });
    const reportingService = createReportingService({ db });
    const channelUserId = event.callback?.userId || event.userId;
    const fullName = event.callback?.fullName || event.fullName;
    const actor = masterService.resolveActor({ channelUserId, telegramId: channel === 'telegram' ? channelUserId : null, maxId: channel === 'max' ? channelUserId : null, fullName });
    const recipientId = resolveRecipientId(channel, channelUserId, event.callback?.chatId || event.chatId);
    const sessionKey = `${channel}:${channelUserId}`;
    const text = String(event.text || '').trim();

    if (text === '/whoami') {
      return respondWithMessage({ channel, token, recipientId, text: [`Identity: ${actor?.id || channelUserId || '-'}`, `Role: ${actor?.role || 'unknown'}`, `Channel: ${channel}`, `Channel user id: ${channelUserId || '-'}`, `Name: ${actor?.fullName || fullName || '-'}`].join('\n'), payload: { ok: true, action: 'whoami', channelUserId, channel, actor } });
    }

    if (text === '/help' || text === 'Инструкция') {
      return respondWithMessage({ channel, token, recipientId, text: helpText(channel), payload: { ok: true, action: 'help' } });
    }

    if (!actor) {
      if (recipientId) await respondWithMessage({ channel, token, recipientId, text: `Доступ запрещён: user_id ${channelUserId || '-'} не найден в staff/admin. Используйте /whoami.`, payload: { ok: false, error: 'ACCESS_DENIED', reason: 'ACTOR_NOT_FOUND_OR_NOT_ALLOWED', channelUserId } });
      return { ok: false, error: 'ACCESS_DENIED', reason: 'ACTOR_NOT_FOUND_OR_NOT_ALLOWED', channelUserId };
    }

    if (event.callback?.id) {
      const data = String(event.callback.data || '');
      if (data.startsWith('card:')) {
        const requestId = data.split(':')[1];
        const card = masterService.getRequestCard(requestId);
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: card ? 'Открываю карточку' : 'Заявка не найдена' });
        if (!card) return { ok: false, error: 'REQUEST_NOT_FOUND' };
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(requestId, card) } });
      }
      if (data === 'admin:diagnostics' || data === 'admin:diagnostics_short') {
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Готово' });
        return respondWithMessage({ channel, token, recipientId, text: buildDiagnosticsText({ config, actor, channel, detailed: false }), payload: { ok: true } });
      }
      if (data === 'admin:diagnostics_detailed') {
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Подробно' });
        return respondWithMessage({ channel, token, recipientId, text: buildDiagnosticsText({ config, actor, channel, detailed: true }), payload: { ok: true } });
      }
      if (data === 'admin:logs' || data === 'admin:logs_short' || data === 'admin:logs_detailed') {
        sessions.set(sessionKey, { step: 'logs_filter', detailed: data === 'admin:logs_detailed' });
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите фильтр' });
        return respondWithMessage({ channel, token, recipientId, text: 'Введите фильтр логов в формате request:<id> type:<type> bot:<bot> since:YYYY-MM-DD' });
      }
      if (data.startsWith('req:')) {
        const [, requestId, action, maybeSubstatus] = data.split(':');
        if (action === 'ask_client') {
          sessions.set(sessionKey, { step: 'ask_client', requestId });
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите сообщение' });
          return respondWithMessage({ channel, token, recipientId, text: `Введите сообщение клиенту по заявке ${requestId}` });
        }
        if (action === 'processed_menu') {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Выберите подстатус' });
          return respondWithMessage({ channel, token, recipientId, text: 'Выберите подстатус обработки', payload: { ok: true }, extra: { reply_markup: buildProcessedSubstatusKeyboard(requestId) } });
        }
        if (action === 'processed') {
          if (maybeSubstatus === 'rejected') {
            sessions.set(sessionKey, { step: 'rejected_comment', requestId, substatus: maybeSubstatus });
            await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Нужен комментарий' });
            return respondWithMessage({ channel, token, recipientId, text: `Укажите комментарий для отказа по заявке ${requestId}` });
          }
          const result = masterService.changeRequestStatus({ requestId, toStatus: 'processed', substatus: maybeSubstatus, actorId: actor.id, actorRole: actor.role });
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: result?.error ? 'Ошибка' : 'Готово' });
          return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Заявка ${requestId} → processed/${maybeSubstatus}`, payload: { ok: !result?.error, ...result } });
        }
        if (action === 'in_progress') {
          const assignment = masterService.assignRequest({ requestId, assignedTo: actor.id, assignedBy: actor.id, actorId: actor.id, actorRole: actor.role, actorType: actor.role, metaJson: { channel, source: 'take_in_progress' } });
          if (assignment?.error) {
            await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Назначение недоступно' });
            return respondWithMessage({ channel, token, recipientId, text: `Ошибка: ${assignment.error}`, payload: { ok: false, ...assignment } });
          }
        }
        const result = masterService.changeRequestStatus({ requestId, toStatus: action, actorId: actor.id, actorRole: actor.role });
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: result?.error ? 'Ошибка' : 'Готово' });
        return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус заявки ${requestId}: ${action}`, payload: { ok: !result?.error, ...result } });
      }
    }

    if (text === '/start') {
      const baseKeyboard = [['Новые заявки', 'В работе'], ['Архив', 'Поиск'], ['Quality Cases', 'Инструкция']];
      if (isAdmin(actor)) baseKeyboard.push(['Диагностика', 'Логи']);
      if (canManageAccess(actor)) baseKeyboard.push(['Доступы']);
      await sendChannelMessage({ channel, token, recipientId, text: `Master Bot запущен. Роль: ${actor.role}.`, extra: { reply_markup: { keyboard: baseKeyboard, resize_keyboard: true } } });
      db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: { channel } });
      return { ok: true, action: 'start' };
    }

    if (text === 'Новые заявки' || text === 'В работе') {
      const items = text === 'Новые заявки' ? masterService.listRequestsByStatus('new') : masterService.listActiveRequests();
      await respondWithMessage({ channel, token, recipientId, text: items.map(formatRequestLine).join('\n') || (text === 'Новые заявки' ? 'Нет новых заявок' : 'Нет заявок в работе') });
      for (const item of items.slice(0, 10)) await sendChannelMessage({ channel, token, recipientId, text: `Заявка ${item.id}`, extra: { reply_markup: buildRequestActionsKeyboard(item.id, { request: item }) } });
      return { ok: true, items };
    }
    if (text === 'Архив') {
      const items = masterService.listArchiveRequests();
      await respondWithMessage({ channel, token, recipientId, text: items.map(formatRequestLine).join('\n') || 'Архив пуст' });
      for (const item of items.slice(0, 10)) await sendChannelMessage({ channel, token, recipientId, text: `Архивная заявка ${item.id}`, extra: { reply_markup: buildRequestActionsKeyboard(item.id, { request: item }) } });
      return { ok: true, items };
    }

    if (text === 'Поиск') {
      sessions.set(sessionKey, { step: 'search_query' });
      return respondWithMessage({ channel, token, recipientId, text: 'Введите строку для поиска (ФИО, телефон, VIN или номер).' });
    }
    if (text === 'Диагностика' || text === '/diagnostics') {
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      return respondWithMessage({
        channel,
        token,
        recipientId,
        text: buildDiagnosticsText({ config, actor, channel, detailed: false }),
        payload: { ok: true },
        extra: {
          reply_markup: {
            inline_keyboard: [
              [{ text: 'обновить', callback_data: 'admin:diagnostics' }, { text: 'прогнать проверку', callback_data: 'admin:diagnostics' }],
              [{ text: 'краткий статус', callback_data: 'admin:diagnostics_short' }, { text: 'подробный статус', callback_data: 'admin:diagnostics_detailed' }]
            ]
          }
        }
      });
    }
    if (text === 'Логи' || text.startsWith('/logs')) {
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const filters = parseLogsFilter(text.replace('/logs', '').trim());
      if (!Object.keys(filters).length && text === 'Логи') {
        sessions.set(sessionKey, { step: 'logs_filter' });
        return respondWithMessage({ channel, token, recipientId, text: 'Введите фильтр логов в формате request:<id> type:<type> bot:<bot> since:YYYY-MM-DD' });
      }
      return respondWithMessage({
        channel,
        token,
        recipientId,
        text: buildLogsText(filters, false),
        payload: { ok: true, filters },
        extra: { reply_markup: { inline_keyboard: [[{ text: 'кратко', callback_data: 'admin:logs_short' }, { text: 'подробно', callback_data: 'admin:logs_detailed' }]] } }
      });
    }
    if (text === 'Доступы') {
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      return respondWithMessage({ channel, token, recipientId, text: `Раздел доступов:\n/access_list\n/access_grant <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager> [ФИО]\n/access_revoke <${channel === 'max' ? 'maxId' : 'telegramId'}>` });
    }
    if (text === 'Quality Cases' || text === '/quality_cases') {
      const items = masterService.listQualityCases();
      return respondWithMessage({ channel, token, recipientId, text: qualityCasesText(items), payload: { ok: true, items } });
    }

    const session = sessions.get(sessionKey);
    if (session?.step === 'search_query') {
      sessions.delete(sessionKey);
      const results = masterService.search(text);
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, action: 'search_results', card, ...results }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id, card) } });
      }
      return respondWithMessage({ channel, token, recipientId, text: 'Ничего не найдено', payload: { ok: true, action: 'search_results', ...results } });
    }
    if (session?.step === 'ask_client') {
      sessions.delete(sessionKey);
      const result = await masterService.requestClientClarification({ requestId: session.requestId, actorId: actor.id, actorRole: actor.role, text, telegramClientBotToken: config.telegramClientBotToken, maxClientBotToken: config.maxClientBotToken });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : `Сообщение клиенту ${result.ok ? 'отправлено' : 'не отправлено'}`, payload: result });
    }
    if (session?.step === 'rejected_comment') {
      sessions.delete(sessionKey);
      const result = masterService.changeRequestStatus({ requestId: session.requestId, toStatus: 'processed', substatus: 'rejected', actorId: actor.id, actorRole: actor.role, comment: text, lostReason: text });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : `Заявка ${session.requestId} переведена в отказ`, payload: { ok: !result.error, ...result } });
    }
    if (session?.step === 'logs_filter') {
      sessions.delete(sessionKey);
      return respondWithMessage({ channel, token, recipientId, text: buildLogsText(parseLogsFilter(text), Boolean(session.detailed)), payload: { ok: true } });
    }

    if (text.startsWith('/access_list')) {
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const items = masterService.listStaffUsers();
      return respondWithMessage({ channel, token, recipientId, text: items.map((u) => `${staffIdentity(u)} | ${u.role} | ${u.fullName || '-'}`).join('\n') || 'Список пуст', payload: { ok: true, items } });
    }
    if (text.startsWith('/access_grant ') || text.startsWith('/access_role ')) {
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const [, externalId, role, ...nameParts] = text.split(' ');
      const result = masterService.grantStaffAccess({ channelUserId: externalId, telegramId: channel === 'telegram' ? externalId : null, maxId: channel === 'max' ? externalId : null, fullName: nameParts.join(' ').trim(), role, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : `Доступ обновлён: ${externalId} -> ${role}`, payload: { ok: !result.error, ...result } });
    }
    if (text.startsWith('/access_revoke ')) {
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const [, externalId] = text.split(' ');
      const result = masterService.revokeStaffAccess({ channelUserId: externalId, telegramId: channel === 'telegram' ? externalId : null, maxId: channel === 'max' ? externalId : null, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : `Доступ отозван: ${externalId}`, payload: { ok: !result.error, ...result } });
    }
    if (text.startsWith('/search ')) {
      const results = masterService.search(text.slice(8));
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, ...results, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id, card) } });
      }
      return respondWithMessage({ channel, token, recipientId, text: 'Ничего не найдено', payload: { ok: true, ...results } });
    }
    if (text.startsWith('/client ')) {
      const card = masterService.getClientCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'CLIENT_NOT_FOUND' };
    }

    if (text.startsWith('/request ')) {
      const card = masterService.getRequestCard(text.split(' ')[1]);
      return card ? respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id, card) } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }
    if (text.startsWith('/set_status ')) {
      const [, requestId, toStatus, maybeSubstatus, ...rest] = text.split(' ');
      const substatus = REQUEST_SUBSTATUSES.includes(maybeSubstatus) ? maybeSubstatus : null;
      const comment = substatus ? rest.join(' ') : [maybeSubstatus, ...rest].filter(Boolean).join(' ');
      const result = masterService.changeRequestStatus({ requestId, toStatus, substatus, actorId: actor.id, actorRole: actor.role, comment, lostReason: comment });
      return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус обновлён: ${toStatus}${substatus ? '/' + substatus : ''}`, payload: { ok: !result?.error, ...result } });
    }
    if (text.startsWith('/comment ')) {
      const [, requestId, ...commentParts] = text.split(' ');
      const comment = masterService.addInternalComment({ requestId, actorId: actor.id, actorRole: actor.role, text: commentParts.join(' ') });
      return comment ? respondWithMessage({ channel, token, recipientId, text: 'Комментарий добавлен', payload: { ok: true, comment } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }
    if (text.startsWith('/ask_client ')) {
      const [, requestId, ...textParts] = text.split(' ');
      const result = await masterService.requestClientClarification({ requestId, actorId: actor.id, actorRole: actor.role, text: textParts.join(' '), telegramClientBotToken: config.telegramClientBotToken, maxClientBotToken: config.maxClientBotToken });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : 'Запрос клиенту отправлен/зафиксирован', payload: result });
    }
    if (text === '/report_week' || text === '/report_month' || text === '/report_quarter' || text === '/report_stats') {
      if (!canUseReports(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав для отчётов.', payload: { ok: false, error: 'REPORT_ACCESS_DENIED', allowedRoles: ['manager', 'admin'] } });
      const periodMap = { '/report_week': 'weekly', '/report_month': 'monthly', '/report_quarter': 'quarterly', '/report_stats': 'weekly' };
      const report = reportingService.buildManagementSummary({ period: periodMap[text] });
      return respondWithMessage({ channel, token, recipientId, text: report.summaryText, payload: { ok: true, report } });
    }
    if (text.startsWith('/quality_case ')) {
      const card = masterService.getQualityCaseCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }
    if (text.startsWith('/quality_status ')) {
      const [, qualityCaseId, status] = text.split(' ');
      const qualityCase = masterService.changeQualityCaseStatus({ qualityCaseId, status, actorId: actor.id, actorRole: actor.role });
      return qualityCase ? { ok: true, qualityCase } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }
    if (text.startsWith('/quality_comment ')) {
      const [, qualityCaseId, ...parts] = text.split(' ');
      const comment = masterService.addQualityCaseComment({ qualityCaseId, actorId: actor.id, actorRole: actor.role, text: parts.join(' ') });
      return comment ? { ok: true, comment } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }

    return respondWithMessage({ channel, token, recipientId, text: 'Используйте /help для списка команд.', payload: { ok: true, action: 'fallback' } });
  } catch (error) {
    logger.error('master_bot handler error', { channel, pathname, method, error: String(error?.message || error), body });
    const fallbackUserId = String(body?.message?.from?.user_id || body?.message?.from?.id || body?.callback?.from?.user_id || body?.callback?.from?.id || body?.user?.user_id || body?.user?.id || '');
    const fallbackChatId = body?.message?.chat_id || body?.message?.chat?.id || body?.callback?.message?.chat_id || body?.callback?.message?.chat?.id || null;
    const recipientId = resolveRecipientId(channel, fallbackUserId, fallbackChatId);
    if (recipientId) await respondWithMessage({ channel, token: masterToken(config, channel), recipientId, text: 'Внутренняя ошибка master bot.', payload: { ok: false, error: 'MASTER_BOT_ERROR' } });
    return { ok: false, error: 'MASTER_BOT_ERROR', statusCode: 500 };
  }
}

module.exports = { registerMasterBotRoutes, handleMasterWebhook };
