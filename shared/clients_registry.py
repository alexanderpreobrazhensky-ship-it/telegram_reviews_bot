from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "clients.jsonl"
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_SLEEP_SECONDS = 0.05


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def registry_path() -> Path:
    raw = (os.getenv("CLIENTS_REGISTRY_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_REGISTRY_PATH


@contextmanager
def _file_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    started = time.monotonic()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() - started >= LOCK_TIMEOUT_SECONDS:
                raise TimeoutError(f"clients registry lock timeout: {lock_path}")
            time.sleep(LOCK_SLEEP_SECONDS)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _read_all(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            row = line.strip()
            if not row:
                continue
            try:
                obj = json.loads(row)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                result.append(obj)
    return result


def _write_all(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for item in records:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    os.replace(temp_name, path)


def _norm_username(username: Any) -> str | None:
    if username is None:
        return None
    value = str(username).strip().lstrip("@")
    return value or None


def _as_unique_list(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, list):
        return out
    for item in values:
        if item is None:
            continue
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _merge_unique(base: list[str], extra: list[str]) -> list[str]:
    merged = list(base)
    seen = set(base)
    for item in extra:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _record_key(record: dict[str, Any]) -> tuple[str | None, str | None]:
    user_id = record.get("telegram_user_id")
    username = _norm_username(record.get("telegram_username"))
    return (str(user_id).strip() if user_id is not None and str(user_id).strip() else None, username)


def upsert_client(client: dict[str, Any], source_tag: str | None = None) -> dict[str, Any]:
    path = registry_path()
    now = _utc_now_iso()

    incoming_id = client.get("telegram_user_id")
    incoming_id = str(incoming_id).strip() if incoming_id is not None and str(incoming_id).strip() else None
    incoming_username = _norm_username(client.get("telegram_username"))

    phones = _as_unique_list(client.get("phones") or ([client.get("phone")] if client.get("phone") else []))
    cars = _as_unique_list(client.get("car_numbers") or ([client.get("car_number")] if client.get("car_number") else []))
    vins = _as_unique_list(client.get("vin_codes") or ([client.get("vin")] if client.get("vin") else []))

    with _file_lock(path):
        records = _read_all(path)
        match_index = None
        for idx, record in enumerate(records):
            rec_id, rec_username = _record_key(record)
            if incoming_id and rec_id == incoming_id:
                match_index = idx
                break
            if not incoming_id and incoming_username and rec_username == incoming_username:
                match_index = idx
                break

        if match_index is None:
            base: dict[str, Any] = {
                "telegram_user_id": incoming_id,
                "telegram_username": incoming_username,
                "full_name": client.get("full_name") or "",
                "phones": [],
                "car_numbers": [],
                "vin_codes": [],
                "email": None,
                "vk_username": None,
                "max_username": None,
                "created_at": now,
                "updated_at": now,
                "source_tags": [],
            }
            records.append(base)
            match_index = len(records) - 1
        else:
            base = records[match_index]

        base["telegram_user_id"] = incoming_id or base.get("telegram_user_id")
        base["telegram_username"] = incoming_username or _norm_username(base.get("telegram_username"))
        if not base.get("full_name") and client.get("full_name"):
            base["full_name"] = str(client.get("full_name")).strip()

        base["phones"] = _merge_unique(_as_unique_list(base.get("phones")), phones)
        base["car_numbers"] = _merge_unique(_as_unique_list(base.get("car_numbers")), cars)
        base["vin_codes"] = _merge_unique(_as_unique_list(base.get("vin_codes")), vins)

        for nullable in ("email", "vk_username", "max_username"):
            if client.get(nullable):
                base[nullable] = str(client.get(nullable)).strip()

        tags = _as_unique_list(base.get("source_tags"))
        if source_tag:
            tags = _merge_unique(tags, [source_tag])
        for extra_tag in _as_unique_list(client.get("source_tags")):
            tags = _merge_unique(tags, [extra_tag])
        base["source_tags"] = tags
        base["updated_at"] = now
        if not base.get("created_at"):
            base["created_at"] = now

        records[match_index] = base
        _write_all(path, records)
        return base
