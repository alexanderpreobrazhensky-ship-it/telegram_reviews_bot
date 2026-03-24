# Persistence

## Canonical storage
SQLite (`src/infrastructure/db/index.js`) — основной и обязательный persistence layer.

## Runtime metadata
DB runtime info включает:
- текущий путь к БД
- факт существования файла
- init status
- migration meta

## Request lifecycle data
Ключевые поля:
- `status`
- `substatus`
- `archived`
- `assigned_to` / `assigned_by` / `assigned_at`
- `last_followup_at`
- `completed_at`
- `last_outbound_error`
- `rejection_comment`

## Operational trail
`request_events` — основной trail:
- status/substatus transitions
- assignment
- comments
- follow-up events
- outbound failures
- meta_json context

## Scheduler persistence
`tasks` хранит follow-up и retry задачи:
- `waiting_decision_followup`
- `consulted_followup`
- `feedback_request`

Это обеспечивает корректную работу после рестарта runtime.

## Email intake persistence
Через integration events + meta сохраняются:
- last IMAP uid
- intake diagnostics state
- dedupe/parse counters
- payload flags (`existing_client`, `needs_review`, `match_confidence`, `source_provider`)

## Reference dataset (not runtime persistence)
Справочный bridge dataset хранится отдельно:
- `data/reference/client_vehicle_bridge/lira_normalized_database.xlsx`
- `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`

Важно: этот SQLite не участвует в runtime migration/state и не заменяет canonical persistence для заявок/событий/задач.
