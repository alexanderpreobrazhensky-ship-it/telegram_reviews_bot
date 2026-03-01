from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


STATUSES = ["new", "in_progress", "waiting_data", "processed", "archived"]
POSTPONED_STATUS = "postponed"  # intentionally prepared for staged rollout


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Ticket:
    ticket_id: int
    telegram_user_id: int
    text: str
    status: str = "new"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    master_id: int | None = None
    postponed_until: str | None = None
