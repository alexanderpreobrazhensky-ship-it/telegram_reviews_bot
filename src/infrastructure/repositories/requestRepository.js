function createRequestRepository({ db }) {
  return {
    create(payload) {
      return db.createRequest(payload);
    },
    createClient(payload) {
      return db.upsertClient(payload);
    },
    createVehicle(payload) {
      return db.upsertVehicle(payload);
    },
    findById(id) {
      return db.findRequestById(id);
    },
    findRecentDuplicate(criteria) {
      return db.findRecentDuplicateRequest(criteria);
    },
    markDuplicate(payload) {
      return db.markRequestDuplicate(payload);
    },
    list(filters) {
      return db.listRequests(filters);
    },
    getCard(id) {
      return db.getRequestCard(id);
    },
    updateStatus(payload) {
      return db.updateRequestStatus(payload);
    },
    updateAssignment(payload) {
      return db.updateRequestAssignment(payload);
    }
  };
}

module.exports = { createRequestRepository };
