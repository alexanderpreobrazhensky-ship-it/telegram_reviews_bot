import os
import sys
import json
import sqlite3
import logging
import requests
import re
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from typing import List, Dict, Optional, Any
import openai

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== КОНСТАНТЫ ==========
DB_PATH = "reviews.db"
SERVICE_NAME = "Автосервис"
SERVICE_ADDRESS = "г. Москва"
SERVICE_PHONE = "+7 999 000-00-00"

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
        CREATE INDEX IF NOT EXISTS idx_reviews_created_at 
        ON reviews(created_at)
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_database()

# ========== УТИЛИТЫ ДЛЯ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
def safe_getenv(name: str, default: str = None, is_secret: bool = False) -> str:
    value = os.getenv(name, default)
    if value:
        if is_secret or any(secret in name.upper() for secret in ["TOKEN", "KEY", "SECRET", "PASSWORD"]):
            logger.info(f"✅ {name}: установлена (значение скрыто)")
        else:
            logger.info(f"✅ {name}: {value}")
    else:
        if default is None:
            logger.warning(f"⚠️ {name}: не установлена")
        else:
            logger.info(f"✅ {name}: используем значение по умолчанию: {default}")
    return value if value is not None else default

# ========== ЗАГРУЗКА КОНФИГУРАЦИИ ==========
TELEGRAM_TOKEN = safe_getenv("TELEGRAM_BOT_TOKEN", is_secret=True)
OPENAI_API_KEY = safe_getenv("OPENAI_API_KEY", is_secret=True)
REPORT_CHAT_IDS = safe_getenv("REPORT_CHAT_IDS", "")
PORT = int(safe_getenv("PORT", "8000"))

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Настройка openai
openai.api_key = OPENAI_API_KEY

# ========== TELEGRAM API ФУНКЦИИ ==========
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not TELEGRAM_TOKEN:
        logger.error(f"❌ Не могу выполнить {method}: TELEGRAM_BOT_TOKEN не установлен")
        return None
    try:
        url = f"{TELEGRAM_API}/{method}"
        response = requests.post(url, json=data, timeout=15)
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            logger.error(f"❌ Telegram API ошибка в {method}: {result}")
            return None
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети в {method}: {e}")
        return None

def send_telegram_message(chat_id: int, text: str, 
                         parse_mode: str = "Markdown",
                         keyboard: List[List[Dict]] = None) -> bool:
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    result = telegram_api_request("sendMessage", data)
    if result:
        logger.info(f"📤 Сообщение отправлено в чат {chat_id}")
        return True
    return False

# ========== GPT-3.5 API ==========
def test_chatgpt_api() -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        return {"status": "error", "message": "OPENAI_API_KEY не установлен", "available": False}
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
        logger.warning("⚠️ OPENAI_API_KEY не установлен, используется простой анализ")
        return None
    try:
        prompt = f"""Ты — опытный менеджер автосервиса. Проанализируй отзыв клиента и верни ТОЛЬКО JSON без пояснений.

Структура JSON:
{{
    "rating": 1-5,
    "sentiment": "negative/neutral/positive/very_negative/very_positive",
    "categories": ["quality", "service", "time", "price", "cleanliness", "diagnostics", "professionalism"],
    "requires_response": true/false,
    "response_type": "apology/thanks/clarification"
}}

Отзыв для анализа: "{text[:1000]}"

Верни только JSON объект."""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        content = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            analysis_result = json.loads(json_match.group())
            logger.info(f"✅ ChatGPT анализ завершен: рейтинг {analysis_result.get('rating', 'N/A')}")
            return analysis_result
        else:
            logger.error(f"❌ Не удалось извлечь JSON из ответа ChatGPT")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка ChatGPT API: {e}")
        return None

# ========== ПРОСТОЙ АНАЛИЗ (FALLBACK) ==========
def simple_text_analysis(text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    negative_words = ["плохо", "ужас", "кошмар", "отврат", "не рекоменд", "никогда", "хуже", "жалоба"]
    positive_words = ["хорошо", "отлично", "супер", "класс", "спасибо", "рекомендую", "доволен", "прекрасно"]
    neg_count = sum(1 for word in negative_words if word in text_lower)
    pos_count = sum(1 for word in positive_words if word in text_lower)
    
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
    if any(word in text_lower for word in ["ремонт", "почини", "диагност", "поломк"]):
        categories.append("quality")
    if any(word in text_lower for word in ["обслуживан", "прием", "мастер", "менеджер"]):
        categories.append("service")
    if any(word in text_lower for word in ["цена", "дорог", "дешев", "стоимость"]):
        categories.append("price")
    if any(word in text_lower for word in ["ждал", "долго", "быстро", "время", "срок"]):
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
    if result:
        result["source"] = "chatgpt"
        return result
    return simple_text_analysis(text)

# ========== ДАЛЕЕ ОСТАЕТСЯ ВСЕ КОД, СВЯЗАННЫЙ С БАЗОЙ, TELEGRAM И FASTAPI ==========
# save_review_to_db, get_review_stats, get_weekly_report, format_stars, generate_response_template,
# get_report_chat_ids, FastAPI endpoints, webhook обработчик — всё как в твоем исходном коде
# без изменений, просто вместо deepseek используется GPT-3.5