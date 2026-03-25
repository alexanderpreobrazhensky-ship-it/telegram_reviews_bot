# RUNTIME_RECHECK_TASK

## Цель
Провести прицельную runtime/deploy перепроверку критичных operational-блоков поверх `audit/MASTER_AUDIT.md` и зафиксировать итог только в одном audit source of truth.

## 5 блоков проверки
1. Reference dataset / existing client lookup.
2. WebApp -> DB -> рабочие списки master-бота.
3. Telegram / MAX parity (source-of-truth и delivery UX).
4. Email intake / T-Business runtime readiness.
5. AI runtime config / provider readiness.

## Ключевые вопросы
- Работает ли exact phone match как достаточное правило для existing client.
- Доходят ли WebApp-заявки до `status=new` и списков «Новые заявки»/«В работе».
- Есть ли parity между Telegram и MAX на уровне сущности и фактической доставки.
- Работает ли T-Business intake operationally (IMAP/folder/poller/parse/create).
- Operationally ready ли AI-контур или только architecturally ready.

## Expected outputs
- Обновлённый раздел runtime re-check в `audit/MASTER_AUDIT.md` с маркировкой `confirmed / partially confirmed / not confirmed / hypothesis only`.
- Явные ответы по всем 5 блокам и обновлённый operational verdict.
- Фиксация открытых проблем и root cause без ложных пометок `fixed`.

## Критерий готовности
- Создан этот task-файл.
- Все результаты и выводы внесены только в `audit/MASTER_AUDIT.md`.
- Перепроверены все 5 критичных блоков и дан финальный operational verdict.
