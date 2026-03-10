const db = require('../../infrastructure/db');
const { createMasterService } = require('../../core/application');

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

function formatRequestLine(request) {
  return `${request.id} | ${request.requestType} | ${request.status} | ${request.description || '-'} `;
}

function registerMasterBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/master_bot/webhook', handler: handleMasterWebhook });
}

async function handleMasterWebhook({ body, config }) {
  const message = body?.message;
  if (!message) return { ok: true };

  const telegramId = String(message.from?.id || '');
  const chatId = message.chat?.id;
  const text = String(message.text || '').trim();
  const actor = masterService.resolveActor({ telegramId, fullName: [message.from?.first_name, message.from?.last_name].filter(Boolean).join(' ').trim() });

  if (text === '/start') {
    const roles = masterService.getAvailableRoles().join(', ');
    await sendTelegramMessage(config.telegramMasterBotToken, chatId, `Master Bot MVP запущен. Роль: ${actor.role}. Доступные роли в системе: ${roles}.`, {
      reply_markup: {
        keyboard: [['Новые заявки', 'В работе'], ['Поиск', 'Quality Cases']],
        resize_keyboard: true
      }
    });
    db.recordMasterAction({ actorId: actor.id, role: actor.role, action: 'master_start', payload: {} });
    return { ok: true, action: 'start' };
  }

  if (text === 'Новые заявки') {
    const items = masterService.listRequestsByStatus('new');
    return { ok: true, items, text: items.map(formatRequestLine).join('\n') || 'Нет новых заявок' };
  }

  if (text === 'В работе') {
    const items = masterService.listRequestsByStatus('in_progress');
    return { ok: true, items, text: items.map(formatRequestLine).join('\n') || 'Нет заявок в работе' };
  }

  if (text === 'Поиск') {
    sessions.set(telegramId, { step: 'search_query' });
    return { ok: true, action: 'await_search_query' };
  }

  if (text === 'Quality Cases') {
    return { ok: true, items: masterService.listQualityCases() };
  }

  const session = sessions.get(telegramId);
  if (session?.step === 'search_query') {
    sessions.delete(telegramId);
    return { ok: true, action: 'search_results', query: text, ...masterService.search(text) };
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

  if (text === '/quality_cases') {
    return { ok: true, items: masterService.listQualityCases() };
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

  return { ok: true, action: 'unknown_command' };
}

module.exports = { registerMasterBotRoutes, handleMasterWebhook };
