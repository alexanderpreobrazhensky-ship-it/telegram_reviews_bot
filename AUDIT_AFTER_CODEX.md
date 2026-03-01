# AUDIT_AFTER_CODEX

## 1) Исправления по BotHost-логам (проблема → решение)

### 1.1 BotHost запускал Node/webapp/app.js (`window is not defined`)
- **Проблема:** в корне был legacy `main.py` с чужой логикой, из-за чего автоопределение entrypoint было нестабильным.
- **Решение:** корневой `main.py` заменён на минимальный Python-entrypoint для client-bot service.
- **Файлы:** `main.py`.

### 1.2 `client_bot token missing`
- **Проблема:** токен искался только в `CLIENT_TELEGRAM_BOT_TOKEN`.
- **Решение:** единый fallback-chain:
  `CLIENT_TELEGRAM_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN` → `BOT_API_TOKEN` → `API_TOKEN`.
  При отсутствии токена — `RuntimeError` (не тихий skip).
- **Файлы:**
  - `services/client_bot_service/app/config.py`
  - `bots/client_bot/main.py`

### 1.3 Некорректные WebApp URL / DOMAIN (Railway хвосты)
- **Проблема:** URL брался фрагментарно и мог содержать двойные схемы.
- **Решение:** добавлена нормализация `DOMAIN` и `WebApp URL`:
  - приоритет `CLIENT_WEBAPP_URL`, затем `WEBAPP_URL`;
  - fallback: `https://{DOMAIN}{WEBAPP_PATH}`;
  - очистка схем/хоста, канонизация в HTTPS.
- **Файлы:** `bots/client_bot/main.py`.

### 1.4 Конфликт портов (8000/8010)
- **Проблема:** сервис использовал только `CLIENT_SERVICE_PORT` c default `8010`.
- **Решение:** единая формула порта:
  `PORT` → `CLIENT_SERVICE_PORT` → `8000`.
- **Файлы:** `services/client_bot_service/app/config.py`.

### 1.5 Поведение мастер-чата
- **Статус:** логика уже была корректна (plain text в masters chat не создаёт тикет).
- **Подтверждение:** существующий smoke-тест + сохранена текущая реализация.
- **Файлы:** `bots/client_bot/main.py`, `tests/test_service_smoke.py`.

### 1.6 Pin-flow
- **Статус:** в коде уже используется `parse_int_maybe` и обработка `message is not modified` как успех.
- **Действие:** поведение подтверждено тестами, без регрессий.
- **Файлы:** `bots/client_bot/main.py`, `tests/test_client_bot_utils.py`.

---

## 2) Конечная схема запуска на BotHost

- **Entrypoint:** `main.py` (корень репозитория).
- **Команда:** `python main.py`.
- **Сервис:** `services.client_bot_service.app.main`.
- **Порт:** `PORT` (fallback `CLIENT_SERVICE_PORT`, иначе `8000`).
- **Host:** `0.0.0.0` (по умолчанию).
- **Mode:** `CLIENT_BOT_MODE=polling` по умолчанию.

---

## 3) Полный список ENV, реально читаемых client-bot (алфавитно)

> Ниже перечислены env, которые читаются в `services/client_bot_service/app/*` и/или `bots/client_bot/main.py` для client-bot runtime.

### Required / critical
- `API_TOKEN` (fallback токена)
- `BOT_API_TOKEN` (fallback токена)
- `CLIENT_MASTER_USER_IDS` (мастера в личку)
- `CLIENT_MASTERS_CHAT_ID` (чат мастеров)
- `CLIENT_TELEGRAM_BOT_TOKEN` (приоритетный токен)
- `DOMAIN` (для корректного публичного WebApp URL fallback)
- `PORT` (приоритетный порт)
- `TELEGRAM_BOT_TOKEN` (fallback токена)

### Optional (active)
- `AUTO_PIN_ON_DEPLOY`, `AUTO_PIN_ON_START`, `CLIENT_AUTO_PIN_ON_DEPLOY`, `CLIENT_AUTO_PIN_ON_START`
- `BOT_PATH_SECRET`
- `CLIENT_ACTIVE_TICKET_TTL_HOURS`
- `CLIENT_BOT_MODE`
- `CLIENT_CHAT_ID`
- `CLIENT_DATA_DIR`
- `CLIENT_MASTER_CHAT_ID` (alias)
- `CLIENT_MASTER_IDS` (alias)
- `CLIENT_MASTER_CHAT_MODE`, `MASTER_CHAT_MODE`
- `CLIENT_NOTIFY_MODE`
- `CLIENT_RUN_MODE`, `RUN_MODE` (aliases)
- `CLIENT_SERVICE_HOST`
- `CLIENT_SERVICE_PORT`
- `CLIENT_WEBAPP_ENABLED`, `WEBAPP_ENABLED`
- `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS`
- `CLIENT_WEBAPP_SESSION_SECRET`
- `CLIENT_WEBAPP_URL`, `WEBAPP_URL`
- `DATABASE_URL`, `POSTGRES_URL`, `POSTGRESQL_URL`
- `LIRA_ADDRESS`, `LIRA_MAP_URL`, `LIRA_PHONE`
- `PORT`
- `ROUTE_URL`
- `SHOW_REGLAMENT_PHRASE`, `CLIENT_SHOW_REGLAMENT_PHRASE`
- `SHOW_ROUTE_IMAGE`
- `TELEGRAM_BOT_TOKEN`
- `TIMEZONE`
- `WEBAPP_PATH`

### Legacy / compatibility
- `CLIENT_RUN_MODE`, `RUN_MODE`
- `CLIENT_MASTER_CHAT_ID`, `CLIENT_MASTER_IDS`
- `WEBAPP_URL`
- `POSTGRES_URL`, `POSTGRESQL_URL`

---

## 4) Локальные проверки

Выполненные проверки:
1. unit/smoke тесты (`unittest discover`)
2. targeted тесты BotHost contract:
   - root entrypoint
   - port resolution
   - token fallback chain
   - DOMAIN/WebApp URL sanitize
3. webapp submit validation (`phone_required`)
4. masters chat filter (no ticket on plain text)

---

## 5) Known limitations / edge cases

1. `CLIENT_BOT_MODE=webhook` пока не является основной целевой схемой для BotHost в этом репозитории; production-рекомендуемый режим — polling.
2. При эфемерной FS `clients.jsonl` и `data/*` нужно обязательно включать `DATABASE_URL` и/или внешний persistent volume.
3. DM мастеру может вернуть `403/400`, если мастер не запускал бота или id неверен; тикет при этом сохраняется.

---

## 6) Файлы, изменённые в рамках задачи

- `main.py`
- `services/client_bot_service/app/config.py`
- `services/client_bot_service/app/main.py`
- `bots/client_bot/main.py`
- `tests/test_bothost_contract.py`
- `README_AFTER_DEPLOY.md`
- `AUDIT_AFTER_CODEX.md`
- `clients.jsonl`
