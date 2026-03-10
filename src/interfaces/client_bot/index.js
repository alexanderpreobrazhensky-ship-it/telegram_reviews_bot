function registerClientBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/client_bot/webhook' });
}

module.exports = { registerClientBotRoutes };
