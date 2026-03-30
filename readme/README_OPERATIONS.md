# Operations

## Recommended production checks
1. `GET /health`
2. `GET /health/db`
3. `GET /health/max`
4. `GET /internal/diagnostics` (authorized)
5. Telegram master bot: `/start`, пройти всё меню.
6. MAX master bot: `/start`, пройти всё меню.
7. Проверить навигацию `Назад` / `В меню` в menu/input режимах.
8. Создать заявку и пройти card actions.
9. Проверить архив (spam/rejected/completed).
10. Проверить follow-up visibility (`waiting_decision`, `consulted`).
11. Проверить `/logs` и `/internal/logs`.
12. Проверить AI status/diagnostics/switch/logs как admin.
13. Если email intake enabled: проверить IMAP состояние, folder, last poll, duplicates/parse counters.

## Master operator notes
- `error` обычно означает проблему outbound доставки клиенту.
- Archived заявки не должны менять статус.
- Для `needs_review` (email intake) требуется ручная валидация карточки и payload.

## AI control-plane operations
- `AI Статус` / `/ai_status`
- `AI Диагностика` / `/ai_diagnostics`
- `AI Переключение` / `/ai_switch ...`
- `AI Логи` / `/ai_logs ...`

## Policy
- Не заявлять «AI исправлен», если диагностика всё ещё показывает mismatch/failure.
- Отдельно трактовать `CONFIG_INVALID` и provider connectivity failures.
- Единый audit источник: `audit/MASTER_AUDIT.md`.

## Reference dataset operational checks
При ручных релизных проверках дополнительно убедиться, что:
1. Bridge dataset лежит в `data/reference/client_vehicle_bridge/`.
2. Файлы отсутствуют в корне репозитория.
3. Runtime конфиг (`DB_SQLITE_PATH`) не указывает на bridge SQLite.

## Existing client lookup checks (WebApp/site)
После релиза проверять дополнительно:
1. `GET /internal/diagnostics` содержит блок `existingClientLookup`:
   - `configured`, `datasetPath`, `datasetExists`, `datasetReadable`, `datasetType`
   - `loaderStatus`, `available`, `totalClientRows`, `phoneIndexBuilt`
   - `lastLookupResult`, `lastLookupTargetPhone`, `lastLookupMatchCount`, `lastError`
2. Создать WebApp заявку с known phone из reference dataset (например `9506275333`):
   - в payload заявки есть `existing_client=true`, `client_match_basis=phone`.
3. Создать заявку без совпадения:
   - `existing_client=false`, `client_match_basis=no_match`.
4. Для конфликтного кейса (multiple matches):
   - `existing_client=false`, `needs_review=true`, `client_match_basis=multiple_phone_matches`.
5. В карточке master-бота проверить видимость полей:
   - `Действующий клиент`
   - `Основание`
   - `ID в reference-базе`
   - `Источник reference`
   - `Требуется проверка`

## Management reports (admin-only)
- Основной вход: master-бот кнопкой `Отчёты` (только для `admin`).
- Разделы: `Сводка`, `Воронка`, `Источники`, `Отказы`, `Гарантия`, `Зависшие`, `Existing/New`, `T-Business`.
- Периоды кнопками: `Сегодня`, `7 дней`, `30 дней`, `Месяц`, `Квартал`, `Всё время`.
- В каждом отчёте доступны кнопки: `Обновить`, `Экспорт`, `Подробнее`, `Назад`, `В меню`.
- Экспорт: CSV по текущему типу отчёта/периоду (через кнопку в master-боте или `/api/reports/export` с admin auth).
- Internal/API доступ к отчётам должен использовать admin whitelist (`admin_id` / `x-admin-id`).

## Update 2026-03-25: WebApp request flow + Telegram/MAX parity
- После создания WebApp заявки проверяется operational цепочка:
  1) request received,
  2) request persisted,
  3) request visible in `new` list,
  4) telegram notification result,
  5) max notification result.
- Последняя диагностическая запись сохраняется в `meta` и доступна в `/internal/diagnostics` как `webappRequestFlow`.
- Existing client diagnostics расширена: `configured`, `available`, `datasetPath`, `source`, `loaderStatus`, `lastLookupAttemptedAt`, `lastLookupResult`, `lastError`.
- Для MAX parity уведомления о новых WebApp заявках отправляются также в MAX master channel (по `MAX_MASTER_BOT_ADMIN_IDS`) при включённом MAX.

## Update 2026-03-25: Reference Dataset / Client Lookup Diagnostics (master-бот)
Добавлен отдельный operational блок диагностики `Reference Dataset / Client Lookup Diagnostics`.

### Что показывает «Статус базы»
- dataset configured/path resolved/exists/readable;
- dataset type (`sqlite`/`xlsx`/`runtime cache`);
- dataset loader status (`not_started`/`loaded`/`failed`);
- total rows, phone index built, lookup enabled;
- effective business rule: `phone exact match active`;
- last lookup status/result/error/target/match_count.

### Статусы (разделены по причинам)
- `DATASET_NOT_CONFIGURED`
- `DATASET_PATH_UNRESOLVED`
- `DATASET_FILE_MISSING`
- `DATASET_UNREADABLE`
- `DATASET_LOAD_FAILED`
- `LOOKUP_DISABLED`
- `LOOKUP_OK_NO_MATCH`
- `LOOKUP_OK_EXACT_MATCH`
- `LOOKUP_OK_MULTIPLE_MATCHES`
- `LOOKUP_FAILED`
- `REFERENCE_DATASET_UNAVAILABLE`

### Master-бот flow
Меню `Диагностика -> База клиентов`:
- `Статус базы`
- `Проверить lookup (9506275333)`
- `Проверить номер` (ручной ввод, с `Назад`/`В меню`)

Ключевое: диагностика использует тот же runtime lookup path, что и WebApp request creation/existing client detection.

## Update 2026-03-27: Reference lookup runtime checks (prod-ready)
Root cause деградации `reference_dataset_unavailable` в инцидентном сценарии: runtime получал невалидный dataset path из env/deploy-конфига (missing/unreadable SQLite), и lookup не мог стартовать.

Что проверять после deploy:
1. Runtime path:
   - если env override задан, используется только он (strict);
   - если env override не задан, используется `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite` (в контейнере обычно `/app/data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`).
2. `GET /internal/diagnostics`:
   - `datasetPath`, `datasetExists`, `datasetReadable`, `datasetType=sqlite`,
   - `datasetOpenOk`, `loaderStatus=loaded`, `phoneIndexBuilt=true`, `available=true`.
3. Probe номер `9506275333` через master-бот (`Диагностика -> База клиентов -> Проверить lookup (9506275333)`):
   - `result=exact_match`, `matchBasis=phone`, `matchCount=1`.
4. Создать WebApp заявку с `9506275333`:
   - в карточке master-бота: `Действующий клиент: Да`, `Основание: phone`, `Требуется проверка: Нет`.

Safety mode:
- При `REFERENCE_LOOKUP_REQUIRED=true` и недоступном dataset `/health` возвращает `status=degraded`, а diagnostics содержит `criticalDegradation=true`.

## Update 2026-03-27: Master diagnostics «База клиентов» (expanded)
Новый блок `Диагностика -> База клиентов` в master-боте включает:
1. `Статус базы` — полный runtime статус dataset (configured/path/exists/readable/type/loader/rows/index/lookup/error).
2. `Проверить lookup (9506275333)` и `Проверить lookup (9200201890)` — отдельные runtime-пробы тем же lookup path, что WebApp request creation flow.
3. `Проверить номер` — ручной ввод телефона с нормализацией и детальным результатом (raw/normalized/match count/matched ids/result/error).
4. `Логи базы` — операторский срез path resolution + file checks + loader/index status + last lookup + runtime cwd/main module + candidate paths.

## Update 2026-03-30: Deploy mismatch fix for reference SQLite (variant A)
Root cause деградации в контейнере: в части deploy-сценариев runtime слой `/app/data` оказывался пустым/перекрытым, из-за чего файл `lira_normalized_database.sqlite` отсутствовал по ожидаемому пути `/app/data/reference/client_vehicle_bridge/...` и lookup переходил в `DATASET_FILE_MISSING`.

Что изменено в deploy chain:
1. В Docker-образ добавлена immutable seed-копия SQLite вне runtime data-каталога: `/opt/reference-assets/client_vehicle_bridge/lira_normalized_database.sqlite`.
2. На старте приложения выполняется self-check/repair:
   - проверка expected runtime path;
   - если файла нет/нечитаем — копирование из seed path в `/app/data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`;
   - повторная фиксация `exists/readable/size`.
3. После этого запускается штатный loader `createReferenceClientLookup` с тем же runtime path.

Operational expected result после deploy:
- `dataset configured: yes`
- `dataset path resolved: yes`
- `runtime dataset exists: yes`
- `dataset readable: yes`
- `dataset open: ok`
- `phone index built: yes`
- `lookup enabled: yes`
