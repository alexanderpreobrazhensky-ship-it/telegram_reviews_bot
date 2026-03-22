const { REQUEST_STATUSES, REQUEST_SUBSTATUSES, validateRequestStatus, validateRequestSubstatus } = require('../shared/requestValidation');
const QUALITY_CASE_STATUSES = ['new', 'assigned', 'in_progress', 'resolved', 'unresolved', 'archived'];

function deriveClientChannel(requestCard) {
  if (requestCard.client?.preferredChannel === 'max' || String(requestCard.request?.sourceChannel || '').startsWith('max_')) {
    return 'max';
  }
  return 'telegram';
}

function deriveClientRecipientId(requestCard, channel) {
  if (channel === 'max') return requestCard.client?.maxId || null;
  return requestCard.client?.telegramId || null;
}

async function sendViaPreferredOrFallback({ requestCard, text, sendClientMessage, telegramClientBotToken, maxClientBotToken, actorChannel }) {
  const preferredChannel = deriveClientChannel(requestCard);
  const primaryToken = preferredChannel === 'max' ? maxClientBotToken : telegramClientBotToken;
  const primaryRecipientId = deriveClientRecipientId(requestCard, preferredChannel);
  const fallbackChannel = preferredChannel === 'max' ? 'telegram' : 'max';
  const fallbackToken = fallbackChannel === 'max' ? maxClientBotToken : telegramClientBotToken;
  const fallbackRecipientId = deriveClientRecipientId(requestCard, fallbackChannel);

  const attempts = [];
  if (preferredChannel === 'telegram' || preferredChannel === 'max') {
    attempts.push({ channel: preferredChannel, token: primaryToken, recipientId: primaryRecipientId, mode: 'preferred' });
  }
  if (preferredChannel !== 'telegram' && actorChannel !== 'max') {
    attempts.push({ channel: 'telegram', token: telegramClientBotToken, recipientId: requestCard.client?.telegramId || null, mode: 'fallback' });
  }
  if (preferredChannel !== 'max' && actorChannel !== 'telegram') {
    attempts.push({ channel: 'max', token: maxClientBotToken, recipientId: requestCard.client?.maxId || null, mode: 'fallback' });
  }
  if (preferredChannel === 'telegram') {
    attempts.push({ channel: 'max', token: fallbackToken, recipientId: fallbackRecipientId, mode: 'fallback' });
  }
  if (preferredChannel === 'max') {
    attempts.push({ channel: 'telegram', token: fallbackToken, recipientId: fallbackRecipientId, mode: 'fallback' });
  }

  const seen = new Set();
  for (const attempt of attempts) {
    const key = `${attempt.channel}:${attempt.recipientId || ''}`;
    if (!attempt.token || !attempt.recipientId || seen.has(key)) continue;
    seen.add(key);
    const delivered = await sendClientMessage({ channel: attempt.channel, token: attempt.token, recipientId: attempt.channel === 'telegram' ? Number(attempt.recipientId) : attempt.recipientId, text });
    if (delivered) return { ok: true, channel: attempt.channel, mode: attempt.mode };
  }
  return { ok: false, error: 'CLIENT_MESSAGE_DELIVERY_FAILED' };
}

function createMasterService({ db, sendClientMessage, adminIds = [], actorChannel = 'telegram' }) {
  return {
    getAvailableRoles() {
      return ['master', 'manager', 'admin'];
    },

    getStatusCatalog() {
      return { statuses: REQUEST_STATUSES, substatuses: REQUEST_SUBSTATUSES };
    },

    resolveActor({ channelUserId, telegramId, maxId, fullName }) {
      return db.resolveStaffUser({
        channel: actorChannel,
        channelUserId,
        telegramId,
        maxId,
        fullName,
        adminIds
      });
    },

    listRequestsByStatus(status) {
      const normalized = validateRequestStatus(status);
      if (!normalized) return [];
      return db.listRequests({ statuses: [normalized] });
    },

    listActiveRequests() {
      return db.listRequests({ statuses: ['in_progress', 'processed', 'in_service', 'error'] }).filter((item) => !item.archived);
    },

    search(query) {
      return db.searchCRM(query);
    },

    getClientCard(clientId) {
      return db.getClientCard(clientId);
    },

    getRequestCard(requestId) {
      return db.getRequestCard(requestId);
    },

    getClientRecommendations(clientId) {
      return db.listRecommendations({ clientId, includeHistory: true });
    },

    changeRequestStatus({ requestId, toStatus, substatus = null, actorId, actorRole, lostReason, comment }) {
      return db.updateRequestStatus({ requestId, toStatus, substatus, actorId, actorRole, lostReason, comment });
    },

    assignRequest({ requestId, assignedTo, assignedBy, actorId, actorRole, actorType, metaJson }) {
      return db.updateRequestAssignment({ requestId, assignedTo, assignedBy, actorId, actorRole, actorType, metaJson });
    },

    addInternalComment({ requestId, actorId, actorRole, text }) {
      return db.addInternalComment({ requestId, actorId, actorRole, text });
    },

    addClientNote({ clientId, actorId, actorRole, text }) {
      return db.addClientNote({ clientId, actorId, actorRole, text });
    },

    listQualityCases(statuses = []) {
      return db.listQualityCases(statuses);
    },

    getQualityCaseCard(qualityCaseId) {
      return db.getQualityCaseCard(qualityCaseId);
    },

    changeQualityCaseStatus({ qualityCaseId, status, actorId, actorRole }) {
      if (!QUALITY_CASE_STATUSES.includes(status)) return null;
      return db.updateQualityCaseStatus({ qualityCaseId, status, actorId, actorRole });
    },

    addQualityCaseComment({ qualityCaseId, actorId, actorRole, text }) {
      return db.addQualityCaseComment({ qualityCaseId, actorId, actorRole, text });
    },

    listStaffUsers() {
      return db.listStaffUsers();
    },

    grantStaffAccess({ channelUserId, telegramId, maxId, fullName, role, actorId, actorRole }) {
      return db.createStaffUser({ channel: actorChannel, channelUserId, telegramId, maxId, fullName, role, actorId, actorRole });
    },

    revokeStaffAccess({ channelUserId, telegramId, maxId, actorId, actorRole }) {
      return db.revokeStaffUser({ channel: actorChannel, channelUserId, telegramId, maxId, actorId, actorRole });
    },

    async requestClientClarification({ requestId, actorId, actorRole, text, telegramClientBotToken, maxClientBotToken }) {
      const requestCard = db.getRequestCard(requestId);
      if (!requestCard) return { error: 'REQUEST_NOT_FOUND' };
      db.recordMasterAction({
        actorId,
        role: actorRole,
        action: 'client_clarification_requested',
        requestId,
        clientId: requestCard.request.clientId,
        payload: { text }
      });
      db.createCommunicationEvent({
        clientId: requestCard.request.clientId,
        requestId,
        source: actorChannel === 'max' ? 'max_master_bot' : 'master_bot',
        channel: deriveClientChannel(requestCard),
        direction: 'outbound',
        payload: { action: 'client_clarification_requested', text }
      });

      const delivery = await sendViaPreferredOrFallback({
        requestCard,
        text: `Сообщение мастера по заявке ${requestId}: ${text}`,
        sendClientMessage,
        telegramClientBotToken,
        maxClientBotToken,
        actorChannel
      });

      if (!delivery.ok) {
        db.updateRequestStatus({ requestId, toStatus: 'error', actorId, actorRole, comment: 'client_message_delivery_failed' });
        db.recordRequestEvent({
          requestId,
          clientId: requestCard.request.clientId,
          eventType: 'message_delivery_failed',
          actorId,
          actorRole,
          actorType: actorRole,
          comment: 'client_message_delivery_failed',
          metaJson: { requestedText: text }
        });
        return delivery;
      }

      db.recordRequestEvent({
        requestId,
        clientId: requestCard.request.clientId,
        eventType: 'message_sent',
        actorId,
        actorRole,
        actorType: actorRole,
        comment: delivery.channel,
        metaJson: { requestedText: text, channel: delivery.channel, mode: delivery.mode }
      });
      return { ok: true, ...delivery };
    },

    reactivateWaitingDecisionRequest({ requestId }) {
      return db.reactivateWaitingDecisionRequest({ requestId });
    },

    listOperationalLogs(filters) {
      return db.listOperationalLogs(filters);
    }
  };
}

module.exports = { createMasterService, deriveClientChannel, deriveClientRecipientId };
