function createRequestUseCase({ requestRepository, eventBus }) {
  return {
    async execute(payload) {
      const request = await requestRepository.create(payload);
      await eventBus.publish({ type: 'request.created', payload: { id: request.id } });
      return request;
    }
  };
}

module.exports = {
  createRequestUseCase
};
