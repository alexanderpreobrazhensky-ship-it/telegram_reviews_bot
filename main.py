import os
import logging
import requests
from flask import Flask, request, jsonify

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные среды
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")

if not TELEGRAM_TOKEN or not WEBHOOK_URL:
    raise ValueError("TELEGRAM_BOT_TOKEN и WEBHOOK_URL должны быть установлены в переменных среды!")

app = Flask(__name__)

# Функция отправки сообщений в Telegram
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        logger.error(f"Ошибка отправки сообщения: {r.text}")
    else:
        logger.info(f"Ответ отправлен: {text}")

# Пример функции анализа через Gemini (замените на реальный вызов API Gemini)
def analyze_with_gemini(message_text):
    # Простейший пример, замените на реальную интеграцию
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    # Пример запроса к Gemini
    # response = requests.post("https://api.gemini.example/analyze", json={"text": message_text}, headers=headers)
    # return response.json().get("result", "Ошибка анализа")
    return f"[Gemini ответ на]: {message_text}"

# Разделение команд и текста
def handle_update(update):
    if "message" not in update:
        return
    message = update["message"]
    chat_id = message["chat"]["id"]
    message_text = message.get("text", "")
    logger.info(f"Получено сообщение: {message}")

    if message_text.startswith("/"):
        # Обработка команд
        if message_text == "/start":
            answer = "Привет! Я бот для анализа отзывов."
        elif message_text == "/myid":
            answer = f"Ваш ID: {chat_id}"
        elif message_text == "/help":
            answer = "/start - запуск\n/myid - ваш ID\n/analyze <текст> - анализ текста через Gemini"
        elif message_text.startswith("/analyze"):
            text_to_analyze = message_text[len("/analyze "):].strip()
            if text_to_analyze:
                answer = analyze_with_gemini(text_to_analyze)
            else:
                answer = "Пожалуйста, укажите текст после команды /analyze"
        else:
            answer = "Неизвестная команда."
    else:
        # Обычный текст
        answer = analyze_with_gemini(message_text)

    send_message(chat_id, answer)

# Вебхук
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    handle_update(update)
    return jsonify({"ok": True})

# Ручные эндпоинты для теста/админки
@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={url}")
    logger.info(f"Вебхук установлен автоматически.")
    return jsonify(r.json())

@app.route("/remove_webhook", methods=["GET"])
def remove_webhook():
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    logger.info(f"Вебхук удален.")
    return jsonify(r.json())

@app.route("/debug", methods=["GET"])
def debug():
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo")
    return jsonify(r.json())

if __name__ == "__main__":
    # При старте проверяем вебхук
    webhook_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo").json()
    if not webhook_info.get("url"):
        logger.info("Вебхук не установлен или устарел. Устанавливаем новый...")
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={WEBHOOK_URL}/{TELEGRAM_TOKEN}")
        logger.info("Вебхук установлен автоматически.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
