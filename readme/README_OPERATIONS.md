# Operations

## Recommended smoke checks after deploy
1. `GET /health`
2. `GET /health/db`
3. `GET /health/max`
4. Telegram master bot: `/start` -> every menu button
5. MAX master bot: `/start` -> every menu button
6. Create one request and verify: take in progress, processed/substatus, in service, complete
7. Trigger legacy callback on an old card and verify friendly refresh UX
8. Trigger `/diagnostics` and `/logs` as admin
9. Verify one `waiting_decision` and one `consulted` task exist in scheduler persistence
10. Confirm archive contains `spam`, `rejected`, and `completed`

## Operator notes
- Archived requests are read-only from the bot UI.
- `error` indicates outbound clarification failure and should be investigated through logs.
- Diagnostics and logs are admin-only.
