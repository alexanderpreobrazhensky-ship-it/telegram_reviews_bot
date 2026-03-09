# AUDIT_AFTER_CODEX

## Выполнено
1. Node runtime убран из production-path: `index.js` удалён из корня и перенесён в `legacy/index.js`.
2. Корень репозитория приведён к Python-only виду для BotHost runtime detection.
3. Production-контракт закреплён и синхронизирован в документации:
   - branch = `main`
   - deploy path = Dockerfile-first
   - entrypoint = `main.py`
   - runtime = Python
   - default mode = webhook-first
4. Обновлены контрактные тесты по entrypoint/Node markers.
5. Обновлены audit-артефакты и manifest.

## Изменённые/затронутые файлы
- `legacy/index.js`
- `tests/test_entrypoints.py`
- `README.md`
- `bots/client_bot/README.md`
- `AUDIT_AFTER_CODEX.md`
- `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.md`
- `audit/MASTER_AUDIT_FOR_EXTERNAL_AI.json`
- `audit/REPO_MANIFEST.txt`

## Проверки
- `python -m unittest discover -s tests -p "test_*.py"`

## Итог
Репозиторий зафиксирован как Python-only в production-path; у BotHost не остаётся Node-entrypoint триггеров в корне.
