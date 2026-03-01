# README_AFTER_DEPLOY

## BotHost: production entrypoint (client-bot only)

### Единственный entrypoint
- Корневой файл: `main.py`.
- Содержимое: импорт `from services.client_bot_service.app.main import main as client_main` и вызов `client_main()`.
- Никаких запусков legacy `reviews_bot`, никаких dual-service стартов.

### Запуск
- Основная команда: `python main.py`
- Актуализированы launcher-файлы:
  - `Procfile`: `web: python main.py`
  - `railway.toml`: `startCommand = "python main.py"`
  - `run_all.sh`: вызывает `python main.py` и печатает `client_bot_service starting …`

---

## ENV для client-bot (алфавитно)

> Ниже только переменные, влияющие на `client_bot` runtime.

- `API_TOKEN` — fallback токена.
- `AUTO_PIN_ON_DEPLOY` — alias auto pin.
- `AUTO_PIN_ON_START` — alias auto pin.
- `BOT_API_TOKEN` — fallback токена.
- `BOT_PATH_SECRET` — fallback секрет для webapp session token.
- `CLIENT_ACTIVE_TICKET_TTL_HOURS` — TTL активного тикета.
- `CLIENT_AUTO_PIN_ON_DEPLOY` — auto pin.
- `CLIENT_AUTO_PIN_ON_START` — auto pin.
- `CLIENT_BOT_MODE` — `polling` (default).
- `CLIENT_CHAT_ID` — legacy fallback chat id.
- `CLIENT_DATA_DIR` — data directory для service config.
- `CLIENT_MASTER_CHAT_ID` — legacy alias `CLIENT_MASTERS_CHAT_ID`.
- `CLIENT_MASTER_IDS` — legacy alias `CLIENT_MASTER_USER_IDS`.
- `CLIENT_MASTER_USER_IDS` — список master user id для DM.
- `CLIENT_MASTERS_CHAT_ID` — master chat id (поддерживает `-100...`).
- `CLIENT_NOTIFY_MODE` — `dm_then_chat` (default), `dm_only`, `chat_only`, `chat_then_dm`.
- `CLIENT_RUN_MODE` — legacy alias `CLIENT_BOT_MODE`.
- `CLIENT_SERVICE_HOST` — default `0.0.0.0`.
- `CLIENT_SERVICE_PORT` — fallback порта.
- `CLIENT_TELEGRAM_BOT_TOKEN` — приоритетный токен.
- `CLIENT_WEBAPP_ENABLED` — включение WebApp routes.
- `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS` — TTL initData/session.
- `CLIENT_WEBAPP_SESSION_SECRET` — секрет подписи session token.
- `CLIENT_WEBAPP_URL` — приоритетный публичный URL WebApp.
- `CLIENTS_REGISTRY_PATH` — путь к `clients.jsonl` (default корень repo).
- `DATABASE_URL` — postgres DSN.
- `DOMAIN` — fallback хост для сборки webapp URL.
- `LIRA_ADDRESS` — адрес в сообщениях.
- `LIRA_MAP_URL` — ссылка на карту.
- `LIRA_PHONE` — контактный телефон.
- `PORT` — приоритетный порт.
- `POSTGRESQL_URL` — fallback postgres DSN.
- `POSTGRES_URL` — fallback postgres DSN.
- `RUN_MODE` — legacy alias `CLIENT_BOT_MODE`.
- `SHOW_REGLAMENT_PHRASE` — pin text toggle.
- `SHOW_ROUTE_IMAGE` — media toggle.
- `TELEGRAM_BOT_TOKEN` — fallback токена.
- `TIMEZONE` — timezone (default Europe/Moscow).
- `WEBAPP_ENABLED` — fallback флаг webapp.
- `WEBAPP_PATH` — default `/WEBAPP`.
- `WEBAPP_URL` — fallback публичного URL WebApp.

---

## Token contract

Приоритет токена строго такой:
1. `CLIENT_TELEGRAM_BOT_TOKEN`
2. `TELEGRAM_BOT_TOKEN`
3. `BOT_API_TOKEN`
4. `API_TOKEN`

Если токен отсутствует — приложение аварийно завершается с `RuntimeError` (без тихого skip).
В логах печатается только `token_source` (без значения токена).

---

## Port/host/domain rules

### Port
1. `PORT`
2. `CLIENT_SERVICE_PORT`
3. `8000`

### Host
- `CLIENT_SERVICE_HOST`, default `0.0.0.0`

### WebApp URL
1. `CLIENT_WEBAPP_URL`
2. `WEBAPP_URL`
3. иначе: `https://{DOMAIN}{WEBAPP_PATH}`

Нормализация URL:
- trim пробелов;
- удаление двойной схемы (`https://https://...`, `https://http://...`);
- принудительный `https://`;
- если URL невалидный, он отбрасывается (`None`), в логах warning и fallback к `DOMAIN + WEBAPP_PATH`.

---

## WebApp backend /WEBAPP

Гарантированные маршруты:
- `/WEBAPP`, `/WEBAPP/` → `index.html`
- `/app.css` → 200
- `/app.js` → 200
- `/WEBAPP/config.json` → 200

API:
- `POST /api/webapp/session`
  - принимает `initData`
  - валидирует
  - возвращает `session_token` + `ttl_seconds`
  - подпись через `CLIENT_WEBAPP_SESSION_SECRET` (fallback `BOT_PATH_SECRET`)
- `POST /api/webapp/submit`
  - сначала `session_token`
  - fallback: `initData`
  - без телефона: `400 {ok:false,error:"phone_required"}`
  - просроченная сессия: `401 {ok:false,error:"session_expired"}`
  - невалидный initData: `401 {ok:false,error:"invalid_init_data"}`
  - успех: `200 {ok:true,ticket_id:"..."}`

PII-safe logging:
- initData полностью не логируется;
- логируется только status/reason/age/ticket_id.

---

## Notify modes + master chat filter

### Delivery rules
- если `CLIENT_MASTERS_CHAT_ID` пустой → только DM мастерам;
- если `CLIENT_MASTER_USER_IDS` пустой → только master-chat;
- если оба заданы → по `CLIENT_NOTIFY_MODE`.

DM ошибки (`400/403`) не останавливают рассылку остальным получателям.

### Master chat filtering
- В master chat plain text без команды/без ticket marker не создаёт тикет.
- Разрешены команды (`/new`, `/tickets`, `/ticket <id>`, `/waiting`, `/inprogress`, `/queue`, callbacks).
- `/new` и `/tickets` показывают `new + waiting_data`.

---

## Ticket intake (private chat)

Любое private сообщение пользователя (не команда):
- upsert клиента в `clients.jsonl`;
- создание/апдейт тикета;
- если телефона нет — `status=waiting_data` и запрос телефона;
- если телефон есть — `status=new`.

Поля тикета:
- `client_user_id`
- `client_username` (без `@`)
- `full_name`
- `client_phone`
- `original_message_text`
- `source` = `telegram_chat` или `webapp`

---

## Pin flow (anti-duplication)

- `pinned_message_id` хранится как int в core/system storage.
- При наличии id: сначала edit existing pin (`editMessageText`/`editMessageReplyMarkup`).
- `message is not modified` считается успехом, новый pin не создаётся.
- При `message to edit not found`/rights issue — fallback: создать новый pin и сохранить новый id.

---

## Подключение мастеров

1. Мастер обязан написать боту `/start` в ЛС.
2. До этого Telegram API может отвечать `403`, и DM не доставится.
3. После `/start` мастер добавляется в `CLIENT_MASTER_USER_IDS` либо через админ-поток.

---

## Smoke test перед/после деплоя

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
