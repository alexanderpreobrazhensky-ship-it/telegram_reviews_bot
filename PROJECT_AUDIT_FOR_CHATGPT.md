# PROJECT AUDIT FOR CHATGPT

## 1. Краткое описание проекта
- Репозиторий в текущем состоянии — **Node-first платформа** для обработки клиентских обращений автосервиса «Лира», с несколькими ботами (client/master/integration), WebApp, отчётами, email intake и AI control plane.
- Есть также **legacy Python-бот** в `bots/client_bot/main.py`, но он не выглядит основным production entrypoint для текущей архитектуры.
- Важное расхождение с формулировкой задачи: в кодовой базе **не найден отдельный Telegram-бот отзывов** с сущностями `reviews`, `review_analyses`, `access_users` и сценариями «Добавить отзыв / ИИ Анализ / Ответ на отзыв / Жалоба на отзыв».

## 2. Стек и запуск
- Node.js runtime: `app.js` -> `src/server/index.js`.
- Инфраструктура: собственный HTTP router, SQLite-first persistence слой, отдельные интерфейсные модули для telegram/max.
- Python присутствует как legacy-контур (`bots/client_bot/main.py`, Flask + psycopg + requests).
- Python dependencies: `requirements.txt` в корне и `bots/client_bot/requirements.txt`.
- Node dependencies: `package.json`.

## 3. Структура файлов
Ключевые области:
- `app.js` — старт HTTP runtime.
- `src/server/index.js` — сервер, регистрация маршрутов, rate limiting, диагностика.
- `src/interfaces/master_bot/index.js` — основной master bot (webhook, callbacks, меню, доступы, AI, отчёты).
- `src/interfaces/client_bot/index.js` — client bot сценарии.
- `src/interfaces/integration_bot/index.js` — integration bot.
- `src/infrastructure/config/index.js` — env-конфиг.
- `src/infrastructure/db/*` — persistence слой.
- `public/*` — webapp.
- `bots/client_bot/main.py` — legacy Python/Flask bot.

## 4. Точка входа и webhook
- Фактическая production-точка входа: `app.js` + `src/server/index.js`.
- Telegram webhook routes (Node):
  - `POST /telegram/client_bot/webhook`
  - `POST /telegram/master_bot/webhook`
  - `POST /telegram/integration_bot/webhook`
- Также есть MAX webhook routes.
- В legacy Python есть собственная Flask-реализация webhook-механики, но это отдельный контур.

## 5. Telegram handlers
### Node master bot
- Центральный обработчик: `handleMasterWebhook(...)`.
- Входящие апдейты нормализуются через `extractIncomingEvent(...)`.
- Обработка message/callback идет через ветвления по `text` и `callback_data`.
- Меню callback-driven (inline keyboard-first).

### Что найдено / не найдено по требуемым командам
- Найдено: `/start`, `/help`, `/whoami`, `/search`, `/request`, `/set_status`, `/comment`, `/ask_client`, `/access_*`, `/diagnostics`, `/logs`, `/ai_*`.
- Не найдено как отдельные реализованные команды/ветки в текущем Node master bot:
  - `/myid`
  - «➕ Добавить отзыв»
  - «🧠 ИИ Анализ» (в терминах анализа отзывов)
  - «✍️ Ответ на отзыв по ID»
  - «⚠️ Жалоба на отзыв по ID»
  - «🔍 Поиск отзывов»
  - «📊 Недельный отчёт» (есть отчёты по периодам, но не отдельная кнопка именно так)
  - «📤 Экспорт CSV» (есть экспорт в разделе `Отчёты`)

## 6. Меню и кнопки
### Фактическое главное меню (master bot)
- `Новые заявки` -> `menu:new_requests`
- `В работе` -> `menu:in_progress`
- `Архив` -> `menu:archive`
- `Поиск` -> `menu:search`
- `Quality Cases` -> `menu:quality_cases`
- `Инструкция` -> `menu:instruction`
- Для admin: `Диагностика`, `Логи`, `AI`, `Отчёты`
- Для manager/admin: `Доступы`

### AI меню
- Отдельная inline-клавиатура (`buildAiMenuKeyboard`) и callback-команды `admin:ai:*`.

### Reports меню
- Типы: summary/funnel/sources/rejections/warranty/stuck/existing_new/t_business.
- Есть кнопка `Экспорт` внутри report menu.

## 7. Состояния пользователя
- Node master bot: in-memory `sessions = new Map()`.
- В сессии хранятся `screen`, `backAction`, `step`, доп.поля (например, reportType/reportPeriod).
- Примеры шагов: `search_query`, `logs_filter`, AI input states.
- Очистка/переключение состояния — через `updateSession(...)` при смене экрана/действия.

## 8. Система доступов
- В Node доступ определяется ролью actor (`master/manager/admin`).
- Проверки: `canUseReports`, `canManageAccess`, `isAdmin`.
- В master bot есть команды `access_grant`, `access_revoke`, `access_list` и раздел `Доступы`.
- `SUPERADMIN_ID` и функция `can_use_bot()` в Node-контуре **не найдены**.
- `SUPERADMIN_ID` найден только в legacy Python (`bots/client_bot/main.py`, bootstrap admin IDs из env).

## 9. База данных
### Фактический runtime (Node)
- Основная persistence-модель ориентирована на заявки (`requests`) и связанные сущности (events, communications, analytics, tasks, meta и т.д.) в SQLite-first слое.

### PostgreSQL
- В legacy Python есть `db_connect()` через `DATABASE_URL`/`POSTGRES_URL`/`POSTGRESQL_URL` и таблицы настроек:
  - `public.client_bot_settings`
  - `public.settings`

### Таблицы из задачи
- `reviews` — не найдено в актуальном Node-коде.
- `review_analyses` — не найдено.
- `access_users` — не найдено.
- `settings` — есть в legacy Python (`public.settings` как key/value для core settings).
- Поле `review_analyses.input_json` — не найдено (следовательно, место для ошибки `null value in column "input_json"` в этом репозитории не идентифицировано).

## 10. Отзывы
- Полноценный lifecycle «отзыва» (ручное добавление / по ссылке / хранение в `reviews`) в текущем коде не найден.
- Найденный домен проекта — lifecycle **заявок клиентов**, а не отзывов.

## 11. Парсинг отзывов по ссылке
- `detect_platform`, `fetch_url`, `parse_2gis_review`, `parse_yandex_review` — в репозитории не найдены.
- Сценарий дозапроса недостающих полей для отзыва — не найден.

## 12. AI-интеграции
- AI-контур в Node: `src/infrastructure/ai/*` + интеграция в master bot.
- Поддерживаются провайдеры и fallback-модель (по env и runtime override), включая OpenAI/DeepSeek/Gemini (по README/env-контракту и AI config resolution).
- Доступны:
  - AI status
  - AI diagnostics
  - AI logs
  - AI runtime switch
- Это **инфраструктурный AI control plane**, а не модуль «анализа отзывов по ID».

## 13. Анализ отзывов
- Не найден как отдельная бизнес-функция по сущности review.
- Есть AI-диагностика инфраструктуры и AI-логирование.

## 14. Ответы и жалобы на отзывы
- Отдельные функции «ответ на отзыв по ID» и «жалоба на отзыв по ID» не найдены.

## 15. Недельный отчёт
- Есть управленческий reporting контур в master bot, выбор периода (`today`, `7d`, `30d`, `month`, `quarter`, `all_time`).
- Отдельной hardcoded кнопки/команды «Недельный отчёт» не найдено, но `7d` покрывает аналогичный период.

## 16. Экспорт CSV
- Экспорт реализован в reporting-контуре master bot (кнопка `Экспорт` в разделе отчётов).
- Экспорт относится к отчётным данным заявок, не к отзывам.
- Требует ручной проверки формата CSV, кодировки и набора полей в соответствующих report/export методах инфраструктуры.

## 17. Настройки
- Настройки в Node: env + runtime AI settings + meta/persistence.
- Настройки в legacy Python: key/value через `public.client_bot_settings` и `public.settings`.
- Доступ к admin-настройкам ограничен role checks.

## 18. Логирование и самодиагностика
- Node: структурное логирование + системная диагностика в master bot (`menu:diagnostics`, `/diagnostics`, AI diagnostics).
- Есть short/detailed diagnostics, проверка конфигурации, роутов, db runtime, AI состояния.
- Legacy Python тоже логирует, но это другой контур.

## 19. Railway / deployment
- Для текущего runtime нужны проверка `Dockerfile`, `.bothost/entrypoint.conf`, env из README_ENV.
- Отдельные `Procfile`/`runtime.txt` в корне не обнаружены.
- Порт и host управляются Node server конфигом и env.

## 20. Переменные окружения
- Основной список — `readme/README_ENV.md`.
- Ключевые группы: Telegram, MAX, AI, scheduler, email intake, internal/admin.
- Legacy Python использует отдельные env-переменные для Flask/бота/Postgres.

## 21. Найденные проблемы
### Критичные
1) **Несоответствие целевого ТЗ и фактической кодовой базы**.
- Файлы: `src/interfaces/master_bot/index.js`, `src/interfaces/client_bot/index.js`, `src/infrastructure/db/*`, `bots/client_bot/main.py`.
- Проблема: запрошенные review-сценарии и таблицы отсутствуют.
- Риск: нельзя «точечно чинить» требуемый модуль, т.к. его нет в текущей ветке/репозитории.
- Рекомендация: подтвердить, правильный ли репозиторий/ветка перед следующими правками.

### Средние
2) **Смешение двух контуров (Node-first и legacy Python)**.
- Проблема: высок риск ложных выводов при эксплуатации и поддержке.
- Риск: неправильный деплой или модификация неактивного контура.
- Рекомендация: формально зафиксировать production source-of-truth и статус legacy.

3) **Доступы реализованы role-моделью, но не по ожидаемому `can_use_bot`/`SUPERADMIN_ID` паттерну**.
- Риск: расхождение с ожидаемой политикой доступа из ТЗ.
- Рекомендация: согласовать unified auth/access contract.

### Мелкие
4) **Терминология в ТЗ и в коде различается (отзывы vs заявки)**.
- Риск: ошибки постановки задач и тестирования.
- Рекомендация: выровнять словарь доменных сущностей.

## 22. Критические риски
- Невозможность реализовать требуемые фиксы по `review_analyses.input_json`, `Добавить отзыв`, `Ответ/Жалоба по ID`, т.к. соответствующих сущностей в коде не обнаружено.
- Риск внедрения правок «не туда» из-за присутствия legacy Python рядом с Node runtime.

## 23. Рекомендации для следующего этапа
1) Сначала подтвердить: это тот же репозиторий и нужная ветка для review-бота.
2) Если нужен именно review-бот:
   - предоставить/найти модуль с таблицами `reviews`, `review_analyses`, `access_users`;
   - предоставить migrations/schema SQL.
3) Если текущий Node runtime — целевой:
   - переписать ТЗ в терминах `requests`/master bot/reporting.
4) Для access-политики:
   - формализовать public actions до auth check;
   - определить механизм супер-админа в текущем контуре.
5) Для AI:
   - разделить «AI diagnostics/control plane» и «AI business features» в явных продуктовых сценариях.
6) Для меню:
   - составить целевую карту меню и матрицу прав по ролям.

## 24. Чек-лист ручного тестирования
1) Проверить живость webhook routes:
   - `/telegram/master_bot/webhook`
   - `/telegram/client_bot/webhook`
   - `/telegram/integration_bot/webhook`
2) В master bot:
   - `/start`, `/help`, `/whoami`
   - кнопки главного меню
   - `⬅️ Назад` и `🏠 В меню`
3) Проверить доступы:
   - выдача/отзыв ролей
   - блок admin-only разделов для не-admin
4) Проверить отчёты:
   - выбор типа
   - выбор периода `7d`
   - экспорт
5) Проверить diagnostics/AI:
   - `/diagnostics`
   - `/ai_status`
   - `/ai_diagnostics`
   - `/ai_logs`
6) Если нужен review-контур, подтвердить отдельный модуль/репозиторий перед тестированием.
