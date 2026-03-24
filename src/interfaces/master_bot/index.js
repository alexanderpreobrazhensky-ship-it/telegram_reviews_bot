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
  waiting_decision: 'ждёт решения',
  rejected: 'отказ'
};
const LEGACY_CALLBACK_MAP = Object.freeze({
  assigned: { action: 'in_progress', event: 'legacy_assign' },
  awaiting_client: { action: 'refresh_only', event: 'legacy_waiting_client' },
  waiting_data: { action: 'refresh_only', event: 'legacy_waiting_data' },
  scheduled: { action: 'processed_menu', event: 'legacy_scheduled' },
  done: { action: 'completed', event: 'legacy_done' },
  cancelled: { action: 'rejected_only', event: 'legacy_cancelled' }
});

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
      [{ text: 'Записан', callback_data: `req:${requestId}:processed:recorded` }],
      [{ text: 'Проконсультирован', callback_data: `req:${requestId}:processed:consulted` }],
      [{ text: 'Спам', callback_data: `req:${requestId}:processed:spam` }],
      [{ text: 'Ждёт решения', callback_data: `req:${requestId}:processed:waiting_decision` }],
      [{ text: 'Отказ', callback_data: `req:${requestId}:processed:rejected` }]
    ]
  };
}

function buildHistoryLines(card) {
  return (card.requestEvents || [])
    .slice(-20)
    .map((event) => `${event.createdAt}: ${event.canonicalEventType || event.eventType} ${event.oldValue || event.oldStatus || '-'} -> ${event.newValue || event.newStatus || '-'}${event.comment ? ` (${event.comment})` : ''}`)
    .join('\n') || 'Нет истории';
}

function buildRequestActionsKeyboard(requestId, card = null, actor = null) {
  const request = card?.request || {};
  const archived = Boolean(request.archived);
  const completed = request.status === 'completed';
  if (archived || completed) {
    const archivedRows = [[{ text: 'Подробнее', callback_data: `card:${requestId}` }, { text: 'История', callback_data: `history:${requestId}` }]];
    if (isAdmin(actor)) archivedRows.push([{ text: 'Логи', callback_data: `logs:${requestId}` }]);
    return { inline_keyboard: archivedRows };
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
        { text: 'Комментарий', callback_data: `req:${requestId}:comment` }
      ],
      [
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
  const history = buildHistoryLines(card);
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

const MENU_TEXT_TO_ACTION = Object.freeze({
  'Новые заявки': 'menu:new_requests',
  'В работе': 'menu:in_progress',
  'Архив': 'menu:archive',
  'Поиск': 'menu:search',
  'Quality Cases': 'menu:quality_cases',
  'Инструкция': 'menu:instruction',
  'Диагностика': 'menu:diagnostics',
  'Логи': 'menu:logs',
  'AI': 'menu:ai',
  'Доступы': 'menu:access'
});

function buildMainMenuKeyboard(actor) {
  const rows = [
    [
      { text: 'Новые заявки', callback_data: 'menu:new_requests' },
      { text: 'В работе', callback_data: 'menu:in_progress' }
    ],
    [
      { text: 'Архив', callback_data: 'menu:archive' },
      { text: 'Поиск', callback_data: 'menu:search' }
    ],
    [
      { text: 'Quality Cases', callback_data: 'menu:quality_cases' },
      { text: 'Инструкция', callback_data: 'menu:instruction' }
    ]
  ];
  if (isAdmin(actor)) rows.push([{ text: 'Диагностика', callback_data: 'menu:diagnostics' }, { text: 'Логи', callback_data: 'menu:logs' }]);
  if (isAdmin(actor)) rows.push([{ text: 'AI', callback_data: 'menu:ai' }]);
  if (canManageAccess(actor)) rows.push([{ text: 'Доступы', callback_data: 'menu:access' }]);
  return { inline_keyboard: rows };
}

function staffIdentity(user) {
  return user.maxId ? `max:${user.maxId}` : `telegram:${user.telegramId}`;
}

function helpText(channel) {
  return [
    'Инструкция по заявкам:',
    'Статусы:',
    '- Новая (new): заявка только пришла, ещё никем не взята.',
    '- В работе (in_progress): мастер взял заявку и отвечает за дальнейшее движение.',
    '- Обработана (processed): обязательный основной статус после общения, всегда идёт с подстатусом.',
    '- В сервисе (in_service): клиент записан/приехал, заявка передана в сервисный контур.',
    '- Завершена (completed): окончательно закрыта и архивирована.',
    '- Ошибка отправки (error): не удалось отправить сообщение клиенту в подтверждённый канал.',
    '',
    'Подстатусы processed:',
    '- recorded: записан, заявка остаётся активной.',
    '- consulted: проконсультирован, заявка не архивируется, scheduler напоминает о повторном контакте.',
    '- spam: архивируется сразу и исключается из follow-up.',
    '- waiting_decision: ждёт решения, каждые 7 дней scheduler возвращает заявку в «В работе».',
    '- rejected: отказ, архивируется сразу, комментарий обязателен.',
    '',
    'Кнопки карточки:',
    '- «Взять в работу»: безопасное назначение на мастера.',
    '- «Запросить данные»: свободный текст клиенту в исходный подтверждённый канал.',
    '- «Обработана»: выбор подстатуса второго уровня.',
    '- «В сервисе»: отдельный статус до завершения.',
    '- «Завершить»: финальное закрытие заявки.',
    '- «Комментарий»: внутренний комментарий.',
    '- «Подробнее»: карточка, история, служебные поля.',
    '',
    'Архив:',
    '- В архив автоматически попадают spam, rejected и completed.',
    '- Для архивных заявок доступны только Подробнее/История/Логи (админ).',
    '',
    'Повторные касания:',
    '- waiting_decision: авто-возврат в in_progress через 7 дней + событие и уведомление.',
    '- consulted: напоминание мастеру каждые 7 дней без смены статуса.',
    '',
    'Каналы отправки:',
    '- Telegram -> Telegram.',
    '- MAX -> MAX.',
    '- Иной источник -> сначала MAX при наличии maxId, затем Telegram при наличии telegramId.',
    '- Email не используется как outbound-канал.',
    '',
    'Права:',
    '- Админ: диагностика, логи, переназначение, доступы.',
    '- Master/manager: работа с заявками и поиском.',
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
    '/logs [request:<id>] [type:<type>] [bot:<bot>] [since:YYYY-MM-DD]',
    '/ai_status',
    '/ai_diagnostics',
    '/ai_logs [since:YYYY-MM-DD] [provider:<proxy|openai|deepseek>] [status:<success|fail>] [task:<task_type>]',
    '/ai_switch provider:<name> model:<name> fallbackProvider:<name> fallbackModel:<name>'
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

function buildDiagnosticsText({ config, actor, channel, detailed = false, aiInfrastructure = null }) {
  const runtime = db.getDbRuntimeInfo();
  const followupTasks = db.listTasks(['scheduled', 'processing', 'failed']).filter((item) => ['waiting_decision_followup', 'consulted_followup'].includes(item.taskType));
  const writable = require('node:fs').existsSync(runtime.dir || '.');
  const ai = config.ai || {};
  const aiRuntime = aiInfrastructure?.runtimeSettings?.get ? aiInfrastructure.runtimeSettings.get() : null;
  const base = [
    'Диагностика:',
    `/health: OK`,
    `/health/db: ${runtime.path ? 'OK' : 'ERROR'} (${runtime.type})`,
    `/health/max: ${config.maxEnabled ? (config.maxWebhookSecret && config.maxMasterBotToken && config.maxClientBotToken ? 'OK' : 'ERROR') : 'OK (disabled)'}`,
    `DB доступ: ${writable ? 'OK' : 'ERROR'} (${runtime.path})`,
    `Telegram bot: ${config.telegramMasterBotToken && config.telegramClientBotToken ? 'OK' : 'ERROR'}`,
    `MAX bot: ${config.maxEnabled ? (config.maxMasterBotToken && config.maxClientBotToken ? 'OK' : 'ERROR') : 'OK (disabled)'}`,
    `WebApp URL: ${config.webAppUrl ? 'OK' : 'ERROR'}`,
    `Master admins: ${(config.masterBotAdminIds || []).length}`,
    `MAX master admins: ${(config.maxMasterBotAdminIds || []).length}`,
    `Scheduler follow-up tasks: ${followupTasks.length}`,
    `AI ready: ${ai.enabled ? 'ON' : 'OFF'} (${(aiRuntime?.activeProvider || ai.provider || 'proxy')}${(aiRuntime?.activeModel || ai.model) ? `/${aiRuntime?.activeModel || ai.model}` : ''})`,
    `Webhook routes: /${channel}/master_bot/webhook, /telegram/client_bot/webhook, /max/client_bot/webhook, /telegram/integration_bot/webhook`,
    `Internal routes: /internal/requests, /internal/export, /internal/diagnostics, /internal/logs`,
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
    `max webhook secret: ${maskConfigValue(config.maxWebhookSecret)}`,
    `ai enabled: ${ai.enabled ? 'true' : 'false'}`,
    `ai provider: ${ai.provider || '-'}`,
    `ai model: ${ai.model || '-'}`,
    `ai proxy token: ${maskConfigValue(ai.proxyToken)}`,
    `ai openai key: ${maskConfigValue(ai.openaiApiKey)}`,
    `ai deepseek key: ${maskConfigValue(ai.deepseekApiKey)}`
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
  sections.push('request_events:');
  sections.push((logs.events || []).slice(0, detailed ? 20 : 10).map((item) => detailed
    ? `${item.createdAt} | request_id=${item.requestId || '-'} | action=${item.canonicalEventType || item.eventType} | result=${item.newValue || item.newStatus || item.comment || 'ok'} | error=${item.metaJson?.reason || '-'} | actor=${item.actorId || '-'} | meta=${JSON.stringify(item.metaJson || {})}`
    : `${item.createdAt} | request_id=${item.requestId || '-'} | action=${item.canonicalEventType || item.eventType} | result=${item.newValue || item.newStatus || item.comment || 'ok'} | error=${item.metaJson?.reason || '-'}`).join('\n') || 'Нет request_events');
  sections.push('communications:');
  sections.push((logs.communications || []).slice(0, detailed ? 20 : 10).map((item) => detailed
    ? `${item.createdAt} | request_id=${item.requestId || '-'} | action=${item.payload?.action || item.direction || '-'} | result=${item.source || item.channel} | error=${item.payload?.error || '-'} | payload=${JSON.stringify(item.payload || {})}`
    : `${item.createdAt} | request_id=${item.requestId || '-'} | action=${item.payload?.action || item.direction || '-'} | result=${item.source || item.channel} | error=${item.payload?.error || '-'}`).join('\n') || 'Нет communications');
  sections.push('analytics_events:');
  sections.push((logs.integration || []).slice(0, detailed ? 20 : 10).map((item) => detailed
    ? `${item.createdAt} | request_id=${item.requestId || '-'} | action=${item.eventType} | result=${item.status || item.processingStatus || '-'} | error=${item.metaJson?.error || '-'} | meta=${JSON.stringify(item.metaJson || {})}`
    : `${item.createdAt} | request_id=${item.requestId || '-'} | action=${item.eventType} | result=${item.status || item.processingStatus || '-'} | error=${item.metaJson?.error || '-'}`).join('\n') || 'Нет analytics/integration ошибок');
  return sections.join('\n\n');
}


function buildAiMenuKeyboard() {
  return {
    inline_keyboard: [
      [{ text: 'AI Статус', callback_data: 'ai:status' }],
      [{ text: 'AI Диагностика', callback_data: 'ai:diagnostics' }],
      [{ text: 'AI Переключение', callback_data: 'ai:switch' }],
      [{ text: 'AI Логи', callback_data: 'ai:logs' }]
    ]
  };
}

function buildAiStatusText({ aiInfrastructure, config }) {
  if (!aiInfrastructure) return 'AI infrastructure not initialized';
  const runtime = aiInfrastructure.runtimeSettings.get();
  const diagnostics = aiInfrastructure.runtimeSettings.getDiagnosticsState() || {};
  return [
    'AI статус:',
    `AI enabled: ${runtime.aiEnabledRuntime ? 'ON' : 'OFF'} (env=${config.ai?.enabled ? 'ON' : 'OFF'})`,
    `AI business usage enabled: ${runtime.aiBusinessUsageEnabledRuntime ? 'ON' : 'OFF'} (env=${config.ai?.businessUsageEnabled ? 'ON' : 'OFF'})`,
    `Active provider/model: ${runtime.activeProvider}/${runtime.activeModel}`,
    `Active source: provider=${config.ai?.sources?.AI_PROVIDER?.source || 'default'} model=${config.ai?.sources?.AI_MODEL?.source || 'default'}`,
    `Fallback provider/model: ${runtime.activeFallbackProvider}/${runtime.activeFallbackModel}`,
    `Allowed providers: ${(runtime.allowedProviders || []).join(', ') || '-'}`,
    `Timeout: ${config.ai?.timeoutMs || 0}ms (source=${config.ai?.sources?.AI_TIMEOUT_MS?.source || 'default'})`,
    `Proxy configured: ${config.ai?.proxyUrl && config.ai?.proxyToken ? 'yes' : 'no'}`,
    `Legacy AI env used: ${(config.ai?.legacyUsed || []).join(', ') || '-'}`,
    `Last diagnostics: ${diagnostics.status || runtime.lastAiDiagnosticsStatus || 'never'}`,
    `Last diagnostics at: ${diagnostics.at || runtime.lastAiDiagnosticsAt || '-'}`,
    `Last diagnostics summary: ${diagnostics.summary || runtime.lastAiDiagnosticsSummary || '-'}`
  ].join('\n');
}

function buildAiLogsText(aiInfrastructure, filters = {}) {
  const events = aiInfrastructure?.listLogs({
    since: filters.since || null,
    provider: filters.provider || null,
    status: filters.status || null,
    taskType: filters.task || null,
    limit: Number(filters.limit || 20)
  }) || [];
  const lines = events.map((item) => `${item.timestamp} | task_type=${item.taskType} | provider=${item.provider} | model=${item.model} | duration_ms=${item.durationMs} | ${item.success ? 'success' : 'fail'} | fallback_used=${item.fallbackUsed ? 'yes' : 'no'} | error_code=${item.errorCode || '-'} | error=${item.errorSummary || '-'}`);
  return ['AI логи:', `Фильтры: since=${filters.since || '-'} provider=${filters.provider || '-'} status=${filters.status || '-'} task=${filters.task || '-'}`, lines.join('\n') || 'Нет AI событий'].join('\n\n');
}

function parseAiSwitchCommand(text = '') {
  const parts = String(text || '').trim().split(/\s+/);
  if (parts[0] !== '/ai_switch') return null;
  const payload = {};
  for (const part of parts.slice(1)) {
    const [key, ...rest] = part.split(':');
    if (!rest.length) continue;
    payload[key] = rest.join(':');
  }
  return {
    activeProvider: payload.provider,
    activeModel: payload.model,
    activeFallbackProvider: payload.fallbackProvider,
    activeFallbackModel: payload.fallbackModel
  };
}
async function handleMenuAction({ action, actor, channel, token, recipientId, masterService, config, sessionKey, callbackId = null, aiInfrastructure = null }) {
  const callbackText = {
    'menu:new_requests': 'Новые заявки',
    'menu:in_progress': 'В работе',
    'menu:archive': 'Архив',
    'menu:search': 'Поиск',
    'menu:quality_cases': 'Quality Cases',
    'menu:instruction': 'Инструкция',
    'menu:diagnostics': 'Диагностика',
    'menu:logs': 'Логи',
    'menu:ai': 'AI',
    'menu:access': 'Доступы'
  }[action] || 'Готово';
  if (callbackId) await answerChannelCallback({ channel, token, callbackId, text: callbackText });

  if (action === 'menu:new_requests') {
    const items = masterService.listRequestsByStatus('new');
    await respondWithMessage({ channel, token, recipientId, text: items.map(formatRequestLine).join('\n') || 'Нет новых заявок', extra: { reply_markup: buildMainMenuKeyboard(actor) } });
    for (const item of items.slice(0, 10)) {
      const card = masterService.getRequestCard(item.id) || { request: item };
      await sendChannelMessage({ channel, token, recipientId, text: buildRequestCardText(card), extra: { reply_markup: buildRequestActionsKeyboard(item.id, card, actor) } });
    }
    return { ok: true, items, action };
  }
  if (action === 'menu:in_progress') {
    const items = masterService.listActiveRequests();
    await respondWithMessage({ channel, token, recipientId, text: items.map(formatRequestLine).join('\n') || 'Нет заявок в работе', extra: { reply_markup: buildMainMenuKeyboard(actor) } });
    for (const item of items.slice(0, 10)) {
      const card = masterService.getRequestCard(item.id) || { request: item };
      await sendChannelMessage({ channel, token, recipientId, text: buildRequestCardText(card), extra: { reply_markup: buildRequestActionsKeyboard(item.id, card, actor) } });
    }
    return { ok: true, items, action };
  }
  if (action === 'menu:archive') {
    const items = masterService.listArchiveRequests();
    await respondWithMessage({ channel, token, recipientId, text: items.map(formatRequestLine).join('\n') || 'Архив пуст', extra: { reply_markup: buildMainMenuKeyboard(actor) } });
    for (const item of items.slice(0, 10)) {
      const card = masterService.getRequestCard(item.id) || { request: item };
      await sendChannelMessage({ channel, token, recipientId, text: buildRequestCardText(card), extra: { reply_markup: buildRequestActionsKeyboard(item.id, card, actor) } });
    }
    return { ok: true, items, action };
  }
  if (action === 'menu:search') {
    sessions.set(sessionKey, { step: 'search_query' });
    return respondWithMessage({ channel, token, recipientId, text: 'Введите строку для поиска (ФИО, телефон, VIN или номер).', payload: { ok: true, action } });
  }
  if (action === 'menu:quality_cases') {
    const items = masterService.listQualityCases();
    return respondWithMessage({ channel, token, recipientId, text: qualityCasesText(items), payload: { ok: true, items, action }, extra: { reply_markup: buildMainMenuKeyboard(actor) } });
  }
  if (action === 'menu:instruction') {
    return respondWithMessage({ channel, token, recipientId, text: helpText(channel), payload: { ok: true, action }, extra: { reply_markup: buildMainMenuKeyboard(actor) } });
  }
  if (action === 'menu:diagnostics') {
    if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED', action } });
    return respondWithMessage({ channel, token, recipientId, text: buildDiagnosticsText({ config, actor, channel, detailed: false, aiInfrastructure }), payload: { ok: true, action }, extra: { reply_markup: { inline_keyboard: [[{ text: 'обновить', callback_data: 'admin:diagnostics' }, { text: 'прогнать проверку', callback_data: 'admin:diagnostics' }], [{ text: 'краткий статус', callback_data: 'admin:diagnostics_short' }, { text: 'подробный статус', callback_data: 'admin:diagnostics_detailed' }]] } } });
  }
  if (action === 'menu:logs') {
    if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED', action } });
    sessions.set(sessionKey, { step: 'logs_filter' });
    return respondWithMessage({ channel, token, recipientId, text: 'Введите фильтр логов в формате request:<id> type:<type> bot:<bot> since:YYYY-MM-DD', payload: { ok: true, action } });
  }
  if (action === 'menu:ai') {
    if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED', action } });
    return respondWithMessage({ channel, token, recipientId, text: 'AI control plane', payload: { ok: true, action }, extra: { reply_markup: buildAiMenuKeyboard() } });
  }
  if (action === 'menu:access') {
    if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED', action } });
    return respondWithMessage({ channel, token, recipientId, text: `Раздел доступов:
/access_list
/access_grant <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager> [ФИО]
/access_revoke <${channel === 'max' ? 'maxId' : 'telegramId'}>`, payload: { ok: true, action }, extra: { reply_markup: buildMainMenuKeyboard(actor) } });
  }
  return { ok: false, error: 'UNKNOWN_MENU_ACTION', action };
}

function recordLegacyCallback({ requestId, actor, channel, legacyAction, mappedAction }) {
  db.recordRequestEvent({
    requestId,
    eventType: 'comment_added',
    actorId: actor.id,
    actorRole: actor.role,
    actorType: actor.role,
    comment: 'legacy_callback_used',
    metaJson: { event: 'legacy_callback_used', channel, legacyAction, mappedAction }
  });
  db.createAnalyticsEvent({
    eventType: 'status_changed',
    channel,
    platform: channel,
    requestId,
    status: 'legacy_callback_used',
    metaJson: { event: 'legacy_callback_used', legacyAction, mappedAction, actorId: actor.id }
  });
}

function buildHistoryText(card) {
  return `История заявки ${card.request.id}:\n${buildHistoryLines(card)}`;
}

async function handleMasterWebhook({ body, config, headers = {}, rawHeaders = [], pathname = '', method = 'POST', channel = 'telegram', aiInfrastructure = null }) {
  if (channel === 'max') {
    const bodyKeys = body && typeof body === 'object' && !Array.isArray(body) ? Object.keys(body).sort() : [];
    logger.info('master_bot MAX webhook route hit', { channel, pathname, method: String(method || '').toUpperCase(), bodyPresent: Boolean(body), bodyKeys });
    db.createAnalyticsEvent({ eventType: 'max_webhook_received', channel: 'max', platform: 'max', status: 'received', metaJson: { route: 'master_bot', pathname, method: String(method || '').toUpperCase(), bodyKeys } });
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
    logger.info('master_bot webhook parsed update', { channel, pathname, method, updateType, senderBlock, text: String(event.callback ? event.callback.data || '' : event.text || '').slice(0, 500), rawSummary: channel === 'max' ? event.rawSummary : undefined });
    if (!event.message && !event.callback) {
      logger.warn('master_bot unknown update without message/callback', { channel, pathname, method, reason: 'NO_MESSAGE_AND_NO_CALLBACK', rawSummary: channel === 'max' ? event.rawSummary : undefined, body });
      return { ok: true, action: 'ignored_unknown_update', updateType };
    }

    const token = masterToken(config, channel);
    const masterService = createMasterService({ db, sendClientMessage: sendChannelMessage, adminIds: adminIds(config, channel), actorChannel: channel });
    const reportingService = createReportingService({ db });
    const channelUserId = event.callback?.userId || event.userId;
    const fullName = event.callback?.fullName || event.fullName;
    const actor = masterService.resolveActor({ channelUserId, telegramId: channel === 'telegram' ? channelUserId : null, maxId: channel === 'max' ? channelUserId : null, fullName });
    const recipientId = resolveRecipientId(channel, channelUserId, event.callback?.chatId || event.chatId);
    const sessionKey = `${channel}:${channelUserId}`;
    const rawText = String(event.text || '').trim();
    const text = MENU_TEXT_TO_ACTION[rawText] || rawText;

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
      if (data.startsWith('menu:')) {
        return handleMenuAction({ action: data, actor, channel, token, recipientId, masterService, config, sessionKey, callbackId: event.callback.id, aiInfrastructure });
      }
      if (data.startsWith('card:')) {
        const requestId = data.split(':')[1];
        const card = masterService.getRequestCard(requestId);
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: card ? 'Открываю карточку' : 'Заявка не найдена' });
        if (!card) return { ok: false, error: 'REQUEST_NOT_FOUND' };
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(requestId, card, actor) } });
      }
      if (data.startsWith('history:')) {
        const requestId = data.split(':')[1];
        const card = masterService.getRequestCard(requestId);
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: card ? 'История готова' : 'Заявка не найдена' });
        if (!card) return { ok: false, error: 'REQUEST_NOT_FOUND' };
        return respondWithMessage({ channel, token, recipientId, text: buildHistoryText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(requestId, card, actor) } });
      }
      if (data.startsWith('logs:')) {
        if (!isAdmin(actor)) {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Недостаточно прав' });
          return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
        }
        const requestId = data.split(':')[1];
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Логи готовы' });
        return respondWithMessage({ channel, token, recipientId, text: buildLogsText({ request: requestId }, true), payload: { ok: true, requestId } });
      }
      if (data === 'admin:diagnostics' || data === 'admin:diagnostics_short') {
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Готово' });
        return respondWithMessage({ channel, token, recipientId, text: buildDiagnosticsText({ config, actor, channel, detailed: false, aiInfrastructure }), payload: { ok: true } });
      }
      if (data === 'admin:diagnostics_detailed') {
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Подробно' });
        return respondWithMessage({ channel, token, recipientId, text: buildDiagnosticsText({ config, actor, channel, detailed: true, aiInfrastructure }), payload: { ok: true } });
      }
      if (data === 'admin:logs' || data === 'admin:logs_short' || data === 'admin:logs_detailed') {
        sessions.set(sessionKey, { step: 'logs_filter', detailed: data === 'admin:logs_detailed' });
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите фильтр' });
        return respondWithMessage({ channel, token, recipientId, text: 'Введите фильтр логов в формате request:<id> type:<type> bot:<bot> since:YYYY-MM-DD' });
      }

      if (data.startsWith('ai:')) {
        if (!isAdmin(actor)) {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Недостаточно прав' });
          return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
        }
        if (!aiInfrastructure) {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'AI infra missing' });
          return respondWithMessage({ channel, token, recipientId, text: 'AI infrastructure unavailable', payload: { ok: false, error: 'AI_INFRA_UNAVAILABLE' } });
        }
        if (data === 'ai:status') {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'AI статус' });
          return respondWithMessage({ channel, token, recipientId, text: buildAiStatusText({ aiInfrastructure, config }), payload: { ok: true }, extra: { reply_markup: buildAiMenuKeyboard() } });
        }
        if (data === 'ai:diagnostics') {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'AI диагностика...' });
          const result = await aiInfrastructure.runDiagnostics();
          return respondWithMessage({ channel, token, recipientId, text: `${result.ok ? '✅' : '❌'} ${result.probe.summary}
provider=${result.probe.state.provider || '-'} model=${result.probe.state.model || '-'} fallback=${result.probe.state.fallbackUsed ? 'yes' : 'no'} duration=${result.probe.state.durationMs}ms`, payload: { ok: result.ok, diagnostics: result }, extra: { reply_markup: buildAiMenuKeyboard() } });
        }
        if (data === 'ai:switch') {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите /ai_switch ...' });
          sessions.set(sessionKey, { step: 'ai_switch' });
          return respondWithMessage({ channel, token, recipientId, text: 'Формат: /ai_switch provider:<name> model:<name> fallbackProvider:<name> fallbackModel:<name>' });
        }
        if (data === 'ai:logs') {
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'AI логи' });
          sessions.set(sessionKey, { step: 'ai_logs_filter' });
          return respondWithMessage({ channel, token, recipientId, text: 'Введите фильтр: since:YYYY-MM-DD provider:proxy status:success task:classifyIntent' });
        }
      }
      if (data.startsWith('req:')) {
        const [, requestId, rawAction, maybeSubstatus] = data.split(':');
        const legacyMapping = LEGACY_CALLBACK_MAP[rawAction] || null;
        const action = legacyMapping?.action || rawAction;
        if (legacyMapping) {
          recordLegacyCallback({ requestId, actor, channel, legacyAction: rawAction, mappedAction: action });
        }
        if (action === 'refresh_only') {
          const card = masterService.getRequestCard(requestId);
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Карточка обновлена' });
          if (!card) return { ok: false, error: 'REQUEST_NOT_FOUND' };
          return respondWithMessage({ channel, token, recipientId, text: `Карточка обновлена\n\n${buildRequestCardText(card)}`, payload: { ok: true, legacy: true, requestId }, extra: { reply_markup: buildRequestActionsKeyboard(requestId, card, actor) } });
        }
        if (action === 'rejected_only') {
          sessions.set(sessionKey, { step: 'rejected_comment', requestId, substatus: 'rejected' });
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Используйте отказ' });
          return respondWithMessage({ channel, token, recipientId, text: `Старая кнопка отключена. Карточка обновлена.\nУкажите комментарий для отказа по заявке ${requestId}` });
        }
        if (action === 'ask_client') {
          sessions.set(sessionKey, { step: 'ask_client', requestId });
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите сообщение' });
          return respondWithMessage({ channel, token, recipientId, text: `Введите сообщение клиенту по заявке ${requestId}` });
        }
        if (action === 'comment') {
          sessions.set(sessionKey, { step: 'comment', requestId });
          await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите комментарий' });
          return respondWithMessage({ channel, token, recipientId, text: `Введите внутренний комментарий по заявке ${requestId}` });
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
          if (result?.error && legacyMapping) {
            const card = masterService.getRequestCard(requestId);
            return respondWithMessage({ channel, token, recipientId, text: `Старая кнопка больше неактуальна. Карточка обновлена.\n\n${buildRequestCardText(card)}`, payload: { ok: true, legacy: true, requestId }, extra: { reply_markup: buildRequestActionsKeyboard(requestId, card, actor) } });
          }
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
        if (legacyMapping && result?.error === 'INVALID_TRANSITION') {
          const card = masterService.getRequestCard(requestId);
          return respondWithMessage({ channel, token, recipientId, text: `Карточка обновлена\n\n${buildRequestCardText(card)}`, payload: { ok: true, legacy: true, requestId }, extra: { reply_markup: buildRequestActionsKeyboard(requestId, card, actor) } });
        }
        return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус заявки ${requestId}: ${action}`, payload: { ok: !result?.error, ...result } });
      }
    }

    if (text === '/start') {
      db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: { channel } });
      return respondWithMessage({ channel, token, recipientId, text: `Master Bot запущен. Роль: ${actor.role}.`, payload: { ok: true, action: 'start' }, extra: { reply_markup: buildMainMenuKeyboard(actor) } });
    }

    if (String(text).startsWith('menu:')) {
      return handleMenuAction({ action: text, actor, channel, token, recipientId, masterService, config, sessionKey, aiInfrastructure });
    }

    if (text === '/diagnostics') {
      return handleMenuAction({ action: 'menu:diagnostics', actor, channel, token, recipientId, masterService, config, sessionKey, aiInfrastructure });
    }
    if (text === 'Логи' || text.startsWith('/logs')) {
      if (text === 'Логи') return handleMenuAction({ action: 'menu:logs', actor, channel, token, recipientId, masterService, config, sessionKey, aiInfrastructure });
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
      const filters = parseLogsFilter(text.replace('/logs', '').trim());
      return respondWithMessage({
        channel,
        token,
        recipientId,
        text: buildLogsText(filters, false),
        payload: { ok: true, filters },
        extra: { reply_markup: { inline_keyboard: [[{ text: 'кратко', callback_data: 'admin:logs_short' }, { text: 'подробно', callback_data: 'admin:logs_detailed' }]] } }
      });
    }

    if (text === '/ai_status') {
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
      return respondWithMessage({ channel, token, recipientId, text: buildAiStatusText({ aiInfrastructure, config }), payload: { ok: true }, extra: { reply_markup: buildAiMenuKeyboard() } });
    }
    if (text === '/ai_diagnostics') {
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
      const result = await aiInfrastructure.runDiagnostics();
      return respondWithMessage({ channel, token, recipientId, text: `${result.ok ? '✅' : '❌'} ${result.probe.summary}` , payload: { ok: result.ok, diagnostics: result }, extra: { reply_markup: buildAiMenuKeyboard() } });
    }
    if (text.startsWith('/ai_logs')) {
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
      const filters = parseLogsFilter(text.replace('/ai_logs', '').trim());
      return respondWithMessage({ channel, token, recipientId, text: buildAiLogsText(aiInfrastructure, filters), payload: { ok: true, filters }, extra: { reply_markup: buildAiMenuKeyboard() } });
    }
    if (text.startsWith('/ai_switch')) {
      if (!isAdmin(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.', payload: { ok: false, error: 'ACCESS_DENIED' } });
      const payload = parseAiSwitchCommand(text) || {};
      const patch = Object.fromEntries(Object.entries(payload).filter(([, v]) => Boolean(v)));
      const updated = aiInfrastructure.runtimeSettings.update(patch);
      return respondWithMessage({ channel, token, recipientId, text: updated.ok ? 'AI runtime settings updated' : `Ошибка: ${updated.error}`, payload: updated, extra: { reply_markup: buildAiMenuKeyboard() } });
    }

    if (text === '/quality_cases') {
      return handleMenuAction({ action: 'menu:quality_cases', actor, channel, token, recipientId, masterService, config, sessionKey, aiInfrastructure });
    }

    const session = sessions.get(sessionKey);
    if (session?.step === 'search_query') {
      sessions.delete(sessionKey);
      const results = masterService.search(text);
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, action: 'search_results', card, ...results }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id, card, actor) } });
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
    if (session?.step === 'comment') {
      sessions.delete(sessionKey);
      const comment = masterService.addInternalComment({ requestId: session.requestId, actorId: actor.id, actorRole: actor.role, text });
      return comment
        ? respondWithMessage({ channel, token, recipientId, text: 'Комментарий добавлен', payload: { ok: true, comment } })
        : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }
    if (session?.step === 'logs_filter') {
      sessions.delete(sessionKey);
      return respondWithMessage({ channel, token, recipientId, text: buildLogsText(parseLogsFilter(text), Boolean(session.detailed)), payload: { ok: true } });
    }


    if (session?.step === 'ai_logs_filter') {
      sessions.delete(sessionKey);
      return respondWithMessage({ channel, token, recipientId, text: buildAiLogsText(aiInfrastructure, parseLogsFilter(text)), payload: { ok: true } });
    }
    if (session?.step === 'ai_switch') {
      sessions.delete(sessionKey);
      const payload = parseAiSwitchCommand(text) || {};
      const patch = Object.fromEntries(Object.entries(payload).filter(([, v]) => Boolean(v)));
      const updated = aiInfrastructure.runtimeSettings.update(patch);
      return respondWithMessage({ channel, token, recipientId, text: updated.ok ? 'AI runtime settings updated' : `Ошибка: ${updated.error}`, payload: updated, extra: { reply_markup: buildAiMenuKeyboard() } });
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
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, ...results, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id, card, actor) } });
      }
      return respondWithMessage({ channel, token, recipientId, text: 'Ничего не найдено', payload: { ok: true, ...results } });
    }
    if (text.startsWith('/client ')) {
      const card = masterService.getClientCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'CLIENT_NOT_FOUND' };
    }

    if (text.startsWith('/request ')) {
      const card = masterService.getRequestCard(text.split(' ')[1]);
      return card ? respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id, card, actor) } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
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
