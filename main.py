import os
import json
import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DB_PATH = "reviews.db"

app = FastAPI()

# -------------------------------------------------
# КОНФИГУРАЦИЯ
# -------------------------------------------------

SERVICE_NAME = "ЛИРА"
SERVICE_ADDRESS = "Нижний Новгород, ул. Удмуртская, 10"
SERVICE_PHONE = "+7 (XXX) XXX-XX-XX"

def get_env(name: str, default: str = None) -> str:
    value = os.getenv(name, default)
    if not value and default is None:
        raise RuntimeError(f"{name} не установлен")
    return value

# -------------------------------------------------
# БАЗА ДАННЫХ
# -------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            text TEXT,
            rating INTEGER,
            sentiment TEXT,
            categories TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_review(chat_id: int, text: str, rating: int, sentiment: str, categories: List[str]):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO reviews (chat_id, text, rating, sentiment, categories, created_at) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (chat_id, text, rating, sentiment, json.dumps(categories), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

# -------------------------------------------------
# АНАЛИЗ ОТЗЫВОВ
# -------------------------------------------------

def analyze_with_deepseek(text: str) -> Dict:
    """Анализ через DeepSeek с возвратом структурированных данных"""
    try:
        api_key = get_env("DEEPSEEK_API_KEY", "")
        if not api_key:
            return simple_analyze(text)
            
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        prompt = f"""Проанализируй отзыв для автосервиса и верни JSON:
{{
    "rating": 1-5,
    "sentiment": "very_negative/negative/neutral/positive/very_positive",
    "categories": ["quality", "service", "time", "price", "cleanliness"],
    "violations": ["insults", "fake_info", "spam"] или [],
    "suitable_for_dialogue": true/false
}}

Отзыв: "{text}"
"""
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        result = r.json()["choices"][0]["message"]["content"]
        
        # Парсим JSON ответ
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            result = result.split("```")[1].split("```")[0]
            
        return json.loads(result)
        
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return simple_analyze(text)

def simple_analyze(text: str) -> Dict:
    """Простой анализ по ключевым словам"""
    text_lower = text.lower()
    
    # Определение рейтинга
    negative = ['плох', 'ужас', 'кошмар', 'отврат', 'не рекоменд']
    positive = ['хорош', 'отличн', 'супер', 'рекоменд', 'спасиб']
    
    neg = sum(1 for word in negative if word in text_lower)
    pos = sum(1 for word in positive if word in text_lower)
    
    if neg > pos:
        rating = 1 if neg > 3 else 2
        sentiment = "negative"
    elif pos > neg:
        rating = 5 if pos > 3 else 4
        sentiment = "positive"
    else:
        rating = 3
        sentiment = "neutral"
    
    # Категории
    categories = []
    if any(word in text_lower for word in ['ремонт', 'почин', 'диагност']):
        categories.append('quality')
    if any(word in text_lower for word in ['обслуживан', 'приёмк']):
        categories.append('service')
    if any(word in text_lower for word in ['время', 'ждал', 'долго']):
        categories.append('time')
    
    return {
        "rating": rating,
        "sentiment": sentiment,
        "categories": categories,
        "violations": [],
        "suitable_for_dialogue": True
    }

# -------------------------------------------------
# ТЕЛЕГРАМ ОТВЕТЫ
# -------------------------------------------------

def telegram_request(method: str, payload: dict):
    token = get_env("TELEGRAM_BOT_TOKEN")
    url = TELEGRAM_API_URL.format(token=token, method=method)
    response = requests.post(url, json=payload, timeout=15)
    if response.status_code != 200:
        logger.error(f"Telegram API error: {response.text}")
    return response.json()

def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    return telegram_request("sendMessage", payload)

def send_keyboard(chat_id: int, text: str, buttons: List[List[Dict]]):
    keyboard = {"inline_keyboard": buttons}
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    return telegram_request("sendMessage", payload)

# -------------------------------------------------
# КОМАНДЫ БОТА
# -------------------------------------------------

def handle_start(chat_id: int):
    text = f"""🤖 *Бот автосервиса «{SERVICE_NAME}»*

📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

*Команды:*
▫️ /analyze текст - анализ отзыва
▫️ /stats - статистика
▫️ /myid - ваш chat_id
▫️ /report - отчёт за неделю

*Пример:*
`/analyze Отличный сервис, быстро починили!`"""
    
    send_message(chat_id, text)

def handle_analyze(chat_id: int, text: str):
    if not text.strip():
        send_message(chat_id, "Напишите: /analyze ваш текст отзыва")
        return
    
    # Анализируем
    analysis = analyze_with_deepseek(text)
    rating = analysis.get("rating", 3)
    sentiment = analysis.get("sentiment", "neutral")
    categories = analysis.get("categories", [])
    violations = analysis.get("violations", [])
    
    # Сохраняем
    save_review(chat_id, text, rating, sentiment, categories)
    
    # Формируем ответ
    stars = "⭐" * rating + "☆" * (5 - rating)
    response = f"""{stars}
📊 *РЕЗУЛЬТАТ АНАЛИЗА*

📝 Текст: {text[:150]}...

🎯 Оценка: {rating}/5 звезд
🎭 Тональность: {sentiment}"""
    
    if categories:
        response += f"\n🏷 Категории: {', '.join(categories)}"
    
    if violations:
        response += f"\n🚨 Нарушения: {', '.join(violations)}"
    
    # Кнопки
    buttons = []
    if rating <= 3:
        buttons.append([{"text": "📝 Сформировать ответ", "callback_data": f"response:{rating}"}])
    if rating >= 4:
        buttons.append([{"text": "🙏 Ответ с благодарностью", "callback_data": f"thanks:{rating}"}])
    
    if buttons:
        send_keyboard(chat_id, response, buttons)
    else:
        send_message(chat_id, response)

def handle_stats(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), AVG(rating) FROM reviews")
    total, avg = c.fetchone()
    conn.close()
    
    avg = avg or 0
    response = f"""📊 *СТАТИСТИКА*

Всего отзывов: {total}
Средний рейтинг: {avg:.1f}/5

📍 {SERVICE_ADDRESS}"""
    
    send_message(chat_id, response)

def handle_myid(chat_id: int):
    send_message(chat_id, f"🆔 *Ваш Chat ID:* `{chat_id}`")

# -------------------------------------------------
# WEBHOOK ОБРАБОТЧИК
# -------------------------------------------------

@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        
        if text.startswith("/start"):
            handle_start(chat_id)
        elif text.startswith("/analyze"):
            content = text[8:].strip()  # Убираем "/analyze "
            handle_analyze(chat_id, content)
        elif text.startswith("/stats"):
            handle_stats(chat_id)
        elif text.startswith("/myid") or text.startswith("/id"):
            handle_myid(chat_id)
        elif text.startswith("/"):
            send_message(chat_id, "Неизвестная команда. Используйте /start")
    
    elif "callback_query" in update:
        callback = update["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        data = callback["data"]
        
        if data.startswith("response:"):
            rating = data.split(":")[1]
            response = f"""📝 *ОТВЕТ ДЛЯ ПЛОЩАДКИ*

Благодарим за обратную связь. Для решения вопроса просим предоставить номер и дату заказ-наряда. Готовы связаться с вами для урегулирования ситуации.

С уважением, команда автосервиса «{SERVICE_NAME}»
📞 {SERVICE_PHONE}
📍 {SERVICE_ADDRESS}"""
            
            send_message(chat_id, response)
        
        elif data.startswith("thanks:"):
            response = f"""🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*

Рады, что остались довольны обслуживанием! 😊
Спасибо за тёплые слова — обязательно передадим команде.

Ждём вас снова в автосервисе «{SERVICE_NAME}»!

С наилучшими пожеланиями,
команда автосервиса «{SERVICE_NAME}»"""
            
            send_message(chat_id, response)
    
    return {"ok": True}

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "telegram-bot"}

# -------------------------------------------------
# ЗАПУСК
# -------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
