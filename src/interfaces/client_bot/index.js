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

  const parsedFeedback = parseRating(text);
  const client = db.findClientByTelegramId(telegramId);
  if (client && parsedFeedback) {
    const task = takePendingFeedbackTask(client.id);
    const requestId = task?.payload?.requestId || null;
    const result = db.createFeedback({
      clientId: client.id,
      requestId,
      rating: parsedFeedback.rating,
      comment: parsedFeedback.comment,
      sourceChannel: 'telegram',
      createdBy: 'client'
    });

    if (task) {
      db.completeTask(task.id);
    }

    const confirmation = parsedFeedback.comment
      ? `Спасибо за оценку ${parsedFeedback.rating}/5 и комментарий. Мы зафиксировали обратную связь.`
      : `Спасибо за оценку ${parsedFeedback.rating}/5. Обратная связь сохранена.`;
    await sendTelegramMessage(config.telegramClientBotToken, chatId, confirmation);
    if (result.qualityCase) {
      const { masterChatId, managerChatId } = findStaffForQualityNotifications(result.qualityCase.id);
      const textForStaff = `Quality case ${result.qualityCase.id}: низкая оценка ${parsedFeedback.rating}/5 по заявке ${requestId || '-'}; клиент ${client.fullName || client.id}`;
      if (masterChatId) {
        await sendTelegramMessage(config.telegramMasterBotToken, masterChatId, textForStaff);
      }
      if (managerChatId) {
        await sendTelegramMessage(config.telegramMasterBotToken, managerChatId, `[manager copy] ${textForStaff}`);
      }
    }
    return { ok: true, action: 'feedback_saved', feedbackId: result.feedback.id, qualityCaseId: result.qualityCase?.id || null };
  }

  await sendTelegramMessage(config.telegramClientBotToken, chatId, 'Используйте /start для запуска сценария.');
  return { ok: true, action: 'fallback' };
}

module.exports = { registerClientBotRoutes, handleClientWebhook, quickTypeFromText };
