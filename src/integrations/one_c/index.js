const { integrationService } = require('../../core/application');

function oneCSyncPlaceholder(eventType, payload) {
  return integrationService.receiveIntegrationEvent({
    sourceSystem: integrationService.INTEGRATION_SOURCES.ONE_C,
    eventType,
    rawPayload: payload,
    dedupeKey: payload?.externalId ? `one_c:${eventType}:${payload.externalId}` : null
  });
}

module.exports = { oneCSyncPlaceholder };
