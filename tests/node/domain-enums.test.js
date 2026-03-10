const test = require('node:test');
const assert = require('node:assert/strict');
const { REQUEST_TYPES, REQUEST_STATUSES, VISIT_STATUSES, RECOMMENDATION_STATUSES, QUALITY_CASE_STATUSES } = require('../../src/core/domain');

test('agreed request types are fixed in domain enums', () => {
  assert.deepEqual(Object.values(REQUEST_TYPES), [
    'service_request',
    'parts_request',
    'warranty_request',
    'complaint_request',
    'feedback_request',
    'consultation_request',
    'callback_request',
    'data_change_request',
    'other_request'
  ]);
});

test('agreed status enums exist', () => {
  assert.equal(Object.values(REQUEST_STATUSES).includes('archived'), true);
  assert.equal(Object.values(VISIT_STATUSES).includes('closed'), true);
  assert.equal(Object.values(RECOMMENDATION_STATUSES).includes('deleted'), true);
  assert.equal(Object.values(QUALITY_CASE_STATUSES).includes('unresolved'), true);
});
