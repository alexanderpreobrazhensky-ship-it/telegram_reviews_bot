function ingestEmail(message) {
  return {
    provider: 'email',
    status: 'accepted',
    messageId: message?.id || null
  };
}

module.exports = { ingestEmail };
