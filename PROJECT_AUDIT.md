# PROJECT_AUDIT

## 1) Статус этапов
- Skeleton-этап: завершён.
- Этап 2 (client_bot + WebApp MVP): сохранён рабочим.
- Этап 3 (master_bot MVP): сохранён рабочим.
- Этап 4 (reminders + feedback + quality flow MVP): сохранён рабочим.
- Этап 5 (integration layer MVP + 1С-ready foundation): сохранён рабочим.
- Этап 6 (analytics + management reporting MVP): реализован.

## 2) Production contract (BotHost-safe)
- Runtime: Node.js.
- Entrypoint: `app.js`.
- Manifest: `package.json`.
- Ветка деплоя: `main`.
- Node-first запуск сохранён, Python как production path не используется.

## 3) Что добавлено в этапе 6

### 3.1 Analytics/reporting service layer
Добавлен application-сервис `src/core/application/reportingService.js`:
- `buildRequestsMetrics(...)`
- `buildFeedbackMetrics(...)`
- `buildQualityMetrics(...)`
- `buildMasterMetrics(...)`
- `buildSourceMetrics(...)`
- `buildRecommendationMetrics(...)`
- `buildManagementSummary(...)`
- `buildPeriodicSnapshot(...)`

Бизнес-логика аналитики вынесена из route/bot handlers в отдельный сервисный слой.

### 3.2 Реализованные KPI и метрики
- **Requests:** total, by type/status/source channel/source system, processed/lost/archived.
- **Conversion-like:** processed share, lost share, in_progress share.
- **Feedback/quality:** total feedback, average rating, low-rating count/share, quality case count, quality cases by status, resolved/unresolved.
- **Masters:** requests touched/processed/lost, quality assigned/resolved by master.
- **Sources:** `telegram_chat`, `webapp`, `email`, `manual_import`, `one_c`, `other`.
- **Recommendations:** total/actual/completed/declined/expired/critical.
- **Timing (MVP best-effort):** time-to-first-move-from-new, time-to-in_progress, time-to-processed, time-to-feedback-task-creation.

### 3.3 Периоды и фильтрация
Поддержаны периоды:
- `weekly`
- `monthly`
- `quarterly`
- `custom` (`from` + `to`)

Поддержаны фильтры:
- date range
- `masterId`
- `requestType`
- `sourceChannel`
- `sourceSystem`

### 3.4 Management summaries
Реализованы два формата:
1. structured JSON summary;
2. human-readable text summary (готов для manager bot delivery/future AI post-processing).

В summary включены:
- период;
- общее число обращений/обработано/потеряно;
- средняя оценка и негатив;
- quality open/resolved;
- top sources;
- мастер-метрики;
- data limitations block.

### 3.5 Reporting API
Добавлены endpoints:
- `GET /api/reports/summary?period=weekly|monthly|quarterly`
- `GET /api/reports/summary?from=...&to=...`
- `GET /api/reports/requests`
- `GET /api/reports/feedback`
- `GET /api/reports/quality`
- `GET /api/reports/masters`
- `GET /api/reports/sources`
- `GET /api/reports/recommendations`
- `POST /api/reports/snapshots`
- `GET /api/reports/snapshots`
- `GET /api/reports/snapshots/:id`

### 3.6 Snapshot/persistence
В store добавлена коллекция `reportSnapshots`.

Snapshot содержит:
- `id`
- `reportType`
- `periodType`
- `periodStart`
- `periodEnd`
- `generatedAt`
- `metrics`
- `summaryText`
- `generatedBy`
- `sourceDataVersion` (optional)
- `notes` (optional)

Реализовано:
- создание snapshot по запросу;
- сохранение в `data/db.json`;
- чтение list/by-id через API и service layer.

### 3.7 Manager-facing hooks
В `master_bot` добавлены manager/admin команды:
- `/report_week`
- `/report_month`
- `/report_quarter`
- `/report_stats`

Доступ:
- `manager`, `admin` — разрешён;
- `master` — ограничен (`REPORT_ACCESS_DENIED`).

### 3.8 Worker/scheduling preparation
Автоматический scheduler для periodic report snapshots не включён как production flow.
Реализован service-level skeleton через `buildPeriodicSnapshot(...)` и ручной trigger (`POST /api/reports/snapshots`).

## 4) Изменения в хранилище `data/db.json`
Добавлено:
- `reportSnapshots`

Существующие коллекции этапов 2–5 не ломались.

## 5) Regression статус этапов 2–5
Подтверждено тестами:
- `/health` жив;
- `client_bot` webhook жив;
- `master_bot` webhook жив;
- `integration_bot` webhook жив;
- текущие client/integration flow маршруты не сломаны.

## 6) Тестовое покрытие этапа 6
Добавлен `tests/node/analytics-reporting.test.js`:
- requests/feedback/quality/source/recommendation metrics;
- summary для weekly/monthly/custom;
- snapshot creation/persistence/retrieval;
- manager/admin access к report commands и запрет для master;
- regression по `/health` и telegram webhooks + report routes.

## 7) Что реально работает и что skeleton
### Реально работает
- analytics/reporting service layer;
- KPI-агрегирование по platform data;
- management summary JSON + text;
- reporting API;
- report snapshots storage/retrieval;
- manager/admin report hooks в master_bot.

### Skeleton / ограничения
- нет полноценного BI/DWH;
- нет продвинутой финансовой и 1С-обогащённой аналитики;
- timing/conversion считаются в MVP best-effort формате;
- периодическая автогенерация snapshot оставлена как foundation (manual trigger + service-level scaffold).
