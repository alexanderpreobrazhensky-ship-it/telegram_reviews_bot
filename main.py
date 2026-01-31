import os
import json
import logging
import threading
import requests
import ast
import re

from flask import Flask, request, jsonify, redirect
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# =========================
# CONFIG
# =========================

TELEGRAM_TOKEN = "8415726004:AAGJRwT0P42gCBOCuMqH0uX4D5Eb0yePm6A"
WEBHOOK_URL = f"https://{os.environ.get('RAILWAY_PUBLIC_DOMAIN')}/webhook"

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///reviews.db")

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s"
)

# =========================
# FLASK
# =========================
app = Flask(__name__)

# =========================
# DATABASE
# =========================
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    pool_pre_ping=True
)

Base = declarative_base()


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    message = Column(Text)
    rating = Column(Integer)
    problem = Column(Text)
    employees = Column(Text)
    response = Column(Text)
    complaint = Column(Boolean, default=False)


Base.metadata.create_all(engine)

SessionLocal = scoped_session(sessionmaker(bind=engine))


# =========================
# TELEGRAM SEND
# =========================
def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logging.error(f"TG SEND ERROR: {e}")


# ============================
# REVIEW ANALYZER (Gemini stub)
# ============================
def analyze_review(text: str):
    """
    БЕЗВРЕДНЫЙ ПАРСИНГ JSON от Gemini
    """

    fake_ai_response = """{
        "rating": 5,
        "problem": "Отзыв положительный",
        "employees": ["Иван"],
        "response": "Спасибо за отзыв!",
        "complaint": false
    }"""

    try:
        # Безопасный разбор
        data = ast.literal_eval(fake_ai_response)
        if isinstance(data, dict):
            return data
        else:
            return {}
    except Exception:
        return {}


# =========================
# BACKGROUND PROCESSING
# =========================
def process_async(update):
    session = None
    try:
        message = update.get("message")
        if not message:
            return

        try:
            chat_id = int(message["chat"]["id"])
        except Exception:
            logging.error("Invalid chat_id")
            return

        text = message.get("text", "").strip()
        if not text:
            tg_send(chat_id, "Пустое сообщение")
            return

        result = analyze_review(text)

        session = SessionLocal()
        review = Review(
            chat_id=chat_id,
            message=text,
            rating=result.get("rating"),
            problem=result.get("problem", ""),
            employees=json.dumps(result.get("employees", [])),
            response=result.get("response", ""),
            complaint=bool(result.get("complaint"))
        )

        session.add(review)
        session.commit()

        tg_send(chat_id, f"Ваш отзыв принят!\n\nАнализ:\n{json.dumps(result, ensure_ascii=False, indent=2)}")

    except Exception as e:
        logging.error(f"PROCESS ERROR: {e}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()


# =========================
# WEBHOOK ENDPOINT
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True)

    threading.Thread(target=process_async, args=(update,), daemon=True).start()

    return jsonify({"ok": True})


# =========================
# ADMIN CHECK
# =========================
@app.route("/admin")
def admin():
    return "<h1>Админка будет здесь</h1>"


# =========================
# HEALTH CHECK
# =========================
@app.route("/health")
def health():
    return "OK", 200


# =========================
# AUTO SET WEBHOOK
# =========================
def setup_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    data = {"url": WEBHOOK_URL}

    try:
        r = requests.post(url, json=data, timeout=5)
        logging.info(f"Webhook setup response: {r.text}")
    except Exception as e:
        logging.error(f"Webhook setup error: {e}")


# =========================
# ROOT PAGE
# =========================
@app.route("/")
def index():
    return "Bot is running!"


# =========================
# APP START
# =========================
if __name__ == "__main__":
    setup_webhook()
    app.run(host="0.0.0.0", port=8080)
