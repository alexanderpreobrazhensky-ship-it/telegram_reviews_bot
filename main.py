import os
import json
import logging
import threading
from typing import Any, Dict, Optional

import requests
from flask import Flask, request

# -------------------------
# Logging
# -------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("review-bot")

# -------------------------
# Env (Telegram)
# -------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://<railway-domain>
if not WEBHOOK_URL:
    raise ValueError("Missing WEBHOOK_URL")

BOT_PATH_SECRET = os.getenv("BOT_PATH_SECRET", "hook")
WEBHOOK_PATH = f"/webhook/{BOT_PATH_SECRET}"

TG_TIMEOUT = float(os.getenv("TG_TIMEOUT", "10"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "12"))

# -------------------------
# Env (AI multi-engine)
# -------------------------
AI_ENGINE = (os.getenv("AI_ENGINE") or "deepseek").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")  # на всякий случай

# Models (override via env if you want)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-beta")

# Endpoints
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
GROK_URL = os.getenv("GROK_URL", "https://api.x.ai/v1/chat/completions")

# -------------------------
# Flask
# -------------------------
app = Flask(__name__)

# -------------------------
# Helpers: redaction (avoid leaking keys)
# -------------------------
def _redact(s: str) -> str:
    if not s:
        return s
    # crude but effective: hide common key patterns in logs
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
    full_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
    logger.info("Setting webhook: %s", full_url)

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": full_url},
            timeout=TG_TIMEOUT,
        )
        # 429 здесь возможен, если несколько воркеров одновременно поставили вебхук.
        if r.status_code == 429:
            logger.warning("setWebhook got 429 (ignored): %s", _redact(r.text[:500]))
            return
        if r.status_code != 200:
            logger.error("setWebhook failed status=%s body=%s", r.status_code, _redact(r.text[:800]))
        else:
            logger.info("setWebhook OK: %s", _redact(r.text[:500]))
    except Exception as e:
        logger.exception("set_webhook exception: %s", e)

# ставим webhook при старте (под gunicorn тоже)
if os.getenv("DISABLE_WEBHOOK_SETUP", "0") != "1":
    set_webhook()

# -------------------------
# Prompt builder (unified)
# -------------------------
def build_review_prompt(review_text: str) -> str:
    return (
        "Ты — аналитик клиентских отзывов. Проанализируй отзыв и верни:\n"
        "1) Тональность (позитив/нейтр/негатив)\n"
        "2) Основные темы (список)\n"
        "3) Ключевые проблемы (если есть)\n"
        "4) Рекомендации бизнесу (2-5 пунктов)\n"
        "5) Короткое резюме в 1-2 предло
