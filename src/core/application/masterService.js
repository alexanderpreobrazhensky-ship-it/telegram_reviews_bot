const REQUEST_STATUSES = ['new', 'waiting_data', 'in_progress', 'processed', 'lost', 'archived'];
const QUALITY_CASE_STATUSES = ['new', 'assigned', 'in_progress', 'resolved', 'unresolved', 'archived'];

function createMasterService({ db, sendClientMessage, adminTelegramIds = [] }) {
  return {
    getAvailableRoles() {
      return ['master', 'manager', 'admin'];
    },

    resolveActor({ telegramId, fullName }) {
      return db.resolveStaffUser({ telegramId, fullName, adminTelegramIds });
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

    changeRequestStatus({ requestId, toStatus, actorId, actorRole, lostReason }) {
      return db.updateRequestStatus({ requestId, toStatus, actorId, actorRole, lostReason });
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

    grantStaffAccess({ telegramId, fullName, role, actorId, actorRole }) {
      return db.createStaffUser({ telegramId, fullName, role, actorId, actorRole });
    },

    revokeStaffAccess({ telegramId, actorId, actorRole }) {
      return db.revokeStaffUser({ telegramId, actorId, actorRole });
    },

    async requestClientClarification({ requestId, actorId, actorRole, text, chatId, telegramClientBotToken }) {
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
        source: 'master_bot',
        payload: { action: 'client_clarification_requested', text }
      });

      if (!requestCard.client?.telegramId || !telegramClientBotToken || !sendClientMessage) {
        return { ok: true, mode: 'intent_logged' };
      }

      await sendClientMessage(telegramClientBotToken, chatId || Number(requestCard.client.telegramId), `Запрос уточнения от мастера по заявке ${requestId}: ${text}`);
      return { ok: true, mode: 'intent_logged_and_sent' };
    }
  };
}

module.exports = { createMasterService };
