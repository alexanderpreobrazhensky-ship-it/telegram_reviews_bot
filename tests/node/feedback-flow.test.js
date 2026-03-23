const test = require('node:test');
const assert = require('node:assert/strict');
const db = require('../../src/infrastructure/db');
const { createScheduler } = require('../../src/infrastructure/scheduler');
const { createServer } = require('../../src/server');
const { loadConfig } = require('../../src/infrastructure/config');
const logger = require('../../src/infrastructure/logging/logger');

async function withServer(run) {
  db.resetStore();
  process.env.MASTER_BOT_ADMIN_IDS = '7001';
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const port = server.address().port;
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    delete process.env.MASTER_BOT_ADMIN_IDS;
  }
}

async function sendMaster(base, text, fromId = 7001) {
  const response = await fetch(`${base}/telegram/master_bot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: { text, chat: { id: fromId }, from: { id: fromId, first_name: 'Master' } } })
  });
  return response.json();
}

async function sendClient(base, text, fromId) {
  const response = await fetch(`${base}/telegram/client_bot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: { text, chat: { id: fromId }, from: { id: fromId, first_name: 'Client' } } })
  });
  return response.json();
}

test('processed request creates feedback task and low feedback creates quality case', async () => {
  await withServer(async (base) => {
    const telegramId = 300001;
    const reqResponse = await fetch(`${base}/api/client/requests/service`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fullName: 'Клиент Фидбек', phone: '0000000100', telegramId, wasClientBefore: 'yes', brand: 'Lada', model: 'Vesta', year: '2020', vin: 'VIN-FB', description: 'Нужен ремонт' })
    });
    const request = await reqResponse.json();

    await sendMaster(base, `/set_status ${request.id} assigned`);
    await sendMaster(base, `/set_status ${request.id} in_service`);
    await sendMaster(base, `/set_status ${request.id} done`);

    const scheduled = db.listTasks(['scheduled']).filter((item) => item.taskType === 'feedback_request');
    assert.equal(scheduled.length, 1);

    const feedbackReply = await sendClient(base, '2 плохо', telegramId);
    assert.equal(feedbackReply.ok, true);
    assert.equal(feedbackReply.action, 'feedback_saved');

    const state = db.readStore();
    assert.equal(state.feedback.length, 1);
    assert.equal(state.feedback[0].rating, 2);
    assert.equal(Boolean(state.feedback[0].qualityCaseId), true);
    assert.equal(state.qualityCases.length, 1);
    assert.equal(state.qualityCases[0].status, 'new');

    const hasManagerDuplication = state.communicationEvents.some((item) => item.payload?.duplicateForRole === 'manager');
    assert.equal(hasManagerDuplication, true);
    const hasMasterAction = state.masterActions.some((item) => item.action === 'quality_case_auto_created_from_feedback');
    assert.equal(hasMasterAction, true);
  });
});

test('scheduler executes due tasks and retries failed tasks safely', async () => {
  db.resetStore();
  const executed = [];
  const task = db.createTask({ taskType: 'feedback_request', dueAt: new Date(Date.now() - 1000).toISOString(), payload: { requestId: 'r-1' } });
  db.createTask({ taskType: 'maintenance_reminder', dueAt: new Date(Date.now() - 1000).toISOString(), payload: {} });

  const scheduler = createScheduler({
    db,
    logger: { warn() {}, error() {} },
    handlers: {
      async feedback_request(item) {
        executed.push(item.id);
      },
      async maintenance_reminder() {
        throw new Error('temporary_error');
      }
    },
    maxAttempts: 1,
    batchSize: 10
  });

  const pass1 = await scheduler.runOnce();
  assert.equal(pass1.processed, 1);
  let state = db.readStore();
  const feedbackTask = state.tasks.find((item) => item.id === task.id);
  const failedCandidate = state.tasks.find((item) => item.taskType === 'maintenance_reminder');
  assert.equal(feedbackTask.status, 'completed');
  assert.equal(failedCandidate.status, 'failed');
  assert.equal(failedCandidate.attemptCount, 1);
  assert.equal(executed.includes(task.id), true);
});

test('waiting_decision and consulted follow-up tasks are persisted and processed safely', async () => {
  db.resetStore();
  const clientA = db.upsertClient({ fullName: 'Wait Client', phone: '0000000101', telegramId: '9101' });
  const clientB = db.upsertClient({ fullName: 'Consult Client', phone: '0000000102', telegramId: '9102' });
  const staff = db.createStaffUser({ channelUserId: '7001', telegramId: '7001', fullName: 'Master', role: 'master', actorId: 'admin', actorRole: 'admin' }).user;
  const requestA = db.createRequest({ clientId: clientA.id, requestType: 'service_request', description: 'wait', sourceChannel: 'telegram_chat' });
  const requestB = db.createRequest({ clientId: clientB.id, requestType: 'service_request', description: 'consult', sourceChannel: 'telegram_chat' });

  db.updateRequestAssignment({ requestId: requestA.id, assignedTo: staff.id, assignedBy: 'admin', actorId: 'admin', actorRole: 'admin' });
  db.updateRequestAssignment({ requestId: requestB.id, assignedTo: staff.id, assignedBy: 'admin', actorId: 'admin', actorRole: 'admin' });
  db.updateRequestStatus({ requestId: requestA.id, toStatus: 'in_progress', actorId: staff.id, actorRole: 'master' });
  db.updateRequestStatus({ requestId: requestB.id, toStatus: 'in_progress', actorId: staff.id, actorRole: 'master' });
  db.updateRequestStatus({ requestId: requestA.id, toStatus: 'processed', substatus: 'waiting_decision', actorId: staff.id, actorRole: 'master' });
  db.updateRequestStatus({ requestId: requestB.id, toStatus: 'processed', substatus: 'consulted', actorId: staff.id, actorRole: 'master' });

  const tasks = db.listTasks(['scheduled']);
  const waitingTask = tasks.find((item) => item.taskType === 'waiting_decision_followup' && item.payload?.requestId === requestA.id);
  const consultedTask = tasks.find((item) => item.taskType === 'consulted_followup' && item.payload?.requestId === requestB.id);
  assert.equal(Boolean(waitingTask), true);
  assert.equal(Boolean(consultedTask), true);

  const store = db.readStore();
  store.tasks = store.tasks.map((item) => {
    if (item.id === waitingTask.id || item.id === consultedTask.id) {
      return { ...item, dueAt: new Date(Date.now() - 1000).toISOString() };
    }
    return item;
  });
  db.replaceStore(store);

  const notifications = [];
  const scheduler = createScheduler({
    db,
    logger: { warn() {}, error() {} },
    handlers: {
      async waiting_decision_followup(item) {
        const result = db.reactivateWaitingDecisionRequest({ requestId: item.payload.requestId, actorId: 'scheduler', actorRole: 'system' });
        notifications.push({ type: 'waiting', requestId: result.request.id });
      },
      async consulted_followup(item) {
        const result = db.registerConsultedFollowup({ requestId: item.payload.requestId, actorId: 'scheduler', actorRole: 'system' });
        notifications.push({ type: 'consulted', requestId: result.request.id });
      }
    },
    batchSize: 10
  });

  const processed = await scheduler.runOnce();
  assert.equal(processed.processed, 2);

  const reloadedA = db.findRequestById(requestA.id);
  const reloadedB = db.findRequestById(requestB.id);
  assert.equal(reloadedA.status, 'in_progress');
  assert.equal(reloadedA.substatus, null);
  assert.equal(reloadedB.status, 'processed');
  assert.equal(reloadedB.substatus, 'consulted');
  assert.equal(Boolean(reloadedB.lastFollowupAt), true);
  assert.equal(notifications.length, 2);
});
