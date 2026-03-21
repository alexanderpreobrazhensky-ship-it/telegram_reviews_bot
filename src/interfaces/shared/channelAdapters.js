const { buildMaxMiniAppLink } = require('../../infrastructure/messaging');

const QUICK_TYPE_BY_KEY = Object.freeze({
  service: 'service_request',
  parts: 'parts_request',
  consultation: 'consultation_request',
  warranty: 'warranty_request',
  data_change: 'data_change_request',
  callback: 'callback_request'
});

function parseCommandText(rawText = '') {
  const text = String(rawText || '').trim();
  if (!text.startsWith('/')) return { text, command: '', payload: '' };
  const [head, ...rest] = text.split(/\s+/);
  const [commandOnly] = head.split('@');
  return {
    text,
    command: commandOnly.toLowerCase(),
    payload: rest.join(' ').trim()
  };
}

function normalizePayloadToken(raw = '') {
  return String(raw || '')
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .slice(0, 128);
}

function buildMiniAppUrl({ channel = 'telegram', config, deeplinkPayload = '', route = '' }) {
  const normalizedRoute = String(route || '').trim().replace(/^\//, '');
  const routePart = normalizedRoute ? `/${normalizedRoute}` : '';
  const webAppBase = channel === 'max' ? (config.maxWebAppUrl || config.webAppUrl) : config.webAppUrl;

  if (channel === 'max') {
    return buildMaxMiniAppLink({
      botName: config.maxBotName,
      baseUrl: `${String(webAppBase || '').replace(/\/$/, '')}${routePart}`,
      startAppPayload: normalizePayloadToken(deeplinkPayload),
      fallbackUrl: `${String(config.webAppUrl || '').replace(/\/$/, '')}${routePart}`
    });
  }

  if (!routePart && !deeplinkPayload) return String(webAppBase || '');
  try {
    const url = new URL(`${String(webAppBase || '').replace(/\/$/, '')}${routePart}`);
    if (deeplinkPayload) url.searchParams.set('startapp', normalizePayloadToken(deeplinkPayload));
    return url.toString();
  } catch {
    return `${String(webAppBase || '').replace(/\/$/, '')}${routePart}`;
  }
}

function resolveStartContext(payload = '') {
  const value = normalizePayloadToken(payload);
  if (!value) return { payload: '', route: '', requestType: null };
  const routeByPayload = {
    form_service: 'forms/service-request',
    form_parts: 'forms/parts-request',
    form_consultation: 'forms/consultation',
    form_warranty: 'forms/warranty-request',
    form_data_change: 'forms/data-change-request',
    requests: 'requests'
  };
  const requestTypeByPayload = {
    form_service: QUICK_TYPE_BY_KEY.service,
    form_parts: QUICK_TYPE_BY_KEY.parts,
    form_consultation: QUICK_TYPE_BY_KEY.consultation,
    form_warranty: QUICK_TYPE_BY_KEY.warranty,
    form_data_change: QUICK_TYPE_BY_KEY.data_change
  };
  return {
    payload: value,
    route: routeByPayload[value] || '',
    requestType: requestTypeByPayload[value] || null
  };
}

function extractTelegramEvent(body = {}) {
  const message = body?.message || null;
  const callbackQuery = body?.callback_query || null;
  return {
    message,
    contact: message?.contact ? { phoneNumber: String(message.contact.phone_number || ''), firstName: message.contact.first_name || '', lastName: message.contact.last_name || '', userId: String(message.contact.user_id || '') } : (body?.contact ? { phoneNumber: String(body.contact.phone_number || body.contact.phone || ''), userId: String(body.contact.user_id || body.contact.userId || '') } : null),
    callback: callbackQuery
      ? {
          id: callbackQuery.id,
          data: String(callbackQuery.data || ''),
          chatId: callbackQuery.message?.chat?.id,
          userId: String(callbackQuery.from?.id || ''),
          fullName: [callbackQuery.from?.first_name, callbackQuery.from?.last_name].filter(Boolean).join(' ').trim(),
          text: String(callbackQuery.message?.text || '')
        }
      : null,
    text: String(message?.text || ''),
    chatId: message?.chat?.id,
    userId: String(message?.from?.id || ''),
    fullName: [message?.from?.first_name, message?.from?.last_name].filter(Boolean).join(' ').trim(),
    startPayload: parseCommandText(message?.text || '').payload
  };
}

function extractMaxEvent(body = {}) {
  const message = body?.message || body?.payload?.message || body?.update?.message || null;
  const callback = body?.callback || body?.message_callback || body?.payload?.callback || null;
  const user = message?.from || message?.sender || body?.user || callback?.user || {};
  const callbackUser = callback?.from || callback?.sender || user;
  const callbackMessage = callback?.message || message || {};
  return {
    message,
    contact: message?.contact ? { phoneNumber: String(message.contact.phone_number || message.contact.phone || ''), firstName: message.contact.first_name || '', lastName: message.contact.last_name || '', userId: String(message.contact.user_id || message.contact.userId || '') } : (body?.contact ? { phoneNumber: String(body.contact.phone_number || body.contact.phone || ''), userId: String(body.contact.user_id || body.contact.userId || '') } : null),
    callback: callback
      ? {
          id: callback.callback_id || callback.id || callback.query_id || '',
          data: String(callback.payload || callback.data || ''),
          chatId: callbackMessage.chat_id || callbackMessage.chat?.chat_id || callbackMessage.chat?.id || callback.chat_id || null,
          userId: String(callbackUser.user_id || callbackUser.id || ''),
          fullName: [callbackUser.first_name, callbackUser.last_name, callbackUser.name].filter(Boolean).join(' ').trim(),
          text: String(callbackMessage.body?.text || callbackMessage.text || '')
        }
      : null,
    text: String(message?.body?.text || message?.text || body?.text || ''),
    chatId: message?.recipient?.chat_id || message?.chat_id || message?.chat?.chat_id || message?.chat?.id || null,
    userId: String(user.user_id || user.id || message?.recipient?.user_id || ''),
    fullName: [user.first_name, user.last_name, user.name].filter(Boolean).join(' ').trim(),
    startPayload: String(body?.start_payload || body?.payload?.start_payload || '').trim()
  };
}

function extractIncomingEvent({ body, channel }) {
  return channel === 'max' ? extractMaxEvent(body) : extractTelegramEvent(body);
}

function buildClientMainMenu({ channel, config, deeplinkPayload = '', route = '' }) {
  const miniAppUrl = buildMiniAppUrl({ channel, config, deeplinkPayload, route });
  if (channel === 'max') {
    return {
      reply_markup: {
        inline_keyboard: [
          [{ text: 'Открыть mini app', url: miniAppUrl }],
          [
            { text: 'Запись на сервис', callback_data: 'quick:service' },
            { text: 'Запрос запчастей', callback_data: 'quick:parts' }
          ],
          [
            { text: 'Вопрос мастеру', callback_data: 'quick:consultation' },
            { text: 'Гарантия', callback_data: 'quick:warranty' }
          ],
          [
            { text: 'Изменение данных', callback_data: 'quick:data_change' },
            { text: 'Свяжитесь со мной', callback_data: 'quick:callback' }
          ]
        ]
      }
    };
  }

  return {
    reply_markup: {
      inline_keyboard: [[{ text: 'Открыть WebApp', web_app: { url: miniAppUrl } }]],
      keyboard: [
        [{ text: 'Мини-приложение', web_app: { url: miniAppUrl } }],
        ['Нужна запись / сервис', 'Нужны запчасти'],
        ['Вопрос мастеру', 'Гарантийное обращение'],
        ['Изменение данных', 'Свяжитесь со мной']
      ],
      resize_keyboard: true
    }
  };
}

module.exports = {
  QUICK_TYPE_BY_KEY,
  parseCommandText,
  normalizePayloadToken,
  resolveStartContext,
  extractIncomingEvent,
  buildClientMainMenu,
  buildMiniAppUrl
};
