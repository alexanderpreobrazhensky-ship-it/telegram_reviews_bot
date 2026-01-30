import os
import json
import logging
from flask import Flask, request
import requests
from google import genai
from google.genai import types

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # ← Должен быть в Railway variables
WEBHOOK_URL = os.getenv("WEBHOOK_URL")        # https://yourapp.up.railway.app (без /)

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------
# ОТВЕТ В TELEGRAM
# ---------------------------------------------------------
def tg_send(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    requests.post(url, json=data)


# ---------------------------------------------------------
# АНАЛИЗ ОТЗЫВА ЧЕРЕЗ GEMINI
# ---------------------------------------------------------
def analyze_review(text: str) -> dict:
    prompt = f"""
Ты — ИИ-аналитик отзывов автосервиса.

Проанализируй отзыв и верни ЖЁСТКИЙ JSON строго по структуре:

{{
  "rating": 1-5,
  "problem": "краткое описание проблемы",
  "employees": ["имя1", "имя2"],
  "response": "готовый человеческий ответ клиенту",
  "complaint": true/false
}}

Возвращай ТОЛЬКО JSON.  
Отзыв клиента:
{text}
"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=300
        )
    )

    raw = response.text.strip()

    # Пытаемся безопасно достать JSON
    try:
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        json_str = raw[json_start:json_end]
        data = json.loads(json_str)
        return data
    except Exception as e:
        return {
            "rating": 3,
            "problem": "Не удалось разобрать отзыв",
            "employees": [],
            "response": "Благодарим за отзыв!",
            "complaint": False,
            "error": str(e),
            "raw": raw
        }


# ---------------------------------------------------------
# WEBHOOK ДЛЯ TELEGRAM
# ---------------------------------------------------------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()

    if not update or "message" not in update:
        return "ok"

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text")

    if not text:
        tg_send(chat_id, "Отправь, пожалуйста, текст отзыва.")
        return "ok"

    tg_send(chat_id, "Анализирую отзыв... 🔍")

    result = analyze_review(text)

    answer = (
        f"Готово!\n\n"
        f"⭐ Рейтинг: {result.get('rating')}\n"
        f"🛠 Проблема: {result.get('problem')}\n"
        f"👨‍🔧 Сотрудники: {', '.join(result.get('employees', [])) or 'не указаны'}\n"
        f"📩 Ответ клиенту:\n{result.get('response')}\n\n"
        f"🚨 Жалоба: {'Да' if result.get('complaint') else 'Нет'}"
    )

    tg_send(chat_id, answer)
    return "ok"


# ---------------------------------------------------------
# ROOT + УСТАНОВКА WEBHOOK
# ---------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "Bot is running!"

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"

    result = requests.get(url, params={"url": webhook_url}).json()
    return result


# ---------------------------------------------------------
# RUN (Railway сам использует PORT)
# ---------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
