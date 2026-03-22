const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));

test('production path is node-first', () => {
  assert.equal(packageJson.main, 'app.js');
  assert.equal(fs.existsSync('app.js'), true);
});

test('centralized repository audit file exists under audit/', () => {
  assert.equal(fs.existsSync('audit/MASTER_AUDIT.md'), true);
});
