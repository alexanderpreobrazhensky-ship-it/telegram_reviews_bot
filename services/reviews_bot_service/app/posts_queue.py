from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
QUEUE_JSON = DATA_DIR / "posts_queue.json"
LEGACY_JSONL = DATA_DIR / "posts_queue.jsonl"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        row = line.strip()
        if not row:
            continue
        try:
            obj = json.loads(row)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            items.append(obj)
    return items


def ensure_posts_queue_storage() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if QUEUE_JSON.exists():
        return QUEUE_JSON

    posts: list[dict[str, Any]] = []
    if LEGACY_JSONL.exists():
        posts = _load_jsonl(LEGACY_JSONL)

    QUEUE_JSON.write_text(
        json.dumps({"posts": posts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return QUEUE_JSON
