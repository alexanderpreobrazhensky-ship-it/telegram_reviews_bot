# Security

## Access model
- Bootstrap: `MASTER_BOT_ADMIN_IDS`, `MAX_MASTER_BOT_ADMIN_IDS`.
- Persistent grants/revokes: через `staff_users` (master bot access flow).
- Internal pages: `INTERNAL_ADMIN_WHITELIST`.

## Secret handling
- В диагностиках и статусах секреты маскируются.
- В AI-блоке отображается только masked/boolean readiness.
- `MAX_WEBHOOK_SECRET` обязателен для MAX webhook validation при `MAX_ENABLED=true`.

## Data safety constraints
- Номер телефона нормализуется в 10 цифр.
- Архивные заявки read-only в master card flow.
- Outbound клиентские сообщения не используют email fallback.

## AI security notes
- AI status/diagnostics/logs доступны только admin роли.
- Разделяются config-invalid и provider-failed состояния.
- Runtime override не должен скрывать некорректную canonical config.

## Operational risks
- Internal endpoints защищены allowlist-подходом, не полноценным IAM.
- Безопасность SQLite зависит от прав файловой системы и deploy-контекста.
