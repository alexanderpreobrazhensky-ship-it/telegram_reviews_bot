import os
import threading
import logging
import json
from flask import Flask, request, jsonify, render_template_string
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

# ------------------ CONFIG ------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8415726004:AAGJRwT0P42gCBOCuMqH0uX4D5Eb0yePm6A")
WEBHOOK_PATH = "/webhook"  # Telegram будет слать POST сюда
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///reviews.db")
MAX_REVIEW_LENGTH = 3000

# ------------------ LOGGING ------------------
logging.basicConfig(level=logging.INFO)

# ------------------ FLASK APP ------------------
app = Flask(__name__)

# ------------------ DATABASE ------------------
Base = declarative_base()

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    message = Column(Text)
    rating = Column(Integer, nullable=True)
    problem = Column(String(500), nullable=True)
    employees = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    complaint = Column(Boolean, default=False)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

# ------------------ UTILS ------------------
def safe_text(text: str) -> str:
    """Ограничение длины и экранирование"""
    return text[:MAX_REVIEW_LENGTH]

def send_message(chat_id: int, text: str):
    """Отправка сообщения Telegram"""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=data)
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")

# ------------------ AI ANALYSIS ------------------
def analyze_review(text: str) -> dict:
    """
    Пример анализа через ИИ.
    Здесь можно подключить Gemini / ChatGPT.
    Возвращает dict с оценкой, проблемой, сотрудниками, ответом и жалобой.
    """
    # Для примера заглушка
    return {
        "rating": 5,
        "problem": "Нет проблем",
        "employees": ["Иванов И."],
        "response": f"Спасибо за отзыв: {text[:50]}...",
        "complaint": False
    }

# ------------------ ASYNC PROCESS ------------------
def process_message_async(update):
    session = None
    try:
        message = update.get("message")
        if not message or "chat" not in message:
            return
        try:
            chat_id = int(message["chat"]["id"])
        except (ValueError, TypeError, KeyError):
            logging.error("Invalid chat_id")
            return

        text = message.get("text", "").strip()
        if not text:
            send_message(chat_id, "Сообщение пустое")
            return

        text = safe_text(text)
        result = analyze_review(text)

        session = SessionLocal()
        review = Review(
            chat_id=chat_id,
            message=text,
            rating=result.get('rating'),
            problem=result.get('problem', '')[:500],
            employees=json.dumps(result.get('employees', [])),
            response=result.get('response', '')[:1000],
            complaint=bool(result.get('complaint', False))
        )
        session.add(review)
        session.commit()

        send_message(chat_id, result.get("response", "Спасибо за отзыв!"))

    except Exception as e:
        logging.error(f"Ошибка обработки: {e}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()

# ------------------ FLASK ROUTES ------------------
@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        update = request.get_json()
        if not update:
            return jsonify({"status": "no data"}), 200
        threading.Thread(target=process_message_async, args=(update,)).start()
        return jsonify({"status": "processing"})
    except Exception as e:
        logging.error(f"Ошибка вебхука: {e}")
        return jsonify({"status": "error"}), 500

@app.route("/admin")
def admin_panel():
    """Простая админка для просмотра отзывов"""
    session = SessionLocal()
    reviews = session.query(Review).order_by(Review.id.desc()).limit(50).all()
    session.close()
    template = """
    <h1>Последние отзывы</h1>
    <table border="1" cellpadding="5">
    <tr><th>ID</th><th>Chat ID</th><th>Сообщение</th><th>Оценка</th><th>Ответ</th></tr>
    {% for r in reviews %}
    <tr>
        <td>{{ r.id }}</td>
        <td>{{ r.chat_id }}</td>
        <td>{{ r.message|e }}</td>
        <td>{{ r.rating }}</td>
        <td>{{ r.response|e }}</td>
    </tr>
    {% endfor %}
    </table>
    """
    return render_template_string(template, reviews=reviews)

@app.route("/set_webhook")
def set_webhook():
    """Авто-установка вебхука Telegram"""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    webhook_url = f"https://{os.getenv('RAILWAY_STATIC_URL','YOUR_DOMAIN')}{WEBHOOK_PATH}"
    r = requests.get(url, params={"url": webhook_url})
    return jsonify(r.json())

@app.route("/")
def root():
    return "Bot is running!"

# ------------------ RUN ------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
