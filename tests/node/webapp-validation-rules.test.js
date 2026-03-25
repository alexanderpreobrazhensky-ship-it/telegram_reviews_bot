const test = require('node:test');
const assert = require('node:assert/strict');
const { validateClientRequestPayload } = require('../../src/core/shared/requestValidation');

test('wasClientBefore=yes allows empty VIN', () => {
  const { errors } = validateClientRequestPayload({
    fullName: 'Иванов',
    phone: '9991112233',
    wasClientBefore: 'yes',
    brand: 'Lada',
    model: 'Vesta',
    year: '2024',
    description: 'test',
    vin: ''
  }, 'service_request');
  assert.equal(errors.length, 0);
});

test('wasClientBefore=no requires VIN', () => {
  const { errors } = validateClientRequestPayload({
    fullName: 'Иванов',
    phone: '9991112233',
    wasClientBefore: 'no',
    brand: 'Lada',
    model: 'Vesta',
    year: '2024',
    description: 'test',
    vin: ''
  }, 'service_request');
  assert.ok(errors.includes('vin is required when wasClientBefore is no'));
});

test('wasClientBefore is mandatory', () => {
  const { errors } = validateClientRequestPayload({
    fullName: 'Иванов',
    phone: '9991112233',
    brand: 'Lada',
    model: 'Vesta',
    year: '2024',
    description: 'test',
    vin: 'VIN'
  }, 'service_request');
  assert.ok(errors.includes('wasClientBefore must be selected'));
});

test('wasClientBefore=no with VIN is allowed', () => {
  const { errors } = validateClientRequestPayload({
    fullName: 'Иванов',
    phone: '9991112233',
    wasClientBefore: 'no',
    brand: 'Lada',
    model: 'Vesta',
    year: '2024',
    description: 'test',
    vin: 'VIN'
  }, 'service_request');
  assert.equal(errors.length, 0);
});
