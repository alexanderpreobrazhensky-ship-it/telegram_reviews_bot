function filterRequestsForExport(requests = [], filters = {}) {
  const fromMs = filters.from ? Date.parse(filters.from) : null;
  const toMs = filters.to ? Date.parse(filters.to) : null;
  const statuses = Array.isArray(filters.statuses) ? filters.statuses.filter(Boolean) : [];
  const requestTypes = Array.isArray(filters.requestTypes) ? filters.requestTypes.filter(Boolean) : [];
  const sourceChannels = Array.isArray(filters.sourceChannels) ? filters.sourceChannels.filter(Boolean) : [];

  return requests.filter((request) => {
    const createdAtMs = Date.parse(request.createdAt || '');
    if (Number.isFinite(fromMs) && (!Number.isFinite(createdAtMs) || createdAtMs < fromMs)) return false;
    if (Number.isFinite(toMs) && (!Number.isFinite(createdAtMs) || createdAtMs > toMs)) return false;
    if (statuses.length && !statuses.includes(String(request.status || ''))) return false;
    if (requestTypes.length && !requestTypes.includes(String(request.requestType || ''))) return false;
    if (sourceChannels.length && !sourceChannels.includes(String(request.sourceChannel || ''))) return false;
    return true;
  });
}

function mapRequestForExport(request, card = {}) {
  return {
    id: request.id,
    created_at: request.createdAt || '',
    status: request.status || '',
    source_channel: request.sourceChannel || '',
    request_type: request.requestType || '',
    phone: card.client?.phone || '',
    assigned_to: request.assignedTo || request.assignedMasterId || '',
    description: request.description || ''
  };
}

function serializeCsv(rows = []) {
  const headers = ['id', 'created_at', 'request_type', 'status', 'phone', 'source_channel', 'assigned_to', 'description'];
  const escape = (value) => {
    const raw = String(value ?? '');
    return /[",\n]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
  };
  return [headers.join(','), ...rows.map((row) => headers.map((key) => escape(row[key])).join(','))].join('\n');
}

module.exports = {
  filterRequestsForExport,
  mapRequestForExport,
  serializeCsv
};
