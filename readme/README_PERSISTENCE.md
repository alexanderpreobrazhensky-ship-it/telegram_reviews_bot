# Persistence

## Canonical store
SQLite via `src/infrastructure/db/index.js`.

## Path rules
- Prefer `DB_SQLITE_PATH`.
- `DB_FILE_PATH` still works as a legacy alias.
- If a legacy `.json` path is supplied, the runtime converts the active DB path to `.sqlite` and can import JSON on first empty init.

## Important behavior
- Schema is auto-created.
- SQLite uses WAL mode.
- Legacy JSON import exists for migration.
- Request export exists via `/internal/export`.

## Operational caution
- Treat import/replace flows as destructive operations unless backed up first.
