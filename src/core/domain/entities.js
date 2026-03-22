const { REQUEST_STATUSES, REQUEST_SUBSTATUSES, SOURCE_SYSTEM } = require('./enums');

const baseEntity = {
  id: 'uuid',
  createdAt: 'ISODate',
  updatedAt: 'ISODate',
  externalIds: {
    oneCId: null,
    legacyId: null
  },
  sourceOfTruth: SOURCE_SYSTEM.PLATFORM
};

const Client = {
  ...baseEntity,
  fullName: 'string',
  phone: 'string',
  email: 'string',
  channelAccounts: ['ChannelAccount.id'],
  vehicles: ['Vehicle.id']
};

const ChannelAccount = {
  ...baseEntity,
  clientId: 'Client.id',
  channel: 'telegram|vk|max|email',
  channelUserId: 'string',
  username: 'string|null'
};

const Vehicle = {
  ...baseEntity,
  clientId: 'Client.id',
  vin: 'string',
  plateNumber: 'string',
  brand: 'string',
  model: 'string'
};

const Request = {
  ...baseEntity,
  clientId: 'Client.id',
  vehicleId: 'Vehicle.id|null',
  requestType: 'REQUEST_TYPES',
  status: REQUEST_STATUSES.NEW,
  substatus: 'REQUEST_SUBSTATUSES|null',
  assignedTo: 'string|null',
  assignedAt: 'ISODate|null',
  archived: false,
  lastFollowupAt: 'ISODate|null',
  description: 'string',
  communicationEvents: ['CommunicationEvent.id']
};

const Visit = {
  ...baseEntity,
  clientId: 'Client.id',
  vehicleId: 'Vehicle.id',
  requestId: 'Request.id|null',
  status: 'VISIT_STATUSES',
  isRepeat: false,
  isWarranty: false,
  isPromo: false
};

const Recommendation = {
  ...baseEntity,
  clientId: 'Client.id',
  vehicleId: 'Vehicle.id',
  visitId: 'Visit.id|null',
  status: 'RECOMMENDATION_STATUSES',
  severity: 'RECOMMENDATION_SEVERITY',
  text: 'string'
};

const PartRequest = {
  ...baseEntity,
  clientId: 'Client.id',
  requestId: 'Request.id',
  partNumber: 'string',
  quantity: 1,
  status: 'new|ordered|received|cancelled'
};

const Feedback = {
  ...baseEntity,
  clientId: 'Client.id',
  requestId: 'Request.id|null',
  visitId: 'Visit.id|null',
  rating: 5,
  comment: 'string',
  sourceChannel: 'telegram|webapp|phone|other',
  createdBy: 'client|staff|system',
  status: 'received|escalated|closed',
  qualityCaseId: 'QualityCase.id|null'
};

const QualityCase = {
  ...baseEntity,
  clientId: 'Client.id|null',
  feedbackId: 'Feedback.id|null',
  requestId: 'Request.id|null',
  visitId: 'Visit.id|null',
  status: 'QUALITY_CASE_STATUSES',
  assignedTo: 'string|null',
  reasonCategory: 'string|null'
};

const CommunicationEvent = {
  ...baseEntity,
  clientId: 'Client.id|null',
  requestId: 'Request.id|null',
  channel: 'telegram|webapp|email|phone',
  direction: 'inbound|outbound',
  payload: {}
};

const Task = {
  ...baseEntity,
  taskType: 'feedback_request|quality_followup|recommendation_reminder|maintenance_reminder',
  dueAt: 'ISODate',
  processedAt: 'ISODate|null',
  status: 'scheduled|processing|completed|failed|cancelled',
  attemptCount: 0,
  lastError: 'string|null',
  payload: {}
};

const IntegrationEvent = {
  ...baseEntity,
  eventType: 'inbound|outbound|sync',
  integration: 'email|one_c|other',
  aggregateType: 'Request|Visit|Recommendation|Client',
  aggregateId: 'uuid',
  status: 'new|processed|failed|retrying',
  payload: {}
};

module.exports = {
  Client,
  ChannelAccount,
  Vehicle,
  Request,
  Visit,
  Recommendation,
  PartRequest,
  Feedback,
  QualityCase,
  CommunicationEvent,
  Task,
  IntegrationEvent
};
