const db = require('../../infrastructure/db');
const { integrationService } = require('../../core/application');
const logger = require('../../infrastructure/logging/logger');
const { sendChannelMessage, answerChannelCallback } = require('../../infrastructure/messaging');

const PENDING_STATUSES = new Set(['received', 'normalized', 'processing', 'retry_scheduled']);
const MAIN_MENU_LABELS = Object.freeze({
  events: 'Все события',
  failed: 'Ошибки',
  pending: 'В ожидании',
  stats: 'Статистика',
  help: 'Инструкция',
  selfcheck: 'Самодиагностика'
});
const MENU_TEXT_TO_COMMAND = Object.freeze({
  [MAIN_MENU_LABELS.events]: '/events',
  [MAIN_MENU_LABELS.failed]: '/failed',
  [MAIN_MENU_LABELS.pending]: '/pending',
  [MAIN_MENU_LABELS.stats]: '/stats',
  [MAIN_MENU_LABELS.help]: '/help',
  [MAIN_MENU_LABELS.selfcheck]: '/selfcheck'
});
const MAIN_REPLY_KEYBOARD = Object.freeze({
  keyboard: [
    [{ text: MAIN_MENU_LABELS.events }, { text: MAIN_MENU_LABELS.failed }],
    [{ text: MAIN_MENU_LABELS.pending }, { text: MAIN_MENU_LABELS.stats }],
    [{ text: MAIN_MENU_LABELS.help }, { text: MAIN_MENU_LABELS.selfcheck }]
  ],
  resize_keyboard: true,
  one_time_keyboard: false,
  input_field_placeholder: 'Выберите раздел или введите /event <id>'
});

function compact(event) {
  return {
    id: event.id,
    sourceSystem: event.sourceSystem,
    eventType: event.eventType,
    integrationEventType: event.integrationEventType,
    status: event.processingStatus,
    attempts: event.processingAttemptCount,
    lastError: event.lastError,
    createdAt: event.createdAt,
    relatedEntityType: event.relatedEntityType,
    relatedEntityId: event.relatedEntityId,
    processedAt: event.processedAt
  };
}

function parseCommand(rawText = '') {
  const text = String(rawText || '').trim();
  if (!text.startsWith('/')) return { text, command: '', arg: '' };
  const [head, ...rest] = text.split(/\s+/);
  const [commandOnly] = head.split('@');
  return {
    text,
    command: commandOnly.toLowerCase(),
    arg: rest.join(' ').trim()
  };
}

function normalizeIncomingText(rawText = '') {
  const text = String(rawText || '').trim();
  if (!text) return text;
  return MENU_TEXT_TO_COMMAND[text] || text;
}

function normalizeEventType(event = {}) {
  return event.integrationEventType || event.eventType || '-';
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toISOString().replace('T', ' ').replace('.000Z', ' UTC');
}

function truncate(value, max = 160) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '-';
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function eventLine(event) {
  return `${event.id} | ${event.status} | ${normalizeEventType(event)} | ${event.sourceSystem}`;
}

function eventInlineKeyboard(eventId, options = {}) {
  const rows = [[{ text: 'Подробнее', callback_data: `int:event:${eventId}` }]];
  if (options.canRetry !== false) rows[0].push({ text: 'Повторить', callback_data: `int:retry:${eventId}` });
  if (options.canIgnore !== false) rows.push([{ text: 'Игнорировать', callback_data: `int:ignore:${eventId}` }]);
  return { inline_keyboard: rows };
}

function formatEventSummaryCard(event) {
  const retryAvailable = event.status === 'failed' || PENDING_STATUSES.has(event.status);
  return [
    `🧩 ID: ${event.id}`,
    `Тип: ${normalizeEventType(event)}`,
    `Источник: ${event.sourceSystem || '-'}`,
    `Статус: ${event.status}`,
    `Создано: ${formatDate(event.createdAt)}`,
    `Ошибка: ${truncate(event.lastError || '-', 120)}`,
    `Retry: ${retryAvailable ? 'доступен' : 'не требуется / зависит от статуса'}`,
    `Reference: ${event.relatedEntityType || '-'} / ${event.relatedEntityId || '-'}`
  ].join('\n');
}

function formatEventCard(card) {
  const event = card.event;
  const logs = (card.logs || [])
    .slice(-8)
    .map((entry) => `• ${formatDate(entry.createdAt)} · ${entry.processingStatus || entry.status || '-'} · ${truncate(entry.message || '-', 180)}`)
    .join('\n') || 'Логи отсутствуют';
  const retryAvailable = event.processingStatus === 'failed' || PENDING_STATUSES.has(event.processingStatus);
  return [
    'Карточка integration event',
    `ID: ${event.id}`,
    `Тип: ${normalizeEventType(event)}`,
    `Источник: ${event.sourceSystem || '-'}`,
    `Статус: ${event.processingStatus}`,
    `Попытки: ${event.processingAttemptCount}`,
    `Создано: ${formatDate(event.createdAt)}`,
    `Обработано: ${formatDate(event.processedAt)}`,
    `Ошибка: ${truncate(event.lastError || '-', 300)}`,
    `Связанный объект: ${event.relatedEntityType || '-'} / ${event.relatedEntityId || '-'}`,
    `Retry path: ${retryAvailable ? 'доступен' : 'не требуется / зависит от статуса'}`,
    `Logs/reference: ${(card.logs || []).length ? `${card.logs.length} записей` : 'логов пока нет'}`,
    '',
    'Последние логи:',
    logs
  ].join('\n');
}

function buildHelpText() {
  return [
    '🤖 Integration Bot — рабочий бот оператора/админа для контроля integration events.',
    '',
    'Что здесь можно делать:',
    '• смотреть все события интеграции;',
    '• быстро открывать ошибки (failed) и очередь ожидания (pending);',
    '• проверять сводную статистику;',
    '• открывать карточку события и запускать retry / ignore;',
    '• выполнять самодиагностику, если бот или интеграции ведут себя нестабильно.',
    '',
    'Разделы на кнопках:',
    `• ${MAIN_MENU_LABELS.events} — последние integration events.`,
    `• ${MAIN_MENU_LABELS.failed} — события со статусом failed.`,
    `• ${MAIN_MENU_LABELS.pending} — события, которые ещё обрабатываются или ждут retry.`,
    `• ${MAIN_MENU_LABELS.stats} — краткая сводка по статусам.`,
    `• ${MAIN_MENU_LABELS.help} — эта инструкция.`,
    `• ${MAIN_MENU_LABELS.selfcheck} — проверка здоровья бота и хранилища.`,
    '',
    'Что такое integration event:',
    'Это запись о внешнем событии из интеграции (например, email/manual/1C), которое бот принял, обработал, завершил, отправил в retry или пометил как ошибку.',
    '',
    'Статусы событий:',
    '• received — событие принято, но ещё не обработано;',
    '• normalized — payload разобран и подготовлен;',
    '• processing — идёт обработка;',
    '• retry_scheduled — запрошен повторный прогон;',
    '• processed — событие успешно завершено;',
    '• failed — обработка завершилась ошибкой;',
    '• ignored — событие осознанно проигнорировано оператором или логикой.',
    '',
    'Как работать:',
    '1. Нажмите «Самодиагностика», если бот кажется нестабильным.',
    '2. Для проблемных кейсов откройте «Ошибки».',
    '3. Для зависших кейсов откройте «В ожидании».',
    '4. Нажмите «Подробнее» в карточке, чтобы увидеть логи и служебные поля.',
    '5. Нажмите «Повторить», если нужно заново прогнать событие.',
    '6. Нажмите «Игнорировать», если событие не должно обрабатываться дальше.',
    '',
    'Команды совместимости:',
    '/start',
    '/help',
    '/selfcheck или /diag',
    '/events',
    '/failed',
    '/pending',
    '/stats',
    '/event <id>',
    '/retry <id>',
    '/ignore <id>',
    '',
    'Когда использовать самодиагностику:',
    '• бот не отвечает как ожидается;',
    '• нужно быстро понять, видит ли он БД и integration events;',
    '• непонятно, есть ли токен, доступен ли retry path и есть ли последние события.'
  ].join('\n');
}

function buildStartText() {
  return [
    'Integration Bot запущен.',
    'Ниже основные кнопки для работы с integration events.',
    'Если нужно, используйте slash-команды как fallback: /help, /events, /failed, /pending, /stats, /selfcheck.'
  ].join('\n');
}

function buildStatsText(stats) {
  if (!stats.total) {
    return [
      'Статистика integration events пока пуста.',
      'События ещё не поступали или БД пустая.'
    ].join('\n');
  }
  return [
    '📊 Статистика integration events:',
    `Всего: ${stats.total}`,
    `Pending: ${stats.pending}`,
    `Processed: ${stats.processed}`,
    `Failed: ${stats.failed}`,
    `Ignored: ${stats.ignored}`,
    `Received: ${stats.received}`,
    `Normalized: ${stats.normalized}`,
    `Processing: ${stats.processing}`,
    `Retry scheduled: ${stats.retryScheduled}`,
    `Последнее событие: ${stats.latestEventAt ? formatDate(stats.latestEventAt) : 'нет данных'}`
  ].join('\n');
}

function buildSelfcheck({ config }) {
  const checks = [];
  const pushCheck = (name, ok, details, level = ok ? 'OK' : 'ERROR') => {
    checks.push({ name, ok: Boolean(ok), level, details });
  };

  pushCheck('Webhook handler', true, 'Запрос дошёл до integration bot handler.', 'OK');
  pushCheck('Bot token', Boolean(config?.telegramIntegrationBotToken), Boolean(config?.telegramIntegrationBotToken) ? 'TELEGRAM_INTEGRATION_BOT_TOKEN задан.' : 'Не задан TELEGRAM_INTEGRATION_BOT_TOKEN.', Boolean(config?.telegramIntegrationBotToken) ? 'OK' : 'ERROR');

  let runtime = null;
  try {
    runtime = db.getDbRuntimeInfo();
    pushCheck('File DB access', Boolean(runtime?.path), `SQLite: ${runtime?.path || 'path unavailable'}. exists=${runtime?.exists ? 'yes' : 'no'}. init=${runtime?.initStatus || 'unknown'}.`, runtime?.exists ? 'OK' : 'WARNING');
  } catch (error) {
    pushCheck('File DB access', false, `Ошибка чтения DB runtime: ${String(error?.message || error)}`);
  }

  let items = [];
  try {
    items = db.listIntegrationEvents({ limit: 200 });
    pushCheck('Integration events store', true, `Хранилище читается. Прочитано ${items.length} последних событий.`, 'OK');
  } catch (error) {
    pushCheck('Integration events store', false, `Не удалось прочитать integration events: ${String(error?.message || error)}`);
  }

  pushCheck('Route registration', true, 'Webhook route: POST /telegram/integration_bot/webhook.', 'OK');
  pushCheck('Handler dependencies', typeof db.listIntegrationEvents === 'function' && typeof db.getIntegrationEventCard === 'function' && typeof integrationService.retryIntegrationEvent === 'function', 'Проверены db.listIntegrationEvents, db.getIntegrationEventCard, integrationService.retryIntegrationEvent.', typeof db.listIntegrationEvents === 'function' && typeof db.getIntegrationEventCard === 'function' && typeof integrationService.retryIntegrationEvent === 'function' ? 'OK' : 'ERROR');

  try {
    const scheduled = db.listTasks(['scheduled', 'processing']);
    const staleProcessing = scheduled.filter((item) => item.status === 'processing').length;
    pushCheck('Scheduler/runtime', true, `Scheduler persistence доступна. Активных задач: ${scheduled.length}, processing: ${staleProcessing}.`, staleProcessing > 20 ? 'WARNING' : 'OK');
  } catch (error) {
    pushCheck('Scheduler/runtime', false, `Ошибка чтения scheduler tasks: ${String(error?.message || error)}`);
  }

  const stats = integrationService.integrationStats();
  const latestEvents = items.slice(0, 3).map((item) => `${item.id} (${item.processingStatus})`);
  pushCheck('Retry path', typeof integrationService.retryIntegrationEvent === 'function', typeof integrationService.retryIntegrationEvent === 'function' ? 'Функция retryIntegrationEvent доступна.' : 'retryIntegrationEvent недоступна.', typeof integrationService.retryIntegrationEvent === 'function' ? 'OK' : 'ERROR');
  pushCheck('Latest integration events', items.length > 0, items.length > 0 ? `Есть последние события: ${latestEvents.join(', ')}.` : 'Событий пока нет — это не авария, но проверить источники интеграции стоит.', items.length > 0 ? 'OK' : 'WARNING');
  pushCheck('Configuration audit', !(config?.envAudit?.requiredMissing || []).length, (config?.envAudit?.requiredMissing || []).length ? `Отсутствуют обязательные env: ${(config.envAudit.requiredMissing || []).join(', ')}` : 'Явных ошибок обязательной конфигурации не найдено.', (config?.envAudit?.requiredMissing || []).length ? 'WARNING' : 'OK');

  const hasError = checks.some((item) => item.level === 'ERROR');
  const hasWarning = checks.some((item) => item.level === 'WARNING');
  const overallStatus = hasError ? 'ERROR' : (hasWarning ? 'WARNING' : 'OK');
  const summary = hasError
    ? 'Есть критичные проблемы, которые мешают нормальной работе.'
    : (hasWarning ? 'Бот жив, но есть предупреждения, на которые стоит обратить внимание.' : 'Ключевые проверки пройдены, бот выглядит рабочим.');

  const text = [
    `Selfcheck: ${overallStatus}`,
    summary,
    '',
    'Ключевые проверки:',
    ...checks.map((item) => `${item.level === 'OK' ? '✅' : item.level === 'WARNING' ? '⚠️' : '❌'} ${item.name}: ${item.details}`),
    '',
    'Сводка по событиям:',
    `• всего: ${stats.total}`,
    `• failed: ${stats.failed}`,
    `• pending: ${stats.pending}`,
    `• processed: ${stats.processed}`,
    `• ignored: ${stats.ignored}`
  ].join('\n');

  return { overallStatus, summary, checks, stats, text };
}

function buildSectionHeader(title, items, emptyText) {
  if (!items.length) return emptyText;
  return `${title}\n${items.map((item) => `• ${eventLine(item)}`).join('\n')}`;
}

function getChatContext(body = {}) {
  if (body?.callback_query) {
    return {
      chatId: body.callback_query.message?.chat?.id,
      callbackId: body.callback_query.id,
      callbackData: String(body.callback_query.data || ''),
      text: String(body.callback_query.message?.text || ''),
      source: 'callback'
    };
  }
  return {
    chatId: body?.message?.chat?.id,
    callbackId: null,
    callbackData: '',
    text: String(body?.message?.text || ''),
    source: 'message'
  };
}

async function sendTelegramMessage(token, chatId, text, extra = {}) {
  if (!token || !chatId || !text) return false;
  return sendChannelMessage({ channel: 'telegram', token, recipientId: chatId, text, extra });
}

async function replyToIntegrationChat({ config, body, text, extra = {} }) {
  const token = config?.telegramIntegrationBotToken;
  const { chatId } = getChatContext(body);
  const sent = await sendTelegramMessage(token, chatId, text, extra);
  if (!sent) {
    logger.error('integration_bot sendMessage failed', {
      chatId,
      hasToken: Boolean(token),
      textPreview: String(text || '').slice(0, 80)
    });
  }
  return sent;
}

async function answerIntegrationCallback({ config, body, text }) {
  const token = config?.telegramIntegrationBotToken;
  const { callbackId } = getChatContext(body);
  if (!callbackId) return false;
  const answered = await answerChannelCallback({ channel: 'telegram', token, callbackId, text });
  if (!answered) {
    logger.error('integration_bot answerCallback failed', { callbackId, textPreview: String(text || '').slice(0, 80) });
  }
  return answered;
}

async function sendMenuMessage({ config, body, text }) {
  return replyToIntegrationChat({ config, body, text, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
}

async function sendEventList({ config, body, title, items, emptyText }) {
  const summaryText = buildSectionHeader(title, items, emptyText);
  await replyToIntegrationChat({ config, body, text: summaryText, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
  for (const item of items.slice(0, 5)) {
    await replyToIntegrationChat({ config, body, text: formatEventSummaryCard(item), extra: { reply_markup: eventInlineKeyboard(item.id, { canRetry: item.status === 'failed' || PENDING_STATUSES.has(item.status), canIgnore: item.status !== 'ignored' }) } });
  }
}

async function showEventCard({ config, body, id }) {
  const card = db.getIntegrationEventCard(id);
  if (!card) {
    const message = `Событие ${id} не найдено.`;
    await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
    return { ok: false, action: 'event_card', error: 'EVENT_NOT_FOUND', text: message };
  }
  const message = formatEventCard(card);
  await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: eventInlineKeyboard(id, { canRetry: card.event.processingStatus === 'failed' || PENDING_STATUSES.has(card.event.processingStatus), canIgnore: card.event.processingStatus !== 'ignored' }) } });
  return { ok: true, action: 'event_card', event: card.event, logs: card.logs, text: message };
}

async function retryEvent({ config, body, id }) {
  if (!id) {
    const message = 'Использование: /retry <id>';
    await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
    return { ok: false, action: 'retry', error: 'EVENT_ID_REQUIRED', text: message };
  }
  try {
    const event = await integrationService.retryIntegrationEvent(id);
    const message = `Повторная обработка запущена для ${id}. Текущий статус: ${event.processingStatus}.`;
    await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: eventInlineKeyboard(id, { canRetry: event.processingStatus === 'failed' || PENDING_STATUSES.has(event.processingStatus), canIgnore: event.processingStatus !== 'ignored' }) } });
    return { ok: true, action: 'retry', event: compact(event), text: message };
  } catch (error) {
    const errorMessage = String(error?.message || error);
    logger.error('integration_bot command error', { branch: 'retry', id, error: errorMessage });
    const message = `Не удалось повторить событие ${id}: ${errorMessage}`;
    await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
    return { ok: false, action: 'retry', error: errorMessage, text: message };
  }
}

async function ignoreEvent({ config, body, id }) {
  if (!id) {
    const message = 'Использование: /ignore <id>';
    await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
    return { ok: false, action: 'ignored', error: 'EVENT_ID_REQUIRED', text: message };
  }

  const updated = db.updateIntegrationEvent(id, { processingStatus: 'ignored' }, 'Marked ignored from integration bot');
  if (!updated) {
    const message = `Событие ${id} не найдено.`;
    await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: MAIN_REPLY_KEYBOARD } });
    return { ok: false, action: 'ignored', error: 'EVENT_NOT_FOUND', text: message };
  }

  const message = `Событие ${id} помечено как ignored.`;
  await replyToIntegrationChat({ config, body, text: message, extra: { reply_markup: eventInlineKeyboard(id, { canRetry: false, canIgnore: false }) } });
  return { ok: true, action: 'ignored', event: compact(updated), text: message };
}

async function processCommand({ command, arg, config, body }) {
  if (command === '/start') {
    const message = buildStartText();
    await sendMenuMessage({ config, body, text: message });
    return { ok: true, action: 'start', text: message, buttons: Object.values(MAIN_MENU_LABELS) };
  }

  if (command === '/help') {
    const message = buildHelpText();
    await sendMenuMessage({ config, body, text: message });
    return { ok: true, action: 'help', text: message };
  }

  if (command === '/selfcheck' || command === '/diag') {
    const payload = buildSelfcheck({ config });
    await sendMenuMessage({ config, body, text: payload.text });
    return { ok: payload.overallStatus !== 'ERROR', action: 'selfcheck', ...payload };
  }

  if (command === '/events') {
    try {
      const items = db.listIntegrationEvents({ limit: 10 }).map(compact);
      const message = items.length ? `Последние integration events: ${items.length}` : 'Нет событий интеграции.';
      await sendEventList({ config, body, title: 'Последние integration events:', items, emptyText: 'Нет событий интеграции.' });
      return { ok: true, action: 'events', items, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'events', error: String(error?.message || error) });
      const message = 'Не удалось прочитать integration events.';
      await sendMenuMessage({ config, body, text: message });
      return { ok: false, action: 'events', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/failed') {
    try {
      const items = db.listIntegrationEvents({ status: 'failed', limit: 10 }).map(compact);
      const message = items.length ? `Failed события: ${items.length}` : 'Нет ошибок интеграции.';
      await sendEventList({ config, body, title: 'Failed события:', items, emptyText: 'Нет ошибок интеграции.' });
      return { ok: true, action: 'failed', items, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'failed', error: String(error?.message || error) });
      const message = 'Не удалось получить failed события.';
      await sendMenuMessage({ config, body, text: message });
      return { ok: false, action: 'failed', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/pending') {
    try {
      const all = db.listIntegrationEvents({ limit: 50 });
      const items = all.filter((item) => PENDING_STATUSES.has(item.processingStatus)).map(compact);
      const message = items.length ? `Pending события: ${items.length}` : 'Нет pending событий.';
      await sendEventList({ config, body, title: 'Pending события:', items, emptyText: 'Нет pending событий.' });
      return { ok: true, action: 'pending', items, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'pending', error: String(error?.message || error) });
      const message = 'Не удалось получить pending события.';
      await sendMenuMessage({ config, body, text: message });
      return { ok: false, action: 'pending', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/stats') {
    const stats = integrationService.integrationStats();
    const message = buildStatsText(stats);
    await sendMenuMessage({ config, body, text: message });
    return { ok: true, action: 'stats', ...stats, text: message };
  }

  if (command === '/event') {
    if (!arg) {
      const message = 'Использование: /event <id>';
      await sendMenuMessage({ config, body, text: message });
      return { ok: false, action: 'event_card', error: 'EVENT_ID_REQUIRED', text: message };
    }
    try {
      return await showEventCard({ config, body, id: arg });
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'event', error: String(error?.message || error), id: arg });
      const message = 'Не удалось получить карточку integration event.';
      await sendMenuMessage({ config, body, text: message });
      return { ok: false, action: 'event_card', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/retry') return retryEvent({ config, body, id: arg });
  if (command === '/ignore') return ignoreEvent({ config, body, id: arg });

  const message = 'Неизвестная команда. Нажмите кнопку ниже или используйте /help.';
  await sendMenuMessage({ config, body, text: message });
  return { ok: true, action: 'unknown', text: message };
}

function parseCallbackAction(data = '') {
  const [prefix, action, ...rest] = String(data || '').split(':');
  if (prefix !== 'int' || !action) return null;
  return { action, id: rest.join(':') };
}

async function processCallback({ config, body }) {
  const { callbackData } = getChatContext(body);
  const parsed = parseCallbackAction(callbackData);
  logger.info('integration_bot callback received', { callbackData, parsed });

  if (!parsed) {
    await answerIntegrationCallback({ config, body, text: 'Неизвестная кнопка.' });
    const message = 'Кнопка не распознана. Используйте /start.';
    await sendMenuMessage({ config, body, text: message });
    return { ok: false, action: 'callback_unknown', error: 'UNKNOWN_CALLBACK', text: message };
  }

  await answerIntegrationCallback({ config, body, text: 'Обрабатываю…' });

  if (parsed.action === 'event') return showEventCard({ config, body, id: parsed.id });
  if (parsed.action === 'retry') return retryEvent({ config, body, id: parsed.id });
  if (parsed.action === 'ignore') return ignoreEvent({ config, body, id: parsed.id });

  const message = 'Действие кнопки пока не поддерживается.';
  await sendMenuMessage({ config, body, text: message });
  return { ok: false, action: 'callback_unknown', error: 'UNSUPPORTED_CALLBACK', text: message };
}

async function handleIntegrationBotWebhook({ body, config }) {
  const context = getChatContext(body);
  const normalizedText = normalizeIncomingText(context.text);
  const { text, command, arg } = parseCommand(normalizedText);
  logger.info('integration_bot incoming update', {
    source: context.source,
    text,
    command,
    arg,
    callbackData: context.callbackData,
    hasMessage: Boolean(body?.message),
    hasCallback: Boolean(body?.callback_query)
  });

  if (body?.callback_query) {
    const result = await processCallback({ config, body });
    logger.info('integration_bot command branch', { branch: result.action, via: 'callback' });
    return result;
  }

  if (!text) {
    const message = 'Пустая команда. Используйте /start или кнопки ниже.';
    await sendMenuMessage({ config, body, text: message });
    logger.info('integration_bot command branch', { branch: 'empty' });
    return { ok: true, action: 'empty', text: message };
  }

  const result = await processCommand({ command, arg, config, body });
  logger.info('integration_bot command branch', { branch: result.action, via: 'message' });
  return result;
}

function registerIntegrationBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/integration_bot/webhook', handler: handleIntegrationBotWebhook });
}

module.exports = {
  MAIN_MENU_LABELS,
  MAIN_REPLY_KEYBOARD,
  buildHelpText,
  buildSelfcheck,
  registerIntegrationBotRoutes,
  handleIntegrationBotWebhook,
  parseCommand
};
