import os
import threading
import logging
import json
import re
import ast
from flask import Flask, request, jsonify, render_template_string, redirect
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
import requests

# -----------------------
# Конфигурация
# -----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", f"https://{os.getenv('RAILWAY_STATIC_URL', '')}/{TELEGRAM_TOKEN}")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")
MAX_REVIEW_LENGTH = 3000

# -----------------------
# Логирование
# -----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# -----------------------
# Flask
# -----------------------
app = Flask(__name__)

# -----------------------
# БД
# -----------------------
Base = declarative_base()
DB_PATH = os.path.join("/tmp", "reviews.db") if "RAILWAY" in os.environ else "reviews.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=engine)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, index=True)
    message = Column(Text)
    rating = Column(String(50))
    problem = Column(String(500))
    employees = Column(Text)
    response = Column(Text)
    complaint = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)

# -----------------------
# Утилиты
# -----------------------
def safe_parse_json(raw):
    """Безопасный парсинг JSON из ответа ИИ"""
    try:
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            parsed = ast.literal_eval(json_match.group())
            if isinstance(parsed, dict):
                return parsed
    except Exception as e:
        logging.error(f"Ошибка парсинга JSON: {e}")
    return {}


def tg_send(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")


def analyze_review(text: str) -> dict:
    """
    Заглушка ИИ. Здесь должен быть вызов вашего Gemini / OpenAI.
    """
    text = text[:MAX_REVIEW_LENGTH]
    # Пример анализа
    return {
        "rating": "positive" if "хорошо" in text.lower() else "negative",
        "problem": "нет проблем" if "хорошо" in text.lower() else "неизвестно",
        "employees": [],
        "response": f"Спасибо за отзыв: {text[:100]}",
        "complaint": False
    }


# -----------------------
# Асинхронная обработка
# -----------------------
def process_message_async(update):
    session = None
    try:
        message = update.get("message")
        if not message or "chat" not in message:
            return
        try:
            chat_id = int(message["chat"]["id"])
        except (ValueError, TypeError, KeyError):
            logging.error(f"Некорректный chat_id: {message.get('chat', {})}")
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
            rating=result.get('rating'),
            problem=result.get('problem', '')[:500],
            employees=json.dumps(result.get('employees', [])),
            response=result.get('response', '')[:1000],
            complaint=bool(result.get('complaint', False))
        )
        session.add(review)
        session.commit()

        tg_send(chat_id, result.get("response", "Спасибо за отзыв!"))

    except Exception as e:
        logging.error(f"Ошибка обработки: {e}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()


# -----------------------
# Декоратор админа
# -----------------------
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Admin Login"'})
        return f(*args, **kwargs)
    return decorated


# -----------------------
# Эндпоинты
# -----------------------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if update:
        threading.Thread(target=process_message_async, args=(update,)).start()
    return jsonify({"status": "ok"})


@app.route("/set_webhook")
def set_webhook():
    url = f"https://{os.getenv('RAILWAY_STATIC_URL', '')}/{TELEGRAM_TOKEN}"
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={url}")
    return jsonify(r.json())


@app.route("/remove_webhook")
def remove_webhook():
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    return jsonify(r.json())


@app.route("/admin")
@admin_required
def admin_panel():
    session = SessionLocal()
    reviews = session.query(Review).order_by(Review.id.desc()).limit(50).all()
    session.close()
    template = """
    <h2>Отзывы</h2>
    <table border="1">
    <tr><th>ID</th><th>Chat ID</th><th>Message</th><th>Rating</th><th>Problem</th></tr>
    {% for r in reviews %}
    <tr>
      <td>{{ r.id }}</td>
      <td>{{ r.chat_id }}</td>
      <td>{{ r.message|e }}</td>
      <td>{{ r.rating|e }}</td>
      <td>{{ r.problem|e }}</td>
    </tr>
    {% endfor %}
    </table>
    """
    return render_template_string(template, reviews=reviews)


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "db_exists": os.path.exists(DB_PATH),
        "webhook_url": f"/{TELEGRAM_TOKEN}"
    })


@app.route("/")
def root():
    return "Bot is running!"


# -----------------------
# Запуск
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
