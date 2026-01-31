import os
import logging
from flask import Flask, request, jsonify, Response
import requests

# =======================
# Настройка логирования
# =======================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =======================
# Проверка переменных среды
# =======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
AI_ENGINE = os.getenv("AI_ENGINE", "gemini")  # По умолчанию Gemini

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("TELEGRAM_BOT_TOKEN и WEBHOOK_URL должны быть установлены в переменных среды!")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# =======================
# Flask приложение
# =======================
app = Flask(__name__)

# =======================
# Простая функция для отправки сообщений
# =======================
def send_message(chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    r = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
    if r.status_code != 200:
        logger.error(f"Ошибка отправки сообщения: {r.text}")

# =======================
# AI функция (stub для Gemini)
# =======================
def generate_ai_response(prompt):
    # В будущем здесь будет подключение к Gemini API
    return f"Спасибо за ваш отзыв! Вы написали: {prompt}"

# =======================
# Проверка базовой аутентификации
# =======================
def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    return Response(
        "Необходимо авторизоваться", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

# =======================
# Вебхуки управления
# =======================
@app.route("/set_webhook")
def set_webhook():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()
    
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    r = requests.get(f"{TELEGRAM_API_URL}/setWebhook?url={webhook_url}")
    logger.info(f"Установка вебхука: {r.text}")
    return r.text

@app.route("/remove_webhook")
def remove_webhook():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()
    
    r = requests.get(f"{TELEGRAM_API_URL}/deleteWebhook")
    logger.info(f"Удаление вебхука: {r.text}")
    return r.text

@app.route("/debug")
def debug():
    r = requests.get(f"{TELEGRAM_API_URL}/getWebhookInfo")
    return r.text

# =======================
# Основной обработчик Telegram сообщений
# =======================
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "no data"}), 400
    
    logger.info(f"Получено сообщение: {data}")

    message = data.get("message") or data.get("edited_message")
    if not message:
        return jsonify({"status": "no message"}), 200

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # Формируем ответ через AI
    response_text = generate_ai_response(text)

    send_message(chat_id, response_text)
    logger.info(f"Ответ отправлен: {response_text}")
    return jsonify({"status": "ok"})

# =======================
# Автоматическая проверка вебхука при старте
# =======================
def init_webhook():
    info = requests.get(f"{TELEGRAM_API_URL}/getWebhookInfo").json()
    if info.get("result", {}).get("url") != f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}":
        logger.info("Вебхук не установлен или устарел. Устанавливаем новый...")
        requests.get(f"{TELEGRAM_API_URL}/deleteWebhook")
        requests.get(f"{TELEGRAM_API_URL}/setWebhook?url={WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")
        logger.info("Вебхук установлен автоматически.")
    else:
        logger.info("Вебхук уже корректный.")

if __name__ == "__main__":
    init_webhook()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
