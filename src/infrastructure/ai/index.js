const { createProviderRegistry } = require('./providerRegistry');
const { createAiRuntimeSettings } = require('./aiRuntimeSettings');
const { createAiService } = require('./aiService');
const { runAiDiagnostics, maskSecret } = require('./aiDiagnostics');

let singleton = null;

function initializeAiInfrastructure({ config, db, logger }) {
  const configAi = config.ai || {};
  const providerRegistry = createProviderRegistry({ config: configAi });
  const runtimeSettings = createAiRuntimeSettings({ db, configAi });
  const aiService = createAiService({ configAi, runtimeSettings, providerRegistry, db, logger });

  singleton = {
    configAi,
    providerRegistry,
    runtimeSettings,
    aiService,
    async runDiagnostics() {
      return runAiDiagnostics({ aiService, runtimeSettings, configAi, providerRegistry });
    },
    listLogs(filters = {}) {
      return db.listAiEvents(filters);
    },
    maskSecret
  };
  return singleton;
}

function getAiInfrastructure() {
  return singleton;
}

module.exports = { initializeAiInfrastructure, getAiInfrastructure };
