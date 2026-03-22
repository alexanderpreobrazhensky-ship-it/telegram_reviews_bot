# Master Audit for External AI

## Scope
Compact source of truth for the next GPT/AI agent that needs to reason about the repository and then perform runtime checks without re-discovering the whole project.

## Current state
- Production reality is Node-first.
- Entrypoint: `app.js`.
- Main server/runtime router: `src/server/index.js`.
- Main config loader: `src/infrastructure/config/index.js`.
- Main persistence module: `src/infrastructure/db/index.js`.
- Main WebApp runtime: `public/webapp.js` served through `public/index.html` with server-side runtime injection.
- Telegram client bot, Telegram master bot, Telegram integration bot, MAX client bot, and MAX master bot all live in the same Node service.

## Confirmed facts
### Production reality summary
- This is not a Python-first project in production terms.
- This is not a JSON-first project in production terms.
- BotHost and Docker point at `app.js`.
- SQLite is the active persistence engine.
- MAX is embedded in the same runtime, not deployed as a separate project.

### Active runtime path summary
- Bootstrap: `app.js`.
- HTTP server and route map: `src/server/index.js`.
- Bot handlers: `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js`, `src/interfaces/integration_bot/index.js`.
- MAX security gate: `src/interfaces/shared/maxSecurity.js`.
- Shared messaging/deeplink utilities: `src/infrastructure/messaging/index.js`.
- WebApp client logic: `public/webapp.js`.

### Env reality summary
- Truly required baseline in code: `WEBAPP_URL` and `DB_SQLITE_PATH` or `DB_FILE_PATH` in strict mode.
- Operationally critical Telegram env: `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`.
- Operationally critical MAX env when MAX is enabled: `MAX_ENABLED`, `MAX_CLIENT_BOT_TOKEN`, `MAX_MASTER_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_MASTER_BOT_ADMIN_IDS`.
- Canonical DB env is `DB_SQLITE_PATH`; `DB_FILE_PATH` is legacy compatibility.

### Persistence reality summary
- Active DB is SQLite.
- Legacy JSON import path still exists and can run on first empty init.
- If `DB_FILE_PATH` ends in `.json`, runtime DB still becomes `.sqlite`.
- Request dedupe is heuristic, not hard uniqueness.

### Telegram / MAX / WebApp reality summary
- Telegram is the more mature/proven channel.
- MAX has real code paths and tests, but live readiness still needs runtime confirmation.
- Integration bot is Telegram-only.
- WebApp forms are active and use a 10-digit phone model.
- WebApp identity uses provider runtime objects / submitted IDs and is not cryptographically verified.

### Confirmed risks summary
- Unauthenticated integration/reporting/mutation endpoints at app-layer.
- Telegram webhook requests lack in-app secret verification.
- Internal admin pages use allowlisted IDs rather than stronger auth.
- In-memory sessions and rate limits are instance-local.
- Deploy/runtime drift is still possible if env or BotHost config is stale.

## What changed after modernization
- Node-first runtime is now the canonical truth.
- SQLite-first persistence replaced JSON-first descriptions.
- MAX should now be treated as an embedded supported contour, not as a non-existent one.
- Phone-input and request-validation narratives now match the fixed 10-digit implementation.

## Remaining gaps
- No live runtime confirmation is embedded in the repo.
- No cryptographic WebApp identity verification.
- No auth on several operational/integration endpoints.
- No proof here of actual BotHost persistent-volume behavior.

## Risks
- A stale production env can still undermine the code-confirmed architecture.
- Multi-instance scaling would require rethinking scheduler, rate limiting, dedupe, and session handling.
- External platform configuration remains outside repo proof.

## Legacy / dead / misleading parts
- Do not start analysis from `bots/**`, `services/**`, `shared/clients_registry.py`, or `legacy/index.js`.
- Do not treat `src/interfaces/webapp/routes.js` as the real route source.
- Do not describe the project as Python-first, JSON-first, or legacy-first.
- Do not describe session-specific mini-app anomalies as global blockers unless reproduced.

## Confidence level
High for repository truth; medium for live production truth.

## Recommended follow-up checks
- Check live env values for: `WEBAPP_URL`, `DB_SQLITE_PATH`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `MAX_ENABLED`, `MAX_CLIENT_BOT_TOKEN`, `MAX_MASTER_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_MASTER_BOT_ADMIN_IDS`, `MAX_WEBAPP_URL`.
- Verify `/health`, `/health/db`, and `/health/max` in the live environment.
- Create one Telegram WebApp request and one MAX WebApp request end-to-end.
- Verify Telegram client bot, Telegram master bot, Telegram integration bot, MAX client bot, and MAX master bot with real credentials.
- Confirm SQLite persistence across a real restart/redeploy.
- Check whether unauthenticated integration/reporting endpoints are protected by the production perimeter.
