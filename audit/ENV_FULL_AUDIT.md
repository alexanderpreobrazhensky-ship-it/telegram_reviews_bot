# Full environment audit

## Scope and method
This audit reconciles all currently relevant env reads across:
- active Node runtime
- legacy Python contour
- Dockerfile / BotHost entrypoint expectations
- tests and documentation

## 1. Active Node env classification
### Required in the base Node production contour
- `PORT`
- `DB_FILE_PATH`
- `WEBAPP_URL`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`

### Required when MAX contour is enabled
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_MASTER_BOT_ADMIN_IDS`

### Strongly recommended
- `NODE_ENV`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `TELEGRAM_MASTERS_CHAT_ID`
- `TELEGRAM_CHANNEL_URL`
- `WEBAPP_DEDUPE_WINDOW_MS`
- `SCHEDULER_INTERVAL_MS`
- `MAX_ENABLED`
- `MAX_WEBHOOK_SECRET`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`

### Optional / low-impact
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `MAX_DEEPLINK_BASE_URL`
- `ONE_C_WEBHOOK_SECRET`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `ENABLE_INTEGRATION_WORKER`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`

### Legacy / declarative / dead
- `WEBAPP_TELEGRAM_CHANNEL_LINK`
- `DB_URL`
- `QUEUE_DRIVER`

## 2. Per-variable audit
| ENV | Default | Read location(s) | Used for real runtime behavior? | Classification | Notes |
|---|---|---|---|---|---|
| `PORT` | `3000` | config loader, `app.js` logging | yes | required | BotHost usually injects it |
| `NODE_ENV` | `development` | config loader | yes | recommended | exposed by `/health` |
| `DB_FILE_PATH` | `data/db.json` | DB module | yes | required | critical BotHost persistence env |
| `WEBAPP_URL` | `https://example.com` | config, server, adapters | yes | required | base URL for shared WebApp |
| `TELEGRAM_CLIENT_BOT_TOKEN` | empty | config, app, client/master flows | yes | required | client bot messaging and webhook workflows |
| `TELEGRAM_MASTER_BOT_TOKEN` | empty | config, server, master flows | yes | required | master bot and masters-chat duplication |
| `TELEGRAM_INTEGRATION_BOT_TOKEN` | empty | config, integration bot | yes | recommended | Telegram integration operator bot |
| `MASTER_BOT_ADMIN_IDS` | empty | config, master service, DB resolution | yes | required | bootstrap Telegram admin access |
| `TELEGRAM_MASTERS_CHAT_ID` | empty | config, server | yes | recommended | duplicates new requests into Telegram staff chat |
| `TELEGRAM_CHANNEL_URL` | empty | config, server, frontend runtime data | yes | recommended | result-screen CTA target |
| `WEBAPP_TELEGRAM_CHANNEL_LINK` | empty | config only | indirectly | legacy alias | fallback alias for `TELEGRAM_CHANNEL_URL` |
| `WEBAPP_DEDUPE_WINDOW_MS` | `45000` | config, server | yes | recommended | dedupe window for web requests |
| `FEEDBACK_REQUEST_DELAY_MINUTES` | `5` | config, DB task scheduling | yes | optional | controls when feedback tasks become due |
| `SCHEDULER_INTERVAL_MS` | `15000` | config, app | yes | recommended | scheduler polling cadence |
| `SCHEDULER_BATCH_SIZE` | `10` | config, app | yes | optional | per-loop task claim count |
| `SCHEDULER_MAX_ATTEMPTS` | `3` | config, app | yes | optional | max task failure attempts |
| `SCHEDULER_STUCK_TIMEOUT_MS` | `300000` | config, app | yes | optional | stale task recovery window |
| `MAX_ENABLED` | `false` | config | weakly | recommended/documentary | does not disable route registration |
| `MAX_CLIENT_BOT_TOKEN` | empty | config, app, client/master flows | yes | required if MAX | MAX client chat + scheduler delivery |
| `MAX_MASTER_BOT_TOKEN` | empty | config, master bot | yes | required if MAX | MAX staff bot |
| `MAX_MASTER_BOT_ADMIN_IDS` | empty | config, master service, DB resolution | yes | required if MAX | bootstrap MAX admin access |
| `MAX_WEBHOOK_SECRET` | empty | config, MAX client/master webhook handlers | yes | recommended/near-required | primary MAX webhook protection |
| `MAX_WEBAPP_URL` | `WEBAPP_URL` fallback | config, server runtime injection | yes | recommended | dedicated MAX mini app URL |
| `MAX_BOT_NAME` | empty | config, channel adapters | yes | recommended | MAX deep-link URL generation |
| `MAX_DEEPLINK_BASE_URL` | empty | config, server runtime injection | weakly | optional | metadata only in current contour |
| `ONE_C_WEBHOOK_SECRET` | empty | config | not yet at route layer | recommended future-facing | should protect 1C routes once auth middleware exists |
| `ONE_C_SYNC_ENABLED` | `false` | config | no strong effect | optional/declarative | placeholder feature switch |
| `EMAIL_IMPORT_ENABLED` | `true` | config | no strong effect | optional/declarative | placeholder feature switch |
| `ENABLE_INTEGRATION_WORKER` | `true` | config | no strong effect | optional/declarative | no standalone worker exists |
| `INTEGRATION_RETRY_MAX` | `3` | config | not materially | optional/declarative | no worker consumes it directly |
| `INTEGRATION_RETRY_DELAY_SECONDS` | `60` | config | not materially | optional/declarative | same caveat as above |
| `DB_URL` | `postgres://localhost:5432/telegram_reviews` | config | no | legacy/dead | no live postgres driver path |
| `QUEUE_DRIVER` | `memory` | config | no | legacy/dead | no queue driver switch implemented |

## 3. Legacy Python env audit
The Python contour reads many env variables and aliases, including token aliases, webhook URL fallbacks, GitHub-backed persistence options, and UI/behavior toggles. They are **real reads in code** but **not relevant to the current production path**.

### Legacy Python env categories seen in code
- Bot token aliases.
- Webhook URL/base URL aliases.
- Legacy polling/webhook mode toggles.
- Route/WebApp path settings.
- Timezone and content toggles.
- GitHub storage sync variables.
- Local file path variables for registries and storage.

### Operational conclusion
These env reads must be treated as **legacy/dead for production documentation** unless the Python contour is explicitly restored.

## 4. BotHost env readiness
### Mandatory operational env checks
- `DB_FILE_PATH` points to persistent storage.
- All active bot tokens are present for enabled channels.
- At least one master admin ID exists for each active master bot channel.
- `WEBAPP_URL` resolves to the deployed HTTPS host.
- `MAX_WEBHOOK_SECRET` is configured if MAX routes are exposed.

### BotHost env risk conclusion
The env surface is manageable, but the presence of legacy/declarative variables can still mislead deploy operators if they rely on stale docs.

## 5. MAX env readiness
### Needed for practical MAX operation
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBHOOK_SECRET`
- `MAX_BOT_NAME`
- optional `MAX_WEBAPP_URL`

### Remaining limitation
Even with all env configured, MAX still needs live webhook registration and smoke validation because recommendation parity and integration-bot parity are incomplete.
