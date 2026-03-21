# Deploy

## Core deploy contract
- Entrypoint: `app.js`
- BotHost main file: `.bothost/entrypoint.conf`
- Container command: `node app.js`
- Runtime image: Node 20 Alpine in `Dockerfile`

## Minimum Telegram-oriented env
```env
WEBAPP_URL=https://your-host
DB_SQLITE_PATH=/persistent/data/db.sqlite
TELEGRAM_CLIENT_BOT_TOKEN=...
TELEGRAM_MASTER_BOT_TOKEN=...
MASTER_BOT_ADMIN_IDS=123456789
```

## Additional MAX env
```env
MAX_ENABLED=true
MAX_CLIENT_BOT_TOKEN=...
MAX_MASTER_BOT_TOKEN=...
MAX_WEBHOOK_SECRET=...
MAX_MASTER_BOT_ADMIN_IDS=max-admin-id
MAX_BOT_NAME=your_max_bot
MAX_WEBAPP_URL=https://your-host
```

## Important deploy notes
- Telegram and MAX webhook registration is external to the app.
- Persistence durability depends on the mounted SQLite path.
- Do not split MAX into a separate BotHost project.
