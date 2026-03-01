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

    @classmethod
    def from_env(cls) -> "ClientBotConfig":
        token = (os.getenv("CLIENT_TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("CLIENT_TELEGRAM_BOT_TOKEN is required")
        return cls(
            token=token,
            mode=(os.getenv("CLIENT_BOT_MODE") or "polling").strip().lower(),
            host=(os.getenv("CLIENT_SERVICE_HOST") or "0.0.0.0").strip(),
            port=int(os.getenv("CLIENT_SERVICE_PORT") or "8010"),
            data_dir=(os.getenv("CLIENT_DATA_DIR") or "data").strip(),
        )
