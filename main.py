import os
import re
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request
import requests

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DB_PATH = "reviews.db"

# Проверяем и корректируем WEBHOOK_URL
if WEBHOOK_URL:
    logger.info(f"Получен WEBHOOK_URL: {WEBHOOK_URL}")
    # Если в URL есть токен в конце - убираем его
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN in WEBHOOK_URL:
        logger.warning("WEBHOOK_URL содержит токен! Убираем...")
        WEBHOOK_URL = WEBHOOK_URL.replace(f"/{TELEGRAM_BOT_TOKEN}", "")
    # Убедимся, что URL заканчивается на /
    if not WEBHOOK_URL.endswith("/"):
        WEBHOOK_URL = WEBHOOK_URL + "/"
    logger.info(f"Используется WEBHOOK_URL: {WEBHOOK_URL}")
else:
    logger.error("WEBHOOK_URL не задан в переменных окружения!")

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

# ИСПРАВЛЕННЫЙ ПУТЬ: принимаем запросы на корневой URL
@app.route("/", methods=["POST"])
def telegram_webhook():
    logger.info("Получен запрос от Telegram")
    
    update = request.get_json()
    if not update:
        logger.warning("Пустой запрос от Telegram")
        return "ok"

    message = update.get("message")
    if not message:
        logger.warning("Нет сообщения в запросе")
        return "ok"

    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    username = message["from"].get("username", "")
    user_id = message["from"].get("id", "")
    
    logger.info(f"Сообщение от @{username} (ID: {user_id}): {text[:50]}...")

    if text.startswith("/start"):
        send_telegram_message(chat_id, "Привет! Я бот для анализа отзывов.\n\nДоступные команды:\n/analyze [текст] - анализ отзыва\n/stats - статистика\n/myid - ваш ID")
    elif text.startswith("/myid"):
        send_telegram_message(chat_id, f"👤 Ваш ID: {chat_id}\n👤 Username: @{username}")
    elif text.startswith("/analyze"):
        review_text = text.replace("/analyze", "").strip()
        if not review_text:
            send_telegram_message(chat_id, "Пожалуйста, пришли текст отзыва после команды /analyze")
        else:
            rating = analyze_review(review_text)
            save_review(chat_id, username, review_text, rating)
            send_telegram_message(chat_id, f"📊 Рейтинг отзыва: {rating}/5\n\nТекст: {review_text[:200]}...")
    elif text.startswith("/stats"):
        stats_text = get_stats()
        send_telegram_message(chat_id, stats_text)
    elif text.startswith("/report"):
        send_telegram_message(chat_id, "📈 Отчётная функция в разработке.")
    else:
        send_telegram_message(chat_id, "Неизвестная команда. Используйте /start для списка команд.")
    
    return "ok"

# --- Анализ отзыва ---
def analyze_review(text: str) -> int:
    engine = os.getenv("AI_ENGINE", "gptfree")
    # Простая заглушка: рейтинг 1-5 на основе длины текста
    text_length = len(text)
    if text_length < 10:
        return 1
    elif text_length < 30:
        return 2
    elif text_length < 60:
        return 3
    elif text_length < 100:
        return 4
    else:
        return 5

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
    logger.info(f"Сохранён отзыв от @{username}, рейтинг: {rating}/5")

# --- Статистика ---
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating, COUNT(*) FROM reviews GROUP BY rating ORDER BY rating")
    rows = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM reviews")
    total = c.fetchone()[0]
    
    c.execute("SELECT AVG(rating) FROM reviews")
    avg_rating = c.fetchone()[0]
    
    conn.close()
    
    if not rows:
        return "📊 Статистика:\nНет данных об отзывах."
    
    result = ["📊 Статистика отзывов:"]
    result.append(f"Всего отзывов: {total}")
    if avg_rating:
        result.append(f"Средний рейтинг: {avg_rating:.1f}/5")
    result.append("\nПо рейтингам:")
    for r, cnt in rows:
        result.append(f"⭐ {r}/5: {cnt} отзывов")
    
    return "\n".join(result)

# --- Установка webhook на Railway ---
def set_webhook():
    if not WEBHOOK_URL or not TELEGRAM_BOT_TOKEN:
        logger.error("Не заданы TELEGRAM_BOT_TOKEN или WEBHOOK_URL!")
        return
    
    # 1. Сначала удаляем старый вебхук
    logger.info("Удаляю старый вебхук...")
    delete_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    delete_res = requests.post(delete_url, json={"drop_pending_updates": True})
    logger.info(f"Удаление вебхука: {delete_res.status_code} - {delete_res.text}")
    
    # 2. Устанавливаем новый вебхук
    logger.info(f"Устанавливаю новый вебхук на: {WEBHOOK_URL}")
    set_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    set_res = requests.post(set_url, json={"url": WEBHOOK_URL})
    
    logger.info(f"Установка вебхука: {set_res.status_code} - {set_res.text}")
    
    if set_res.status_code == 200:
        logger.info("✅ Webhook успешно установлен!")
    else:
        logger.error(f"❌ Ошибка установки webhook: {set_res.text}")
        
    # 3. Проверяем установку
    logger.info("Проверяю установленный вебхук...")
    check_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    check_res = requests.get(check_url)
    logger.info(f"Информация о вебхуке: {check_res.text}")

if __name__ == "__main__":
    logger.info("=== Запуск бота ===")
    logger.info(f"Токен бота: {TELEGRAM_BOT_TOKEN[:10]}...")
    logger.info(f"Webhook URL: {WEBHOOK_URL}")
    
    # Устанавливаем вебхук
    set_webhook()
    
    # Запускаем Flask сервер
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Запускаю Flask сервер на порту {port}")
    app.run(host="0.0.0.0", port=port)
