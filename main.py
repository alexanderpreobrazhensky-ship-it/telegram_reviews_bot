import os
import logging
import requests
from flask import Flask, request, jsonify

# ------------------ Настройка логирования ------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ------------------ Переменные среды ------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TELEGRAM_TOKEN or not WEBHOOK_URL or not GEMINI_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN, WEBHOOK_URL и GEMINI_API_KEY должны быть установлены!")

BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ------------------ Flask ------------------
app = Flask(__name__)

# ------------------ Gemini ------------------
def call_gemini(prompt: str) -> str:
    """
    Отправляет запрос к Gemini API и возвращает ответ
    """
    try:
        headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"}
        data = {"prompt": prompt, "max_tokens": 500}
        response = requests.post("https://api.gemini.example.com/v1/completions", json=data, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result.get("text", "[Gemini не вернул ответ]")
    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini: {e}")
        return "[Ошибка при обращении к Gemini]"

# ------------------ Telegram ------------------
def set_webhook():
    """
    Устанавливает вебхук на ваш URL
    """
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    response = requests.get(f"{BASE_TELEGRAM_URL}/setWebhook?url={webhook_url}")
    if response.status_code == 200:
        logger.info("Вебхук установлен автоматически.")
    else:
        logger.error(f"Не удалось установить вебхук: {response.text}")

def send_message(chat_id, text):
    """
    Отправка сообщения в Telegram
    """
    try:
        resp = requests.post(f"{BASE_TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()
        logger.info(f"Ответ отправлен: {text}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")

# ------------------ Эндпоинт вебхука ------------------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    logger.info(f"Получено сообщение: {update}")

    if "message" not in update:
        return jsonify({"ok": True})

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # Обработка команд
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я бот для анализа отзывов.")
    elif text.startswith("/help"):
        send_message(chat_id, "/start - запуск\n/myid - ваш ID\n/analyze <текст> - анализ текста через Gemini")
    elif text.startswith("/myid"):
        send_message(chat_id, f"Ваш ID: {chat_id}")
    elif text.startswith("/analyze"):
        user_text = text[len("/analyze"):].strip()
        if not user_text:
            send_message(chat_id, "Пожалуйста, введите текст после команды /analyze")
        else:
            gemini_response = call_gemini(user_text)
            send_message(chat_id, gemini_response)
    else:
        # Любой текст тоже через Gemini
        gemini_response = call_gemini(text)
        send_message(chat_id, gemini_response)

    return jsonify({"ok": True})

# ------------------ Старт приложения ------------------
if __name__ == "__main__":
    logger.info("Проверка вебхука...")
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
