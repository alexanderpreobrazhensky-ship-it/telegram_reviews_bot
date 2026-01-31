import os
import json
from flask import Flask, request
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# -----------------------------------------
#   НАСТРОЙКИ
# -----------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment!")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set! Example: https://your-app.up.railway.app")

WEBHOOK_SET_URL = f"{WEBHOOK_URL}/{BOT_TOKEN}"

# Файл с отзывами
REVIEWS_FILE = "reviews.json"


# -----------------------------------------
#   ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------------------
def send_message(chat_id, text):
    url = f"{TELEGRAM_API}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})


def load_reviews():
    if not os.path.exists(REVIEWS_FILE):
        return []
    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_review(user, rating, text):
    reviews = load_reviews()
    reviews.append({"user": user, "rating": rating, "text": text})
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)


# -----------------------------------------
#   АВТО-УСТАНОВКА ВЕБХУКА ПРИ ЗАПУСКЕ
# -----------------------------------------
def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    r = requests.get(f"{TELEGRAM_API}/setWebhook", params={"url": webhook_url})
    print("SET_WEBHOOK:", r.text)


@app.before_first_request
def startup():
    print(">>> Starting bot…")
    set_webhook()


# -----------------------------------------
#   МАРШРУТ ДЛЯ ВЕБХУКА (ВАЖНО!)
# -----------------------------------------
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    update = request.get_json()

    print(">>> UPDATE:", update)

    if "message" not in update:
        return "ok"

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "")

    # ADMIN PANEL
    if chat_id == ADMIN_ID:
        if text == "/reviews":
            reviews = load_reviews()
            if not reviews:
                send_message(chat_id, "Пока нет отзывов.")
            else:
                msg_out = "\n\n".join(
                    [f"⭐ {r['rating']} — {r['text']}\n👤 {r['user']}" for r in reviews]
                )
                send_message(chat_id, msg_out)
            return "ok"

    # USER SIDE
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Оставьте рейтинг от 1 до 5:")
        return "ok"

    if text.isdigit() and 1 <= int(text) <= 5:
        rating = int(text)
        save_review(chat_id, rating, "Без текста")
        send_message(chat_id, f"Спасибо! Ваша оценка: {rating} ⭐")
        return "ok"

    # текстовый отзыв
    save_review(chat_id, 5, text)
    send_message(chat_id, "Спасибо за отзыв! ❤️")

    return "ok"


# -----------------------------------------
#   РУЧНАЯ КНОПКА ДЛЯ ОТЛАДКИ (НЕ УДАЛЯТЬ)
# -----------------------------------------
@app.route("/set_webhook")
def manual_set():
    set_webhook()
    return "Webhook set manually"


# -----------------------------------------
#   ЗАПУСК
# -----------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
