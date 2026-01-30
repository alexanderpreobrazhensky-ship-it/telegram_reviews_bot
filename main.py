import os
import json
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
import requests
from google import genai
from google.genai import types

# -----------------------
# INIT
# -----------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# -----------------------
# CONFIG
# -----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip('/')
AI_ENGINE = os.getenv("AI_ENGINE", "gptfree").strip()
DB_PATH = "reviews.db"

if not TELEGRAM_TOKEN:
    logging.error("❌ TELEGRAM_TOKEN не установлен")
if not GEMINI_API_KEY:
    logging.warning("⚠️ GEMINI_API_KEY не установлен, будет использоваться заглушка")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# -----------------------
# DATABASE
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        text TEXT,
        rating INTEGER,
        problem TEXT,
        employees TEXT,
        response TEXT,
        complaint BOOLEAN,
        timestamp TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_review(chat_id, text, analysis):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reviews (chat_id, text, rating, problem, employees, response, complaint, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id,
        text,
        analysis.get("rating"),
        analysis.get("problem"),
        ",".join(analysis.get("employees", [])),
        analysis.get("response"),
        analysis.get("complaint"),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

# -----------------------
# TELEGRAM SEND MESSAGE
# -----------------------
def tg_send(chat_id: int, text: str, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(text) > 4000:
        text = text[:4000] + "\n...[сообщение сокращено]"
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=data, timeout=10)
        if r.status_code != 200:
            logging.error(f"Ошибка отправки: {r.text}")
    except Exception as e:
        logging.error(f"Ошибка сети: {e}")

# -----------------------
# ANALYZE REVIEW
# -----------------------
def analyze_review(text: str) -> dict:
    if not client:
        return {
            "rating": 3,
            "problem": "API ключ не настроен",
            "employees": [],
            "response": "Спасибо за отзыв! Мы его обработаем.",
            "complaint": False,
            "error": "GEMINI_API_KEY не установлен"
        }

    prompt = f"""
Ты — ИИ-аналитик отзывов автосервиса.
Проанализируй отзыв и верни ЖЁСТКИЙ JSON строго по структуре:

{{
  "rating": 1-5,
  "problem": "краткое описание проблемы",
  "employees": ["имя1", "имя2"],
  "response": "готовый ответ клиенту",
  "complaint": true/false
}}

Отзыв клиента:
{text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4, max_output_tokens=500)
        )
        raw = response.text.strip()
        logging.info(f"Gemini raw: {raw[:200]}...")
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = raw[json_start:json_end]
            data = json.loads(json_str)
            return data
        raise ValueError("JSON не найден")
    except Exception as e:
        logging.error(f"Анализ не удался: {e}")
        return {
            "rating": 3,
            "problem": f"Ошибка анализа: {str(e)[:100]}",
            "employees": [],
            "response": "Благодарим за отзыв!",
            "complaint": False
        }

# -----------------------
# TELEGRAM WEBHOOK
# -----------------------
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if not update:
        return jsonify({"status": "no data"}), 200

    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()

        if not text:
            tg_send(chat_id, "Отправьте текстовый отзыв.")
            return jsonify({"status": "ok"})

        if text.startswith("/"):
            if text == "/start":
                tg_send(chat_id, "Привет! Отправьте отзыв для анализа.")
            elif text == "/myid":
                tg_send(chat_id, f"Ваш ID: {chat_id}")
            return jsonify({"status": "ok"})

        tg_send(chat_id, "🔍 Анализирую отзыв...")
        result = analyze_review(text)
        save_review(chat_id, text, result)

        answer = (
            f"<b>📊 Результат анализа</b>\n"
            f"⭐ <b>Рейтинг:</b> {result.get('rating')}/5\n"
            f"🛠 <b>Проблема:</b> {result.get('problem')}\n"
            f"👨‍🔧 <b>Сотрудники:</b> {', '.join(result.get('employees', [])) or 'не указаны'}\n"
            f"📩 <b>Ответ клиенту:</b>\n{result.get('response')}\n"
            f"🚨 <b>Жалоба:</b> {'ДА ⚠️' if result.get('complaint') else 'Нет'}"
        )
        tg_send(chat_id, answer)
    return jsonify({"status": "ok"})

# -----------------------
# ROOT, SET/REMOVE WEBHOOK, DEBUG
# -----------------------
@app.route("/", methods=["GET"])
def root():
    return "✅ Бот работает! Используйте /set_webhook"

@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    try:
        result = requests.get(url, params={"url": webhook_url}).json()
        return jsonify({"webhook_url": webhook_url, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/remove_webhook", methods=["GET"])
def remove_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
    result = requests.get(url).json()
    return jsonify(result)

@app.route("/debug", methods=["GET"])
def debug():
    return jsonify({
        "bot_status": "running",
        "token_length": len(TELEGRAM_TOKEN),
        "webhook_url": f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        "gemini_configured": bool(GEMINI_API_KEY)
    })

# -----------------------
# RUN
# -----------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Starting bot on port {port}")
    if TELEGRAM_TOKEN and WEBHOOK_URL:
        try:
            webhook_url = f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook", params={"url": webhook_url}, timeout=5)
            logging.info(f"Webhook auto-set: {webhook_url}")
        except Exception as e:
            logging.warning(f"Webhook auto-set failed: {e}")
    app.run(host="0.0.0.0", port=port)
