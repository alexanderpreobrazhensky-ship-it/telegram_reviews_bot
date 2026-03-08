# AUDIT_AFTER_CODEX

## Что изменено
- Синхронизирован production-контракт в документации: `main` как production branch, Python + Dockerfile + `main.py` как единый путь запуска.
- Обновлён `bots/client_bot/README.md` и устранён drift с корневым `README.md`.
- Обновлены аудит-файлы `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.md`, `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.json`, `audit/REPO_MANIFEST.txt`.
- Добавлен тест fail-fast кейса: webhook-mode без `BOT_PATH_SECRET` должен падать с явной ошибкой.

## Какие риски устранены
- Противоречие README vs service README по polling/webhook.
- Неоднозначность production-контракта запуска.
- Недостаточная тестовая фиксация webhook prerequisite `BOT_PATH_SECRET`.

## Production-контракт (итог)
- Branch для деплоя: `main`.
- Runtime: Python.
- Deploy path: Dockerfile-first.
- Entrypoint: `main.py`.
- Default mode: webhook-first с fallback в polling при невалидном/пустом base URL.

## Выполненные проверки
- Unit tests: `python -m unittest discover -s tests -p "test_*.py"`.
- Точечные проверки: entrypoint contract, webhook URL builder, runtime behavior, static/health routes.

## Ограничения / known limitations
- Текущая рабочая ветка в локальном репо — `work`; для фактического прод-деплоя нужно держать `main` синхронизированной с этим состоянием.
- Локальный smoke-run с реальным Telegram webhook не выполнялся без внешнего публичного домена/токена.
