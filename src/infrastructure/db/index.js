const { schemaOverview } = require('./schema');

function createDbClient({ url }) {
  return {
    url,
    schemaOverview,
    async ping() {
      return true;
    }
  };
}

module.exports = { createDbClient, schemaOverview };
