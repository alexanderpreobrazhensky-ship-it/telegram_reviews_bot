import os
import json
import sqlite3
import logging
import re
import requests
from datetime import datetime
from fastapi import FastAPI, Request
from typing import List, Dict, Optional, Any
from openai import OpenAI

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ПЕРЕМЕННЫЕ ==========
DB_PATH = "reviews.db"
SERVICE_NAME = "Автосервис"
SERVICE_ADDRESS = "г. Москва"
SERVICE_PHONE = "+7 999 000-00-00"

# ========== FASTAPI ==========
app = FastAPI(title="Review Analyzer Bot", version="2.0")

# ========== OpenAI ==========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# ========== TELEGRAM ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
REPORT_CHAT_IDS = os.getenv("REPORT_CHAT_IDS", "")
PORT = int(os.getenv("PORT", "8000"))

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
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_database()

# ========== TELEGRAM ФУНКЦИИ ==========
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not TELEGRAM_TOKEN:
        logger.error(f"❌ Telegram токен не установлен")
        return None
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

def send_telegram_message(chat_id: int, text: str, parse_mode: str="Markdown", keyboard: List[List[Dict]]=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    return telegram_api_request("sendMessage", data)

# ========== ChatGPT ==========
def analyze_with_chatgpt(text: str) -> Optional[Dict[str, Any]]:
    if not OPENAI_API_KEY:
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
    negative_words = ["плохо","ужас","отврат","не рекоменд","никогда","хуже","жалоба"]
    positive_words = ["хорошо","отлично","спасибо","рекомендую","доволен"]
    neg_count = sum(1 for w in negative_words if w in text_lower)
    pos_count = sum(1 for w in positive_words if w in text_lower)
    if neg_count>pos_count:
        rating = 1 if neg_count>3 else 2
        sentiment="negative"
        requires_response=True
        response_type="apology"
    elif pos_count>neg_count:
        rating = 5 if pos_count>3 else 4
        sentiment="positive"
        requires_response=True
        response_type="thanks"
    else:
        rating = 3
        sentiment="neutral"
        requires_response=False
        response_type="clarification"
    categories=[]
    if any(w in text_lower for w in ["ремонт","почини","диагност","поломк"]):
        categories.append("quality")
    if any(w in text_lower for w in ["обслуживан","прием","мастер","менеджер"]):
        categories.append("service")
    if any(w in text_lower for w in ["цена","дорог","дешев","стоимость"]):
        categories.append("price")
    if any(w in text_lower for w in ["ждал","долго","быстро","время","срок"]):
        categories.append("time")
    return {
        "rating": rating,
        "sentiment": sentiment,
        "categories": categories,
        "requires_response": requires_response,
        "response_type": response_type,
        "source": "simple_analysis"
    }

def analyze_review_text(text: str) -> Dict[str, Any]:
    result = analyze_with_chatgpt(text)
    return result if result else simple_text_analysis(text)

# ========== БД ==========
def save_review_to_db(chat_id:int, text:str, analysis:Dict[str,Any]) -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reviews 
            (chat_id, text, rating, sentiment, categories, analysis_data, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            chat_id, text, analysis.get("rating",3), analysis.get("sentiment","neutral"),
            json.dumps(analysis.get("categories",[]), ensure_ascii=False),
            json.dumps(analysis, ensure_ascii=False),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
        return False

def get_review_stats() -> Dict[str, Any]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM reviews")
        total_stats = cursor.fetchone()
        cursor.execute("SELECT rating, COUNT(*) as count FROM reviews GROUP BY rating ORDER BY rating")
        rating_stats = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as weekly_count FROM reviews WHERE created_at >= datetime('now','-7 days')")
        weekly_stats = cursor.fetchone()
        conn.close()
        return {
            "total_reviews": total_stats["total"] if total_stats else 0,
            "average_rating": round(total_stats["avg_rating"],2) if total_stats and total_stats["avg_rating"] else 0,
            "weekly_reviews": weekly_stats["weekly_count"] if weekly_stats else 0,
            "rating_distribution":[{"rating":row["rating"],"count":row["count"]} for row in rating_stats]
        }
    except Exception as e:
        logger.error(f"❌ Ошибка статистики: {e}")
        return {"total_reviews":0,"average_rating":0,"weekly_reviews":0,"rating_distribution":[]}

# ========== ВСПОМОГАТЕЛЬНЫЕ ==========
def format_stars(rating:int) -> str:
    return "⭐"*rating + "☆"*(5-rating)

def generate_response_template(response_type:str) -> str:
    templates = {
        "apology": f"📋 *ОТВЕТ НА НЕГАТИВНЫЙ ОТЗЫВ*\n📍 {SERVICE_NAME}\n📞 {SERVICE_PHONE}\n{SERVICE_ADDRESS}",
        "thanks": f"🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*\n📍 {SERVICE_NAME}",
        "clarification": f"❓ *ЗАПРОС УТОЧНЕНИЯ*\n📍 {SERVICE_NAME}"
    }
    return templates.get(response_type,templates["clarification"])

def get_report_chat_ids() -> List[int]:
    ids=[]
    for item in REPORT_CHAT_IDS.split(","):
        item=item.strip()
        if item and (item.isdigit() or (item.startswith('-') and item[1:].isdigit())):
            ids.append(int(item))
    return ids

# ========== FASTAPI ЭНДПОИНТЫ ==========
@app.get("/")
async def root():
    return {"status":"online","service":"telegram-reviews-bot","version":"2.0"}

@app.get("/health")
async def health_check():
    return {"telegram":bool(TELEGRAM_TOKEN),"chatgpt":test_chatgpt_api(),"database":os.path.exists(DB_PATH)}

@app.post("/webhook")
async def telegram_webhook(request:Request):
    update_data = await request.json()
    chat_id = None
    try:
        if "message" in update_data:
            message = update_data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text","").strip()
            if text.startswith("/start"):
                keyboard = [[{"text":"📋 Инструкция и команды","callback_data":"help"}]]
                send_telegram_message(chat_id,f"🤖 Бот {SERVICE_NAME} активирован",keyboard=keyboard)
            elif text.startswith("/myid"):
                send_telegram_message(chat_id,f"🆔 {chat_id}")
            elif text.startswith("/stats"):
                stats = get_review_stats()
                msg = (
                    f"📊 *Статистика отзывов*\n"
                    f"Общее: {stats['total_reviews']}\n"
                    f"Средний рейтинг: {stats['average_rating']}\n"
                    f"За неделю: {stats['weekly_reviews']}\n"
                    f"Распределение по звёздам: {', '.join(f'{r['rating']}⭐={r['count']}' for r in stats['rating_distribution'])}"
                )
                send_telegram_message(chat_id,msg)
            elif text.startswith("/analyze"):
                review_text = text.replace("/analyze","",1).strip()
                if not review_text: return {"ok":True}
                analysis = analyze_review_text(review_text)
                save_review_to_db(chat_id, review_text, analysis)
                stars = format_stars(analysis.get("rating",3))
                msg = f"{stars}\n🎭 {analysis.get('sentiment')}\n{generate_response_template(analysis.get('response_type','clarification'))}"
                send_telegram_message(chat_id,msg)
        elif "callback_query" in update_data:
            query = update_data["callback_query"]
            chat_id = query["message"]["chat"]["id"]
            data = query.get("data","")
            if data=="help":
                help_text = (
                    "📋 *Команды бота*\n"
                    "/start - запуск бота\n"
                    "/myid - ваш Telegram ID\n"
                    "/analyze <текст> - анализ отзыва\n"
                    "/stats - статистика отзывов\n"
                    "Кнопка с инструкцией всегда доступна"
                )
                send_telegram_message(chat_id,help_text)
        return {"ok":True}
    except Exception as e:
        logger.error(f"❌ Ошибка webhook chat_id={chat_id}: {e}")
        return {"ok":False,"error":str(e)}

# ========== ЗАПУСК ==========
if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)