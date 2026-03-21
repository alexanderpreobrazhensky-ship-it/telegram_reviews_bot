# Post-fix verification report

## Scope
- MAX webhook hardening for `/max/client_bot/webhook` and `/max/master_bot/webhook`.
- WebApp phone input normalization and submission safety.
- JSON persistence transparency around `DB_FILE_PATH`.
- Regression check that `review.html` and `index.html` were not changed.

## Code audit findings
1. `MAX_WEBHOOK_SECRET` is now enforced centrally in `src/interfaces/shared/maxSecurity.js`.
2. Both MAX webhook routes use the same guard before handler logic runs.
3. `MAX_ENABLED` now meaningfully gates MAX runtime and returns a clear `MAX_DISABLED` response when disabled.
4. Client-bot quick flow no longer creates a request until the phone is normalized to exactly 10 digits.
5. HTTP request creation still normalizes and validates phones on the server side before persistence.
6. JSON DB path resolution now follows `DB_FILE_PATH` dynamically, logs initialization, and logs read/write failures.
7. `public/index.html` and `bots/client_bot/webapp/index.html` were intentionally left unchanged by this fix set.

## Automated verification summary
- Node unit and route tests cover phone normalization, WebApp masking flows, MAX secret enforcement, DB path behavior, invalid payload handling, and request persistence.
- MAX route tests now cover valid secret, invalid secret, missing configured secret, invalid payload, and disabled runtime scenarios.
- DB behavior tests cover env-driven path selection, missing-store initialization, and malformed JSON fallback behavior.

## Manual QA checklist executed in local simulated environment
- Desktop browser simulation via JSDOM for digit-by-digit typing.
- Backspace and delete in the middle of a masked number.
- Full paste with `+7`, `8`, spaces, hyphens, and brackets.
- Selection replacement and cut/re-paste flows.
- Payload verification that backend-bound phone values are stored as 10 digits.

## Remaining manual checks requiring live runtime
- Real Telegram WebView smoke on device.
- Real MAX WebView smoke on device.
- BotHost redeploy persistence verification against the actual mounted persistent path.
