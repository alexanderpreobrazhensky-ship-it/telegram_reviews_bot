import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

VERSION = "0.2.0"
POLLING_TIMEOUT = 30
POLLING_SLEEP_SECONDS = 1


def build_logger(timezone: str) -> logging.Logger:
    logger = logging.getLogger("client_bot")
    logger.setLevel(logging.INFO)

    log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    tz = ZoneInfo(timezone)

    def format_time(record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    formatter.formatTime = format_time

    if not logger.handlers:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def build_start_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Скоро"}]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def send_message(token: str, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()


def handle_update(token: str, update: dict, logger: logging.Logger) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")

    logger.info(
        "update_id=%s chat_id=%s message_id=%s text=%s",
        update.get("update_id"),
        chat_id,
        message.get("message_id"),
        text,
    )

    if not chat_id:
        return

    if text.startswith("/start"):
        send_message(
            token,
            chat_id,
            "Привет! Главное меню скоро появится. Сейчас это заглушка.",
            reply_markup=build_start_keyboard(),
        )


def poll_updates(token: str, logger: logging.Logger) -> None:
    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"

    logger.info("client_bot polling started (version=%s)", VERSION)

    while True:
        try:
            response = requests.get(
                url,
                params={"timeout": POLLING_TIMEOUT, "offset": offset},
                timeout=POLLING_TIMEOUT + 5,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                logger.warning("telegram response not ok: %s", payload)
                time.sleep(POLLING_SLEEP_SECONDS)
                continue

            updates = payload.get("result", [])
            for update in updates:
                offset = max(offset, update.get("update_id", 0) + 1)
                handle_update(token, update, logger)
        except Exception as exc:  # noqa: BLE001 - keep polling on errors
            logger.exception("polling error: %s", exc)
            time.sleep(POLLING_SLEEP_SECONDS)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN_CLIENT")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_CLIENT is required")

    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    logger = build_logger(timezone)
    logger.info("client_bot starting (polling mode)")
    poll_updates(token, logger)


if __name__ == "__main__":
    main()
