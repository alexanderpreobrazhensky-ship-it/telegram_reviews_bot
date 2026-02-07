import html
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_RETRY_MAX = 5
DEFAULT_RETRY_BASE_SLEEP_SECONDS = 1

_TOKEN: str | None = None


def configure_telegram(token: str) -> None:
    global _TOKEN
    _TOKEN = token.strip() if token else None


def get_timeout_seconds() -> int:
    value = os.getenv("CLIENT_TG_TIMEOUT_SECONDS", "")
    if value.strip().isdigit():
        return int(value)
    return DEFAULT_TIMEOUT_SECONDS


def get_retry_max() -> int:
    value = os.getenv("CLIENT_TG_RETRY_MAX", "")
    if value.strip().isdigit():
        return int(value)
    return DEFAULT_RETRY_MAX


def get_retry_base_sleep_seconds() -> int:
    value = os.getenv("CLIENT_TG_RETRY_BASE_SLEEP_SECONDS", "")
    if value.strip().isdigit():
        return int(value)
    return DEFAULT_RETRY_BASE_SLEEP_SECONDS


@dataclass
class TgRequestResult:
    ok: bool
    retryable: bool
    status_code: int | None
    error: str | None
    retry_after_seconds: int | None = None
    response_json: dict[str, Any] | None = None


def _log_attempt(logger: logging.Logger, method: str, chat_id: Any, status_code: Any, attempt: int, reason: str) -> None:
    logger.info(
        "telegram request method=%s chat_id=%s status_code=%s attempt=%s reason=%s",
        method,
        chat_id,
        status_code,
        attempt,
        reason,
    )


def tg_request(
    method: str,
    payload: dict[str, Any] | None,
    *,
    files: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> TgRequestResult:
    logger = logging.getLogger("client_bot")
    if not _TOKEN:
        logger.error("telegram request skipped: token is not configured")
        return TgRequestResult(False, False, None, "token is not configured")

    url = f"https://api.telegram.org/bot{_TOKEN}/{method}"
    retries = get_retry_max()
    base_sleep = get_retry_base_sleep_seconds()
    timeout_seconds = timeout or get_timeout_seconds()

    payload_chat_id = None
    if payload and "chat_id" in payload:
        payload_chat_id = payload.get("chat_id")
    elif data and "chat_id" in data:
        payload_chat_id = data.get("chat_id")

    retry_after_seconds: int | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                url,
                json=payload if payload is not None and files is None and data is None else None,
                data=data,
                files=files,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            reason = f"request_error={exc}"
            _log_attempt(logger, method, payload_chat_id, None, attempt, reason)
            if attempt >= retries:
                return TgRequestResult(False, True, None, reason, retry_after_seconds)
            sleep_seconds = base_sleep * (2 ** (attempt - 1))
            time.sleep(sleep_seconds + random.uniform(0.05, 0.3))
            continue

        status_code = response.status_code
        response_text = response.text
        response_json: dict[str, Any] | None = None
        try:
            response_json = response.json()
        except (ValueError, json.JSONDecodeError):
            response_json = None

        if status_code == 429:
            retry_after = 1
            if response_json:
                retry_after = int(response_json.get("parameters", {}).get("retry_after", 1))
            reason = f"http_429 retry_after={retry_after}"
            _log_attempt(logger, method, payload_chat_id, status_code, attempt, reason)
            retry_after_seconds = retry_after
            if attempt >= retries:
                return TgRequestResult(False, True, status_code, reason, retry_after_seconds, response_json)
            time.sleep(retry_after + random.uniform(0.1, 0.4))
            continue

        if status_code >= 500:
            reason = f"http_{status_code}"
            _log_attempt(logger, method, payload_chat_id, status_code, attempt, reason)
            if attempt >= retries:
                return TgRequestResult(False, True, status_code, reason, retry_after_seconds, response_json)
            sleep_seconds = base_sleep * (2 ** (attempt - 1))
            time.sleep(sleep_seconds + random.uniform(0.05, 0.3))
            continue

        if status_code in {400, 403}:
            reason = f"http_{status_code} body={response_text}"
            _log_attempt(logger, method, payload_chat_id, status_code, attempt, reason)
            return TgRequestResult(False, False, status_code, reason, retry_after_seconds, response_json)

        if status_code >= 400:
            reason = f"http_{status_code}"
            _log_attempt(logger, method, payload_chat_id, status_code, attempt, reason)
            return TgRequestResult(False, False, status_code, reason, retry_after_seconds, response_json)

        reason = "ok"
        _log_attempt(logger, method, payload_chat_id, status_code, attempt, reason)
        return TgRequestResult(True, False, status_code, None, retry_after_seconds, response_json)

    return TgRequestResult(False, True, None, "unknown_error", retry_after_seconds)


def _escape_html_text(text: str, allow_html: bool) -> str:
    if allow_html:
        return text
    return html.escape(text)


def send_message(
    chat_id: int | str,
    text: str,
    reply_markup: dict | None = None,
    disable_web_page_preview: bool = True,
    parse_mode: str | None = "HTML",
    allow_html: bool = False,
) -> bool:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": _escape_html_text(text, allow_html),
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = tg_request("sendMessage", payload)
    return result.ok


def send_document(
    chat_id: int | str,
    file_path: str,
    caption: str | None = None,
    parse_mode: str | None = "HTML",
    allow_html: bool = False,
) -> bool:
    logger = logging.getLogger("client_bot")
    if not os.path.exists(file_path):
        logger.error("telegram sendDocument missing file chat_id=%s path=%s", chat_id, file_path)
        return False
    data: dict[str, Any] = {"chat_id": chat_id}
    if caption:
        data["caption"] = _escape_html_text(caption, allow_html)
        if parse_mode:
            data["parse_mode"] = parse_mode
    try:
        with open(file_path, "rb") as file_handle:
            result = tg_request("sendDocument", None, files={"document": file_handle}, data=data)
    except OSError as exc:
        logger.error("telegram sendDocument file error chat_id=%s error=%s", chat_id, exc)
        return False
    return result.ok


def send_photo(
    chat_id: int | str,
    photo: str,
    caption: str | None = None,
    parse_mode: str | None = "HTML",
    allow_html: bool = False,
) -> TgRequestResult:
    data: dict[str, Any] = {"chat_id": chat_id}
    if caption:
        data["caption"] = _escape_html_text(caption, allow_html)
        if parse_mode:
            data["parse_mode"] = parse_mode
    if os.path.exists(photo):
        try:
            with open(photo, "rb") as file_handle:
                return tg_request("sendPhoto", None, files={"photo": file_handle}, data=data)
        except OSError as exc:
            logger = logging.getLogger("client_bot")
            logger.error("telegram sendPhoto file error chat_id=%s error=%s", chat_id, exc)
            return TgRequestResult(False, False, None, str(exc))
    payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
    if caption:
        payload["caption"] = _escape_html_text(caption, allow_html)
        if parse_mode:
            payload["parse_mode"] = parse_mode
    return tg_request("sendPhoto", payload)


def edit_message_text(
    chat_id: int | str,
    message_id: int,
    text: str,
    parse_mode: str | None = "HTML",
    allow_html: bool = False,
) -> TgRequestResult:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": _escape_html_text(text, allow_html),
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return tg_request("editMessageText", payload)


def edit_message_caption(
    chat_id: int | str,
    message_id: int,
    caption: str,
    parse_mode: str | None = "HTML",
    allow_html: bool = False,
) -> TgRequestResult:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": _escape_html_text(caption, allow_html),
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return tg_request("editMessageCaption", payload)


def edit_message_media(
    chat_id: int | str,
    message_id: int,
    photo_file_id: str,
    caption: str | None = None,
    parse_mode: str | None = "HTML",
    allow_html: bool = False,
) -> TgRequestResult:
    media: dict[str, Any] = {"type": "photo", "media": photo_file_id}
    if caption:
        media["caption"] = _escape_html_text(caption, allow_html)
        if parse_mode:
            media["parse_mode"] = parse_mode
    payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "media": media}
    return tg_request("editMessageMedia", payload)


def pin_chat_message(chat_id: int | str, message_id: int) -> TgRequestResult:
    payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
    return tg_request("pinChatMessage", payload)


def unpin_chat_message(chat_id: int | str, message_id: int) -> TgRequestResult:
    payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
    return tg_request("unpinChatMessage", payload)


def answer_callback_query(callback_query_id: str, text: str | None = None) -> bool:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    result = tg_request("answerCallbackQuery", payload)
    return result.ok
