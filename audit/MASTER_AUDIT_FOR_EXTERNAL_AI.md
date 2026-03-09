# MASTER AUDIT FOR EXTERNAL AI

## 1. Executive summary
- Production contract enforced as Python-only.
- Node trigger removed from root: `index.js` moved to `legacy/index.js`.
- BotHost contract fixed: branch `main`, Dockerfile-first, `main.py`, webhook-first.

## 2. Production contract
- branch: `main`
- runtime: `python`
- deploy path: `dockerfile-first`
- entrypoint: `main.py`
- default mode: `webhook`
- runtime chain: `main.py` -> `services/client_bot_service/app/main.py` -> `bots/client_bot/main.py`

## 3. BotHost safety status
- Root repository has no Node entrypoint markers (`index.js`, `app.js`, `server.js`, `main.js`, `package.json`).
- `.bothost/entrypoint.conf` contains `main_file=main.py` and `branch=main`.
- Dockerfile runs `CMD ["python", "main.py"]`.

## 4. Webhook-first contract
- Base URL priority: `WEBHOOK_URL` -> `PUBLIC_BASE_URL` -> `DOMAIN`.
- URL normalization: trim, double-scheme cleanup, forced https, invalid => missing.
- `BOT_PATH_SECRET` is required in webhook mode (fail fast).
- Polling fallback is used only when webhook base URL cannot be resolved.
- Startup logs include mode, token source, base URL source, port, storage mode (no secrets).

## 5. Route and feature integrity
Confirmed existing runtime paths remain available:
- `/health`
- `/service-health`
- `/WEBAPP`
- `/WEBAPP/config.json`
- `/assets/webapp.bundle.js`
- `/assets/webapp.bundle.css`
- `/app.js`
- `/app.css`

## 6. Validation
- `python -m unittest discover -s tests -p "test_*.py"`
- Contract tests include root Node marker absence and Dockerfile/main.py runtime checks.
