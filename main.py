import os
import logging
import requests
from flask import Flask, request

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Переменные окружения
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения!")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.warning("⚠ GEMINI_API_KEY отсутствует — анализ работать не будет")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("Не задан WEBHOOK_URL!")

# URL Gemini API (актуальный)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

app = Flask(__name__)

# Отправка сообщения пользователю
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text})
    if r.status_code != 200:
        logging.error(f"Ошибка отправки: {r.text}")

# Анализ текста через Gemini
def analyze_with_gemini(text):
    if not GEMINI_API_KEY:
        return "❌ Gemini не настроен. Проверь GEMINI_API_KEY"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": text}]
            }
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    try:
        resp = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=20)
        logging.info(f"Gemini response raw: {resp.text}")
        resp.raise_for_status()

        data = resp.json()

        # Корректный путь к тексту ответа
        candidates = data.get("candidates", [])
        if not candidates:
            return "❌ Gemini вернул пустой ответ"

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return "❌ Gemini не прислал parts"

        result_text = parts[0].get("text", "")
        if not result_text:
            return "❌ Gemini прислал пустой текст"

        return result_text

    except Exception as e:
        logging.error(f"Ошибка Gemini: {e}")
        return "❌ Ошибка обращения к Gemini. Проверь API ключ или лимиты."

# Установка вебхука при старте
def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    r = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    )
    if r.status_code == 200:
        logging.info(f"Webhook установлен: {webhook_url}")
    else:
        logging.error(f"Ошибка установки вебхука: {r.text}")

# Вебхук Telegram
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    logging.info(f"Получено: {update}")

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id:
        return "ok"

    # Обработка команд
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я бот для анализа отзывов.")
        return "ok"

    if text.startswith("/help"):
        send_message(chat_id, "/start — начать\n/help — помощь\n/myid — ваш ID\n/analyze текст — анализ")
        return "ok"

    if text.startswith("/myid"):
        send_message(chat_id, f"Ваш ID: {chat_id}")
        return "ok"

    if text.startswith("/analyze"):
        analyze_text = text.replace("/analyze", "", 1).strip()
        if not analyze_text:
            send_message(chat_id, "Введите текст после команды /analyze")
            return "ok"

        result = analyze_with_gemini(analyze_text)
        send_message(chat_id, result)
        return "ok"

    # Если просто текст
    result = analyze_with_gemini(text)
    send_message(chat_id, result)
    return "ok"

if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
