const { integrationService } = require('../../core/application');

function ingestEmail(message) {
  return integrationService.receiveIntegrationEvent({
    sourceSystem: integrationService.INTEGRATION_SOURCES.EMAIL,
    eventType: integrationService.INTEGRATION_EVENT_TYPES.EMAIL_REQUEST_RECEIVED,
    rawPayload: message,
    dedupeKey: message?.threadId ? `email:${message.threadId}` : null
  });
}

module.exports = { ingestEmail };
