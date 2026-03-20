const MAX_API_BASE_URL = 'https://platform-api.max.ru';

function safeUrl(value) {
  try {
    return new URL(String(value || ''));
  } catch {
    return null;
  }
}

function appendQueryParams(rawUrl, params = {}) {
  const url = safeUrl(rawUrl);
  if (!url) return String(rawUrl || '');
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

function buildMaxBotLink({ botName, baseUrl, startPayload = '' } = {}) {
  const normalizedBotName = String(botName || '').replace(/^@/, '').trim();
  const payload = String(startPayload || '').trim();
  if (baseUrl) return appendQueryParams(baseUrl, payload ? { start: payload } : {});
  if (!normalizedBotName) return '';
  const url = new URL(`https://max.ru/${normalizedBotName}`);
  if (payload) url.searchParams.set('start', payload);
  return url.toString();
}

function buildMaxMiniAppLink({ botName, baseUrl, startAppPayload = '', fallbackUrl = '' } = {}) {
  const payload = String(startAppPayload || '').trim();
  if (baseUrl) return appendQueryParams(baseUrl, payload ? { startapp: payload, channel: 'max' } : { channel: 'max' });
  const botLink = buildMaxBotLink({ botName, startPayload: payload ? `startapp_${payload}` : '' });
  return botLink || appendQueryParams(fallbackUrl, { channel: 'max', startapp: payload || undefined });
}

function mapTelegramButtonsToMax(buttonRows = []) {
  const buttons = [];
  for (const row of buttonRows) {
    const mappedRow = [];
    for (const button of row || []) {
      if (typeof button === 'string') {
        mappedRow.push({ type: 'callback', text: button, payload: `text:${button}` });
        continue;
      }
      if (!button || typeof button !== 'object') continue;
      if (button.web_app?.url) {
        mappedRow.push({ type: 'link', text: button.text || 'Открыть', url: button.web_app.url });
        continue;
      }
      if (button.url) {
        mappedRow.push({ type: 'link', text: button.text || 'Открыть', url: button.url });
        continue;
      }
      if (button.callback_data) {
        mappedRow.push({ type: 'callback', text: button.text || 'Действие', payload: button.callback_data });
        continue;
      }
      if (button.text) {
        mappedRow.push({ type: 'callback', text: button.text, payload: `text:${button.text}` });
      }
    }
    if (mappedRow.length) buttons.push(mappedRow);
  }
  return buttons;
}

function buildMaxAttachments(extra = {}) {
  const replyMarkup = extra.reply_markup || {};
  const inlineButtons = mapTelegramButtonsToMax(replyMarkup.inline_keyboard || []);
  const keyboardButtons = mapTelegramButtonsToMax((replyMarkup.keyboard || []).map((row) => row.map((item) => (typeof item === 'string' ? item : item))));
  const buttons = inlineButtons.length ? inlineButtons : keyboardButtons;
  if (!buttons.length) return [];
  return [
    {
      type: 'inline_keyboard',
      payload: { buttons }
    }
  ];
}

async function sendTelegramMessage(token, chatId, text, extra = {}) {
  if (!token || !chatId) return false;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, ...extra })
  }).catch(() => {});
  return true;
}

async function sendMaxMessage(token, userId, text, extra = {}) {
  if (!token || !userId) return false;
  const attachments = buildMaxAttachments(extra);
  const payload = { text };
  if (attachments.length) payload.attachments = attachments;
  await fetch(`${MAX_API_BASE_URL}/messages?user_id=${encodeURIComponent(String(userId))}`, {
    method: 'POST',
    headers: {
      Authorization: token,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  }).catch(() => {});
  return true;
}

async function sendChannelMessage({ channel = 'telegram', token, recipientId, text, extra = {} }) {
  if (channel === 'max') return sendMaxMessage(token, recipientId, text, extra);
  return sendTelegramMessage(token, recipientId, text, extra);
}

async function answerTelegramCallback(token, callbackId, text) {
  if (!token || !callbackId) return false;
  await fetch(`https://api.telegram.org/bot${token}/answerCallbackQuery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ callback_query_id: callbackId, text })
  }).catch(() => {});
  return true;
}

async function answerMaxCallback(token, callbackId, text) {
  if (!token || !callbackId) return false;
  await fetch(`${MAX_API_BASE_URL}/answers?callback_id=${encodeURIComponent(String(callbackId))}`, {
    method: 'POST',
    headers: {
      Authorization: token,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ notification: text })
  }).catch(() => {});
  return true;
}

async function answerChannelCallback({ channel = 'telegram', token, callbackId, text }) {
  if (channel === 'max') return answerMaxCallback(token, callbackId, text);
  return answerTelegramCallback(token, callbackId, text);
}

module.exports = {
  MAX_API_BASE_URL,
  appendQueryParams,
  buildMaxBotLink,
  buildMaxMiniAppLink,
  sendChannelMessage,
  answerChannelCallback
};
