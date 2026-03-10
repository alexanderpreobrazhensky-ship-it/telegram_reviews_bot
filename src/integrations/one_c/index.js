function oneCSyncPlaceholder(event) {
  return {
    provider: 'one_c',
    accepted: true,
    externalId: event?.externalId || null
  };
}

module.exports = { oneCSyncPlaceholder };
