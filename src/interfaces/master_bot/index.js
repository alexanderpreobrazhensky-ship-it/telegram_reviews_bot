const db = require('../../infrastructure/db');
const { createMasterService, createReportingService } = require('../../core/application');
const logger = require('../../infrastructure/logging/logger');
const { sendChannelMessage, answerChannelCallback } = require('../../infrastructure/messaging');
const { extractIncomingEvent } = require('../shared/channelAdapters');

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
        { text: 'Взять в работу', callback_data: `req:${requestId}:in_progress` },
        { text: 'Запросить данные', callback_data: `req:${requestId}:waiting_data` }
      ],
      [
        { text: 'Завершить', callback_data: `req:${requestId}:processed` },
        { text: 'Потеряно', callback_data: `req:${requestId}:lost` }
      ],
      [
        { text: 'Архивировать', callback_data: `req:${requestId}:archived` },
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
  const history = (card.statusHistory || []).map((h) => `${h.createdAt}: ${h.fromStatus} -> ${h.toStatus}`).join('\n') || 'Нет истории';
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
    '/search <query>',
    '/request <id>',
    '/set_status <requestId> <status> [reason]',
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

function registerMasterBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/master_bot/webhook', handler: (ctx) => handleMasterWebhook({ ...ctx, channel: 'telegram' }) });
  router.push({ method: 'POST', path: '/max/master_bot/webhook', handler: (ctx) => handleMasterWebhook({ ...ctx, channel: 'max' }) });
}

async function respondWithMessage({ channel, token, recipientId, text, payload = {}, extra = {} }) {
  if (text) await sendChannelMessage({ channel, token, recipientId, text, extra });
  return text ? { ...payload, text } : payload;
}

async function handleMasterWebhook({ body, config, headers = {}, channel = 'telegram' }) {
  if (channel === 'max' && config.maxWebhookSecret && headers['x-max-bot-api-secret'] !== config.maxWebhookSecret) {
    return { ok: false, error: 'INVALID_WEBHOOK_SECRET', statusCode: 403 };
  }

  const event = extractIncomingEvent({ body, channel });
  if (!event.message && !event.callback) return { ok: true };

  const token = masterToken(config, channel);
  const masterService = createMasterService({ db, sendClientMessage: sendChannelMessage, adminIds: adminIds(config, channel), actorChannel: channel });
  const reportingService = createReportingService({ db });
  const channelUserId = event.callback?.userId || event.userId;
  const fullName = event.callback?.fullName || event.fullName;
  const actor = masterService.resolveActor({ channelUserId, telegramId: channel === 'telegram' ? channelUserId : null, maxId: channel === 'max' ? channelUserId : null, fullName });
  const recipientId = event.callback?.chatId || event.chatId || channelUserId;
  const sessionKey = `${channel}:${channelUserId}`;

  if (!actor) {
    if (recipientId) await sendChannelMessage({ channel, token, recipientId, text: 'Доступ запрещён. Обратитесь к администратору.' });
    return { ok: false, error: 'ACCESS_DENIED' };
  }

  if (event.callback?.id) {
    const data = String(event.callback.data || '');
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
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Введите комментарий' });
        return respondWithMessage({ channel, token, recipientId, text: `Введите внутренний комментарий по заявке ${requestId}` });
      }
      if (toStatus === 'lost') {
        sessions.set(sessionKey, { step: 'lost_reason', requestId });
        await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: 'Укажите причину' });
        return respondWithMessage({ channel, token, recipientId, text: `Укажите причину для статуса "Потеряно" по заявке ${requestId}` });
      }
      const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role });
      if (!result?.error && toStatus === 'waiting_data') {
        await masterService.requestClientClarification({
          requestId,
          actorId: actor.id,
          actorRole: actor.role,
          text: 'Пожалуйста, уточните недостающие данные по вашему обращению.',
          telegramClientBotToken: config.telegramClientBotToken,
          maxClientBotToken: config.maxClientBotToken
        });
      }
      await answerChannelCallback({ channel, token, callbackId: event.callback.id, text: result?.error ? 'Ошибка' : 'Готово' });
      return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус заявки ${requestId}: ${toStatus}`, payload: { ok: !result?.error, ...result } });
    }
  }

  const text = String(event.text || '').trim();
  logger.info('master_bot incoming text', { channel, channelUserId, recipientId, text });
  try {
    if (text === '/start') {
      const baseKeyboard = [['Новые заявки', 'В работе'], ['Поиск', 'Quality Cases'], ['/help']];
      if (canManageAccess(actor)) baseKeyboard.push(['Доступы']);
      await sendChannelMessage({ channel, token, recipientId, text: `Master Bot запущен. Роль: ${actor.role}.`, extra: { reply_markup: { keyboard: baseKeyboard, resize_keyboard: true } } });
      db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: { channel } });
      return { ok: true, action: 'start' };
    }

    if (text === '/help') {
      return respondWithMessage({ channel, token, recipientId, text: helpText(channel), payload: { ok: true, action: 'help' } });
    }

    if (text === 'Новые заявки' || text === 'В работе') {
      const status = text === 'Новые заявки' ? 'new' : 'in_progress';
      const items = masterService.listRequestsByStatus(status);
      const lines = items.map(formatRequestLine);
      await respondWithMessage({ channel, token, recipientId, text: lines.join('\n') || (status === 'new' ? 'Нет новых заявок' : 'Нет заявок в работе') });
      for (const item of items.slice(0, 10)) {
        await sendChannelMessage({ channel, token, recipientId, text: `Заявка ${item.id}`, extra: { reply_markup: buildRequestActionsKeyboard(item.id) } });
      }
      return { ok: true, items };
    }

    if (text === 'Поиск') {
      sessions.set(sessionKey, { step: 'search_query' });
      return respondWithMessage({ channel, token, recipientId, text: 'Введите строку для поиска (ФИО, телефон, VIN или номер).' });
    }

    if (text === 'Доступы') {
      if (!canManageAccess(actor)) return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав.' });
      sessions.set(sessionKey, { step: 'access_menu' });
      return respondWithMessage({ channel, token, recipientId, text: `Раздел доступов:\n/access_list\n/access_grant <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager> [ФИО]\n/access_revoke <${channel === 'max' ? 'maxId' : 'telegramId'}>\n/access_role <${channel === 'max' ? 'maxId' : 'telegramId'}> <master|manager>` });
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
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, action: 'search_results', card, ...results }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } });
      }
      return respondWithMessage({ channel, token, recipientId, text: 'Ничего не найдено', payload: { ok: true, action: 'search_results', ...results } });
    }

    if (session?.step === 'lost_reason') {
      sessions.delete(sessionKey);
      const result = masterService.changeRequestStatus({ requestId: session.requestId, toStatus: 'lost', actorId: actor.id, actorRole: actor.role, lostReason: text });
      return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Заявка ${session.requestId} переведена в потерянные`, payload: { ok: !result?.error, ...result } });
    }

    if (session?.step === 'request_comment') {
      sessions.delete(sessionKey);
      const comment = masterService.addInternalComment({ requestId: session.requestId, actorId: actor.id, actorRole: actor.role, text });
      return comment ? respondWithMessage({ channel, token, recipientId, text: 'Комментарий добавлен', payload: { ok: true, comment } }) : respondWithMessage({ channel, token, recipientId, text: 'Заявка не найдена', payload: { ok: false } });
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
        return respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, ...results, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } });
      }
      return { ok: true, ...results };
    }

    if (text.startsWith('/client ')) {
      const card = masterService.getClientCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'CLIENT_NOT_FOUND' };
    }

    if (text.startsWith('/request ')) {
      const card = masterService.getRequestCard(text.split(' ')[1]);
      return card ? respondWithMessage({ channel, token, recipientId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }

    if (text.startsWith('/set_status ')) {
      const [, requestId, toStatus, ...reasonParts] = text.split(' ');
      const lostReason = reasonParts.join(' ');
      const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role, lostReason });
      return respondWithMessage({ channel, token, recipientId, text: result?.error ? `Ошибка: ${result.error}` : `Статус обновлён: ${toStatus}`, payload: { ok: !result?.error, ...result } });
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
      if (!canUseReports(actor)) {
        return respondWithMessage({ channel, token, recipientId, text: 'Недостаточно прав для отчётов.', payload: { ok: false, error: 'REPORT_ACCESS_DENIED', allowedRoles: ['manager', 'admin'] } });
      }
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
    logger.error('master_bot handler error', { channel, channelUserId, recipientId, text, error: String(error?.message || error) });
    return respondWithMessage({ channel, token, recipientId, text: 'Внутренняя ошибка master bot.', payload: { ok: false, error: 'MASTER_BOT_ERROR' } });
  }
}

module.exports = { registerMasterBotRoutes, handleMasterWebhook };
