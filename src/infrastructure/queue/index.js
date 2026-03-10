function createQueue() {
  const events = [];
  return {
    async publish(event) {
      events.push(event);
      return event;
    },
    snapshot() {
      return [...events];
    }
  };
}

module.exports = { createQueue };
