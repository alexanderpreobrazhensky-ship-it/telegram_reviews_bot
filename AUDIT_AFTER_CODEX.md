# AUDIT_AFTER_CODEX

## 1) Scope summary
Выполнен production-safe рефактор и фиксы по `client_bot` с сохранением legacy-совместимости, а также проверка связки с `reviews_bot` через общий модуль картотеки клиентов.

---

## 2) Key directory tree (focused)
- `bots/client_bot/main.py` — основная runtime-логика client bot, WebApp API, маршрутизация, тикеты, мастера.
- `shared/clients_registry.py` — единый JSONL-реестр клиентов (lock + atomic write).
- `services/client_bot_service/app/main.py` — entrypoint сервиса client bot.
- `services/reviews_bot_service/app/main.py` — entrypoint сервиса reviews bot.
- `clients.jsonl` — общий реестр клиентов в корне репо.
- `data/tickets.jsonl` — журнал тикетов.
- `data/system.json` — system settings (в т.ч. pin related state).
- `tests/` — smoke/unit покрытие ключевых сценариев.
- `.github/workflows/tests.yml` — CI запуск unit tests.

---

## 3) Entrypoints and launch commands
### 3.1 Client bot service
- Root launch:
  - `python -m services.client_bot_service.app.main`
- Service-folder launch:
  - `cd services/client_bot_service`
  - `python -m app.main`

### 3.2 Reviews bot service
- Root launch:
  - `python -m services.reviews_bot_service.app.main`
- Service-folder launch:
  - `cd services/reviews_bot_service`
  - `python -m app.main`

---

## 4) ENV table (effective)

### 4.1 Shared / registry
- `CLIENTS_REGISTRY_PATH` (optional, default `./clients.jsonl`): путь единого реестра клиентов.
- `CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS` (optional, default `5`): timeout lock-файла `clients.lock`.

### 4.2 Client bot core
- `CLIENT_TELEGRAM_BOT_TOKEN` (**required**) — токен клиентского бота.
- `CLIENT_BOT_MODE` (default `polling`).
- `CLIENT_SERVICE_HOST` (default `0.0.0.0`).
- `CLIENT_SERVICE_PORT` (default `8010`).
- `CLIENT_ACTIVE_TICKET_TTL_HOURS` (default `12`) — TTL переиспользования активного тикета.
- `CLIENT_NOTIFY_MODE` (default `dm_then_chat`) — режим доставки мастерам.
- `CLIENT_MASTER_USER_IDS` (optional) — список мастеров (dm).
- `CLIENT_MASTERS_CHAT_ID` (optional) — мастер-чат.

### 4.3 WebApp-related
- `CLIENT_WEBAPP_ENABLED` / `WEBAPP_ENABLED` (default enabled).
- `CLIENT_WEBAPP_URL` / `WEBAPP_URL` — публичный URL WebApp (санитизируется).
- `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS` (default `86400`) — TTL для session endpoint.
- `CLIENT_WEBAPP_SESSION_SECRET` (optional) — secret подписи session_token.

### 4.4 Reviews bot service
- `REVIEWS_TELEGRAM_BOT_TOKEN` (**required**).
- `REVIEWS_BOT_MODE` (default `polling`).
- `REVIEWS_SERVICE_HOST` (default `0.0.0.0`).
- `REVIEWS_SERVICE_PORT` (default `8020`).

---

## 5) Ticket lifecycle / state machine
Поддерживаемые статусы:
- `new`
- `in_progress`
- `waiting_data`
- `processed`
- `archived`
- `postponed` (+ `postponed_until`)

Канонизация legacy-статусов:
- `in_work` -> `in_progress`
- `closed/done` -> `processed`

Реактивация postponed:
- scheduler (каждые 60 сек) проверяет `postponed_until`;
- при `now >= postponed_until` -> `status=new`, `postponed_until=None`, повторная отправка мастерам.

---

## 6) Master workflow
Доступные команды в мастер-чате:
- `/tickets` и `/new` — активные (`new`, `waiting_data`, `in_progress`)
- `/waiting` — только `waiting_data`
- `/inprogress` — только `in_progress`
- `/queue` — активная очередь
- `/ticket <ID>` — карточка

Карточка содержит статус, клиента, контакты, авто-поля, сообщения и inline-кнопки:
- «В работу» -> `in_progress`
- «Запросить данные» -> `waiting_data`
- «Обработана» -> `processed`
- «В архив» -> `archived`
- «Написать клиенту»

---

## 7) Notify mode matrix + 400/403 behavior
`CLIENT_NOTIFY_MODE`:
- `dm_then_chat`: сначала DM всем мастерам, затем мастер-чат.
- `dm_only`: только DM.
- `chat_only`: только мастер-чат.
- `chat_then_dm`: сначала мастер-чат, потом DM.

Ошибка DM одному мастеру (400/403) не блокирует остальных и не отменяет сохранение тикета.

---

## 8) Master-chat filter (critical)
Если сообщение пришло в `CLIENT_MASTERS_CHAT_ID`:
- обычные сообщения без команд не создают тикеты;
- обрабатываются команды/callback;
- логируется `master_chat_message_ignored`.

---

## 9) Shared clients registry format
Формат JSONL, одна строка = один JSON-объект клиента.
Primary key: `telegram_user_id`, fallback: `telegram_username`.

Пример синтетических записей:
```json
{"telegram_user_id":"1001","telegram_username":"client_a","full_name":"Client A","phones":["+79990000001"],"car_numbers":["A001AA152"],"vin_codes":[],"email":null,"vk_username":null,"max_username":null,"created_at":"2026-03-01T08:00:00+00:00","updated_at":"2026-03-01T08:10:00+00:00","source_tags":["telegram_client_bot"]}
{"telegram_user_id":"1002","telegram_username":null,"full_name":"Client B","phones":["+79990000002","+79990000003"],"car_numbers":[],"vin_codes":["VIN00000000000001"],"email":"client-b@example.com","vk_username":"client_b_vk","max_username":null,"created_at":"2026-03-01T08:05:00+00:00","updated_at":"2026-03-01T08:20:00+00:00","source_tags":["webapp","telegram"]}
{"telegram_user_id":null,"telegram_username":"fallback_user","full_name":"","phones":[],"car_numbers":[],"vin_codes":[],"email":null,"vk_username":null,"max_username":null,"created_at":"2026-03-01T08:30:00+00:00","updated_at":"2026-03-01T08:31:00+00:00","source_tags":["reviews_bot"]}
```

---

## 10) WebApp API contracts
### POST `/api/webapp/session`
Input: `initData`
- Success: `{ "ok": true, "session_token": "...", "ttl_seconds": 86400 }`
- Invalid: `{ "ok": false, "error": "invalid_init_data", "reason": "..." }`

### POST `/api/webapp/submit`
Input: `session_token` (priority), fallback `initData`, form fields.
- Missing phone: `400 {"ok":false,"error":"phone_required"}`
- Session expired: `401 {"ok":false,"error":"session_expired"}`
- Invalid auth: `401 {"ok":false,"error":"invalid_init_data","reason":"..."}`
- Success: `{ "ok": true, "ticket_id": "..." }`

---

## 11) Pin-flow behavior
- `pinned_message_id` читается через `parse_int_maybe` (int/str/None safe).
- Алгоритм:
  1. try edit existing pinned message text/markup;
  2. `message is not modified` = успешный no-op;
  3. `message to edit not found` / rights issues -> fallback to send new + pin + store id.
- Исключено некорректное использование `.isdigit()` для int в этом path.

---

## 12) URL sanitization for WebApp
Добавлена защита для URL вида:
- `https://HTTPS://...`
- `https://http://...`

Правила:
- убирается дублирующая схема;
- URL должен быть `https://...`;
- URL со пробелами/невалидной схемой отклоняется (`None`).

---

## 13) What was changed and why
1. `bots/client_bot/main.py`
   - расширена state-machine статусов (processed/archived/postponed canonical);
   - исправлена матрица notify mode (включая `chat_then_dm` порядок);
   - добавлен/уточнён мастер-контур `/waiting`, `/inprogress`;
   - улучшена нормализация WebApp URL и защита от double-scheme;
   - улучшен обработчик postponed через canonical status.
2. `tests/test_webapp_submit_validation.py`
   - добавлен smoke кейс `phone_required` через валидный session_token path.
3. `tests/test_client_bot_utils.py`
   - добавлен тест на URL `https://http://...`.
4. `README_AFTER_DEPLOY.md`
   - синхронизирован с фактическим состоянием кода.

---

## 14) Tests and local verification
Запуск:
- `python -m unittest discover -s tests -p 'test_*.py'`

Добавленные/обновлённые проверки:
- webapp submit validation (`phone_required`)
- normalize_webapp_url double-scheme case
- существующие smoke/registry/pin/master-chat tests сохранены

---

## 15) Known limitations / edge cases
- `telegram_username` может отсутствовать, используется `telegram_user_id`/fallback key.
- Telegram DM мастеру невозможен, если мастер не писал боту (`403`) или неверный id (`400 chat not found`).
- Жёсткая политика `https://` для WebApp URL: `http://` не принимается.
- Сроки `initData`/session token зависят от env TTL.

---

## 16) Mini-FAQ: «почему не приходит в ЛС мастеру?»
1. **403 bot can't initiate conversation**
   - Причина: мастер не запускал бота.
   - Действие: мастер должен написать `/start` боту.
2. **400 chat not found**
   - Причина: неверный `CLIENT_MASTER_USER_IDS`.
   - Действие: проверить `user_id` через `/whoami`.
3. **Ticket есть, но не увидели в ЛС**
   - Проверить `CLIENT_NOTIFY_MODE`, мастер-чат, и что тикет не archived.
4. **Что точно не ломается**
   - Тикет сохраняется даже при ошибке отправки мастеру.

