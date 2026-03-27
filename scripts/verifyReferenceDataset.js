#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const { getBuildInfo } = require('../src/infrastructure/buildInfo');

const REFERENCE_DATASET_RELATIVE_PATH = path.join('data', 'reference', 'client_vehicle_bridge', 'lira_normalized_database.sqlite');
const DEFAULT_REFERENCE_DATASET_PATH = path.resolve(__dirname, '..', REFERENCE_DATASET_RELATIVE_PATH);

function parseArgs(argv = []) {
  const strict = argv.includes('--strict');
  const datasetArg = argv.find((item) => item.startsWith('--dataset='));
  const datasetPath = datasetArg ? datasetArg.slice('--dataset='.length) : '';
  return { strict, datasetPath };
}

function canReadFile(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

function safeStatSize(filePath) {
  try {
    return fs.statSync(filePath).size;
  } catch {
    return null;
  }
}

function getDirectoryInfo(dirPath) {
  try {
    const stats = fs.statSync(dirPath);
    if (!stats.isDirectory()) return { exists: false, listing: [] };
    const listing = fs.readdirSync(dirPath, { withFileTypes: true })
      .slice(0, 50)
      .map((entry) => `${entry.name}${entry.isDirectory() ? '/' : ''}`);
    return { exists: true, listing };
  } catch {
    return { exists: false, listing: [] };
  }
}

function resolveDatasetPath(explicitPath = '') {
  const envPath = process.env.REFERENCE_CLIENT_LOOKUP_DATASET_PATH || process.env.REFERENCE_CLIENT_LOOKUP_SQLITE_PATH || '';
  const preferred = explicitPath || envPath || DEFAULT_REFERENCE_DATASET_PATH;
  return path.resolve(preferred);
}

function run() {
  const args = parseArgs(process.argv.slice(2));
  const buildInfo = getBuildInfo();
  const resolvedDatasetPath = resolveDatasetPath(args.datasetPath);
  const datasetDirPath = path.dirname(resolvedDatasetPath);
  const dirInfo = getDirectoryInfo(datasetDirPath);
  const exists = fs.existsSync(resolvedDatasetPath);
  const readable = exists ? canReadFile(resolvedDatasetPath) : false;
  const size = safeStatSize(resolvedDatasetPath);

  const payload = {
    buildCommitHash: buildInfo.commitHash,
    buildBranch: buildInfo.branch,
    buildTimestamp: buildInfo.buildTimestamp,
    datasetResolvedPath: resolvedDatasetPath,
    datasetDirectoryPath: datasetDirPath,
    datasetDirectoryExists: dirInfo.exists,
    datasetDirectoryListing: dirInfo.listing,
    datasetFileExists: exists,
    datasetFileReadable: readable,
    datasetFileSizeBytes: size
  };

  const prefix = '[deploy-check][reference-dataset]';
  process.stdout.write(`${prefix} ${JSON.stringify(payload)}\n`);

  if (args.strict && (!exists || !readable)) {
    process.stderr.write(`${prefix} strict mode failed: dataset missing or unreadable at ${resolvedDatasetPath}\n`);
    process.exit(1);
  }
}

run();
