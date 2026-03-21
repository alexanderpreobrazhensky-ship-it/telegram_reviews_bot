# Local run, deployment, and operations

## 1. Local development
### Prerequisites
- Node.js 18+.
- npm.
- Optional Python only if you want to inspect the legacy contour.

### Minimal local run
```bash
npm ci
PORT=3000 \
WEBAPP_URL=http://localhost:3000 \
TELEGRAM_CLIENT_BOT_TOKEN=dummy-client \
TELEGRAM_MASTER_BOT_TOKEN=dummy-master \
MASTER_BOT_ADMIN_IDS=123 \
npm start
```

### Optional local env additions
- `DB_FILE_PATH=./data/db.json`
- `TELEGRAM_INTEGRATION_BOT_TOKEN=dummy-integration`
- `TELEGRAM_MASTERS_CHAT_ID=-1000000000000`
- MAX variables only if testing the MAX contour.

## 2. BotHost deploy checklist
### BotHost contract
- Branch in `.bothost/entrypoint.conf` is `main`.
- Main file in `.bothost/entrypoint.conf` is `app.js`.
- Runtime image in `Dockerfile` is Node 20 Alpine.
- Dependency install uses `npm ci --omit=dev`.

### Required BotHost env for Telegram-first production
- `PORT` (usually injected by platform)
- `DB_FILE_PATH`
- `WEBAPP_URL`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`

### Recommended Telegram env
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `TELEGRAM_MASTERS_CHAT_ID`
- `TELEGRAM_CHANNEL_URL`
- `NODE_ENV=production`
- scheduler tuning envs as needed

### Required extra env when MAX is enabled
- `MAX_ENABLED=true`
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBHOOK_SECRET`
- `MAX_BOT_NAME`
- optionally `MAX_WEBAPP_URL`

## 3. Webhook setup expectations
The application exposes webhook routes but does not self-register them. You must configure external providers manually.

### Telegram
Configure bot webhooks to:
- `/telegram/client_bot/webhook`
- `/telegram/master_bot/webhook`
- `/telegram/integration_bot/webhook`

### MAX
Configure bot webhooks to:
- `/max/client_bot/webhook`
- `/max/master_bot/webhook`

Also ensure the sender includes the `X-Max-Bot-Api-Secret` header value expected by `MAX_WEBHOOK_SECRET`.

## 4. Post-deploy smoke checklist
1. `GET /health` returns `200`.
2. `GET /`, `GET /styles.css`, and `GET /webapp.js` return successfully.
3. Submit one request through each WebApp form.
4. Verify the request appears in `GET /api/client/requests`.
5. Verify `/start` in Telegram client bot.
6. Verify `/start` in Telegram master bot and access control for an allowed account.
7. Verify `/start` in Telegram integration bot if the token is configured.
8. If MAX is enabled, verify `/start` in MAX client and master bots.
9. If `TELEGRAM_MASTERS_CHAT_ID` is set, confirm new request duplication appears in the Telegram masters chat.
10. Run `GET /api/reports/summary?period=weekly`.
11. Run `POST /api/reports/snapshots`.
12. Confirm `DB_FILE_PATH` writes persist after restart/redeploy.

## 5. Access and roles
### Telegram / MAX master access
- Bootstrap admins come from `MASTER_BOT_ADMIN_IDS` and `MAX_MASTER_BOT_ADMIN_IDS`.
- Staff access is persisted in the JSON DB.
- Unknown users are denied.

### Operational recommendation
Keep at least one known-good admin ID per active master channel so that role recovery remains possible after a DB issue or first deploy.

## 6. Known deployment blockers / warnings
- Multi-instance deployment against one JSON file is unsafe.
- Integration routes currently lack HTTP auth; deploy behind trusted ingress or add auth before exposing broadly.
- `MAX_ENABLED` is documentary/configurational; webhook routes are still mounted even if it is false.
- The integration bot has no MAX route.
- Recommendation API auth is Telegram-centric.
