const { REQUEST_STATUSES, REQUEST_SUBSTATUSES, validateRequestStatus, validateRequestSubstatus, canTransitionRequest } = require('../shared/requestValidation');
const QUALITY_CASE_STATUSES = ['new', 'assigned', 'in_progress', 'resolved', 'unresolved', 'archived'];

function deriveClientChannel(requestCard) {
  const source = String(requestCard.request?.sourceChannel || '').toLowerCase();
  if (source.startsWith('telegram')) return 'telegram';
  if (source.startsWith('max')) return 'max';
  if (requestCard.client?.preferredChannel === 'max') {
    return 'max';
  }
  return 'unknown';
}

function deriveClientRecipientId(requestCard, channel) {
  if (channel === 'max') return requestCard.client?.maxId || null;
  return requestCard.client?.telegramId || null;
}

async function sendViaPreferredOrFallback({ requestCard, text, sendClientMessage, telegramClientBotToken, maxClientBotToken }) {
  const preferredChannel = deriveClientChannel(requestCard);
  const attempts = [];
  if (preferredChannel === 'telegram') {
    attempts.push({ channel: 'telegram', token: telegramClientBotToken, recipientId: requestCard.client?.telegramId || null, mode: 'primary' });
    if (requestCard.client?.maxId) attempts.push({ channel: 'max', token: maxClientBotToken, recipientId: requestCard.client?.maxId, mode: 'fallback' });
  } else if (preferredChannel === 'max') {
    attempts.push({ channel: 'max', token: maxClientBotToken, recipientId: requestCard.client?.maxId || null, mode: 'primary' });
    if (requestCard.client?.telegramId) attempts.push({ channel: 'telegram', token: telegramClientBotToken, recipientId: requestCard.client?.telegramId, mode: 'fallback' });
  } else {
    if (requestCard.client?.maxId) attempts.push({ channel: 'max', token: maxClientBotToken, recipientId: requestCard.client?.maxId, mode: 'primary' });
    if (requestCard.client?.telegramId) attempts.push({ channel: 'telegram', token: telegramClientBotToken, recipientId: requestCard.client?.telegramId, mode: attempts.length ? 'fallback' : 'primary' });
  }

  if (!attempts.length) return { ok: false, error: 'CLIENT_CHANNEL_UNRESOLVED', attempts: [] };

  const seen = new Set();
  for (const attempt of attempts) {
    const key = `${attempt.channel}:${attempt.recipientId || ''}`;
    if (!attempt.token || !attempt.recipientId || seen.has(key)) continue;
    seen.add(key);
    const delivered = await sendClientMessage({ channel: attempt.channel, token: attempt.token, recipientId: attempt.channel === 'telegram' ? Number(attempt.recipientId) : attempt.recipientId, text });
    if (delivered) return { ok: true, channel: attempt.channel, mode: attempt.mode, attempts: [attempt.channel] };
  }
  return { ok: false, error: 'CLIENT_MESSAGE_DELIVERY_FAILED', attempts: attempts.map((item) => item.channel) };
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

    listArchiveRequests() {
      return db.listRequests({ statuses: ['processed', 'completed'] }).filter((item) => item.archived);
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

    canChangeRequestStatus({ requestId, toStatus, substatus = null, allowArchived = false }) {
      const requestCard = db.getRequestCard(requestId);
      if (!requestCard) return { ok: false, error: 'REQUEST_NOT_FOUND' };
      return canTransitionRequest({
        fromStatus: requestCard.request.status,
        fromSubstatus: requestCard.request.substatus,
        toStatus,
        toSubstatus: substatus,
        archived: requestCard.request.archived,
        allowArchived
      });
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
      if (requestCard.request.status === 'completed') return { error: 'COMPLETED_IMMUTABLE' };
      if (requestCard.request.archived) return { error: 'ARCHIVED_IMMUTABLE' };
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
        maxClientBotToken
      });

      if (!delivery.ok) {
        db.updateRequestStatus({
          requestId,
          toStatus: 'error',
          actorId,
          actorRole,
          comment: delivery.error,
          metaJson: {
            channel: deriveClientChannel(requestCard),
            text,
            reason: delivery.error,
            attempts: delivery.attempts || []
          }
        });
        db.recordRequestEvent({
          requestId,
          clientId: requestCard.request.clientId,
          eventType: 'outbound_message_failed',
          actorId,
          actorRole,
          actorType: actorRole,
          comment: delivery.error,
          metaJson: {
            requestedText: text,
            channel: deriveClientChannel(requestCard),
            reason: delivery.error,
            attempts: delivery.attempts || [],
            timestamp: new Date().toISOString()
          }
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
