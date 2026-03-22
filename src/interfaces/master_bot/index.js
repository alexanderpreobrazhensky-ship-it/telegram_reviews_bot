const db = require('../../infrastructure/db');
const { createMasterService, createReportingService } = require('../../core/application');
const logger = require('../../infrastructure/logging/logger');
const { sendChannelMessage, answerChannelCallback } = require('../../infrastructure/messaging');
const { extractIncomingEvent } = require('../shared/channelAdapters');
const { validateMaxWebhookRequest } = require('../shared/maxSecurity');
const { REQUEST_STATUSES } = require('../../core/shared/requestValidation');

const sessions = new Map();

function canUseReports(actor) {
  return actor?.role === 'manager' || actor?.role === 'admin';
}

function canManageAccess(actor) {
  return actor?.role === 'manager' || actor?.role === 'admin';
}

function formatRequestLine(request) {
  return `${request.id} | ${request.requestType} | ${request.status} | ${request.description || '-'}`;
}

function buildRequestActionsKeyboard(requestId) {
  return {
    inline_keyboard: [
      [
        { text: 'Назначить', callback_data: `req:${requestId}:assigned` },
        { text: 'Ждём клиента', callback_data: `req:${requestId}:awaiting_client` }
      ],
      [
        { text: 'Запланировать', callback_data: `req:${requestId}:scheduled` },
        { text: 'В сервисе', callback_data: `req:${requestId}:in_service` }
      ],
      [
        { text: 'Завершить', callback_data: `req:${requestId}:done` },
        { text: 'Отменить', callback_data: `req:${requestId}:cancelled` }
      ],
      [
        { text: 'Комментарий', callback_data: `req:${requestId}:comment` }
      ],
      [{ text: 'Подробнее', callback_data: `card:${requestId}` }]
    ]
  };
}

function buildRequestCardText(card) {
  const r = card.request;
  const client = card.client || {};
  const vehicle = card.vehicle || {};
  const history = (card.requestEvents || [])
    .slice(-10)
    .map((event) => `${event.createdAt}: ${event.canonicalEventType || event.eventType} ${event.oldValue || event.oldStatus || '-'} -> ${event.newValue || event.newStatus || '-'}${event.comment ? ` (${event.comment})` : ''}`)
    .join('\n') || 'Нет истории';
  return [
    `ID: ${r.id}`,
    `Тип: ${r.requestType}`,
    `Статус: ${r.status}`,
    `ФИО: ${client.fullName || '-'}`,
    `Телефон: ${client.phone || '-'}`,
    `Telegram ID: ${client.telegramId || '-'}`,
    `MAX ID: ${client.maxId || '-'}`,
    `Был ранее: ${r.payload?.wasClientBefore || '-'}`,
    `VIN: ${vehicle.vin || '-'}`,
    `Автомобиль: ${r.payload?.car || '-'}`,
    `Марка/модель: ${vehicle.brand || '-'} / ${vehicle.model || '-'}`,
    `Год: ${vehicle.year || '-'}`,
    `Описание: ${r.description || '-'}`,
    `Источник: ${r.sourceChannel || '-'}`,
    `Назначено: ${r.assignedTo || r.assignedMasterId || '-'}`,
    `Назначил: ${r.assignedBy || '-'}`,
    `Когда назначено: ${r.assignedAt || '-'}`,
    `Создано: ${r.createdAt || '-'}`,
    `Клиент ID: ${r.clientId || '-'}`,
    `Авто ID: ${r.vehicleId || '-'}`,
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
    '/start',
    '/help',
    '/whoami',
    '/search <query>',
    '/request <id>',
    `/set_status <requestId> <${REQUEST_STATUSES.join('|')}> [reason]`,
    '/comment <requestId> <text>',
    '/ask_client <requestId> <text>',
    `/access_grant <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager> [ФИО]`,
    `/access_revoke <${channel === 'max' ? 'maxId' : 'telegramId'}>`
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
    if (!delivered) {
      logger.error('master_bot outbound sendMessage failed', { channel, recipientId, textPreview: String(text || '').slice(0, 200) });
    }
  }
  return text ? { ...payload, text } : payload;
}

async function handleMasterWebhook({ body, config, headers = {}, rawHeaders = [], pathname = '', method = 'POST', channel = 'telegram' }) {
  if (channel === 'max') {
    db.createAnalyticsEvent({
      eventType: 'max_webhook_received',
      channel: 'max',
      platform: 'max',
      status: 'received',
      metaJson: { route: 'master_bot', pathname, method }
    });
    const validation = validateMaxWebhookRequest({
      config,
      headers,
      rawHeaders,
      pathname,
      method,
      logger,
      routeLabel: 'master_bot',
      token: masterToken(config, channel),
      body
    });
    if (!validation.ok) {
      db.createAnalyticsEvent({
        eventType: 'max_webhook_rejected',
        channel: 'max',
        platform: 'max',
        status: validation.error,
        metaJson: { route: 'master_bot', pathname, method, statusCode: validation.statusCode }
      });
      return { ok: false, error: validation.error, statusCode: validation.statusCode };
    }
  }

  try {
    const event = extractIncomingEvent({ body, channel });
    const updateType = event.callback ? 'callback' : (event.message ? 'message' : 'unknown');
    const senderBlock = buildSenderSnapshot({ body, event });
    logger.info('master_bot webhook parsed update', {
      channel,
      pathname,
      method,
      updateType,
      hasMessage: Boolean(event.message),
      hasSender: Boolean(event.message?.from || body?.sender || body?.user || event.callback),
      senderBlock,
      userId: event.callback?.userId || event.userId || null,
      text: String(event.callback ? event.callback.data || '' : event.text || '').slice(0, 500)
    });
    if (!event.message && !event.callback) {
      logger.warn('master_bot unknown update without message/callback', {
        channel,
        pathname,
        method,
        reason: 'NO_MESSAGE_AND_NO_CALLBACK',
        body
      });
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
    const text = String(event.text || '').trim();

    if (text === '/whoami') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/whoami', channelUserId, recipientId });
      return respondWithMessage({
        channel,
        token,
        recipientId,
        text: [
          `Identity: ${actor?.id || channelUserId || '-'}`,
          `Role: ${actor?.role || 'unknown'}`,
          `Channel: ${channel}`,
          `Channel user id: ${channelUserId || '-'}`,
          `Name: ${actor?.fullName || fullName || '-'}`
        ].join('\n'),
        payload: { ok: true, action: 'whoami', channelUserId, channel, actor }
      });
    }

    if (!actor) {
      logger.warn('master_bot access denied', {
        channel,
        pathname,
        reason: 'ACTOR_NOT_FOUND_OR_NOT_ALLOWED',
        channelUserId,
        recipientId,
        configuredAdminIds: adminIds(config, channel)
      });
      if (recipientId) {
        await respondWithMessage({
          channel,
          token,
          recipientId,
          text: `Доступ запрещён: user_id ${channelUserId || '-'} не найден в staff/admin. Используйте /whoami и добавьте ID в MAX_MASTER_BOT_ADMIN_IDS или выдайте доступ через /access_grant.`,
          payload: { ok: false, error: 'ACCESS_DENIED', channelUserId, reason: 'ACTOR_NOT_FOUND_OR_NOT_ALLOWED' }
        });
      }
      return { ok: false, error: 'ACCESS_DENIED', channelUserId, reason: 'ACTOR_NOT_FOUND_OR_NOT_ALLOWED' };
    }

    if (event.callback?.id) {
      const data = String(event.callback.data || '');
      logger.info('master_bot callback received', { channel, pathname, channelUserId, recipientId, data });
      if (data.startsWith('card:')) {
        const requestId = data.split(':')[1];
        const card = masterService.getRequestCard(requestId);
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: card ? 'Открываю карточку' : 'Заявка не найдена' });
        if (!card) return { ok: false, error: 'REQUEST_NOT_FOUND' };
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(requestId) } });
      }
      if (data.startsWith('req:')) {
        const [, requestId, toStatus] = data.split(':');
        if (toStatus === 'comment') {
          sessions.set(sessionKey, { step: 'request_comment', requestId });
          const answered = await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите комментарий' });
          if (!answered) logger.error('master_bot callback answer failed', { channel, callbackId: event.callback.id, recipientId });
          return respondWithMessage({ channel, token, recipientId, text: `Введите внутренний комментарий по заявке ${requestId}` });
        }
        if (toStatus === 'cancelled') {
          sessions.set(sessionKey, { step: 'cancel_comment', requestId });
          const answered = await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Укажите комментарий' });
          if (!answered) logger.error('master_bot callback answer failed', { channel, callbackId: event.callback.id, recipientId });
          return respondWithMessage({ channel, token, recipientId, text: `Укажите комментарий для отмены заявки ${requestId}` });
        }
        if (toStatus === 'assigned') {
          masterService.assignRequest({
            requestId,
            assignedTo: actor.id,
            assignedBy: actor.id,
            actorId: actor.id,
            actorRole: actor.role,
            actorType: actor.role,
            metaJson: { channel }
          });
        }
        const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role });
        if (!result?.error && toStatus === 'awaiting_client') {
          await masterService.requestClientClarification({
            requestId,
            actorId: actor.id,
            actorRole: actor.role,
            text: 'Пожалуйста, уточните недостающие данные по вашему обращению.',
            telegramClientBotToken: config.telegramClientBotToken,
            maxClientBotToken: config.maxClientBotToken
          });
        }
        const answered = await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: result?.error ? 'Ошибка' : 'Готово' });
        if (!answered) logger.error('master_bot callback answer failed', { channel, callbackId: event.callback.id, recipientId });
        return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус заявки ${requestId}: ${toStatus}`, payload: { ok: !result?.error, ...result } });
      }
    }

    logger.info('master_bot incoming text', { channel, channelUserId, recipientId, text });
    if (text === '/start') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/start', channelUserId, recipientId, actorRole: actor.role });
      const baseKeyboard = [['Новые заявки', 'В работе'], ['Поиск', 'Quality Cases'], ['/help']];
      if (canManageAccess(actor)) baseKeyboard.push(['Доступы']);
      await sendChannelMessage({ channel, token, recipientId, text: `Master Bot запущен. Роль: ${actor.role}.`, extra: { reply_markup: { keyboard: baseKeyboard, resize_keyboard: true } } });
      db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: { channel } });
      return { ok: true, action: 'start' };
    }

    if (text === '/help') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/help', channelUserId, recipientId, actorRole: actor.role });
      return respondWithMessage({ channel, token, recipientId, text: helpText(channel), payload: { ok: true, action: 'help' } });
    }

    if (text === 'Новые заявки' || text === 'В работе') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: text, channelUserId, recipientId, actorRole: actor.role });
      const items = text === 'Новые заявки'
        ? masterService.listRequestsByStatus('new')
        : db.listRequests({ statuses: ['assigned', 'awaiting_client', 'scheduled', 'in_service'] });
      const lines = items.map(formatRequestLine);
      await respondWithMessage({ channel, token, recipientId, text: lines.join('\n') || (text === 'Новые заявки' ? 'Нет новых заявок' : 'Нет заявок в работе') });
      for (const item of items.slice(0, 10)) {
        await sendChannelMessage({ channel, token, recipientId, text: `Заявка ${item.id}`, extra: { reply_markup: buildRequestActionsKeyboard(item.id) } });
      }
      return { ok: true, items };
    }

    if (text === 'Поиск') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: 'Поиск', channelUserId, recipientId, actorRole: actor.role });
      sessions.set(sessionKey, { step: 'search_query' });
      return respondWithMessage({ channel, token, recipientId, text: 'Введите строку для поиска (ФИО, телефон, VIN или номер).' });
    }

    if (text === 'Доступы') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: 'Доступы', channelUserId, recipientId, actorRole: actor.role });
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      sessions.set(sessionKey, { step: 'access_menu' });
      return respondWithMessage({ channel, token, recipientId, text: `Раздел доступов:\n/access_list\n/access_grant <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager> [ФИО]\n/access_revoke <${channel === 'max' ? 'maxId' : 'telegramId'}>\n/access_role <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager>` });
    }

    if (text === 'Quality Cases' || text === '/quality_cases') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: 'quality_cases', channelUserId, recipientId, actorRole: actor.role });
      const items = masterService.listQualityCases();
      return respondWithMessage({ channel, token, recipientId, text: qualityCasesText(items), payload: { ok: true, items } });
    }

    const session = sessions.get(sessionKey);
    if (session?.step === 'search_query') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: 'search_query', channelUserId, recipientId, actorRole: actor.role });
      sessions.delete(sessionKey);
      const results = masterService.search(text);
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, action: 'search_results', card, ...results }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } });
      }
      return respondWithMessage({ channel, token, recipientId, text: 'Ничего не найдено', payload: { ok: true, action: 'search_results', ...results } });
    }

    if (session?.step === 'cancel_comment') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: 'cancel_comment', channelUserId, recipientId, actorRole: actor.role });
      sessions.delete(sessionKey);
      const result = masterService.changeRequestStatus({ requestId: session.requestId, toStatus: 'cancelled', actorId: actor.id, actorRole: actor.role, comment: text });
      return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Заявка ${session.requestId} отменена`, payload: { ok: !result?.error, ...result } });
    }

    if (session?.step === 'request_comment') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: 'request_comment', channelUserId, recipientId, actorRole: actor.role });
      sessions.delete(sessionKey);
      const comment = masterService.addInternalComment({ requestId: session.requestId, actorId: actor.id, actorRole: actor.role, text });
      return comment ? respondWithMessage({ channel, token, recipientId, text: 'Комментарий добавлен', payload: { ok: true, comment } }) : respondWithMessage({ channel, token, recipientId, text: 'Заявка не найдена', payload: { ok: false } });
    }

    if (text.startsWith('/access_list')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/access_list', channelUserId, recipientId, actorRole: actor.role });
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const items = masterService.listStaffUsers();
      return respondWithMessage({ channel, token, recipientId, text: items.map((u) => `${staffIdentity(u)} | ${u.role} | ${u.fullName || '-'}`).join('\n') || 'Список пуст', payload: { ok: true, items } });
    }

    if (text.startsWith('/access_grant ') || text.startsWith('/access_role ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: text.startsWith('/access_grant ') ? '/access_grant' : '/access_role', channelUserId, recipientId, actorRole: actor.role });
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const [, externalId, role, ...nameParts] = text.split(' ');
      const result = masterService.grantStaffAccess({ channelUserId: externalId, telegramId: channel === 'telegram' ? externalId : null, maxId: channel === 'max' ? externalId : null, fullName: nameParts.join(' ').trim(), role, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : `Доступ обновлён: ${externalId} -> ${role}`, payload: { ok: !result.error, ...result } });
    }

    if (text.startsWith('/access_revoke ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/access_revoke', channelUserId, recipientId, actorRole: actor.role });
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      const [, externalId] = text.split(' ');
      const result = masterService.revokeStaffAccess({ channelUserId: externalId, telegramId: channel === 'telegram' ? externalId : null, maxId: channel === 'max' ? externalId : null, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : `Доступ отозван: ${externalId}`, payload: { ok: !result.error, ...result } });
    }

    if (text.startsWith('/search ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/search', channelUserId, recipientId, actorRole: actor.role });
      const results = masterService.search(text.slice(8));
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, ...results, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } });
      }
      return respondWithMessage({ channel, token, recipientId, text: 'Ничего не найдено', payload: { ok: true, ...results } });
    }

    if (text.startsWith('/client ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/client', channelUserId, recipientId, actorRole: actor.role });
      const card = masterService.getClientCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'CLIENT_NOT_FOUND' };
    }

    if (text.startsWith('/request ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/request', channelUserId, recipientId, actorRole: actor.role });
      const card = masterService.getRequestCard(text.split(' ')[1]);
      return card ? respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }

    if (text.startsWith('/set_status ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/set_status', channelUserId, recipientId, actorRole: actor.role });
      const [, requestId, toStatus, ...reasonParts] = text.split(' ');
      const comment = reasonParts.join(' ');
      const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role, comment, lostReason: comment });
      return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус обновлён: ${toStatus}`, payload: { ok: !result?.error, ...result } });
    }

    if (text.startsWith('/comment ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/comment', channelUserId, recipientId, actorRole: actor.role });
      const [, requestId, ...commentParts] = text.split(' ');
      const comment = masterService.addInternalComment({ requestId, actorId: actor.id, actorRole: actor.role, text: commentParts.join(' ') });
      return comment ? respondWithMessage({ channel, token, recipientId, text: 'Комментарий добавлен', payload: { ok: true, comment } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }

    if (text.startsWith('/ask_client ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/ask_client', channelUserId, recipientId, actorRole: actor.role });
      const [, requestId, ...textParts] = text.split(' ');
      const result = await masterService.requestClientClarification({ requestId, actorId: actor.id, actorRole: actor.role, text: textParts.join(' '), telegramClientBotToken: config.telegramClientBotToken, maxClientBotToken: config.maxClientBotToken });
      return respondWithMessage({ channel, token, recipientId, text: result.error ? `Ошибка: ${result.error}` : 'Запрос клиенту отправлен/зафиксирован', payload: result });
    }

    if (text === '/report_week' || text === '/report_month' || text === '/report_quarter' || text === '/report_stats') {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: text, channelUserId, recipientId, actorRole: actor.role });
      if (!canUseReports(actor)) {
        return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав для отчётов.', payload: { ok: false, error: 'REPORT_ACCESS_DENIED', allowedRoles: ['manager', 'admin'] } });
      }
      const periodMap = { '/report_week': 'weekly', '/report_month': 'monthly', '/report_quarter': 'quarterly', '/report_stats': 'weekly' };
      const report = reportingService.buildManagementSummary({ period: periodMap[text] });
      return respondWithMessage({ channel, token, recipientId, text: report.summaryText, payload: { ok: true, report } });
    }

    if (text.startsWith('/quality_case ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/quality_case', channelUserId, recipientId, actorRole: actor.role });
      const card = masterService.getQualityCaseCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }

    if (text.startsWith('/quality_status ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/quality_status', channelUserId, recipientId, actorRole: actor.role });
      const [, qualityCaseId, status] = text.split(' ');
      const qualityCase = masterService.changeQualityCaseStatus({ qualityCaseId, status, actorId: actor.id, actorRole: actor.role });
      return qualityCase ? { ok: true, qualityCase } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }

    if (text.startsWith('/quality_comment ')) {
      logger.info('master_bot handler branch selected', { channel, pathname, branch: '/quality_comment', channelUserId, recipientId, actorRole: actor.role });
      const [, qualityCaseId, ...parts] = text.split(' ');
      const comment = masterService.addQualityCaseComment({ qualityCaseId, actorId: actor.id, actorRole: actor.role, text: parts.join(' ') });
      return comment ? { ok: true, comment } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }

    logger.info('master_bot handler branch selected', { channel, pathname, branch: 'fallback', channelUserId, recipientId, actorRole: actor.role });
    return respondWithMessage({ channel, token, recipientId, text: 'Используйте /help для списка команд.', payload: { ok: true, action: 'fallback' } });
  } catch (error) {
    logger.error('master_bot handler error', { channel, pathname, method, error: String(error?.message || error), body });
    const fallbackUserId = String(
      body?.message?.from?.user_id || body?.message?.from?.id || body?.callback?.from?.user_id || body?.callback?.from?.id || body?.user?.user_id || body?.user?.id || ''
    );
    const fallbackChatId = body?.message?.chat_id || body?.message?.chat?.id || body?.callback?.message?.chat_id || body?.callback?.message?.chat?.id || null;
    const recipientId = resolveRecipientId(channel, fallbackUserId, fallbackChatId);
    if (recipientId) {
      await respondWithMessage({
        channel,
        token: masterToken(config, channel),
        recipientId,
        text: 'Внутренняя ошибка master bot.',
        payload: { ok: false, error: 'MASTER_BOT_ERROR' }
      });
    }
    return { ok: false, error: 'MASTER_BOT_ERROR', statusCode: 500 };
  }
}

module.exports = { registerMasterBotRoutes, handleMasterWebhook };
