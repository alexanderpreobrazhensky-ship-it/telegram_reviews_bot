import os
import logging
import requests
from flask import Flask, request

# ===========================
# ЛОГИРОВАНИЕ
# ===========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ===========================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ===========================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ Не задан TELEGRAM_BOT_TOKEN в переменных окружения!")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not WEBHOOK_URL:
    raise ValueError("❌ Не задан WEBHOOK_URL!")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

app = Flask(__name__)


# ===========================
# ОТПРАВКА СООБЩЕНИЙ
# ===========================
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    try:
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            logging.error(f"Ошибка отправки: {r.text}")
    except Exception as e:
        logging.error(f"send_message error: {e}")


# ===========================
# ЗАПРОС К GEMINI
# ===========================
def analyze_with_gemini(text):
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API не настроен"

    payload = {
        "contents": [{"parts": [{"text": text}]}]
    }
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }

    try:
        r = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()

        # Новый формат Gemini
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except:
            return str(data)

    except Exception as e:
        logging.error(f"Gemini ошибка: {e}")
        return "❌ Ошибка обращения к Gemini"


# ===========================
# УСТАНОВКА ВЕБХУКА
# ===========================
def set_webhook():
    webhook = f"{WEBHOOK_URL}/webhook"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook}"

    try:
        r = requests.get(url)
        if r.status_code == 200:
            logging.info(f"Вебхук установлен: {webhook}")
        else:
            logging.error(f"Ошибка установки вебхука: {r.text}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")


# ===========================
# ВЕБХУК TELEGRAM
# ===========================
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    logging.info(f"Получено: {update}")

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text")

    if not chat_id or not text:
        return "ok"

    # Команды
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я анализирую текст через Gemini.")
        return "ok"

    elif text.startswith("/help"):
        send_message(
            chat_id,
            "/start — начать\n/help — помощь\n/myid — ваш ID\n/analyze текст — анализ"
        )
        return "ok"

    elif text.startswith("/myid"):
        send_message(chat_id, f"Ваш ID: {chat_id}")
        return "ok"

    elif text.startswith("/analyze"):
        query = text.replace("/analyze", "").strip()
        if not query:
            send_message(chat_id, "Введите текст после команды /analyze")
            return "ok"

        reply = analyze_with_gemini(query)
        send_message(chat_id, reply)
        return "ok"

    # Обычный текст — тоже в анализ
    reply = analyze_with_gemini(text)
    send_message(chat_id, reply)

    return "ok"


# ===========================
# START
# ===========================
if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
