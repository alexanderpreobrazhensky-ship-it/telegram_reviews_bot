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

MODE_KEYS = ["CLIENT_BOT_MODE", "CLIENT_RUN_MODE", "RUN_MODE"]
PORT_KEYS = ["PORT", "CLIENT_SERVICE_PORT"]
BASE_URL_KEYS = ["WEBHOOK_URL", "PUBLIC_BASE_URL", "DOMAIN"]
WEBAPP_URL_KEYS = ["CLIENT_WEBAPP_URL", "WEBAPP_URL"]
WEBAPP_PATH_KEYS = ["WEBAPP_PATH"]
MASTERS_CHAT_KEYS = ["CLIENT_MASTERS_CHAT_ID", "CLIENT_CHAT_ID", "CLIENT_MASTER_CHAT_ID"]
MASTER_IDS_KEYS = ["CLIENT_MASTER_USER_IDS", "CLIENT_MASTER_IDS"]
LEGACY_KEYS = [
    "REPORT_CHAT_IDS",
    "SUPERADMIN_ID",
    "CLIENT_ADMIN_IDS",
    "MASTER_USERNAMES",
    "REMINDER_USERNAMES",
]


@dataclass
class RuntimeConfig:
    run_mode: str
    host: str
    port: int
    token: str
    token_source: str
    base_url_source: str
    webapp_url_source: str
    env_used_count: int
    env_ignored_count: int


def _pick_first(keys: list[str], used_keys: set[str]) -> tuple[str | None, str | None]:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            used_keys.add(key)
            return value, key
    return None, None


def _normalize_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "webhook").strip().lower()
    return mode if mode in {"webhook", "polling"} else "webhook"


def load_runtime_config() -> RuntimeConfig:
    used_keys: set[str] = set()

    mode_value, mode_source = _pick_first(MODE_KEYS, used_keys)
    if mode_source:
        used_keys.add(mode_source)
    run_mode = _normalize_mode(mode_value)

    token, token_source = _pick_first(TOKEN_KEYS, used_keys)
    if not token or not token_source:
        raise RuntimeError(
            "Client bot token is required: set one of CLIENT_TELEGRAM_BOT_TOKEN/TELEGRAM_BOT_TOKEN/BOT_API_TOKEN/API_TOKEN/BOT_TOKEN/TOKEN"
        )

    host = (os.getenv("CLIENT_SERVICE_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    if os.getenv("CLIENT_SERVICE_HOST"):
        used_keys.add("CLIENT_SERVICE_HOST")

    port_raw, _ = _pick_first(PORT_KEYS, used_keys)
    port = int(port_raw or "8000")

    _, base_url_source = _pick_first(BASE_URL_KEYS, used_keys)
    if not base_url_source:
        base_url_source = "missing"

    webapp_url, webapp_url_source = _pick_first(WEBAPP_URL_KEYS, used_keys)
    if not webapp_url:
        domain = (os.getenv("DOMAIN") or "").strip()
        webapp_path = (os.getenv("WEBAPP_PATH") or "/WEBAPP").strip() or "/WEBAPP"
        if domain:
            used_keys.add("DOMAIN")
            if os.getenv("WEBAPP_PATH"):
                used_keys.add("WEBAPP_PATH")
            webapp_url_source = "DOMAIN+WEBAPP_PATH"

    for group in (MASTERS_CHAT_KEYS, MASTER_IDS_KEYS, LEGACY_KEYS):
        for key in group:
            if (os.getenv(key) or "").strip():
                used_keys.add(key)

    recognized_keys = set(
        TOKEN_KEYS
        + MODE_KEYS
        + PORT_KEYS
        + BASE_URL_KEYS
        + WEBAPP_URL_KEYS
        + WEBAPP_PATH_KEYS
        + MASTERS_CHAT_KEYS
        + MASTER_IDS_KEYS
        + LEGACY_KEYS
        + ["BOT_PATH_SECRET", "CLIENT_SERVICE_HOST", "CLIENT_WEBAPP_SESSION_SECRET"]
    )

    ignored_keys = {
        key
        for key, value in os.environ.items()
        if value.strip() and key in recognized_keys and key not in used_keys
    }

    return RuntimeConfig(
        run_mode=run_mode,
        host=host,
        port=port,
        token=token,
        token_source=token_source,
        base_url_source=base_url_source,
        webapp_url_source=webapp_url_source or "missing",
        env_used_count=len(used_keys),
        env_ignored_count=len(ignored_keys),
    )
