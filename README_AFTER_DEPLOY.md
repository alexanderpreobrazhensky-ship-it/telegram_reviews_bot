# LIRA client-bot: BotHost deploy checklist

## BotHost settings
- Branch: `main`
- Main file: `index.js` (Node bootstrap that starts Python `main.py`)

## Required environment variables
- `CLIENT_TELEGRAM_BOT_TOKEN` (or fallback: `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`)
- `BOT_PATH_SECRET`
- `WEBHOOK_URL` **or** `PUBLIC_BASE_URL` **or** `DOMAIN`
- `PORT`
- `CLIENT_WEBAPP_SESSION_SECRET`

## Optional aliases
- `CLIENT_MASTERS_CHAT_ID` ← `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`
- `CLIENT_MASTER_USER_IDS` ← `CLIENT_MASTER_IDS`
- `CLIENT_ADMIN_IDS`, `REPORT_CHAT_IDS`, `SUPERADMIN_ID`

## Runtime behavior
- Default mode is `webhook` (`CLIENT_BOT_MODE`)
- Webhook URL: `<base>/webhook/<BOT_PATH_SECRET>`
- Fallback to polling only when base URL cannot be formed.

## Post-deploy checks
1. `GET /health`
2. `GET /WEBAPP`
3. `GET /assets/webapp.bundle.js`
4. `GET /assets/webapp.bundle.css`

## BotFather reminder
Mini App URL in BotFather should point to BotHost domain, not Railway:
- Main App: `https://<bothost-domain>/WEBAPP`
- Menu Button: `https://<bothost-domain>/WEBAPP`

This only affects WebApp opening and does **not** affect BotHost runtime selection.


## Manual upload fallback
If BotHost/Git sync is unstable, use `MANUAL_UPLOAD_GUIDE.md` to upload full files manually.
