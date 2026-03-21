# Repository Full Audit

## Scope
Repository structure, production relevance, legacy contours, misleading files, and file-placement compliance after the current deploy state.

## Current state
- The active runtime is a single Node.js service rooted at `app.js`, `src/server/index.js`, `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js`, bot interface adapters, and `public/webapp.js`.
- Repository reality is narrower than the tree shape suggests: `src/**`, `public/**`, `.bothost/entrypoint.conf`, `Dockerfile`, `package.json`, and `tests/node/**` drive the real platform; `bots/**`, `services/**`, `shared/**`, `legacy/index.js`, and Python tests are historical/supporting material.
- Audit files are now centralized only under `audit/`, and operational README files are centralized only under `readme/`.

## Confirmed facts
- Deploy contract is Node-first: `package.json` starts `node app.js`, `.bothost/entrypoint.conf` points to `app.js`, and `Dockerfile` runs `node app.js`.
- Production-relevant directories: `src/core/**`, `src/infrastructure/**`, `src/interfaces/**`, `src/integrations/**`, `src/server/**`, `public/**`, `data/`, `.bothost/`, and `tests/node/**`.
- Supporting but not production-critical: `tests/test_*.py` (skipped), `.github/**`, and audit/readme documentation.
- Legacy/historical: `bots/client_bot/**`, `services/client_bot_service/**`, `shared/clients_registry.py`, and `legacy/index.js`.
- Dead or misleading surface:
  - `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` are not authoritative runtime routers.
  - Python contour files can still imply an older architecture if someone scans the tree superficially.

## Risks
- Legacy Python and historical folders remain close to the active path and can mislead future maintainers.
- Some placeholder config names (`DB_DRIVER`, `QUEUE_DRIVER`, `ENABLE_INTEGRATION_WORKER`) imply infrastructure that does not yet exist.
- MAX foundation files exist in the active runtime, but feature parity is still partial compared with Telegram.

## Gaps
- No explicit archive boundary separates legacy Python materials from live Node production code.
- There is no generated route or module manifest in code; repository understanding still depends on manual reading.
- Some scaffolding modules remain checked in even though the authoritative route map lives in `src/server/index.js`.

## Legacy / dead / misleading parts
- `bots/**`, `services/**`, `shared/clients_registry.py`: historical Python contour, not the active deploy path.
- `legacy/index.js`: not referenced by the live bootstrap chain.
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js`: scaffolding/documentation-adjacent, not runtime source of truth.

## Recommendations
1. Keep treating the Node contour as canonical for all deploy and product work.
2. Move legacy Python assets into a clearer archive area or mark them even more explicitly.
3. Add a generated route/runtime manifest if future contributors keep getting lost in the tree.
4. Remove or clearly annotate scaffolding modules that are not runtime-authoritative.

## Confidence level
High. The production path is directly confirmed by executable files and passing Node tests.

## Follow-up checks
- Re-run repository drift checks whenever legacy folders are moved or revived.
- If a separate MAX/BotHost topology is ever proposed, verify it still respects the current “single Node-first project” constraint.
