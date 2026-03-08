# LIRA client-bot (BotHost, Dockerfile-first, Python-only)

## Production contract
- Runtime: **Python only**.
- Deploy path: **Use custom Dockerfile** on BotHost.
- Entrypoint: `python main.py`.
- Default mode: `webhook`.
- Polling is used only as fallback when base webhook URL cannot be built.

## BotHost setup
1. Repository branch: `main`.
2. Enable **Use custom Dockerfile**.
3. Build and run from root `Dockerfile`.
4. If BotHost requires “Main file”, set `main.py` (compatibility hint only; real runtime is Dockerfile).
5. Do not use Node entrypoint as primary production path.

`.bothost/entrypoint.conf` is kept only for compatibility and points to `main.py`, but production should run via Dockerfile.

## Runtime flow
`main.py` → `services/client_bot_service/app/main.py` → `bots/client_bot/main.py`.

Startup logs include:
- mode
- token source (name only)
- base URL source (name only)
- port
- storage mode
- env used/ignored counters

Secrets are never logged.

## ENV

### Required
- `CLIENT_TELEGRAM_BOT_TOKEN` (or token alias from fallback chain).
- `BOT_PATH_SECRET` (required for webhook mode).
- One base URL source:
  - `WEBHOOK_URL`, or
  - `PUBLIC_BASE_URL`, or
  - `DOMAIN`

### Recommended
- `CLIENT_WEBAPP_SESSION_SECRET`
- `PORT` (set by platform)
- `TIMEZONE`
- `CLIENT_MASTERS_CHAT_ID` (or alias)

### Optional / legacy aliases (supported for compatibility)
- Token aliases: `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`
- Mode aliases: `CLIENT_RUN_MODE`, `RUN_MODE`
- Port alias: `CLIENT_SERVICE_PORT`
- Base URL aliases: `PUBLIC_BASE_URL`, `DOMAIN`
- WebApp URL/path aliases: `CLIENT_WEBAPP_URL`, `WEBAPP_URL`, `WEBAPP_PATH`
- WebApp toggle aliases: `CLIENT_WEBAPP_ENABLED`, `WEBAPP_ENABLED`
- Masters chat aliases: `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`
- Master ids aliases: `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTER_IDS`
- Notify mode: `CLIENT_NOTIFY_MODE`
- Storage/db aliases: `DATABASE_URL`, `POSTGRES_URL`, `POSTGRESQL_URL`, `CLIENTS_REGISTRY_PATH`, `CLIENT_DATA_DIR`

## Webhook-first behavior
Base URL priority:
1. `WEBHOOK_URL`
2. `PUBLIC_BASE_URL`
3. `DOMAIN`

Normalization:
- trims spaces
- removes trailing slash
- fixes malformed prefixes (`https://https://...`, `https://http://...`)
- forces `https://`
- treats invalid URL as missing

Webhook URL format:
- `<base>/webhook/<BOT_PATH_SECRET>`

Webhook startup sequence:
1. `deleteWebhook(drop_pending_updates=True)`
2. `setWebhook(url=...)`
3. Flask server on `0.0.0.0:$PORT`

Fallback:
- if mode is `webhook` but base URL is missing/invalid, bot logs warning and switches to polling after `deleteWebhook(drop_pending_updates=True)`.

## HTTP checks
- `GET /health`
- `GET /service-health`
- `GET /WEBAPP`, `GET /WEBAPP/`
- `GET /assets/webapp.bundle.js`
- `GET /assets/webapp.bundle.css`
- `GET /app.js`, `GET /app.css`
- `GET /WEBAPP/config.json`

WebApp API:
- `POST /api/webapp/session`
- `POST /api/webapp/submit`
- `GET /api/webapp/lookup`

Expected API errors include:
- `phone_required`
- `invalid_init_data`
- `session_expired`

## BotFather note
BotFather WebApp URL affects only the client-side WebApp open link.
It does not define runtime mode or deployment contract.

## Verify webhook after deploy
1. Check service health:
   - `curl -fsS https://<your-domain>/health`
2. Check Telegram webhook info:
   - `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`

## Tests / CI
Commands used in CI:
```bash
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
```


## Repository cleanliness
- Runtime data files are not versioned (`data/*.jsonl`, `data/system.json`, queue snapshots).
- Keep only `data/.gitkeep` in Git; actual bot data is generated at runtime in `/app/data`.
