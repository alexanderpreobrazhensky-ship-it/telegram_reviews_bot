# Финальный технический аудит (после доработок)

## 1) Что изменено в WebApp
- Поля обязательности вынесены по типам обращений и валидируются на клиенте и сервере.
- Телефон переведён на маску `+7 (___) ___-__-__`, ввод мусора ограничен, paste поддержан с нормализацией.
- Submit-защита: кнопка блокируется, текст меняется на `Отправка…`, повторный submit с клиента невозможен до ответа.
- Добавлен экран результата (успех/ошибка) с:
  - CTA на Telegram-канал,
  - ссылкой на канал,
  - кнопкой создать ещё одно обращение,
  - ссылкой на главную.
- Визуальный редизайн: тёмно-синий фон, карточная центральная верстка, крупные кнопки, единый стиль для главной/форм/requests/recommendations/result.

## 2) Защита от дублей
- Клиентская: блокировка submit-кнопки на период запроса.
- Серверная best-effort дедупликация: по `(requestType, phone, vin, текст обращения)` в окне `WEBAPP_DEDUPE_WINDOW_MS` (default 45s).
- При дубле сервер возвращает существующую заявку с `deduplicated: true`, новую не создаёт.

## 3) Телефон: masking / normalization / storage
- Frontend: маска `+7 (...) ...-..-..`, пользователь вводит только цифры после префикса.
- Normalization: `+7XXXXXXXXXX` / `8XXXXXXXXXX` -> `XXXXXXXXXX`.
- API принимает только 10 цифр (валидация regex), пустое/невалидное — `400 Validation error`.
- Хранение в store: только 10 цифр, без `+7/8` (совместимость с 1С).

## 4) Обязательные поля по типам
- `service_request`: `fullName`, `phone`, `year`, `vin`, `description`
- `parts_request`: `fullName`, `phone`, `year`, `vin`, `description` (brand/model остаются optional)
- `consultation_request`: `fullName`, `phone`, `year`, `vin`, `question`
- `warranty_request`: `fullName`, `phone`, `year`, `vin`, `description`, `visitContext`
- `data_change_request`: `fullName`, `phone`, `changeDetails` (year/vin optional)

## 5) Master bot workflow
- Сохранены `/start`, кнопки: `Новые заявки`, `В работе`, `Поиск`, `Quality Cases`.
- Внедрены inline-кнопки карточки/действий:
  - `Взять в работу` (`new -> in_progress`)
  - `Запросить данные` (`new -> waiting_data`)
  - `Завершить` (`in_progress -> processed`)
  - `Потеряно` (`in_progress -> lost`, с обязательной причиной)
  - `Открыть карточку`
- Комментарии: `/comment <requestId> ...` сохраняются в `requestInternalComments`.
- Поиск: интерактивный и `/search`, с выводом карточки первой найденной заявки.
- Карточка содержит id/тип/статус/клиент/телефон/VIN/год/описание/источник/создание/историю статусов.

## 6) Access-control
- Убрано авто-выдача доступа неизвестным.
- Неизвестный `/start` -> `ACCESS_DENIED`.
- `admin` назначается только через `MASTER_BOT_ADMIN_IDS` (ENV) и имеет приоритет.
- Для `manager/admin` доступен раздел `Доступы` и команды:
  - `/access_list`
  - `/access_grant <telegramId> <master|manager> [ФИО]`
  - `/access_role <telegramId> <master|manager>`
  - `/access_revoke <telegramId>`

## 7) Чат мастеров
- Новые WebApp-заявки дублируются в `TELEGRAM_MASTERS_CHAT_ID`.
- Сообщение в чат мастеров содержит рабочие inline-кнопки статусов + карточка.
- Для quality-related логики сохранены существующие уведомления при auto quality case из фидбека.

## 8) ENV
- Добавлен отдельный deploy-reference: `audit/ENV_DEPLOY_REFERENCE.md`.
- Новые/критичные для задачи ENV:
  - `MASTER_BOT_ADMIN_IDS`
  - `TELEGRAM_MASTERS_CHAT_ID`
  - `WEBAPP_TELEGRAM_CHANNEL_LINK`
  - `WEBAPP_DEDUPE_WINDOW_MS`

## 9) Логотип
- Использован существующий стиль без бинарных добавлений; бинарные ассеты не генерировались.

## 10) Проверки
- Авто: полный `npm test` (Node test suite) зелёный.
- Smoke (ручной) рекомендуется:
  1. Все 5 форм: required поля + маска телефона + submit/result.
  2. Двойной клик submit и повтор после refresh/back.
  3. Проверка дубля в окне дедупликации.
  4. Новый request -> master_bot list/card/status transitions.
  5. `lost` без причины (ошибка) и с причиной (успех).
  6. `waiting_data` + `/ask_client` при привязанном telegram.
  7. Access rules: неизвестный отказ, admin из ENV доступ, manager/admin доступы.
  8. Дублирование в чат мастеров и работа inline-кнопок.

## 11) Риски/ограничения
- Дедупликация best-effort по локальному JSON-store, при распределённом deployment нужен общий persist/lock.
- `DB_URL` остаётся legacy placeholder (JSON store активен).
- Для полноценной мультиканальности `waiting_data` требуется выделенный transport-слой (сейчас Telegram-ready, архитектурно не блокирует расширение).

## 12) Контроль защищённых файлов
- `review.html` не изменялся.
- `index.html` не изменялся.
- Пути/имена сохранены.
