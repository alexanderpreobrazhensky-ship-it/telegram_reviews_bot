const db = require('../../infrastructure/db');
const { integrationService } = require('../../core/application');

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

async function handleIntegrationBotWebhook({ body }) {
  const text = String(body?.message?.text || '').trim();
  if (text === '/start') {
    return {
      action: 'start',
      menu: ['/events', '/failed', '/pending', '/stats', '/event <id>', '/retry <id>']
    };
  }
  if (text === '/events') {
    return { action: 'events', items: db.listIntegrationEvents({ limit: 10 }).map(compact) };
  }
  if (text === '/failed') {
    return { action: 'failed', items: db.listIntegrationEvents({ status: 'failed', limit: 20 }).map(compact) };
  }
  if (text === '/pending') {
    const all = db.listIntegrationEvents({ limit: 50 });
    return { action: 'pending', items: all.filter((item) => ['received', 'normalized', 'processing', 'retry_scheduled'].includes(item.processingStatus)).map(compact) };
  }
  if (text === '/stats') {
    return { action: 'stats', ...integrationService.integrationStats() };
  }
  if (text.startsWith('/event ')) {
    const id = text.split(' ')[1];
    const card = db.getIntegrationEventCard(id);
    return card ? { action: 'event_card', ...card } : { ok: false, error: 'EVENT_NOT_FOUND' };
  }
  if (text.startsWith('/retry ')) {
    const id = text.split(' ')[1];
    try {
      const event = integrationService.retryIntegrationEvent(id);
      return { ok: true, action: 'retry', event: compact(event) };
    } catch (error) {
      return { ok: false, error: String(error.message || error) };
    }
  }
  if (text.startsWith('/ignore ')) {
    const id = text.split(' ')[1];
    const updated = db.updateIntegrationEvent(id, { processingStatus: 'ignored' }, 'Marked ignored from integration bot');
    return updated ? { ok: true, action: 'ignored', event: compact(updated) } : { ok: false, error: 'EVENT_NOT_FOUND' };
  }
  return { ok: true, action: 'help', message: 'Use /events /failed /pending /stats /event <id> /retry <id>' };
}

function registerIntegrationBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/integration_bot/webhook', handler: handleIntegrationBotWebhook });
}

module.exports = { registerIntegrationBotRoutes, handleIntegrationBotWebhook };
