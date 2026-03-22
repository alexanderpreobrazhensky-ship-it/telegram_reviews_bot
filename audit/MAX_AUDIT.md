# MAX Audit

## Scope
MAX webhook routes, env usage, secret protection, identity assumptions, callback/message handling, mini-app linkage, and current readiness level.

## Current state
- MAX support is embedded in the same Node runtime as Telegram; there is no separate MAX project.
- Two MAX webhook routes exist: client bot and master bot.
- MAX readiness is materially better than a placeholder, but still more runtime-dependent and less proven than Telegram.

## Confirmed facts
### Confirmed
- MAX client webhook route: `/max/client_bot/webhook`.
- MAX master webhook route: `/max/master_bot/webhook`.
- Both MAX routes call `validateMaxWebhookRequest()` before business logic is processed.
- MAX validation requires: `MAX_ENABLED=true`, presence of the relevant MAX bot token, presence of `MAX_WEBHOOK_SECRET`, exact `X-Max-Bot-Api-Secret` match, and object-shaped payload.
- Secret-bearing headers are sanitized before logging.
- MAX client and master flows reuse the same core request/master services used by Telegram where possible.
- MAX outbound messaging and callback answering are implemented against `https://platform-api.max.ru`.
- MAX mini-app URLs are built from `MAX_WEBAPP_URL` or `WEBAPP_URL`, with optional `MAX_BOT_NAME` and deep-link payload handling.
- WebApp runtime can detect a MAX context and submit requests with `sourceChannel = max_webapp` plus `maxId`.

### Partially confirmed
- MAX identity is taken from webhook payloads and from `MAX.WebApp.initDataUnsafe`, which is code-confirmed but not cryptographically validated by this repo.
- MAX contact-request support is implemented in the WebApp, but real provider behavior still needs live runtime confirmation.
- MAX master access bootstrap through `MAX_MASTER_BOT_ADMIN_IDS` is implemented, but live correctness depends on actual configured IDs.

### Not confirmed
- Live MAX webhook registration state in the external MAX platform.
- Real delivery success with production MAX tokens.
- Device-specific MAX WebView behavior outside the automated tests.

### Hypothesis only
- It would be too strong to claim full production parity with Telegram based on repository evidence alone.

## What changed after modernization
- MAX is now documented as an embedded, code-backed contour of the Node production runtime rather than a hypothetical add-on.
- Secret validation and route rejection semantics are explicit in code.
- MAX mini-app launch handling is integrated with the shared WebApp shell.
- Earlier blanket statements that MAX is only skeletal are now outdated; the code supports meaningful request and master workflows, though runtime proof remains partial.

## Remaining gaps
- No cryptographic verification of MAX WebApp identity beyond trusted runtime objects.
- No MAX integration bot exists.
- No separate MAX-specific operator broadcast equivalent to Telegram masters-chat duplication is present.
- No live runtime evidence was collected for production MAX webhook registration or outbound delivery.

## Risks
- Misconfiguration of `MAX_ENABLED`, tokens, or webhook secret causes routes to exist but reject traffic.
- Identity spoofing risk remains if downstream logic over-trusts webhook/user payloads or `initDataUnsafe`.
- MAX readiness can be overstated if code-confirmed behavior is confused with live platform confirmation.
- Operational confusion remains possible if MAX env is partially filled and the health endpoint appears superficially okay.

## Legacy / dead / misleading parts
- `MAX_ENABLED` is an acceptance gate, not a route-registration switch.
- MAX should not be described as a separate deployment topology for this project.
- Any stale doc claiming MAX has no meaningful implementation is no longer accurate.

## Confidence level
Medium-high for code-confirmed behavior; medium for real production readiness because live MAX runtime validation was not part of this pass.

## Recommended follow-up checks
- Verify live MAX webhook registration and secret/header behavior.
- Test `/max/client_bot/webhook` and `/max/master_bot/webhook` with real credentials.
- Run live MAX mini-app smoke tests for launch, submit, and callback flows.
