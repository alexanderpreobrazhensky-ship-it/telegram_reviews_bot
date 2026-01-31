import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://telegramreviewsbot-production-xxx.up.railway.app

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_ID = os.getenv("ADMIN_ID", "0")  # необязательно


# ===========================
#  Функция отправки сообщений
# ===========================
def send_message(chat_id, text):
    url = f"{TELEGRAM_API}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})


# ===========================
#  Установка вебхука при старте
# ===========================
def setup_webhook():
    full_webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    url = f"{TELEGRAM_API}/setWebhook?url={full_webhook_url}"

    try:
        r = requests.get(url)
        print("=== SET_WEBHOOK RESPONSE ===")
        print(r.text)
        print("============================")
    except Exception as e:
        print("ERROR setting webhook:", e)


# ===========================
#  Проверка, что бот жив
# ===========================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"


# ===========================
#   ОСНОВНОЙ ВЕБХУК
# ===========================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    update = request.get_json()
    print("=== INCOMING UPDATE ===")
    print(update)
    print("=======================")

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        # простейшая реакция
        if text == "/start":
            send_message(chat_id, "Бот работает! Webhook активен.")
        else:
            send_message(chat_id, f"Вы сказали: {text}")

    return "OK", 200


# ===========================
#  Запуск приложения
# ===========================
if __name__ == "__main__":
    print("=== STARTING BOT ===")
    print("BOT_TOKEN:", BOT_TOKEN)
    print("WEBHOOK_URL:", WEBHOOK_URL)

    setup_webhook()

    app.run(host="0.0.0.0", port=8080)
