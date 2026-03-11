# PROJECT_AUDIT.md

## Executive summary
- Проект остаётся в рамках production contract: **Node.js runtime**, entrypoint `app.js`, manifest `package.json`, деплой из ветки `main`, BotHost-ориентированный запуск.
- Для MVP уже production-ready: `client_bot`, `master_bot`, `integration_bot`, WebApp/Mini App контур, feedback/quality flow, integration layer MVP (email/manual + one_c skeleton), reporting/snapshots, scheduler/reminders.
- По итогам финальной преддеплойной стабилизации подтверждены: работоспособность ключевых маршрутов, доступность статики (`/styles.css`, `/webapp.js`), корректный WebApp opening flow и theme-safe стилизация (light/dark + Telegram theme variables).
- Оставшиеся риски: file-based DB без межпроцессных lock, single-instance ограничение, one_c остаётся skeleton-интеграцией, часть проверок HTTPS/Telegram требует ручной валидации на боевом домене.

## Production contract
- Runtime: Node.js (`>=18`).
- Entrypoint: `app.js`.
- Manifest: `package.json` (`main: app.js`, `start: node app.js`).
- Branch для деплоя: `main`.
- Production path: Node-first (Python не используется как production runtime).

## BotHost domain risk (критично)
- По информации поддержки BotHost, дефолтный случайный домен нельзя считать надёжной production-базой: у него наблюдается нестабильность обновлений из Git.
- Следствие: дефолтный домен нельзя использовать как основной домен для webhook/WebApp/BotFather.
- Рекомендация для production: короткий пользовательский домен вида **`вашлогин.bothost.ru`**.

## Domain strategy
Использовать единый домен **`https://вашлогин.bothost.ru`** для:
1. `WEBAPP_URL`.
2. `setWebhook` URL для `client_bot`, `master_bot`, `integration_bot`.
3. BotFather Menu Button URL.
4. Smoke tests и эксплуатационного мониторинга.

### Webhook target paths
- `POST /telegram/client_bot/webhook`
- `POST /telegram/master_bot/webhook`
- `POST /telegram/integration_bot/webhook`

## HTTPS / certificate readiness
До запуска в production обязательно проверить:
1. Домен `вашлогин.bothost.ru` назначен и резолвится корректно.
2. Сертификат валиден и не просрочен.
3. В браузере/Telegram нет предупреждений безопасности.
4. Нет ошибок вида `NET::ERR_CERT_AUTHORITY_INVALID`.
5. WebApp (Mini App) открывается по HTTPS стабильно.

## Telegram Mini App compatibility
- WebApp рассматривается как Telegram Mini App контур и проверен на:
  - открытие напрямую по URL;
  - открытие из `client_bot` (через `WEBAPP_URL`/Menu Button);
  - загрузку `/styles.css` и `/webapp.js`;
  - рабочие формы и клиентские сценарии.
- Theme compatibility:
  - добавлены CSS variables + Telegram `themeParams` mapping с fallback;
  - покрыты light/dark сценарии, чтобы избежать нечитабельных сочетаний текста/фона;
  - кнопки, поля ввода, заголовки, блоки и навигация используют theme-aware цвета.

## Static and route readiness
Проверенные критичные маршруты:
- `GET /health`
- `GET /`, `/requests`, `/recommendations`
- `GET /forms/service-request`, `/forms/parts-request`, `/forms/consultation`, `/forms/warranty-request`, `/forms/data-change-request`
- `GET /styles.css`, `GET /webapp.js`
- `GET /api/reports/summary?period=weekly`
- `POST /api/reports/snapshots`
- webhooks для всех трёх ботов

## Pre-deploy checklist
1. Branch = `main`.
2. Runtime = Node.js.
3. Entrypoint = `app.js`.
4. Обязательные ENV заданы.
5. `WEBAPP_URL` указывает на короткий пользовательский домен.
6. `DB_FILE_PATH` указывает на persistent storage.
7. Статика доступна (`/styles.css`, `/webapp.js`).
8. Theme compatibility проверена (light/dark).
9. Webhook URL/path проверены.

## Post-deploy checklist
1. `GET /health`.
2. `GET /`.
3. `GET /styles.css`.
4. `GET /webapp.js`.
5. `GET /api/reports/summary?period=weekly`.
6. `POST /api/reports/snapshots`.
7. WebApp открывается напрямую по HTTPS.
8. WebApp открывается из `client_bot`.
9. `client_bot` отвечает на `/start`.
10. `master_bot` отвечает на `/start`.
11. `integration_bot` отвечает на `/start`.
12. Webhook зарегистрирован и обновления приходят (`getWebhookInfo`).
13. Light/dark themes не ломают интерфейс.

## Separate domain/certificate check
- Назначен короткий пользовательский домен `вашлогин.bothost.ru`.
- Сертификат валиден.
- Нет `NET::ERR_CERT_AUTHORITY_INVALID`.
- Mini App открывается без security проблем.

## Known risks (остаются)
1. File-based DB (`db.json`) ограничивает горизонтальное масштабирование.
2. Multi-instance запуск на общей файловой БД рискован из-за race conditions.
3. Нет внешней очереди/dead-letter механизма.
4. One-C интеграция остаётся MVP/skeleton без полноценного production sync.

## Final deploy readiness conclusion
**Проект готов к деплою на BotHost сейчас** для MVP-нагрузки при соблюдении условий:
- используется короткий пользовательский домен `вашлогин.bothost.ru`;
- валиден SSL сертификат и Mini App открывается без warning;
- настроены все обязательные ENV и persistent `DB_FILE_PATH`;
- выполнены pre/post-deploy проверки из этого audit.

Если условия нарушены (особенно домен/сертификат/persistent storage), deploy readiness считается неполной и запуск в production откладывается.
