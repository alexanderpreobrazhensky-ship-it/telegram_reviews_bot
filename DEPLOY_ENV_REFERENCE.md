# DEPLOY_ENV_REFERENCE.md

Актуальный практический реестр ENV по результатам полного аудита кода, deploy-контракта и документации.

## Scope и метод
- Проверены runtime-контуры: `app.js`, `src/**`, `public/**`, `Dockerfile`, `.bothost/entrypoint.conf`, `package.json`, `tests/**`.
- Отдельно проверен legacy-контур: `bots/**`, `services/**`, `shared/**` (Python-исторический слой).
- Статусы ниже:
  - `required` — реально обязателен для рабочего production-path (Node-first).
  - `recommended` — не обязателен для старта процесса, но обязателен для полноценного прод-использования.
  - `optional` — имеет рабочий default и не блокирует runtime.
  - `legacy/dead` — относится к legacy-контуру или не влияет на фактический Node runtime.

---

## 1) Node production path (актуальный runtime)

| ENV | Статус | Default | Где используется | Назначение | Нужен для production deploy | Нужен для BotHost deploy | Комментарий |
|---|---|---|---|---|---|---|---|
| `PORT` | required | `3000` (fallback) | `src/infrastructure/config/index.js`, `app.js` | Порт HTTP runtime | Да (порт-контракт) | Да (BotHost передаёт) | Без `PORT` локально берётся `3000`; на BotHost задаётся платформой. |
| `TELEGRAM_CLIENT_BOT_TOKEN` | recommended | `''` | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js`, `app.js` | Client bot webhook + исходящие сообщения | Для полного прод-флоу — да | Рекомендуется как обязательный | Процесс стартует и без него, но клиентские уведомления деградируют. |
| `TELEGRAM_MASTER_BOT_TOKEN` | recommended | `''` | `src/infrastructure/config/index.js`, `src/interfaces/master_bot/index.js`, `src/server/index.js` | Master bot webhook/ответы | Для полного прод-флоу — да | Рекомендуется как обязательный | Без токена ветка master bot нерабочая. |
| `TELEGRAM_INTEGRATION_BOT_TOKEN` | recommended | `''` | `src/infrastructure/config/index.js`, `src/interfaces/integration_bot/index.js` | Integration bot webhook/операторские команды | Для полного прод-флоу — да | Рекомендуется как обязательный | Без токена интеграционный бот недоступен. |
| `MASTER_BOT_ADMIN_IDS` | recommended | `''` | `src/infrastructure/config/index.js`, `src/core/application/masterService.js` | Bootstrap admin-доступа master bot | Сильно рекомендуется | Сильно рекомендуется | Без него не назначается env-driven admin bootstrap. |
| `WEBAPP_URL` | recommended | `https://example.com` | `src/infrastructure/config/index.js`, `src/interfaces/client_bot/index.js` | URL Mini App кнопки в client bot | Да (если используется WebApp) | Да (практически) | Дефолт технический, не production-safe. |
| `DB_FILE_PATH` | recommended | `data/db.json` | `src/infrastructure/db/index.js` | Путь к file DB | Рекомендуется | Рекомендуется | Для устойчивого deploy лучше указывать persistent путь явно. |
| `TELEGRAM_MASTERS_CHAT_ID` | optional | `''` | `src/infrastructure/config/index.js`, `src/server/index.js` | Дубли заявок в общий чат мастеров | Не обязательно | Не обязательно | Активирует masters-chat notifications. |
| `WEBAPP_TELEGRAM_CHANNEL_LINK` | optional | `''` | `src/infrastructure/config/index.js`, `src/server/index.js`, `public/webapp.js` | Ссылка на канал в WebApp | Не обязательно | Не обязательно | Канал не показывается при пустом значении. |
| `WEBAPP_DEDUPE_WINDOW_MS` | optional | `45000` | `src/infrastructure/config/index.js`, `src/server/index.js` | Дедупликация WebApp submit | Нет | Нет | Тюнинг anti-duplicate окна. |
| `NODE_ENV` | optional | `development` | `src/infrastructure/config/index.js` | Режим окружения | Нет | Нет | В коде не влияет на ветвление критических фич. |
| `SCHEDULER_INTERVAL_MS` | optional | `15000` | `src/infrastructure/config/index.js`, `app.js` | Интервал scheduler loop | Нет | Нет | Имеет clamp/валидацию. |
| `SCHEDULER_BATCH_SIZE` | optional | `10` | `src/infrastructure/config/index.js`, `app.js` | Размер batch задач | Нет | Нет | Имеет clamp/валидацию. |
| `SCHEDULER_MAX_ATTEMPTS` | optional | `3` | `src/infrastructure/config/index.js`, `app.js` | Лимит retry задач | Нет | Нет | Имеет clamp/валидацию. |
| `SCHEDULER_STUCK_TIMEOUT_MS` | optional | `300000` | `src/infrastructure/config/index.js`, `app.js` | Recovery stuck processing задач | Нет | Нет | Имеет clamp/валидацию. |
| `FEEDBACK_REQUEST_DELAY_MINUTES` | optional | `5` | `src/infrastructure/config/index.js`, `src/infrastructure/db/index.js` | Отложенная задача фидбека | Нет | Нет | Тюнинг SLA напоминаний. |
| `INTEGRATION_RETRY_MAX` | legacy/dead | `3` | `src/infrastructure/config/index.js` | Задекларированный retry лимит интеграций | Нет | Нет | В Node runtime практически не применяется отдельным worker-пайплайном. |
| `INTEGRATION_RETRY_DELAY_SECONDS` | legacy/dead | `60` | `src/infrastructure/config/index.js` | Задекларированный retry delay | Нет | Нет | Аналогично, декларативно. |
| `DB_URL` | legacy/dead | `postgres://localhost:5432/telegram_reviews` | `src/infrastructure/config/index.js` | Декларация SQL-подключения | Нет | Нет | Фактический runtime работает на file DB. |
| `QUEUE_DRIVER` | legacy/dead | `memory` | `src/infrastructure/config/index.js` | Декларация queue backend | Нет | Нет | Реального внешнего queue driver нет. |
| `ENABLE_INTEGRATION_WORKER` | legacy/dead | `true` | `src/infrastructure/config/index.js` | Feature toggle worker | Нет | Нет | Отдельный worker-процесс отсутствует. |
| `ONE_C_SYNC_ENABLED` | legacy/dead | `false` | `src/infrastructure/config/index.js` | Toggle 1C sync | Нет | Нет | Не гейтит фактические route execution paths. |
| `EMAIL_IMPORT_ENABLED` | legacy/dead | `true` | `src/infrastructure/config/index.js` | Toggle email import | Нет | Нет | Роут email не отключается этим флагом. |
| `ONE_C_WEBHOOK_SECRET` | legacy/dead | `''` | `src/infrastructure/config/index.js` | Секрет webhook 1C | Нет | Нет | В HTTP route не валидируется. |

---

## 2) Integration-related ENV
- Активно влияющие: `TELEGRAM_INTEGRATION_BOT_TOKEN`.
- Технический тюнинг scheduler/inbox: `SCHEDULER_*`, `FEEDBACK_REQUEST_DELAY_MINUTES`.
- Декларативные/legacy: `ONE_C_WEBHOOK_SECRET`, `ONE_C_SYNC_ENABLED`, `ENABLE_INTEGRATION_WORKER`, `INTEGRATION_RETRY_*`, `EMAIL_IMPORT_ENABLED`, `DB_URL`, `QUEUE_DRIVER`.

## 3) Bot-related ENV
- Client bot (Node path): `TELEGRAM_CLIENT_BOT_TOKEN`, `WEBAPP_URL`.
- Master bot (Node path): `TELEGRAM_MASTER_BOT_TOKEN`, `MASTER_BOT_ADMIN_IDS`, `TELEGRAM_MASTERS_CHAT_ID`.
- Integration bot (Node path): `TELEGRAM_INTEGRATION_BOT_TOKEN`.

## 4) Scheduler-related ENV
- `SCHEDULER_INTERVAL_MS`, `SCHEDULER_BATCH_SIZE`, `SCHEDULER_MAX_ATTEMPTS`, `SCHEDULER_STUCK_TIMEOUT_MS`, `FEEDBACK_REQUEST_DELAY_MINUTES`.

## 5) Reporting-related ENV
- Прямых отдельных ENV для Node reporting-эндпоинтов не найдено.

---

## 6) Legacy Python contour ENV (не обязателен для Node production path)
Эти переменные реально читаются в `bots/**`, `services/**`, `shared/**`, но относятся к историческому/альтернативному контуру:

- Токены/алиасы: `CLIENT_TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`, `TELEGRAM_BOT_TOKEN_CLIENT`.
- Webhook/WebApp: `WEBHOOK_URL`, `PUBLIC_BASE_URL`, `DOMAIN`, `WEBAPP_PATH`, `CLIENT_WEBAPP_URL`, `CLIENT_WEBAPP_ENABLED`, `WEBAPP_ENABLED`, `CLIENT_WEBAPP_SESSION_SECRET`, `CLIENT_WEBAPP_INITDATA_MAX_AGE_SECONDS`, `CLIENT_WEBAPP_TEST_MODE`, `BOT_PATH_SECRET`.
- Режимы запуска: `CLIENT_BOT_MODE`, `CLIENT_RUN_MODE`, `RUN_MODE`, `CLIENT_SERVICE_PORT`, `CLIENT_SERVICE_HOST`.
- Доступ/админы/чаты: `CLIENT_ADMIN_IDS`, `CLIENT_MASTERS_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`, `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTER_IDS`, `CLIENT_CHAT_ID`, `CLIENT_MASTER_CHAT_MODE`, `MASTER_CHAT_MODE`, `CLIENT_NOTIFY_MODE`, `MASTER_USERNAMES`, `REPORT_CHAT_IDS`, `SUPERADMIN_ID`.
- Прочее функциональное: `CLIENT_CHANNEL_ID`, `CLIENT_POST_TARGET_ID`, `CLIENT_POST_CHAT_ID`, `CLIENT_BOT_USERNAME`, `TELEGRAM_BOT_USERNAME`, `BOT_USERNAME`, `TIMEZONE`, `LIRA_PHONE`, `LIRA_ADDRESS`, `LIRA_MAP_URL`, `SHOW_ROUTE_IMAGE`, `CLIENT_SHOW_REGLAMENT_PHRASE`, `SHOW_REGLAMENT_PHRASE`, `PIN_TEMPLATE_VERSION`, `CLIENT_AUTO_PIN_ON_START`, `CLIENT_AUTO_PIN_ON_DEPLOY`, `AUTO_PIN_ON_START`, `AUTO_PIN_ON_DEPLOY`, `CLIENT_ACTIVE_TICKET_TTL_HOURS`, `AI_FALLBACK_THRESHOLD`, `AI_FALLBACK_TTL_SECONDS`, `AI_FALLBACK_WINDOW_SECONDS`, `ROUTE_URL`.
- Legacy persistence/integration: `DATABASE_URL`, `POSTGRES_URL`, `POSTGRESQL_URL`, `CLIENTS_REGISTRY_PATH`, `CLIENTS_REGISTRY_LOCK_TIMEOUT_SECONDS`, `CLIENT_GITHUB_TOKEN`, `GITHUB_TOKEN`, `CLIENT_GITHUB_REPO`, `GITHUB_REPO`, `CLIENT_GITHUB_BRANCH`, `GITHUB_BRANCH`, `CLIENT_TG_TIMEOUT_SECONDS`, `CLIENT_TG_RETRY_MAX`, `CLIENT_TG_RETRY_BASE_SLEEP_SECONDS`, `CLIENT_TG_QUEUE_ENABLED`.

Статус legacy-контура: `legacy/dead` для текущего Node-first deploy; применим только если осознанно запускается старый Python стек.

---

## 7) Минимальные наборы ENV

### 7.1 Минимум для рабочего production deploy (Node-first, полный функционал)
```env
PORT=3000
TELEGRAM_CLIENT_BOT_TOKEN=<token>
TELEGRAM_MASTER_BOT_TOKEN=<token>
TELEGRAM_INTEGRATION_BOT_TOKEN=<token>
MASTER_BOT_ADMIN_IDS=123456789
WEBAPP_URL=https://<your-domain>
DB_FILE_PATH=data/db.json
```

### 7.2 Минимум именно для BotHost
```env
# PORT задаётся BotHost автоматически
TELEGRAM_CLIENT_BOT_TOKEN=<token>
TELEGRAM_MASTER_BOT_TOKEN=<token>
TELEGRAM_INTEGRATION_BOT_TOKEN=<token>
MASTER_BOT_ADMIN_IDS=123456789
WEBAPP_URL=https://<login>.bothost.ru
DB_FILE_PATH=data/db.json
```

### 7.3 ENV для мастер-чата/канала/доступа (если фича нужна)
```env
TELEGRAM_MASTERS_CHAT_ID=-1001234567890
WEBAPP_TELEGRAM_CHANNEL_LINK=https://t.me/<channel>
MASTER_BOT_ADMIN_IDS=123456789,987654321
```

### 7.4 Рекомендуемый расширенный пример ручного заполнения
```env
PORT=3000
NODE_ENV=production

TELEGRAM_CLIENT_BOT_TOKEN=<token>
TELEGRAM_MASTER_BOT_TOKEN=<token>
TELEGRAM_INTEGRATION_BOT_TOKEN=<token>
MASTER_BOT_ADMIN_IDS=123456789
TELEGRAM_MASTERS_CHAT_ID=-1001234567890

WEBAPP_URL=https://<login>.bothost.ru
WEBAPP_TELEGRAM_CHANNEL_LINK=https://t.me/<channel>
WEBAPP_DEDUPE_WINDOW_MS=45000

DB_FILE_PATH=data/db.json

SCHEDULER_INTERVAL_MS=15000
SCHEDULER_BATCH_SIZE=10
SCHEDULER_MAX_ATTEMPTS=3
SCHEDULER_STUCK_TIMEOUT_MS=300000
FEEDBACK_REQUEST_DELAY_MINUTES=5
```

---

## 8) Drift notes (docs vs code)
- `README.md` частично относит часть legacy/declarative ENV к runtime optional, хотя часть из них в Node path фактически не влияет.
- `PROJECT_AUDIT.md` в целом ближе к фактическому состоянию, но содержит исторические формулировки и может устаревать по мере изменений кода.

