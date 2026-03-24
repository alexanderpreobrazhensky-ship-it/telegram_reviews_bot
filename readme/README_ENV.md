# Environment Reference

## Required
- `WEBAPP_URL`
- `DB_SQLITE_PATH` (preferred)

## Telegram
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`
- `TELEGRAM_MASTERS_CHAT_ID`

## MAX
- `MAX_ENABLED`
- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`
- `MAX_WEBHOOK_BASE_URL`
- `MAX_DEEPLINK_BASE_URL`

## Internal/admin
- `INTERNAL_ADMIN_WHITELIST`
- `TELEGRAM_DEBUG_CHAT_ID`

## Scheduler
- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `REQUEST_FOLLOWUP_INTERVAL_DAYS`

## AI canonical env contract (Stage 1, DeepSeek-focused)
These are canonical and must be used as source of truth:
- `AI_ENABLED=true`
- `AI_BUSINESS_USAGE_ENABLED=false`
- `AI_PROVIDER=proxy`
- `AI_MODEL=deepseek-chat`
- `AI_PROXY_URL=`
- `AI_PROXY_TOKEN=`
- `AI_TIMEOUT_MS=8000`
- `AI_ALLOWED_PROVIDERS=proxy,deepseek`
- `AI_DIAGNOSTICS_ENABLED=true`

Additional compatibility env (non-canonical but supported):
- `AI_FALLBACK_PROVIDER=deepseek`
- `AI_FALLBACK_MODEL=deepseek-chat`
- `AI_DEEPSEEK_API_KEY=`
- `AI_DEEPSEEK_BASE_URL=https://api.deepseek.com/chat/completions`
- `AI_OPENAI_API_KEY=`
- `AI_GEMINI_API_KEY=`

## Legacy Railway compatibility (old -> new)
Priority order (hard): canonical `AI_*` -> shared legacy -> `CLIENT_*` legacy -> defaults.
If canonical env is configured for a key, corresponding legacy aliases are detected and ignored (they are no longer source of truth).

| Legacy env | Canonical/internal target | Notes |
|---|---|---|
| `AI_ENGINE` | `AI_PROVIDER` | shared legacy alias |
| `AI_TIMEOUT_SECONDS` | `AI_TIMEOUT_MS` | converted seconds -> milliseconds |
| `CLIENT_AI_TIMEOUT_SECONDS` | `AI_TIMEOUT_MS` | fallback alias after shared legacy |
| `DEEPSEEK_MODEL` | `AI_MODEL` | shared legacy alias |
| `CLIENT_DEEPSEEK_MODEL` | `AI_MODEL` | fallback alias |
| `DEEPSEEK_BASE_URL` | `AI_PROXY_URL` + `AI_DEEPSEEK_BASE_URL` | proxy-first compatibility + deepseek direct endpoint compatibility |
| `CLIENT_DEEPSEEK_BASE_URL` | `AI_PROXY_URL` + `AI_DEEPSEEK_BASE_URL` | fallback alias |
| `DEEPSEEK_API_KEY` | `AI_PROXY_TOKEN` + `AI_DEEPSEEK_API_KEY` | proxy token compatibility + deepseek direct compatibility |
| `CLIENT_DEEPSEEK_API_KEY` | `AI_PROXY_TOKEN` + `AI_DEEPSEEK_API_KEY` | fallback alias |
| `DEEPSEEK_ALLOW_REQUESTS_FALLBACK` | diagnostics-only legacy signal | detected as legacy, ignored for runtime resolution |
| `CLIENT_FORCE_FALLBACK` | deprecated legacy flag | detected as legacy, ignored for runtime resolution |
| `FORCT_FALLBACK` | deprecated legacy typo | detected as legacy typo, ignored for runtime resolution |
| `OPENAI_API_KEY` | `AI_OPENAI_API_KEY` | compatibility only |
| `GEMINI_API_KEY` | `AI_GEMINI_API_KEY` | compatibility placeholder only |

## Legacy aliases still accepted
- `DB_FILE_PATH`
- `INTERNAL_ADMIN_WHITELIST_IDS`
- `WEBAPP_TELEGRAM_CHANNEL_LINK`
- `AI_API_KEY` (mapped as legacy alias for `AI_OPENAI_API_KEY`)

## AI runtime visibility
- AI Status / diagnostics include three explicit lists:
  - `legacy env detected`
  - `legacy env ignored`
  - `legacy env used`
- Internal diagnostics include effective provider/model, resolution source, and ignored legacy keys.
