function pickFirstNonEmpty(values = []) {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim() !== '') return String(value).trim();
  }
  return '';
}

function getBuildInfo() {
  const commitHash = pickFirstNonEmpty([
    process.env.APP_BUILD_COMMIT,
    process.env.BUILD_COMMIT,
    process.env.GIT_COMMIT,
    process.env.VERCEL_GIT_COMMIT_SHA,
    process.env.RENDER_GIT_COMMIT
  ]) || 'unknown';
  const branch = pickFirstNonEmpty([
    process.env.APP_BUILD_BRANCH,
    process.env.BUILD_BRANCH,
    process.env.GIT_BRANCH,
    process.env.VERCEL_GIT_COMMIT_REF,
    process.env.RENDER_GIT_BRANCH
  ]) || 'unknown';
  const buildTimestamp = pickFirstNonEmpty([
    process.env.APP_BUILD_TIMESTAMP,
    process.env.BUILD_TIMESTAMP,
    process.env.SOURCE_DATE_EPOCH
  ]) || 'unknown';
  return { commitHash, branch, buildTimestamp };
}

module.exports = {
  getBuildInfo
};
