# Persistence Audit

## Scope
Current persistence model, SQLite path resolution, schema creation, JSON import compatibility, integrity behavior, and remaining data-loss / duplicate risks.

## Current state
- The active persistence layer is SQLite via `better-sqlite3` in `src/infrastructure/db/index.js`.
- The runtime resolves its active DB path from `DB_SQLITE_PATH`, then legacy `DB_FILE_PATH`, then a default `data/db.sqlite` path.
- If the configured/legacy path ends in `.json`, the active runtime DB path is rewritten to a `.sqlite` filename while the JSON path remains eligible for import.
- Schema creation is automatic and idempotent at startup.

## Confirmed facts
### Confirmed by code
- SQLite is the only implemented active database driver in production code.
- The DB connection enables `journal_mode = WAL`, `synchronous = NORMAL`, and `foreign_keys = ON`.
- `initializeStore()` creates the schema and then conditionally imports legacy JSON when the SQLite store is empty and a legacy JSON file exists.
- `getLegacyJsonPath()` can use `DB_JSON_IMPORT_PATH`; otherwise it derives the path from legacy/default logic.
- Schema includes at least: `clients`, `vehicles`, `requests`, `request_events`, `communications`, `tasks`, `staff_users`, `quality_cases`, `analytics_events`, `recommendations`, `feedback`, `report_snapshots`, and `meta`.
- Clients have a DB-level `CHECK` constraint limiting stored phone values to either `NULL` or exactly 10 digits.
- Requests, analytics events, communications, tasks, quality cases, feedback, and report snapshots are all stored in SQLite and then rehydrated into JS objects.
- The runtime still supports destructive JSON-to-SQLite import and whole-store replacement helpers, which are used in tests and migration-style logic.
- Request duplicate handling is heuristic: new requests are still created, then marked as duplicates if a recent match is found.
- Task processing and reporting snapshots are persisted in SQLite, not in memory-only structures.

### Confirmed by tests
- SQLite file creation, table creation, JSON migration, CRUD persistence, and restart survival are covered by `tests/node/sqlite-persistence.test.js`.

### Confirmed only by runtime/deploy assumption
- The live BotHost filesystem path configured for SQLite is assumed to be persistent.
- The live production DB is assumed to already be on SQLite unless an operator still deploys with a JSON-oriented env mismatch.

### Unresolved / hypothesis only
- There is no runtime evidence in this repo alone that production has completed any needed one-time JSON import already.
- There is no direct proof here that operators are backing up the SQLite file before destructive migration/import operations.

## What changed after modernization
- SQLite is now the canonical persistence layer; JSON is no longer the primary store.
- Initialization now explicitly logs DB runtime info and migration status at boot.
- Request lifecycle state, analytics, quality cases, feedback, tasks, and reporting snapshots are all aligned to the SQLite-backed runtime.
- The project moved from “legacy JSON-first possibility” to “SQLite-first with compatibility import path.”

## Remaining gaps
- There is no formal migration framework with explicit version files.
- There is no built-in backup/restore CLI for operators.
- Some relational links still depend on JSON payload fields in addition to table columns.
- The DB module still exposes destructive helpers that would need careful operational handling if used outside tests.

## Risks
- If production is misconfigured with a legacy JSON path, operators may misunderstand where the active `.sqlite` file is actually written.
- JSON import and `replaceStore()` are destructive operations for target tables.
- Duplicate prevention is advisory, not enforced by a unique DB constraint.
- `synchronous = NORMAL` trades some durability margin for performance.
- Multi-instance deployment would raise integrity risk for scheduler/task claiming and duplicate heuristics unless carefully coordinated.

## Legacy / dead / misleading parts
- `DB_FILE_PATH` and `DB_JSON_IMPORT_PATH` remain legacy-oriented persistence knobs.
- The presence of JSON import logic should not be described as JSON-first persistence anymore.
- `DB_DRIVER` and `DB_URL` are misleading for persistence architecture because alternate DB drivers are not implemented in the active path.

## Confidence level
High for code-confirmed persistence behavior; medium for live production data location and migration state because runtime filesystem inspection was not performed.

## Recommended follow-up checks
- Confirm the live production env points to the intended SQLite file path.
- Verify that the active `.sqlite` file survives restart and redeploy in BotHost.
- Before any migration/import activity, take and test a SQLite backup.
- If request dedupe becomes business-critical, consider unique constraints or stronger idempotency keys.
