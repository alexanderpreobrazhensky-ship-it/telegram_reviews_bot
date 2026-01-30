import os
import re
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request
import requests

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://your-app.railway.app/{TOKEN}
DB_PATH = "reviews.db"

# --- Zero-width очистка ---
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return ZERO_WIDTH_PATTERN.sub("", text)

# --- Разбиение длинных сообщений ---
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

# --- Отправка сообщений в Telegram ---
def send_telegram_message(chat_id: int, text: str, keyboard=None):
    text = clean_text(text)
    chunks = split_long_message(text)
    for chunk in chunks:
        data = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if keyboard:
            data["reply_markup"] = {"inline_keyboard": keyboard}
        data["parse_mode"] = "Markdown"
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=data,
            timeout=10
        )
        if response.status_code == 200:
            continue
        logger.warning(f"Markdown error: {response.text}")
        data.pop("parse_mode", None)
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=data,
            timeout=10
        )
        if response.status_code != 200:
            logger.error(f"Telegram send error: {response.text}")
            raise Exception(f"Telegram error: {response.text}")
    return True

# --- Инициализация базы ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            rating INTEGER,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Flask сервер для webhook ---
app = Flask(__name__)

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if not update:
        return "ok"

    message = update.get("message")
    if not message:
        return "ok"

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.startswith("/start"):
        send_telegram_message(chat_id, "Привет! Я бот для анализа отзывов.")
    elif text.startswith("/myid"):
        send_telegram_message(chat_id, f"Твой ID: {chat_id}")
    elif text.startswith("/analyze"):
        review_text = text.replace("/analyze", "").strip()
        if not review_text:
            send_telegram_message(chat_id, "Пожалуйста, пришли текст отзыва после команды.")
        else:
            rating = analyze_review(review_text)
            save_review(chat_id, message["from"].get("username", ""), review_text, rating)
            send_telegram_message(chat_id, f"Рейтинг отзыва: {rating}/5")
    elif text.startswith("/stats"):
        stats_text = get_stats()
        send_telegram_message(chat_id, stats_text)
    elif text.startswith("/report"):
        send_telegram_message(chat_id, "Отчётная функция в разработке.")
    return "ok"

# --- Анализ отзыва ---
def analyze_review(text: str) -> int:
    """
    Здесь вызывается AI движок по умолчанию.
    Для мультидвижка можно добавить проверку переменной окружения AI_ENGINE
    """
    engine = os.getenv("AI_ENGINE", "gptfree")
    # Заглушка: рейтинг 1-5 (можно заменить вызовом API AI)
    return min(5, max(1, len(text) % 6))

# --- Сохранение в базу ---
def save_review(user_id, username, text, rating):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO reviews (user_id, username, text, rating, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, text, rating, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

# --- Статистика ---
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating, COUNT(*) FROM reviews GROUP BY rating")
    rows = c.fetchall()
    conn.close()
    if not rows:
        return "Нет данных."
    return "\n".join([f"Рейтинг {r}: {cnt} отзывов" for r, cnt in rows])

# --- Установка webhook на Railway ---
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    res = requests.post(url, json={"url": WEBHOOK_URL})
    if res.status_code == 200:
        logger.info("Webhook установлен успешно.")
    else:
        logger.error(f"Ошибка установки webhook: {res.text}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)