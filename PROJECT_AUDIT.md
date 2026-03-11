# PROJECT_AUDIT

## 1) Статус этапов
- Skeleton-этап: завершён.
- Этап 2 (client_bot + WebApp MVP): реализован и сохранён рабочим.
- Этап 3 (master_bot MVP): реализован и сохранён рабочим.
- Этап 4 (reminders + feedback + quality flow MVP): реализован.

## 2) Production contract (BotHost-safe)
- Runtime: Node.js.
- Entrypoint: `app.js`.
- Manifest: `package.json`.
- Ветка деплоя: `main`.
- Node-first запуск сохранён, Python как production path не используется.

## 3) Что добавлено в этапе 4
### 3.1 Feedback flow MVP
Реализовано:
- получение клиентского feedback из `client_bot` (формат: `1..5` + optional comment);
- сохранение feedback в БД (`feedback` коллекция);
- поля feedback: `id`, `clientId`, `requestId`, `visitId`, `rating`, `comment`, `sourceChannel`, `createdAt`, `createdBy`, `status`, `qualityCaseId`;
- фиксация communication event при получении feedback;
- автосоздание quality case при рейтинге `< 3`.

### 3.2 Reminder / task layer MVP
Реализовано:
- БД-слой для task/jobs (`tasks`);
- обязательные поля задачи: `id`, `taskType`, `status`, `dueAt`, `createdAt`, `processedAt`, `attemptCount`, `lastError`, `payload`;
- статусы: `scheduled`, `processing`, `completed`, `failed`, `cancelled`;
- task types:
  - `feedback_request` (реально исполняется),
  - `quality_followup` (skeleton),
  - `recommendation_reminder` (skeleton),
  - `maintenance_reminder` (skeleton);
- планировщик (`src/infrastructure/scheduler`) с interval-worker, claim due задач, idempotent-safe обработкой, retry/fail логикой.

### 3.3 Feedback request trigger
MVP правило реализовано:
- при переводе заявки в `processed` автоматически создаётся отложенная задача `feedback_request`;
- delay настраивается через env `FEEDBACK_REQUEST_DELAY_MINUTES`.

### 3.4 Отправка feedback request
Реализовано:
- scheduler-обработчик `feedback_request` отправляет клиенту Telegram-сообщение с запросом оценки 1..5;
- при недоступном канале задача корректно уходит в retry/fail по лимиту попыток;
- отправка логируется в `communicationEvents`.

### 3.5 Quality flow MVP
При feedback `< 3`:
- автоматически создаётся `QualityCase` со статусом `new`;
- заполняются `clientId`, `feedbackId`, `requestId`, `assignedTo` (если известен мастер), `reasonCategory=low_rating`;
- пишется событие в `communicationEvents`;
- пишется action в `masterActions`;
- в event model фиксируется дублирование для руководителя (`duplicateForRole: manager`);
- при наличии telegram binding отправляется уведомление мастеру и manager-copy через master bot token.

## 4) Изменения в хранилище `data/db.json`
Новые коллекции:
- `feedback`
- `tasks`

Расширения:
- `qualityCases` дополнен полями для feedback-driven quality workflow (`clientId`, `feedbackId`, `reasonCategory`).

## 5) Обратная совместимость этапов 2/3
Сохранены рабочими:
- `client_bot` webhook;
- `master_bot` webhook;
- WebApp маршруты и API;
- `/health`.

## 6) Покрытие тестами этапа 4
Добавлены node-тесты:
- создание feedback task при `processed`;
- приём feedback клиента и автосоздание quality case для низкой оценки;
- фиксация manager duplication event и staff action;
- scheduler run-once обработка due tasks и безопасный fail-path.

## 7) Готовность к следующему шагу
Платформа готова к расширению reminder-логики (recommendation/time/mileage/rule-based), enrichment quality workflow и дальнейшей интеграции без нарушения BotHost-safe Node.js production contract.
