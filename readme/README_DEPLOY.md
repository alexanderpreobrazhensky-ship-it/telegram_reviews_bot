# Deploy

## Core deploy contract
- Entrypoint: `app.js`
- Runtime: Node.js
- Canonical HTTP server: `src/server/index.js`
- Keep MAX inside the same project/runtime.

## Required baseline env
```env
WEBAPP_URL=https://your-host
DB_SQLITE_PATH=/persistent/data/db.sqlite
TELEGRAM_MASTER_BOT_TOKEN=...
MASTER_BOT_ADMIN_IDS=123456789
```

## Optional production env
```env
TELEGRAM_CLIENT_BOT_TOKEN=...
TELEGRAM_INTEGRATION_BOT_TOKEN=...
TELEGRAM_MASTERS_CHAT_ID=...
MAX_ENABLED=true
MAX_CLIENT_BOT_TOKEN=...
MAX_MASTER_BOT_TOKEN=...
MAX_WEBHOOK_SECRET=...
MAX_MASTER_BOT_ADMIN_IDS=max-admin-id
MAX_WEBAPP_URL=https://your-host
AI_ENABLED=false
AI_PROVIDER=
AI_MODEL=
AI_API_KEY=
AI_TIMEOUT_MS=5000
```

## Post-deploy focus
- verify `/health`, `/health/db`, `/health/max`
- open master bot `/start` and press every inline menu button
- create one request and verify request-card actions
- verify scheduler follow-up tasks are created/persisted
- verify diagnostics/logs mask secrets
