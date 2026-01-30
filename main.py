import os
import json
import sqlite3
import logging
from fastapi import FastAPI, Request
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "reviews.db"

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            rating INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}"

SERVICE_NAME = "Автосервис"
SERVICE_ADDRESS = "г. Москва"
SERVICE_PHONE = "+7 999 000-00-00"

def detect_railway_url():
    for var in ["RAILWAY_STATIC_URL", "RAILWAY_PUBLIC_DOMAIN", "RAILWAY_PRODUCTION_URL"]:
        url = os.getenv(var)
        if url and url.startswith("http"):
            return url
    proj = os.getenv("RAILWAY_PROJECT_NAME")
    if proj:
        return f"https://{proj}-production.up.railway.app"
    return None

RAILWAY_URL = detect_railway_url()
WEBHOOK_URL = f"{RAILWAY_URL}/webhook" if RAILWAY_URL else None

def send_message(chat_id, text):
    requests.post(f"{API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })

def analyze_text(text):
    text_l = text.lower()
    if any(w in text_l for w in ["хорош", "отличн", "супер", "класс", "норм"]):
        return 5
    if any(w in text_l for w in ["плохо", "ужас", "кошмар", "отврат"]):
        return 1
    return 3

def save_review(text, rating):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO reviews (text, rating, created_at) VALUES (?, ?, ?)", (
        text, rating, datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

def load_report_chat_ids():
    ids = os.getenv("REPORT_CHAT_IDS", "")
    if not ids:
        return []
    return [int(x) for x in ids.split(",") if x.strip().isdigit()]

app = FastAPI()

@app.on_event("startup")
async def set_webhook():
    if WEBHOOK_URL:
        requests.get(f"{API}/setWebhook", params={"url": WEBHOOK_URL})

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        if "message" not in update:
            return {"ok": True}

        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        if text.startswith("/start"):
            start_text = f"""🤖 *Бот автосервиса «{SERVICE_NAME}»*

📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

*Команды:*
▫️ `/analyze текст` - анализ отзыва
▫️ `/stats` - статистика
▫️ `/myid` - ваш chat_id
▫️ `/report` - отчёт за неделю

*Пример:*
`/analyze Отличный сервис, быстро починили!`"""
            send_message(chat_id, start_text)

        elif text.startswith("/myid"):
            send_message(chat_id, f"Ваш chat_id: `{chat_id}`")

        elif text.startswith("/analyze"):
            review = text.replace("/analyze", "", 1).strip()
            if not review:
                send_message(chat_id, "Введите текст: `/analyze ваш отзыв`")
                return {"ok": True}

            rating = analyze_text(review)
            save_review(review, rating)
            send_message(chat_id, f"Оценка отзыва: *{rating}/5*")

        elif text.startswith("/stats"):
            conn = db()
            c = conn.cursor()
            c.execute("SELECT rating, COUNT(*) as cnt FROM reviews GROUP BY rating")
            rows = c.fetchall()
            conn.close()

            if not rows:
                send_message(chat_id, "Нет данных")
                return {"ok": True}

            out = "*Статистика отзывов:*\n\n"
            for r in rows:
                out += f"⭐ {r['rating']}: {r['cnt']} шт.\n"
            send_message(chat_id, out)

        elif text.startswith("/report"):
            allowed = load_report_chat_ids()
            if chat_id not in allowed and chat_id > 0:
                send_message(chat_id, "⚠️ У вас нет прав на просмотр отчетов")
                return {"ok": True}

            conn = db()
            c = conn.cursor()
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            c.execute("SELECT rating, COUNT(*) FROM reviews WHERE created_at >= ? GROUP BY rating", (week_ago,))
            rows = c.fetchall()
            conn.close()

            if not rows:
                send_message(chat_id, "За неделю нет отзывов")
                return {"ok": True}

            out = "*Отчет за неделю:*\n\n"
            for r in rows:
                out += f"⭐ {r[0]}: {r[1]} шт.\n"

            send_message(chat_id, out)

    except Exception as e:
        logger.error(f"error: {e}")
        return {"ok": False}

    return {"ok": True}