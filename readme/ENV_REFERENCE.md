# Unified environment reference

This is the current env reference aligned with the checked-in code. Status labels:
- **required** — needed for the stated contour to work correctly.
- **recommended** — not always mandatory, but strongly advised.
- **optional** — supported with safe defaults.
- **legacy/dead** — still read or documented, but not materially active in the production design.

## Active Node runtime env
| ENV | Status | Default | Where read | Real runtime effect | BotHost relevance | MAX relevance | Telegram relevance |
|---|---|---:|---|---|---|---|---|
| `PORT` | required | `3000` | Node config loader | HTTP listen port | required | shared | shared |
| `NODE_ENV` | recommended | `development` | Node config loader | visible in `/health`, runtime labeling | recommended | shared | shared |
| `DB_FILE_PATH` | required | `data/db.json` | DB layer | selects persistent JSON DB file | required | shared | shared |
| `WEBAPP_URL` | required | `https://example.com` | config loader + server + client bot helpers | primary WebApp base URL | required | fallback | required |
| `TELEGRAM_CLIENT_BOT_TOKEN` | required for Telegram | empty | config/app/client bot/master service | Telegram client bot inbound/outbound | required in Telegram deploys | none | required |
| `TELEGRAM_MASTER_BOT_TOKEN` | required for Telegram | empty | config/server/master bot | Telegram master bot + masters chat fan-out | required in Telegram deploys | none | required |
| `TELEGRAM_INTEGRATION_BOT_TOKEN` | recommended | empty | config/integration bot | Telegram integration operator bot replies | recommended | none | recommended |
| `MASTER_BOT_ADMIN_IDS` | required for Telegram master access | empty | config/master service/DB resolution | bootstrap admin role list | required in Telegram deploys | none | required |
| `TELEGRAM_MASTERS_CHAT_ID` | recommended | empty | config/server | duplicate new requests into Telegram masters chat | recommended | none | recommended |
| `TELEGRAM_CHANNEL_URL` | recommended | empty | config/server/frontend runtime injection | channel CTA in WebApp result screen | recommended | none | recommended |
| `WEBAPP_TELEGRAM_CHANNEL_LINK` | legacy alias | empty | config loader only | fallback alias for `TELEGRAM_CHANNEL_URL` | low | none | low |
| `WEBAPP_DEDUPE_WINDOW_MS` | recommended | `45000` | config/server | best-effort duplicate-request suppression window | recommended | shared | shared |
| `FEEDBACK_REQUEST_DELAY_MINUTES` | optional | `5` | config + DB task scheduling | delay before feedback task due time | optional | shared | shared |
| `SCHEDULER_INTERVAL_MS` | recommended | `15000` | config/app | scheduler polling interval | recommended | shared | shared |
| `SCHEDULER_BATCH_SIZE` | optional | `10` | config/app | number of due tasks per polling iteration | optional | shared | shared |
| `SCHEDULER_MAX_ATTEMPTS` | optional | `3` | config/app | max task failure attempts before terminal failure | optional | shared | shared |
| `SCHEDULER_STUCK_TIMEOUT_MS` | optional | `300000` | config/app | timeout before a stuck task can be reclaimed | optional | shared | shared |
| `MAX_ENABLED` | recommended/documentary | `false` | config loader | marks intent; does not gate route registration | recommended when MAX exists | high | none |
| `MAX_CLIENT_BOT_TOKEN` | required when MAX enabled | empty | config/app/client bot/master service | MAX client bot inbound/outbound | required for MAX | required | none |
| `MAX_MASTER_BOT_TOKEN` | required when MAX enabled | empty | config/master bot | MAX master bot inbound/outbound | required for MAX | required | none |
| `MAX_MASTER_BOT_ADMIN_IDS` | required when MAX master enabled | empty | config/master service/DB resolution | bootstrap MAX admin list | required for MAX | required | none |
| `MAX_WEBHOOK_SECRET` | recommended/near-required | empty | config/client bot/master bot | validates `X-Max-Bot-Api-Secret` | recommended | required in practice | none |
| `MAX_WEBAPP_URL` | recommended | falls back to `WEBAPP_URL` | config/server/runtime injection | dedicated MAX mini app URL if needed | recommended | high | none |
| `MAX_BOT_NAME` | recommended | empty | config/channel adapter helpers | MAX deep links and launch URLs | recommended | high | none |
| `MAX_DEEPLINK_BASE_URL` | optional | empty | config/runtime injection | metadata for MAX launch/deep-link scenarios | optional | medium | none |
| `ONE_C_WEBHOOK_SECRET` | recommended | empty | config loader | currently documentary unless used by future auth middleware | recommended if 1C exposed | none | none |
| `ONE_C_SYNC_ENABLED` | optional | `false` | config loader | configuration placeholder only | optional | none | none |
| `EMAIL_IMPORT_ENABLED` | optional | `true` | config loader | configuration placeholder only | optional | none | none |
| `ENABLE_INTEGRATION_WORKER` | optional | `true` | config loader | placeholder; there is no separate worker process | optional | none | none |
| `INTEGRATION_RETRY_MAX` | optional | `3` | config loader | currently config-only; not actively driving a worker loop | optional | none | none |
| `INTEGRATION_RETRY_DELAY_SECONDS` | optional | `60` | config loader | currently config-only; not actively driving a worker loop | optional | none | none |
| `DB_URL` | legacy/dead | `postgres://localhost:5432/telegram_reviews` | config loader | no live DB connection uses it | none | none | none |
| `QUEUE_DRIVER` | legacy/dead | `memory` | config loader | no real queue driver switch exists | none | none | none |

## Legacy Python contour env
The repository still contains many Python-only env aliases under `bots/client_bot/**`, `services/client_bot_service/**`, and `shared/**`. Those variables are not part of the active Node production contract. They matter only if you intentionally revive the legacy Python contour.

The main legacy groups are:
- Token aliases such as `CLIENT_TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `BOT_TOKEN`, `TOKEN`.
- Webhook/base URL aliases such as `WEBHOOK_URL`, `PUBLIC_BASE_URL`, `DOMAIN`, `WEBAPP_PATH`.
- Python-specific storage or GitHub persistence env such as `CLIENTS_REGISTRY_PATH`, `CLIENT_GITHUB_TOKEN`, `CLIENT_GITHUB_REPO`.
- Feature toggles for the historical Python bot UI/UX.

## Minimal env sets
### Telegram-only deployment
```env
PORT=3000
DB_FILE_PATH=/persistent/data/db.json
WEBAPP_URL=https://example.bothost.ru
TELEGRAM_CLIENT_BOT_TOKEN=...
TELEGRAM_MASTER_BOT_TOKEN=...
MASTER_BOT_ADMIN_IDS=123456789
```

### Telegram + MAX deployment
```env
PORT=3000
DB_FILE_PATH=/persistent/data/db.json
WEBAPP_URL=https://example.bothost.ru
TELEGRAM_CLIENT_BOT_TOKEN=...
TELEGRAM_MASTER_BOT_TOKEN=...
MASTER_BOT_ADMIN_IDS=123456789
MAX_ENABLED=true
MAX_CLIENT_BOT_TOKEN=...
MAX_MASTER_BOT_TOKEN=...
MAX_MASTER_BOT_ADMIN_IDS=max-admin-1
MAX_WEBHOOK_SECRET=...
MAX_BOT_NAME=your_max_bot
```

## Practical env conclusions
- The only persistence env that truly matters today is `DB_FILE_PATH`.
- `DB_URL` and `QUEUE_DRIVER` are legacy signals and should not be presented as active production features.
- `MAX_ENABLED` is useful for deploy clarity but does not disable MAX routes by itself.
- `ONE_C_WEBHOOK_SECRET` should be treated as a future-facing security requirement because the HTTP routes are already present.
