import os
import re
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request
import requests
import json

# --- Настройки (ЖЕСТКО ПРОПИСАННЫЕ) ---
TELEGRAM_BOT_TOKEN = "8415726004:AAGl6ecMF-1Rv9TK6rmYmFYp9cvVPsnesj8"
WEBHOOK_URL = "https://telegramreviewsbot-production-06e5.up.railway.app/"
DB_PATH = "reviews.db"

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Логируем настройки
logger.info("=" * 50)
logger.info("🚀 ЗАПУСК БОТА LIRA_REVIEW_BOT2.0")
logger.info(f"🤖 Токен: {TELEGRAM_BOT_TOKEN[:10]}...")
logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")
logger.info("=" * 50)

# --- База данных ---
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
    logger.info("✅ База данных инициализирована")

init_db()

# --- Функции бота ---
def send_message(chat_id, text):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return None

def analyze_review(text):
    """Простой анализ отзыва (заглушка)"""
    length = len(text)
    if length < 20: return 1
    elif length < 50: return 2
    elif length < 100: return 3
    elif length < 150: return 4
    else: return 5

def save_review(user_id, username, text, rating):
    """Сохранение отзыва в БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO reviews (user_id, username, text, rating, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, text, rating, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    logger.info(f"💾 Сохранён отзыв от {username}, рейтинг: {rating}")

def get_stats():
    """Статистика отзывов"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating, COUNT(*) FROM reviews GROUP BY rating ORDER BY rating")
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return "📊 Пока нет отзывов"
    
    result = ["📊 СТАТИСТИКА ОТЗЫВОВ:"]
    for rating, count in rows:
        result.append(f"⭐ {rating}/5: {count} отзывов")
    return "\n".join(result)

# --- Flask приложение ---
app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    """Обработчик вебхука от Telegram"""
    try:
        data = request.get_json()
        logger.info(f"📩 Получен запрос: {json.dumps(data)[:200]}...")
        
        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            user = msg.get("from", {})
            username = user.get("username", "Неизвестный")
            
            logger.info(f"👤 Сообщение от @{username}: {text[:50]}...")
            
            # Обработка команд
            if text.startswith("/start"):
                send_message(chat_id, 
                    "🤖 <b>LIRA REVIEW BOT 2.0</b>\n\n"
                    "Я бот для анализа отзывов!\n\n"
                    "📝 <b>Команды:</b>\n"
                    "/analyze [текст] - Анализ отзыва\n"
                    "/stats - Статистика\n"
                    "/myid - Ваш ID\n"
                    "/help - Помощь"
                )
                
            elif text.startswith("/myid"):
                send_message(chat_id, f"🆔 <b>Ваш ID:</b> {chat_id}\n👤 <b>Username:</b> @{username}")
                
            elif text.startswith("/analyze"):
                review_text = text.replace("/analyze", "", 1).strip()
                if review_text:
                    rating = analyze_review(review_text)
                    save_review(chat_id, username, review_text, rating)
                    send_message(chat_id, 
                        f"📊 <b>АНАЛИЗ ОТЗЫВА</b>\n\n"
                        f"<b>Рейтинг:</b> {rating}/5 ⭐\n\n"
                        f"<b>Текст:</b>\n{review_text[:300]}"
                    )
                else:
                    send_message(chat_id, "📝 Напиши текст отзыва после команды /analyze")
                    
            elif text.startswith("/stats"):
                stats = get_stats()
                send_message(chat_id, stats)
                
            elif text.startswith("/help"):
                send_message(chat_id, 
                    "🆘 <b>ПОМОЩЬ</b>\n\n"
                    "/analyze [текст] - Проанализировать отзыв\n"
                    "/stats - Показать статистику\n"
                    "/myid - Узнать свой ID\n"
                    "/help - Эта справка"
                )
                
            else:
                send_message(chat_id, 
                    "❓ Неизвестная команда\n"
                    "Используй /help для списка команд"
                )
                
    except Exception as e:
        logger.error(f"❌ Ошибка обработки: {e}")
    
    return "OK"

@app.route("/health", methods=["GET"])
def health():
    """Проверка здоровья сервиса"""
    return {"status": "ok", "bot": "LIRA_REVIEW_BOT2.0"}

@app.route("/set_webhook", methods=["GET"])
def set_webhook_route():
    """Ручная установка вебхука"""
    try:
        # Удаляем старый
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        
        # Устанавливаем новый
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": WEBHOOK_URL}
        )
        
        if response.status_code == 200:
            return {"status": "success", "message": "Webhook установлен!"}
        else:
            return {"status": "error", "message": response.text}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Запуск ---
if __name__ == "__main__":
    # Автоматически устанавливаем вебхук при запуске
    try:
        logger.info("🔄 Устанавливаю вебхук...")
        delete_res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        logger.info(f"🗑️ Удаление вебхука: {delete_res.status_code}")
        
        set_res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": WEBHOOK_URL}
        )
        
        if set_res.status_code == 200:
            logger.info("✅ Вебхук успешно установлен!")
        else:
            logger.error(f"❌ Ошибка установки: {set_res.text}")
            
    except Exception as e:
        logger.error(f"⚠️ Ошибка при установке вебхука: {e}")
    
    # Запускаем сервер
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Запускаю сервер на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
