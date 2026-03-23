# WebApp

## Canonical frontend files
- `public/index.html`
- `public/webapp.js`
- `public/styles.css`

## Important constraints
- Do not rely on `review.html` for runtime changes.
- Phone input/storage rule remains strict: exactly 10 digits without `+7/8`.
- Current backend compatibility assumes Node-first APIs under `/api/client/requests/*`.

## Channel identities
- Telegram source keeps `telegramId` when present.
- MAX source keeps `maxId` when present.
- These IDs are later reused for safe outbound clarification routing.
