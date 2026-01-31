import os
import logging
import requests
from flask import Flask, request, jsonify

# Настройка логов
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Переменные среды
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")

if not TELEGRAM_TOKEN or not WEBHOOK_URL or not GEMINI_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN, WEBHOOK_URL и GEMINI_API_KEY должны быть установлены!")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

app = Flask(__name__)

# Функция отправки сообщения
def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    if resp.status_code != 200:
        logging.error(f"Ошибка при отправке сообщения: {resp.text}")
    else:
        logging.info(f"Ответ отправлен: {text}")

# Установка вебхука автоматически
def set_webhook():
    resp = requests.get(f"{TELEGRAM_API}/getWebhookInfo").json()
    current_url = resp.get("result", {}).get("url", "")
    if current_url != f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}":
        logging.info("Вебхук не установлен или устарел. Устанавливаем новый...")
        r = requests.get(f"{TELEGRAM_API}/setWebhook?url={WEBHOOK_URL}/{TELEGRAM_TOKEN}")
        if r.status_code == 200:
            logging.info("Вебхук установлен автоматически.")
        else:
            logging.error(f"Ошибка установки вебхука: {r.text}")
    else:
        logging.info("Вебхук актуален.")

set_webhook()

# Обработка запросов Telegram
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"Получено сообщение: {data}")

    if "message" not in data:
        return jsonify({"ok": True})

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я бот для анализа отзывов.")
    elif text.startswith("/help"):
        send_message(chat_id, "/start - запуск\n/myid - ваш ID\n/analyze <текст> - анализ текста через Gemini")
    elif text.startswith("/myid"):
        send_message(chat_id, f"Ваш ID: {chat_id}")
    elif text.startswith("/analyze"):
        user_text = text[len("/analyze "):].strip()
        if not user_text:
            send_message(chat_id, "Пожалуйста, введите текст после команды /analyze")
        else:
            try:
                response = requests.post(
                    GEMINI_API_URL,
                    headers={"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY},
                    json={
                        "contents": [{"parts": [{"text": user_text}]}]
                    },
                    timeout=30
                )
                response.raise_for_status()
                result_json = response.json()
                # Получаем текст ответа от Gemini
                gemini_output = ""
                if "candidates" in result_json.get("result", {}):
                    gemini_output = result_json["result"]["candidates"][0].get("content", "")
                if not gemini_output:
                    gemini_output = "[Gemini ответ пустой]"
                send_message(chat_id, gemini_output)
            except Exception as e:
                logging.error(f"Ошибка при обращении к Gemini: {e}")
                send_message(chat_id, "[Ошибка при обращении к Gemini]")
    else:
        send_message(chat_id, "Пожалуйста, используйте команды /start, /help, /myid или /analyze <текст>")

    return jsonify({"ok": True})

# Запуск приложения
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
