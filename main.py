import os
import json
import sqlite3
import logging
import requests
import re
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from typing import List, Dict, Optional, Any
import openai

# ================= НАСТРОЙКА ЛОГИРОВАНИЯ =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= КОНСТАНТЫ =================
DB_PATH = "reviews.db"
SERVICE_NAME = "Автосервис"
SERVICE_ADDRESS = "г. Москва"
SERVICE_PHONE = "+7 999 000-00-00"

# ================= БАЗА ДАННЫХ =================
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
        CREATE INDEX IF NOT EXISTS idx_reviews_created_at 
        ON reviews(created_at)
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_database()

# ================= ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ =================
def safe_getenv(name: str, default: str = None, is_secret: bool = False) -> str:
    value = os.getenv(name, default)
    if value:
        if is_secret:
            logger.info(f"✅ {name}: установлена (значение скрыто)")
        else:
            logger.info(f"✅ {name}: {value}")
    else:
        logger.warning(f"⚠️ {name}: не установлена, используется значение по умолчанию")
    return value if value is not None else default

TELEGRAM_TOKEN = safe_getenv("TELEGRAM_BOT_TOKEN", is_secret=True)
OPENAI_API_KEY = safe_getenv("OPENAI_API_KEY", is_secret=True)
REPORT_CHAT_IDS = safe_getenv("REPORT_CHAT_IDS", "")
PORT = int(safe_getenv("PORT", "8000"))

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
openai.api_key = OPENAI_API_KEY

# ================= TELEGRAM =================
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен")
        return None
    try:
        url = f"{TELEGRAM_API}/{method}"
        resp = requests.post(url, json=data, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            logger.error(f"❌ Telegram API ошибка {method}: {result}")
            return None
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram API {method}: {e}")
        return None

def send_telegram_message(chat_id: int, text: str, 
                          parse_mode: str = "Markdown",
                          keyboard: List[List[Dict]] = None) -> bool:
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    return bool(telegram_api_request("sendMessage", data))

# ================= GPT-3.5 =================
def test_chatgpt_api() -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        return {"status": "error", "available": False, "message": "OPENAI_API_KEY не установлен"}
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Привет"}],
            max_tokens=5,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()
        return {"status": "success", "available": True, "response": answer}
    except Exception as e:
        return {"status": "error", "available": False, "message": str(e)}

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
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        content = resp.choices[0].message.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            analysis_result = json.loads(json_match.group())
            analysis_result["source"] = "chatgpt"
            return analysis_result
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка ChatGPT: {e}")
        return None

# ================= ПРОСТОЙ АНАЛИЗ =================
def simple_text_analysis(text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    neg_words = ["плохо","ужас","кошмар","отврат","не рекоменд","никогда","хуже","жалоба"]
    pos_words = ["хорошо","отлично","супер","класс","спасибо","рекомендую","доволен","прекрасно"]
    neg_count = sum(word in text_lower for word in neg_words)
    pos_count = sum(word in text_lower for word in pos_words)
    if neg_count>pos_count:
        rating, sentiment, req, rtype = (1 if neg_count>3 else 2, "negative", True, "apology")
    elif pos_count>neg_count:
        rating, sentiment, req, rtype = (5 if pos_count>3 else 4, "positive", True, "thanks")
    else:
        rating, sentiment, req, rtype = 3,"neutral",False,"clarification"
    categories = []
    if any(word in text_lower for word in ["ремонт","почини","диагност","поломк"]): categories.append("quality")
    if any(word in text_lower for word in ["обслуживан","прием","мастер","менеджер"]): categories.append("service")
    if any(word in text_lower for word in ["цена","дорог","дешев","стоимость"]): categories.append("price")
    if any(word in text_lower for word in ["ждал","долго","быстро","время","срок"]): categories.append("time")
    return {"rating":rating,"sentiment":sentiment,"categories":categories,"requires_response":req,"response_type":rtype,"source":"simple_analysis"}

def analyze_review_text(text: str) -> Dict[str, Any]:
    result = analyze_with_chatgpt(text)
    if result: return result
    return simple_text_analysis(text)

# ================= ДАЛЕЕ ВСЁ, ЧТО БЫЛО В КОДЕ =================
# save_review_to_db, get_review_stats, get_weekly_report, формат звезд, generate_response_template,
# обработчик /webhook и FastAPI endpoints — оставляем без изменений, только ссылки на DeepSeek заменяем на GPT.