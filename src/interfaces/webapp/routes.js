const { webappRoutes } = require('./index');

module.exports = {
  webappRouteMap: webappRoutes().map((route) => ({ route, component: 'PlaceholderPage' }))
};
