# PROJECT_AUDIT.md

## 1. Контекст и цель аудита
Этот аудит выполнен как единый источник правды по текущему состоянию репозитория перед подготовкой отдельного ТЗ на исправления и доведение до деплоя. Проект подтверждён как **Node.js-first** по production-контракту: runtime Node.js, entrypoint `app.js`, manifest `package.json`, целевая платформа BotHost.

---

## 2. Общая структура репозитория

### 2.1 Корневая структура (ключевые зоны)
- Runtime/deploy: `app.js`, `package.json`, `package-lock.json`, `Dockerfile`, `.bothost/entrypoint.conf`.
- Основной код Node: `src/`.
- Frontend WebApp: `public/`.
- Тесты Node: `tests/node/`.
- Legacy-тесты Python (отключены): `tests/test_*.py`.
- Данные/персистентность: `data/` (`db.json` создаётся runtime-ом).
- Legacy/исторический контур: `bots/`, `services/`, `shared/`, `requirements.txt`, `legacy/index.js`.
- Документация/аудиты: `README.md`, `PROJECT_AUDIT.md`, `audit/*`.

### 2.2 Production-critical файлы
- `app.js` — фактический bootstrap процесса, создание HTTP-сервера + запуск scheduler.
- `src/server/index.js` — HTTP routing: health, webhooks, client/integration/reporting API, static/WebApp routes.
- `src/infrastructure/config/index.js` — loadConfig и env parsing.
- `src/infrastructure/db/index.js` — file-based persistence и бизнес-операции.
- `src/infrastructure/scheduler/index.js` — interval scheduler и retry/stuck механика.
- `src/interfaces/*` — webhook handlers трёх ботов.
- `public/*` — клиентский WebApp.
- `package.json`/`package-lock.json` — Node manifest + lockfile.
- `.bothost/entrypoint.conf`, `Dockerfile` — deploy/runtime указания.

### 2.3 Служебные файлы
- `.github/workflows/tests.yml` — CI на `npm ci` + `npm test`.
- `audit/*` — старые аудиторские артефакты, не должны считаться актуальным runtime source-of-truth.

### 2.4 Legacy/подозрительные артефакты
- `bots/`, `services/`, `shared/`, `requirements.txt` — Python/гибридный исторический слой, не используемый production Node path.
- `legacy/index.js` — shim с warning и редиректом в `app.js`.
- `src/interfaces/webapp/routes.js`, `src/interfaces/webapp/state.js` — вспомогательный skeleton, напрямую в runtime роутере не участвует.

---

## 3. Entrypoints и startup chain

### 3.1 Основной production entrypoint (de-facto)
- **`app.js`** — подтверждён в `package.json.main`, Docker CMD и BotHost `main_file`.

### 3.2 Secondary entrypoints
- `npm start` → `node app.js`.
- `legacy/index.js` → лог предупреждения + `require('../app')` (не основной путь).

### 3.3 Фактическая цепочка запуска
1. `bootstrap()` в `app.js`.
2. `loadConfig()` читает env.
3. `createServer({ config, logger })` создаёт HTTP server.
4. Регистрируются webhook routes из `client_bot`, `master_bot`, `integration_bot` интерфейсов.
5. Инициализируется scheduler (`createScheduler`) с параметрами из config.
6. `server.listen(config.port)`.
7. После успешного listen запускается `scheduler.start()`.
8. На `server.close` вызывается `scheduler.stop()`.

### 3.4 Где что стартует
- HTTP server: `src/server/index.js`.
- Webhook handlers: `src/interfaces/client_bot`, `master_bot`, `integration_bot`.
- Scheduler: создаётся в `app.js`, loop — `src/infrastructure/scheduler/index.js`.
- Config reading: `src/infrastructure/config/index.js`.

### 3.5 Сверка code vs Dockerfile vs BotHost config vs docs
- `app.js` как entrypoint: **согласовано** (`package.json`, Dockerfile, `.bothost/entrypoint.conf`, README).
- Branch `main`: отражён в `.bothost/entrypoint.conf` и README.
- Node runtime narrative: согласован в README и CI (`npm ci`, `npm test`).

---

## 4. Runtime model
- Модель: **single-process Node.js**.
- В одном процессе живут одновременно:
  - HTTP API + static/WebApp routes,
  - Telegram webhooks (3 бота),
  - scheduler loop.
- Queue broker отсутствует; retry и scheduling опираются на file DB.
- Persistence: JSON file на диске (`DB_FILE_PATH` или `data/db.json`).

### Runtime assumptions
- Процесс один, без горизонтального масштабирования по умолчанию.
- Доступ к файлу БД локальный и консистентный в рамках одного процесса.
- Фоновые задачи обрабатываются этим же процессом, отдельного worker-процесса нет.

### Ограничения модели
- Нет distributed lock и coordination для multi-instance.
- Нет transactional/ACID гарантий уровня SQL.
- Перезапуск процесса/падения влияют и на API, и на scheduler одновременно.

---

## 5. Полный ENV audit

### 5.1 Runtime-active env (Node path)
| ENV | Статус | Default | Где читается | Назначение | Критичность deploy/runtime |
|---|---|---|---|---|---|
| `PORT` | required (prod) | `3000` | `src/infrastructure/config/index.js` | Порт HTTP-сервера | Критично для deploy и runtime |
| `NODE_ENV` | recommended | `development` | `src/infrastructure/config/index.js` | Маркер окружения (в `/health`) | Средняя |
| `TELEGRAM_CLIENT_BOT_TOKEN` | required (prod) | `''` | `src/infrastructure/config/index.js`, `app.js`, `client/master handlers` | Отправка сообщений client bot / уточнения | Высокая |
| `TELEGRAM_MASTER_BOT_TOKEN` | required (prod) | `''` | `src/infrastructure/config/index.js`, `client_bot` quality notify | Отправка уведомлений в master bot | Высокая |
| `TELEGRAM_INTEGRATION_BOT_TOKEN` | required (prod) | `''` | `src/infrastructure/config/index.js` | Интеграционный бот (на уровне webhook route и config) | Средняя/высокая |
| `WEBAPP_URL` | required (фактически для Mini App UX) | `https://example.com` | `src/infrastructure/config/index.js`, `client_bot /start` | URL WebApp-кнопки в Telegram | Высокая для бизнес-сценария |
| `DB_FILE_PATH` | recommended | `data/db.json` | `src/infrastructure/db/index.js` | Путь к JSON БД | Высокая |
| `SCHEDULER_INTERVAL_MS` | optional | `15000` | `config` → `app.js` scheduler | Интервал loop | Средняя |
| `SCHEDULER_BATCH_SIZE` | optional | `10` | `config` → scheduler | Batch due tasks | Средняя |
| `SCHEDULER_MAX_ATTEMPTS` | optional | `3` | `config` → scheduler | Retry лимит фоновых задач | Средняя |
| `SCHEDULER_STUCK_TIMEOUT_MS` | optional | `300000` | `config` → scheduler/db | Recovery зависших processing задач | Средняя |
| `FEEDBACK_REQUEST_DELAY_MINUTES` | optional | `5` | `config`, `db.updateRequestStatus` | Отложенный запрос фидбека после `processed` | Средняя |
| `INTEGRATION_RETRY_MAX` | optional (documented) | `3` | `config` | Задекларирован лимит retry интеграций | Низкая (де-факто не применяется) |
| `INTEGRATION_RETRY_DELAY_SECONDS` | optional (documented) | `60` | `config` | Задекларирован delay retry интеграций | Низкая (де-факто не применяется) |

### 5.2 Documented/legacy/dead env
| ENV | Категория | Комментарий |
|---|---|---|
| `DB_URL` | documented-only / dead for runtime | Читается в config, но storage фактически file JSON, не Postgres driver. |
| `QUEUE_DRIVER` | documented-only / dead | Читается в config, но отдельный queue backend не используется. |
| `ONE_C_WEBHOOK_SECRET` | documented-only / dead | Читается в config, но в HTTP routes не валидируется. |
| `ENABLE_INTEGRATION_WORKER` | documented-only / dead | Включатель worker не влияет на фактический runtime (отдельного worker нет). |
| `ONE_C_SYNC_ENABLED` | documented-only / dead | Читается, но one_c поток работает как skeleton через route + placeholder. |
| `EMAIL_IMPORT_ENABLED` | documented-only / dead | Читается, но email ingest route не gated этим флагом. |

### 5.3 Legacy env (Python contour, не production path)
Обнаружены в `bots/client_bot/*` и `services/client_bot_service/*`: `CLIENT_TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, `BOT_API_TOKEN`, `API_TOKEN`, `BOT_TOKEN`, `TOKEN`, `CLIENT_SERVICE_PORT`, `CLIENT_WEBAPP_URL`, `WEBAPP_PATH`, `CLIENT_MASTERS_CHAT_ID`, `CLIENT_MASTER_CHAT_ID`, `CLIENT_MASTER_USER_IDS`, `CLIENT_MASTER_IDS`, `CLIENT_CHAT_ID`, `TELEGRAM_BOT_USERNAME`, `REPORT_CHAT_IDS`.

### 5.4 Спец-проверки из ТЗ
- `PORT`: слушается через `config.port` (из `process.env.PORT`, fallback 3000).
- `WEBAPP_URL`: реально используется в client bot (`/start`, quick flow сообщения).
- `DB_FILE_PATH`: реально используется для DB path.
- `NODE_ENV`: отражается в health payload.
- Telegram tokens: реально читаются и используются для исходящих Telegram API вызовов.
- Scheduler env: реально влияет на scheduler loop.
- Integration env: в основном декларативные, не все влияют на фактический поток.

---

## 6. Полный inventory маршрутов

### 6.1 Health
- `GET /health` — health-check + `env`.

### 6.2 Telegram webhooks
- `POST /telegram/client_bot/webhook` — обработка клиентского бота.
- `POST /telegram/master_bot/webhook` — обработка мастер/менеджер бота.
- `POST /telegram/integration_bot/webhook` — команды интеграционного бота.

### 6.3 Client API
- `POST /api/client/requests/service`
- `POST /api/client/requests/parts`
- `POST /api/client/requests/consultation`
- `POST /api/client/requests/warranty`
- `POST /api/client/requests/data-change`
- `GET /api/client/requests`
- `GET /api/client/recommendations`
- `POST /api/client/recommendations/:id/interest`

### 6.4 Integration API
- `POST /api/integrations/email`
- `POST /api/integrations/manual`
- `POST /api/integrations/one-c/:entityType` (`client|vehicle|visit|recommendation`)
- `GET /api/integrations/events`
- `GET /api/integrations/events/:id`
- `POST /api/integrations/events/:id/retry`

### 6.5 Reporting API
- `GET /api/reports/summary`
- `GET /api/reports/requests`
- `GET /api/reports/feedback`
- `GET /api/reports/quality`
- `GET /api/reports/masters`
- `GET /api/reports/sources`
- `GET /api/reports/recommendations`
- `POST /api/reports/snapshots`
- `GET /api/reports/snapshots`
- `GET /api/reports/snapshots/:id`

### 6.6 WebApp/static
- `GET /`
- `GET /requests`
- `GET /recommendations`
- `GET /forms/service-request`
- `GET /forms/parts-request`
- `GET /forms/consultation`
- `GET /forms/warranty-request`
- `GET /forms/data-change-request`
- `GET /styles.css`
- `GET /webapp.js`

---

## 7. Bot audit

### 7.1 client_bot
Реально реализовано:
- `/start`: приветствие + inline WebApp button (`WEBAPP_URL`) + reply-клавиатура быстрых сценариев.
- Быстрые обращения из чата (через state machine `fullName -> phone`).
- Сохранение request + communication event.
- Приём фидбека формата `1..5 [comment]`.
- При низкой оценке создаётся quality case и отправляются уведомления мастеру/менеджеру (если найдены staff chat ids).

Риски/пробелы:
- In-memory sessions (`Map`) теряются при рестарте процесса.
- Нет валидации телефона в quick flow.
- Ошибки Telegram API подавляются (`catch(() => {})`), нет наблюдаемой доставки/alerts.

### 7.2 master_bot
Реально реализовано:
- `/start`, выдача роли и базового меню.
- Списки заявок по статусам (`Новые заявки`, `В работе`).
- Поиск (`Поиск`, `/search`).
- Карточки клиента/заявки (`/client`, `/request`).
- Изменение статуса заявки (`/set_status`), комментарии, client notes, запрос уточнения клиенту.
- Отчётные команды (`/report_week|month|quarter|stats`) с role check (`manager/admin`).
- Quality cases: list/card/status/comment.

Ограничения:
- Role model упрощённая: новый staff user по умолчанию создаётся как `master`.
- Нет внешней authz/policy системы кроме локальной проверки роли.

### 7.3 integration_bot
Реально реализовано:
- `/start`, `/events`, `/failed`, `/pending`, `/stats`, `/event <id>`, `/retry <id>`, `/ignore <id>`.
- Работает поверх той же integration events таблицы в file DB.

Skeleton/ограничения:
- Это operator-интерфейс к текущему integration state, без изоляции прав и без отдельного worker-процесса.

---

## 8. WebApp audit

### 8.1 Структура `public/`
- `index.html` — контейнер + навигация + подключение `webapp.js`.
- `webapp.js` — SPA-логика рендеринга форм/списков/рекомендаций.
- `styles.css` — базовые стили.

### 8.2 Страницы и формы
- Формы: service, parts, consultation, warranty, data-change.
- Разделы: `Мои обращения`, `Рекомендации`.
- Главная: приветственный текст.

### 8.3 API usage
- Submit форм в `/api/client/requests/*`.
- Загрузка списка обращений через `/api/client/requests?phone=...`.
- Загрузка рекомендаций через `/api/client/recommendations`.
- Подтверждение интереса: `POST /api/client/recommendations/:id/interest`.

### 8.4 Flow открытия из client_bot
- Кнопка WebApp формируется в `/start` client bot и использует `config.webAppUrl` (`WEBAPP_URL`).

### 8.5 Готовность к Telegram Mini App
- Базовый HTTPS URL open-flow есть.
- Специфическая Telegram Mini App интеграция (theme params, viewport адаптация, init data verification) отсутствует.
- Требуется ручная проверка внутри Telegram-клиентов.

### 8.6 Theme compatibility
- Используются hardcoded цвета (`#f5f7fb`, `#fff`, `#1155cc`, `#eef3ff`, `#1f7a1f`).
- Нет интеграции с Telegram theme variables.
- Риск визуальных проблем в dark mode.

---

## 9. Persistence audit
- Драйвер: JSON file storage (`src/infrastructure/db/index.js`).
- Путь: `DB_FILE_PATH` или `data/db.json`.
- Коллекции: clients, vehicles, visits, requests, communicationEvents, integrationEvents, integrationEventLogs, recommendations, staffUsers, requestStatusHistory, requestInternalComments, clientInternalNotes, masterActions, qualityCases, qualityCaseComments, feedback, tasks, reportSnapshots.

### Поведение при пустой/битой БД
- При отсутствии файла: auto-init структуры.
- При ошибке чтения JSON: fallback на initial store (фактически «восстановление через reset структуры»).
- При schema drift: `ensureStore()` дозаполняет отсутствующие ключи.

### Риски file-based persistence
- Нет блокировок на multi-process запись.
- Риск потери/порчи при конкурентной записи или аварийном прерывании.
- Рост файла влияет на latency операций read-modify-write.

### Масштабирование / MVP пригодность
- Для MVP/single-node — допустимо.
- Для production growth потребуется переход на внешнюю БД и очередь.

---

## 10. Scheduler / task audit

### 10.1 Task types
- Реально создаётся автоматически: `feedback_request` (при переводе заявки в `processed`).
- В handlers зарегистрированы также `quality_followup`, `recommendation_reminder`, `maintenance_reminder`, но обработчики пустые (`async () => {}`) и автогенерация этих задач не обнаружена.

### 10.2 Retry и stuck recovery
- `claimDueTasks`: переводит due `scheduled` → `processing`, повышает `attemptCount`.
- `failTask`: возвращает в `scheduled` либо в `failed` по `maxAttempts`, с backoff по минутам.
- Stuck recovery: processing-задачи дольше `stuckTimeoutMs` возвращаются в `scheduled`.

### 10.3 Гарантии
- At-least-once обработка.
- Exactly-once отсутствует.
- Нет кросс-процессной координации.

### 10.4 Риски для BotHost
- При рестартах/деплое background loop прерывается.
- При горизонтальном scale (если включить) возможны гонки по file DB.

---

## 11. Integration layer audit

### 11.1 Source systems и event types
- Source systems: `email`, `manual_import`, `one_c`, `system`.
- Event types: email receive, manual import/sync, one_c sync варианты.

### 11.2 Pipeline
- Receive event → normalize payload → process branch:
  - email/manual_request_import: создаёт/обновляет client/vehicle/request + communication event;
  - one_c: нормализуется и помечается `ignored` (skeleton path).

### 11.3 Retry flow
- Manual retry через API (`/api/integrations/events/:id/retry`) и integration_bot (`/retry`).
- Автоматический отдельный integration worker отсутствует.

### 11.4 Working paths vs skeleton
- Working: email/manual import базового запроса.
- Skeleton: one_c полноценная синхронизация сущностей (client/vehicle/visit/recommendation) не доведена до applied sync.

### 11.5 one_c readiness
- Частичная готовность (ingest/normalize/logging).
- Не готово как полнофункциональный production sync adapter.

---

## 12. Reporting / analytics audit

### Что реализовано
- Метрики по requests, feedback, quality, masters, sources, recommendations, timing.
- Management summary + текстовая сводка.
- Snapshot механизм (`create/list/get`).

### Ограничения данных
- В коде явно зашито предупреждение о неполноте при пустых `visits`.
- При отсутствии one_c событий аналитика ограничивается платформенными данными.

### Что реально работает
- Все reporting endpoints доступны и покрыты Node-тестами.

---

## 13. Tests audit

### 13.1 Актуальные тесты
- `tests/node/*.test.js` — активный контур, запускается через `npm test`.
- Покрытие: routes, webhook flows, client/master/integration сценарии, reporting, hardening, scheduler, production path checks.

### 13.2 Legacy тесты
- `tests/test_*.py` — помечены `@unittest.skip`, исторические placeholders.

### 13.3 Пробелы покрытия
- Нет e2e Telegram Mini App внутри реального Telegram-клиента.
- Нет инфраструктурных e2e проверок webhook + SSL на BotHost.
- Нет нагрузочных тестов file DB/scheduler гонок.

### 13.4 Потенциально вводящие в заблуждение моменты
- Наличие Python-тестов и Python-кода может создать ложное впечатление dual-runtime production, хотя текущий контракт Node-first.

---

## 14. Documentation audit

### Проверено
- `README.md` соответствует Node-first контракту и текущим route/env нарративам.
- `PROJECT_AUDIT.md` обновлён как единый audit source-of-truth.
- Deploy hints в README синхронизированы с BotHost-конфигом.

### Найденный doc/code drift
1. В README env-переменные интеграционного worker-профиля перечислены как optional runtime, но в коде часть из них фактически не влияет на поведение (`ENABLE_INTEGRATION_WORKER`, `ONE_C_SYNC_ENABLED`, `EMAIL_IMPORT_ENABLED`, `ONE_C_WEBHOOK_SECRET`, `DB_URL`, `QUEUE_DRIVER`).
2. В репозитории остаются Python docs/traces (`bots/client_bot/README.md`, legacy env aliases), которые не соответствуют production path.

---

## 15. Deploy readiness audit

### 15.1 Обязательные условия запуска
- `npm ci` должен выполняться.
- `package-lock.json` должен быть консистентен с `package.json`.
- `node app.js` как entrypoint.
- Должны быть заданы токены Telegram-ботов.
- `WEBAPP_URL` должен указывать на рабочий HTTPS домен.

### 15.2 Спец-проверки из ТЗ (подтверждение)
1. `package-lock.json` корректен: lockfile v3, имя совпадает, `npm ci` проходит.
2. `npm ci` работает в текущем состоянии.
3. `npm-shrinkwrap.json` отсутствует и не мешает.
4. Runtime слушает `process.env.PORT` (через config), не хардкодит 8000.
5. `Dockerfile` соответствует Node-first (`node app.js`, `npm ci`).
6. `.bothost/entrypoint.conf` соответствует Node-first (`main_file=app.js`, `branch=main`).
7. `README.md` в целом согласован с кодом (с оговоркой по documented-only env).
8. WebApp готов к базовому запуску как Mini App URL, но без глубокой Telegram theme/init-data интеграции.

### 15.3 Что проверить вручную после деплоя
- `/health`, `/`, `/styles.css`, `/webapp.js`.
- Все 3 webhook endpoint-а с реальными Telegram bot tokens.
- `/start` сценарии всех ботов.
- WebApp формы и list-flow в реальном Telegram клиенте.
- HTTPS/certificate отсутствие browser warnings.

---

## 16. BotHost-specific audit

### Подтверждённые BotHost нюансы
- Случайный дефолтный домен BotHost — риск нестабильности и drift.
- Предпочтительный короткий домен: `https://вашлогин.bothost.ru`.
- Этот же домен нужно использовать консистентно для:
  - `WEBAPP_URL`,
  - webhook URLs,
  - BotFather menu button.

### Ограничения runtime на BotHost
- Процессовая модель без отдельного worker предполагает, что API+scheduler делят один process budget.
- Нужно учитывать restart behavior при update-from-git.

---

## 17. Legacy cleanup candidates (следующий этап)
1. `bots/`, `services/`, `shared/`, `requirements.txt` — Python legacy слой, не нужный для Node deploy.
2. `legacy/index.js` — можно оставить как compatibility shim либо удалить после окончательной миграции.
3. `audit/*` старых форматов — оставить как архив, но не как operational doc source.
4. Documented-only env в README/config — либо реализовать, либо убрать из публичного deploy narrative.

---

## 18. Known issues / limitations
- File DB и single-process scheduler ограничивают масштабирование.
- one_c integration путь преимущественно skeleton (`ignored` после normalize).
- Отсутствует строгая доставка Telegram сообщений (ошибки подавляются).
- In-memory сессии ботов теряются при рестарте.
- Theme/Telegram Mini App UX интеграция базовая, без адаптации к Telegram theme variables.
- Legacy Python следы остаются и могут запутывать при эксплуатации.

---

## 19. Final conclusion

### Готовность к MVP deploy
**Да, условно готов к MVP deploy** на BotHost как Node-first сервис при выполнении обязательных условий окружения.

### Условия, при которых deploy допустим
- Валидные Telegram tokens заданы.
- `WEBAPP_URL` установлен на `https://вашлогин.bothost.ru`.
- HTTPS сертификат валиден.
- Запуск в single-instance режиме (или без конкурентной записи в одну file DB).

### Что блокирует полноценный production-scale deploy
- Отсутствие промышленной БД и очереди.
- one_c не завершён как полноценный sync path.
- Отсутствие e2e инфраструктурного контроля Telegram/SSL/BotHost runtime.

### Что желательно исправить до запуска
1. Уточнить и почистить env-контракт (убрать/реализовать dead env).
2. Явно зафиксировать operational limits single-process + file DB в README/runbook.
3. Провести ручной Mini App UX smoke в Telegram (light/dark).

### Что можно отложить на после запуска
- Полный рефактор интеграционного worker-пайплайна.
- Миграция на внешнюю БД/queue при росте нагрузки.
- Полная зачистка legacy Python следов (после стабилизации MVP).
