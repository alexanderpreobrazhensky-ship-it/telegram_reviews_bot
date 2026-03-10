const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const DB_PATH = process.env.DB_FILE_PATH || path.join(process.cwd(), 'data', 'db.json');

function ensureStore() {
  if (!fs.existsSync(path.dirname(DB_PATH))) {
    fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
  }

  if (!fs.existsSync(DB_PATH)) {
    const now = new Date().toISOString();
    const initial = {
      clients: [],
      vehicles: [],
      requests: [],
      communicationEvents: [],
      recommendations: [
        { id: crypto.randomUUID(), clientId: null, text: 'Проверить состояние тормозных колодок в ближайшие 500 км.', severity: 'critical', status: 'actual', createdAt: now, interested: false },
        { id: crypto.randomUUID(), clientId: null, text: 'Рекомендуется сезонная диагностика кондиционера.', severity: 'normal', status: 'actual', createdAt: now, interested: false }
      ]
    };
    fs.writeFileSync(DB_PATH, JSON.stringify(initial, null, 2));
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
      createdAt: new Date().toISOString()
    };
    store.clients.push(client);
  } else {
    client.fullName = fullName || client.fullName;
    client.phone = phone || client.phone;
    client.telegramId = telegramId || client.telegramId;
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
    vehicle = { id: crypto.randomUUID(), clientId, brand: brand || '', model: model || '', year: year || '', vin: vin || '', plateNumber: plateNumber || '', createdAt: new Date().toISOString() };
    store.vehicles.push(vehicle);
  } else {
    Object.assign(vehicle, { brand: brand || vehicle.brand, model: model || vehicle.model, year: year || vehicle.year, vin: vin || vehicle.vin, plateNumber: plateNumber || vehicle.plateNumber });
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
    createdAt: new Date().toISOString()
  };
  store.requests.push(request);
  writeStore(store);
  return request;
}

function createCommunicationEvent({ clientId, requestId, source, payload }) {
  const store = readStore();
  const event = { id: crypto.randomUUID(), clientId: clientId || null, requestId: requestId || null, source, payload, createdAt: new Date().toISOString() };
  store.communicationEvents.push(event);
  writeStore(store);
  return event;
}

function listRequests({ phone, telegramId }) {
  const store = readStore();
  const client = store.clients.find((c) => (phone && c.phone === phone) || (telegramId && c.telegramId === telegramId));
  if (!client) return [];
  return store.requests.filter((r) => r.clientId === client.id).map((r) => ({ ...r, summary: r.description.slice(0, 120) }));
}

function listRecommendations({ phone, telegramId }) {
  const store = readStore();
  const client = store.clients.find((c) => (phone && c.phone === phone) || (telegramId && c.telegramId === telegramId));
  return store.recommendations.filter((r) => r.status === 'actual' && (!r.clientId || (client && r.clientId === client.id)));
}

function markRecommendationInterest(id) {
  const store = readStore();
  const recommendation = store.recommendations.find((r) => r.id === id);
  if (!recommendation) return null;
  recommendation.interested = true;
  writeStore(store);
  return recommendation;
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
  resetStore,
  readStore
};
