# WebApp Audit

## Scope
Current WebApp routes, forms, submit logic, validation, identity handling, phone-input behavior, and UX/runtime caveats for Telegram and MAX.

## Current state
- The WebApp shell is `public/index.html`, but behavior is defined by `public/webapp.js` and runtime values injected by the server.
- The server serves the same HTML shell for `/`, `/requests`, `/recommendations`, and five form routes.
- Active forms are: service request, parts request, consultation request, warranty request, and data-change request.
- The phone field now stores digits-only raw values with a hard 10-digit cap in the visible input.

## Confirmed facts
### Confirmed by code
- Form routes map to API endpoints under `/api/client/requests/service|parts|consultation|warranty|data-change`.
- Client-side required-field validation is per request type and mirrors server-side field expectations.
- The phone input controller strips non-digits, limits input to 10 digits, normalizes pasted values, and blocks submit when invalid.
- Submit logic normalizes `payload.phone`, optionally replaces it with `nativeContactState.phoneNumber`, attaches channel identity, and posts JSON to the relevant request endpoint.
- Channel detection uses the `channel` query parameter first; if `channel=max`, the WebApp treats the source as MAX.
- Telegram identity is read from `window.Telegram.WebApp.initDataUnsafe.user.id` or cached localStorage fallback.
- MAX identity is read from `window.MAX.WebApp.initDataUnsafe.user.id` or cached localStorage fallback.
- Native contact acquisition prefers `MAX.WebApp.requestContact()` when available, otherwise `Telegram.WebApp.requestContact()` when available.
- Result screens include Telegram channel CTA buttons using the injected `TELEGRAM_CHANNEL_URL` / legacy alias.
- `/requests` requires a 10-digit phone input and fetches `GET /api/client/requests?phone=...`.
- `/recommendations` exists as a route in the shell, but effective data depends on server-side recommendation availability and Telegram-ID based lookup.

### Confirmed by tests
- JSDOM tests cover phone normalization, paste/edit behavior, invalid-submit blocking, and submission payloads for both Telegram and MAX-simulated webviews.

### Confirmed only partially / not cryptographically confirmed
- Telegram and MAX identity handling is code-confirmed, but the repository does not cryptographically verify WebApp identity or init data.
- Native-contact behavior is implemented, but real provider runtime behavior still depends on actual Telegram/MAX webview support.

### Hypothesis only
- Any claim that all device-specific WebView quirks are fully eliminated would be too strong without live runtime checks.

## What changed after modernization
- Phone input behavior is now explicitly digits-only and 10-digit constrained instead of relying on looser or mask-driven assumptions.
- WebApp payload preparation now consistently carries `sourceChannel`, `telegramId`, or `maxId` depending on context.
- Runtime config injection allows a single shell to serve Telegram and MAX contexts without editing `public/index.html`.
- Previous generic claims about WebApp instability are no longer accurate as blanket statements; the code and tests show concrete improvements.

## Remaining gaps
- There is no cryptographic verification of Telegram/MAX WebApp identity.
- Field definitions and validation rules still exist in both client and server code, so drift remains possible.
- No offline retry/queue UX exists for failed submits.
- Recommendation retrieval currently relies on Telegram ID, so MAX-specific recommendation parity remains limited in the server API surface.

## Risks
- Cached localStorage identity can preserve old user/channel identifiers inside a stale client session.
- Trust in `initDataUnsafe` and client-provided IDs creates spoofing risk for workflows that assume strong identity.
- UX still depends on provider support for `requestContact()` and mini-app launch behavior.
- Recommendations can appear empty in legitimate production scenarios when sync data is absent; this is a remaining runtime/data dependency, not proof of a frontend bug.

## Legacy / dead / misleading parts
- `src/interfaces/webapp/routes.js` and `src/interfaces/webapp/state.js` are not the runtime route or state source of truth for the shipped WebApp.
- Older audit claims that described the phone field as fundamentally broken should not be retained as current production facts.
- `review.html` is outside this audit rewrite scope and was intentionally not changed.

## Confidence level
High for code-confirmed WebApp behavior and phone handling; medium for real-device Telegram/MAX runtime behavior because no live device validation happened in this pass.

## Recommended follow-up checks
- Run live Telegram WebApp tests for all five forms, including native contact fill and result screen links.
- Run live MAX WebApp tests for launch, identity propagation, and contact access.
- Check whether stale-client-session behavior reproduces only on specific sessions/devices before treating it as a global production issue.
