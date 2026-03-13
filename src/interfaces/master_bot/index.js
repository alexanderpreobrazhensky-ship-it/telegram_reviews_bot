const db = require('../../infrastructure/db');
const { createMasterService, createReportingService } = require('../../core/application');
const logger = require('../../infrastructure/logging/logger');

const sessions = new Map();

async function sendTelegramMessage(token, chatId, text, extra = {}) {
  if (!token || !chatId) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, ...extra })
  }).catch(() => {});
}

async function answerCallbackQuery(token, callbackQueryId, text) {
  if (!token || !callbackQueryId) return;
  await fetch(`https://api.telegram.org/bot${token}/answerCallbackQuery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ callback_query_id: callbackQueryId, text })
  }).catch(() => {});
}

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

function registerMasterBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/master_bot/webhook', handler: handleMasterWebhook });
}

async function respondWithMessage({ token, chatId, text, payload = {}, extra = {} }) {
  if (text) await sendTelegramMessage(token, chatId, text, extra);
  return text ? { ...payload, text } : payload;
}

function qualityCasesText(items) {
  return items.map((item) => `${item.id} | ${item.status} | ${item.summary || '-'}`).join('\n') || 'Нет quality cases';
}

async function handleMasterWebhook({ body, config }) {
  const message = body?.message;
  const callbackQuery = body?.callback_query;
  const token = config.telegramMasterBotToken;
  const masterService = createMasterService({ db, sendClientMessage: sendTelegramMessage, adminTelegramIds: config.masterBotAdminIds });
  const reportingService = createReportingService({ db });

  if (!message && !callbackQuery) return { ok: true };

  const from = callbackQuery?.from || message?.from || {};
  const telegramId = String(from.id || '');
  const fullName = [from.first_name, from.last_name].filter(Boolean).join(' ').trim();
  const actor = masterService.resolveActor({ telegramId, fullName });
  const chatId = callbackQuery?.message?.chat?.id || message?.chat?.id;

  if (!actor) {
    if (chatId) await sendTelegramMessage(token, chatId, 'Доступ запрещён. Обратитесь к администратору.');
    return { ok: false, error: 'ACCESS_DENIED' };
  }

  if (callbackQuery) {
    const data = String(callbackQuery.data || '');
    if (data.startsWith('card:')) {
      const requestId = data.split(':')[1];
      const card = masterService.getRequestCard(requestId);
      await answerCallbackQuery(token, callbackQuery.id, card ? 'Открываю карточку' : 'Заявка не найдена');
      if (!card) return { ok: false, error: 'REQUEST_NOT_FOUND' };
      return respondWithMessage({ token, chatId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(requestId) } });
    }
    if (data.startsWith('req:')) {
      const [, requestId, toStatus] = data.split(':');
      if (toStatus === 'comment') {
        sessions.set(telegramId, { step: 'request_comment', requestId });
        await answerCallbackQuery(token, callbackQuery.id, 'Введите комментарий');
        return respondWithMessage({ token, chatId, text: `Введите внутренний комментарий по заявке ${requestId}` });
      }
      if (toStatus === 'lost') {
        sessions.set(telegramId, { step: 'lost_reason', requestId });
        await answerCallbackQuery(token, callbackQuery.id, 'Укажите причину');
        return respondWithMessage({ token, chatId, text: `Укажите причину для статуса "Потеряно" по заявке ${requestId}` });
      }
      const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role });
      if (!result?.error && toStatus === 'waiting_data') {
        await masterService.requestClientClarification({
          requestId,
          actorId: actor.id,
          actorRole: actor.role,
          text: 'Пожалуйста, уточните недостающие данные по вашему обращению.',
          telegramClientBotToken: config.telegramClientBotToken
        });
      }
      await answerCallbackQuery(token, callbackQuery.id, result?.error ? 'Ошибка' : 'Готово');
      return respondWithMessage({ token, chatId, text: result?.error ? `Ошибка: ${result.error}` : `Статус заявки ${requestId}: ${toStatus}`, payload: { ok: !result?.error, ...result } });
    }
  }

  const text = String(message?.text || '').trim();
  logger.info('master_bot incoming text', { telegramId, chatId, text });
  try {
    if (text === '/start') {
      const baseKeyboard = [['Новые заявки', 'В работе'], ['Поиск', 'Quality Cases']];
      if (canManageAccess(actor)) baseKeyboard.push(['Доступы']);
      await sendTelegramMessage(token, chatId, `Master Bot запущен. Роль: ${actor.role}.`, { reply_markup: { keyboard: baseKeyboard, resize_keyboard: true } });
      db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: {} });
      return { ok: true, action: 'start' };
    }

    if (text === 'Новые заявки' || text === 'В работе') {
      const status = text === 'Новые заявки' ? 'new' : 'in_progress';
      const items = masterService.listRequestsByStatus(status);
      const lines = items.map(formatRequestLine);
      await respondWithMessage({ token, chatId, text: lines.join('\n') || (status === 'new' ? 'Нет новых заявок' : 'Нет заявок в работе') });
      for (const item of items.slice(0, 10)) {
        await sendTelegramMessage(token, chatId, `Заявка ${item.id}`, { reply_markup: buildRequestActionsKeyboard(item.id) });
      }
      return { ok: true, items };
    }

    if (text === 'Поиск') {
      sessions.set(telegramId, { step: 'search_query' });
      return respondWithMessage({ token, chatId, text: 'Введите строку для поиска (ФИО, телефон, VIN или номер).' });
    }

    if (text === 'Доступы') {
      if (!canManageAccess(actor)) return respondWithMessage({ token, chatId, text: 'Недостаточно прав.' });
      sessions.set(telegramId, { step: 'access_menu' });
      return respondWithMessage({ token, chatId, text: 'Раздел доступов:\n/access_list\n/access_grant <telegramId> <master|manager> [ФИО]\n/access_revoke <telegramId>\n/access_role <telegramId> <master|manager>' });
    }

    if (text === 'Quality Cases') {
      const items = masterService.listQualityCases();
      return respondWithMessage({ token, chatId, text: qualityCasesText(items), payload: { ok: true, items } });
    }

    const session = sessions.get(telegramId);
    if (session?.step === 'search_query') {
      sessions.delete(telegramId);
      const results = masterService.search(text);
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ token, chatId, text: buildRequestCardText(card), payload: { ok: true, action: 'search_results', card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } });
      }
      return respondWithMessage({ token, chatId, text: 'Ничего не найдено', payload: { ok: true, action: 'search_results', ...results } });
    }

    if (session?.step === 'lost_reason') {
      sessions.delete(telegramId);
      const result = masterService.changeRequestStatus({ requestId: session.requestId, toStatus: 'lost', actorId: actor.id, actorRole: actor.role, lostReason: text });
      return respondWithMessage({ token, chatId, text: result?.error ? `Ошибка: ${result.error}` : `Заявка ${session.requestId} переведена в потерянные`, payload: { ok: !result?.error, ...result } });
    }

    if (session?.step === 'request_comment') {
      sessions.delete(telegramId);
      const comment = masterService.addInternalComment({ requestId: session.requestId, actorId: actor.id, actorRole: actor.role, text });
      return comment ? respondWithMessage({ token, chatId, text: 'Комментарий добавлен', payload: { ok: true, comment } }) : respondWithMessage({ token, chatId, text: 'Заявка не найдена', payload: { ok: false } });
    }

    if (text === 'Список доступов') {
      const items = masterService.listStaffUsers();
      return respondWithMessage({ token, chatId, text: items.map((u) => `${u.telegramId} | ${u.role} | ${u.fullName || '-'}`).join('\n') || 'Список пуст', payload: { ok: true, items } });
    }
    if (text === 'Выдать доступ') {
      sessions.set(telegramId, { step: 'access_grant_input' });
      return respondWithMessage({ token, chatId, text: 'Введите: <telegramId> <master|manager> <ФИО>' });
    }
    if (text === 'Изменить роль') {
      sessions.set(telegramId, { step: 'access_role_input' });
      return respondWithMessage({ token, chatId, text: 'Введите: <telegramId> <master|manager>' });
    }
    if (text === 'Отозвать доступ') {
      sessions.set(telegramId, { step: 'access_revoke_input' });
      return respondWithMessage({ token, chatId, text: 'Введите telegramId для отзыва доступа' });
    }
    if (text === 'Назад') {
      sessions.delete(telegramId);
      return respondWithMessage({ token, chatId, text: 'Главное меню', extra: { reply_markup: { keyboard: [['Новые заявки', 'В работе'], ['Поиск', 'Quality Cases'], ['Доступы']], resize_keyboard: true } } });
    }

    if (session?.step === 'access_grant_input') {
      sessions.delete(telegramId);
      const [tid, role, ...nameParts] = text.split(' ');
      const result = masterService.grantStaffAccess({ telegramId: tid, fullName: nameParts.join(' ').trim(), role, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ token, chatId, text: result.error ? `Ошибка: ${result.error}` : `Доступ выдан: ${tid} -> ${role}` });
    }
    if (session?.step === 'access_role_input') {
      sessions.delete(telegramId);
      const [tid, role] = text.split(' ');
      const result = masterService.grantStaffAccess({ telegramId: tid, role, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ token, chatId, text: result.error ? `Ошибка: ${result.error}` : `Роль обновлена: ${tid} -> ${role}` });
    }
    if (session?.step === 'access_revoke_input') {
      sessions.delete(telegramId);
      const result = masterService.revokeStaffAccess({ telegramId: text.trim(), actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ token, chatId, text: result.error ? `Ошибка: ${result.error}` : `Доступ отозван: ${text.trim()}` });
    }

    if (text.startsWith('/access_list')) {
      if (!canManageAccess(actor)) return respondWithMessage({ token, chatId, text: 'Недостаточно прав.' });
      const items = masterService.listStaffUsers();
      return respondWithMessage({ token, chatId, text: items.map((u) => `${u.telegramId} | ${u.role} | ${u.fullName || '-'}`).join('\n') || 'Список пуст', payload: { ok: true, items } });
    }

    if (text.startsWith('/access_grant ') || text.startsWith('/access_role ')) {
      if (!canManageAccess(actor)) return respondWithMessage({ token, chatId, text: 'Недостаточно прав.' });
      const [, tid, role, ...nameParts] = text.split(' ');
      const result = masterService.grantStaffAccess({ telegramId: tid, fullName: nameParts.join(' ').trim(), role, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ token, chatId, text: result.error ? `Ошибка: ${result.error}` : `Доступ обновлён: ${tid} -> ${role}`, payload: { ok: !result.error, ...result } });
    }

    if (text.startsWith('/access_revoke ')) {
      if (!canManageAccess(actor)) return respondWithMessage({ token, chatId, text: 'Недостаточно прав.' });
      const [, tid] = text.split(' ');
      const result = masterService.revokeStaffAccess({ telegramId: tid, actorId: actor.id, actorRole: actor.role });
      return respondWithMessage({ token, chatId, text: result.error ? `Ошибка: ${result.error}` : `Доступ отозван: ${tid}`, payload: { ok: !result.error, ...result } });
    }


    if (text.startsWith('/search ')) {
      const results = masterService.search(text.slice(8));
      if (results.requests[0]) {
        const card = masterService.getRequestCard(results.requests[0].id);
        return respondWithMessage({ token, chatId, text: buildRequestCardText(card), payload: { ok: true, ...results, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } });
      }
      return { ok: true, ...results };
    }

    if (text.startsWith('/client ')) {
      const card = masterService.getClientCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'CLIENT_NOT_FOUND' };
    }

    if (text.startsWith('/request ')) {
      const card = masterService.getRequestCard(text.split(' ')[1]);
      return card ? respondWithMessage({ token, chatId, text: buildRequestCardText(card), payload: { ok: true, card }, extra: { reply_markup: buildRequestActionsKeyboard(card.request.id) } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }

    if (text.startsWith('/set_status ')) {
      const [, requestId, toStatus, ...reasonParts] = text.split(' ');
      const lostReason = reasonParts.join(' ');
      const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role, lostReason });
      return respondWithMessage({ token, chatId, text: result?.error ? `Ошибка: ${result.error}` : `Статус обновлён: ${toStatus}`, payload: { ok: !result?.error, ...result } });
    }

    if (text.startsWith('/comment ')) {
      const [, requestId, ...commentParts] = text.split(' ');
      const comment = masterService.addInternalComment({ requestId, actorId: actor.id, actorRole: actor.role, text: commentParts.join(' ') });
      return comment ? respondWithMessage({ token, chatId, text: 'Комментарий добавлен', payload: { ok: true, comment } }) : { ok: false, error: 'REQUEST_NOT_FOUND' };
    }

    if (text.startsWith('/ask_client ')) {
      const [, requestId, ...textParts] = text.split(' ');
      const result = await masterService.requestClientClarification({ requestId, actorId: actor.id, actorRole: actor.role, text: textParts.join(' '), telegramClientBotToken: config.telegramClientBotToken });
      return respondWithMessage({ token, chatId, text: result.error ? `Ошибка: ${result.error}` : 'Запрос клиенту отправлен/зафиксирован', payload: result });
    }

    if (text === '/report_week' || text === '/report_month' || text === '/report_quarter' || text === '/report_stats') {
      if (!canUseReports(actor)) {
        return respondWithMessage({ token, chatId, text: 'Недостаточно прав для отчётов.', payload: { ok: false, error: 'REPORT_ACCESS_DENIED', allowedRoles: ['manager', 'admin'] } });
      }
      const periodMap = { '/report_week': 'weekly', '/report_month': 'monthly', '/report_quarter': 'quarterly', '/report_stats': 'weekly' };
      const report = reportingService.buildManagementSummary({ period: periodMap[text] });
      return respondWithMessage({ token, chatId, text: report.summaryText, payload: { ok: true, report } });
    }


    if (text === '/quality_cases') {
      const items = masterService.listQualityCases();
      return respondWithMessage({ token, chatId, text: qualityCasesText(items), payload: { ok: true, items } });
    }

    if (text.startsWith('/quality_case ')) {
      const card = masterService.getQualityCaseCard(text.split(' ')[1]);
      return card ? { ok: true, card } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }

    if (text.startsWith('/quality_status ')) {
      const [, qualityCaseId, status] = text.split(' ');
      const updated = masterService.changeQualityCaseStatus({ qualityCaseId, status, actorId: actor.id, actorRole: actor.role });
      return updated ? { ok: true, qualityCase: updated } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND_OR_STATUS_INVALID' };
    }

    if (text.startsWith('/quality_comment ')) {
      const [, qualityCaseId, ...commentParts] = text.split(' ');
      const comment = masterService.addQualityCaseComment({ qualityCaseId, actorId: actor.id, actorRole: actor.role, text: commentParts.join(' ') });
      return comment ? { ok: true, comment } : { ok: false, error: 'QUALITY_CASE_NOT_FOUND' };
    }

    return respondWithMessage({ token, chatId, text: 'Команда не распознана. Используйте /start.', payload: { ok: true, action: 'unknown_command' } });
  } catch (error) {
    logger.error('master_bot handler error', { telegramId, chatId, text, error: String(error?.message || error) });
    await sendTelegramMessage(token, chatId, 'Произошла ошибка при обработке сообщения. Попробуйте ещё раз.');
    return { ok: false, error: 'MASTER_BOT_HANDLER_ERROR' };
  }
}

module.exports = { registerMasterBotRoutes, handleMasterWebhook, buildRequestActionsKeyboard };
