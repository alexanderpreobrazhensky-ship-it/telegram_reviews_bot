# WebApp

## Canonical files
- `public/index.html`
- `public/webapp.js`
- `public/styles.css`

## Routes
- `/`
- `/requests`
- `/recommendations`
- `/forms/service-request`
- `/forms/parts-request`
- `/forms/consultation`
- `/forms/warranty-request`
- `/forms/data-change-request`

## Constraints
- `app.js` + Node runtime остаются primary execution path.
- `review.html` и `public/index.html` не используются как место для изменений этой задачи.
- Phone validation остаётся строгой: ровно 10 цифр.

## Channel context
WebApp payload может содержать Telegram/MAX identity;
дальше эти идентификаторы используются master-ботом для безопасного outbound маршрута.

## Existing client lookup (site/WebApp)
- Для submit flow (`/api/client/requests/*`) добавлен backend lookup в `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`.
- Правило детерминированное и exact-only: совпасть должны одновременно `phone (10 digits)` + `ФИО` после нормализации (trim, collapse spaces, case-insensitive, `ё -> е`).
- Если найден один точный match:
  - `payload.existing_client = true`
  - `payload.client_match_basis = phone_fio`
  - `payload.matched_reference_client_id` заполняется из `clients.client_code`
  - `payload.needs_review = false`
- Если match не найден: `existing_client = false`.
- Если найдено несколько записей по `phone+fio`: `existing_client = false`, `needs_review = true`, `client_match_basis = conflict_multiple_matches`.
- Email/VIN не используются как ключи в этом WebApp lookup.

## Update 2026-03-25 (WebApp intake hardening)
- Existing client lookup переведён на primary business rule `phone exact match` (нормализованный 10-значный номер).
- FIO больше не блокирует match: если телефон найден ровно один раз -> `existing_client=true`, `client_match_basis=phone`.
- Если нет совпадения -> `client_match_basis=no_match`.
- Если по одному телефону найдено >1 клиента -> `client_match_basis=multiple_phone_matches`, `needs_review=true`.
- Если dataset недоступен -> `client_match_basis=reference_dataset_unavailable` (не маскируется под `no_match`).
- Поле `Был у нас ранее` (`wasClientBefore`) обязательно для всех WebApp форм.
- VIN-правило:
  - `wasClientBefore=yes` -> VIN не обязателен;
  - `wasClientBefore=no` -> VIN обязателен;
  - если признак не выбран -> submit блокируется.
- Проверка правила выполняется и на frontend (`public/webapp.js`), и на backend (`validateClientRequestPayload`).
