import os
import json
import ast
import logging
import threading
from flask import Flask, request, jsonify, render_template_string, redirect
import requests
from google import genai
from google.genai import types
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from functools import wraps

# ---------------------- CONFIG ----------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip('/')
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "secret123")
MAX_REVIEW_LENGTH = 3000

# SQLite для Railway (ephemeral storage)
DB_PATH = "/tmp/reviews.db" if "RAILWAY" in os.environ else "reviews.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ---------------------- LOGGING ----------------------
logging.basicConfig(level=logging.INFO)
if TELEGRAM_TOKEN:
    logging.info(f"Telegram token loaded, first 10 chars: {TELEGRAM_TOKEN[:10]}...")
else:
    logging.error("TELEGRAM_TOKEN not set!")

# ---------------------- DB ----------------------
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, index=True)
    message = Column(Text)
    rating = Column(Integer)
    problem = Column(String(500))
    employees = Column(String(500))
    response = Column(String(1000))
    complaint = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

# ---------------------- Flask ----------------------
app = Flask(__name__)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ---------------------- Utils ----------------------
def safe_text(t):
    t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    return t[:4000] if len(t) > 4000 else t

def tg_send(chat_id: int, text: str):
    if not TELEGRAM_TOKEN:
        logging.error("Cannot send: TELEGRAM_TOKEN missing")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": safe_text(text), "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=data, timeout=10)
        if resp.status_code != 200:
            logging.error(f"Telegram send error: {resp.text}")
    except Exception as e:
        logging.error(f"Network error sending to Telegram: {e}")

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Admin Login"'})
        return f(*args, **kwargs)
    return decorated

# ---------------------- Gemini Analysis ----------------------
def analyze_review(text: str) -> dict:
    if not client:
        return {
            "rating": 3,
            "problem": "AI not configured",
            "employees": [],
            "response": "Спасибо за отзыв!",
            "complaint": False
        }
    text = text[:MAX_REVIEW_LENGTH]
    prompt = f"""
Ты — ИИ-аналитик отзывов автосервиса.
Проанализируй отзыв и верни JSON строго по структуре:
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
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=500)
        )
        raw = response.text.strip()
        logging.info(f"Gemini response: {raw[:100]}...")
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            parsed = ast.literal_eval(json_match.group())
            if isinstance(parsed, dict):
                return parsed
    except Exception as e:
        logging.error(f"Error analyzing Gemini: {e}")
    return {
        "rating": 3,
        "problem": "Ошибка анализа AI",
        "employees": [],
        "response": "Спасибо за отзыв!",
        "complaint": False
    }

def save_review(chat_id, text, result):
    session = None
    try:
        session = SessionLocal()
        review = Review(
            chat_id=int(chat_id),
            message=text,
            rating=result.get("rating"),
            problem=result.get("problem", "")[:500],
            employees=json.dumps(result.get("employees", [])),
            response=result.get("response", "")[:1000],
            complaint=bool(result.get("complaint", False))
        )
        session.add(review)
        session.commit()
    except Exception as e:
        if session:
            session.rollback()
        logging.error(f"DB save error: {e}")
    finally:
        if session:
            session.close()

def send_analysis_result(chat_id, result):
    rating_emoji = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}
    emoji = rating_emoji.get(result.get("rating", 3), "⭐⭐⭐")
    answer = (
        f"📊 <b>Результат анализа</b>\n\n"
        f"{emoji} <b>Рейтинг:</b> {result.get('rating','N/A')}/5\n"
        f"🛠 <b>Проблема:</b> {result.get('problem','Не определена')}\n"
        f"👨‍🔧 <b>Сотрудники:</b> {', '.join(result.get('employees',[])) or 'не указаны'}\n"
        f"📝 <b>Ответ клиенту:</b>\n{result.get('response','Спасибо за отзыв!')}\n\n"
        f"🚨 <b>Требует жалобы:</b> {'ДА ⚠️' if result.get('complaint') else 'Нет'}"
    )
    tg_send(chat_id, answer)

def process_message_async(update):
    session = None
    try:
        message = update.get("message")
        if not message or "chat" not in message:
            return
        try:
            chat_id = int(message["chat"]["id"])
        except Exception:
            logging.error(f"Invalid chat_id: {message.get('chat',{})}")
            return
        text = message.get("text","").strip()
        if not text:
            tg_send(chat_id,"Пожалуйста, отправьте текстовый отзыв.")
            return
        result = analyze_review(text[:MAX_REVIEW_LENGTH])
        save_review(chat_id, text, result)
        send_analysis_result(chat_id, result)
    except Exception as e:
        logging.error(f"Async processing error: {e}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()

# ---------------------- WEBHOOK ----------------------
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    try:
        update = request.get_json()
        if not update:
            return jsonify({"status":"no data"}), 200
        threading.Thread(target=process_message_async,args=(update,)).start()
        return jsonify({"status":"processing"})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({"status":"error"}),500

# ---------------------- ADMIN ----------------------
@app.route("/admin")
@admin_required
def admin_panel():
    page = request.args.get("page",1,type=int)
    per_page = 50
    offset = (page-1)*per_page
    session = SessionLocal()
    try:
        reviews = session.query(Review).order_by(Review.id.desc()).offset(offset).limit(per_page).all()
        template = """
        <h2>Админ-панель</h2>
        <table border=1>
        <tr><th>ID</th><th>Chat</th><th>Message</th><th>Rating</th><th>Problem</th></tr>
        {% for r in reviews %}
        <tr>
        <td>{{r.id}}</td>
        <td>{{r.chat_id}}</td>
        <td>{{r.message|e}}</td>
        <td>{{r.rating}}</td>
        <td>{{r.problem|e}}</td>
        </tr>
        {% endfor %}
        </table>
        """
        return render_template_string(template,reviews=reviews)
    finally:
        session.close()

# ---------------------- UTILS ----------------------
@app.route("/")
def root():
    token_preview = TELEGRAM_TOKEN[:3]+"..." if TELEGRAM_TOKEN else "не установлен"
    return f"<h1>Бот анализа отзывов</h1><p>Token preview: {token_preview}</p><ul>"\
           f"<li><a href='/set_webhook'>Set webhook</a></li>"\
           f"<li><a href='/remove_webhook'>Remove webhook</a></li>"\
           f"<li><a href='/admin'>Admin</a></li></ul>"

@app.route("/set_webhook")
def set_webhook():
    if not TELEGRAM_TOKEN or not WEBHOOK_URL:
        return "Missing TELEGRAM_TOKEN or WEBHOOK_URL"
    url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook", params={"url":url})
    return jsonify(resp.json())

@app.route("/remove_webhook")
def remove_webhook():
    if not TELEGRAM_TOKEN:
        return "Missing TELEGRAM_TOKEN"
    resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook")
    return jsonify(resp.json())

@app.route("/health")
def health():
    return jsonify({
        "status":"healthy",
        "db_exists": os.path.exists(DB_PATH),
        "telegram_token": bool(TELEGRAM_TOKEN),
        "gemini": bool(GEMINI_API_KEY)
    })

# ---------------------- RUN ----------------------
if __name__=="__main__":
    import re
    port = int(os.environ.get("PORT",8080))
    logging.info(f"Starting bot on port {port}, webhook: {WEBHOOK_URL}/{TELEGRAM_TOKEN}")
    app.run(host="0.0.0.0", port=port, debug=False)
