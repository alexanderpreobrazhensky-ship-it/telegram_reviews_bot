import os
import json
import sqlite3
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import requests
from fastapi import FastAPI, Request

# OpenAI новый клиент
from openai import OpenAI

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "ВАШ_ТОКЕН_ЗДЕСЬ"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "sk-ВАШ_КЛЮЧ_ЗДЕСЬ"
DOMAIN = os.getenv("DOMAIN") or os.getenv("RAILWAY_STATIC_URL") or "http://localhost:8000"
PORT = int(os.getenv("PORT", 8000))
REPORT_CHAT_IDS = os.getenv("REPORT_CHAT_IDS", "")  # chat_id через запятую для отчетов

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
DB_PATH = "reviews.db"
SERVICE_NAME = "Автосервис"
SERVICE_ADDRESS = "г. Москва"
SERVICE_PHONE = "+7 999 000-00-00"

# ========== OpenAI клиент ==========
client = OpenAI(api_key=OPENAI_API_KEY)

# ========== FastAPI ==========
app = FastAPI(title="Telegram Reviews Bot", version="1.0")

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            rating INTEGER NOT NULL,
            sentiment TEXT,
            categories TEXT,
            analysis_data TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(chat_id, text, created_at)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at)
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_database()

# ========== TELEGRAM ==========
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        url = f"{TELEGRAM_API}/{method}"
        response = requests.post(url, json=data, timeout=15)
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            logger.error(f"❌ Telegram API ошибка: {result}")
            return None
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram API {method}: {e}")
        return None

def send_telegram_message(chat_id: int, text: str, keyboard: List[List[Dict]] = None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    return telegram_api_request("sendMessage", data)

# ========== CHATGPT ==========
def analyze_with_chatgpt(text: str) -> Optional[Dict[str, Any]]:
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-ВАШ_КЛЮЧ"):
        return None
    try:
        prompt = f"""Ты — опытный менеджер автосервиса. Проанализируй отзыв клиента и верни только JSON без пояснений.

JSON структура:
{{
    "rating": 1-5,
    "sentiment": "negative/neutral/positive/very_negative/very_positive",
    "categories": ["quality","service","time","price","cleanliness","diagnostics","professionalism"],
    "requires_response": true/false,
    "response_type": "apology/thanks/clarification"
}}

Отзыв: "{text[:1000]}" """
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        content = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            analysis_result = json.loads(json_match.group())
            analysis_result["source"] = "chatgpt"
            return analysis_result
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка ChatGPT: {e}")
        return None

def test_chatgpt_api() -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        return {"status": "error", "available": False, "message": "OPENAI_API_KEY не установлен"}
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Привет"}],
            max_tokens=5,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()
        return {"status": "success", "available": True, "response": answer}
    except Exception as e:
        return {"status": "error", "available": False, "message": str(e)}

# ========== ПРОСТОЙ АНАЛИЗ ==========
def simple_text_analysis(text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    negative_words = ["плохо", "ужас", "кошмар", "отврат", "не рекоменд", "никогда", "хуже", "жалоба"]
    positive_words = ["хорошо", "отлично", "супер", "класс", "спасибо", "рекомендую", "доволен", "прекрасно"]
    neg_count = sum(1 for w in negative_words if w in text_lower)
    pos_count = sum(1 for w in positive_words if w in text_lower)

    if neg_count > pos_count:
        rating = 1 if neg_count > 3 else 2
        sentiment = "negative"
        requires_response = True
        response_type = "apology"
    elif pos_count > neg_count:
        rating = 5 if pos_count > 3 else 4
        sentiment = "positive"
        requires_response = True
        response_type = "thanks"
    else:
        rating = 3
        sentiment = "neutral"
        requires_response = False
        response_type = "clarification"

    categories = []
    if any(w in text_lower for w in ["ремонт", "почини", "диагност", "поломк"]): categories.append("quality")
    if any(w in text_lower for w in ["обслуживан", "прием", "мастер", "менеджер"]): categories.append("service")
    if any(w in text_lower for w in ["цена", "дорог", "дешев", "стоимость"]): categories.append("price")
    if any(w in text_lower for w in ["ждал", "долго", "быстро", "время", "срок"]): categories.append("time")

    return {"rating": rating, "sentiment": sentiment, "categories": categories,
            "requires_response": requires_response, "response_type": response_type, "source": "simple_analysis"}

def analyze_review_text(text: str) -> Dict[str, Any]:
    result = analyze_with_chatgpt(text)
    return result if result else simple_text_analysis(text)

# ========== БАЗА ДАННЫХ ==========
def save_review_to_db(chat_id: int, text: str, analysis: Dict[str, Any]) -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reviews (chat_id, text, rating, sentiment, categories, analysis_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (chat_id, text, analysis.get("rating", 3), analysis.get("sentiment", "neutral"),
              json.dumps(analysis.get("categories", []), ensure_ascii=False),
              json.dumps(analysis, ensure_ascii=False),
              datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        logger.info(f"💾 Отзыв сохранен: {chat_id}, рейтинг {analysis.get('rating')}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ Отзыв уже существует: {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def get_review_stats() -> Dict[str, Any]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM reviews")
        total_stats = cursor.fetchone()
        cursor.execute("SELECT rating, COUNT(*) as count FROM reviews GROUP BY rating ORDER BY rating")
        rating_stats = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as weekly_count FROM reviews WHERE created_at >= datetime('now', '-7 days')")
        weekly_stats = cursor.fetchone()
        conn.close()
        return {"total_reviews": total_stats["total"] if total_stats else 0,
                "average_rating": round(total_stats["avg_rating"],2) if total_stats and total_stats["avg_rating"] else 0,
                "weekly_reviews": weekly_stats["weekly_count"] if weekly_stats else 0,
                "rating_distribution": [{"rating": r["rating"], "count": r["count"]} for r in rating_stats]}
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {"total_reviews": 0,"average_rating": 0,"weekly_reviews":0,"rating_distribution":[]}

def get_weekly_report() -> List[Dict[str, Any]]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        cursor.execute("""
            SELECT rating, COUNT(*) as count, GROUP_CONCAT(DISTINCT substr(text,1,100)) as samples
            FROM reviews WHERE created_at >= ? GROUP BY rating ORDER BY rating
        """, (week_ago,))
        results = cursor.fetchall()
        conn.close()
        return [{"rating": r["rating"], "count": r["count"], "samples": r["samples"].split(",") if r["samples"] else []} for r in results]
    except Exception as e:
        logger.error(f"❌ Ошибка недельного отчета: {e}")
        return []

# ========== ВЕБХУК ==========
async def auto_set_webhook():
    if not TELEGRAM_TOKEN or not DOMAIN:
        return
    webhook_url = f"{DOMAIN}/webhook"
    try:
        response = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url, "max_connections":100})
        logger.info(f"✅ Вебхук установлен: {webhook_url}")
    except Exception:
        logger.warning("⚠️ Не удалось автоматически установить вебхук")

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Сервер запускается...")
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен!")
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-ВАШ_КЛЮЧ"):
        logger.warning("⚠️ OPENAI_API_KEY не установлен, ChatGPT не будет работать")
    await auto_set_webhook()
    logger.info(f"✅ Сервер готов! Домен: {DOMAIN}")

# ========== FastAPI эндпоинты ==========
@app.get("/")
async def root():
    return {"status":"online","service":"telegram-reviews-bot","timestamp":datetime.utcnow().isoformat()}

@app.get("/health")
async def health_check():
    chatgpt_status = test_chatgpt_api()
    return {"status":"healthy","telegram":bool(TELEGRAM_TOKEN),"chatgpt":chatgpt_status,"database":os.path.exists(DB_PATH),"webhook":DOMAIN}

@app.get("/test-chatgpt")
async def test_chatgpt():
    return test_chatgpt_api()

@app.get("/stats")
async def stats():
    return {"statistics": get_review_stats(), "weekly_report": get_weekly_report(), "generated_at": datetime.utcnow().isoformat()}

# ========== WEBHOOK Telegram ==========
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    chat_id = None
    message_text = None

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        message_text = data["message"].get("text", "").strip()
    elif "callback_query" in data:
        chat_id = data["callback_query"]["message"]["chat"]["id"]
        message_text = data["callback_query"]["data"]

    if not chat_id or not message_text:
        return {"ok": True}

    # Простейшая обработка команд
    if message_text.startswith("/start"):
        welcome = f"""🤖 *Бот {SERVICE_NAME}*
📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

Команды:
/analyze [текст] - анализ отзыва
/stats - статистика отзывов
/myid - ваш ID
/report - недельный отчет (только для админов)
"""
        send_telegram_message(chat_id, welcome)
        return {"ok": True}

    if message_text.startswith("/myid"):
        send_telegram_message(chat_id, f"🆔 Ваш Chat ID: `{chat_id}`")
        return {"ok": True}

    if message_text.startswith("/analyze"):
        review_text = message_text.replace("/analyze","",1).strip()
        if not review_text:
            send_telegram_message(chat_id, "Введите текст отзыва после команды /analyze")
            return {"ok": True}
        analysis = analyze_review_text(review_text)
        save_review_to_db(chat_id, review_text, analysis)
        resp = f"⭐ {analysis.get('rating',3)}\nТональность: {analysis.get('sentiment')}\nКатегории: {', '.join(analysis.get('categories',[]))}"
        send_telegram_message(chat_id, resp)
        return {"ok": True}

    if message_text.startswith("/stats"):
        stats = get_review_stats()
        send_telegram_message(chat_id, f"Всего отзывов: {stats['total_reviews']}\nСредний рейтинг: {stats['average_rating']}")
        return {"ok": True}

    send_telegram_message(chat_id, "Команда не распознана. /start для списка команд.")
    return {"ok": True}

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)