import os
import re
import json
import sqlite3
import logging
import requests
from flask import Flask, request

# ----------------------------
# Настройки
# ----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://yourproject.up.railway.app
AI_ENGINE = os.getenv("AI_ENGINE", "gptfree")  # gptfree / openai / deepseek / gemini

DATABASE = "reviews.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------
# Инициализация Flask
# ----------------------------
app = Flask(__name__)

# ----------------------------
# SQLite
# ----------------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            review_text TEXT,
            rating INTEGER,
            issue_summary TEXT,
            employees TEXT,
            response_suggestion TEXT,
            complaint_suggestion TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ----------------------------
# Telegram: безопасная отправка
# ----------------------------
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return ZERO_WIDTH_PATTERN.sub("", text)

def split_long_message(text: str, limit: int = 4000):
    chunks = []
    while len(text) > limit:
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = limit
        chunks.append(text[:split_pos])
        text = text[split_pos:]
    chunks.append(text)
    return chunks

def send_telegram_message(chat_id: int, text: str, keyboard=None):
    text = clean_text(text)
    chunks = split_long_message(text)
    for chunk in chunks:
        data = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if keyboard:
            data["reply_markup"] = {"inline_keyboard": keyboard}
        # Попытка с Markdown
        data["parse_mode"] = "Markdown"
        response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=data, timeout=10)
        if response.status_code == 200:
            continue
        # Markdown не прошел — plain text
        data.pop("parse_mode", None)
        response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=data, timeout=10)
        if response.status_code != 200:
            logger.error(f"Telegram send error: {response.text}")
            raise Exception(f"Telegram error: {response.text}")
    return True

# ----------------------------
# AI движки
# ----------------------------
def analyze_review_ai(review_text: str) -> dict:
    """
    Возвращает JSON:
    {
      rating: int,
      issue_summary: str,
      employees: [str],
      response_suggestion: str,
      complaint_suggestion: str or None
    }
    """
    prompt = f"""
    Ты аналитик отзывов автосервиса. Проанализируй следующий отзыв:

    {review_text}

    Нужно:
    1) Определи рейтинг отзыва по шкале 1–5.
    2) Определи суть проблемы кратко.
    3) Если упомянут сотрудник, укажи его имя/инициалы.
    4) Предложи готовый ответ на площадку.
    5) Если есть основание для жалобы, сформулируй текст жалобы.

    Выводи строго в формате JSON:
    {{
      "rating": int,
      "issue_summary": str,
      "employees": [str],
      "response_suggestion": str,
      "complaint_suggestion": str or null
    }}
    """

    if AI_ENGINE == "gptfree":
        # Простейший бесплатный движок (заглушка)
        # На практике можно использовать gptfree API / библиотеку
        rating = 3 if "не понравилось" in review_text.lower() else 5
        employees = re.findall(r"\b[А-ЯЁ][а-яё]\.", review_text)
        issue_summary = "Замена фильтра/неправильная установка, задержка ответа" if "фильтр" in review_text else "Общее обращение"
        response_suggestion = "Спасибо за отзыв. Мы разберёмся с ситуацией и свяжемся с вами."
        complaint_suggestion = "Жалоба оправдана" if rating <= 2 else None
        return {
            "rating": rating,
            "issue_summary": issue_summary,
            "employees": employees,
            "response_suggestion": response_suggestion,
            "complaint_suggestion": complaint_suggestion
        }
    else:
        # Тут можно вставить OpenAI / DeepSeek / Gemini
        # Для примера заглушка
        return {
            "rating": 4,
            "issue_summary": "Общее обращение",
            "employees": [],
            "response_suggestion": "Спасибо за отзыв",
            "complaint_suggestion": None
        }

# ----------------------------
# Сохранение отзыва
# ----------------------------
def save_review(user_id: int, review_text: str, analysis: dict):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reviews
        (user_id, review_text, rating, issue_summary, employees, response_suggestion, complaint_suggestion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        review_text,
        analysis["rating"],
        analysis["issue_summary"],
        json.dumps(analysis["employees"], ensure_ascii=False),
        analysis["response_suggestion"],
        analysis["complaint_suggestion"]
    ))
    conn.commit()
    conn.close()

# ----------------------------
# Flask routes
# ----------------------------
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" not in data:
        return {"ok": True}
    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.startswith("/start"):
        send_telegram_message(chat_id, "Привет! Я бот для анализа отзывов автосервиса. Используй /analyze <текст отзыва>.")
    elif text.startswith("/myid"):
        send_telegram_message(chat_id, f"Твой chat_id: {chat_id}")
    elif text.startswith("/analyze"):
        review_text = text.replace("/analyze", "").strip()
        if not review_text:
            send_telegram_message(chat_id, "Пожалуйста, введите текст отзыва после команды /analyze")
        else:
            analysis = analyze_review_ai(review_text)
            save_review(chat_id, review_text, analysis)
            result_text = (
                f"*Рейтинг:* {analysis['rating']}/5\n"
                f"*Суть проблемы:* {analysis['issue_summary']}\n"
                f"*Сотрудники:* {', '.join(analysis['employees']) if analysis['employees'] else 'не указаны'}\n"
                f"*Ответ клиенту:* {analysis['response_suggestion']}\n"
            )
            if analysis['complaint_suggestion']:
                result_text += f"*Жалоба:* {analysis['complaint_suggestion']}\n"
            send_telegram_message(chat_id, result_text)
    else:
        send_telegram_message(chat_id, "Команда не распознана. Используй /analyze для анализа отзывов.")

    return {"ok": True}

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}")
    return response.text

@app.route("/debug", methods=["GET"])
def debug():
    return {"status": "ok"}

# ----------------------------
# Запуск на Railway
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
