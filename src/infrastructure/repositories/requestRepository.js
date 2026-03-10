function createRequestRepository() {
  return {
    async create(payload) {
      return {
        id: payload.id || 'stub-request-id',
        ...payload
      };
    },
    async findById(id) {
      return id ? { id } : null;
    }
  };
}

module.exports = { createRequestRepository };
