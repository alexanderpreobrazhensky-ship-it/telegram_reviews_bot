function registerIntegrationBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/integration_bot/webhook' });
}

module.exports = { registerIntegrationBotRoutes };
