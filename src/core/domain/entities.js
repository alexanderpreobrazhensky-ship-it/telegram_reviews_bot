const { REQUEST_STATUSES, SOURCE_SYSTEM } = require('./enums');

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
  comment: 'string'
};

const QualityCase = {
  ...baseEntity,
  requestId: 'Request.id',
  visitId: 'Visit.id|null',
  status: 'QUALITY_CASE_STATUSES',
  assignedTo: 'string|null'
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
  taskType: 'reminder|quality_followup|recommendation_followup|integration_retry',
  scheduledAt: 'ISODate',
  status: 'pending|running|completed|failed',
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
