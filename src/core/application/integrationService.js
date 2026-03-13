const db = require('../../infrastructure/db');
const { REQUEST_TYPES } = require('../domain');

const INTEGRATION_SOURCES = Object.freeze({
  EMAIL: 'email',
  ONE_C: 'one_c',
  MANUAL_IMPORT: 'manual_import',
  SYSTEM: 'system'
});

const INTEGRATION_EVENT_TYPES = Object.freeze({
  EMAIL_REQUEST_RECEIVED: 'email_request_received',
  ONE_C_CLIENT_SYNC: 'one_c_client_sync',
  ONE_C_VEHICLE_SYNC: 'one_c_vehicle_sync',
  ONE_C_VISIT_SYNC: 'one_c_visit_sync',
  ONE_C_RECOMMENDATION_SYNC: 'one_c_recommendation_sync',
  MANUAL_REQUEST_IMPORT: 'manual_request_import',
  MANUAL_CLIENT_SYNC: 'manual_client_sync',
  MANUAL_RECOMMENDATION_SYNC: 'manual_recommendation_sync'
});

function normalizePhone(rawPhone) {
  if (!rawPhone) return null;
  const digits = String(rawPhone).replace(/[^\d+]/g, '');
  return digits.startsWith('+') ? digits : `+${digits}`;
}

function parseEmailPayload(raw = {}) {
  const fromRaw = String(raw.from || '');
  const fromEmail = fromRaw.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/)?.[1] || null;
  const body = String(raw.body || '');
  const subject = String(raw.subject || '');
  const phone = normalizePhone(body.match(/(\+?\d[\d\s\-()]{8,}\d)/)?.[1] || null);
  const name = body.match(/(?:имя|name)[:\s]+([^\n,]+)/i)?.[1]?.trim() || subject.match(/^[^-:]+/)?.[0]?.trim() || null;
  const vin = body.match(/VIN[:\s]+([A-HJ-NPR-Z0-9]{11,17})/i)?.[1] || null;
  const text = body.slice(0, 1500);

  let requestType = REQUEST_TYPES.CONSULTATION;
  if (/гарант|warranty/i.test(`${subject} ${body}`)) requestType = REQUEST_TYPES.WARRANTY;
  if (/запчаст|parts/i.test(`${subject} ${body}`)) requestType = REQUEST_TYPES.PARTS;
  if (/запис|service|ремонт|диагност/i.test(`${subject} ${body}`)) requestType = REQUEST_TYPES.SERVICE;

  return {
    sender: { raw: fromRaw, email: fromEmail, displayName: name },
    message: {
      subject,
      body: text,
      receivedAt: raw.receivedAt || new Date().toISOString(),
      attachments: Array.isArray(raw.attachments) ? raw.attachments : []
    },
    extracted: { fullName: name, phone, vin, requestType, text },
    sourceOfTruth: 'external',
    externalIds: raw.threadId ? { email_thread: String(raw.threadId) } : {}
  };
}

function normalizeOneCPayload(eventType, raw = {}) {
  const common = {
    sourceOfTruth: 'external',
    sourceSystem: INTEGRATION_SOURCES.ONE_C,
    externalIds: raw.externalId ? { one_c: String(raw.externalId) } : {}
  };

  if (eventType === INTEGRATION_EVENT_TYPES.ONE_C_CLIENT_SYNC) {
    return {
      ...common,
      entityType: 'client',
      expectedRawShape: ['externalId', 'fullName', 'phone', 'email'],
      mapping: {
        externalIdField: 'externalId',
        fullNameField: 'fullName',
        phoneField: 'phone',
        emailField: 'email'
      },
      payload: {
        fullName: raw.fullName || null,
        phone: normalizePhone(raw.phone || null),
        email: raw.email || null
      }
    };
  }

  if (eventType === INTEGRATION_EVENT_TYPES.ONE_C_VEHICLE_SYNC) {
    return {
      ...common,
      entityType: 'vehicle',
      expectedRawShape: ['externalId', 'vin', 'plateNumber', 'brand', 'model', 'clientExternalId'],
      mapping: {
        externalIdField: 'externalId',
        vinField: 'vin',
        plateField: 'plateNumber',
        clientExternalIdField: 'clientExternalId'
      },
      payload: {
        vin: raw.vin || null,
        plateNumber: raw.plateNumber || null,
        brand: raw.brand || null,
        model: raw.model || null,
        clientExternalId: raw.clientExternalId || null
      }
    };
  }

  if (eventType === INTEGRATION_EVENT_TYPES.ONE_C_VISIT_SYNC) {
    return {
      ...common,
      entityType: 'visit',
      expectedRawShape: ['externalId', 'clientExternalId', 'vehicleExternalId', 'status', 'scheduledAt'],
      mapping: {
        externalIdField: 'externalId',
        clientExternalIdField: 'clientExternalId',
        vehicleExternalIdField: 'vehicleExternalId'
      },
      payload: {
        clientExternalId: raw.clientExternalId || null,
        vehicleExternalId: raw.vehicleExternalId || null,
        status: raw.status || 'scheduled',
        scheduledAt: raw.scheduledAt || null
      }
    };
  }

  return {
    ...common,
    entityType: 'recommendation',
    expectedRawShape: ['externalId', 'clientExternalId', 'vehicleExternalId', 'text', 'severity'],
    mapping: {
      externalIdField: 'externalId',
      clientExternalIdField: 'clientExternalId',
      vehicleExternalIdField: 'vehicleExternalId'
    },
    payload: {
      clientExternalId: raw.clientExternalId || null,
      vehicleExternalId: raw.vehicleExternalId || null,
      text: raw.text || null,
      severity: raw.severity || 'normal'
    }
  };
}

function normalizeIntegrationPayload(event) {
  if (event.sourceSystem === INTEGRATION_SOURCES.EMAIL || event.eventType === INTEGRATION_EVENT_TYPES.EMAIL_REQUEST_RECEIVED) {
    return parseEmailPayload(event.rawPayload);
  }
  if (event.sourceSystem === INTEGRATION_SOURCES.ONE_C) {
    return normalizeOneCPayload(event.eventType, event.rawPayload);
  }
  return {
    sourceSystem: event.sourceSystem,
    sourceOfTruth: 'external',
    payload: event.rawPayload,
    externalIds: event.rawPayload?.externalId ? { external: String(event.rawPayload.externalId) } : {}
  };
}

function findExistingClient({ phone, fullName, externalIds = {} }) {
  const store = db.readStore();
  const byExternal = Object.entries(externalIds).map(([system, value]) => store.clients.find((client) => client.externalIds?.[system] === value)).find(Boolean);
  if (byExternal) return { client: byExternal, confidence: 'high' };
  if (phone) {
    const byPhone = store.clients.find((client) => client.phone === phone);
    if (byPhone) return { client: byPhone, confidence: 'high' };
  }
  if (phone && fullName) {
    const byCombo = store.clients.find((client) => client.phone === phone && String(client.fullName || '').toLowerCase() === String(fullName || '').toLowerCase());
    if (byCombo) return { client: byCombo, confidence: 'medium' };
  }
  return { client: null, confidence: 'none' };
}

function processEmailEvent(event, normalized) {
  const extracted = normalized.extracted || {};
  const dedupeMatch = findExistingClient({ phone: extracted.phone, fullName: extracted.fullName, externalIds: normalized.externalIds });
  const needsManualReview = dedupeMatch.confidence === 'medium';

  const client = db.upsertClient({ fullName: extracted.fullName || normalized.sender?.displayName || 'Email client', phone: extracted.phone, telegramId: null });
  db.applyEntitySyncMetadata({
    collection: 'clients',
    entityId: client.id,
    metadata: {
      externalIds: normalized.externalIds,
      sourceSystem: INTEGRATION_SOURCES.EMAIL,
      sourceOfTruth: normalized.sourceOfTruth,
      lastSyncedAt: new Date().toISOString(),
      needsManualReview
    }
  });

  const vehicle = db.upsertVehicle({ clientId: client.id, vin: extracted.vin, brand: null, model: null, year: null, plateNumber: null });
  if (vehicle) {
    db.applyEntitySyncMetadata({
      collection: 'vehicles',
      entityId: vehicle.id,
      metadata: {
        sourceSystem: INTEGRATION_SOURCES.EMAIL,
        sourceOfTruth: normalized.sourceOfTruth,
        lastSyncedAt: new Date().toISOString(),
        needsManualReview
      }
    });
  }

  const request = db.createRequest({
    clientId: client.id,
    vehicleId: vehicle?.id || null,
    requestType: extracted.requestType || REQUEST_TYPES.CONSULTATION,
    description: extracted.text || normalized.message?.body || '',
    sourceChannel: INTEGRATION_SOURCES.EMAIL
  });

  db.applyEntitySyncMetadata({
    collection: 'requests',
    entityId: request.id,
    metadata: {
      externalIds: normalized.externalIds,
      sourceSystem: INTEGRATION_SOURCES.EMAIL,
      sourceOfTruth: normalized.sourceOfTruth,
      lastSyncedAt: new Date().toISOString(),
      needsManualReview
    }
  });

  db.createCommunicationEvent({
    clientId: client.id,
    requestId: request.id,
    source: INTEGRATION_SOURCES.EMAIL,
    payload: {
      action: 'email_ingested',
      sender: normalized.sender,
      subject: normalized.message?.subject || '',
      attachments: normalized.message?.attachments || []
    }
  });

  return { relatedEntityType: 'request', relatedEntityId: request.id };
}

function processIntegrationEvent(eventId) {
  const event = db.getIntegrationEventById(eventId);
  if (!event) throw new Error('INTEGRATION_EVENT_NOT_FOUND');

  db.updateIntegrationEvent(eventId, { processingStatus: 'processing', processingAttemptCount: event.processingAttemptCount + 1 }, 'Processing started');

  try {
    const normalizedPayload = normalizeIntegrationPayload(event);
    db.updateIntegrationEvent(eventId, { processingStatus: 'normalized', normalizedPayload }, 'Payload normalized');

    let result = { relatedEntityType: null, relatedEntityId: null };
    if (event.eventType === INTEGRATION_EVENT_TYPES.EMAIL_REQUEST_RECEIVED || event.eventType === INTEGRATION_EVENT_TYPES.MANUAL_REQUEST_IMPORT) {
      result = processEmailEvent(event, normalizedPayload);
    } else if (event.sourceSystem === INTEGRATION_SOURCES.ONE_C) {
      if (event.eventType === INTEGRATION_EVENT_TYPES.ONE_C_RECOMMENDATION_SYNC) {
        const payload = normalizedPayload.payload || {};
        const rec = db.upsertRecommendationFromSync({
          externalId: event.rawPayload?.externalId || null,
          clientId: null,
          text: payload.text || '',
          severity: payload.severity || 'normal',
          status: 'actual'
        });
        result = { relatedEntityType: 'recommendation', relatedEntityId: rec.id };
      } else {
        db.updateIntegrationEvent(eventId, { processingStatus: 'ignored' }, '1C skeleton received and normalized');
        return db.getIntegrationEventById(eventId);
      }
    } else {
      db.updateIntegrationEvent(eventId, { processingStatus: 'ignored' }, 'Unsupported event type in MVP');
      return db.getIntegrationEventById(eventId);
    }

    db.updateIntegrationEvent(eventId, { processingStatus: 'processed', relatedEntityType: result.relatedEntityType, relatedEntityId: result.relatedEntityId, lastError: null }, 'Event processed');
    return db.getIntegrationEventById(eventId);
  } catch (error) {
    db.updateIntegrationEvent(eventId, { processingStatus: 'failed', lastError: String(error.message || error) }, 'Processing failed');
    throw error;
  }
}

function receiveIntegrationEvent({ sourceSystem, eventType, rawPayload, dedupeKey = null }) {
  const event = db.createIntegrationEvent({ sourceSystem, eventType, rawPayload, dedupeKey });
  try {
    return processIntegrationEvent(event.id);
  } catch {
    return db.getIntegrationEventById(event.id);
  }
}

function retryIntegrationEvent(eventId) {
  const event = db.getIntegrationEventById(eventId);
  if (!event) throw new Error('INTEGRATION_EVENT_NOT_FOUND');
  db.updateIntegrationEvent(eventId, { processingStatus: 'retry_scheduled' }, 'Manual retry scheduled');
  return processIntegrationEvent(eventId);
}

function markIntegrationEventFailed(eventId, error) {
  return db.updateIntegrationEvent(eventId, { processingStatus: 'failed', lastError: String(error || 'unknown_error') }, 'Manually marked as failed');
}

function integrationStats() {
  const items = db.listIntegrationEvents({ limit: 500 });
  return {
    received: items.filter((item) => item.processingStatus === 'received').length,
    processed: items.filter((item) => item.processingStatus === 'processed').length,
    failed: items.filter((item) => item.processingStatus === 'failed').length
  };
}

module.exports = {
  INTEGRATION_SOURCES,
  INTEGRATION_EVENT_TYPES,
  receiveIntegrationEvent,
  normalizeIntegrationPayload,
  processIntegrationEvent,
  retryIntegrationEvent,
  markIntegrationEventFailed,
  integrationStats
};
