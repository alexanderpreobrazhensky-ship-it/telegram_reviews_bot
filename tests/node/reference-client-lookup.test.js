const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Database = require('better-sqlite3');
const db = require('../../src/infrastructure/db');
const logger = require('../../src/infrastructure/logging/logger');
const { loadConfig } = require('../../src/infrastructure/config');
const { createServer } = require('../../src/server');
const { createReferenceClientLookup, normalizeFio, normalizePhoneForLookup } = require('../../src/infrastructure/referenceClientLookup');

function createReferenceFixture() {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'reference-client-lookup-'));
  const dbPath = path.join(tmpDir, 'reference.sqlite');
  const sqlite = new Database(dbPath);
  sqlite.exec(`
    CREATE TABLE clients (
      client_code TEXT,
      client_name TEXT,
      client_name_norm TEXT,
      phone_norm TEXT,
      source_system TEXT
    );
  `);
  const insert = sqlite.prepare('INSERT INTO clients (client_code, client_name, client_name_norm, phone_norm, source_system) VALUES (?, ?, ?, ?, ?)');
  insert.run('C-1', 'Иванов Иван Иванович', 'ИВАНОВ ИВАН ИВАНОВИЧ', '9991112233', 'fixture_1c');
  insert.run('C-2', 'Петров Петр Петрович', 'ПЕТРОВ ПЕТР ПЕТРОВИЧ', '9991112244', 'fixture_1c');
  insert.run('C-3', 'Смирнов Семен Семенович', 'СМИРНОВ СЕМЕН СЕМЕНОВИЧ', '9995550000', 'fixture_1c');
  insert.run('C-4', 'Смирнов Семен Семенович', 'СМИРНОВ СЕМЕН СЕМЕНОВИЧ', '9995550000', 'fixture_1c');
  sqlite.close();
  return { tmpDir, dbPath };
}

async function withServer(env, run) {
  const prev = {};
  for (const [key, value] of Object.entries(env)) {
    prev[key] = process.env[key];
    process.env[key] = value;
  }
  db.resetStore();
  const config = loadConfig();
  const server = createServer({ config, logger });
  await new Promise((resolve) => server.listen(0, resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run(base);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    for (const [key, value] of Object.entries(prev)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test('lookup normalizes phone/fio and classifies exact/no/conflict cases deterministically', () => {
  const fixture = createReferenceFixture();
  try {
    const lookup = createReferenceClientLookup({ datasetPath: fixture.dbPath, logger: { info() {} } });

    assert.equal(normalizePhoneForLookup('+7 (999) 111-22-33'), '9991112233');
    assert.equal(normalizePhoneForLookup('8 (999) 111-22-33'), '9991112233');
    assert.equal(normalizeFio('  ИВАНОВ   ИВАН   ИВАНОВИЧ  '), 'иванов иван иванович');
    assert.equal(normalizeFio('Ёлкин Ёж'), 'елкин еж');

    const exact = lookup.lookupByPhoneAndFio({ phone: '+7 (999) 111-22-33', fullName: '  иВанОВ   Иван Иванович ' });
    assert.equal(exact.existingClient, true);
    assert.equal(exact.clientMatchBasis, 'phone_fio');
    assert.equal(exact.matchedReferenceClientId, 'C-1');
    assert.equal(exact.needsReview, false);

    const onlyPhone = lookup.lookupByPhoneAndFio({ phone: '89991112244', fullName: 'Совсем Другой Клиент' });
    assert.equal(onlyPhone.existingClient, false);
    assert.equal(onlyPhone.clientMatchBasis, 'phone_fio_no_match');
    assert.equal(onlyPhone.needsReview, false);

    const onlyFio = lookup.lookupByPhoneAndFio({ phone: '9000000000', fullName: 'Петров Петр Петрович' });
    assert.equal(onlyFio.existingClient, false);
    assert.equal(onlyFio.clientMatchBasis, 'phone_fio_no_match');

    const none = lookup.lookupByPhoneAndFio({ phone: '9111111111', fullName: 'Новый Клиент' });
    assert.equal(none.existingClient, false);
    assert.equal(none.clientMatchBasis, 'phone_fio_no_match');

    const multiple = lookup.lookupByPhoneAndFio({ phone: '+7 (999) 555-00-00', fullName: 'Смирнов Семен Семенович' });
    assert.equal(multiple.existingClient, false);
    assert.equal(multiple.needsReview, true);
    assert.equal(multiple.clientMatchBasis, 'conflict_multiple_matches');
    assert.equal(Array.isArray(multiple.matchedReferenceSnapshot.candidates), true);
    assert.equal(multiple.matchedReferenceSnapshot.candidates.length, 2);
  } finally {
    fs.rmSync(fixture.tmpDir, { recursive: true, force: true });
  }
});

test('webapp request persists existing_client flags and master card shows them', async () => {
  const fixture = createReferenceFixture();
  try {
    await withServer(
      {
        REFERENCE_CLIENT_LOOKUP_SQLITE_PATH: fixture.dbPath,
        WEBAPP_EXISTING_CLIENT_LOOKUP_ENABLED: 'true',
        MASTER_BOT_ADMIN_IDS: '5001'
      },
      async (base) => {
        const response = await fetch(`${base}/api/client/requests/service`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            fullName: '  ИВАНОВ   ИВАН   ИВАНОВИЧ ',
            phone: '9991112233',
            wasClientBefore: 'yes',
            brand: 'Lada',
            model: 'Vesta',
            year: '2024',
            vin: 'VIN-EXACT-MATCH',
            description: 'Проверка existing client'
          })
        });
        assert.equal(response.status, 201);
        const created = await response.json();
        assert.equal(created.payload.existing_client, true);
        assert.equal(created.payload.client_match_basis, 'phone_fio');
        assert.equal(created.payload.matched_reference_client_id, 'C-1');
        assert.equal(created.payload.needs_review, false);

        const search = await fetch(`${base}/telegram/master_bot/webhook`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: { text: '/search 9991112233', chat: { id: 5001 }, from: { id: 5001, first_name: 'Admin' } } })
        });
        const payload = await search.json();
        assert.equal(payload.ok, true);
        assert.match(payload.text, /Действующий клиент: Да/i);
        assert.match(payload.text, /Основание проверки: phone_fio/i);
        assert.match(payload.text, /ID в reference-базе: C-1/i);
      }
    );
  } finally {
    fs.rmSync(fixture.tmpDir, { recursive: true, force: true });
  }
});
