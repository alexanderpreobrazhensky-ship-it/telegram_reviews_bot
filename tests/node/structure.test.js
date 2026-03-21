const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const requiredPaths = [
  'app.js',
  'package.json',
  'readme/README.md',
  'audit/REPOSITORY_FULL_AUDIT.md',
  'src/core/domain',
  'src/core/application',
  'src/interfaces/client_bot',
  'src/interfaces/master_bot',
  'src/interfaces/integration_bot',
  'src/interfaces/webapp',
  'src/integrations/email',
  'src/integrations/one_c',
  'src/infrastructure/db',
  'src/infrastructure/queue',
  'src/infrastructure/scheduler',
  'public'
];

test('required skeleton paths exist', () => {
  for (const requiredPath of requiredPaths) {
    assert.equal(fs.existsSync(requiredPath), true, `missing ${requiredPath}`);
  }
});
