const crypto = require('node:crypto');
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

const TBUSINESS_SENDER_PATTERNS = [/emails\.tinsurance\.ru$/i, /@tinsurance\.ru$/i, /@tbank\.ru$/i];
const TBUSINESS_SUBJECT_PATTERNS = [/Направление\s*№/i, /\bTRM-[A-Z0-9-]+/i];
const TBUSINESS_BODY_PATTERNS = [
  /Направление\s*[—-]\s*во вложении/i,
  /возьмите заявку в работу/i,
  /100% стоимости ремонта/i,
  /согласовывать со страховой не нужно/i
];

let runtimeHooks = {
  masterNotifier: async () => ({ ok: false, reason: 'master_notifier_not_configured' }),
  aiService: null,
  logger: console
};

function configureIntegrationRuntime({ masterNotifier = null, aiService = null, logger = null } = {}) {
  if (typeof masterNotifier === 'function') runtimeHooks.masterNotifier = masterNotifier;
  if (aiService) runtimeHooks.aiService = aiService;
  if (logger) runtimeHooks.logger = logger;
}

function boolEnv(name, fallback = false) {
  const raw = process.env[name];
  if (raw === undefined || raw === null || raw === '') return fallback;
  return String(raw).toLowerCase() === 'true';
}

function normalizePhone(rawPhone) {
  if (!rawPhone) return null;
  const digits = String(rawPhone).replace(/\D/g, '');
  if (!digits) return null;
  if (digits.length === 10) return `+7${digits}`;
  if (digits.length === 11 && (digits.startsWith('7') || digits.startsWith('8'))) return `+7${digits.slice(1)}`;
  if (digits.length > 11 && digits.startsWith('7')) return `+${digits}`;
  return digits.startsWith('+') ? digits : `+${digits}`;
}

function normalizeVin(rawVin) {
  if (!rawVin) return null;
  const vin = String(rawVin).trim().toUpperCase();
  if (!vin || vin.startsWith('NO_VIN_')) return null;
  if (!/^[A-HJ-NPR-Z0-9]{11,17}$/.test(vin)) return null;
  return vin;
}

function buildHash(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest('hex');
}

function parseField(text, patterns = []) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return String(match[1]).trim();
  }
  return null;
}

function extractFieldsFromText(text) {
  const content = String(text || '');
  const fields = {
    fullName: parseField(content, [/(?:ФИО|Клиент|Name)[:\s]+([^\n]+)/i]),
    phone: normalizePhone(parseField(content, [/(?:Телефон|Phone)[:\s]+([^\n]+)/i, /(\+?\d[\d\s()\-]{8,}\d)/])),
    brandModel: parseField(content, [/(?:Марка\/модель|Автомобиль|ТС)[:\s]+([^\n]+)/i]),
    plateNumber: parseField(content, [/(?:Госномер|ГРЗ|Номер авто)[:\s]+([^\n]+)/i]),
    vinRaw: parseField(content, [/(?:VIN)[:\s]+([A-Za-z0-9_\-]+)/i]),
    directionNumber: parseField(content, [/(?:Направление\s*№|Номер направления)[:\s]*([A-Za-z0-9\-/]+)/i]),
    claimNumber: parseField(content, [/(?:Номер убытка|Убыток)[:\s]*([A-Za-z0-9\-/]+)/i]),
    email: parseField(content, [/(?:E-?mail|Почта клиента)[:\s]+([^\n\s,;]+)/i]),
    year: parseField(content, [/(?:Год выпуска|Год)[:\s]+(\d{4})/i]),
    serviceAddress: parseField(content, [/(?:Адрес СТОА|СТОА)[:\s]+([^\n]+)/i]),
    specialConditions: parseField(content, [/(?:Спецусловия|Особые условия)[:\s]+([^\n]+)/i])
  };
  return {
    ...fields,
    vin: normalizeVin(fields.vinRaw),
    text: content.slice(0, 15000)
  };
}

function scoreTBusinessDetection({ fromEmail, subject, body, attachments = [] }) {
  let score = 0;
  const reasons = [];

  if (TBUSINESS_SENDER_PATTERNS.some((rx) => rx.test(fromEmail || ''))) {
    score += 4;
    reasons.push('sender_pattern');
  }
  if (TBUSINESS_SUBJECT_PATTERNS.some((rx) => rx.test(subject || ''))) {
    score += 3;
    reasons.push('subject_pattern');
  }
  const bodyHits = TBUSINESS_BODY_PATTERNS.filter((rx) => rx.test(body || '')).length;
  if (bodyHits) {
    score += Math.min(3, bodyHits);
    reasons.push(`body_phrases:${bodyHits}`);
  }
  const pdfLike = attachments.some((item) => String(item.contentType || '').toLowerCase().includes('pdf') || String(item.filename || '').toLowerCase().endsWith('.pdf'));
  if (pdfLike) {
    score += 2;
    reasons.push('pdf_attachment');
  }

  return {
    isTBusiness: score >= 5,
    score,
    reasons
  };
}

function chooseRequestType(payloadText) {
  const haystack = String(payloadText || '');
  if (/гарант|warranty/i.test(haystack)) return REQUEST_TYPES.WARRANTY;
  if (/запчаст|parts/i.test(haystack)) return REQUEST_TYPES.PARTS;
  if (/ремонт|service|диагност|стоа|направление/i.test(haystack)) return REQUEST_TYPES.SERVICE;
  return REQUEST_TYPES.CONSULTATION;
}

function parseEmailPayload(raw = {}) {
  const fromRaw = String(raw.from || raw.sender || '');
  const fromEmail = fromRaw.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/)?.[1] || null;
  const subject = String(raw.subject || '');
  const body = String(raw.body || raw.text || '');
  const attachmentTexts = Array.isArray(raw.attachments)
    ? raw.attachments.map((item) => String(item.extractedText || '')).filter(Boolean)
    : [];
  const bodyFields = extractFieldsFromText(body);
  const pdfFields = extractFieldsFromText(attachmentTexts.join('\n'));

  const merged = {
    fullName: pdfFields.fullName || bodyFields.fullName || null,
    phone: pdfFields.phone || bodyFields.phone || null,
    vin: pdfFields.vin || bodyFields.vin || null,
    plateNumber: pdfFields.plateNumber || bodyFields.plateNumber || null,
    brandModel: pdfFields.brandModel || bodyFields.brandModel || null,
    directionNumber: pdfFields.directionNumber || bodyFields.directionNumber || null,
    claimNumber: pdfFields.claimNumber || bodyFields.claimNumber || null,
    email: pdfFields.email || bodyFields.email || null,
    year: pdfFields.year || bodyFields.year || null,
    serviceAddress: pdfFields.serviceAddress || bodyFields.serviceAddress || null,
    specialConditions: pdfFields.specialConditions || bodyFields.specialConditions || null,
    text: [bodyFields.text, ...attachmentTexts].filter(Boolean).join('\n').slice(0, 15000)
  };

  const conflicts = [];
  for (const key of ['fullName', 'phone', 'vin', 'plateNumber', 'directionNumber', 'claimNumber']) {
    if (bodyFields[key] && pdfFields[key] && String(bodyFields[key]).toLowerCase() !== String(pdfFields[key]).toLowerCase()) {
      conflicts.push({ field: key, body: bodyFields[key], pdf: pdfFields[key] });
    }
  }

  const detection = scoreTBusinessDetection({ fromEmail, subject, body, attachments: raw.attachments || [] });

  const messageId = String(raw.messageId || raw.message_id || '').trim() || null;
  const date = String(raw.date || raw.receivedAt || new Date().toISOString());
  const bodyHash = buildHash(body);
  const normalizedContentHash = buildHash(`${subject}\n${merged.text}\n${JSON.stringify((raw.attachments || []).map((item) => ({ filename: item.filename, size: item.size || 0 })))}`);
  const attachmentFingerprint = buildHash((raw.attachments || []).map((a) => `${a.filename || ''}:${a.size || 0}:${a.contentType || ''}`).join('|'));

  const requestType = chooseRequestType(`${subject}\n${merged.text}`);

  return {
    sender: { raw: fromRaw, email: fromEmail, displayName: merged.fullName || fromRaw },
    message: {
      messageId,
      subject,
      body: body.slice(0, 10000),
      receivedAt: date,
      attachments: Array.isArray(raw.attachments) ? raw.attachments : []
    },
    extracted: { ...merged, requestType },
    bodyExtracted: bodyFields,
    pdfExtracted: pdfFields,
    conflicts,
    detection,
    sourceOfTruth: 'external',
    externalIds: {
      ...(raw.threadId ? { email_thread: String(raw.threadId) } : {}),
      ...(merged.directionNumber ? { direction_number: merged.directionNumber } : {}),
      ...(merged.claimNumber ? { claim_number: merged.claimNumber } : {})
    },
    hashes: { bodyHash, normalizedContentHash, attachmentFingerprint }
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
      payload: { fullName: raw.fullName || null, phone: normalizePhone(raw.phone || null), email: raw.email || null }
    };
  }

  if (eventType === INTEGRATION_EVENT_TYPES.ONE_C_VEHICLE_SYNC) {
    return {
      ...common,
      entityType: 'vehicle',
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
  if (event.sourceSystem === INTEGRATION_SOURCES.ONE_C) return normalizeOneCPayload(event.eventType, event.rawPayload);
  return {
    sourceSystem: event.sourceSystem,
    sourceOfTruth: 'external',
    payload: event.rawPayload,
    externalIds: event.rawPayload?.externalId ? { external: String(event.rawPayload.externalId) } : {}
  };
}

function findExistingClientMatch({ phone, fullName, vin }) {
  const store = db.readStore();
  const byPhone = boolEnv('EMAIL_MATCH_PHONE_ENABLED', true) && phone
    ? store.clients.find((client) => normalizePhone(client.phone) === normalizePhone(phone))
    : null;
  if (byPhone) return { client: byPhone, basis: 'phone', confidence: 0.98 };

  const byFio = boolEnv('EMAIL_MATCH_FIO_ENABLED', true) && fullName
    ? store.clients.find((client) => String(client.fullName || '').trim().toLowerCase() === String(fullName || '').trim().toLowerCase())
    : null;
  if (byFio) return { client: byFio, basis: 'fio', confidence: 0.72 };

  const realVin = boolEnv('EMAIL_MATCH_VIN_ENABLED', true) ? normalizeVin(vin) : null;
  if (realVin) {
    const vehicle = store.vehicles.find((item) => String(item.vin || '').toUpperCase() === realVin);
    if (vehicle) {
      const owner = store.clients.find((client) => client.id === vehicle.clientId);
      if (owner) return { client: owner, basis: 'vin', confidence: 0.8 };
    }
  }

  return { client: null, basis: 'none', confidence: 0 };
}

function runAiEnrichment(normalized) {
  const aiEnabled = boolEnv('EMAIL_AI_ENRICHMENT_ENABLED', false);
  const scope = String(process.env.EMAIL_AI_BUSINESS_USAGE_SCOPE || '').toLowerCase();
  if (!aiEnabled || scope !== 'email_intake' || !runtimeHooks.aiService) return null;
  return {
    summary: { ok: false, output: null },
    classification: { ok: false, output: null },
    conflictHint: { ok: false, output: null },
    reviewHint: { ok: false, output: null }
  };
}

function processEmailEvent(event, normalized) {
  const extracted = normalized.extracted || {};
  const tBusinessEnabled = boolEnv('EMAIL_SOURCE_TBUSINESS_ENABLED', true);
  const tBusinessDetected = tBusinessEnabled && normalized.detection?.isTBusiness;

  const match = findExistingClientMatch({ phone: extracted.phone, fullName: extracted.fullName, vin: extracted.vin });
  let needsReview = Number(match.confidence) < 0.75;
  if (boolEnv('EMAIL_NEEDS_REVIEW_ON_UNCERTAIN_MATCH', true) && match.basis !== 'none' && Number(match.confidence) < 0.9) {
    needsReview = true;
  }

  let client = match.client;
  const autoCreate = boolEnv('EMAIL_AUTO_CREATE_CLIENT_IF_NO_MATCH', true);
  if (!client && autoCreate) {
    client = db.upsertClient({ fullName: extracted.fullName || normalized.sender?.displayName || 'Email client', phone: extracted.phone, telegramId: null });
  }
  if (!client) {
    client = db.upsertClient({ fullName: extracted.fullName || 'Email client', phone: extracted.phone, telegramId: null });
    needsReview = true;
  }

  db.applyEntitySyncMetadata({
    collection: 'clients',
    entityId: client.id,
    metadata: {
      externalIds: normalized.externalIds,
      sourceSystem: INTEGRATION_SOURCES.EMAIL,
      sourceProvider: tBusinessDetected ? 't_business' : 'email_generic',
      sourceOfTruth: normalized.sourceOfTruth,
      lastSyncedAt: new Date().toISOString(),
      needsManualReview: needsReview
    }
  });

  const vehicle = db.upsertVehicle({
    clientId: client.id,
    vin: extracted.vin || null,
    brand: extracted.brandModel || null,
    model: null,
    year: extracted.year || null,
    plateNumber: extracted.plateNumber || null
  });
  if (vehicle) {
    db.applyEntitySyncMetadata({
      collection: 'vehicles',
      entityId: vehicle.id,
      metadata: {
        sourceSystem: INTEGRATION_SOURCES.EMAIL,
        sourceProvider: tBusinessDetected ? 't_business' : 'email_generic',
        sourceOfTruth: normalized.sourceOfTruth,
        lastSyncedAt: new Date().toISOString(),
        needsManualReview: needsReview
      }
    });
  }

  const ai = runAiEnrichment(normalized);
  const request = db.createRequest({
    clientId: client.id,
    vehicleId: vehicle?.id || null,
    requestType: extracted.requestType || REQUEST_TYPES.SERVICE,
    description: ai?.summary?.ok ? String(ai.summary.output || '').slice(0, 1500) : (extracted.text || normalized.message?.body || '').slice(0, 1500),
    sourceChannel: INTEGRATION_SOURCES.EMAIL,
    payload: {
      source_channel: 'email',
      source_provider: tBusinessDetected ? 't_business' : 'email_generic',
      priority: tBusinessDetected ? String(process.env.EMAIL_SOURCE_TBUSINESS_PRIORITY || 'high') : 'normal',
      direction_number: extracted.directionNumber || null,
      claim_number: extracted.claimNumber || null,
      email_message_id: normalized.message?.messageId || null,
      email_from: normalized.sender?.email || normalized.sender?.raw || null,
      email_subject: normalized.message?.subject || null,
      raw_email_saved: boolEnv('EMAIL_SAVE_RAW_MESSAGE', true),
      parsed_email_ok: true,
      existing_client: Boolean(match.client),
      needs_review: Boolean(needsReview),
      match_basis: needsReview && match.basis !== 'none' ? 'conflict' : match.basis,
      match_confidence: Number(match.confidence || 0),
      intake_status: 'processed',
      intake_errors: [],
      parsed_fields: extracted,
      body_fields: normalized.bodyExtracted,
      pdf_fields: normalized.pdfExtracted,
      conflicts: normalized.conflicts,
      ai_summary: ai?.summary?.ok ? ai.summary.output : null,
      ai_classification: ai?.classification?.ok ? ai.classification.output : null,
      ai_conflict_hint: ai?.conflictHint?.ok ? ai.conflictHint.output : null,
      ai_review_reason: ai?.reviewHint?.ok ? ai.reviewHint.output : null,
      raw_email: boolEnv('EMAIL_SAVE_RAW_MESSAGE', true) ? event.rawPayload : undefined,
      attachments_meta: boolEnv('EMAIL_SAVE_ATTACHMENTS_METADATA', true) ? (normalized.message?.attachments || []).map((a) => ({ filename: a.filename, contentType: a.contentType, size: a.size || 0 })) : []
    }
  });

  db.applyEntitySyncMetadata({
    collection: 'requests',
    entityId: request.id,
    metadata: {
      externalIds: normalized.externalIds,
      sourceSystem: INTEGRATION_SOURCES.EMAIL,
      sourceProvider: tBusinessDetected ? 't_business' : 'email_generic',
      sourceOfTruth: normalized.sourceOfTruth,
      lastSyncedAt: new Date().toISOString(),
      needsManualReview: needsReview,
      matchBasis: match.basis,
      matchConfidence: match.confidence
    }
  });

  db.createCommunicationEvent({
    clientId: client.id,
    requestId: request.id,
    source: INTEGRATION_SOURCES.EMAIL,
    channel: 'email',
    direction: 'inbound',
    payload: {
      action: 'email_ingested',
      sender: normalized.sender,
      subject: normalized.message?.subject || '',
      attachments: normalized.message?.attachments || [],
      tBusinessDetected,
      detectionReasons: normalized.detection?.reasons || []
    }
  });

  const masterDelivery = runtimeHooks.masterNotifier({ requestId: request.id, requestPayload: request.payload, request, client, vehicle });

  return {
    relatedEntityType: 'request',
    relatedEntityId: request.id,
    intakeMeta: {
      tBusinessDetected,
      needsReview,
      matchBasis: match.basis,
      matchConfidence: match.confidence,
      masterDelivery
    }
  };
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

    db.updateIntegrationEvent(eventId, {
      processingStatus: 'processed',
      relatedEntityType: result.relatedEntityType,
      relatedEntityId: result.relatedEntityId,
      lastError: null,
      metaJson: { intakeMeta: result.intakeMeta || null }
    }, 'Event processed');
    return db.getIntegrationEventById(eventId);
  } catch (error) {
    db.updateIntegrationEvent(eventId, { processingStatus: 'failed', lastError: String(error.message || error) }, 'Processing failed');
    throw error;
  }
}

function buildEmailDedupeKey(rawPayload = {}) {
  const messageId = String(rawPayload.messageId || rawPayload.message_id || '').trim();
  if (messageId) return `email:message-id:${messageId.toLowerCase()}`;
  const subject = String(rawPayload.subject || '').trim().toLowerCase();
  const receivedAt = String(rawPayload.date || rawPayload.receivedAt || '').slice(0, 19);
  const bodyHash = buildHash(String(rawPayload.body || rawPayload.text || ''));
  const normalizedHash = buildHash(`${subject}|${receivedAt}|${bodyHash}`);
  return `email:content:${normalizedHash}`;
}

function receiveIntegrationEvent({ sourceSystem, eventType, rawPayload, dedupeKey = null }) {
  const finalDedupeKey = dedupeKey || ((sourceSystem === INTEGRATION_SOURCES.EMAIL || eventType === INTEGRATION_EVENT_TYPES.EMAIL_REQUEST_RECEIVED) ? buildEmailDedupeKey(rawPayload || {}) : null);
  if (finalDedupeKey) {
    const existing = db.findIntegrationEventByDedupeKey(finalDedupeKey);
    if (existing) {
      runtimeHooks.logger?.info?.('integration event deduplicated', { sourceSystem, eventType, dedupeKey: finalDedupeKey, existingEventId: existing.id });
      return existing;
    }
  }

  const event = db.createIntegrationEvent({ sourceSystem, eventType, rawPayload, dedupeKey: finalDedupeKey });
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
  const items = db.listIntegrationEvents({ limit: 1000 });
  const latestEventAt = items[0]?.createdAt || null;
  const stats = {
    total: items.length,
    received: 0,
    normalized: 0,
    processing: 0,
    retryScheduled: 0,
    pending: 0,
    processed: 0,
    failed: 0,
    ignored: 0,
    latestEventAt
  };
  for (const item of items) {
    if (item.processingStatus === 'received') stats.received += 1;
    if (item.processingStatus === 'normalized') stats.normalized += 1;
    if (item.processingStatus === 'processing') stats.processing += 1;
    if (item.processingStatus === 'retry_scheduled') stats.retryScheduled += 1;
    if (item.processingStatus === 'processed') stats.processed += 1;
    if (item.processingStatus === 'failed') stats.failed += 1;
    if (item.processingStatus === 'ignored') stats.ignored += 1;
    if (item.processingStatus === 'pending') stats.pending += 1;
  }
  return stats;
}

module.exports = {
  INTEGRATION_SOURCES,
  INTEGRATION_EVENT_TYPES,
  receiveIntegrationEvent,
  retryIntegrationEvent,
  markIntegrationEventFailed,
  integrationStats,
  normalizeIntegrationPayload,
  processIntegrationEvent,
  parseEmailPayload,
  configureIntegrationRuntime,
  buildEmailDedupeKey
};
