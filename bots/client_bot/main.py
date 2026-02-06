import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request

VERSION = "0.1.0"
START_TIME = time.time()


def build_logger(timezone: str) -> logging.Logger:
    logger = logging.getLogger("client_bot")
    logger.setLevel(logging.INFO)

    log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
    handler = logging.FileHandler(log_path)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    tz = ZoneInfo(timezone)

    def format_time(record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    formatter.formatTime = format_time
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
LOGGER = build_logger(TIMEZONE)

app = Flask(__name__)


def extract_update_fields(update: dict) -> dict:
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    user = message.get("from") or {}

    return {
        "update_id": update.get("update_id"),
        "chat_id": chat.get("id"),
        "message_id": message.get("message_id"),
        "username": user.get("username"),
    }


@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    fields = extract_update_fields(payload)
    LOGGER.info(
        "update_id=%s chat_id=%s message_id=%s username=%s",
        fields["update_id"],
        fields["chat_id"],
        fields["message_id"],
        fields["username"],
    )
    return jsonify({"status": "OK"})


@app.get("/health")
def health():
    uptime_seconds = int(time.time() - START_TIME)
    return jsonify(
        {
            "status": "OK",
            "version": VERSION,
            "uptime_seconds": uptime_seconds,
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
