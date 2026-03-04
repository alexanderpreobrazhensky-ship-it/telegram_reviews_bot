import os
from dataclasses import dataclass


TOKEN_KEYS = [
    "CLIENT_TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "BOT_API_TOKEN",
    "API_TOKEN",
    "BOT_TOKEN",
    "TOKEN",
]


@dataclass
class RuntimeConfig:
    run_mode: str
    host: str
    port: int
    token: str
    token_source: str
    base_url_source: str
    ignored_env_keys: list[str]


def _first_env(keys: list[str]) -> tuple[str, str] | tuple[None, None]:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value, key
    return None, None


def load_runtime_config() -> RuntimeConfig:
    run_mode = (
        os.getenv("CLIENT_BOT_MODE")
        or os.getenv("CLIENT_RUN_MODE")
        or os.getenv("RUN_MODE")
        or "webhook"
    ).strip().lower()

    token, token_source = _first_env(TOKEN_KEYS)
    if not token or not token_source:
        raise RuntimeError(
            "Client bot token is required: set one of CLIENT_TELEGRAM_BOT_TOKEN/TELEGRAM_BOT_TOKEN/BOT_API_TOKEN/API_TOKEN/BOT_TOKEN/TOKEN"
        )

    host = (os.getenv("CLIENT_SERVICE_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port_raw, _ = _first_env(["PORT", "CLIENT_SERVICE_PORT"])
    port = int(port_raw or "8000")

    if (os.getenv("WEBHOOK_URL") or "").strip():
        base_url_source = "WEBHOOK_URL"
    elif (os.getenv("PUBLIC_BASE_URL") or "").strip():
        base_url_source = "PUBLIC_BASE_URL"
    elif (os.getenv("DOMAIN") or "").strip():
        base_url_source = "DOMAIN"
    else:
        base_url_source = "missing"

    known_keys = {
        "CLIENT_BOT_MODE",
        "CLIENT_RUN_MODE",
        "RUN_MODE",
        "CLIENT_SERVICE_HOST",
        "PORT",
        "CLIENT_SERVICE_PORT",
        "WEBHOOK_URL",
        "PUBLIC_BASE_URL",
        "DOMAIN",
        "BOT_PATH_SECRET",
        "CLIENT_MASTERS_CHAT_ID",
        "CLIENT_CHAT_ID",
        "CLIENT_MASTER_CHAT_ID",
        "CLIENT_MASTER_USER_IDS",
        "CLIENT_MASTER_IDS",
        "CLIENT_ADMIN_IDS",
        "REPORT_CHAT_IDS",
        "SUPERADMIN_ID",
    }.union(TOKEN_KEYS)

    ignored = sorted(
        [key for key in os.environ if key.startswith("CLIENT_") and key not in known_keys]
    )

    return RuntimeConfig(
        run_mode=run_mode,
        host=host,
        port=port,
        token=token,
        token_source=token_source,
        base_url_source=base_url_source,
        ignored_env_keys=ignored,
    )
