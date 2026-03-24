const test = require('node:test');
const assert = require('node:assert/strict');
const { createReportingService } = require('../../src/core/application');
const db = require('../../src/infrastructure/db');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');
const { handleMasterWebhook } = require('../../src/interfaces/master_bot');


test('reporting service builds metrics and summaries for weekly/monthly/custom', () => {
  db.resetStore();
  const client = db.upsertClient({ fullName: 'A', phone: '+79991112233', telegramId: '11' });
  const req = db.createRequest({ clientId: client.id, requestType: 'service', description: 'x', sourceChannel: 'webapp' });
  db.updateRequestStatus({ requestId: req.id, toStatus: 'assigned', actorId: 'm1', actorRole: 'master' });
  db.updateRequestStatus({ requestId: req.id, toStatus: 'in_service', actorId: 'm1', actorRole: 'master' });
  db.updateRequestStatus({ requestId: req.id, toStatus: 'done', actorId: 'm1', actorRole: 'master' });
  db.createFeedback({ clientId: client.id, requestId: req.id, rating: 2, comment: 'bad' });
  db.upsertRecommendationFromSync({ clientId: client.id, externalId: 'r1', text: 'x', severity: 'critical', status: 'completed' });

  const reporting = createReportingService({ db });
  const requests = reporting.buildRequestsMetrics({ period: 'weekly' });
  const feedback = reporting.buildFeedbackMetrics({ period: 'weekly' });
  const quality = reporting.buildQualityMetrics({ period: 'weekly' });
  const sources = reporting.buildSourceMetrics({ period: 'weekly' });
  const recommendations = reporting.buildRecommendationMetrics({ period: 'weekly' });

  assert.equal(requests.totalRequests, 1);
  assert.equal(feedback.totalFeedbackCount, 1);
  assert.equal(quality.qualityCaseCount, 1);
  assert.equal(sources.webapp, 1);
  assert.equal(recommendations.criticalRecommendationsCount >= 1, true);

  const weekly = reporting.buildManagementSummary({ period: 'weekly' });
  const monthly = reporting.buildManagementSummary({ period: 'monthly' });
  const custom = reporting.buildManagementSummary({ from: '2000-01-01T00:00:00.000Z', to: new Date().toISOString() });
  assert.match(weekly.summaryText, /Сводка за период/);
  assert.equal(monthly.summary.period.periodType, 'monthly');
  assert.equal(custom.summary.period.periodType, 'custom');
});

test('report snapshots can be created, persisted and retrieved', () => {
  db.resetStore();
  const reporting = createReportingService({ db });
  const snapshot = reporting.buildPeriodicSnapshot({ period: 'weekly', generatedBy: 'manual' });
  assert.ok(snapshot.id);

  const listed = reporting.listSnapshots();
  assert.equal(listed.length, 1);
  const loaded = reporting.getSnapshotById(snapshot.id);
  assert.equal(loaded.id, snapshot.id);
});

test('report routes and stage 2-5 regression routes stay alive with admin auth', async () => {
  db.resetStore();
  process.env.MASTER_BOT_ADMIN_IDS = '2,778';
  process.env.INTERNAL_ADMIN_WHITELIST = '2,778';
  const server = createServer({ config: loadConfig(), logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const base = `http://127.0.0.1:${server.address().port}`;

  try {
    const health = await fetch(`${base}/health`);
    const clientHook = await fetch(`${base}/telegram/client_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 1 }, from: { id: 1 } } }) });
    const masterHook = await fetch(`${base}/telegram/master_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 2 }, from: { id: 2 } } }) });
    const integrationHook = await fetch(`${base}/telegram/integration_bot/webhook`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: { text: '/start', chat: { id: 3 }, from: { id: 3 } } }) });
    const summaryDenied = await fetch(`${base}/api/reports/summary?period=weekly`);
    const summary = await fetch(`${base}/api/reports/summary?period=7d&admin_id=2`);
    const snapshotCreate = await fetch(`${base}/api/reports/snapshots?admin_id=2`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ period: '7d' }) });
    const snapshots = await fetch(`${base}/api/reports/snapshots?admin_id=2`);
    const exported = await fetch(`${base}/api/reports/export?admin_id=2&reportType=summary&period=7d`);

    assert.equal(health.status, 200);
    assert.equal(clientHook.status, 200);
    assert.equal(masterHook.status, 200);
    assert.equal(integrationHook.status, 200);
    assert.equal(summaryDenied.status, 403);
    assert.equal(summary.status, 200);
    assert.equal(snapshotCreate.status, 201);
    assert.equal(snapshots.status, 200);
    assert.equal(exported.status, 200);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.MASTER_BOT_ADMIN_IDS;
    delete process.env.INTERNAL_ADMIN_WHITELIST;
  }
});

test('only admin can use report bot hooks while master/manager cannot', async () => {
  db.resetStore();
  process.env.MASTER_BOT_ADMIN_IDS = '778';
  db.createStaffUser({ telegramId: '777', fullName: 'M', role: 'manager' });

  const denied = await handleMasterWebhook({ body: { message: { text: '/report_week', chat: { id: 10 }, from: { id: 10, first_name: 'Master' } } }, config: loadConfig() });
  const allowedManager = await handleMasterWebhook({ body: { message: { text: '/report_week', chat: { id: 777 }, from: { id: 777, first_name: 'Manager' } } }, config: loadConfig() });
  const allowedAdmin = await handleMasterWebhook({ body: { message: { text: '/report_month', chat: { id: 778 }, from: { id: 778, first_name: 'Admin' } } }, config: loadConfig() });
  delete process.env.MASTER_BOT_ADMIN_IDS;

  assert.equal(denied.ok, false);
  assert.equal(allowedManager.ok, false);
  assert.equal(allowedAdmin.ok, true);
});
