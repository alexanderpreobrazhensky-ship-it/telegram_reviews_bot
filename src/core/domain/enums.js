const REQUEST_TYPES = Object.freeze({
  SERVICE: 'service_request',
  PARTS: 'parts_request',
  WARRANTY: 'warranty_request',
  COMPLAINT: 'complaint_request',
  FEEDBACK: 'feedback_request',
  CONSULTATION: 'consultation_request',
  CALLBACK: 'callback_request',
  DATA_CHANGE: 'data_change_request',
  OTHER: 'other_request'
});

const REQUEST_STATUSES = Object.freeze({
  NEW: 'new',
  ASSIGNED: 'assigned',
  AWAITING_CLIENT: 'awaiting_client',
  SCHEDULED: 'scheduled',
  IN_SERVICE: 'in_service',
  DONE: 'done',
  CANCELLED: 'cancelled'
});

const VISIT_STATUSES = Object.freeze({
  SCHEDULED: 'scheduled',
  IN_SERVICE: 'in_service',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
  NO_SHOW: 'no_show',
  CLOSED: 'closed'
});

const RECOMMENDATION_STATUSES = Object.freeze({
  ACTUAL: 'actual',
  COMPLETED: 'completed',
  DECLINED: 'declined',
  EXPIRED: 'expired',
  DELETED: 'deleted'
});

const RECOMMENDATION_SEVERITY = Object.freeze({
  NORMAL: 'normal',
  CRITICAL: 'critical'
});

const QUALITY_CASE_STATUSES = Object.freeze({
  NEW: 'new',
  ASSIGNED: 'assigned',
  IN_PROGRESS: 'in_progress',
  RESOLVED: 'resolved',
  UNRESOLVED: 'unresolved',
  ARCHIVED: 'archived'
});

const SOURCE_SYSTEM = Object.freeze({
  PLATFORM: 'platform',
  TELEGRAM: 'telegram',
  MAX: 'max',
  WEBAPP: 'webapp',
  EMAIL: 'email',
  ONE_C: 'one_c'
});

module.exports = {
  REQUEST_TYPES,
  REQUEST_STATUSES,
  VISIT_STATUSES,
  RECOMMENDATION_STATUSES,
  RECOMMENDATION_SEVERITY,
  QUALITY_CASE_STATUSES,
  SOURCE_SYSTEM
};
