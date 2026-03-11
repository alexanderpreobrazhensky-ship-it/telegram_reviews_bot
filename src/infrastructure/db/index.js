const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const DB_PATH = process.env.DB_FILE_PATH || path.join(process.cwd(), 'data', 'db.json');

function nowIso() {
  return new Date().toISOString();
}

function makeInitialStore() {
  const now = nowIso();
  return {
    clients: [],
    vehicles: [],
    requests: [],
    communicationEvents: [],
    recommendations: [
      { id: crypto.randomUUID(), clientId: null, text: 'Проверить состояние тормозных колодок в ближайшие 500 км.', severity: 'critical', status: 'actual', createdAt: now, interested: false },
      { id: crypto.randomUUID(), clientId: null, text: 'Рекомендуется сезонная диагностика кондиционера.', severity: 'normal', status: 'actual', createdAt: now, interested: false }
    ],
    staffUsers: [],
    requestStatusHistory: [],
    requestInternalComments: [],
    clientInternalNotes: [],
    masterActions: [],
    qualityCases: [],
    qualityCaseComments: [],
    feedback: [],
    tasks: []
  };
}

function ensureStore() {
  if (!fs.existsSync(path.dirname(DB_PATH))) {
    fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
  }

  if (!fs.existsSync(DB_PATH)) {
    fs.writeFileSync(DB_PATH, JSON.stringify(makeInitialStore(), null, 2));
    return;
  }

  const store = JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
  const initial = makeInitialStore();
  let changed = false;
  for (const [key, value] of Object.entries(initial)) {
    if (!Object.hasOwn(store, key)) {
      store[key] = value;
      changed = true;
    }
  }
  if (changed) {
    fs.writeFileSync(DB_PATH, JSON.stringify(store, null, 2));
  }
}

function readStore() {
  ensureStore();
  return JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
}

function writeStore(store) {
  fs.writeFileSync(DB_PATH, JSON.stringify(store, null, 2));
}

function upsertClient({ fullName, phone, telegramId }) {
  const store = readStore();
  let client = store.clients.find((c) => (telegramId && c.telegramId === telegramId) || (phone && c.phone === phone));
  if (!client) {
    client = {
      id: crypto.randomUUID(),
      fullName,
      phone,
      telegramId: telegramId || null,
      preferredChannel: 'telegram',
      createdAt: nowIso()
    };
    store.clients.push(client);
  } else {
    client.fullName = fullName || client.fullName;
    client.phone = phone || client.phone;
    client.telegramId = telegramId || client.telegramId;
    client.updatedAt = nowIso();
  }
  writeStore(store);
  return client;
}

function upsertVehicle({ clientId, brand, model, year, vin, plateNumber }) {
  if (!brand && !model && !year && !vin && !plateNumber) {
    return null;
  }
  const store = readStore();
  let vehicle = store.vehicles.find((v) => v.clientId === clientId && ((vin && v.vin === vin) || (plateNumber && v.plateNumber === plateNumber)));
  if (!vehicle) {
    vehicle = { id: crypto.randomUUID(), clientId, brand: brand || '', model: model || '', year: year || '', vin: vin || '', plateNumber: plateNumber || '', createdAt: nowIso() };
    store.vehicles.push(vehicle);
  } else {
    Object.assign(vehicle, { brand: brand || vehicle.brand, model: model || vehicle.model, year: year || vehicle.year, vin: vin || vehicle.vin, plateNumber: plateNumber || vehicle.plateNumber, updatedAt: nowIso() });
  }
  writeStore(store);
  return vehicle;
}

function createRequest({ clientId, vehicleId, requestType, description, sourceChannel }) {
  const store = readStore();
  const request = {
    id: crypto.randomUUID(),
    clientId,
    vehicleId: vehicleId || null,
    requestType,
    status: 'new',
    sourceChannel,
    description: description || '',
    assignedMasterId: null,
    lostReason: null,
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
  store.requests.push(request);
  store.requestStatusHistory.push({
    id: crypto.randomUUID(),
    requestId: request.id,
    fromStatus: null,
    toStatus: 'new',
    changedBy: 'system',
    changedByRole: 'system',
    reason: null,
    createdAt: nowIso()
  });
  writeStore(store);
  return request;
}

function createCommunicationEvent({ clientId, requestId, source, payload }) {
  const store = readStore();
  const event = { id: crypto.randomUUID(), clientId: clientId || null, requestId: requestId || null, source, payload, createdAt: nowIso() };
  store.communicationEvents.push(event);
  writeStore(store);
  return event;
}

function recordMasterAction({ actorId, role, action, requestId = null, clientId = null, payload = {} }) {
  const store = readStore();
  const item = { id: crypto.randomUUID(), actorId, role, action, requestId, clientId, payload, createdAt: nowIso() };
  store.masterActions.push(item);
  writeStore(store);
  return item;
}

function resolveStaffUser({ telegramId, fullName }) {
  const store = readStore();
  const tid = String(telegramId || '');
  let user = store.staffUsers.find((u) => u.telegramId === tid);
  if (!user) {
    user = { id: crypto.randomUUID(), telegramId: tid, fullName: fullName || `master_${tid}`, role: 'master', createdAt: nowIso() };
    store.staffUsers.push(user);
    writeStore(store);
  }
  return user;
}

function listRequests({ phone, telegramId, statuses }) {
  const store = readStore();
  let requests = store.requests;
  if (phone || telegramId) {
    const client = store.clients.find((c) => (phone && c.phone === phone) || (telegramId && c.telegramId === telegramId));
    if (!client) return [];
    requests = requests.filter((r) => r.clientId === client.id);
  }
  if (statuses?.length) {
    requests = requests.filter((r) => statuses.includes(r.status));
  }
  return requests.map((r) => ({ ...r, summary: r.description.slice(0, 120) }));
}

function listRecommendations({ phone, telegramId, clientId = null, includeHistory = false }) {
  const store = readStore();
  let resolvedClientId = clientId;
  if (!resolvedClientId && (phone || telegramId)) {
    const client = store.clients.find((c) => (phone && c.phone === phone) || (telegramId && c.telegramId === telegramId));
    resolvedClientId = client?.id || null;
  }
  return store.recommendations.filter((r) => {
    if (!includeHistory && r.status !== 'actual') return false;
    if (!r.clientId) return true;
    return resolvedClientId && r.clientId === resolvedClientId;
  });
}

function markRecommendationInterest(id) {
  const store = readStore();
  const recommendation = store.recommendations.find((r) => r.id === id);
  if (!recommendation) return null;
  recommendation.interested = true;
  writeStore(store);
  return recommendation;
}

const allowedRequestTransitions = {
  new: ['waiting_data', 'in_progress'],
  waiting_data: ['in_progress'],
  in_progress: ['processed', 'lost'],
  processed: ['archived'],
  lost: ['archived'],
  archived: []
};

function updateRequestStatus({ requestId, toStatus, actorId, actorRole, lostReason = null }) {
  const store = readStore();
  const request = store.requests.find((item) => item.id === requestId);
  if (!request) return { error: 'REQUEST_NOT_FOUND' };
  const fromStatus = request.status;
  if (!allowedRequestTransitions[fromStatus]?.includes(toStatus)) {
    return { error: 'INVALID_TRANSITION', fromStatus, toStatus };
  }
  if (toStatus === 'lost' && !String(lostReason || '').trim()) {
    return { error: 'LOST_REASON_REQUIRED' };
  }
  request.status = toStatus;
  request.updatedAt = nowIso();
  request.lostReason = toStatus === 'lost' ? lostReason : request.lostReason;
  if (!request.assignedMasterId && actorId) {
    request.assignedMasterId = actorId;
  }
  const history = {
    id: crypto.randomUUID(),
    requestId,
    fromStatus,
    toStatus,
    changedBy: actorId,
    changedByRole: actorRole,
    reason: toStatus === 'lost' ? lostReason : null,
    createdAt: nowIso()
  };
  store.requestStatusHistory.push(history);
  store.communicationEvents.push({
    id: crypto.randomUUID(),
    clientId: request.clientId,
    requestId,
    source: 'master_bot',
    payload: { action: 'request_status_changed', fromStatus, toStatus, actorId, actorRole, lostReason: history.reason },
    createdAt: nowIso()
  });
  store.masterActions.push({ id: crypto.randomUUID(), actorId, role: actorRole, action: 'request_status_changed', requestId, clientId: request.clientId, payload: { fromStatus, toStatus, lostReason: history.reason }, createdAt: nowIso() });

  if (toStatus === 'processed') {
    const feedbackTaskExists = store.tasks.some((task) => task.taskType === 'feedback_request' && task.status !== 'cancelled' && task.payload?.requestId === requestId);
    if (!feedbackTaskExists) {
      const delayMinutes = Number(process.env.FEEDBACK_REQUEST_DELAY_MINUTES || 5);
      const dueAt = new Date(Date.now() + Math.max(0, delayMinutes) * 60 * 1000).toISOString();
      store.tasks.push({
        id: crypto.randomUUID(),
        taskType: 'feedback_request',
        status: 'scheduled',
        dueAt,
        createdAt: nowIso(),
        processedAt: null,
        attemptCount: 0,
        lastError: null,
        payload: {
          clientId: request.clientId,
          requestId,
          assignedMasterId: request.assignedMasterId || null
        }
      });
    }
  }

  writeStore(store);
  return { request, history };
}

function addInternalComment({ requestId, actorId, actorRole, text }) {
  const store = readStore();
  const request = store.requests.find((item) => item.id === requestId);
  if (!request) return null;
  const comment = {
    id: crypto.randomUUID(),
    requestId,
    actorId,
    actorRole,
    text,
    createdAt: nowIso()
  };
  store.requestInternalComments.push(comment);
  store.masterActions.push({ id: crypto.randomUUID(), actorId, role: actorRole, action: 'request_internal_comment_added', requestId, clientId: request.clientId, payload: { commentId: comment.id }, createdAt: nowIso() });
  writeStore(store);
  return comment;
}

function addClientNote({ clientId, actorId, actorRole, text }) {
  const store = readStore();
  if (!store.clients.find((item) => item.id === clientId)) return null;
  const note = { id: crypto.randomUUID(), clientId, actorId, actorRole, text, createdAt: nowIso() };
  store.clientInternalNotes.push(note);
  store.masterActions.push({ id: crypto.randomUUID(), actorId, role: actorRole, action: 'client_note_added', requestId: null, clientId, payload: { noteId: note.id }, createdAt: nowIso() });
  writeStore(store);
  return note;
}

function searchCRM(query) {
  const store = readStore();
  const q = String(query || '').trim().toLowerCase();
  if (!q) return { clients: [], requests: [] };

  const matchedVehicles = store.vehicles.filter((v) => [v.vin, v.plateNumber].some((value) => String(value || '').toLowerCase().includes(q)));
  const vehicleIds = new Set(matchedVehicles.map((v) => v.id));
  const clientIdsFromVehicle = new Set(matchedVehicles.map((v) => v.clientId));

  const clients = store.clients.filter((c) => {
    const nameMatch = String(c.fullName || '').toLowerCase().includes(q);
    const phoneMatch = String(c.phone || '').toLowerCase().includes(q);
    const vehicleMatch = clientIdsFromVehicle.has(c.id);
    return nameMatch || phoneMatch || vehicleMatch;
  });
  const clientIds = new Set(clients.map((c) => c.id));

  const requests = store.requests.filter((r) => clientIds.has(r.clientId) || vehicleIds.has(r.vehicleId));
  return { clients, requests };
}

function getClientCard(clientId) {
  const store = readStore();
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return null;
  return {
    client,
    telegramBinding: client.telegramId || null,
    vehicles: store.vehicles.filter((v) => v.clientId === clientId),
    requests: store.requests.filter((r) => r.clientId === clientId),
    recommendations: store.recommendations.filter((r) => !r.clientId || r.clientId === clientId),
    internalNotes: store.clientInternalNotes.filter((n) => n.clientId === clientId)
  };
}

function getRequestCard(requestId) {
  const store = readStore();
  const request = store.requests.find((item) => item.id === requestId);
  if (!request) return null;
  const client = store.clients.find((item) => item.id === request.clientId) || null;
  const vehicle = store.vehicles.find((item) => item.id === request.vehicleId) || null;
  const master = store.staffUsers.find((item) => item.id === request.assignedMasterId) || null;
  return {
    request,
    client,
    vehicle,
    assignedMaster: master,
    statusHistory: store.requestStatusHistory.filter((h) => h.requestId === requestId),
    internalComments: store.requestInternalComments.filter((c) => c.requestId === requestId)
  };
}

function listQualityCases(statuses = []) {
  const store = readStore();
  const cases = statuses.length ? store.qualityCases.filter((item) => statuses.includes(item.status)) : store.qualityCases;
  return cases;
}

function createQualityCase({ requestId, status = 'new', assignedTo = null, summary = 'Manual quality case' }) {
  const store = readStore();
  const request = requestId ? store.requests.find((item) => item.id === requestId) : null;
  const qualityCase = {
    id: crypto.randomUUID(),
    requestId,
    clientId: request?.clientId || null,
    feedbackId: null,
    status,
    assignedTo,
    reasonCategory: null,
    summary,
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
  store.qualityCases.push(qualityCase);
  writeStore(store);
  return qualityCase;
}

function findClientByTelegramId(telegramId) {
  const store = readStore();
  return store.clients.find((item) => item.telegramId === String(telegramId || '')) || null;
}

function findRequestById(requestId) {
  const store = readStore();
  return store.requests.find((item) => item.id === requestId) || null;
}

function createFeedback({ clientId, requestId = null, visitId = null, rating, comment = '', sourceChannel = 'telegram', createdBy = 'client' }) {
  const store = readStore();
  const request = requestId ? store.requests.find((item) => item.id === requestId) : null;
  let qualityCase = null;
  const feedback = {
    id: crypto.randomUUID(),
    clientId,
    requestId,
    visitId,
    rating,
    comment,
    sourceChannel,
    createdAt: nowIso(),
    createdBy,
    status: 'received',
    qualityCaseId: null
  };
  store.feedback.push(feedback);

  store.communicationEvents.push({
    id: crypto.randomUUID(),
    clientId,
    requestId,
    source: sourceChannel,
    payload: { action: 'feedback_received', feedbackId: feedback.id, rating, comment },
    createdAt: nowIso()
  });

  if (rating < 3) {
    qualityCase = {
      id: crypto.randomUUID(),
      clientId,
      feedbackId: feedback.id,
      requestId,
      status: 'new',
      assignedTo: request?.assignedMasterId || null,
      reasonCategory: 'low_rating',
      summary: `Автокейс по низкой оценке (${rating}/5)`,
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
    store.qualityCases.push(qualityCase);
    feedback.qualityCaseId = qualityCase.id;
    feedback.status = 'escalated';

    store.communicationEvents.push({
      id: crypto.randomUUID(),
      clientId,
      requestId,
      source: 'system',
      payload: {
        action: 'quality_case_created_from_feedback',
        qualityCaseId: qualityCase.id,
        feedbackId: feedback.id,
        duplicateForRole: 'manager'
      },
      createdAt: nowIso()
    });

    store.masterActions.push({
      id: crypto.randomUUID(),
      actorId: 'system',
      role: 'system',
      action: 'quality_case_auto_created_from_feedback',
      requestId,
      clientId,
      payload: { qualityCaseId: qualityCase.id, feedbackId: feedback.id, assignedTo: qualityCase.assignedTo, duplicateForRole: 'manager' },
      createdAt: nowIso()
    });
  }

  writeStore(store);
  return { feedback, qualityCase };
}

function createTask({ taskType, dueAt, payload = {} }) {
  const store = readStore();
  const task = {
    id: crypto.randomUUID(),
    taskType,
    status: 'scheduled',
    dueAt: dueAt || nowIso(),
    createdAt: nowIso(),
    processedAt: null,
    attemptCount: 0,
    lastError: null,
    payload
  };
  store.tasks.push(task);
  writeStore(store);
  return task;
}

function listTasks(statuses = []) {
  const store = readStore();
  return statuses.length ? store.tasks.filter((item) => statuses.includes(item.status)) : store.tasks;
}

function claimDueTasks({ now = new Date().toISOString(), limit = 10 } = {}) {
  const store = readStore();
  const due = store.tasks
    .filter((task) => task.status === 'scheduled' && task.dueAt <= now)
    .sort((a, b) => String(a.dueAt).localeCompare(String(b.dueAt)))
    .slice(0, limit);

  due.forEach((task) => {
    task.status = 'processing';
    task.attemptCount += 1;
    task.lastError = null;
  });
  if (due.length) writeStore(store);
  return due;
}

function completeTask(taskId) {
  const store = readStore();
  const task = store.tasks.find((item) => item.id === taskId);
  if (!task) return null;
  task.status = 'completed';
  task.processedAt = nowIso();
  writeStore(store);
  return task;
}

function failTask(taskId, error, maxAttempts = 3) {
  const store = readStore();
  const task = store.tasks.find((item) => item.id === taskId);
  if (!task) return null;
  task.lastError = String(error || 'unknown_error');
  task.status = task.attemptCount >= maxAttempts ? 'failed' : 'scheduled';
  if (task.status === 'scheduled') {
    task.dueAt = new Date(Date.now() + Math.min(task.attemptCount, 5) * 60 * 1000).toISOString();
  } else {
    task.processedAt = nowIso();
  }
  writeStore(store);
  return task;
}

function updateQualityCaseStatus({ qualityCaseId, status, actorId, actorRole }) {
  const store = readStore();
  const qualityCase = store.qualityCases.find((item) => item.id === qualityCaseId);
  if (!qualityCase) return null;
  qualityCase.status = status;
  qualityCase.updatedAt = nowIso();
  store.masterActions.push({ id: crypto.randomUUID(), actorId, role: actorRole, action: 'quality_case_status_changed', requestId: qualityCase.requestId, clientId: null, payload: { qualityCaseId, status }, createdAt: nowIso() });
  writeStore(store);
  return qualityCase;
}

function addQualityCaseComment({ qualityCaseId, actorId, actorRole, text }) {
  const store = readStore();
  const qualityCase = store.qualityCases.find((item) => item.id === qualityCaseId);
  if (!qualityCase) return null;
  const comment = { id: crypto.randomUUID(), qualityCaseId, actorId, actorRole, text, createdAt: nowIso() };
  store.qualityCaseComments.push(comment);
  store.masterActions.push({ id: crypto.randomUUID(), actorId, role: actorRole, action: 'quality_case_comment_added', requestId: qualityCase.requestId, clientId: null, payload: { qualityCaseId, commentId: comment.id }, createdAt: nowIso() });
  writeStore(store);
  return comment;
}

function getQualityCaseCard(qualityCaseId) {
  const store = readStore();
  const qualityCase = store.qualityCases.find((item) => item.id === qualityCaseId);
  if (!qualityCase) return null;
  return {
    qualityCase,
    request: store.requests.find((r) => r.id === qualityCase.requestId) || null,
    comments: store.qualityCaseComments.filter((c) => c.qualityCaseId === qualityCaseId)
  };
}

function resetStore() {
  if (fs.existsSync(DB_PATH)) fs.unlinkSync(DB_PATH);
  ensureStore();
}

module.exports = {
  DB_PATH,
  upsertClient,
  upsertVehicle,
  createRequest,
  createCommunicationEvent,
  listRequests,
  listRecommendations,
  markRecommendationInterest,
  resolveStaffUser,
  recordMasterAction,
  updateRequestStatus,
  addInternalComment,
  addClientNote,
  searchCRM,
  getClientCard,
  getRequestCard,
  listQualityCases,
  createQualityCase,
  updateQualityCaseStatus,
  addQualityCaseComment,
  getQualityCaseCard,
  findClientByTelegramId,
  findRequestById,
  createFeedback,
  createTask,
  listTasks,
  claimDueTasks,
  completeTask,
  failTask,
  resetStore,
  readStore
};
