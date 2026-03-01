from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewsConfig:
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "ReviewsConfig":
        return cls(
            host=(os.getenv("REVIEWS_SERVICE_HOST") or "0.0.0.0").strip(),
            port=int(os.getenv("REVIEWS_SERVICE_PORT") or "8020"),
        )
