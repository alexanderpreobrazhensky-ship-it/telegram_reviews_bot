import os
import logging
import requests
from flask import Flask, request, jsonify

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Переменные среды
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL or not GEMINI_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN, WEBHOOK_URL и GEMINI_API_KEY должны быть установлены в переменных среды!")

# Telegram API
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Gemini API
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Flask app
app = Flask(__name__)

# Установка вебхука автоматически
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    resp = requests.post(url, json={"url": WEBHOOK_URL})
    if resp.ok:
        logging.info("Вебхук установлен автоматически.")
    else:
        logging.error(f"Ошибка установки вебхука: {resp.text}")

set_webhook()

def send_telegram_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(TELEGRAM_API_URL, json=payload)
    if resp.ok:
        logging.info(f"Ответ отправлен: {text}")
    else:
        logging.error(f"Ошибка отправки сообщения: {resp.text}")

def analyze_with_gemini(user_text):
    try:
        payload = {
            "contents": [{"parts": [{"text": user_text}]}]
        }
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": GEMINI_API_KEY
        }
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Извлечение ответа
        gemini_output = ""
        candidates = data.get("candidates") or data.get("result", {}).get("candidates")
        if candidates and len(candidates) > 0:
            gemini_output = candidates[0].get("content", "")
        if not gemini_output:
            gemini_output = "[Gemini ответ пустой]"
        return gemini_output
    except Exception as e:
        logging.error(f"Ошибка при обращении к Gemini: {e}")
        return "[Ошибка при обращении к Gemini]"

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" not in data:
        return jsonify({"ok": True})
    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    logging.info(f"Получено сообщение: {message}")

    # Команды
    if text.startswith("/start"):
        send_telegram_message(chat_id, "Привет! Я бот для анализа отзывов.")
    elif text.startswith("/help"):
        send_telegram_message(chat_id, "/start - запуск\n/myid - ваш ID\n/analyze <текст> - анализ текста через Gemini")
    elif text.startswith("/myid"):
        send_telegram_message(chat_id, f"Ваш ID: {chat_id}")
    elif text.startswith("/analyze"):
        user_text = text.replace("/analyze", "").strip()
        if not user_text:
            send_telegram_message(chat_id, "Пожалуйста, укажите текст для анализа после команды /analyze")
        else:
            gemini_response = analyze_with_gemini(user_text)
            send_telegram_message(chat_id, f"[Gemini ответ на]: {gemini_response}")
    else:
        # Сообщения без команд тоже анализируем
        gemini_response = analyze_with_gemini(text)
        send_telegram_message(chat_id, f"[Gemini ответ на]: {gemini_response}")

    return jsonify({"ok": True})

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    # Проверка вебхука при старте
    logging.info("Проверка вебхука...")
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
