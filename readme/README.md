# telegram_reviews_bot documentation contour

## Project purpose
`telegram_reviews_bot` is a Node.js-first service platform for an auto-service business. One HTTP process serves the shared WebApp, accepts Telegram and MAX webhooks for the client and master bots, stores operational data in a JSON file database, exposes reporting and integration APIs, and runs an in-process scheduler for follow-up tasks.

The current production contour is **not** the legacy Python bot. The active deploy path is the Node application rooted at `app.js` and `package.json`.

## Production contract
- **Runtime:** Node.js 18+.
- **Entrypoint:** `app.js`.
- **Server:** `src/server/index.js`.
- **Deploy manifest:** `package.json` + `package-lock.json`.
- **BotHost entrypoint:** `.bothost/entrypoint.conf` points to `app.js` on branch `main`.
- **Container contract:** `Dockerfile` installs with `npm ci --omit=dev` and starts `node app.js`.
- **Persistence contract:** JSON file at `DB_FILE_PATH` or `data/db.json`.
- **Protected files:** `review.html` and `public/index.html` must remain untouched.

## Runtime model
### Active production path
1. `app.js` loads runtime config from `src/infrastructure/config/index.js`.
2. `app.js` creates the HTTP server from `src/server/index.js`.
3. The server registers client, master, and integration bot webhook adapters.
4. The same process initializes the JSON DB layer and the in-process scheduler.
5. After `server.listen()`, the scheduler starts polling due tasks.

### What runs inside the same process
- WebApp and static asset serving.
- REST API for client requests, integrations, and reporting.
- Telegram client bot webhook handling.
- Telegram master bot webhook handling.
- Telegram integration bot webhook handling.
- MAX client bot webhook handling.
- MAX master bot webhook handling.
- Scheduler processing for delayed tasks such as feedback requests.

### What is not on the active production path
- `bots/**`, `services/**`, `shared/**`, `requirements.txt`, and the skipped Python tests are legacy/historical material.
- `legacy/index.js` is not the runtime entrypoint.
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` are documentation/scaffolding artifacts; routing is hard-coded in `src/server/index.js` and `public/webapp.js`.

## Repository map
### Production-critical directories/files
- `app.js`
- `package.json`, `package-lock.json`
- `.bothost/entrypoint.conf`
- `Dockerfile`
- `src/server/**`
- `src/infrastructure/**`
- `src/interfaces/client_bot/**`
- `src/interfaces/master_bot/**`
- `src/interfaces/integration_bot/**`
- `src/core/**`
- `src/integrations/**`
- `public/**`
- `data/.gitkeep`

### Legacy / historical tails
- `bots/client_bot/**`
- `services/client_bot_service/**`
- `shared/clients_registry.py`
- `tests/test_*.py`
- `requirements.txt`

### Documentation contour
- `readme/README.md` — current high-level operating guide.
- `readme/ARCHITECTURE.md` — route, bot, persistence, scheduler, and integration detail.
- `readme/DEPLOYMENT.md` — local run, BotHost deploy, smoke checks, and access notes.
- `readme/ENV_REFERENCE.md` — single current env reference aligned with the code.
- `readme/LEGACY_PYTHON.md` — retained context for the deprecated Python contour.
- `audit/*` — all audit artifacts, current and explicitly-scoped machine-readable summaries.

## Feature contour
### Bots
- **Client bot:** Telegram and MAX webhooks, `/start`, `/help`, quick request intake, feedback parsing, and Mini App entry.
- **Master bot:** Telegram and MAX webhooks, staff access model, request management, comments, clarification back to client, quality case commands, and reporting commands.
- **Integration bot:** Telegram-only webhook/operator bot for integration event inspection, retry, and ignore actions.

### WebApp
- Shared single-page WebApp served from `public/index.html` and `public/webapp.js`.
- Supports request submission for service, parts, consultation, warranty, and data change flows.
- Detects Telegram or MAX context and submits either `webapp` or `max_webapp` source metadata.
- Recommendation list UI exists, but MAX recommendation auth is intentionally incomplete.

### Integrations
- Manual import endpoint.
- Email ingestion endpoint.
- 1C placeholder sync endpoints for client, vehicle, visit, and recommendation events.
- Reporting endpoints that build summaries and snapshots from the JSON store.

## Route inventory
### Static and WebApp routes
- `GET /health`
- `GET /styles.css`
- `GET /webapp.js`
- `GET /logo.png`
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`

### Client API
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### Integration API
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/client`
- `POST /api/integrations/one-c/vehicle`
- `POST /api/integrations/one-c/visit`
- `POST /api/integrations/one-c/recommendation`
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

### Reporting API
- `GET /api/reports/summary`
- `GET /api/reports/requests`
- `GET /api/reports/feedback`
- `GET /api/reports/quality`
- `GET /api/reports/masters`
- `GET /api/reports/sources`
- `GET /api/reports/recommendations`
- `POST /api/reports/snapshots`
- `GET /api/reports/snapshots`
- `GET /api/reports/snapshots/:id`

### Bot webhooks
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`
- `POST /max/client_bot/webhook`
- `POST /max/master_bot/webhook`

## Local run
```bash
npm ci
npm start
```
The service listens on `PORT` if provided, otherwise on `3000` for local development.

## Testing
```bash
npm test
python -m unittest discover -s tests -p 'test_*.py'
```
The Python suite is currently historical-only and intentionally skipped, but it is retained as evidence of the legacy contour.

## Deploy / BotHost summary
- Set `PORT`, Telegram bot tokens, `MASTER_BOT_ADMIN_IDS`, `WEBAPP_URL`, and `DB_FILE_PATH`.
- Add MAX env only if MAX is enabled in the deploy contour.
- Ensure `DB_FILE_PATH` points to persistent storage.
- Register Telegram and MAX webhooks manually outside the app.
- After deploy, run the smoke checklist in `readme/DEPLOYMENT.md`.

## Current limitations that matter operationally
- JSON-file persistence is single-instance oriented.
- Scheduler runs in-process and is not safe for multi-instance active-active deployment.
- Manual/email/1C integration endpoints do not enforce auth in the current server router.
- MAX recommendation UX and MAX integration bot parity are incomplete.
- Legacy Python files still exist and can confuse maintainers if the documentation contour is ignored.
