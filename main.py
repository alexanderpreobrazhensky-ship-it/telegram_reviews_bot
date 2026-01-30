# main.py
import os
import re
import logging
import sqlite3
import requests
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# ENV & CONFIG
# ======================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # public URL Railway + токен
AI_ENGINE = os.environ.get("AI_ENGINE", "gptfree")  # по умолчанию gptfree

# ======================
# ZERO-WIDTH CLEAN
# ======================
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")

def clean_text(text: str) -> str:
    """Удаляем опасные zero-width символы"""
    if not isinstance(text, str):
        text = str(text)
    text = ZERO_WIDTH_PATTERN.sub("", text)
    return text

# ======================
# SPLIT LONG MESSAGE
# ======================
def split_long_message(text: str, limit: int = 4000):
    chunks = []
    while len(text) > limit:
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = limit
        chunks.append(text[:split_pos])
        text = text[split_pos:]
    chunks.append(text)
    return chunks

# ======================
# TELEGRAM SEND
# ======================
def send_telegram_message(chat_id: int, text: str, keyboard=None):
    text = clean_text(text)
    chunks = split_long_message(text)

    for chunk in chunks:
        data = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if keyboard:
            data["reply_markup"] = {"inline_keyboard": keyboard}
        # Markdown attempt
        data["parse_mode"] = "Markdown"
        response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                                 json=data, timeout=10)
        if response.status_code == 200:
            continue
        # fallback plain
        logger.warning(f"Markdown error: {response.text}")
        data.pop("parse_mode", None)
        response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                                 json=data, timeout=10)
        if response.status_code != 200:
            logger.error(f"Telegram send error: {response.text}")
            raise Exception(f"Telegram error: {response.text}")
    return True

# ======================
# SQLITE SETUP
# ======================
DB_FILE = "reviews.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    rating INTEGER
)
""")
conn.commit()

# ======================
# AI ANALYSIS
# ======================
def analyze_review(text: str) -> int:
    """Возвращает рейтинг 1-5 с использованием выбранного AI"""
    text = clean_text(text)
    if AI_ENGINE.lower() == "gptfree":
        # GPTFREE PUBLIC API (условный пример)
        try:
            payload = {"input": f"Оцени отзыв от 1 до 5: {text}"}
            resp = requests.post("https://gptfree-api.herokuapp.com/api/v1/predict", json=payload, timeout=10)
            if resp.status_code == 200:
                result = resp.json()
                rating = int(result.get("output", 3))  # default 3
                rating = max(1, min(rating, 5))
                return rating
        except Exception as e:
            logger.error(f"gptfree error: {e}")
            return 3
    # другие движки placeholder
    return 3

# ======================
# FLASK APP
# ======================
app = Flask(__name__)

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" not in data:
        return jsonify({"ok": True})
    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.startswith("/start"):
        send_telegram_message(chat_id, "Привет! Я бот для анализа отзывов.")
    elif text.startswith("/myid"):
        send_telegram_message(chat_id, f"Ваш ID: {chat_id}")
    elif text.startswith("/analyze"):
        review_text = text.replace("/analyze", "").strip()
        if not review_text:
            send_telegram_message(chat_id, "Пожалуйста, введите текст отзыва после команды /analyze")
        else:
            rating = analyze_review(review_text)
            cursor.execute("INSERT INTO reviews (user_id, text, rating) VALUES (?, ?, ?)",
                           (chat_id, review_text, rating))
            conn.commit()
            send_telegram_message(chat_id, f"Рейтинг: {rating}/5")
    elif text.startswith("/stats"):
        cursor.execute("SELECT COUNT(*), AVG(rating) FROM reviews")
        count, avg = cursor.fetchone()
        avg = round(avg or 0, 2)
        send_telegram_message(chat_id, f"Всего отзывов: {count}\nСредний рейтинг: {avg}")
    else:
        send_telegram_message(chat_id, "Неизвестная команда. Используйте /start, /myid, /analyze, /stats")
    return jsonify({"ok": True})

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={url}")
    return jsonify(resp.json())

@app.route("/debug", methods=["GET"])
def debug():
    return jsonify({"ok": True, "ai_engine": AI_ENGINE})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)