import os
import logging
import requests
from flask import Flask, request, jsonify

# ----------------------
# Настройка логирования
# ----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ----------------------
# Проверка переменных среды
# ----------------------
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
AI_ENGINE = os.getenv('AI_ENGINE', 'gemini')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("TELEGRAM_BOT_TOKEN и WEBHOOK_URL должны быть установлены в переменных среды!")
if AI_ENGINE.lower() == 'gemini' and not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY должна быть установлена для AI_ENGINE=gemini!")

# ----------------------
# Flask и Telegram
# ----------------------
app = Flask(__name__)
BASE_TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ----------------------
# Вспомогательные функции
# ----------------------
def set_webhook():
    """Устанавливает вебхук для Telegram автоматически."""
    url = f"{BASE_TELEGRAM_URL}/setWebhook"
    data = {"url": WEBHOOK_URL}
    resp = requests.post(url, data=data)
    if resp.ok:
        logging.info("Вебхук установлен автоматически.")
    else:
        logging.error(f"Ошибка при установке вебхука: {resp.text}")

def send_message(chat_id, text):
    """Отправка сообщения в Telegram."""
    data = {"chat_id": chat_id, "text": text}
    resp = requests.post(f"{BASE_TELEGRAM_URL}/sendMessage", data=data)
    if resp.ok:
        logging.info(f"Ответ отправлен: {text}")
    else:
        logging.error(f"Ошибка при отправке сообщения: {resp.text}")

def call_gemini(prompt_text):
    """Запрос к Google Gemini API."""
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    data = {
        "contents": [
            {
                "parts": [{"text": prompt_text}]
            }
        ]
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        # Gemini возвращает текст в result['candidates'][0]['content'][0]['text'] по стандарту
        text_out = result['candidates'][0]['content'][0]['text']
        return text_out
    except Exception as e:
        logging.error(f"Ошибка при обращении к Gemini: {e}")
        return "[Ошибка при обращении к Gemini]"

# ----------------------
# Роут для Telegram Webhook
# ----------------------
@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    update = request.get_json()
    logging.info(f"Получено сообщение: {update}")

    if "message" not in update:
        return jsonify({"ok": True})

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # ----------------------
    # Команды
    # ----------------------
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я бот для анализа отзывов.")
    elif text.startswith("/help"):
        help_text = "/start - запуск\n/myid - ваш ID\n/analyze <текст> - анализ текста через Gemini"
        send_message(chat_id, help_text)
    elif text.startswith("/myid"):
        send_message(chat_id, f"Ваш ID: {chat_id}")
    elif text.startswith("/analyze"):
        prompt_text = text[len("/analyze"):].strip()
        if not prompt_text:
            send_message(chat_id, "Пожалуйста, укажите текст для анализа после команды /analyze")
        else:
            response = call_gemini(prompt_text)
            send_message(chat_id, f"[Gemini ответ на]: {response}")
    else:
        # Любое другое сообщение
        response = call_gemini(text)
        send_message(chat_id, f"[Gemini ответ на]: {response}")

    return jsonify({"ok": True})

# ----------------------
# Главный запуск
# ----------------------
if __name__ == "__main__":
    logging.info("Проверка вебхука...")
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
