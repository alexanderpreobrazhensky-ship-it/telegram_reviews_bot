# Deploy

## Базовый контракт деплоя
- Entrypoint: `node app.js`
- Runtime: единый Node.js процесс
- DB: SQLite-first (`DB_SQLITE_PATH`)
- Telegram/MAX/WebApp живут в одном runtime

## Минимальные env
```env
WEBAPP_URL=https://your-host
DB_SQLITE_PATH=/persistent/data/db.sqlite
TELEGRAM_MASTER_BOT_TOKEN=...
MASTER_BOT_ADMIN_IDS=123456789
```

## Расширенный env (production)
```env
TELEGRAM_CLIENT_BOT_TOKEN=...
TELEGRAM_INTEGRATION_BOT_TOKEN=...
MAX_ENABLED=true
MAX_CLIENT_BOT_TOKEN=...
MAX_MASTER_BOT_TOKEN=...
MAX_WEBHOOK_SECRET=...
MAX_MASTER_BOT_ADMIN_IDS=max-admin-id
MAX_WEBAPP_URL=https://your-host
INTERNAL_ADMIN_WHITELIST=123456789
EMAIL_INTAKE_ENABLED=false
AI_ENABLED=true
AI_BUSINESS_USAGE_ENABLED=false
AI_PROVIDER=proxy
AI_MODEL=deepseek-chat
AI_DIAGNOSTICS_ENABLED=true
```

## Post-deploy checklist
1. Проверить `/health`, `/health/db`, `/health/max`.
2. Проверить `/internal/diagnostics` (через whitelist admin).
3. Пройти master-бот меню и карточку заявки.
4. Проверить навигацию `Назад` / `В меню` в menu/input режимах.
5. Проверить архивные заявки (должны быть read-only).
6. Проверить AI status/diagnostics/switch/logs (admin).
7. Если email intake включён — проверить IMAP connection/folder и last poll.
8. Убедиться, что секреты в диагностиках маскируются.

## Anti-regression constraints
- Не менять production entrypoint (`app.js`).
- Не выносить MAX в отдельный runtime.
- Не ломать unified status model/master-bot flow.

## Проверка deploy-артефакта reference dataset
- На старте (`npm start`) автоматически выполняется `node scripts/verifyReferenceDataset.js` и пишет в лог:
  - `buildCommitHash`, `buildBranch`, `buildTimestamp`
  - `datasetResolvedPath`, `datasetDirectoryExists`, `datasetDirectoryListing`
  - `datasetFileExists`, `datasetFileReadable`, `datasetFileSizeBytes`
- В Docker build включена strict-проверка: `node scripts/verifyReferenceDataset.js --strict`.
  - Если `.sqlite` не попал в образ или недоступен, build завершится ошибкой.
- Для корректной трассировки деплоя передавайте build args:

```bash
docker build \
  --build-arg APP_BUILD_COMMIT=$(git rev-parse HEAD) \
  --build-arg APP_BUILD_BRANCH=$(git rev-parse --abbrev-ref HEAD) \
  --build-arg APP_BUILD_TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t telegram-reviews-bot:latest .
```
