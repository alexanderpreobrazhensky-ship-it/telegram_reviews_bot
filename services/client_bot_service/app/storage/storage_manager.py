from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.models.client import Client
from app.utils.phone_normalizer import normalize_phone


class StorageManager:
    def __init__(self, data_dir: str = "data") -> None:
        self.base = Path(data_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.clients_path = self.base / "clients.jsonl"
        self.tickets_path = self.base / "tickets.jsonl"
        self.system_path = self.base / "system.json"

    def upsert_client(self, payload: dict) -> Client:
        user_id = int(payload["telegram_user_id"])
        records = self._load_clients()
        existing = records.get(user_id) or {}
        merged = Client(
            telegram_user_id=user_id,
            telegram_username=payload.get("telegram_username") or existing.get("telegram_username", ""),
            full_name=payload.get("full_name") or existing.get("full_name", ""),
            phones=self._merge_list(existing.get("phones", []), [normalize_phone(payload.get("phone"))]),
            car_numbers=self._merge_list(existing.get("car_numbers", []), payload.get("car_numbers", [])),
            vin_codes=self._merge_list(existing.get("vin_codes", []), payload.get("vin_codes", [])),
            vk_username=payload.get("vk_username") or existing.get("vk_username", ""),
            max_username=payload.get("max_username") or existing.get("max_username", ""),
            email=payload.get("email") or existing.get("email", ""),
            created_at=existing.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            source_tags=self._merge_list(existing.get("source_tags", []), payload.get("source_tags", [])),
        )
        records[user_id] = asdict(merged)
        self._write_jsonl(self.clients_path, records.values())
        return merged

    @staticmethod
    def _merge_list(current: list, incoming: list) -> list:
        result = [item for item in current if item]
        for item in incoming:
            if item and item not in result:
                result.append(item)
        return result

    def _load_clients(self) -> dict[int, dict]:
        result: dict[int, dict] = {}
        if not self.clients_path.exists():
            return result
        for line in self.clients_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            result[int(row["telegram_user_id"])] = row
        return result

    @staticmethod
    def _write_jsonl(path: Path, rows) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
