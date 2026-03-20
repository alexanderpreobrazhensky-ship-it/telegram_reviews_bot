# ENV Full Audit

## Scope
Этот файл перечисляет все ENV, которые реально читаются Node runtime-кодом после добавления MAX-канала.

| ENV | Status | Default | Where used | Purpose | Required prod | Required BotHost | Runtime scope | Notes |
|---|---|---|---|---|---|---|---|---|
| PORT | required | `3000` | `src/infrastructure/config/index.js`, `app.js` | HTTP server port | yes | yes | common | BotHost обычно задаёт автоматически |
| NODE_ENV | recommended | `development` | `src/infrastructure/config/index.js` | runtime mode / `/health` marker | no | no | common | |
| DB_FILE_PATH | required | `data/db.json` | `src/infrastructure/db/index.js` | JSON persistence path | yes | yes | common | должен указывать на persistent storage |
| TELEGRAM_CLIENT_BOT_TOKEN | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `app.js`, `src/interfaces/master_bot/index.js` | Telegram client bot inbound/outbound | yes | yes | telegram | |
| TELEGRAM_MASTER_BOT_TOKEN | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/server/index.js`, `src/interfaces/client_bot/index.js` | Telegram master bot and staff notifications | yes | yes | telegram | |
| TELEGRAM_INTEGRATION_BOT_TOKEN | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/integration_bot/index.js` | Telegram integration bot | recommended | recommended | telegram | integration bot остаётся только в Telegram |
| MASTER_BOT_ADMIN_IDS | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/core/application/masterService.js`, `src/infrastructure/db/index.js` | Telegram admin access list | yes | yes | telegram | comma-separated |
| MAX_MASTER_BOT_ADMIN_IDS | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/core/application/masterService.js`, `src/infrastructure/db/index.js` | MAX admin access list | yes if MAX enabled | yes if MAX enabled | max | comma-separated |
| MAX_ENABLED | recommended | `false` | `src/infrastructure/config/index.js` | feature flag / deploy documentation marker | recommended if MAX enabled | recommended if MAX enabled | max | код читает переменную, но route wiring не блокирует по ней вебхуки |
| MAX_CLIENT_BOT_TOKEN | required when MAX enabled | empty | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js`, `app.js` | MAX client bot inbound/outbound | yes if MAX enabled | yes if MAX enabled | max | нужен для чата, mini app callbacks и outbound foundation |
| MAX_MASTER_BOT_TOKEN | required when MAX enabled | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js` | MAX master bot inbound/outbound | yes if MAX enabled | yes if MAX enabled | max | |
| MAX_WEBHOOK_SECRET | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js` | verification of `X-Max-Bot-Api-Secret` | recommended | recommended | max | соответствует webhook security model MAX |
| MAX_WEBAPP_URL | recommended | falls back to `WEBAPP_URL` | `src/infrastructure/config/index.js`, `src/server/index.js` | dedicated MAX mini app URL if separate URL is needed | optional | optional | max | при пустом значении используется единый WebApp |
| MAX_BOT_NAME | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/shared/channelAdapters.js`, `src/infrastructure/messaging/index.js` | build MAX deep links / bot links | recommended if MAX enabled | recommended if MAX enabled | max | без него deep link foundation ограничивается fallback URL |
| MAX_DEEPLINK_BASE_URL | optional | empty | `src/infrastructure/config/index.js`, `src/server/index.js` | explicit base for MAX deep links metadata | optional | optional | max | пока используется как injected runtime metadata |
| WEBAPP_URL | required | `https://example.com` | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/shared/channelAdapters.js`, `src/server/index.js` | base URL of shared WebApp | yes | yes | common | основной URL для Telegram и fallback для MAX |
| TELEGRAM_MASTERS_CHAT_ID | recommended | empty | `src/infrastructure/config/index.js`, `src/server/index.js` | duplicate new requests to Telegram masters chat | optional | optional | telegram | не влияет на MAX master bot |
| TELEGRAM_CHANNEL_URL | recommended | empty | `src/infrastructure/config/index.js`, `src/server/index.js`, `public/webapp.js` | channel link on result screens | optional | optional | telegram/webapp | |
| WEBAPP_TELEGRAM_CHANNEL_LINK | legacy/dead | empty | `src/infrastructure/config/index.js` | backwards-compatible alias for channel URL | no | no | legacy | fallback only |
| WEBAPP_DEDUPE_WINDOW_MS | optional | `45000` | `src/infrastructure/config/index.js`, `src/server/index.js` | duplicate request protection window | recommended | recommended | common | |
| FEEDBACK_REQUEST_DELAY_MINUTES | optional | `5` | `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js`, `app.js` | feedback task delay | optional | optional | common | now works for Telegram and MAX outbound foundation |
| SCHEDULER_INTERVAL_MS | optional | `15000` | `src/infrastructure/config/index.js`, `app.js` | scheduler poll interval | recommended | recommended | common | |
| SCHEDULER_BATCH_SIZE | optional | `10` | `src/infrastructure/config/index.js`, `app.js` | scheduler batch size | optional | optional | common | |
| SCHEDULER_MAX_ATTEMPTS | optional | `3` | `src/infrastructure/config/index.js`, `app.js` | task retry max attempts | optional | optional | common | |
| SCHEDULER_STUCK_TIMEOUT_MS | optional | `300000` | `src/infrastructure/config/index.js`, `app.js` | stuck task recovery | optional | optional | common | |
| INTEGRATION_RETRY_MAX | optional | `3` | `src/infrastructure/config/index.js` | integration retry limit | optional | optional | common | |
| INTEGRATION_RETRY_DELAY_SECONDS | optional | `60` | `src/infrastructure/config/index.js` | integration retry delay | optional | optional | common | |
| ONE_C_WEBHOOK_SECRET | recommended | empty | `src/infrastructure/config/index.js` | 1C webhook verification | recommended | recommended | integrations | |
| ONE_C_SYNC_ENABLED | optional | `false` | `src/infrastructure/config/index.js` | 1C sync toggle | optional | optional | integrations | |
| EMAIL_IMPORT_ENABLED | optional | `true` | `src/infrastructure/config/index.js` | email ingest toggle | optional | optional | integrations | |
| ENABLE_INTEGRATION_WORKER | optional | `true` | `src/infrastructure/config/index.js` | integration worker toggle | optional | optional | integrations | |
| DB_URL | legacy/dead | `postgres://localhost:5432/telegram_reviews` | `src/infrastructure/config/index.js` | legacy documented DB url | no | no | legacy | runtime JSON storage не использует |
| QUEUE_DRIVER | legacy/dead | `memory` | `src/infrastructure/config/index.js` | legacy queue driver placeholder | no | no | legacy | реального переключения драйвера нет |

## Required / recommended / optional / legacy summary

### Required
- `PORT`
- `DB_FILE_PATH`
- `WEBAPP_URL`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`
- `MAX_CLIENT_BOT_TOKEN` *(если MAX включён в production)*
- `MAX_MASTER_BOT_TOKEN` *(если MAX включён в production)*

### Recommended
- `NODE_ENV`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `TELEGRAM_MASTERS_CHAT_ID`
- `TELEGRAM_CHANNEL_URL`
- `MAX_ENABLED`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBHOOK_SECRET`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`
- `ONE_C_WEBHOOK_SECRET`
- `WEBAPP_DEDUPE_WINDOW_MS`
- `SCHEDULER_INTERVAL_MS`

### Optional
- `MAX_DEEPLINK_BASE_URL`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `ENABLE_INTEGRATION_WORKER`

### Legacy / dead
- `WEBAPP_TELEGRAM_CHANNEL_LINK`
- `DB_URL`
- `QUEUE_DRIVER`

## MAX-specific ENV added in this task
- `MAX_ENABLED`
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`
- `MAX_DEEPLINK_BASE_URL`
- `MAX_MASTER_BOT_ADMIN_IDS`

## Minimal production sets

### Telegram-only runtime
`PORT`, `DB_FILE_PATH`, `WEBAPP_URL`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`.

### Telegram + MAX runtime
`PORT`, `DB_FILE_PATH`, `WEBAPP_URL`, `TELEGRAM_CLIENT_BOT_TOKEN`, `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `MAX_CLIENT_BOT_TOKEN`, `MAX_MASTER_BOT_TOKEN`, `MAX_MASTER_BOT_ADMIN_IDS`, `MAX_WEBHOOK_SECRET`, `MAX_BOT_NAME`.

## BotHost notes
- `DB_FILE_PATH` обязателен для persistent mounted storage.
- `MAX_WEBHOOK_SECRET` и `ONE_C_WEBHOOK_SECRET` должны храниться как secrets.
- Если используется единый WebApp, `MAX_WEBAPP_URL` можно не задавать: будет использован `WEBAPP_URL`.
