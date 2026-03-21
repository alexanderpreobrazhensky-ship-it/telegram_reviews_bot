const REQUEST_STATUSES = ['new', 'assigned', 'awaiting_client', 'scheduled', 'in_service', 'done', 'cancelled'];
const QUALITY_CASE_STATUSES = ['new', 'assigned', 'in_progress', 'resolved', 'unresolved', 'archived'];

function deriveClientChannel(requestCard) {
  if (requestCard.client?.preferredChannel === 'max' || String(requestCard.request?.sourceChannel || '').startsWith('max_')) {
    return 'max';
  }
  return 'telegram';
}

function deriveClientRecipientId(requestCard) {
  const channel = deriveClientChannel(requestCard);
  return channel === 'max' ? requestCard.client?.maxId : requestCard.client?.telegramId;
}

function createMasterService({ db, sendClientMessage, adminIds = [], actorChannel = 'telegram' }) {
  return {
    getAvailableRoles() {
      return ['master', 'manager', 'admin'];
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
      if (!REQUEST_STATUSES.includes(status)) return [];
      return db.listRequests({ statuses: [status] });
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

    changeRequestStatus({ requestId, toStatus, actorId, actorRole, lostReason, comment }) {
      return db.updateRequestStatus({ requestId, toStatus, actorId, actorRole, lostReason, comment });
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
      const channel = deriveClientChannel(requestCard);
      const recipientId = deriveClientRecipientId(requestCard);
      db.recordMasterAction({
        actorId,
        role: actorRole,
        action: 'client_clarification_requested',
        requestId,
        clientId: requestCard.request.clientId,
        payload: { text, channel }
      });
      db.createCommunicationEvent({
        clientId: requestCard.request.clientId,
        requestId,
        source: actorChannel === 'max' ? 'max_master_bot' : 'master_bot',
        channel,
        direction: 'outbound',
        payload: { action: 'client_clarification_requested', text }
      });

      const token = channel === 'max' ? maxClientBotToken : telegramClientBotToken;
      if (!recipientId || !token || !sendClientMessage) {
        return { ok: true, mode: 'intent_logged', channel };
      }

      await sendClientMessage({ channel, token, recipientId, text: `Запрос уточнения от мастера по заявке ${requestId}: ${text}` });
      return { ok: true, mode: 'intent_logged_and_sent', channel };
    }
  };
}

module.exports = { createMasterService, deriveClientChannel, deriveClientRecipientId };
