from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewsConfig:
    host: str
    port: int
    token: str
    mode: str

    @classmethod
    def from_env(cls) -> "ReviewsConfig":
        token = (os.getenv("REVIEWS_TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("REVIEWS_TELEGRAM_BOT_TOKEN is required")
        return cls(
            host=(os.getenv("REVIEWS_SERVICE_HOST") or "0.0.0.0").strip(),
            port=int(os.getenv("REVIEWS_SERVICE_PORT") or "8020"),
            token=token,
            mode=(os.getenv("REVIEWS_BOT_MODE") or "polling").strip().lower(),
        )
