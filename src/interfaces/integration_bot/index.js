const db = require('../../infrastructure/db');
const { integrationService } = require('../../core/application');
const logger = require('../../infrastructure/logging/logger');

const PENDING_STATUSES = new Set(['received', 'normalized', 'processing', 'retry_scheduled']);

function compact(event) {
  return {
    id: event.id,
    sourceSystem: event.sourceSystem,
    eventType: event.eventType,
    status: event.processingStatus,
    attempts: event.processingAttemptCount,
    lastError: event.lastError,
    createdAt: event.createdAt,
    relatedEntityType: event.relatedEntityType,
    relatedEntityId: event.relatedEntityId
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

function eventLine(event) {
  return `${event.id} | ${event.status} | ${event.eventType} | ${event.sourceSystem}`;
}

function formatEventCard(card) {
  const event = card.event;
  const logs = (card.logs || [])
    .map((entry) => `${entry.createdAt} | ${entry.status} | ${entry.message || '-'}`)
    .join('\n') || 'Логи отсутствуют';
  return [
    `ID: ${event.id}`,
    `Статус: ${event.processingStatus}`,
    `Источник: ${event.sourceSystem}`,
    `Тип: ${event.eventType}`,
    `Попытки: ${event.processingAttemptCount}`,
    `Ошибка: ${event.lastError || '-'}`,
    `Связь: ${event.relatedEntityType || '-'} / ${event.relatedEntityId || '-'}`,
    `Создано: ${event.createdAt || '-'}`,
    `Обработано: ${event.processedAt || '-'}`,
    `Логи:\n${logs}`
  ].join('\n');
}

async function sendTelegramMessage(token, chatId, text) {
  if (!token || !chatId || !text) return false;
  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text })
  }).catch(() => null);
  return Boolean(response?.ok);
}

async function replyToIntegrationChat({ config, body, text }) {
  const token = config?.telegramIntegrationBotToken;
  const chatId = body?.message?.chat?.id;
  const sent = await sendTelegramMessage(token, chatId, text);
  if (!sent) {
    logger.error('integration_bot sendMessage failed', {
      chatId,
      hasToken: Boolean(token),
      textPreview: String(text || '').slice(0, 80)
    });
  }
  return sent;
}

async function handleIntegrationBotWebhook({ body, config }) {
  const { text, command, arg } = parseCommand(body?.message?.text || '');
  logger.info('integration_bot incoming text', { text, command, arg });

  if (!text) {
    const message = 'Пустая команда. Используйте /start.';
    await replyToIntegrationChat({ config, body, text: message });
    logger.info('integration_bot command branch', { branch: 'empty' });
    return { ok: true, action: 'empty', text: message };
  }

  if (command === '/start') {
    const menu = ['/events', '/failed', '/pending', '/stats', '/event <id>', '/retry <id>', '/ignore <id>'];
    const message = `Команды integration bot:\n${menu.join('\n')}`;
    await replyToIntegrationChat({ config, body, text: message });
    logger.info('integration_bot command branch', { branch: 'start' });
    return { ok: true, action: 'start', menu, text: message };
  }

  if (command === '/events') {
    try {
      const items = db.listIntegrationEvents({ limit: 10 }).map(compact);
      const message = items.length ? `Последние integration events:\n${items.map(eventLine).join('\n')}` : 'Событий пока нет.';
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'events', count: items.length });
      return { ok: true, action: 'events', items, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'events', error: String(error?.message || error) });
      const message = 'Не удалось прочитать integration events.';
      await replyToIntegrationChat({ config, body, text: message });
      return { ok: false, action: 'events', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/failed') {
    try {
      const items = db.listIntegrationEvents({ status: 'failed', limit: 20 }).map(compact);
      const message = items.length ? `Failed события:\n${items.map(eventLine).join('\n')}` : 'Failed событий пока нет.';
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'failed', count: items.length });
      return { ok: true, action: 'failed', items, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'failed', error: String(error?.message || error) });
      const message = 'Не удалось получить failed события.';
      await replyToIntegrationChat({ config, body, text: message });
      return { ok: false, action: 'failed', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/pending') {
    try {
      const all = db.listIntegrationEvents({ limit: 50 });
      const items = all.filter((item) => PENDING_STATUSES.has(item.processingStatus)).map(compact);
      const message = items.length ? `Pending события:\n${items.map(eventLine).join('\n')}` : 'Pending событий пока нет.';
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'pending', count: items.length });
      return { ok: true, action: 'pending', items, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'pending', error: String(error?.message || error) });
      const message = 'Не удалось получить pending события.';
      await replyToIntegrationChat({ config, body, text: message });
      return { ok: false, action: 'pending', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/stats') {
    const stats = integrationService.integrationStats();
    const message = [
      'Статистика integration events:',
      `Всего: ${stats.total}`,
      `received: ${stats.received}`,
      `processing: ${stats.processing}`,
      `processed: ${stats.processed}`,
      `failed: ${stats.failed}`,
      `ignored: ${stats.ignored}`
    ].join('\n');
    await replyToIntegrationChat({ config, body, text: message });
    logger.info('integration_bot command branch', { branch: 'stats' });
    return { ok: true, action: 'stats', ...stats, text: message };
  }

  if (command === '/event') {
    const id = arg;
    if (!id) {
      const message = 'Использование: /event <id>';
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'event_missing_id' });
      return { ok: false, action: 'event_card', error: 'EVENT_ID_REQUIRED', text: message };
    }
    try {
      const card = db.getIntegrationEventCard(id);
      if (!card) {
        const message = `Событие ${id} не найдено.`;
        await replyToIntegrationChat({ config, body, text: message });
        logger.info('integration_bot command branch', { branch: 'event_not_found' });
        return { ok: false, action: 'event_card', error: 'EVENT_NOT_FOUND', text: message };
      }
      const message = formatEventCard(card);
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'event_card', id });
      return { ok: true, action: 'event_card', ...card, text: message };
    } catch (error) {
      logger.error('integration_bot integration events read error', { branch: 'event', error: String(error?.message || error), id });
      const message = 'Не удалось получить карточку integration event.';
      await replyToIntegrationChat({ config, body, text: message });
      return { ok: false, action: 'event_card', error: 'EVENTS_READ_FAILED', text: message };
    }
  }

  if (command === '/retry') {
    const id = arg;
    if (!id) {
      const message = 'Использование: /retry <id>';
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'retry_missing_id' });
      return { ok: false, action: 'retry', error: 'EVENT_ID_REQUIRED', text: message };
    }
    try {
      const event = integrationService.retryIntegrationEvent(id);
      const message = `Повторная обработка запущена для ${id}. Текущий статус: ${event.processingStatus}.`;
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'retry', id });
      return { ok: true, action: 'retry', event: compact(event), text: message };
    } catch (error) {
      const errorMessage = String(error?.message || error);
      logger.error('integration_bot command error', { branch: 'retry', id, error: errorMessage });
      const message = `Не удалось повторить событие ${id}: ${errorMessage}`;
      await replyToIntegrationChat({ config, body, text: message });
      return { ok: false, action: 'retry', error: errorMessage, text: message };
    }
  }

  if (command === '/ignore') {
    const id = arg;
    if (!id) {
      const message = 'Использование: /ignore <id>';
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'ignore_missing_id' });
      return { ok: false, action: 'ignored', error: 'EVENT_ID_REQUIRED', text: message };
    }

    const updated = db.updateIntegrationEvent(id, { processingStatus: 'ignored' }, 'Marked ignored from integration bot');
    if (!updated) {
      const message = `Событие ${id} не найдено.`;
      await replyToIntegrationChat({ config, body, text: message });
      logger.info('integration_bot command branch', { branch: 'ignore_not_found' });
      return { ok: false, action: 'ignored', error: 'EVENT_NOT_FOUND', text: message };
    }

    const message = `Событие ${id} помечено как ignored.`;
    await replyToIntegrationChat({ config, body, text: message });
    logger.info('integration_bot command branch', { branch: 'ignore', id });
    return { ok: true, action: 'ignored', event: compact(updated), text: message };
  }

  const message = 'Неизвестная команда. Используйте /start.';
  await replyToIntegrationChat({ config, body, text: message });
  logger.info('integration_bot command branch', { branch: 'help' });
  return { ok: true, action: 'help', message, text: message };
}

function registerIntegrationBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/integration_bot/webhook', handler: handleIntegrationBotWebhook });
}

module.exports = { registerIntegrationBotRoutes, handleIntegrationBotWebhook, parseCommand };
