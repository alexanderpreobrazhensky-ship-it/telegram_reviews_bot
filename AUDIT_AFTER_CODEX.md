# AUDIT AFTER CODEX

## What was removed
- Legacy review artifact: `review.html`
- Non-canonical webapp source files: `bots/client_bot/webapp/webapp.js`, `bots/client_bot/webapp/webapp.css`

## What was added
- Node bootstrap entrypoint: `index.js` (runs `python main.py`)
- Root Python entrypoint: `main.py` (single-service client bot)
- Service entrypoint wrapper: `services/client_bot_service/app/main.py`
- Runtime config layer: `services/client_bot_service/app/config.py`
- BotHost hint: `.bothost/entrypoint.conf`
- CI workflow: `.github/workflows/tests.yml`
- Contract tests in `tests/`

## Webhook-first scheme
1. Resolve base URL by priority: `WEBHOOK_URL` → `PUBLIC_BASE_URL` → `DOMAIN`
2. Build path `/webhook/<BOT_PATH_SECRET>`
3. In webhook mode:
   - `deleteWebhook(drop_pending_updates=True)`
   - `setWebhook(url=...)`
   - start Flask on `CLIENT_SERVICE_HOST`:`PORT`
4. If base URL is missing/invalid: fallback to polling.

## Environment keys consumed
- Mode: `CLIENT_BOT_MODE`, `CLIENT_RUN_MODE`, `RUN_MODE`
- Token chain: `CLIENT_TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`
- Network: `CLIENT_SERVICE_HOST`, `PORT`, `CLIENT_SERVICE_PORT`
- Webhook base: `WEBHOOK_URL`, `PUBLIC_BASE_URL`, `DOMAIN`
- Secret: `BOT_PATH_SECRET`
- Master/admin aliases:
  - `CLIENT_MASTERS_CHAT_ID` ← `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`
  - `CLIENT_MASTER_USER_IDS` ← `CLIENT_MASTER_IDS`
  - optional: `CLIENT_ADMIN_IDS`, `REPORT_CHAT_IDS`, `SUPERADMIN_ID`

## Ignored env keys concept
At startup, config logs:
- `env_ignored_count=N`
- `ignored_env_keys=[...]`

Only names are logged, never values.

## Test suite
Run locally:
- `python -m unittest discover -s tests -p "test_*.py"`

Included tests:
- `test_bothost_entrypoint.py`
- `test_webhook_url_build.py`
- `test_webapp_static_routes.py`
- `test_health.py`
