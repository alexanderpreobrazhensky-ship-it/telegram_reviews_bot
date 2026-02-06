import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from services.telegram_api import TgRequestResult, get_retry_base_sleep_seconds, get_retry_max, tg_request
from storage import now_iso, save_storage

OUTGOING_FILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outgoing_files")


def is_queue_enabled() -> bool:
    return os.getenv("CLIENT_TG_QUEUE_ENABLED", "1") != "0"


def ensure_outgoing_schema(storage: dict) -> None:
    storage.setdefault("outgoing_messages", [])
    for message in storage.get("outgoing_messages", []):
        message.setdefault("attempts", 0)
        message.setdefault("status", "pending")
        message.setdefault("last_error", "")
        message.setdefault("next_retry_at", None)
        message.setdefault("message_key", None)
        message.setdefault("ticket_id", None)


def _next_outgoing_id(storage: dict) -> int:
    ensure_outgoing_schema(storage)
    existing = [item.get("id") for item in storage.get("outgoing_messages", [])]
    numeric = [value for value in existing if isinstance(value, int)]
    return (max(numeric) + 1) if numeric else 1


def enqueue_message(
    storage: dict,
    target_chat_id: int | str,
    kind: str,
    text: str,
    reply_markup: dict | None = None,
    disable_web_page_preview: bool = True,
    message_key: str | None = None,
    ticket_id: str | None = None,
    timezone: str = "Europe/Moscow",
) -> int:
    logger = logging.getLogger("client_bot")
    ensure_outgoing_schema(storage)
    if message_key:
        for item in storage.get("outgoing_messages", []):
            if item.get("status") == "pending" and item.get("message_key") == message_key:
                logger.info("outgoing dedup skip key=%s", message_key)
                return int(item.get("id", 0) or 0)
    payload = {
        "method": "sendMessage",
        "text": text,
        "reply_markup": reply_markup,
        "disable_web_page_preview": disable_web_page_preview,
    }
    message_id = _next_outgoing_id(storage)
    storage["outgoing_messages"].append(
        {
            "id": message_id,
            "created_at": now_iso(timezone),
            "target_chat_id": str(target_chat_id),
            "kind": kind,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "attempts": 0,
            "last_error": "",
            "status": "pending",
            "next_retry_at": None,
            "message_key": message_key,
            "ticket_id": ticket_id,
        }
    )
    return message_id


def store_outgoing_file(content: bytes, filename: str) -> str:
    os.makedirs(OUTGOING_FILES_DIR, exist_ok=True)
    safe_name = filename.replace("/", "_")
    unique_name = f"{int(time.time())}_{uuid.uuid4().hex}_{safe_name}"
    path = os.path.join(OUTGOING_FILES_DIR, unique_name)
    with open(path, "wb") as file_handle:
        file_handle.write(content)
    return path


def enqueue_document(
    storage: dict,
    target_chat_id: int | str,
    kind: str,
    file_path: str,
    caption: str | None,
    message_key: str | None = None,
    ticket_id: str | None = None,
    timezone: str = "Europe/Moscow",
) -> int:
    logger = logging.getLogger("client_bot")
    ensure_outgoing_schema(storage)
    if message_key:
        for item in storage.get("outgoing_messages", []):
            if item.get("status") == "pending" and item.get("message_key") == message_key:
                logger.info("outgoing dedup skip key=%s", message_key)
                return int(item.get("id", 0) or 0)
    payload = {
        "method": "sendDocument",
        "file_path": file_path,
        "caption": caption,
    }
    message_id = _next_outgoing_id(storage)
    storage["outgoing_messages"].append(
        {
            "id": message_id,
            "created_at": now_iso(timezone),
            "target_chat_id": str(target_chat_id),
            "kind": kind,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "attempts": 0,
            "last_error": "",
            "status": "pending",
            "next_retry_at": None,
            "message_key": message_key,
            "ticket_id": ticket_id,
        }
    )
    return message_id


def _attempt_send_message(target_chat_id: str, payload: dict[str, Any]) -> TgRequestResult:
    message_payload = {
        "chat_id": target_chat_id,
        "text": payload.get("text", ""),
        "disable_web_page_preview": payload.get("disable_web_page_preview", True),
    }
    reply_markup = payload.get("reply_markup")
    if reply_markup:
        message_payload["reply_markup"] = reply_markup
    return tg_request("sendMessage", message_payload)


def _attempt_send_document(target_chat_id: str, payload: dict[str, Any]) -> TgRequestResult:
    file_path = payload.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return TgRequestResult(False, False, None, "file missing")
    data: dict[str, Any] = {"chat_id": target_chat_id}
    caption = payload.get("caption")
    if caption:
        data["caption"] = caption
    with open(file_path, "rb") as file_handle:
        return tg_request("sendDocument", None, files={"document": file_handle}, data=data)


def process_outgoing_queue(
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    batch_size: int = 20,
) -> dict:
    ensure_outgoing_schema(storage)
    now_value = datetime.now(ZoneInfo(timezone))
    pending = []
    for item in storage.get("outgoing_messages", []):
        if item.get("status") != "pending":
            continue
        next_retry_at = item.get("next_retry_at")
        if next_retry_at:
            try:
                retry_dt = datetime.fromisoformat(next_retry_at).astimezone(ZoneInfo(timezone))
                if retry_dt > now_value:
                    continue
            except ValueError:
                pass
        pending.append(item)
    if not pending:
        return {"processed": 0, "sent": 0, "failed": 0}

    retry_max = get_retry_max()
    base_sleep = get_retry_base_sleep_seconds()
    processed = 0
    sent = 0
    failed = 0
    updated = False

    for message in pending[:batch_size]:
        processed += 1
        payload_raw = message.get("payload_json") or "{}"
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
        method = payload.get("method")
        target_chat_id = message.get("target_chat_id")
        attempts = int(message.get("attempts", 0)) + 1
        message["attempts"] = attempts

        result: TgRequestResult
        if method == "sendDocument":
            result = _attempt_send_document(target_chat_id, payload)
        else:
            result = _attempt_send_message(target_chat_id, payload)

        if result.ok:
            message["status"] = "sent"
            message["last_error"] = ""
            message["next_retry_at"] = None
            sent += 1
        else:
            error_message = result.error or "unknown_error"
            message["last_error"] = error_message
            if result.retryable and attempts < retry_max:
                message["status"] = "pending"
                retry_after = result.retry_after_seconds
                if retry_after is None:
                    retry_after = base_sleep * (2 ** (attempts - 1))
                message["next_retry_at"] = (now_value + timedelta(seconds=retry_after)).isoformat()
            else:
                message["status"] = "failed"
                message["next_retry_at"] = None
                failed += 1
            logger.warning(
                "outgoing message failed id=%s chat_id=%s kind=%s attempt=%s error=%s",
                message.get("id"),
                target_chat_id,
                message.get("kind"),
                attempts,
                error_message,
            )
        updated = True

    if updated:
        save_storage(storage)
    return {"processed": processed, "sent": sent, "failed": failed}


def get_queue_stats(storage: dict, timezone: str, hours: int = 24) -> dict:
    ensure_outgoing_schema(storage)
    cutoff = datetime.now(ZoneInfo(timezone)) - timedelta(hours=hours)
    stats = {"pending": 0, "sent": 0, "failed": 0}
    for message in storage.get("outgoing_messages", []):
        created_at = message.get("created_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
            except ValueError:
                created_dt = None
            if created_dt and created_dt < cutoff:
                continue
        status = message.get("status")
        if status in stats:
            stats[status] += 1
    return stats


def get_failed_messages(storage: dict, timezone: str, limit: int = 5) -> list[dict]:
    ensure_outgoing_schema(storage)
    failed = [item for item in storage.get("outgoing_messages", []) if item.get("status") == "failed"]
    failed.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return failed[:limit]


def retry_failed_messages(storage: dict, timezone: str, logger: logging.Logger) -> int:
    ensure_outgoing_schema(storage)
    now_value = now_iso(timezone)
    count = 0
    for message in storage.get("outgoing_messages", []):
        if message.get("status") != "failed":
            continue
        message["status"] = "pending"
        message["next_retry_at"] = now_value
        count += 1
    if count:
        save_storage(storage)
        logger.info("outgoing retry failed count=%s", count)
    return count


def clear_failed_messages(storage: dict, timezone: str, logger: logging.Logger) -> int:
    ensure_outgoing_schema(storage)
    count = 0
    for message in storage.get("outgoing_messages", []):
        if message.get("status") != "failed":
            continue
        message["status"] = "archived"
        count += 1
    if count:
        save_storage(storage)
        logger.info("outgoing archived failed count=%s", count)
    return count


def get_outgoing_by_id(storage: dict, message_id: int) -> dict | None:
    ensure_outgoing_schema(storage)
    for message in storage.get("outgoing_messages", []):
        if int(message.get("id", 0) or 0) == message_id:
            return message
    return None


def get_last_queue_error(storage: dict) -> str:
    ensure_outgoing_schema(storage)
    for message in reversed(storage.get("outgoing_messages", [])):
        error = message.get("last_error")
        if error:
            return error
    return "—"
