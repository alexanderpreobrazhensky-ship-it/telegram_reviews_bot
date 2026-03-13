# ENV Full Audit

| ENV | Status | Default | Where used | Purpose | Required prod | Required BotHost | Notes |
|---|---|---|---|---|---|---|---|
| PORT | required | 3000 | `app.js`, `src/infrastructure/config/index.js` | HTTP server port | yes | yes | |
| NODE_ENV | optional | development | `src/infrastructure/config/index.js` | runtime mode | no | no | |
| DB_FILE_PATH | required | `data/db.json` | `src/infrastructure/db/index.js` | JSON DB location (persistence) | yes | yes | Must point to persistent volume |
| TELEGRAM_CLIENT_BOT_TOKEN | required | - | `src/infrastructure/config/index.js`, `app.js`, master/client flows | outgoing client messages | yes | yes | |
| TELEGRAM_MASTER_BOT_TOKEN | required | - | `src/infrastructure/config/index.js` | master bot webhook/send | yes | yes | |
| TELEGRAM_INTEGRATION_BOT_TOKEN | recommended | - | `src/infrastructure/config/index.js` | integration bot | optional | optional | |
| MASTER_BOT_ADMIN_IDS | required | empty | `src/infrastructure/config/index.js` | env-managed admins | yes | yes | comma-separated list |
| TELEGRAM_MASTERS_CHAT_ID | recommended | empty | `src/infrastructure/config/index.js`, `src/server/index.js` | duplicate new requests to masters chat | recommended | recommended | |
| TELEGRAM_CHANNEL_URL | recommended | empty | `src/infrastructure/config/index.js`, injected to webapp | channel link on result screens | recommended | recommended | new canonical var |
| WEBAPP_TELEGRAM_CHANNEL_LINK | legacy/dead | empty | `src/infrastructure/config/index.js` | backward compatibility for channel URL | no | no | kept as fallback |
| WEBAPP_DEDUPE_WINDOW_MS | optional | 45000 | `src/infrastructure/config/index.js`, `src/server/index.js` | dedupe window | recommended | recommended | |
| FEEDBACK_REQUEST_DELAY_MINUTES | optional | 5 | `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js` | delayed feedback task scheduling | optional | optional | scheduler-related |
| SCHEDULER_INTERVAL_MS | optional | 15000 | `src/infrastructure/config/index.js` | scheduler poll interval | recommended | recommended | |
| SCHEDULER_BATCH_SIZE | optional | 10 | `src/infrastructure/config/index.js` | scheduler batch size | optional | optional | |
| SCHEDULER_MAX_ATTEMPTS | optional | 3 | `src/infrastructure/config/index.js` | task retry attempts | optional | optional | |
| SCHEDULER_STUCK_TIMEOUT_MS | optional | 300000 | `src/infrastructure/config/index.js` | stuck processing recovery | optional | optional | |
| INTEGRATION_RETRY_MAX | optional | 3 | `src/infrastructure/config/index.js` | integration retry policy | optional | optional | |
| INTEGRATION_RETRY_DELAY_SECONDS | optional | 60 | `src/infrastructure/config/index.js` | integration retry delay | optional | optional | |
| ONE_C_WEBHOOK_SECRET | recommended | empty | `src/infrastructure/config/index.js` | 1C security | recommended | recommended | |
| ONE_C_SYNC_ENABLED | optional | false | `src/infrastructure/config/index.js` | 1C toggles | optional | optional | |
| EMAIL_IMPORT_ENABLED | optional | true | `src/infrastructure/config/index.js` | email ingestion toggle | optional | optional | |
| ENABLE_INTEGRATION_WORKER | optional | true | `src/infrastructure/config/index.js` | integration worker toggle | optional | optional | |
| WEBAPP_URL | optional | https://example.com | `src/infrastructure/config/index.js` | external URL metadata | optional | optional | |
| DB_URL | legacy/dead | postgres://... | `src/infrastructure/config/index.js` | documented but not used in runtime storage | no | no | runtime uses `DB_FILE_PATH` |
| QUEUE_DRIVER | legacy/dead | memory | `src/infrastructure/config/index.js` | documented queue driver | no | no | no driver switching in runtime |

## Minimal ENV for production deploy
`PORT`, `DB_FILE_PATH`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`.

## Minimal ENV for BotHost
`PORT`, `DB_FILE_PATH`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `TELEGRAM_MASTERS_CHAT_ID` (if chat duplication required).

## New ENV in this task
- `TELEGRAM_CHANNEL_URL` (new preferred URL for WebApp result screens).
