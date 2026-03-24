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
