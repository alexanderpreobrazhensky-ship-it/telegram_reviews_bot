const TASK_POLICIES = Object.freeze({
  classifyIntent: 'cheap',
  summarizeRequest: 'cheap',
  analyzeFeedback: 'cheap',
  generateReply: 'strong',
  explainIntegrationError: 'strong_or_cheap_by_policy',
  runHealthCheck: 'cheap'
});

function resolveTaskPolicy(taskType, { preferStrong = false } = {}) {
  const base = TASK_POLICIES[taskType] || 'cheap';
  if (base === 'strong_or_cheap_by_policy') return preferStrong ? 'strong' : 'cheap';
  return base;
}

module.exports = { TASK_POLICIES, resolveTaskPolicy };
