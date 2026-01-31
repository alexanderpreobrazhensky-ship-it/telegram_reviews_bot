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
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("review-bot")

# -------------------------
# Env
# -------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения!")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("⚠ GEMINI_API_KEY отсутствует — анализ будет работать в fallback-режиме")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например: https://xxxx.up.railway.app
if not WEBHOOK_URL:
    raise ValueError("Не задан WEBHOOK_URL!")

# Секрет для пути вебхука (НЕ токен!)
BOT_PATH_SECRET = os.getenv("BOT_PATH_SECRET", "hook")
WEBHOOK_PATH = f"/webhook/{BOT_PATH_SECRET}"

# Таймауты
TG_TIMEOUT = float(os.getenv("TG_TIMEOUT", "10"))
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "8"))

# Gemini endpoint
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

app = Flask(__name__)

# -------------------------
# Telegram helpers
# -------------------------
def tg_send_message(chat_id: int, text: str, reply_to: Optional[int] = None) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

    try:
        r = requests.post(url, json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("Ошибка отправки сообщения: %s", r.text[:500])
    except Exception as e:
        logger.exception("Исключение при sendMessage: %s", e)

def set_webhook() -> None:
    full_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
    logger.info("Setting webhook: %s", full_url)

    try:
        # Надёжнее, чем GET со строкой
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": full_url},
            timeout=TG_TIMEOUT,
        )
        logger.info("setWebhook status=%s body=%s", r.status_code, r.text[:500])
    except Exception as e:
        logger.exception("Ошибка установки webhook: %s", e)

# ВАЖНО: под gunicorn __main__ не выполняется, поэтому ставим webhook при импорте.
# Это выполнится на старте каждого worker — обычно безопасно (повторная установка webhook не страшна).
if os.getenv("DISABLE_WEBHOOK_SETUP", "0") != "1":
    set_webhook()

# -------------------------
# Gemini helper
# -------------------------
def analyze_with_gemini(review_text: str) -> str:
    if not GEMINI_API_KEY:
        return (
            "❌ Gemini не настроен (нет GEMINI_API_KEY).\n"
            "Могу работать только в fallback-режиме."
        )

    prompt = (
        "Ты — аналитик клиентских отзывов. Проанализируй отзыв и верни:\n"
        "1) Тональность (позитив/нейтр/негатив)\n"
        "2) Основные темы (список)\n"
        "3) Ключевые проблемы (если есть)\n"
        "4) Рекомендации бизнесу (2-5 пунктов)\n"
        "5) Короткое резюме в 1-2 предложения\n\n"
        f"Отзыв:\n{review_text}"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }

    try:
        # В официальных примерах ключ — как query parameter ?key=... :contentReference[oaicite:3]{index=3}
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=GEMINI_TIMEOUT,
        )
        logger.info("Gemini raw: %s", resp.text[:1200])
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return "❌ Gemini вернул пустой ответ (нет candidates)"

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return "❌ Gemini вернул ответ без parts"

        result_text = (parts[0].get("text") or "").strip()
        return result_text or "❌ Gemini прислал пустой текст"

    except Exception as e:
        logger.exception("Ошибка Gemini: %s", e)
        return "❌ Ошибка обращения к Gemini (ключ/лимиты/таймаут)."

def background_analyze_and_reply(chat_id: int, text: str, reply_to: Optional[int]) -> None:
    try:
        result = analyze_with_gemini(text)
        tg_send_message(chat_id, result, reply_to=None)
    except Exception as e:
        logger.exception("Background worker failed: %s", e)
        tg_send_message(
            chat_id,
            "❌ Внутренняя ошибка при анализе. Попробуй позже.",
            reply_to=None,
        )

# -------------------------
# Routes
# -------------------------
@app.get("/")
def health():
    return {
        "ok": True,
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "model": GEMINI_MODEL,
    }, 200

@app.post(WEBHOOK_PATH)
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    logger.info("Update: %s", json.dumps(update)[:1200])

    message = update.get("message") or update.get("edited_message")
    if not message:
        return "ok", 200

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    msg_id = message.get("message_id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return "ok", 200

    logger.info("Parsed: chat_id=%s user_id=%s text=%r", chat_id, user_id, text)

    if not text:
        tg_send_message(chat_id, "Я принимаю только текст 🙂", reply_to=msg_id)
        return "ok", 200

    # Команды
    if text.startswith("/start"):
        tg_send_message(chat_id, "Привет! Я бот для анализа отзывов.", reply_to=msg_id)
        return "ok", 200

    if text.startswith("/help"):
        tg_send_message(
            chat_id,
            "/start — начать\n"
            "/help — помощь\n"
            "/myid — ваш ID\n"
            "/analyze текст — анализ",
            reply_to=msg_id,
        )
        return "ok", 200

    if text.startswith("/myid"):
        # Правильный ID пользователя — from.id, а не chat_id
        tg_send_message(chat_id, f"Ваш user_id: {user_id}\nВаш chat_id: {chat_id}", reply_to=msg_id)
        return "ok", 200

    # Анализ
    if text.startswith("/analyze"):
        analyze_text = text.replace("/analyze", "", 1).strip()
        if not analyze_text:
            tg_send_message(chat_id, "Введите текст после команды /analyze", reply_to=msg_id)
            return "ok", 200

        # Мгновенно подтверждаем, а работу делаем в фоне
        tg_send_message(chat_id, "Принял ✅ Анализирую…", reply_to=msg_id)
        threading.Thread(
            target=background_analyze_and_reply,
            args=(chat_id, analyze_text, msg_id),
            daemon=True,
        ).start()

        return "ok", 200

    # Если просто текст — тоже анализируем, но так же в фоне
    tg_send_message(chat_id, "Принял ✅ Анализирую…", reply_to=msg_id)
    threading.Thread(
        target=background_analyze_and_reply,
        args=(chat_id, text, msg_id),
        daemon=True,
    ).start()

    return "ok", 200
