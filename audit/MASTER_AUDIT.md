# MASTER_AUDIT

`audit/MASTER_AUDIT.md` — единственный актуальный audit source of truth в репозитории.

## 1) Executive summary
- Node-first архитектура подтверждена: runtime строится вокруг `app.js` и `src/server/index.js`.
- Master-bot flow и status model подтверждены, включая архивную модель через `archived=true`.
- Диагностика расширена: runtime/db/channels/webapp/internal/email/workflow + отдельный AI блок.
- README-контур синхронизирован с кодом и текущей эксплуатационной моделью.
- AI проблема не скрывается: диагностика и runtime override отражаются отдельно и прозрачно.

## 2) Runtime reality
- Единый Node runtime обслуживает HTTP, webhooks, internal routes, scheduler.
- Health endpoints: `/health`, `/health/db`, `/health/max`.
- Scheduler persisted: follow-up задачи и retries живут в SQLite tasks.
- Internal routes присутствуют: `/internal/requests`, `/internal/export`, `/internal/diagnostics`, `/internal/logs`.

## 3) Bot reality
- Master bot main menu: Новые заявки, В работе, Архив, Поиск, Quality Cases, Инструкция, Диагностика, Логи, Доступы, AI (по ролям).
- Карточка заявки: Взять в работу, Запросить данные, Обработана, В сервисе, Завершить, Комментарий, Подробнее.
- Legacy callback compatibility работает через map/refresh.
- Telegram и MAX используют единый flow/status model.

## 4) WebApp reality
- Production webapp контур: `public/index.html`, `public/webapp.js`, `public/styles.css`.
- Формы доступны через `/forms/*` маршруты.
- Phone validation policy (10 digits) остаётся действующей.
- `review.html` не рассматривается как production runtime source.

## 5) Persistence reality
- SQLite — canonical persistence.
- request lifecycle fields покрывают assignment/substatus/archive/follow-up/error/rejection.
- `request_events` ведёт операционный trail.
- `tasks` хранит follow-up и retry сценарии.
- runtime info возвращает path/init/migration metadata.

## 6) Diagnostics reality
Общая диагностика покрывает:
- Runtime/health/status routes
- DB path/readiness/schema/migration hints
- Telegram/MAX readiness
- WebApp/internal routes visibility
- Email intake diagnostics (config, IMAP, folder, poll, dedupe/parse counters)
- Workflow visibility (waiting_decision/consulted follow-up)

UX поддерживает:
- краткий статус
- подробный статус
- обновить/прогнать проверку

## 7) AI diagnostics block (separate)
AI вынесен в отдельный блок, где отражаются:
- Config validation status
- Primary provider status
- Fallback status
- Runtime override present/valid
- Effective provider/model + resolution sources
- Final diagnostics verdict:
  - `CONFIG_INVALID`
  - `PRIMARY_PROVIDER_FAILED`
  - `FALLBACK_PROVIDER_FAILED`
  - `DIAGNOSTICS_OK`

## 8) Email intake block
Если email intake включён:
- IMAP enabled/config state
- connection/folder status
- last poll and result
- processed/duplicate/parse counters
- last processed email marker
- T-Business detection readiness/priority
- payload flags (`existing_client`, `needs_review`, `match_basis`, `match_confidence`)

## 9) Status/workflow block
Подтверждённая модель:
- statuses: `new`, `in_progress`, `processed`, `in_service`, `completed`, `error`
- substatuses: `recorded`, `consulted`, `spam`, `waiting_decision`, `rejected`
- archive rules: `spam`/`rejected`/`completed` -> archived
- waiting_decision requeue flow
- consulted reminder flow
- архивные заявки иммутабельны для статусных переходов в UI

## 10) Security observations
- Admin access bootstrap через env + persisted staff roles.
- Internal routes защищаются allowlist-подходом.
- Секреты маскируются в бот-диагностике и internal surfaces.
- Outbound клиентская коммуникация не использует email fallback.

## 11) Testing coverage
- Automated: `npm test` (master bot, status model, routing, persistence, AI infra, MAX/Telegram regressions и т.д.).
- Added focus: обновлённые инструкция и диагностика в master bot.
- Documentation consistency pass: README + audit сверены с runtime reality.

## 12) Known issues
- AI business usage может быть intentionally OFF при включённой AI infrastructure.
- Runtime override может присутствовать и быть invalid относительно provider/model rules.
- Internal endpoints опираются на allowlist, а не на полнофункциональный IAM.

## 13) Remaining risks
- Риск неверной интерпретации AI состояния при смешении config-invalid и provider-failed (смягчено отдельными статусами).
- Риск эксплуатационных проблем при неперсистентном/небезопасном пути SQLite.
- Риск IMAP деградации (folder/connection failures) при включённом email intake.

## 14) Recommended next checks
1. Регулярно прогонять `/diagnostics`, `/ai_diagnostics`, `/internal/diagnostics` после деплоя.
2. Ввести алерты на `CONFIG_INVALID` и provider failures отдельно.
3. Добавить периодическую сверку email-intake counters и duplicate spikes.
4. Зафиксировать runbook для needs_review/T-Business triage.
5. Усилить internal IAM, если проект выходит за текущий trusted perimeter.

---

## AI issue deep-dive (required explicit block)

### Что подтверждено
- AI diagnostics/runtime override/config resolution существуют и отображаются в admin командах.
- Доступны отдельные статусы config, primary provider, fallback provider и финальный verdict.
- Legacy env detection/ignored/used отражается в AI status/diagnostics.

### Что исправлено
- AI блок явно отделён от общей диагностики.
- Вынесены отдельные поля runtime override present/valid и effective provider/model.
- Документация приведена к модели «не смешивать config-invalid и provider-failed».

### Что не исправлено / остаётся открытым
- Нельзя гарантировать `DIAGNOSTICS_OK` без валидного окружения и доступности внешних AI провайдеров.
- При некорректных env/runtime override проблема остаётся эксплуатационной и должна лечиться конфигурацией.

### Как проверялось
- Кодовый аудит master-bot diagnostics + AI diagnostics/state resolution.
- Проверка связки config normalization -> runtime settings -> diagnostics reporting.
- Прогон автоматических тестов (`npm test`) с AI/infra сценариями.

### Текущий статус
- **partially confirmed**: архитектурно разделение и прозрачность статусов подтверждены; live provider health зависит от внешнего окружения и runtime config.

## 15) Reference Bridge Database (Client/Vehicle)

### Что сделано
- Файлы `lira_normalized_database.xlsx` и `lira_normalized_database.sqlite` перенесены из корня репозитория в `data/reference/client_vehicle_bridge/`.
- Добавлен формализованный schema-документ: `data/reference/client_vehicle_bridge/schema.md`.
- Добавлен профильный README: `readme/README_CLIENT_VEHICLE_BRIDGE.md`.
- README-контур репозитория синхронизирован с новым reference dataset и границами runtime.

### Где лежат теперь
- `data/reference/client_vehicle_bridge/lira_normalized_database.xlsx`
- `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`
- `data/reference/client_vehicle_bridge/schema.md`

### Что содержат
Подтверждённые сущности/листы:
- SQLite: `clients`, `vehicles`, `vehicle_owner_history`, `invalid_phones`, `schema_dictionary`, `summary_metrics`
- XLSX: `Summary`, `Schema`, `Clients`, `Vehicles`, `OwnerHistory`, `InvalidPhones`, `SourceMap`

### Назначение
- Временный data bridge для future Excel/1С import.
- Подготовка matching и enrichment контуров (client lookup + owner linkage + mileage hints).
- Справочный слой для дальнейшей интеграции с master bot / integration pipeline.

### Ограничения текущей версии
- Это snapshot/reference слой, а не live-sync.
- Нет runtime автоподключения в production flow (и это ожидаемое поведение).
- Возможны неразрешённые связи owner/vehicle и placeholder VIN (`no_vin_*`).
- Нужна отдельная import/update задача для регулярного обновления.

### Следующие шаги
1. Ввести batch metadata (дата выгрузки, источник, checksum) для каждой новой поставки.
2. Добавить автоматизированный import-пайплайн staging -> normalization -> upsert.
3. Ввести quality-метрики для ambiguous owner matches и invalid phones.
4. Зафиксировать runbook по reconciliation с 1С-справочниками.

### Confirmed
- Файлы убраны из корня и находятся в `data/reference/client_vehicle_bridge/`.
- SQLite/XLSX открываются, таблицы/листы читаются.
- Формализация canonical полей clients/vehicles и linkage rules зафиксирована в `schema.md`.
- README и audit обновлены с явной границей «reference dataset != runtime DB».

### Hypothesis only
- Текущей структуры достаточно для будущего production-grade 1С sync без дополнительных полей/индексов.
- Текущие owner match статусы полностью покрывают все edge-cases исторических владений.

### Требует runtime/use-case проверки
- Эффективность client lookup enrichment в реальном потоке master bot.
- Устойчивость matching-эвристик (`phone -> fio -> vin`) на новых batch-выгрузках.
- Согласованность mileage-индикаторов при инкрементальных обновлениях.

## 16) Known issue block — AI diagnostics/config resolution

Статус AI-проблемы сохраняется как **unresolved/partially resolved** в рамках этой задачи:
- Документационная прозрачность и диагностика подтверждены.
- Live корректность зависит от валидности окружения и внешней доступности провайдеров.
- Задача по переносу reference dataset не включает исправление AI runtime/config logic.

## 17) WebApp existing client deterministic lookup (phone primary)

### Что внедрено
- В backend submit flow WebApp/site (`/api/client/requests/*`) добавлен централизованный lookup в reference bridge SQLite.
- Источник данных: `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite` (read-only usage).
- Правило матчинга: exact-only `phone(10 digits)` как primary.
- Результат сохраняется в `request.payload`:
  - `existing_client`
  - `client_match_basis`
  - `matched_reference_client_id`
  - `matched_reference_source`
  - `matched_reference_snapshot`
  - `needs_review`

### Конфликтная логика
- `1 match`: `existing_client=true`, `client_match_basis=phone`, `needs_review=false`.
- `0 match`: `existing_client=false`, `client_match_basis=no_match`.
- `>1 matches`: `existing_client=false`, `needs_review=true`, `client_match_basis=multiple_phone_matches`.

### Отображение
- Master bot карточка и первичное уведомление содержат поля:
  - `Действующий клиент`
  - `Основание`
  - `ID в reference-базе`
  - `Источник reference`
  - `Требуется проверка`
- Internal request card (`/internal/requests/:id`) также показывает lookup-поля.

## 18) Runtime reference dataset access hardening (2026-03-25)

### Root cause
- Причина повторяющегося `reference_dataset_unavailable` после деплоя: lookup loader использовал default path от `process.cwd()`.
- В отдельных runtime/deploy окружениях рабочая директория отличалась от корня репозитория, поэтому loader искал `data/reference/...` не там, где лежал артефакт.

### Fix
- Default dataset path теперь вычисляется от расположения кода (`src/infrastructure -> ../../data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`), а не от `cwd`.
- Добавлен path resolution self-check с видимой диагностикой:
  - configured/path/exists/readable/type
  - loaderStatus/available
  - totalClientRows/phoneIndexBuilt
  - lastLookupResult/lastLookupTargetPhone/lastLookupMatchCount/lastError
- Если явно задан `REFERENCE_CLIENT_LOOKUP_SQLITE_PATH` или `REFERENCE_CLIENT_LOOKUP_DATASET_PATH`, используется strict path (без silent fallback), чтобы конфигурационные ошибки не маскировались.

### Business rule state
- Primary rule: `exact phone match => existing_client=true` (`client_match_basis=phone`).
- `no match => client_match_basis=no_match`.
- `multiple matches => client_match_basis=multiple_phone_matches`, `needs_review=true`.
- `reference_dataset_unavailable` остаётся только для реальной инфраструктурной недоступности dataset.

### Evidence
- Контрольный номер `9506275333` найден в reference SQLite и проходит runtime lookup (`existing_client=true`, `client_match_basis=phone`).
- Master-карточка/уведомление отображают `Действующий клиент`, `Основание`, `ID в reference-базе`, `Источник reference`, `Требуется проверка`.

### Status
- **fixed** для заявленной проблемы runtime dataset access + phone-primary matching.

### Диагностика
- `GET /internal/diagnostics` дополнен блоком `existingClientLookup`:
  - `enabled`, `available`, `datasetPath`, `lastLookupStatus`, `lastError`.

### Ограничения
- Email/VIN не участвуют в ключе WebApp lookup.
- Fuzzy/AI matching не используется.
- Reference bridge dataset остаётся отдельным lookup-слоем и не подменяет runtime DB.

## Management Reports / Руководительские отчёты

### Реализовано
- Admin-only кнопочный вход в master-боте: `Отчёты`.
- Разделы: `Сводка`, `Воронка`, `Источники`, `Отказы`, `Гарантия`, `Зависшие`, `Existing/New`, `T-Business`.
- Периоды кнопками: `Сегодня`, `7 дней`, `30 дней`, `Месяц`, `Квартал`, `Всё время`.
- Навигация: `Назад`, `В меню`, плюс `Обновить`, `Экспорт`, `Подробнее`.
- Экспорт CSV по текущему выбранному отчёту/периоду.
- API/internal защита: `/api/reports/*` и `/internal/reports` требуют admin whitelist.

### Ограничения
- Экспорт реализован как CSV preview в bot и полный CSV через API endpoint.
- AI summary пока не включён в обязательный runtime отчётов.

### Проверки
- Добавлены/обновлены node tests по admin-only доступу и кнопочному отчётному потоку.
- Подтверждена регрессия базовых webhook/health/report routes.

## 18) Update 2026-03-25 — WebApp intake / lookup / parity remediation

### Root cause: `reference_dataset_unavailable`
- Основная причина: runtime lookup layer фактически зависел от строгого `phone+fio` фильтра и не давал бизнес-матч при корректном phone-only кейсе.
- Дополнительно в диагностике не хватало явных признаков loader state (`configured`, `loaderStatus`, `lastLookupAttemptedAt`, `lastLookupResult`), из-за чего инцидент выглядел как «клиент не найден».

### Что исправлено
1. Lookup переведён на primary rule `exact normalized phone match`.
2. Добавлены явные исходы `no_match`, `multiple_phone_matches`, `reference_dataset_unavailable`.
3. Расширена диагностика reference dataset loader.
4. В WebApp flow добавлен operational trace: persisted/visible/telegram notified/max notified.
5. Для MAX parity добавлена доставка уведомлений о новых WebApp заявках в MAX master контур (`MAX_MASTER_BOT_ADMIN_IDS`).
6. Валидация `wasClientBefore` + VIN dependency внедрена на фронте и бэке.
7. Списки заявок читаются в порядке `created_at DESC`, чтобы новые заявки не прятались внизу старой очереди.

### Текущая матрица отображения в master card
- `existing_client=true` -> `Основание: phone`.
- `existing_client=false` + no match -> `Основание: no_match`.
- dataset unavailable -> `Основание: reference_dataset_unavailable`.
- multiple matches -> `Основание: multiple_phone_matches`, `Требуется проверка: Да`.

### Open items
- Для production MAX parity требуется валидная конфигурация `MAX_MASTER_BOT_TOKEN`, `MAX_WEBHOOK_SECRET`, `MAX_MASTER_BOT_ADMIN_IDS`.
- Если dataset путь не смонтирован в runtime, диагностика теперь это явно покажет, но операционно это должно чиниться окружением/деплоем.
