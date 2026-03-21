const { REQUEST_TYPES } = require('../../core/domain');
const { resolvePhoneInput } = require('../../core/shared/phone');
const db = require('../../infrastructure/db');
const logger = require('../../infrastructure/logging/logger');
const { sendChannelMessage, answerChannelCallback } = require('../../infrastructure/messaging');
const { QUICK_TYPE_BY_KEY, parseCommandText, resolveStartContext, extractIncomingEvent, buildClientMainMenu } = require('../shared/channelAdapters');
const { validateMaxWebhookRequest } = require('../shared/maxSecurity');

const sessions = new Map();

function registerClientBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/client_bot/webhook', handler: (ctx) => handleClientWebhook({ ...ctx, channel: 'telegram' }) });
  router.push({ method: 'POST', path: '/max/client_bot/webhook', handler: (ctx) => handleClientWebhook({ ...ctx, channel: 'max' }) });
}

function quickTypeFromText(text) {
  const value = (text || '').toLowerCase();
  if (value.includes('запчаст')) return REQUEST_TYPES.PARTS;
  if (value.includes('гарант')) return REQUEST_TYPES.WARRANTY;
  if (value.includes('вопрос')) return REQUEST_TYPES.CONSULTATION;
  if (value.includes('свяж')) return REQUEST_TYPES.CALLBACK;
  if (value.includes('измен')) return REQUEST_TYPES.DATA_CHANGE;
  if (value.includes('запись') || value.includes('сервис')) return REQUEST_TYPES.SERVICE;
  return null;
}

function normalizePhone10(raw) {
  const digits = String(raw || '').replace(/\D/g, '');
  if (digits.length === 11 && (digits.startsWith('7') || digits.startsWith('8'))) return digits.slice(1);
  return digits;
}

function isValidPhone10(raw) {
  return /^\d{10}$/.test(normalizePhone10(raw));
}

function parseRating(text) {
  const raw = String(text || '').trim();
  const match = raw.match(/^([1-5])(?:\s+(.+))?$/);
  if (!match) return null;
  return { rating: Number(match[1]), comment: (match[2] || '').trim() };
}

function findStaffForQualityNotifications(qualityCaseId) {
  const store = db.readStore();
  const qualityCase = store.qualityCases.find((item) => item.id === qualityCaseId);
  if (!qualityCase) return { masterChatId: null, managerChatId: null };
  const master = qualityCase.assignedTo ? store.staffUsers.find((item) => item.id === qualityCase.assignedTo) : null;
  const manager = store.staffUsers.find((item) => item.role === 'manager') || null;
  return {
    masterChatId: master?.telegramId ? Number(master.telegramId) : null,
    managerChatId: manager?.telegramId ? Number(manager.telegramId) : null
  };
}

function takePendingFeedbackTask(clientId) {
  const pendingTasks = db
    .listTasks(['scheduled'])
    .filter((task) => task.taskType === 'feedback_request' && task.payload?.clientId === clientId)
    .sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
  return pendingTasks[0] || null;
}

function sourceChannelFor(channel) {
  return channel === 'max' ? 'max_chat' : 'telegram_chat';
}

function feedbackSourceFor(channel) {
  return channel === 'max' ? 'max_chat' : 'telegram';
}

function clientBotToken(config, channel) {
  return channel === 'max' ? config.maxClientBotToken : config.telegramClientBotToken;
}

function buildHelpText(channel) {
  const base = [
    '/start — показать стартовое меню',
    '/help — подсказка по сценариям',
    'Сценарии: запись на сервис, запчасти, вопрос мастеру, гарантия, изменение данных, mini app'
  ];
  if (channel === 'max') base.push('MAX deep links: form_service, form_parts, form_consultation, form_warranty, form_data_change, requests');
  return base.join('\n');
}

function buildPhoneRequestMarkup(channel) {
  if (channel === 'telegram') {
    return {
      reply_markup: {
        keyboard: [[{ text: 'Отправить телефон', request_contact: true }]],
        resize_keyboard: true,
        one_time_keyboard: true
      }
    };
  }
  return {};
}


async function sendBotMessage({ channel, config, recipientId, text, extra = {} }) {
  const delivered = await sendChannelMessage({ channel, token: clientBotToken(config, channel), recipientId, text, extra });
  if (!delivered) {
    logger.error('client_bot outbound sendMessage failed', { channel, recipientId, textPreview: String(text || '').slice(0, 200) });
  }
  return delivered;
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

async function handleClientWebhook({ body, config, headers = {}, rawHeaders = [], pathname = '', method = 'POST', channel = 'telegram' }) {
  if (channel === 'max') {
    db.createAnalyticsEvent({
      eventType: 'max_webhook_received',
      channel: 'max',
      platform: 'max',
      status: 'received',
      metaJson: { route: 'client_bot', pathname, method }
    });
    const validation = validateMaxWebhookRequest({
      config,
      headers,
      rawHeaders,
      pathname,
      method,
      logger,
      routeLabel: 'client_bot',
      token: clientBotToken(config, channel),
      body
    });
    if (!validation.ok) {
      db.createAnalyticsEvent({
        eventType: 'max_webhook_rejected',
        channel: 'max',
        platform: 'max',
        status: validation.error,
        metaJson: { route: 'client_bot', pathname, method, statusCode: validation.statusCode }
      });
      return { ok: false, error: validation.error, statusCode: validation.statusCode };
    }
  }

  try {
    const event = extractIncomingEvent({ body, channel });
    const updateType = event.callback ? 'callback' : (event.message ? 'message' : 'unknown');
    const senderBlock = buildSenderSnapshot({ body, event });
    logger.info('client_bot webhook parsed update', {
      channel,
      pathname,
      method,
      updateType,
      hasMessage: Boolean(event.message),
      hasSender: Boolean(event.message?.from || body?.sender || body?.user || event.callback),
      senderBlock,
      userId: event.callback?.userId || event.userId || null,
      messagePresent: Boolean(event.message),
      text: String(event.callback ? event.callback.data || '' : event.text || '').slice(0, 500)
    });
    if (!event.message && !event.callback) {
      logger.warn('client_bot unknown update without message/callback', {
        channel,
        pathname,
        method,
        reason: 'NO_MESSAGE_AND_NO_CALLBACK',
        body
      });
      return { ok: true, action: 'ignored_unknown_update', updateType };
    }

    const userId = event.callback?.userId || event.userId;
    const recipientId = resolveRecipientId(channel, userId, event.callback?.chatId || event.chatId);
    const sessionKey = `${channel}:${userId}`;
    const callbackData = event.callback?.data || '';
    const incomingText = event.callback ? callbackData : event.text;
    const { command, payload } = parseCommandText(incomingText);
    const startPayload = payload || event.startPayload;

    if (event.callback?.id) {
      const answered = await answerChannelCallback({ channel, token: clientBotToken(config, channel), callbackId: event.callback.id, text: 'Обрабатываю действие' });
      if (!answered) logger.error('client_bot callback answer failed', { channel, callbackId: event.callback.id, recipientId });
    }

    if (command === '/start') {
      logger.info('client_bot handler branch selected', { channel, pathname, branch: '/start', userId, recipientId, startPayload });
      const startContext = resolveStartContext(startPayload);
      const menu = buildClientMainMenu({ channel, config, deeplinkPayload: startContext.payload, route: startContext.route });
      await sendBotMessage({
        channel,
        config,
        recipientId,
        text: startContext.route
          ? `Добро пожаловать! Откройте mini app для сценария ${startContext.payload}.`
          : 'Добро пожаловать! Откройте mini app или создайте быстрое обращение.',
        extra: menu
      });
      db.createCommunicationEvent({ source: channel === 'max' ? 'max_client_bot' : 'bot', channel, direction: 'inbound', payload: { action: 'start', startPayload }, clientId: null, requestId: null });
      return { ok: true, action: 'start', channel, deeplink: startContext };
    }

    if (command === '/help') {
      logger.info('client_bot handler branch selected', { channel, pathname, branch: '/help', userId, recipientId });
      const text = buildHelpText(channel);
      await sendBotMessage({ channel, config, recipientId, text });
      return { ok: true, action: 'help', channel };
    }

    const callbackQuick = callbackData.startsWith('quick:') ? QUICK_TYPE_BY_KEY[callbackData.split(':')[1]] : null;
    const callbackText = callbackData.startsWith('text:') ? callbackData.slice(5) : '';
    const effectiveText = callbackText || incomingText;
    const selectedType = callbackQuick || quickTypeFromText(effectiveText);
    const session = sessions.get(sessionKey);

    if (!session && selectedType) {
      logger.info('client_bot handler branch selected', { channel, pathname, branch: 'quick_request_start', userId, recipientId, selectedType });
      sessions.set(sessionKey, { step: 'fullName', requestType: selectedType, description: effectiveText, recipientId });
      await sendBotMessage({ channel, config, recipientId, text: 'Укажите ФИО для обращения.' });
      return { ok: true, action: 'collect_full_name', channel };
    }

    if (session?.step === 'fullName') {
      logger.info('client_bot handler branch selected', { channel, pathname, branch: 'collect_full_name', userId, recipientId });
      session.fullName = effectiveText;
      session.step = 'phone';
      sessions.set(sessionKey, session);
      await sendBotMessage({ channel, config, recipientId, text: channel === 'telegram' ? 'Отправьте телефон кнопкой ниже или введите вручную.' : 'Укажите телефон в формате +7... или продолжайте через mini app.', extra: buildPhoneRequestMarkup(channel) });
      return { ok: true, action: 'collect_phone', channel };
    }

    if (session?.step === 'phone') {
      logger.info('client_bot handler branch selected', { channel, pathname, branch: 'collect_phone', userId, recipientId, hasNativeContact: Boolean(event.contact) });
      const normalizedPhone = resolvePhoneInput({
        phone: effectiveText,
        nativeContact: event.contact ? { phoneNumber: event.contact.phoneNumber, source: `${channel}_native_contact` } : null
      });
      if (!/^\d{10}$/.test(normalizedPhone)) {
        await sendBotMessage({ channel, config, recipientId, text: 'Нужен корректный телефон: 10 цифр. Попробуйте ещё раз.', extra: buildPhoneRequestMarkup(channel) });
        return { ok: false, action: 'invalid_phone', channel };
      }
      const client = db.upsertClient({
        fullName: session.fullName,
        phone: normalizedPhone,
        telegramId: channel === 'telegram' ? userId : null,
        maxId: channel === 'max' ? userId : null,
        preferredChannel: channel
      });
      const request = db.createRequest({
        clientId: client.id,
        vehicleId: null,
        requestType: session.requestType,
        description: session.description,
        sourceChannel: sourceChannelFor(channel),
        payload: { contactSource: event.contact ? `${channel}_native_contact` : 'manual' }
      });
      db.createCommunicationEvent({
        clientId: client.id,
        requestId: request.id,
        source: channel === 'max' ? 'max_client_bot' : 'bot',
        channel,
        direction: 'inbound',
        payload: { action: 'quick_request_created', requestType: session.requestType }
      });
      db.createAnalyticsEvent({
        eventType: 'tg_request_created',
        channel,
        platform: channel,
        requestType: session.requestType,
        requestId: request.id,
        clientId: client.id,
        status: request.status,
        metaJson: { sourceChannel: sourceChannelFor(channel) }
      });
      sessions.delete(sessionKey);
      await sendBotMessage({
        channel,
        config,
        recipientId,
        text: `Обращение создано (${session.requestType}). Также доступен mini app: ${buildClientMainMenu({ channel, config }).reply_markup.inline_keyboard?.[0]?.[0]?.url || config.webAppUrl}`
      });
      return { ok: true, action: 'request_created', requestId: request.id, channel };
    }

    const parsedFeedback = parseRating(effectiveText);
    const client = channel === 'max' ? db.findClientByMaxId(userId) : db.findClientByTelegramId(userId);
    if (client && parsedFeedback) {
      logger.info('client_bot handler branch selected', { channel, pathname, branch: 'feedback', userId, recipientId, rating: parsedFeedback.rating });
      const task = takePendingFeedbackTask(client.id);
      const requestId = task?.payload?.requestId || null;
      const result = db.createFeedback({
        clientId: client.id,
        requestId,
        rating: parsedFeedback.rating,
        comment: parsedFeedback.comment,
        sourceChannel: feedbackSourceFor(channel),
        createdBy: 'client'
      });

      if (task) {
        db.completeTask(task.id);
      }

      const confirmation = parsedFeedback.comment
        ? `Спасибо за оценку ${parsedFeedback.rating}/5 и комментарий. Мы зафиксировали обратную связь.`
        : `Спасибо за оценку ${parsedFeedback.rating}/5. Обратная связь сохранена.`;
      await sendBotMessage({ channel, config, recipientId, text: confirmation });
      if (result.qualityCase) {
        const { masterChatId, managerChatId } = findStaffForQualityNotifications(result.qualityCase.id);
        const text = `Quality case ${result.qualityCase.id}: низкая оценка ${parsedFeedback.rating}/5 по заявке ${requestId || '-'}; клиент ${client.fullName || client.id}`;
        if (masterChatId) {
          await sendChannelMessage({ channel: 'telegram', token: config.telegramMasterBotToken, recipientId: masterChatId, text });
        }
        if (managerChatId) {
          await sendChannelMessage({ channel: 'telegram', token: config.telegramMasterBotToken, recipientId: managerChatId, text: `[manager copy] ${text}` });
        }
      }
      return { ok: true, action: 'feedback_saved', feedbackId: result.feedback.id, qualityCaseId: result.qualityCase?.id || null, channel };
    }

    logger.info('client_bot handler branch selected', { channel, pathname, branch: 'fallback', userId, recipientId, updateType, command, hasSession: Boolean(session) });
    await sendBotMessage({ channel, config, recipientId, text: 'Используйте /start для запуска сценария или /help для подсказки.' });
    return { ok: true, action: 'fallback', channel };
  } catch (error) {
    logger.error('client_bot handler exception', { channel, pathname, error: String(error?.message || error), body });
    return { ok: false, error: 'CLIENT_BOT_ERROR', statusCode: 500 };
  }
}

module.exports = { registerClientBotRoutes, handleClientWebhook, quickTypeFromText, normalizePhone10, isValidPhone10 };
