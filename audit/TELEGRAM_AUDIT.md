# Telegram Audit

## Scope
Telegram client bot, master bot, integration bot, Telegram WebApp relationship, callback flows, access logic, supported commands, and Telegram-specific runtime limitations.

## Current state
- Telegram remains a first-class production channel inside the Node runtime.
- Three Telegram webhook routes exist: client bot, master bot, and integration bot.
- Telegram WebApp launch links are generated from `WEBAPP_URL` and used in client bot menus.
- Telegram remains the only implemented channel for the integration bot.

## Confirmed facts
### Confirmed by code
- Client bot webhook route: `/telegram/client_bot/webhook`.
- Master bot webhook route: `/telegram/master_bot/webhook`.
- Integration bot webhook route: `/telegram/integration_bot/webhook`.
- Client bot supports `/start`, `/help`, quick-request callbacks, free-text request starts, full-name collection, phone collection, native contact intake, and feedback parsing for `1`-`5` style replies.
- Telegram client bot uses inline/keyboards to open the WebApp and to collect contact data.
- Requests created from Telegram chat are stored with Telegram-oriented source channels such as `telegram_chat`.
- Master bot resolves actor access from `MASTER_BOT_ADMIN_IDS` plus DB-backed staff users, and supports request/status/comment/access/reporting workflows.
- Master bot callback buttons can assign requests, change status, request comments, and open request cards.
- Integration bot supports `/start`, `/events`, `/failed`, `/pending`, `/stats`, `/event <id>`, `/retry <id>`, and `/ignore <id>`.
- WebApp submissions can duplicate new requests into a Telegram masters chat when `TELEGRAM_MASTER_BOT_TOKEN` and `TELEGRAM_MASTERS_CHAT_ID` are configured.

### Confirmed by tests
- Telegram client, master, integration, reporting, feedback, and keyboard flows are covered by the Node test suite.

### Confirmed only partially / runtime-dependent
- Outbound Telegram delivery logic is implemented, but real delivery depends on valid tokens, webhook setup, and network reachability.
- Telegram WebApp identity values are read from Telegram runtime objects, but cryptographic verification is not implemented in this repo.

### Session-specific / non-global observations
- A mini-app issue observed in an old or cached user session would be a session-specific runtime observation unless reproduced broadly; the codebase alone does not justify describing it as a global Telegram production blocker.

## What changed after modernization
- Telegram flows are now explicitly part of the active Node-first runtime rather than a historical or parallel contour.
- Master-bot request management, comments, assignments, and reporting are implemented against the shared SQLite-backed core.
- Client-bot WebApp launching and 10-digit phone normalization are synchronized with the current WebApp/server logic.
- Integration-bot operations are now documented as Telegram-only, which removes ambiguity about channel support.

## Remaining gaps
- No automatic Telegram webhook registration exists in the repository.
- No app-level Telegram webhook secret validation is present.
- Bot sessions remain in memory and disappear on restart.
- The integration bot relies on possession of the Telegram bot/token rather than a richer operator auth model.

## Risks
- Missing Telegram tokens do not always fail startup, so some flows can appear alive while outbound responses silently fail or are skipped.
- WebApp identity and chat-origin identity still rely on provider payload trust rather than stronger verification.
- Master/admin access depends on correct env bootstrap and DB staff state.
- Telegram-specific client sessions can become stale after restarts because conversational session state is not persisted.

## Legacy / dead / misleading parts
- Historical Python Telegram bot code is not part of the active production runtime.
- Any repository narrative that frames Telegram as legacy-only is now misleading.
- Integration bot support should not be described as multi-channel; in current code it is Telegram-only.

## Confidence level
High for code-confirmed Telegram functionality; medium for live platform registration/delivery because no production webhook inspection was performed.

## Recommended follow-up checks
- Verify all three Telegram webhooks are registered in production.
- Smoke-test `/start`, a quick request, a master status change, and one integration-bot command with live credentials.
- Confirm masters-chat duplication works in the live environment when configured.
