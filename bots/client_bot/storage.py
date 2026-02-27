import base64
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timedelta

import requests
from zoneinfo import ZoneInfo

STORAGE_FILE = os.path.join(os.path.dirname(__file__), "storage.json")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CLIENTS_JSON_FILE = os.path.join(DATA_DIR, "clients.json")
TICKETS_JSON_FILE = os.path.join(DATA_DIR, "tickets.json")
SYSTEM_JSON_FILE = os.path.join(DATA_DIR, "system.json")
STORAGE_LOCK = threading.Lock()


def now_iso(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).isoformat()


def ttl_iso(timezone: str, hours: int = 24) -> str:
    return (datetime.now(ZoneInfo(timezone)) + timedelta(hours=hours)).isoformat()


def ensure_storage_schema(storage: dict) -> dict:
    storage.setdefault("tickets", [])
    storage.setdefault("sessions", {})
    storage.setdefault("admins", [])
    storage.setdefault("settings", {})
    storage.setdefault("admin_sessions", {})
    storage.setdefault("blocklist", [])
    storage.setdefault("outgoing_messages", [])
    storage.setdefault("callback_debounce", {})
    storage.setdefault("posts", [])
    storage.setdefault("post_settings", {})
    storage.setdefault("pinned_post", {})
    storage.setdefault("button_clicks", {})
    storage.setdefault("start_clicks", {})
    return storage


def _ensure_data_files() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CLIENTS_JSON_FILE):
        with open(CLIENTS_JSON_FILE, "w", encoding="utf-8") as file:
            json.dump({}, file, ensure_ascii=False, indent=2)
    if not os.path.exists(TICKETS_JSON_FILE):
        with open(TICKETS_JSON_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)
    if not os.path.exists(SYSTEM_JSON_FILE):
        with open(SYSTEM_JSON_FILE, "w", encoding="utf-8") as file:
            json.dump({"pinned_message_id": None}, file, ensure_ascii=False, indent=2)


def _github_sync_file(path: str, payload: object, message: str) -> bool:
    token = (os.getenv("CLIENT_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    repo = (os.getenv("CLIENT_GITHUB_REPO") or os.getenv("GITHUB_REPO") or "").strip()
    branch = (os.getenv("CLIENT_GITHUB_BRANCH") or os.getenv("GITHUB_BRANCH") or "main").strip()
    if not token or not repo:
        print("[storage] github sync skipped: token/repo missing")
        return False
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    b64 = base64.b64encode(body).decode("utf-8")
    rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
    url = f"https://api.github.com/repos/{repo}/contents/{rel}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    sha = None
    try:
        get_resp = requests.get(url, headers=headers, timeout=15)
        if get_resp.status_code == 200:
            sha = (get_resp.json() or {}).get("sha")
        req = {"message": message, "content": b64, "branch": branch}
        if sha:
            req["sha"] = sha
        put_resp = requests.put(url, headers=headers, json=req, timeout=20)
        if put_resp.status_code in {200, 201}:
            return True
        print(f"[storage] github sync failed {rel}: status={put_resp.status_code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[storage] github sync failed {rel}: {exc}")
        return False


def _persist_bot_host_files(storage: dict) -> None:
    _ensure_data_files()
    clients_payload = storage.get("client_profiles") or {}
    tickets_payload = storage.get("tickets") or []
    pinned_id = (
        storage.get("settings", {}).get("pinned_message_id")
        or storage.get("pinned_post", {}).get("message_id")
    )
    system_payload = {"pinned_message_id": pinned_id}

    with open(CLIENTS_JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(clients_payload, file, ensure_ascii=False, indent=2)
    with open(TICKETS_JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(tickets_payload, file, ensure_ascii=False, indent=2)
    with open(SYSTEM_JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(system_payload, file, ensure_ascii=False, indent=2)

    now = datetime.utcnow().isoformat() + "Z"
    _github_sync_file(CLIENTS_JSON_FILE, clients_payload, f"Update clients.json ({now})")
    _github_sync_file(TICKETS_JSON_FILE, tickets_payload, f"Update tickets.json ({now})")
    _github_sync_file(SYSTEM_JSON_FILE, system_payload, f"Update system.json ({now})")


def load_storage() -> dict:
    with STORAGE_LOCK:
        if not os.path.exists(STORAGE_FILE):
            return ensure_storage_schema({"tickets": [], "sessions": {}})
        with open(STORAGE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return ensure_storage_schema(data)


def save_storage(data: dict) -> None:
    with STORAGE_LOCK:
        os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
        tmp_path = f"{STORAGE_FILE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STORAGE_FILE)
        _persist_bot_host_files(data)


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
