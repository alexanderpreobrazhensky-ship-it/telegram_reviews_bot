# Project Overview

## Что это за проект
Единый **Node-first** runtime для обработки заявок и операционной работы мастер-команды:
- HTTP runtime (`app.js` + `src/server/index.js`)
- Telegram client/master/integration bots
- MAX client/master bots
- WebApp (`public/index.html`, `public/webapp.js`)
- SQLite-first persistence
- встроенный persisted scheduler
- AI control plane (инфраструктурный контур + диагностика + runtime switch)
- Email intake (IMAP) с отдельной логикой T-Business/needs_review

## Production baseline (source of truth)
- `app.js`
- `src/server/index.js`
- `src/infrastructure/config/index.js`
- `src/infrastructure/db/index.js`
- `src/interfaces/master_bot/index.js`
- `src/interfaces/client_bot/index.js`
- `src/interfaces/integration_bot/index.js`
- `public/webapp.js`

## Master-bot reality
Главное меню: новые заявки, в работе, архив, поиск, quality cases, инструкция, диагностика, логи, доступы, AI (admin).

Статусная модель заявки:
- `new`
- `in_progress`
- `processed`
- `in_service`
- `completed`
- `error`

Подстатусы `processed`:
- `recorded`
- `consulted`
- `spam`
- `waiting_decision`
- `rejected`

Архив — это `archived=true`, а не отдельный operational status.

## Email intake / T-Business reality
Если включён `EMAIL_INTAKE_ENABLED=true`, пуллер IMAP получает письма, нормализует payload, запускает дедупликацию и создаёт заявки.

В payload фиксируются:
- `source_provider` (`t_business` / `email_generic`)
- `priority` (для T-Business — `high`)
- `existing_client`
- `needs_review`
- `match_basis`
- `match_confidence`

## AI reality
AI уже реализован как отдельный control plane:
- AI Status
- AI Diagnostics
- AI Switch (runtime override)
- AI Logs

Бизнес-использование AI может быть выключено (`AI_BUSINESS_USAGE_ENABLED=false`), даже если инфраструктура и диагностика активны.

## Аудит
Единый audit source of truth: `audit/MASTER_AUDIT.md`.

## Reference bridge dataset (client/vehicle)
В репозитории добавлен отдельный reference-слой данных:
- `data/reference/client_vehicle_bridge/lira_normalized_database.xlsx`
- `data/reference/client_vehicle_bridge/lira_normalized_database.sqlite`

Назначение: подготовка future Excel/1С import, matching и enrichment.
Это не production runtime DB и не подменяет SQLite runtime слой.
Подробности: `readme/README_CLIENT_VEHICLE_BRIDGE.md`.
