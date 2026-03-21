# Telegram Audit

## Scope
Telegram client bot, master bot, integration bot, callbacks, permissions, notification flow, WebApp linkage, and source tracking.

## Current state
- Telegram client bot route: `/telegram/client_bot/webhook`.
- Telegram master bot route: `/telegram/master_bot/webhook`.
- Telegram integration bot route: `/telegram/integration_bot/webhook`.
- Telegram remains the only integration bot channel.

## Confirmed facts
### Client bot
- Supports `/start`, `/help`, quick intake, free-text flows, native contact intake, and feedback parsing.
- Requests created from Telegram chat are tagged with Telegram-specific source channels (`telegram_chat`, bot-origin communication events).
- Start menus include WebApp buttons built from `WEBAPP_URL`.

### Master bot
- Access is bootstrapped via `MASTER_BOT_ADMIN_IDS` and DB-backed staff roles.
- Role resolution supports `admin`, `manager`, and `master` via access flow.
- Status changes, comments, search, request cards, quality cases, and reporting commands are implemented.
- Internal admin pages also accept those admin IDs as part of the internal whitelist set.

### Integration bot
- Telegram-only operator bot supports `/start`, `/events`, `/failed`, `/pending`, `/stats`, `/event <id>`, `/retry <id>`, and `/ignore <id>`.

### Telegram ↔ WebApp link
- Client bot menus launch the WebApp.
- WebApp result screens can link to the configured Telegram channel URL.

## Risks
- Telegram outbound sends are skipped when tokens are absent; webhook handlers can still appear healthy.
- Client-bot chat sessions are in memory only.
- Masters-chat duplication is Telegram-only; there is no equal staff broadcast channel in MAX.

## Gaps
- No Telegram webhook registration automation.
- No cryptographic verification of Telegram WebApp identity within the current server.
- No dedicated operator auth layer beyond possession of the integration bot channel and token.

## Legacy / dead / misleading parts
- Historical Python Telegram bot code is not the active production bot implementation.

## Recommendations
1. Keep Telegram as the only integration-bot channel unless product requirements change.
2. Maintain `MASTER_BOT_ADMIN_IDS` as the bootstrap gate; use access-grant flows for downstream staff roles.
3. Add stronger startup visibility when Telegram tokens are missing in production.

## Confidence level
High.

## Follow-up checks
- Confirm live Telegram webhook registration and message delivery in production.
- Test masters-chat duplication with a real `TELEGRAM_MASTERS_CHAT_ID` after deploy.
