# Runtime

## Startup chain
1. `app.js` загружает конфиг.
2. Инициализируется SQLite (`src/infrastructure/db/index.js`) и применяются schema/migration шаги.
3. `createServer()` регистрирует HTTP routes + bot webhooks + internal routes.
4. Поднимается AI infrastructure/control plane.
5. Запускается scheduler loop.

## Runtime model
- Один Node.js процесс.
- `http.createServer` (без Express).
- Общий event-loop для webhooks, WebApp API, internal pages, scheduler.
- Persisted task model через SQLite `tasks`.

## Health/runtime checks
- `/health`
- `/health/db`
- `/health/max`
- `/internal/diagnostics`
- `/internal/logs`

## Scheduler reality
Scheduler обслуживает persisted задачи, включая:
- `waiting_decision_followup`
- `consulted_followup`
- `feedback_request`

Переходы follow-up не зависят от in-memory таймеров и переживают рестарт процесса.

## AI runtime model
- Конфиг AI нормализуется в `src/infrastructure/config/index.js`.
- Runtime overrides хранятся в DB meta (`active_ai_provider`, `active_ai_model`, fallback keys).
- Эффективная конфигурация вычисляется через `resolveAiConfig`.
- Диагностика AI имеет отдельные статусы (config / primary / fallback / final verdict).
- Business usage может быть отключен независимо от диагностики и runtime switch.

## WebApp/runtime links
WebApp формы доступны по:
- `/forms/service-request`
- `/forms/parts-request`
- `/forms/consultation`
- `/forms/warranty-request`
- `/forms/data-change-request`

## Runtime boundary for reference datasets
`data/reference/client_vehicle_bridge/*` используется только как справочный/offline bridge dataset.
Runtime не должен автоматически подключать этот SQLite как рабочую БД и не должен менять `DB_SQLITE_PATH` на bridge-файл.
