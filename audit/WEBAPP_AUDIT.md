# WebApp Audit

## Scope
Routes, client logic, submit flows, validation, channel detection, identity path, phone input behavior, error handling, and client/server duplication.

## Current state
- The WebApp shell is served from `public/index.html` with behavior in `public/webapp.js`.
- Server-side runtime injection adds `WEBAPP_URL`, `MAX_WEBAPP_URL`, `MAX_BOT_NAME`, deep-link data, and the Telegram channel CTA URL without editing the HTML file on disk.
- Supported forms: service, parts, consultation, warranty, and data change.
- `review.html` and `public/index.html` remain untouched as required; runtime data is injected on response.

## Confirmed facts
- Web routes are hard-coded in `src/server/index.js`: `/`, `/requests`, `/recommendations`, and five `/forms/...` routes.
- Submit endpoints are `/api/client/requests/service|parts|consultation|warranty|data-change`.
- Client channel detection is query-param based first (`?channel=max`) and then environment-object based (`window.MAX` / `window.Telegram`).
- Telegram identity uses `Telegram.WebApp.initDataUnsafe.user.id`; MAX uses `MAX.WebApp.initDataUnsafe.user.id`; both are also cached in `localStorage`.
- Phone is normalized to exactly 10 digits client-side and server-side.
- Client-side validation shows field-level errors, but the server remains the final authority.

## Phone input audit
### Confirmed current behavior
- The input stores only digits; there is no decorative mask left in the final field value.
- `+7` / `8` prefixes are stripped to the last 10 digits when applicable.
- Paste, cut, delete, replacement, and typed edits are normalized through one controller.
- Request submission is blocked client-side for invalid phone length and rejected server-side if still invalid.

### Causes of earlier instability (confirmed by code/tests)
- Phone normalization had to be enforced both in form editing and on submit.
- Contact payloads from Telegram/MAX can arrive via alternate fields (`nativeContact`, `contact`, etc.), requiring shared normalization logic.

### Stability assessment
- Browser/JSDOM regression coverage is good.
- Telegram WebView behavior is partially confirmed by logic parity and tests.
- MAX WebView behavior is partially confirmed by tests and code, but still needs live-device validation because identity/outbound behavior depends on MAX runtime objects.

## Risks
- Identity binding trusts `initDataUnsafe`/runtime-provided user objects; there is no cryptographic verification step for WebApp identity.
- Logic is duplicated between `public/webapp.js` and server-side validation for required fields and phone rules.
- Recommendation UX depends on recommendation sync state; without 1C sync, the page can legitimately be empty.

## Gaps
- No live visual regression or browser screenshot automation was available in this audit run.
- No offline queue or retry logic exists for failed client submits.
- There is no dedicated server-side verification for WebApp launch signatures.

## Legacy / dead / misleading parts
- `src/interfaces/webapp/routes.js` is not the actual route definition.
- Any old documentation implying a separate webapp build system is outdated.

## Recommendations
1. Keep the current phone rule: store 10 digits only, without `+7/8`.
2. If identity trust requirements increase, add signed init-data verification for Telegram/MAX WebApps.
3. Consider extracting shared form schema/field definitions to reduce client/server drift.
4. Validate the current flow on real Telegram WebView and MAX WebView devices after each significant UI change.

## Confidence level
High for route and validation logic; medium for real-device MAX/Telegram WebView runtime nuances.

## Follow-up checks
- Manual live-device test for each form in Telegram and MAX WebViews.
- Confirm recommendation page behavior after real 1C recommendation sync.
