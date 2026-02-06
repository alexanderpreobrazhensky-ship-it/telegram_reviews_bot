import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

STORAGE_FILE = os.path.join(os.path.dirname(__file__), "storage.json")


def now_iso(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).isoformat()


def ttl_iso(timezone: str, hours: int = 24) -> str:
    return (datetime.now(ZoneInfo(timezone)) + timedelta(hours=hours)).isoformat()


def load_storage() -> dict:
    if not os.path.exists(STORAGE_FILE):
        return {"tickets": [], "sessions": {}}
    with open(STORAGE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_storage(data: dict) -> None:
    os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
    tmp_path = f"{STORAGE_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STORAGE_FILE)


def get_session(storage: dict, chat_id: int) -> dict | None:
    session = storage.get("sessions", {}).get(str(chat_id))
    return deepcopy(session) if session else None


def save_session(storage: dict, chat_id: int, session: dict) -> None:
    storage.setdefault("sessions", {})[str(chat_id)] = deepcopy(session)


def clear_session(storage: dict, chat_id: int) -> None:
    storage.setdefault("sessions", {}).pop(str(chat_id), None)


def next_ticket_id(storage: dict, date_prefix: str) -> str:
    existing = [
        ticket["ticket_id"]
        for ticket in storage.get("tickets", [])
        if ticket.get("ticket_id", "").startswith(f"LIRA-{date_prefix}-")
    ]
    sequence = 0
    for ticket_id in existing:
        try:
            sequence = max(sequence, int(ticket_id.split("-")[-1]))
        except ValueError:
            continue
    return f"LIRA-{date_prefix}-{sequence + 1:04d}"
