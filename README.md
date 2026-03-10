# Единая платформа автосервиса (Node.js / BotHost)

## Что это
Репозиторий переведён на **Node.js-first production path** и содержит архитектурный skeleton платформы с тремя сервисными контурами:
- `client_bot`
- `master_bot`
- `integration_bot`

Также добавлен skeleton клиентского **WebApp/Mini App** как основного UX-канала.

## BotHost production contract
- runtime: Node.js
- branch: `main`
- main entrypoint: `app.js`
- package manifest: `package.json`
- Python-файлы считаются legacy и не участвуют в production startup contract

## Архитектура
- `src/core` — доменная модель, типы, use-cases
- `src/interfaces` — Telegram интерфейсы ботов + webapp routing/state skeleton
- `src/integrations` — заготовки email и one_c адаптеров
- `src/infrastructure` — config, db schema, logging, queue, scheduler, repositories
- `src/server` — HTTP entrypoint/роутинг для BotHost
- `public` — статические файлы WebApp
- `tests/node` — structural тесты skeleton-этапа

## MVP на текущем этапе
Включено:
- Node-safe каркас платформы
- согласованные типы обращений и статусы в коде
- заготовка доменных сущностей и связей
- skeleton persistence/queue/scheduler/integration pipelines
- базовая страница WebApp с маршрутами и местом под формы/списки

Не включено (будет на следующих этапах):
- полная бизнес-логика всех ботов
- production-интеграция с 1C
- каналы VK/MAX
- AI/advanced analytics

## Запуск локально
```bash
npm start
```

## Тесты
```bash
npm test
```

## ENV переменные
- `PORT`
- `NODE_ENV`
- `DB_URL`
- `QUEUE_DRIVER`
- `TELEGRAM_CLIENT_BOT_TOKEN`
- `TELEGRAM_MASTER_BOT_TOKEN`
- `TELEGRAM_INTEGRATION_BOT_TOKEN`
- `ONE_C_WEBHOOK_SECRET`

## Порты / домен / HTTPS
- По умолчанию сервер слушает `PORT=3000`
- На BotHost ожидается проксирование через HTTPS-домен платформы
- Webhook и WebApp маршруты обслуживаются тем же Node entrypoint

## Future roadmap
- 1C bi-directional sync через `src/integrations/one_c`
- Подключение VK/MAX как новых channel adapters
- Отдельный analytics/AI контур поверх event/task моделей
