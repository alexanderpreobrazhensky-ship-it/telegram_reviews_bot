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
   - `enabled`
   - `available`
   - `datasetPath`
   - `lastLookupStatus`
2. Создать WebApp заявку с known `phone+fio` из reference dataset:
   - в payload заявки есть `existing_client=true`, `client_match_basis=phone_fio`.
3. Создать заявку без совпадения:
   - `existing_client=false`.
4. Для конфликтного кейса (multiple matches):
   - `existing_client=false`, `needs_review=true`, `client_match_basis=conflict_multiple_matches`.
5. В карточке master-бота проверить видимость полей:
   - `Действующий клиент`
   - `Основание проверки`
   - `ID в reference-базе`
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
