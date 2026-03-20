# DEPLOY_ENV_REFERENCE.md

Полный реестр ENV по результатам code-first аудита. Этот файл разделяет:

- **Node production path** — реально активный runtime на BotHost.
- **Legacy Python contour** — переменные, которые всё ещё читаются в репозитории, но не входят в текущий production-path.
- **Documented-only / dead** — переменные, которые читаются или документированы, но фактически не меняют поведение активного Node runtime.

Статусы:

- `required` — нужен для рабочего контура или платформенного контракта.
- `recommended` — процесс может стартовать и без него, но прод-сценарий будет частично деградирован.
- `optional` — есть рабочий default или это тюнинг.
- `legacy/dead` — относится к legacy-контуру либо не влияет на активный runtime.

## 1) Node production path (активный runtime)

| ENV | Статус | Default | Где читается / реально используется | Зачем нужна | Prod | BotHost | Telegram / MAX / common | Комментарий |
|---|---|---|---|---|---|---|---|---|
| `PORT` | required | `3000` fallback | `src/infrastructure/config/index.js`, `app.js` | Порт HTTP listener | yes | yes | common | На BotHost должен приходить от платформы. |
| `NODE_ENV` | optional | `development` | `src/infrastructure/config/index.js`, `/health` payload | Маркер окружения | no | no | common | Не гейтит бизнес-ветвление. |
| `DB_FILE_PATH` | required | `data/db.json` | `src/infrastructure/db/index.js` | Путь к JSON DB | yes | yes | common | Практически обязателен для persistent storage на BotHost. |
| `TELEGRAM_CLIENT_BOT_TOKEN` | required | empty | `src/infrastructure/config/index.js`, `app.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js` | Входящие/исходящие сообщения client bot и clarifications | yes | yes | telegram | Без него Telegram client contour деградирует. |
| `TELEGRAM_MASTER_BOT_TOKEN` | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/server/index.js` | Telegram master bot webhook/outbound и masters notifications | yes | yes | telegram | Без него ветка master bot нерабочая. |
| `TELEGRAM_INTEGRATION_BOT_TOKEN` | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/integration_bot/index.js` | Telegram integration bot | recommended | recommended | telegram | Нужен для полного текущего Telegram-контура. |
| `MASTER_BOT_ADMIN_IDS` | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/core/application/masterService.js`, `src/infrastructure/db/index.js` | Bootstrap admin access для Telegram master bot | yes | yes | telegram | CSV id list. |
| `TELEGRAM_MASTERS_CHAT_ID` | recommended | empty | `src/infrastructure/config/index.js`, `src/server/index.js` | Дублирование новых заявок в Telegram masters chat | optional | optional | telegram | Не требуется для старта, но полезно в работе. |
| `WEBAPP_URL` | required | `https://example.com` | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/shared/channelAdapters.js`, `src/server/index.js` | Основной URL shared WebApp / Mini App | yes | yes | common | Технический default не пригоден для production. |
| `WEBAPP_TELEGRAM_CHANNEL_LINK` | optional | empty | `src/infrastructure/config/index.js`, `src/server/index.js`, `public/webapp.js` | Ссылка на Telegram-канал внутри WebApp | no | no | telegram/common | Используется только если задана. |
| `TELEGRAM_CHANNEL_URL` | optional | empty | `src/infrastructure/config/index.js`, `src/server/index.js`, `public/webapp.js` | Alias для ссылки на Telegram-канал | no | no | telegram/common | Имеет приоритет над `WEBAPP_TELEGRAM_CHANNEL_LINK`. |
| `WEBAPP_DEDUPE_WINDOW_MS` | optional | `45000` | `src/infrastructure/config/index.js`, `src/server/index.js` | Окно дедупликации повторных WebApp submit | no | no | common | Влияет только на WebApp request create. |
| `FEEDBACK_REQUEST_DELAY_MINUTES` | optional | `5` | `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js` | Отложенная постановка feedback task | no | no | common | Влияет на scheduler-driven feedback. |
| `SCHEDULER_INTERVAL_MS` | optional | `15000` | `src/infrastructure/config/index.js`, `app.js` | Интервал scheduler loop | no | no | common | Clamp/validation есть. |
| `SCHEDULER_BATCH_SIZE` | optional | `10` | `src/infrastructure/config/index.js`, `app.js` | Размер пачки задач | no | no | common | Clamp/validation есть. |
| `SCHEDULER_MAX_ATTEMPTS` | optional | `3` | `src/infrastructure/config/index.js`, `app.js` | Retry budget задач scheduler | no | no | common | Clamp/validation есть. |
| `SCHEDULER_STUCK_TIMEOUT_MS` | optional | `300000` | `src/infrastructure/config/index.js`, `app.js` | Recovery stuck processing tasks | no | no | common | Clamp/validation есть. |
| `MAX_ENABLED` | recommended | `false` | `src/infrastructure/config/index.js` | Operator-facing feature flag for MAX | recommended if MAX | recommended if MAX | max | Читается, но не гейтит route wiring. |
| `MAX_CLIENT_BOT_TOKEN` | required | empty | `src/infrastructure/config/index.js`, `app.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js` | MAX client bot inbound/outbound foundation | yes if MAX | yes if MAX | max | Нужен для chat flow и outbound. |
| `MAX_MASTER_BOT_TOKEN` | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js` | MAX master bot inbound/outbound | yes if MAX | yes if MAX | max | Нужен для staff contour в MAX. |
| `MAX_MASTER_BOT_ADMIN_IDS` | required | empty | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/core/application/masterService.js`, `src/infrastructure/db/index.js` | Bootstrap admin access для MAX master bot | yes if MAX | yes if MAX | max | CSV id list. |
| `MAX_WEBHOOK_SECRET` | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `src/interfaces/master_bot/index.js` | Проверка заголовка `x-max-bot-api-secret` | recommended if MAX | recommended if MAX | max | Если пусто, MAX webhook secret-check не работает. |
| `MAX_WEBAPP_URL` | recommended | fallback to `WEBAPP_URL` | `src/infrastructure/config/index.js`, `src/interfaces/shared/channelAdapters.js`, `src/server/index.js` | Отдельный MAX Mini App URL | optional | optional | max | Если не задан, используется `WEBAPP_URL`. |
| `MAX_BOT_NAME` | recommended | empty | `src/infrastructure/config/index.js`, `src/interfaces/shared/channelAdapters.js`, `src/infrastructure/messaging/index.js` | Построение MAX bot/deep links | recommended if MAX | recommended if MAX | max | Без него deep-link foundation ограничен. |
| `MAX_DEEPLINK_BASE_URL` | optional | empty | `src/infrastructure/config/index.js`, `src/server/index.js` | Доп. metadata для MAX deep links | optional | optional | max | Сейчас только инжектится в HTML runtime metadata. |
| `ONE_C_WEBHOOK_SECRET` | legacy/dead | empty | `src/infrastructure/config/index.js` | Декларируемая проверка webhook 1C | no | no | integrations | В active HTTP route не валидируется. |
| `ENABLE_INTEGRATION_WORKER` | legacy/dead | `true` | `src/infrastructure/config/index.js` | Декларируемый toggle worker | no | no | integrations | Отдельного worker процесса нет. |
| `ONE_C_SYNC_ENABLED` | legacy/dead | `false` | `src/infrastructure/config/index.js` | Декларируемый toggle 1C sync | no | no | integrations | Не блокирует активные 1C routes. |
| `EMAIL_IMPORT_ENABLED` | legacy/dead | `true` | `src/infrastructure/config/index.js` | Декларируемый toggle email import | no | no | integrations | Email route не gated этим флагом. |
| `INTEGRATION_RETRY_MAX` | legacy/dead | `3` | `src/infrastructure/config/index.js` | Retry knob для интеграций | no | no | integrations | В active integration runtime не используется как отдельный retry pipeline. |
| `INTEGRATION_RETRY_DELAY_SECONDS` | legacy/dead | `60` | `src/infrastructure/config/index.js` | Retry delay knob для интеграций | no | no | integrations | Аналогично, декларативно. |
| `DB_URL` | legacy/dead | `postgres://localhost:5432/telegram_reviews` | `src/infrastructure/config/index.js` | SQL URL placeholder | no | no | common | Фактический runtime работает на file DB. |
| `QUEUE_DRIVER` | legacy/dead | `memory` | `src/infrastructure/config/index.js` | Queue backend placeholder | no | no | common | Реального queue backend нет. |

## 2) Legacy Python contour (читается в репозитории, но не в Node production path)

| ENV | Статус | Default | Где читается | Зачем нужна / на что похожа | Node prod path | Комментарий |
|---|---|---|---|---|---|---|
| `CLIENT_TELEGRAM_BOT_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py` | Основной Python client bot token alias | no | Не нужен для Node runtime. |
| `TELEGRAM_BOT_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py` | Token alias | no | Не нужен для Node runtime. |
| `BOT_API_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py` | Token alias | no | Не нужен для Node runtime. |
| `API_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py` | Token alias | no | Не нужен для Node runtime. |
| `BOT_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py` | Token alias | no | Не нужен для Node runtime. |
| `TOKEN` | legacy/dead | empty | `bots/client_bot/main.py` | Token alias | no | Не нужен для Node runtime. |
| `CLIENT_WEBAPP_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python WebApp URL | no | Node runtime использует `WEBAPP_URL` / `MAX_WEBAPP_URL`. |
| `WEBAPP_ENABLED` | legacy/dead | `1` | `bots/client_bot/main.py` | Python toggle WebApp | no | Node path не использует. |
| `CLIENT_WEBAPP_ENABLED` | legacy/dead | `1` | `bots/client_bot/main.py` | Python toggle WebApp | no | Node path не использует. |
| `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS` | legacy/dead | `86400` | `bots/client_bot/main.py` | TTL для Telegram WebApp initData | no | В Node WebApp auth не реализован. |
| `CLIENT_WEBAPP_SESSION_SECRET` | legacy/dead | empty | `bots/client_bot/main.py` | Session signing secret | no | В Node contour нет аналога. |
| `CLIENT_WEBAPP_TEST_MODE` | legacy/dead | empty | `bots/client_bot/main.py` | WebApp test mode | no | В Node contour нет аналога. |
| `WEBAPP_PATH` | legacy/dead | empty | `bots/client_bot/main.py` | Python web route path | no | Node path использует hardcoded routes. |
| `WEBHOOK_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python webhook base URL | no | Node runtime routes fixed in server. |
| `PUBLIC_BASE_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python public base URL | no | Node runtime routes fixed in server. |
| `DOMAIN` | legacy/dead | empty | `bots/client_bot/main.py` | Python domain helper | no | Node runtime не использует. |
| `BOT_PATH_SECRET` | legacy/dead | empty | `bots/client_bot/main.py` | Python path/session secret | no | Не относится к Node runtime. |
| `CLIENT_BOT_MODE` | legacy/dead | empty | `bots/client_bot/main.py` | Python run mode | no | Не относится к Node runtime. |
| `CLIENT_RUN_MODE` | legacy/dead | empty | `bots/client_bot/main.py` | Python run mode | no | Не относится к Node runtime. |
| `RUN_MODE` | legacy/dead | empty | `bots/client_bot/main.py` | Python run mode | no | Не относится к Node runtime. |
| `CLIENT_SERVICE_PORT` | legacy/dead | empty | `services/client_bot_service/app/config.py` | Порт Python сервиса | no | Не относится к Node runtime. |
| `CLIENT_SERVICE_HOST` | legacy/dead | empty | `services/client_bot_service/app/config.py` | Хост Python сервиса | no | Не относится к Node runtime. |
| `CLIENT_MASTERS_CHAT_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python masters chat id | no | В Node path используется `TELEGRAM_MASTERS_CHAT_ID`. |
| `CLIENT_MASTER_CHAT_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python masters chat id alias | no | Не относится к Node runtime. |
| `CLIENT_MASTER_CHAT_MODE` | legacy/dead | `OFF` | `bots/client_bot/main.py` | Python masters chat mode | no | Не относится к Node runtime. |
| `MASTER_CHAT_MODE` | legacy/dead | `OFF` | `bots/client_bot/main.py` | Python masters chat mode alias | no | Не относится к Node runtime. |
| `CLIENT_MASTER_USER_IDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python staff ids | no | Node path uses DB roles instead. |
| `CLIENT_MASTER_IDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python staff ids alias | no | Не относится к Node runtime. |
| `CLIENT_CHAT_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python fallback chat id | no | Не относится к Node runtime. |
| `CLIENT_NOTIFY_MODE` | legacy/dead | `dm_then_chat` | `bots/client_bot/main.py` | Python notification policy | no | Не относится к Node runtime. |
| `CLIENT_ADMIN_IDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python admin ids | no | Node path uses `MASTER_BOT_ADMIN_IDS`. |
| `ADMIN_IDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python admin ids alias | no | Не относится к Node runtime. |
| `SUPERADMIN_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python superadmin id | no | Не относится к Node runtime. |
| `SUPERADMIN_IDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python superadmin ids | no | Не относится к Node runtime. |
| `MASTER_USERNAMES` | legacy/dead | empty | `bots/client_bot/main.py` | Python staff username ACL | no | Не относится к Node runtime. |
| `REPORT_CHAT_IDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python reporting chats | no | Не относится к Node runtime. |
| `CLIENT_CHANNEL_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python channel binding | no | Не относится к Node runtime. |
| `CLIENT_POST_TARGET_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python post target | no | Не относится к Node runtime. |
| `CLIENT_POST_CHAT_ID` | legacy/dead | empty | `bots/client_bot/main.py` | Python post target alias | no | Не относится к Node runtime. |
| `CLIENT_BOT_USERNAME` | legacy/dead | empty | `bots/client_bot/main.py` | Python bot username | no | Не относится к Node runtime. |
| `TELEGRAM_BOT_USERNAME` | legacy/dead | empty | `bots/client_bot/main.py` | Python bot username alias | no | Не относится к Node runtime. |
| `BOT_USERNAME` | legacy/dead | empty | `bots/client_bot/main.py` | Python bot username alias | no | Не относится к Node runtime. |
| `TIMEZONE` | legacy/dead | `Europe/Moscow` | `bots/client_bot/main.py` | Python UI/report timezone | no | Node path не использует. |
| `LIRA_PHONE` | legacy/dead | empty | `bots/client_bot/main.py` | Python business contact data | no | Node path не использует. |
| `LIRA_ADDRESS` | legacy/dead | `Удмуртская 10` | `bots/client_bot/main.py` | Python business contact data | no | Node path не использует. |
| `LIRA_MAP_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python map link | no | Node path не использует. |
| `SHOW_ROUTE_IMAGE` | legacy/dead | empty | `bots/client_bot/main.py` | Python UI flag | no | Не относится к Node runtime. |
| `CLIENT_SHOW_REGLAMENT_PHRASE` | legacy/dead | empty | `bots/client_bot/main.py` | Python UI flag | no | Не относится к Node runtime. |
| `SHOW_REGLAMENT_PHRASE` | legacy/dead | empty | `bots/client_bot/main.py` | Python UI flag alias | no | Не относится к Node runtime. |
| `PIN_TEMPLATE_VERSION` | legacy/dead | `v1` | `bots/client_bot/main.py` | Python pin template version | no | Не относится к Node runtime. |
| `CLIENT_AUTO_PIN_ON_START` | legacy/dead | empty | `bots/client_bot/main.py` | Python startup behavior | no | Не относится к Node runtime. |
| `CLIENT_AUTO_PIN_ON_DEPLOY` | legacy/dead | empty | `bots/client_bot/main.py` | Python deploy behavior | no | Не относится к Node runtime. |
| `AUTO_PIN_ON_START` | legacy/dead | empty | `bots/client_bot/main.py` | Python startup behavior alias | no | Не относится к Node runtime. |
| `AUTO_PIN_ON_DEPLOY` | legacy/dead | empty | `bots/client_bot/main.py` | Python deploy behavior alias | no | Не относится к Node runtime. |
| `CLIENT_ACTIVE_TICKET_TTL_HOURS` | legacy/dead | empty | `bots/client_bot/main.py` | Python ticket TTL | no | Не относится к Node runtime. |
| `AI_FALLBACK_THRESHOLD` | legacy/dead | empty | `bots/client_bot/main.py` | Python AI fallback tuning | no | Не относится к Node runtime. |
| `AI_FALLBACK_TTL_SECONDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python AI fallback tuning | no | Не относится к Node runtime. |
| `AI_FALLBACK_WINDOW_SECONDS` | legacy/dead | empty | `bots/client_bot/main.py` | Python AI fallback tuning | no | Не относится к Node runtime. |
| `ROUTE_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python route link | no | Не относится к Node runtime. |
| `DATABASE_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python DB connection candidate | no | Не относится к Node runtime. |
| `POSTGRES_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python DB connection candidate | no | Не относится к Node runtime. |
| `POSTGRESQL_URL` | legacy/dead | empty | `bots/client_bot/main.py` | Python DB connection candidate | no | Не относится к Node runtime. |
| `CLIENTS_REGISTRY_PATH` | legacy/dead | repo-local file | `bots/client_bot/main.py` | Python clients registry path | no | Не относится к Node runtime. |
| `CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS` | legacy/dead | empty | `shared/clients_registry.py` | Python lock tuning | no | Не относится к Node runtime. |
| `CLIENT_GITHUB_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py`, `bots/client_bot/storage.py` | Python GitHub storage integration | no | Не относится к Node runtime. |
| `GITHUB_TOKEN` | legacy/dead | empty | `bots/client_bot/main.py`, `bots/client_bot/storage.py` | Python GitHub storage integration alias | no | Не относится к Node runtime. |
| `CLIENT_GITHUB_REPO` | legacy/dead | empty | `bots/client_bot/main.py`, `bots/client_bot/storage.py` | Python GitHub storage integration | no | Не относится к Node runtime. |
| `GITHUB_REPO` | legacy/dead | empty | `bots/client_bot/main.py`, `bots/client_bot/storage.py` | Python GitHub storage integration alias | no | Не относится к Node runtime. |
| `CLIENT_GITHUB_BRANCH` | legacy/dead | `main` | `bots/client_bot/storage.py` | Python GitHub storage integration | no | Не относится к Node runtime. |
| `GITHUB_BRANCH` | legacy/dead | `main` | `bots/client_bot/storage.py` | Python GitHub storage integration alias | no | Не относится к Node runtime. |
| `CLIENT_TG_TIMEOUT_SECONDS` | legacy/dead | empty | `bots/client_bot/services/telegram_api.py` | Python Telegram API timeout | no | Не относится к Node runtime. |
| `CLIENT_TG_RETRY_MAX` | legacy/dead | empty | `bots/client_bot/services/telegram_api.py` | Python Telegram retry tuning | no | Не относится к Node runtime. |
| `CLIENT_TG_RETRY_BASE_SLEEP_SECONDS` | legacy/dead | empty | `bots/client_bot/services/telegram_api.py` | Python Telegram retry tuning | no | Не относится к Node runtime. |
| `CLIENT_TG_QUEUE_ENABLED` | legacy/dead | `1` | `bots/client_bot/services/outgoing_queue.py` | Python outgoing queue toggle | no | Не относится к Node runtime. |
| `CLIENT_DEEPSEEK_API_KEY` | legacy/dead | empty | `bots/client_bot/main.py`, `bots/client_bot/services/ai_service.py` | Python AI integration key | no | Не относится к Node runtime. |

## 3) Минимальный обязательный набор ENV для production deploy

```env
PORT=3000
DB_FILE_PATH=/persistent/path/db.json
WEBAPP_URL=https://<your-domain>
TELEGRAM_CLIENT_BOT_TOKEN=<telegram-client-token>
TELEGRAM_MASTER_BOT_TOKEN=<telegram-master-token>
MASTER_BOT_ADMIN_IDS=123456789
```

> Для полного текущего продукта практически нужен ещё и `TELEGRAM_INTEGRATION_BOT_TOKEN`.

## 4) Минимальный обязательный набор ENV именно для BotHost

```env
# PORT обычно задаётся BotHost автоматически
DB_FILE_PATH=/persistent/path/db.json
WEBAPP_URL=https://<login>.bothost.ru
TELEGRAM_CLIENT_BOT_TOKEN=<telegram-client-token>
TELEGRAM_MASTER_BOT_TOKEN=<telegram-master-token>
MASTER_BOT_ADMIN_IDS=123456789
```

Рекомендуется сразу добавить:

```env
TELEGRAM_INTEGRATION_BOT_TOKEN=<telegram-integration-token>
TELEGRAM_MASTERS_CHAT_ID=-1001234567890
WEBAPP_TELEGRAM_CHANNEL_LINK=https://t.me/<channel>
```

## 5) Текущий набор ENV для Telegram-контура

```env
TELEGRAM_CLIENT_BOT_TOKEN=<telegram-client-token>
TELEGRAM_MASTER_BOT_TOKEN=<telegram-master-token>
TELEGRAM_INTEGRATION_BOT_TOKEN=<telegram-integration-token>
MASTER_BOT_ADMIN_IDS=123456789
TELEGRAM_MASTERS_CHAT_ID=-1001234567890
WEBAPP_URL=https://<login>.bothost.ru
WEBAPP_TELEGRAM_CHANNEL_LINK=https://t.me/<channel>
DB_FILE_PATH=/persistent/path/db.json
```

## 6) Рекомендуемый набор ENV для будущего MAX-контура

```env
MAX_ENABLED=true
MAX_CLIENT_BOT_TOKEN=<max-client-token>
MAX_MASTER_BOT_TOKEN=<max-master-token>
MAX_MASTER_BOT_ADMIN_IDS=mx-admin-1,mx-admin-2
MAX_WEBHOOK_SECRET=<secret>
MAX_BOT_NAME=<bot-name>
MAX_WEBAPP_URL=https://<login>.bothost.ru
MAX_DEEPLINK_BASE_URL=https://<custom-max-base>
```

### Что из этого реально обязательно для MAX

- `MAX_CLIENT_BOT_TOKEN`
- `MAX_MASTER_BOT_TOKEN`
- `MAX_MASTER_BOT_ADMIN_IDS`
- `MAX_WEBHOOK_SECRET` — практически обязателен по security-модели webhook
- `MAX_BOT_NAME` — практически обязателен для удобных deep links

## 7) Пример готового набора ENV для ручного заполнения

```env
NODE_ENV=production
DB_FILE_PATH=/persistent/path/db.json
WEBAPP_URL=https://<login>.bothost.ru
WEBAPP_TELEGRAM_CHANNEL_LINK=https://t.me/<channel>
WEBAPP_DEDUPE_WINDOW_MS=45000

TELEGRAM_CLIENT_BOT_TOKEN=<telegram-client-token>
TELEGRAM_MASTER_BOT_TOKEN=<telegram-master-token>
TELEGRAM_INTEGRATION_BOT_TOKEN=<telegram-integration-token>
MASTER_BOT_ADMIN_IDS=123456789
TELEGRAM_MASTERS_CHAT_ID=-1001234567890

SCHEDULER_INTERVAL_MS=15000
SCHEDULER_BATCH_SIZE=10
SCHEDULER_MAX_ATTEMPTS=3
SCHEDULER_STUCK_TIMEOUT_MS=300000
FEEDBACK_REQUEST_DELAY_MINUTES=5

MAX_ENABLED=false
# MAX_CLIENT_BOT_TOKEN=
# MAX_MASTER_BOT_TOKEN=
# MAX_MASTER_BOT_ADMIN_IDS=
# MAX_WEBHOOK_SECRET=
# MAX_BOT_NAME=
# MAX_WEBAPP_URL=
# MAX_DEEPLINK_BASE_URL=
```

## 8) Категории ENV по итогам аудита

### Required

- `PORT`
- `DB_FILE_PATH`
- `WEBAPP_URL`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `MASTER_BOT_ADMIN_IDS`
- MAX-only required when MAX is enabled: `MAX_CLIENT_BOT_TOKEN`, `MAX_MASTER_BOT_TOKEN`, `MAX_MASTER_BOT_ADMIN_IDS`

### Recommended

- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `TELEGRAM_MASTERS_CHAT_ID`
- `WEBAPP_TELEGRAM_CHANNEL_LINK` / `TELEGRAM_CHANNEL_URL`
- `MAX_ENABLED`
- `MAX_WEBHOOK_SECRET`
- `MAX_WEBAPP_URL`
- `MAX_BOT_NAME`

### Optional

- `NODE_ENV`
- `WEBAPP_DEDUPE_WINDOW_MS`
- `FEEDBACK_REQUEST_DELAY_MINUTES`
- `SCHEDULER_INTERVAL_MS`
- `SCHEDULER_BATCH_SIZE`
- `SCHEDULER_MAX_ATTEMPTS`
- `SCHEDULER_STUCK_TIMEOUT_MS`
- `MAX_DEEPLINK_BASE_URL`

### Legacy / dead / documented-only

- `ONE_C_WEBHOOK_SECRET`
- `ENABLE_INTEGRATION_WORKER`
- `ONE_C_SYNC_ENABLED`
- `EMAIL_IMPORT_ENABLED`
- `INTEGRATION_RETRY_MAX`
- `INTEGRATION_RETRY_DELAY_SECONDS`
- `DB_URL`
- `QUEUE_DRIVER`
- весь Python-only ENV contour из раздела 2

## 9) Короткие выводы

- Для BotHost самый чувствительный ENV — `DB_FILE_PATH`, потому что от него зависит сохранность базы на фоне redeploy.
- Для Telegram обязательны токены client/master bot и bootstrap admins.
- Для MAX foundation уже подготовлена, но recommendations/auth и operator parity ещё не доведены до готового production-level состояния.
- Legacy Python ENV нельзя выдавать за обязательные для текущего Node-first deploy.
