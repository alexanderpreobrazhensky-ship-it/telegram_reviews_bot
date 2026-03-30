const fs = require('node:fs');
const path = require('node:path');
const { DEFAULT_REFERENCE_DATASET_PATH } = require('./referenceClientLookup');

const REFERENCE_DATASET_RELATIVE_PATH = path.join('data', 'reference', 'client_vehicle_bridge', 'lira_normalized_database.sqlite');
const EMBEDDED_DATASET_DEFAULT_PATH = path.join('/opt', 'reference-assets', 'client_vehicle_bridge', 'lira_normalized_database.sqlite');

function canReadFile(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

function statFileSize(filePath) {
  try {
    return fs.statSync(filePath).size;
  } catch {
    return null;
  }
}

function resolveSeedCandidates() {
  const explicitSeedPath = process.env.REFERENCE_CLIENT_LOOKUP_EMBEDDED_DATASET_PATH || '';
  const envDatasetPath = process.env.REFERENCE_CLIENT_LOOKUP_DATASET_PATH || process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH || '';
  const fromMainModule = path.join(path.dirname(require.main?.filename || process.cwd()), REFERENCE_DATASET_RELATIVE_PATH);
  const candidates = [
    explicitSeedPath,
    EMBEDDED_DATASET_DEFAULT_PATH,
    DEFAULT_REFERENCE_DATASET_PATH,
    envDatasetPath,
    path.resolve(process.cwd(), REFERENCE_DATASET_RELATIVE_PATH),
    path.resolve(fromMainModule)
  ].filter(Boolean);
  const unique = [];
  const seen = new Set();
  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    if (seen.has(resolved)) continue;
    seen.add(resolved);
    unique.push(resolved);
  }
  return unique;
}

function ensureReferenceDatasetRuntime({ logger = console, expectedPath: expectedPathInput = DEFAULT_REFERENCE_DATASET_PATH } = {}) {
  const expectedPath = path.resolve(expectedPathInput);
  const expectedDir = path.dirname(expectedPath);
  const existsBefore = fs.existsSync(expectedPath);
  const readableBefore = existsBefore ? canReadFile(expectedPath) : false;
  const sizeBefore = statFileSize(expectedPath);

  logger.info?.('reference dataset runtime presence check started', {
    expectedDatasetPath: expectedPath,
    expectedDatasetDirectory: expectedDir,
    datasetExists: existsBefore,
    datasetReadable: readableBefore,
    datasetFileSizeBytes: sizeBefore
  });

  if (existsBefore && readableBefore) {
    logger.info?.('reference dataset runtime presence check completed', {
      copiedFrom: null,
      copied: false,
      datasetPath: expectedPath,
      datasetExists: true,
      datasetReadable: true,
      datasetFileSizeBytes: sizeBefore
    });
    return { copied: false, copiedFrom: null, datasetPath: expectedPath, datasetExists: true, datasetReadable: true, datasetFileSizeBytes: sizeBefore };
  }

  const seedCandidates = resolveSeedCandidates();
  logger.info?.('reference dataset runtime seed candidates resolved', { seedCandidates });

  fs.mkdirSync(expectedDir, { recursive: true });
  for (const candidate of seedCandidates) {
    if (candidate === expectedPath) continue;
    const candidateExists = fs.existsSync(candidate);
    const candidateReadable = candidateExists ? canReadFile(candidate) : false;
    logger.info?.('reference dataset runtime seed candidate checked', { candidate, exists: candidateExists, readable: candidateReadable });
    if (!candidateExists || !candidateReadable) continue;
    fs.copyFileSync(candidate, expectedPath);
    const copiedReadable = canReadFile(expectedPath);
    const copiedSize = statFileSize(expectedPath);
    logger.info?.('reference dataset runtime seed copy result', {
      copiedFrom: candidate,
      copiedTo: expectedPath,
      copiedReadable,
      copiedSizeBytes: copiedSize
    });
    if (copiedReadable) {
      return {
        copied: true,
        copiedFrom: candidate,
        datasetPath: expectedPath,
        datasetExists: true,
        datasetReadable: true,
        datasetFileSizeBytes: copiedSize
      };
    }
  }

  const existsAfter = fs.existsSync(expectedPath);
  const readableAfter = existsAfter ? canReadFile(expectedPath) : false;
  const sizeAfter = statFileSize(expectedPath);
  logger.warn?.('reference dataset runtime presence check failed to heal', {
    expectedDatasetPath: expectedPath,
    datasetExists: existsAfter,
    datasetReadable: readableAfter,
    datasetFileSizeBytes: sizeAfter
  });
  return {
    copied: false,
    copiedFrom: null,
    datasetPath: expectedPath,
    datasetExists: existsAfter,
    datasetReadable: readableAfter,
    datasetFileSizeBytes: sizeAfter
  };
}

module.exports = {
  ensureReferenceDatasetRuntime,
  EMBEDDED_DATASET_DEFAULT_PATH
};
