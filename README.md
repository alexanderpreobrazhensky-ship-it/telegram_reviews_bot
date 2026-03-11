# Единая платформа автосервиса (Node.js / BotHost)

## Этап 6: analytics + management reporting MVP
Реализован MVP-слой аналитики и управленческой отчётности поверх этапов 2–5, без нарушения BotHost-safe production contract и существующих контуров (`client_bot`, `master_bot`, `integration_bot`, WebApp, `/health`, feedback/quality, integration API).

## BotHost production contract
- Runtime: Node.js
- Entrypoint: `app.js`
- Manifest: `package.json`
- Ветка деплоя: `main`
- Python не используется как production startup path.

## Запуск
```bash
npm install
npm start
```

## Analytics/reporting MVP
Добавлен application/service layer `src/core/application/reportingService.js` с методами:
- `buildRequestsMetrics(...)`
- `buildFeedbackMetrics(...)`
- `buildQualityMetrics(...)`
- `buildMasterMetrics(...)`
- `buildSourceMetrics(...)`
- `buildRecommendationMetrics(...)`
- `buildManagementSummary(...)`
- `buildPeriodicSnapshot(...)`

### Какие метрики считаются
- **Requests:** total, by type/status/source channel/source system, processed/lost/archived.
- **Conversion-like:** доля processed/lost/in_progress.
- **Feedback/Quality:** total feedback, average rating, low-rating count/share, quality cases by status, resolved/unresolved.
- **Masters:** touched/processed/lost, quality assigned/resolved by master.
- **Sources:** `telegram_chat`, `webapp`, `email`, `manual_import`, `one_c`, `other`.
- **Recommendations:** total/actual/completed/declined/expired/critical.
- **Timing (best-effort MVP):** от создания заявки до первого движения из `new`, до `in_progress`, до `processed`, до создания feedback task.

## Периоды и фильтры
Поддержаны периоды:
- `weekly`
- `monthly`
- `quarterly`
- `custom` (`from` + `to`)

Фильтры:
- date range
- `masterId`
- `requestType`
- `sourceChannel`
- `sourceSystem`

## Reporting API
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

## Management summaries
`buildManagementSummary(...)` возвращает:
1. structured JSON summary;
2. human-readable text summary (готово для manager-facing delivery/future AI post-processing).

## Manager-facing hooks (master_bot)
Добавлены команды:
- `/report_week`
- `/report_month`
- `/report_quarter`
- `/report_stats`

Доступ: только `manager` и `admin`; `master` получает `REPORT_ACCESS_DENIED`.

## Snapshot storage
В файловой БД (`data/db.json`) добавлена коллекция:
- `reportSnapshots`

Snapshot-поля:
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

## Ограничения MVP
- Нет полноценного BI/дашборда.
- Нет production-grade DWH.
- 1С-обогащение метрик пока ограничено (summary честно отмечает отсутствие полноценных one_c событий).
- Воронка визитов считается best-effort по доступным платформенным данным.

## Тесты
```bash
npm test
```
