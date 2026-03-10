const { createServer } = require('./src/server');
const { loadConfig } = require('./src/infrastructure/config');
const logger = require('./src/infrastructure/logging/logger');

function bootstrap() {
  const config = loadConfig();
  const server = createServer({ config, logger });

  server.listen(config.port, () => {
    logger.info(`Platform skeleton server listening on port ${config.port}`);
  });

  return server;
}

if (require.main === module) {
  bootstrap();
}

module.exports = { bootstrap };
