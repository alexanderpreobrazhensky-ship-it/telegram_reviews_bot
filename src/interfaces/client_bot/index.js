const { REQUEST_TYPES } = require('../../core/domain');
const db = require('../../infrastructure/db');

const sessions = new Map();

function registerClientBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/client_bot/webhook', handler: handleClientWebhook });
}

async function sendTelegramMessage(token, chatId, text, extra = {}) {
  if (!token || !chatId) return;
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, ...extra })
  }).catch(() => {});
}

function quickTypeFromText(text) {
  const value = (text || '').toLowerCase();
  if (value.includes('запчаст')) return REQUEST_TYPES.PARTS;
  if (value.includes('гарант')) return REQUEST_TYPES.WARRANTY;
  if (value.includes('вопрос')) return REQUEST_TYPES.CONSULTATION;
  if (value.includes('свяж')) return REQUEST_TYPES.CALLBACK;
  if (value.includes('запись') || value.includes('сервис')) return REQUEST_TYPES.SERVICE;
  return null;
}

async function handleClientWebhook({ body, config }) {
  const message = body?.message;
  if (!message) return { ok: true };
  const chatId = message.chat?.id;
  const telegramId = String(message.from?.id || '');
  const text = message.text || '';

  if (text === '/start') {
    await sendTelegramMessage(
      config.telegramClientBotToken,
      chatId,
      'Добро пожаловать! Откройте WebApp или создайте быстрое обращение.',
      {
        reply_markup: {
          inline_keyboard: [[{ text: 'Открыть WebApp', web_app: { url: config.webAppUrl } }]],
          keyboard: [['Нужна запись / сервис', 'Нужны запчасти'], ['Вопрос мастеру', 'Гарантийное обращение'], ['Свяжитесь со мной']],
          resize_keyboard: true
        }
      }
    );
    db.createCommunicationEvent({ source: 'bot', payload: { action: 'start' }, clientId: null, requestId: null });
    return { ok: true, action: 'start' };
  }

  const session = sessions.get(telegramId);
  const selectedType = quickTypeFromText(text);

  if (!session && selectedType) {
    sessions.set(telegramId, { step: 'fullName', requestType: selectedType, description: text, chatId });
    await sendTelegramMessage(config.telegramClientBotToken, chatId, 'Укажите ФИО для обращения.');
    return { ok: true, action: 'collect_full_name' };
  }

  if (session?.step === 'fullName') {
    session.fullName = text;
    session.step = 'phone';
    sessions.set(telegramId, session);
    await sendTelegramMessage(config.telegramClientBotToken, chatId, 'Укажите телефон в формате +7...');
    return { ok: true, action: 'collect_phone' };
  }

  if (session?.step === 'phone') {
    const client = db.upsertClient({ fullName: session.fullName, phone: text, telegramId });
    const request = db.createRequest({
      clientId: client.id,
      vehicleId: null,
      requestType: session.requestType,
      description: session.description,
      sourceChannel: 'telegram_chat'
    });
    db.createCommunicationEvent({ clientId: client.id, requestId: request.id, source: 'bot', payload: { action: 'quick_request_created', requestType: session.requestType } });
    sessions.delete(telegramId);
    await sendTelegramMessage(config.telegramClientBotToken, chatId, `Обращение создано (${session.requestType}). Также доступен WebApp: ${config.webAppUrl}`);
    return { ok: true, action: 'request_created', requestId: request.id };
  }

  await sendTelegramMessage(config.telegramClientBotToken, chatId, 'Используйте /start для запуска сценария.');
  return { ok: true, action: 'fallback' };
}

module.exports = { registerClientBotRoutes, handleClientWebhook, quickTypeFromText };
