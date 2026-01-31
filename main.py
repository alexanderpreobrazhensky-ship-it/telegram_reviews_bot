import os
import json
import threading
import logging
from flask import Flask, request, jsonify

import requests

# ===== Настройки и переменные среды =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Токен бота
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Должно быть типа https://<домен>/<token>
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not TELEGRAM_TOKEN or not WEBHOOK_URL:
    raise ValueError("TELEGRAM_BOT_TOKEN и WEBHOOK_URL должны быть установлены в переменных среды!")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ===== Декоратор для админки =====
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

# ===== Простая заглушка анализа отзыва =====
def analyze_review(text: str) -> dict:
    """
    Функция анализа отзыва. Можно заменить на вызов Gemini/AI.
    """
    text = text.strip()
    if not text:
        return {"response": "Пустой текст!"}
    return {"response": f"Спасибо за ваш отзыв! Вы написали: {text}"}

# ===== Функция отправки сообщения через Telegram =====
def tg_send(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=5)
        if not r.ok:
            logging.error(f"Ошибка отправки сообщения: {r.text}")
    except Exception as e:
        logging.error(f"Ошибка запроса к Telegram API: {e}")

# ===== Асинхронная обработка сообщений =====
def process_message_async(update: dict):
    try:
        message = update.get("message")
        if not message or "chat" not in message:
            return
        try:
            chat_id = int(message["chat"]["id"])
        except (ValueError, TypeError):
            logging.error("Некорректный chat_id")
            return

        text = message.get("text", "").strip()
        if not text:
            tg_send(chat_id, "Пустое сообщение, напишите что-нибудь.")
            return

        # Анализ текста
        result = analyze_review(text)
        tg_send(chat_id, result.get("response", "Ответ отсутствует."))

    except Exception as e:
        logging.error(f"Ошибка обработки update: {e}")

# ===== Вебхук для Telegram =====
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if not update:
        return jsonify({"status": "no data"}), 200
    threading.Thread(target=process_message_async, args=(update,)).start()
    return jsonify({"status": "processing"})

# ===== Админ-панель =====
@app.route("/admin")
@admin_required
def admin_panel():
    return "<h2>Админка бота. Всё работает.</h2>"

# ===== Эндпоинт для установки вебхука =====
@app.route("/set_webhook")
@admin_required
def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}")
    return jsonify(r.json())

# ===== Эндпоинт для удаления вебхука =====
@app.route("/remove_webhook")
@admin_required
def remove_webhook():
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    return jsonify(r.json())

# ===== Проверка состояния =====
@app.route("/debug")
@admin_required
def debug():
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo")
    return jsonify(r.json())

# ===== Главная =====
@app.route("/")
def root():
    return "Bot is running!"

# ===== Запуск приложения =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
