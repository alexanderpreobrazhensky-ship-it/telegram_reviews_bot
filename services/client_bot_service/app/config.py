from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ClientBotConfig:
    token: str
    mode: str
    host: str
    port: int
    data_dir: str
    public_base_url: str | None
    webhook_path: str | None
    webhook_url: str | None
    webapp_url: str | None
    database_url: str | None
    master_user_ids_raw: str
    masters_chat_id_raw: str

    @staticmethod
    def resolve_token() -> tuple[str, str]:
        candidates = [("CLIENT_TELEGRAM_BOT_TOKEN", os.getenv("CLIENT_TELEGRAM_BOT_TOKEN"))]
        primary = (os.getenv("CLIENT_TELEGRAM_BOT_TOKEN") or "").strip()
        if not primary:
            candidates.extend(
                [
                    ("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN")),
                    ("BOT_API_TOKEN", os.getenv("BOT_API_TOKEN")),
                    ("API_TOKEN", os.getenv("API_TOKEN")),
                    ("BOT_TOKEN", os.getenv("BOT_TOKEN")),
                    ("TOKEN", os.getenv("TOKEN")),
                ]
            )
        for source, raw in candidates:
            token = (raw or "").strip()
            if token:
                return token, source
        raise RuntimeError(
            "Client bot token is required: set CLIENT_TELEGRAM_BOT_TOKEN "
            "(fallbacks TELEGRAM_BOT_TOKEN/BOT_API_TOKEN/API_TOKEN/BOT_TOKEN/TOKEN are used only when CLIENT_TELEGRAM_BOT_TOKEN is empty)"
        )

    @staticmethod
    def resolve_port() -> int:
        return int((os.getenv("PORT") or os.getenv("CLIENT_SERVICE_PORT") or "8000").strip())

    @staticmethod
    def _normalize_https_url(value: str | None) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None
        normalized = raw
        while normalized.lower().startswith("https://https://"):
            normalized = normalized[len("https://") :]
        while normalized.lower().startswith("https://http://"):
            normalized = "https://" + normalized[len("https://http://") :]
        if normalized.lower().startswith("http://"):
            normalized = "https://" + normalized[len("http://") :]
        if not normalized.lower().startswith("https://"):
            normalized = f"https://{normalized}"
        parsed = urlparse(normalized)
        host = (parsed.netloc or "").strip().lower()
        if not host:
            return None
        path = (parsed.path or "").rstrip("/")
        return f"https://{host}{path}" if path else f"https://{host}"

    @classmethod
    def resolve_public_base_url(cls) -> str | None:
        base, _ = cls.resolve_public_base_url_with_source()
        return base


    @classmethod
    def resolve_public_base_url_with_source(cls) -> tuple[str | None, str]:
        direct = cls._normalize_https_url(os.getenv("WEBHOOK_URL"))
        if direct:
            return direct, "WEBHOOK_URL"
        direct = cls._normalize_https_url(os.getenv("PUBLIC_BASE_URL"))
        if direct:
            return direct, "PUBLIC_BASE_URL"
        domain = (os.getenv("DOMAIN") or "").strip().lower().strip("/")
        if not domain:
            return None, "missing"
        domain = domain.replace("https://", "").replace("http://", "")
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        return (f"https://{domain}" if domain else None), "DOMAIN"

    @staticmethod
    def resolve_database_url() -> str | None:
        for key in ("DATABASE_URL", "POSTGRES_URL", "POSTGRESQL_URL"):
            value = (os.getenv(key) or "").strip()
            if value:
                return value
        return None

    @classmethod
    def resolve_webapp_url(cls, public_base_url: str | None) -> str | None:
        direct = cls._normalize_https_url(os.getenv("CLIENT_WEBAPP_URL") or os.getenv("WEBAPP_URL"))
        if direct:
            return direct
        if not public_base_url:
            return None
        path = (os.getenv("WEBAPP_PATH") or "/WEBAPP").strip() or "/WEBAPP"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{public_base_url}{path.rstrip('/')}"

    @staticmethod
    def resolve_webhook_path() -> str | None:
        secret = (os.getenv("BOT_PATH_SECRET") or "").strip()
        if not secret:
            return None
        return f"/webhook/{secret}"

    @classmethod
    def from_env(cls) -> "ClientBotConfig":
        token, _ = cls.resolve_token()
        mode = (os.getenv("CLIENT_BOT_MODE") or "webhook").strip().lower()
        public_base_url = cls.resolve_public_base_url()
        webhook_path = cls.resolve_webhook_path()

        if mode == "webhook" and not webhook_path:
            raise RuntimeError("BOT_PATH_SECRET is required in webhook mode")

        webhook_url = f"{public_base_url}{webhook_path}" if public_base_url and webhook_path else None

        return cls(
            token=token,
            mode=mode,
            host=(os.getenv("CLIENT_SERVICE_HOST") or "0.0.0.0").strip(),
            port=cls.resolve_port(),
            data_dir=(os.getenv("CLIENT_DATA_DIR") or "data").strip(),
            public_base_url=public_base_url,
            webhook_path=webhook_path,
            webhook_url=webhook_url,
            webapp_url=cls.resolve_webapp_url(public_base_url),
            database_url=cls.resolve_database_url(),
            master_user_ids_raw=(os.getenv("CLIENT_MASTER_USER_IDS") or os.getenv("CLIENT_MASTER_IDS") or "").strip(),
            masters_chat_id_raw=(os.getenv("CLIENT_MASTERS_CHAT_ID") or os.getenv("CLIENT_MASTER_CHAT_ID") or os.getenv("CLIENT_CHAT_ID") or "").strip(),
        )
