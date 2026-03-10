function registerMasterBotRoutes(router) {
  router.push({ method: 'POST', path: '/telegram/master_bot/webhook' });
}

module.exports = { registerMasterBotRoutes };
