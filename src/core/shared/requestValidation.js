
const REQUEST_STATUSES = Object.freeze(['new', 'assigned', 'awaiting_client', 'scheduled', 'in_service', 'done', 'cancelled']);
const ASSIGNMENT_ID_PATTERN = /^[a-zA-Z0-9:_-]{2,128}$/;

function resolveStrictClientPhone(body = {}) {
  const candidates = [
    body.phone,
    body.phoneNumber,
    body.nativeContact?.phoneNumber,
    body.nativeContact?.phone,
    body.contact?.phoneNumber,
    body.contact?.phone,
    body.telegramContact?.phone_number,
    body.maxContact?.phoneNumber
  ];

  for (const value of candidates) {
    if (value === undefined || value === null) continue;
    const normalizedValue = String(value).trim();
    if (!normalizedValue) continue;
    return normalizedValue;
  }

  return '';
}

function validateClientRequestPayload(body = {}, type) {
  const errors = [];
  const requiredByType = {
    service_request: ['fullName', 'phone', 'wasClientBefore', 'brand', 'model', 'year', 'vin', 'description'],
    parts_request: ['fullName', 'phone', 'wasClientBefore', 'year', 'vin', 'description'],
    consultation_request: ['fullName', 'phone', 'wasClientBefore', 'car', 'vin', 'question'],
    warranty_request: ['fullName', 'phone', 'visitDate', 'description'],
    data_change_request: ['fullName', 'phone', 'changeDetails']
  };

  const phone = resolveStrictClientPhone(body);
  for (const field of requiredByType[type] || []) {
    if (field === 'phone') {
      if (!/^\d{10}$/.test(phone)) errors.push('phone must contain exactly 10 digits');
      continue;
    }
    if (!String(body[field] || '').trim()) errors.push(`${field} is required`);
  }

  if ((requiredByType[type] || []).includes('phone') && !/^\d{10}$/.test(phone) && !errors.includes('phone must contain exactly 10 digits')) {
    errors.push('phone must contain exactly 10 digits');
  }

  return { errors, normalizedPhone: phone };
}

function validateRequestStatus(status) {
  const value = String(status || '').trim();
  return REQUEST_STATUSES.includes(value) ? value : '';
}

function validateAssignment(assignedTo) {
  const value = String(assignedTo || '').trim();
  if (!value) return { ok: false, error: 'ASSIGNED_TO_REQUIRED' };
  if (!ASSIGNMENT_ID_PATTERN.test(value)) return { ok: false, error: 'ASSIGNED_TO_INVALID' };
  return { ok: true, value };
}

module.exports = {
  REQUEST_STATUSES,
  validateClientRequestPayload,
  validateRequestStatus,
  validateAssignment
};
