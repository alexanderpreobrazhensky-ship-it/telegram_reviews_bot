import os
import json
import logging
import threading
import csv
import io
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

import requests
from flask import Flask, request

# -------------------------
# Logging
# -------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telegram-reviews-bot")

# -------------------------
# Telegram env
# -------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("Missing WEBHOOK_URL")

BOT_PATH_SECRET = os.getenv("BOT_PATH_SECRET", "hook")
WEBHOOK_PATH = f"/webhook/{BOT_PATH_SECRET}"

TG_TIMEOUT = float(os.getenv("TG_TIMEOUT", "10"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "12"))

# -------------------------
# Admins
# -------------------------
REPORT_CHAT_IDS_RAW = (os.getenv("REPORT_CHAT_IDS") or "").strip()

def parse_admin_ids(raw: str) -> List[int]:
    if not raw:
        return []
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except Exception:
            logger.warning("Invalid REPORT_CHAT_IDS entry: %r", part)
    return out

ADMIN_CHAT_IDS = parse_admin_ids(REPORT_CHAT_IDS_RAW)
if not ADMIN_CHAT_IDS:
    logger.warning("REPORT_CHAT_IDS is empty -> admin commands allowed for everyone (NOT recommended).")

def is_admin(chat_id: int) -> bool:
    return (not ADMIN_CHAT_IDS) or (chat_id in ADMIN_CHAT_IDS)

# -------------------------
# AI multi-engine env
# -------------------------
AI_ENGINE = (os.getenv("AI_ENGINE") or "deepseek").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-beta")

# Endpoints
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")

# DeepSeek via proxy base
DEEPSEEK_BASE_URL = (os.getenv("DEEPSEEK_BASE_URL") or "").strip()
if DEEPSEEK_BASE_URL:
    DEEPSEEK_URL = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
else:
    DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")

GROK_URL = os.getenv("GROK_URL", "https://api.x.ai/v1/chat/completions")

# -------------------------
# DB (Postgres on Railway or SQLite fallback)
# -------------------------
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")
SQL_PARAM = "%s" if USE_POSTGRES else "?"

# psycopg v3 (binary wheels) — не требует libpq.so.5 в системе
if USE_POSTGRES:
    try:
        import psycopg
    except Exception as e:
        raise RuntimeError(
            "Postgres detected (DATABASE_URL set) but psycopg is not available. "
            "Install psycopg[binary]==3.x in requirements.txt"
        ) from e

def db_connect():
    if USE_POSTGRES:
        return psycopg.connect(DATABASE_URL)
    else:
        import sqlite3
        conn = sqlite3.connect("reviews.db")
        conn.row_factory = sqlite3.Row
        return conn

def db_init():
    if USE_POSTGRES:
        ddl = """
        CREATE TABLE IF NOT EXISTS reviews (
          id               SERIAL PRIMARY KEY,
          source           TEXT NOT NULL,
          rating           INTEGER NULL,
          author           TEXT NULL,
          url              TEXT NULL,
          published_at     TIMESTAMP NULL,
          text             TEXT NOT NULL,
          added_by_user_id BIGINT NULL,
          added_by_chat_id BIGINT NULL,
          created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    else:
        ddl = """
        CREATE TABLE IF NOT EXISTS reviews (
          id               INTEGER PRIMARY KEY AUTOINCREMENT,
          source           TEXT NOT NULL,
          rating           INTEGER NULL,
          author           TEXT NULL,
          url              TEXT NULL,
          published_at     TEXT NULL,
          text             TEXT NOT NULL,
          added_by_user_id INTEGER NULL,
          added_by_chat_id INTEGER NULL,
          created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(ddl)
        conn.commit()
        logger.info("DB init OK (postgres=%s)", USE_POSTGRES)
    finally:
        conn.close()

db_init()

# -------------------------
# Flask
# -------------------------
app = Flask(__name__)

# -------------------------
# Helpers: redact secrets in logs
# -------------------------
def _redact(s: str) -> str:
    if not s:
        return s
    for key in [GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, GROK_API_KEY]:
        if key and key in s:
            s = s.replace(key, "***REDACTED***")
    return s

# -------------------------
# Telegram API
# -------------------------
def tg_send_message(chat_id: int, text: str, reply_to: Optional[int] = None) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

    try:
        r = requests.post(url, json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("Telegram sendMessage failed: %s", _redact(r.text[:800]))
    except Exception as e:
        logger.exception("Telegram sendMessage exception: %s", e)

def set_webhook() -> None:
    full
