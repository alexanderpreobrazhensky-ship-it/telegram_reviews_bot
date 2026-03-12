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

const masterService = createMasterService({ db, sendClientMessage: sendTelegramMessage });
const reportingService = createReportingService({ db });



function canUseReports(actor) {
  return actor?.role === 'manager' || actor?.role === 'admin';
}

function formatRequestLine(request) {
  return `${request.id} | ${request.requestType} | ${request.status} | ${request.description || '-'} `;
}

function registerMasterBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/master_bot/webhook', handler: handleMasterWebhook });
}

async function respondWithMessage({ token, chatId, text, payload = {}, extra = {} }) {
  if (text) {
    await sendTelegramMessage(token, chatId, text, extra);
  }
  return text ? { ...payload, text } : payload;
}

function qualityCasesText(items) {
  return items.map((item) => `${item.id} | ${item.status} | ${item.summary || '-'}`).join('\n') || 'Нет quality cases';
}

async function handleMasterWebhook({ body, config }) {
  const message = body?.message;
  if (!message) return { ok: true };

  const telegramId = String(message.from?.id || '');
  const chatId = message.chat?.id;
  const text = String(message.text || '').trim();
  const actor = masterService.resolveActor({ telegramId, fullName: [message.from?.first_name, message.from?.last_name].filter(Boolean).join(' ').trim() });
  const token = config.telegramMasterBotToken;

  logger.info('master_bot incoming text', { telegramId, chatId, text });

  try {

    if (text === '/start') {
      logger.info('master_bot branch: /start', { telegramId });
      const roles = masterService.getAvailableRoles().join(', ');
      await sendTelegramMessage(token, chatId, `Master Bot MVP запущен. Роль: ${actor.role}. Доступные роли в системе: ${roles}.`, {
        reply_markup: {
          keyboard: [['Новые заявки', 'В работе'], ['Поиск', 'Quality Cases']],
          resize_keyboard: true
        }
      });
      db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: {} });
      return { ok: true, action: 'start' };
    }

    if (text === 'Новые заявки') {
      logger.info('master_bot branch: new_requests', { telegramId });
      const items = masterService.listRequestsByStatus('new');
      return respondWithMessage({
        token,
        chatId,
        text: items.map(formatRequestLine).join('\n') || 'Нет новых заявок',
        payload: { ok: true, items }
      });
    }

    if (text === 'В работе') {
      logger.info('master_bot branch: in_progress', { telegramId });
      const items = masterService.listRequestsByStatus('in_progress');
      return respondWithMessage({
        token,
        chatId,
        text: items.map(formatRequestLine).join('\n') || 'Нет заявок в работе',
        payload: { ok: true, items }
      });
    }

    if (text === 'Поиск') {
      logger.info('master_bot branch: search_prompt', { telegramId });
      sessions.set(telegramId, { step: 'search_query' });
      return respondWithMessage({ token, chatId, text: 'Введите строку для поиска (ФИО, телефон, VIN или номер).' , payload: { ok: true, action: 'await_search_query' } });
    }

    if (text === 'Quality Cases') {
      logger.info('master_bot branch: quality_cases', { telegramId });
      const items = masterService.listQualityCases();
      return respondWithMessage({ token, chatId, text: qualityCasesText(items), payload: { ok: true, items } });
    }

    const session = sessions.get(telegramId);
    if (session?.step === 'search_query') {
      logger.info('master_bot branch: search_query', { telegramId, query: text });
      sessions.delete(telegramId);
      const results = masterService.search(text);
      const qualityCases = Array.isArray(results.qualityCases) ? results.qualityCases : [];
      const resultText = [`Клиенты: ${results.clients.length}`, `Заявки: ${results.requests.length}`, `Quality cases: ${qualityCases.length}`].join('\n');
      const payloadResults = { ...results, qualityCases };
      return respondWithMessage({ token, chatId, text: resultText, payload: { ok: true, action: 'search_results', query: text, ...payloadResults } });
    }

  if (text.startsWith('/search ')) {
    return { ok: true, action: 'search_results', query: text.slice(8), ...masterService.search(text.slice(8)) };
  }

  if (text.startsWith('/client ')) {
    const card = masterService.getClientCard(text.split(' ')[1]);
    return card ? { ok: true, card } : { ok: false, error: 'CLIENT_NOT_FOUND' };
  }

  if (text.startsWith('/request ')) {
    const card = masterService.getRequestCard(text.split(' ')[1]);
    return card ? { ok: true, card } : { ok: false, error: 'REQUEST_NOT_FOUND' };
  }

  if (text.startsWith('/set_status ')) {
    const [, requestId, toStatus, ...reasonParts] = text.split(' ');
    const lostReason = reasonParts.join(' ');
    const result = masterService.changeRequestStatus({ requestId, toStatus, actorId: actor.id, actorRole: actor.role, lostReason });
    return { ok: !result?.error, ...result };
  }

  if (text.startsWith('/comment ')) {
    const [, requestId, ...commentParts] = text.split(' ');
    const comment = masterService.addInternalComment({ requestId, actorId: actor.id, actorRole: actor.role, text: commentParts.join(' ') });
    return comment ? { ok: true, comment } : { ok: false, error: 'REQUEST_NOT_FOUND' };
  }

  if (text.startsWith('/client_note ')) {
    const [, clientId, ...noteParts] = text.split(' ');
    const note = masterService.addClientNote({ clientId, actorId: actor.id, actorRole: actor.role, text: noteParts.join(' ') });
    return note ? { ok: true, note } : { ok: false, error: 'CLIENT_NOT_FOUND' };
  }

  if (text.startsWith('/ask_client ')) {
    const [, requestId, ...textParts] = text.split(' ');
    const result = await masterService.requestClientClarification({
      requestId,
      actorId: actor.id,
      actorRole: actor.role,
      text: textParts.join(' '),
      telegramClientBotToken: config.telegramClientBotToken
    });
    return result;
  }


    if (text === '/report_week' || text === '/report_month' || text === '/report_quarter' || text === '/report_stats') {
      if (!canUseReports(actor)) {
        return respondWithMessage({ token, chatId, text: 'Недостаточно прав для отчётов.', payload: { ok: false, error: 'REPORT_ACCESS_DENIED', allowedRoles: ['manager', 'admin'] } });
      }
      const periodMap = {
        '/report_week': 'weekly',
        '/report_month': 'monthly',
        '/report_quarter': 'quarterly',
        '/report_stats': 'weekly'
      };
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

    logger.info('master_bot branch: unknown_command', { telegramId, text });
    return respondWithMessage({ token, chatId, text: 'Команда не распознана. Используйте /start.', payload: { ok: true, action: 'unknown_command' } });
  } catch (error) {
    logger.error('master_bot handler error', { telegramId, chatId, text, error: String(error?.message || error) });
    await sendTelegramMessage(token, chatId, 'Произошла ошибка при обработке сообщения. Попробуйте ещё раз.');
    return { ok: false, error: 'MASTER_BOT_HANDLER_ERROR' };
  }
}

module.exports = { registerMasterBotRoutes, handleMasterWebhook };
