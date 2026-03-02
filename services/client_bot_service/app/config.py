from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClientBotConfig:
    token: str
    mode: str
    host: str
    port: int
    data_dir: str


    @staticmethod
    def resolve_token() -> tuple[str, str]:
        allow_fallback = (os.getenv("ALLOW_TOKEN_FALLBACK") or "0").strip() == "1"
        candidates = [("CLIENT_TELEGRAM_BOT_TOKEN", os.getenv("CLIENT_TELEGRAM_BOT_TOKEN"))]
        if allow_fallback:
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
            "(fallbacks TELEGRAM_BOT_TOKEN/BOT_API_TOKEN/API_TOKEN/BOT_TOKEN/TOKEN require ALLOW_TOKEN_FALLBACK=1)"
        )

    @staticmethod
    def resolve_port() -> int:
        return int((os.getenv("PORT") or os.getenv("CLIENT_SERVICE_PORT") or "8000").strip())

    @classmethod
    def from_env(cls) -> "ClientBotConfig":
        token, _ = cls.resolve_token()
        return cls(
            token=token,
            mode=(os.getenv("CLIENT_BOT_MODE") or "polling").strip().lower(),
            host=(os.getenv("CLIENT_SERVICE_HOST") or "0.0.0.0").strip(),
            port=cls.resolve_port(),
            data_dir=(os.getenv("CLIENT_DATA_DIR") or "data").strip(),
        )
