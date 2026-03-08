# MASTER AUDIT FOR EXTERNAL AI

## 1. Executive summary
- `work -> main` synchronized: production-ready state is now anchored in `main`.
- Single production contract is fixed: **Python runtime**, **Dockerfile-first deploy**, **entrypoint `main.py`**, **default mode webhook**.
- `index.js` and `.bothost/entrypoint.conf` are retained only for compatibility hints and are not the primary production path.

## 2. Repository snapshot
- branch: `main`
- snapshot_commit: `175d2e0`
- manifest: `audit/REPO_MANIFEST.txt`

## 3. Entrypoints and startup chain
- Production entrypoint: `main.py`
- Startup chain: `main.py` -> `services/client_bot_service/app/main.py` -> `bots/client_bot/main.py`
- Compatibility-only entrypoints:
  - `index.js` (node wrapper that just spawns `python main.py`)
  - `.bothost/entrypoint.conf` (platform hint)

## 4. Runtime model
- Primary runtime: Python.
- Primary deploy path: Dockerfile-first.
- Default run mode: webhook-first.
- Fallback behavior: when webhook base URL is unavailable/invalid, service logs warning and falls back to polling.

## 5. Full ENV audit
### Required for webhook-first launch
- Token: `CLIENT_TELEGRAM_BOT_TOKEN` (aliases: `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`)
- `BOT_PATH_SECRET`
- Base URL source: `WEBHOOK_URL` or `PUBLIC_BASE_URL` or `DOMAIN`

### Required for forced polling
- Token from the chain above
- `CLIENT_BOT_MODE=polling` (or mode alias)

### Optional
- `PORT` (alias: `CLIENT_SERVICE_PORT`)
- `TIMEZONE`
- `CLIENT_WEBAPP_SESSION_SECRET`
- master chat/user id aliases (`CLIENT_MASTERS_CHAT_ID`, `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`, `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTER_IDS`)
- storage/db aliases (`DATABASE_URL`, `POSTGRES_URL`, `POSTGRESQL_URL`, `CLIENTS_REGISTRY_PATH`, `CLIENT_DATA_DIR`)

### Legacy/documented-only aliases retained
- Mode: `CLIENT_RUN_MODE`, `RUN_MODE`
- WebApp URL/path: `CLIENT_WEBAPP_URL`, `WEBAPP_URL`, `WEBAPP_PATH`
- WebApp toggle: `CLIENT_WEBAPP_ENABLED`, `WEBAPP_ENABLED`

## 6. Route inventory
- Health:
  - `GET /health`
  - `GET /service-health`
- WebApp static:
  - `GET /WEBAPP`, `GET /WEBAPP/`
  - `GET /WEBAPP/config.json`
  - `GET /assets/webapp.bundle.js`
  - `GET /assets/webapp.bundle.css`
  - `GET /app.js`
  - `GET /app.css`
- WebApp API:
  - `POST /api/webapp/session`
  - `POST /api/webapp/submit`
  - `GET /api/webapp/lookup`

## 7. Deploy/dependency audit
- Dockerfile exists in repo root and runs `CMD ["python", "main.py"]`.
- Dependencies are Python-first (`requirements.txt`).
- CI workflow executes unit tests from `tests/` via unittest discover.
- `.bothost/entrypoint.conf` points to `main.py` as a compatibility hint.
- Docs (`README.md`, `bots/client_bot/README.md`) are aligned with production contract on `main`.

## 8. Risk analysis (remaining)
1. Broad env-alias surface still increases config complexity.
2. Webhook-to-polling fallback can hide base URL misconfiguration in production.
3. Compatibility entrypoints (`index.js`, `.bothost/entrypoint.conf`) may mislead operators if docs are ignored.

## 9. What is likely blocking stable deployment
- Missing/invalid `BOT_PATH_SECRET` in webhook mode.
- Invalid or absent `WEBHOOK_URL|PUBLIC_BASE_URL|DOMAIN` for webhook registration.
- Token misconfiguration across alias chain.

## 10. Minimal required env for first successful launch
### Webhook-first (recommended)
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET`
- `WEBHOOK_URL` (or `PUBLIC_BASE_URL` or `DOMAIN`)

### Polling (compatibility path)
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `CLIENT_BOT_MODE=polling`

## 11. Local validation checklist
1. `python -m unittest discover -s tests -p "test_*.py"`
2. Verify Docker runtime contract: `docker build .` (optional local check)
3. Run service and verify:
   - `/health`
   - `/WEBAPP`

## 12. Post-deploy validation checklist
1. `GET /health` returns success.
2. `GET /WEBAPP` returns HTML.
3. Telegram `getWebhookInfo` returns configured webhook URL.
4. Logs show startup marker from root `main.py` and selected mode.

## 13. Source references
- `Dockerfile`
- `main.py`
- `services/client_bot_service/app/main.py`
- `services/client_bot_service/app/config.py`
- `bots/client_bot/main.py`
- `tests/test_entrypoints.py`
- `tests/test_runtime_behavior.py`
- `tests/test_health.py`
- `tests/test_static_routes.py`
- `tests/test_webhook_url_build.py`
- `README.md`
- `bots/client_bot/README.md`
- `.bothost/entrypoint.conf`
- `.github/workflows/tests.yml`
