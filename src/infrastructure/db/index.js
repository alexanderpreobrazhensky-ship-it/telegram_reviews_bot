const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const DB_PATH = process.env.DB_FILE_PATH || path.join(process.cwd(), 'data', 'db.json');

function nowIso() {
  return new Date().toISOString();
}

function safeReadStoreRaw() {
  try {
    return JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
  } catch {
    return makeInitialStore();
  }
}

function makeInitialStore() {
  const now = nowIso();
  return {
    clients: [],
    vehicles: [],
    visits: [],
    requests: [],
    communicationEvents: [],
    integrationEvents: [],
    integrationEventLogs: [],
    recommendations: [],
    recommendationSync: { lastSyncAt: null, source: null },
    staffUsers: [],
    requestStatusHistory: [],
    requestInternalComments: [],
    clientInternalNotes: [],
    masterActions: [],
    qualityCases: [],
    qualityCaseComments: [],
    feedback: [],
    tasks: [],
    reportSnapshots: []
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

  const store = safeReadStoreRaw();
  const initial = makeInitialStore();
  let changed = false;
  for (const [key, value] of Object.entries(initial)) {
    if (!Object.hasOwn(store, key)) {
      store[key] = value;
      changed = true;
    }
  }


  for (const task of store.tasks || []) {
    if (!Object.hasOwn(task, 'processingStartedAt')) {
      task.processingStartedAt = null;
      changed = true;
    }
    if (!Object.hasOwn(task, 'updatedAt')) {
      task.updatedAt = task.createdAt || nowIso();
      changed = true;
    }
  }

  const entityCollections = ['clients', 'vehicles', 'visits', 'requests', 'recommendations'];
  for (const collection of entityCollections) {
    for (const item of store[collection] || []) {
      if (!item.externalIds) {
        item.externalIds = {};
        changed = true;
      }
      if (!item.sourceSystem) {
        item.sourceSystem = 'system';
        changed = true;
      }
      if (!item.sourceOfTruth) {
        item.sourceOfTruth = 'local';
        changed = true;
      }
      if (!Object.hasOwn(item, 'lastSyncedAt')) {
        item.lastSyncedAt = null;
        changed = true;
      }
      if (!Object.hasOwn(item, 'localPendingChanges')) {
        item.localPendingChanges = false;
        changed = true;
      }
      if (!Object.hasOwn(item, 'needsManualReview')) {
        item.needsManualReview = false;
        changed = true;
      }
    }
  }

  if (changed) {
    fs.writeFileSync(DB_PATH, JSON.stringify(store, null, 2));
  }
}

function readStore() {
  ensureStore();
  return safeReadStoreRaw();
}

function writeStore(store) {
  const tempPath = `${DB_PATH}.tmp`;
  fs.writeFileSync(tempPath, JSON.stringify(store, null, 2));
  fs.renameSync(tempPath, DB_PATH);
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
      externalIds: {},
      sourceSystem: 'system',
      sourceOfTruth: 'local',
      lastSyncedAt: null,
      localPendingChanges: false,
      needsManualReview: false,
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
    vehicle = {
      id: crypto.randomUUID(),
      clientId,
      brand: brand || '',
      model: model || '',
      year: year || '',
      vin: vin || '',
      plateNumber: plateNumber || '',
      externalIds: {},
      sourceSystem: 'system',
      sourceOfTruth: 'local',
      lastSyncedAt: null,
      localPendingChanges: false,
      needsManualReview: false,
      createdAt: nowIso()
    };
    store.vehicles.push(vehicle);
  } else {
    Object.assign(vehicle, { brand: brand || vehicle.brand, model: model || vehicle.model, year: year || vehicle.year, vin: vin || vehicle.vin, plateNumber: plateNumber || vehicle.plateNumber, updatedAt: nowIso() });
  }
  writeStore(store);
  return vehicle;
}

function createRequest({ clientId, vehicleId, requestType, description, sourceChannel, payload = {} }) {
  const store = readStore();
  const request = {
    id: crypto.randomUUID(),
    clientId,
    vehicleId: vehicleId || null,
    requestType,
    status: 'new',
    sourceChannel,
    description: description || '',
    payload: payload || {},
    assignedMasterId: null,
    lostReason: null,
    externalIds: {},
    sourceSystem: sourceChannel || 'system',
    sourceOfTruth: 'local',
    lastSyncedAt: null,
    localPendingChanges: false,
    needsManualReview: false,
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

function resolveStaffUser({ telegramId, fullName, adminTelegramIds = [] }) {
  const store = readStore();
  const tid = String(telegramId || '').trim();
  if (!tid) return null;
  const adminSet = new Set((adminTelegramIds || []).map((id) => String(id).trim()).filter(Boolean));
  const isEnvAdmin = adminSet.has(tid);
  let user = store.staffUsers.find((u) => u.telegramId === tid) || null;

  if (isEnvAdmin) {
    if (!user) {
      user = { id: crypto.randomUUID(), telegramId: tid, fullName: fullName || `admin_${tid}`, role: 'admin', createdAt: nowIso(), updatedAt: nowIso() };
      store.staffUsers.push(user);
      writeStore(store);
    } else if (user.role !== 'admin') {
      user.role = 'admin';
      user.updatedAt = nowIso();
      if (fullName) user.fullName = fullName;
      writeStore(store);
    }
    return user;
  }

  if (!user) return null;
  if (fullName && fullName !== user.fullName) {
    user.fullName = fullName;
    user.updatedAt = nowIso();
    writeStore(store);
  }
  return user;
}

function listStaffUsers() {
  const store = readStore();
  return [...store.staffUsers].sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
}

function createStaffUser({ telegramId, fullName, role, actorId = null, actorRole = null }) {
  const allowedRoles = new Set(['master', 'manager']);
  if (!allowedRoles.has(role)) return { error: 'INVALID_ROLE' };
  const tid = String(telegramId || '').trim();
  if (!tid) return { error: 'TELEGRAM_ID_REQUIRED' };

  const store = readStore();
  let user = store.staffUsers.find((item) => item.telegramId === tid) || null;
  if (user) {
    if (user.role === 'admin') return { error: 'ADMIN_ROLE_IMMUTABLE' };
    user.role = role;
    user.fullName = fullName || user.fullName || `staff_${tid}`;
    user.updatedAt = nowIso();
  } else {
    user = { id: crypto.randomUUID(), telegramId: tid, fullName: fullName || `staff_${tid}`, role, createdAt: nowIso(), updatedAt: nowIso() };
    store.staffUsers.push(user);
  }

  store.masterActions.push({
    id: crypto.randomUUID(),
    actorId,
    role: actorRole,
    action: 'staff_user_upserted',
    requestId: null,
    clientId: null,
    payload: { staffUserId: user.id, telegramId: tid, role },
    createdAt: nowIso()
  });

  writeStore(store);
  return { user };
}

function revokeStaffUser({ telegramId, actorId = null, actorRole = null }) {
  const tid = String(telegramId || '').trim();
  if (!tid) return { error: 'TELEGRAM_ID_REQUIRED' };
  const store = readStore();
  const index = store.staffUsers.findIndex((item) => item.telegramId === tid);
  if (index === -1) return { error: 'STAFF_USER_NOT_FOUND' };
  if (store.staffUsers[index].role === 'admin') return { error: 'ADMIN_ROLE_IMMUTABLE' };
  const [removed] = store.staffUsers.splice(index, 1);
  store.masterActions.push({
    id: crypto.randomUUID(),
    actorId,
    role: actorRole,
    action: 'staff_user_revoked',
    requestId: null,
    clientId: null,
    payload: { staffUserId: removed.id, telegramId: tid },
    createdAt: nowIso()
  });
  writeStore(store);
  return { user: removed };
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

function listRecommendations({ phone, telegramId, clientId = null, includeHistory = false, requireSynced = false }) {
  const store = readStore();
  if (requireSynced && !store.recommendationSync?.lastSyncAt) return [];
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
  recommendation.updatedAt = nowIso();
  writeStore(store);
  return recommendation;
}

function upsertRecommendationFromSync({ externalId = null, clientId = null, text = '', severity = 'normal', status = 'actual' }) {
  const store = readStore();
  let item = null;
  if (externalId) {
    item = store.recommendations.find((r) => r.externalIds?.one_c === String(externalId)) || null;
  }
  if (!item) {
    item = {
      id: crypto.randomUUID(),
      clientId: clientId || null,
      text: String(text || '').trim(),
      severity,
      status,
      interested: false,
      externalIds: externalId ? { one_c: String(externalId) } : {},
      createdAt: nowIso(),
      updatedAt: nowIso()
    };
    store.recommendations.push(item);
  } else {
    item.clientId = clientId || item.clientId || null;
    item.text = String(text || item.text || '').trim();
    item.severity = severity || item.severity || 'normal';
    item.status = status || item.status || 'actual';
    item.updatedAt = nowIso();
  }
  store.recommendationSync = { lastSyncAt: nowIso(), source: 'one_c' };
  writeStore(store);
  return item;
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
        processingStartedAt: null,
        updatedAt: nowIso(),
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

function findRecentDuplicateRequest({ requestType, phone, vin, text, withinMs = 45000 }) {
  const store = readStore();
  const normalizedPhone = String(phone || '').trim();
  const normalizedVin = String(vin || '').trim().toUpperCase();
  const normalizedText = String(text || '').trim().toLowerCase();
  const now = Date.now();
  const windowMs = Math.max(1000, Number(withinMs) || 45000);

  for (let i = store.requests.length - 1; i >= 0; i -= 1) {
    const request = store.requests[i];
    if (request.requestType !== requestType) continue;
    const createdAtMs = Date.parse(request.createdAt || '');
    if (!Number.isFinite(createdAtMs) || now - createdAtMs > windowMs) continue;
    const client = store.clients.find((item) => item.id === request.clientId) || null;
    if (!client || String(client.phone || '').trim() !== normalizedPhone) continue;
    const vehicle = request.vehicleId ? (store.vehicles.find((item) => item.id === request.vehicleId) || null) : null;
    const vinMatch = normalizedVin ? String(vehicle?.vin || '').trim().toUpperCase() === normalizedVin : true;
    if (!vinMatch) continue;
    const textMatch = String(request.description || '').trim().toLowerCase() === normalizedText;
    if (!textMatch) continue;
    return request;
  }
  return null;
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
    processingStartedAt: null,
    updatedAt: nowIso(),
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

function claimDueTasks({ now = new Date().toISOString(), limit = 10, stuckTimeoutMs = 300000 } = {}) {
  const store = readStore();
  const nowMs = Date.parse(now);
  for (const task of store.tasks) {
    if (task.status !== 'processing') continue;
    const startedAtMs = Date.parse(task.processingStartedAt || task.updatedAt || task.createdAt || now);
    if (!Number.isFinite(startedAtMs)) continue;
    if (nowMs - startedAtMs >= Math.max(1000, Number(stuckTimeoutMs) || 300000)) {
      task.status = 'scheduled';
      task.lastError = task.lastError || 'PROCESSING_RECOVERED_AS_STUCK';
      task.processingStartedAt = null;
      task.updatedAt = nowIso();
    }
  }

  const due = store.tasks
    .filter((task) => task.status === 'scheduled' && task.dueAt <= now)
    .sort((a, b) => String(a.dueAt).localeCompare(String(b.dueAt)))
    .slice(0, limit);

  due.forEach((task) => {
    task.status = 'processing';
    task.attemptCount += 1;
    task.lastError = null;
    task.processingStartedAt = nowIso();
    task.updatedAt = nowIso();
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
  task.processingStartedAt = null;
  task.updatedAt = nowIso();
  writeStore(store);
  return task;
}

function failTask(taskId, error, maxAttempts = 3) {
  const store = readStore();
  const task = store.tasks.find((item) => item.id === taskId);
  if (!task) return null;
  task.lastError = String(error || 'unknown_error');
  task.status = task.attemptCount >= maxAttempts ? 'failed' : 'scheduled';
  task.processingStartedAt = null;
  if (task.status === 'scheduled') {
    task.dueAt = new Date(Date.now() + Math.min(task.attemptCount, 5) * 60 * 1000).toISOString();
    task.updatedAt = nowIso();
  } else {
    task.processedAt = nowIso();
    task.updatedAt = nowIso();
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



function createReportSnapshot({ reportType, periodType, periodStart, periodEnd, metrics, summaryText, generatedBy = 'manual', sourceDataVersion = null, notes = null }) {
  const store = readStore();
  const snapshot = {
    id: crypto.randomUUID(),
    reportType,
    periodType,
    periodStart,
    periodEnd,
    generatedAt: nowIso(),
    metrics,
    summaryText,
    generatedBy,
    sourceDataVersion,
    notes
  };
  store.reportSnapshots.push(snapshot);
  writeStore(store);
  return snapshot;
}

function listReportSnapshots({ limit = 50 } = {}) {
  const store = readStore();
  return [...store.reportSnapshots]
    .sort((a, b) => String(b.generatedAt).localeCompare(String(a.generatedAt)))
    .slice(0, limit);
}

function getReportSnapshotById(id) {
  const store = readStore();
  return store.reportSnapshots.find((item) => item.id === id) || null;
}

function resetStore() {
  if (fs.existsSync(DB_PATH)) fs.unlinkSync(DB_PATH);
  ensureStore();
}

function createIntegrationEvent({ sourceSystem, eventType, rawPayload, dedupeKey = null }) {
  const store = readStore();
  const event = {
    id: crypto.randomUUID(),
    sourceSystem,
    eventType,
    rawPayload,
    normalizedPayload: null,
    processingStatus: 'received',
    processingAttemptCount: 0,
    lastError: null,
    createdAt: nowIso(),
    processedAt: null,
    relatedEntityType: null,
    relatedEntityId: null,
    dedupeKey
  };
  store.integrationEvents.push(event);
  store.integrationEventLogs.push({ id: crypto.randomUUID(), eventId: event.id, status: 'received', message: 'Event received', createdAt: nowIso() });
  writeStore(store);
  return event;
}

function updateIntegrationEvent(eventId, patch = {}, logMessage = null) {
  const store = readStore();
  const event = store.integrationEvents.find((item) => item.id === eventId);
  if (!event) return null;
  Object.assign(event, patch);
  if (patch.processingStatus === 'processed' || patch.processingStatus === 'failed' || patch.processingStatus === 'ignored') {
    event.processedAt = event.processedAt || nowIso();
  }
  if (logMessage || patch.processingStatus) {
    store.integrationEventLogs.push({
      id: crypto.randomUUID(),
      eventId,
      status: patch.processingStatus || event.processingStatus,
      message: logMessage || null,
      createdAt: nowIso()
    });
  }
  writeStore(store);
  return event;
}

function getIntegrationEventById(eventId) {
  const store = readStore();
  return store.integrationEvents.find((item) => item.id === eventId) || null;
}

function listIntegrationEvents({ status, sourceSystem, limit = 20 } = {}) {
  const store = readStore();
  let items = [...store.integrationEvents];
  if (status) items = items.filter((item) => item.processingStatus === status);
  if (sourceSystem) items = items.filter((item) => item.sourceSystem === sourceSystem);
  return items.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))).slice(0, limit);
}

function getIntegrationEventCard(eventId) {
  const store = readStore();
  const event = store.integrationEvents.find((item) => item.id === eventId);
  if (!event) return null;
  return { event, logs: store.integrationEventLogs.filter((item) => item.eventId === eventId) };
}

function applyEntitySyncMetadata({ collection, entityId, metadata = {} }) {
  const store = readStore();
  const entity = (store[collection] || []).find((item) => item.id === entityId);
  if (!entity) return null;
  entity.externalIds = { ...(entity.externalIds || {}), ...(metadata.externalIds || {}) };
  if (metadata.sourceSystem) entity.sourceSystem = metadata.sourceSystem;
  if (metadata.sourceOfTruth) entity.sourceOfTruth = metadata.sourceOfTruth;
  if (Object.hasOwn(metadata, 'lastSyncedAt')) entity.lastSyncedAt = metadata.lastSyncedAt;
  if (Object.hasOwn(metadata, 'localPendingChanges')) entity.localPendingChanges = metadata.localPendingChanges;
  if (Object.hasOwn(metadata, 'needsManualReview')) entity.needsManualReview = metadata.needsManualReview;
  entity.updatedAt = nowIso();
  writeStore(store);
  return entity;
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
  upsertRecommendationFromSync,
  resolveStaffUser,
  listStaffUsers,
  createStaffUser,
  revokeStaffUser,
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
  findRecentDuplicateRequest,
  createFeedback,
  createTask,
  listTasks,
  claimDueTasks,
  completeTask,
  failTask,
  createReportSnapshot,
  listReportSnapshots,
  getReportSnapshotById,
  resetStore,
  readStore,
  createIntegrationEvent,
  updateIntegrationEvent,
  getIntegrationEventById,
  listIntegrationEvents,
  getIntegrationEventCard,
  applyEntitySyncMetadata
};
