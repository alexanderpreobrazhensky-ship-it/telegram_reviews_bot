from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Client:
    telegram_user_id: int
    telegram_username: str = ""
    full_name: str = ""
    phones: list[str] = field(default_factory=list)
    car_numbers: list[str] = field(default_factory=list)
    vin_codes: list[str] = field(default_factory=list)
    vk_username: str = ""
    max_username: str = ""
    email: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    source_tags: list[str] = field(default_factory=list)
