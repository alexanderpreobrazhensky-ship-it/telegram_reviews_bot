# Persistence

## Canonical store
SQLite via `src/infrastructure/db/index.js`.

## Request fields in active lifecycle
- `status`
- `substatus`
- `assigned_to`
- `assigned_by`
- `assigned_at`
- `archived`
- `last_followup_at`
- `completed_at`
- `last_outbound_error`
- `rejection_comment`

## Request events
`request_events` is the operational audit trail and stores:
- request id
- event type
- actor type/id/role
- old/new values
- comment
- `meta_json`
- creation time

## Scheduler persistence
Follow-up reminders and retries are persisted in `tasks`.
This includes:
- `waiting_decision_followup`
- `consulted_followup`
- `feedback_request`
