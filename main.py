import os
import logging
import requests
from flask import Flask, request, jsonify

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Токен Telegram бота
if not BOT_TOKEN:
    raise ValueError("Не задан BOT_TOKEN в переменных окружения!")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # API ключ Gemini
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

app = Flask(__name__)

# Функция для отправки сообщений
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    r = requests.post(url, json=data)
    if r.status_code != 200:
        logging.error(f"Ошибка при отправке сообщения: {r.text}")
    else:
        logging.info(f"Ответ отправлен: {text}")

# Функция для обращения к Gemini
def analyze_with_gemini(text):
    if not GEMINI_API_KEY:
        return "[Gemini API не настроен]"
    payload = {
        "contents": [{"parts": [{"text": text}]}]
    }
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    try:
        resp = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        # Здесь предполагается, что ответ лежит в data["candidates"][0]["content"]
        content = data.get("candidates", [{}])[0].get("content", "")
        return content if content else "[Gemini вернул пустой ответ]"
    except Exception as e:
        logging.error(f"Ошибка при обращении к Gemini: {e}")
        return "[Ошибка при обращении к Gemini]"

# Проверка и установка вебхука
def set_webhook():
    webhook_url = f"{os.environ.get('WEBHOOK_URL')}/{BOT_TOKEN}"
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}")
    if r.status_code == 200:
        logging.info(f"Вебхук установлен автоматически: {webhook_url}")
    else:
        logging.error(f"Ошибка установки вебхука: {r.text}")

# Маршрут вебхука Telegram
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    logging.info(f"Получено сообщение: {update}")

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return "ok"

    response_text = ""

    if text.startswith("/start"):
        response_text = "Привет! Я бот для анализа отзывов."
    elif text.startswith("/help"):
        response_text = "/start - запуск\n/myid - ваш ID\n/analyze <текст> - анализ текста через Gemini"
    elif text.startswith("/myid"):
        response_text = f"Ваш ID: {chat_id}"
    elif text.startswith("/analyze"):
        analyze_text = text.replace("/analyze", "", 1).strip()
        if not analyze_text:
            response_text = "Введите текст после команды /analyze"
        else:
            gemini_response = analyze_with_gemini(analyze_text)
            response_text = f"[Gemini ответ на]: {gemini_response}"
    else:
        # Если просто текст без команды, тоже можно анализировать
        gemini_response = analyze_with_gemini(text)
        response_text = f"[Gemini ответ на]: {gemini_response}"

    send_message(chat_id, response_text)
    return "ok"

if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
