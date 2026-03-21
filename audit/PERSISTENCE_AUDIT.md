# Persistence Audit

## Scope
Active persistence layer, initialization path, schema creation, startup behavior with empty/existing stores, migration, import/export mechanics, and data-integrity risks.

## Current state
- Active persistence is SQLite through `better-sqlite3` in `src/infrastructure/db/index.js`.
- `DB_SQLITE_PATH` is canonical; `DB_FILE_PATH` remains a compatibility alias.
- On first init, schema is created automatically.
- If the SQLite DB is empty and a legacy JSON file exists, the app performs a one-time import into SQLite.

## Confirmed facts
- Driver: SQLite only in the active runtime.
- Initialization enables WAL mode, `synchronous=NORMAL`, and `foreign_keys=ON`.
- Schema includes clients, vehicles, requests, request events, communications, tasks, staff users, quality cases, analytics events, recommendations, feedback, report snapshots, and meta.
- Phone is stored with a 10-digit constraint at the DB layer for clients.
- `replaceStore()` exists for import-style replacement in tests/utilities.
- Export exists as an HTTP internal export (`/internal/export`) for requests only; there is no general-purpose full DB export/import UI.

## Behavior audit
### Empty DB
- Schema is created.
- If a legacy JSON store is available and the main tables are empty, import runs and records migration metadata.

### Existing DB
- Existing SQLite file is opened in place.
- Schema creation is idempotent (`CREATE TABLE IF NOT EXISTS`).

### Migration / import
- JSON → SQLite import is destructive for target tables during the import transaction because it clears target tables before rehydration.
- Migration metadata is written to the `meta` table.

## Integrity assessment
- Transactionality: strong for operations wrapped in SQLite transactions, including JSON import and several multi-step mutations.
- Idempotency: mixed. Upserts exist for many entities, but webhook/event processing still relies on higher-level logic and dedupe heuristics.
- Duplicate risk: present for request creation; mitigated by recent-duplicate detection, but duplicates are still created then marked.
- Silent reset risk: low for normal startup, medium for any operator invoking import/replace flows without care.
- Data consistency risk: medium because some relationships are modeled in JSON payload fragments rather than strict relational joins.

## Risks
- `replaceStore()` and JSON import are destructive operations against the current SQLite content.
- Deduplication is advisory rather than a unique constraint.
- `synchronous=NORMAL` improves performance but is slightly weaker than FULL durability under hard crashes.
- In-process scheduler/task handling is safe for the current single-node model but risky for uncontrolled multi-instance operation.

## Gaps
- No formal migration framework versioning beyond ad hoc schema evolution and meta tracking.
- No full backup/restore CLI documented in the app itself.
- No immutable audit log outside the primary SQLite store.

## Legacy / dead / misleading parts
- Legacy JSON persistence still influences startup logic and naming, even though SQLite is now canonical.
- `DB_DRIVER`/`DB_URL` suggest pluggability that is not implemented.

## Recommendations
1. Keep SQLite as the canonical store and document BotHost persistence paths operationally.
2. Add a protected backup/export workflow before any destructive import or replace operation.
3. If concurrency increases, move from heuristic dedupe to stronger uniqueness strategy per request source and identity.
4. Add an explicit migration version ledger if schema changes accelerate.

## Confidence level
High.

## Follow-up checks
- Verify the real BotHost DB path survives redeploy and restart.
- Before any production data import, capture a SQLite backup and test restore.
