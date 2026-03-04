# LIRA client-bot (BotHost-safe, webhook-first)

## Project status: client-bot only
- This repository supports **only** the client bot service.
- Reviews bot functionality was removed and is not supported.
- Active entrypoints and runtime files:
  - `index.js` (Node bootstrap for BotHost)
  - `main.py` (Python entrypoint)
  - `services/client_bot_service/` (client-bot backend)

## CI
GitHub Actions runs on:
- `push` to `main`
- `pull_request` to `main`

Workflow commands:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
```

How to run the same checks locally:
```bash
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
```

## BotHost deploy
- **Branch:** `main`
- **Main file:** `index.js`
- `index.js` is a Node bootstrap that starts `python main.py` and forwards signals/stdout/stderr.

## Runtime mode
- Default mode: `webhook` (when `CLIENT_BOT_MODE` is not set).
- Webhook URL is built as: `<base>/webhook/<BOT_PATH_SECRET>`.
- Base URL priority:
  1. `WEBHOOK_URL`
  2. `PUBLIC_BASE_URL`
  3. `DOMAIN` (normalized to `https://<domain>`)
- If base URL cannot be formed, service logs a warning and falls back to polling.

## Required ENV
- `CLIENT_TELEGRAM_BOT_TOKEN`
- `BOT_PATH_SECRET`
- One of: `WEBHOOK_URL` or `PUBLIC_BASE_URL` or `DOMAIN`
- `CLIENT_WEBAPP_SESSION_SECRET`
- `PORT` (if provided by BotHost, keep as-is)

## Supported ENV aliases
- Token fallback chain: `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`
- Masters chat: `CLIENT_MASTERS_CHAT_ID` with aliases `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`
- Master ids: `CLIENT_MASTER_USER_IDS` with alias `CLIENT_MASTER_IDS`
- Legacy tolerated variables: `REPORT_CHAT_IDS`, `SUPERADMIN_ID`, `CLIENT_ADMIN_IDS`, `MASTER_USERNAMES`, `REMINDER_USERNAMES`

## HTTP endpoints
- `GET /health`
- `GET /WEBAPP` and `GET /WEBAPP/`
- `GET /assets/webapp.bundle.js`
- `GET /assets/webapp.bundle.css`
- `GET /app.js` (alias)
- `GET /app.css` (alias)
- `GET /WEBAPP/config.json`
- `POST /webhook/<BOT_PATH_SECRET>`

## BotFather
Set Mini App URL to your **BotHost domain**:
- `https://<bothost-domain>/WEBAPP`
