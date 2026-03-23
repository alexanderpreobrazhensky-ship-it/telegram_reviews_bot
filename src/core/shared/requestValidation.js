const REQUEST_STATUSES = Object.freeze(['new', 'in_progress', 'processed', 'in_service', 'completed', 'error']);
const REQUEST_SUBSTATUSES = Object.freeze(['recorded', 'consulted', 'spam', 'waiting_decision', 'rejected']);
const ARCHIVED_SUBSTATUSES = new Set(['spam', 'rejected']);
const TERMINAL_STATUSES = new Set(['completed']);
const IMMUTABLE_SUBSTATUSES = new Set(['spam', 'rejected']);
const FOLLOWUP_SUBSTATUSES = new Set(['waiting_decision', 'consulted']);
const REQUEST_EVENT_TYPES = Object.freeze([
  'created',
  'status_changed',
  'substatus_changed',
  'assigned',
  'comment_added',
  'duplicate_detected',
  'export_requested',
  'followup_scheduled',
  'followup_reactivated',
  'message_delivery_failed',
  'message_sent',
  'outbound_message_failed'
]);
const ANALYTICS_EVENT_TYPES = Object.freeze([
  'webapp_opened',
  'form_started',
  'invalid_phone',
  'submit_attempt',
  'request_created',
  'request_rejected',
  'status_changed',
  'assignment_changed',
  'max_webhook_received',
  'max_webhook_rejected'
]);
const ASSIGNMENT_ID_PATTERN = /^[a-zA-Z0-9:_-]{2,128}$/;

const STATUS_ALIASES = Object.freeze({
  assigned: 'in_progress',
  awaiting_client: 'error',
  waiting_data: 'error',
  scheduled: 'processed',
  done: 'completed',
  cancelled: 'processed',
  lost: 'processed',
  archived: 'completed'
});

const SUBSTATUS_ALIASES = Object.freeze({
  recorded: 'recorded',
  booked: 'recorded',
  consulted: 'consulted',
  consultation: 'consulted',
  spam: 'spam',
  waiting: 'waiting_decision',
  waiting_decision: 'waiting_decision',
  pending_decision: 'waiting_decision',
  rejected: 'rejected',
  refusal: 'rejected'
});

const STATUS_TRANSITIONS = Object.freeze({
  new: ['in_progress', 'processed', 'error'],
  in_progress: ['processed', 'in_service', 'error'],
  processed: ['in_progress', 'in_service', 'completed', 'error'],
  in_service: ['completed', 'processed', 'error'],
  completed: [],
  error: ['in_progress', 'processed']
});

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

function normalizeRequestStatus(status) {
  const value = String(status || '').trim();
  if (!value) return '';
  return STATUS_ALIASES[value] || value;
}

function normalizeRequestSubstatus(substatus) {
  const value = String(substatus || '').trim();
  if (!value) return '';
  return SUBSTATUS_ALIASES[value] || value;
}

function validateRequestStatus(status) {
  const value = normalizeRequestStatus(status);
  return REQUEST_STATUSES.includes(value) ? value : '';
}

function validateRequestSubstatus(substatus) {
  const value = normalizeRequestSubstatus(substatus);
  return REQUEST_SUBSTATUSES.includes(value) ? value : '';
}

function isArchivedStatus({ status, substatus, archived }) {
  return Boolean(archived || status === 'completed' || ARCHIVED_SUBSTATUSES.has(normalizeRequestSubstatus(substatus)));
}

function validateAssignment(assignedTo) {
  const value = String(assignedTo || '').trim();
  if (!value) return { ok: true, value: null };
  if (!ASSIGNMENT_ID_PATTERN.test(value)) return { ok: false, error: 'ASSIGNED_TO_INVALID' };
  return { ok: true, value };
}

function normalizeLegacyRequestState({ status, substatus = null, comment = null, archived = false } = {}) {
  let normalizedStatus = normalizeRequestStatus(status) || 'new';
  let normalizedSubstatus = validateRequestSubstatus(substatus) || null;
  let normalizedArchived = Boolean(archived);

  if (status === 'cancelled' || status === 'lost') {
    normalizedSubstatus = 'rejected';
    normalizedStatus = 'processed';
    normalizedArchived = true;
  }
  if (status === 'awaiting_client' || status === 'waiting_data') normalizedStatus = 'error';
  if (status === 'scheduled' && !normalizedSubstatus) normalizedSubstatus = 'recorded';
  if (status === 'done' || status === 'archived') normalizedArchived = true;
  if (ARCHIVED_SUBSTATUSES.has(normalizedSubstatus)) normalizedArchived = true;
  if (normalizedStatus === 'completed') normalizedArchived = true;
  return { status: normalizedStatus, substatus: normalizedSubstatus, archived: normalizedArchived, comment: comment || null };
}

function canTransitionRequest({ fromStatus, fromSubstatus = null, toStatus, toSubstatus = null, archived = false, allowArchived = false } = {}) {
  const currentStatus = validateRequestStatus(fromStatus);
  const nextStatus = validateRequestStatus(toStatus);
  const currentSubstatus = validateRequestSubstatus(fromSubstatus) || null;
  const nextSubstatus = validateRequestSubstatus(toSubstatus) || null;
  const requestArchived = isArchivedStatus({ status: currentStatus, substatus: currentSubstatus, archived });

  if (!currentStatus || !nextStatus) return { ok: false, error: 'INVALID_STATUS' };
  if (requestArchived && !allowArchived) return { ok: false, error: 'ARCHIVED_IMMUTABLE' };
  if (TERMINAL_STATUSES.has(currentStatus)) return { ok: false, error: 'COMPLETED_IMMUTABLE' };
  if (IMMUTABLE_SUBSTATUSES.has(currentSubstatus)) return { ok: false, error: 'ARCHIVED_IMMUTABLE' };
  if (currentStatus === 'new' && nextStatus === 'completed') return { ok: false, error: 'INVALID_TRANSITION' };
  if ((currentSubstatus === 'spam' || currentSubstatus === 'rejected') && nextStatus === 'in_service') return { ok: false, error: 'INVALID_TRANSITION' };
  if (currentStatus === nextStatus && currentSubstatus === nextSubstatus) return { ok: true, noop: true };
  if (!STATUS_TRANSITIONS[currentStatus]?.includes(nextStatus) && currentStatus !== nextStatus) {
    return { ok: false, error: 'INVALID_TRANSITION' };
  }
  if (nextStatus === 'processed' && !nextSubstatus) return { ok: false, error: 'SUBSTATUS_REQUIRED' };
  if (nextStatus !== 'processed' && nextSubstatus) return { ok: false, error: 'INVALID_SUBSTATUS' };
  return { ok: true, noop: false, fromStatus: currentStatus, toStatus: nextStatus, fromSubstatus: currentSubstatus, toSubstatus: nextSubstatus };
}

module.exports = {
  ANALYTICS_EVENT_TYPES,
  REQUEST_EVENT_TYPES,
  REQUEST_STATUSES,
  REQUEST_SUBSTATUSES,
  STATUS_TRANSITIONS,
  TERMINAL_STATUSES,
  IMMUTABLE_SUBSTATUSES,
  FOLLOWUP_SUBSTATUSES,
  validateClientRequestPayload,
  validateRequestStatus,
  validateRequestSubstatus,
  normalizeRequestStatus,
  normalizeRequestSubstatus,
  normalizeLegacyRequestState,
  canTransitionRequest,
  isArchivedStatus,
  validateAssignment
};
