"""
Telegram Review Analyzer Bot - Упрощенная версия "все в одном файле"
Автоматическая настройка для Railway и других платформ
"""

import os
import json
import sqlite3
import logging
import re
import requests
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from typing import List, Dict, Optional, Any
from openai import OpenAI

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ (можно менять) ==========
SERVICE_NAME = "Автосервис 'МастерВин'"
SERVICE_ADDRESS = "г. Москва, ул. Автозаводская, 15"
SERVICE_PHONE = "+7 (495) 123-45-67"
SERVICE_WEBSITE = "https://mastervin-auto.ru"

# ========== АВТОМАТИЧЕСКОЕ ПОЛУЧЕНИЕ КОНФИГУРАЦИИ ==========
# 1. Telegram токен (ищем в разных переменных окружения)
TELEGRAM_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN") or 
    os.getenv("TELEGRAM_TOKEN") or 
    os.getenv("BOT_TOKEN") or 
    ""  # Если не нашли - будет ошибка при запуске
)

# 2. OpenAI ключ (можно оставить пустым, будет работать простой анализ)
OPENAI_API_KEY = (
    os.getenv("OPENAI_API_KEY") or 
    os.getenv("OPENAI_KEY") or 
    ""
)

# 3. Автоматическое определение домена (для вебхука)
def get_domain():
    """Автоматически определяем домен сервера"""
    # Railway
    if os.getenv("RAILWAY_STATIC_URL"):
        return os.getenv("RAILWAY_STATIC_URL")
    if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"
    
    # Render
    if os.getenv("RENDER_EXTERNAL_URL"):
        return os.getenv("RENDER_EXTERNAL_URL")
    
    # Heroku
    if os.getenv("HEROKU_APP_NAME"):
        return f"https://{os.getenv('HEROKU_APP_NAME')}.herokuapp.com"
    
    # Локально или неизвестно - возвращаем None
    return None

DOMAIN = get_domain()

# 4. Chat IDs для отчетов (можно несколько через запятую)
REPORT_CHAT_IDS = [
    int(chat_id.strip()) 
    for chat_id in (os.getenv("REPORT_CHAT_IDS", "").split(",") if os.getenv("REPORT_CHAT_IDS") else [])
    if chat_id.strip().isdigit()
]

# 5. Порт (автоматически определяется на платформах)
PORT = int(os.getenv("PORT", "8000"))

# ========== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ==========
app = FastAPI(
    title="Telegram Review Analyzer Bot",
    description="Автоматический анализ отзывов для автосервиса",
    version="3.0"
)

# OpenAI клиент (если есть ключ)
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Telegram API URL
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

# База данных
DB_PATH = "reviews.db"

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    """Подключение к SQLite базе"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Инициализация базы данных"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Таблица отзывов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                rating INTEGER NOT NULL,
                sentiment TEXT,
                categories TEXT,
                requires_response BOOLEAN,
                response_type TEXT,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(chat_id, text, created_at)
            )
        """)
        
        # Индексы для быстрого поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_chat_id ON reviews(chat_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating)")
        
        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

# Инициализируем БД при импорте
init_database()

# ========== TELEGRAM ФУНКЦИИ ==========
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Отправка запроса к Telegram API"""
    if not TELEGRAM_TOKEN:
        logger.error("❌ Telegram токен не установлен")
        return None
    
    try:
        url = f"{TELEGRAM_API}/{method}"
        response = requests.post(url, json=data, timeout=15)
        response.raise_for_status()
        result = response.json()
        
        if not result.get("ok"):
            logger.error(f"❌ Telegram API ошибка {method}: {result.get('description')}")
            return None
            
        return result
        
    except requests.exceptions.Timeout:
        logger.error(f"❌ Telegram API таймаут: {method}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram API {method}: {e}")
        return None

def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown", 
                         keyboard: List[List[Dict]] = None, disable_preview: bool = True):
    """Отправка сообщения в Telegram"""
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview
    }
    
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    
    return telegram_api_request("sendMessage", data)

# ========== АНАЛИЗ ОТЗЫВОВ ==========
def analyze_with_chatgpt(text: str) -> Optional[Dict[str, Any]]:
    """Анализ отзыва с помощью ChatGPT"""
    if not client:
        return None
    
    try:
        prompt = f"""Ты — опытный менеджер автосервиса. Проанализируй отзыв клиента и верни только JSON без пояснений.

Отзыв: "{text[:1000]}"

Верни JSON в таком формате:
{{
    "rating": 1-5 (1-очень плохо, 5-отлично),
    "sentiment": "negative/neutral/positive/very_negative/very_positive",
    "categories": ["quality","service","time","price","cleanliness","diagnostics","professionalism","communication"],
    "requires_response": true/false,
    "response_type": "apology/thanks/clarification/contact"
}}

Анализируй тщательно, учитывай контекст автосервиса."""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        
        # Ищем JSON в ответе
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            analysis_result = json.loads(json_match.group())
            analysis_result["source"] = "chatgpt"
            logger.info(f"✅ ChatGPT анализ: рейтинг {analysis_result.get('rating')}, {analysis_result.get('sentiment')}")
            return analysis_result
            
        logger.warning(f"⚠️ ChatGPT не вернул JSON: {content[:100]}...")
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка ChatGPT: {e}")
        return None

def simple_text_analysis(text: str) -> Dict[str, Any]:
    """Простой анализ на основе ключевых слов"""
    text_lower = text.lower()
    
    # Ключевые слова для анализа
    negative_words = ["плохо", "ужас", "кошмар", "отврат", "не рекоменд", "никогда", "хуже", "жалоба", "разочарован", "обман"]
    positive_words = ["хорошо", "отлично", "супер", "класс", "спасибо", "рекомендую", "доволен", "прекрасно", "отличный", "благодарю"]
    
    neg_count = sum(1 for word in negative_words if word in text_lower)
    pos_count = sum(1 for word in positive_words if word in text_lower)
    
    # Определяем рейтинг и настроение
    if neg_count > pos_count:
        rating = 1 if neg_count > 3 else 2
        sentiment = "negative" if rating == 2 else "very_negative"
        requires_response = True
        response_type = "apology"
    elif pos_count > neg_count:
        rating = 5 if pos_count > 3 else 4
        sentiment = "positive" if rating == 4 else "very_positive"
        requires_response = True
        response_type = "thanks"
    else:
        rating = 3
        sentiment = "neutral"
        requires_response = False
        response_type = "clarification"
    
    # Определяем категории
    categories = []
    category_keywords = {
        "quality": ["ремонт", "почини", "диагност", "поломк", "деталь", "запчасть"],
        "service": ["обслуживан", "прием", "мастер", "менеджер", "персонал", "сотрудник"],
        "price": ["цена", "дорог", "дешев", "стоимость", "оплат", "деньги"],
        "time": ["ждал", "долго", "быстро", "время", "срок", "оператив"],
        "cleanliness": ["чистот", "гряз", "порядок", "уборк", "аккурат"],
        "communication": ["общение", "объясни", "рассказ", "информац", "связь", "звонок"]
    }
    
    for category, keywords in category_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            categories.append(category)
    
    logger.info(f"✅ Простой анализ: рейтинг {rating}, {sentiment}, категории: {categories}")
    
    return {
        "rating": rating,
        "sentiment": sentiment,
        "categories": categories,
        "requires_response": requires_response,
        "response_type": response_type,
        "source": "simple_analysis"
    }

def analyze_review_text(text: str) -> Dict[str, Any]:
    """Основная функция анализа (пробуем ChatGPT, потом простой анализ)"""
    if not text or len(text.strip()) < 3:
        return {
            "rating": 3,
            "sentiment": "neutral",
            "categories": [],
            "requires_response": False,
            "response_type": "clarification",
            "source": "empty"
        }
    
    # Пробуем ChatGPT если доступен
    chatgpt_result = analyze_with_chatgpt(text)
    if chatgpt_result:
        return chatgpt_result
    
    # Если ChatGPT недоступен - простой анализ
    return simple_text_analysis(text)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def save_review_to_db(chat_id: int, text: str, analysis: Dict[str, Any]) -> bool:
    """Сохранение отзыва в базу данных"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reviews 
            (chat_id, text, rating, sentiment, categories, requires_response, response_type, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id,
            text,
            analysis.get("rating", 3),
            analysis.get("sentiment", "neutral"),
            json.dumps(analysis.get("categories", []), ensure_ascii=False),
            analysis.get("requires_response", False),
            analysis.get("response_type", "clarification"),
            analysis.get("source", "unknown"),
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Отзыв сохранен в БД: chat_id={chat_id}, rating={analysis.get('rating')}")
        return True
        
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ Отзыв уже существует в БД")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения в БД: {e}")
        return False

def get_review_stats(days: int = 7) -> Dict[str, Any]:
    """Получение статистики отзывов"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Общая статистика
        cursor.execute("SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM reviews")
        total_stats = cursor.fetchone()
        
        # Распределение по рейтингам
        cursor.execute("""
            SELECT rating, COUNT(*) as count 
            FROM reviews 
            GROUP BY rating 
            ORDER BY rating
        """)
        rating_stats = cursor.fetchall()
        
        # Статистика за период
        cursor.execute("""
            SELECT COUNT(*) as period_count, AVG(rating) as period_avg 
            FROM reviews 
            WHERE created_at >= datetime('now', ?)
        """, (f"-{days} days",))
        period_stats = cursor.fetchone()
        
        # Последние отзывы
        cursor.execute("""
            SELECT rating, sentiment, created_at 
            FROM reviews 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        recent_reviews = cursor.fetchall()
        
        conn.close()
        
        # Формируем результат
        avg_rating = total_stats["avg_rating"] if total_stats["avg_rating"] else 0
        period_avg = period_stats["period_avg"] if period_stats["period_avg"] else 0
        
        return {
            "total_reviews": total_stats["total"] or 0,
            "average_rating": round(avg_rating, 2),
            "weekly_reviews": period_stats["period_count"] or 0,
            "weekly_average": round(period_avg, 2),
            "rating_distribution": [
                {"rating": row["rating"], "count": row["count"]} 
                for row in rating_stats
            ],
            "recent_reviews": [
                {
                    "rating": row["rating"],
                    "sentiment": row["sentiment"],
                    "created_at": row["created_at"]
                }
                for row in recent_reviews
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {
            "total_reviews": 0,
            "average_rating": 0,
            "weekly_reviews": 0,
            "weekly_average": 0,
            "rating_distribution": [],
            "recent_reviews": []
        }

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def format_stars(rating: int) -> str:
    """Форматирование рейтинга в звезды"""
    if 1 <= rating <= 5:
        return "⭐" * rating + "☆" * (5 - rating)
    return "☆☆☆☆☆"

def generate_response_template(analysis: Dict[str, Any]) -> str:
    """Генерация шаблона ответа на основе анализа"""
    rating = analysis.get("rating", 3)
    sentiment = analysis.get("sentiment", "neutral")
    response_type = analysis.get("response_type", "clarification")
    categories = analysis.get("categories", [])
    
    # Базовый шаблон
    template = f"""
{format_stars(rating)} *Рейтинг: {rating}/5*
🎭 *Настроение:* {sentiment}
🏷️ *Категории:* {', '.join(categories) if categories else 'не определены'}

📍 *{SERVICE_NAME}*
📞 {SERVICE_PHONE}
🗺️ {SERVICE_ADDRESS}
🌐 {SERVICE_WEBSITE}
"""
    
    # Добавляем рекомендацию по ответу
    if response_type == "apology":
        template += "\n📋 *Рекомендуется:* Ответ с извинениями и предложением решения"
    elif response_type == "thanks":
        template += "\n🙏 *Рекомендуется:* Ответ с благодарностью и приглашением снова"
    elif response_type == "contact":
        template += "\n📞 *Рекомендуется:* Связаться с клиентом для уточнения"
    else:
        template += "\n❓ *Рекомендуется:* Запросить дополнительные детали"
    
    return template.strip()

def test_openai_connection() -> Dict[str, Any]:
    """Тест подключения к OpenAI"""
    if not client:
        return {"status": "disabled", "message": "OPENAI_API_KEY не установлен"}
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Тест"}],
            max_tokens=5,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()
        return {"status": "success", "message": f"Подключено: {answer}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ========== АВТОМАТИЧЕСКАЯ НАСТРОЙКА ==========
async def auto_configure_webhook():
    """Автоматическая настройка вебхука при запуске"""
    if not TELEGRAM_TOKEN:
        logger.error("❌ Не могу настроить вебхук: TELEGRAM_TOKEN не установлен")
        return
    
    if not DOMAIN:
        logger.warning("⚠️ Не могу настроить вебхук: домен не определен")
        logger.info("💡 Подсказка: установите переменную RAILWAY_STATIC_URL или укажите домен вручную")
        return
    
    webhook_url = f"{DOMAIN}/webhook"
    
    try:
        # Проверяем текущий вебхук
        check_response = requests.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=10)
        
        if check_response.status_code == 200:
            webhook_info = check_response.json()
            current_url = webhook_info.get("result", {}).get("url", "")
            
            if current_url == webhook_url:
                logger.info(f"✅ Вебхук уже настроен: {webhook_url}")
                return
        
        # Устанавливаем новый вебхук
        logger.info(f"🔄 Настраиваю вебхук: {webhook_url}")
        
        set_response = requests.post(
            f"{TELEGRAM_API}/setWebhook",
            json={"url": webhook_url, "max_connections": 100, "drop_pending_updates": True},
            timeout=15
        )
        
        if set_response.status_code == 200:
            result = set_response.json()
            if result.get("ok"):
                logger.info(f"✅ Вебхук успешно настроен: {webhook_url}")
            else:
                logger.error(f"❌ Ошибка настройки вебхука: {result.get('description')}")
        else:
            logger.error(f"❌ HTTP ошибка настройки вебхука: {set_response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка автоматической настройки вебхука: {e}")
        logger.info("ℹ️ Вы можете настроить вебхук вручную после запуска сервера")

# ========== FASTAPI ЭНДПОИНТЫ ==========
@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": "Telegram Review Analyzer Bot",
        "version": "3.0",
        "status": "online",
        "features": ["review_analysis", "telegram_bot", "statistics", "chatgpt_integration"],
        "endpoints": {
            "health": "/health",
            "stats": "/stats",
            "webhook_info": "/webhook_info",
            "set_webhook": "/set_webhook (POST)",
            "test_openai": "/test_openai"
        },
        "config": {
            "service_name": SERVICE_NAME,
            "has_telegram_token": bool(TELEGRAM_TOKEN),
            "has_openai_key": bool(OPENAI_API_KEY),
            "domain": DOMAIN or "не определен",
            "report_chats": REPORT_CHAT_IDS
        }
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    openai_test = test_openai_connection()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "telegram": {
                "configured": bool(TELEGRAM_TOKEN),
                "webhook_url": f"{DOMAIN}/webhook" if DOMAIN else None
            },
            "openai": openai_test,
            "database": {
                "exists": os.path.exists(DB_PATH),
                "path": DB_PATH
            }
        },
        "system": {
            "python_version": os.sys.version,
            "platform": os.sys.platform
        }
    }

@app.get("/stats")
async def get_stats_api(days: int = 7):
    """API статистики отзывов"""
    stats = get_review_stats(days)
    return {
        "period_days": days,
        "statistics": stats,
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/webhook_info")
async def get_webhook_info():
    """Получение информации о текущем вебхуке"""
    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=400, detail="TELEGRAM_TOKEN не установлен")
    
    try:
        response = requests.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=10)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/set_webhook")
async def set_webhook(request: Request):
    """Установка вебхука (можно указать свой URL)"""
    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=400, detail="TELEGRAM_TOKEN не установлен")
    
    try:
        data = await request.json()
        webhook_url = data.get("url", f"{DOMAIN}/webhook" if DOMAIN else None)
        
        if not webhook_url:
            raise HTTPException(status_code=400, detail="URL не указан и домен не определен")
        
        response = requests.post(
            f"{TELEGRAM_API}/setWebhook",
            json={
                "url": webhook_url,
                "max_connections": 100,
                "drop_pending_updates": True
            },
            timeout=15
        )
        
        return response.json()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/remove_webhook")
async def remove_webhook():
    """Удаление вебхука"""
    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=400, detail="TELEGRAM_TOKEN не установлен")
    
    try:
        response = requests.post(
            f"{TELEGRAM_API}/deleteWebhook",
            json={"drop_pending_updates": True},
            timeout=10
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test_openai")
async def test_openai_endpoint():
    """Тест подключения к OpenAI"""
    return test_openai_connection()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Основной вебхук для Telegram"""
    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=400, detail="Telegram бот не настроен")
    
    try:
        update_data = await request.json()
        logger.debug(f"📨 Получен update: {json.dumps(update_data, ensure_ascii=False)[:200]}...")
        
        # Обработка сообщений
        if "message" in update_data:
            message = update_data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "").strip()
            
            # Команда /start
            if text.startswith("/start"):
                welcome_text = f"""
🤖 *Добро пожаловать в {SERVICE_NAME}!*

Я анализирую отзывы клиентов и помогаю формировать ответы.

*Доступные команды:*
/start - это сообщение
/analyze [отзыв] - проанализировать отзыв
/stats - статистика отзывов
/myid - ваш ID в Telegram

*Пример:*
/analyze Отличный сервис, быстро починили машину!

*Контактная информация:*
📞 {SERVICE_PHONE}
📍 {SERVICE_ADDRESS}
                """.strip()
                
                keyboard = [
                    [{"text": "📋 Как пользоваться", "callback_data": "help"}],
                    [{"text": "📊 Посмотреть статистику", "callback_data": "stats_btn"}]
                ]
                
                send_telegram_message(chat_id, welcome_text, keyboard=keyboard)
                logger.info(f"✅ Отправлено приветствие chat_id={chat_id}")
            
            # Команда /myid
            elif text.startswith("/myid"):
                send_telegram_message(chat_id, f"🆔 Ваш ID: `{chat_id}`")
                logger.info(f"✅ Отправлен ID chat_id={chat_id}")
            
            # Команда /stats
            elif text.startswith("/stats"):
                stats = get_review_stats()
                
                stats_text = f"""
📊 *Статистика отзывов*

*Общая:*
• Всего отзывов: {stats['total_reviews']}
• Средний рейтинг: {stats['average_rating']}/5

*За последнюю неделю:*
• Новых отзывов: {stats['weekly_reviews']}
• Средний рейтинг: {stats['weekly_average']}/5

*Распределение:*
{chr(10).join(f'• {r["rating"]}⭐: {r["count"]} шт.' for r in stats['rating_distribution'])}

*Последние отзывы:*
{chr(10).join(f'• {r["rating"]}⭐ ({r["sentiment"]})' for r in stats['recent_reviews'][:3])}
                """.strip()
                
                send_telegram_message(chat_id, stats_text)
                logger.info(f"✅ Отправлена статистика chat_id={chat_id}")
            
            # Команда /analyze
            elif text.startswith("/analyze"):
                review_text = text.replace("/analyze", "", 1).strip()
                
                if not review_text:
                    send_telegram_message(chat_id, "📝 Пожалуйста, напишите отзыв после команды /analyze\n\nПример: /analyze Отличный сервис!")
                    return {"ok": True}
                
                # Уведомляем о начале анализа
                send_telegram_message(chat_id, "🔍 Анализирую отзыв...")
                
                # Анализируем отзыв
                analysis = analyze_review_text(review_text)
                
                # Сохраняем в БД
                save_success = save_review_to_db(chat_id, review_text, analysis)
                
                # Формируем ответ
                response_template = generate_response_template(analysis)
                
                # Добавляем информацию о сохранении
                if save_success:
                    response_template += f"\n\n💾 Отзыв сохранен в базе данных"
                else:
                    response_template += f"\n\n⚠️ Не удалось сохранить отзыв в базу"
                
                # Отправляем результат
                send_telegram_message(chat_id, response_template)
                
                # Логируем
                logger.info(f"✅ Проанализирован отзыв chat_id={chat_id}, рейтинг={analysis.get('rating')}, длина={len(review_text)}")
            
            # Любое другое сообщение (не команда)
            elif text:
                help_text = """
🤖 Я бот для анализа отзывов!

Используйте команды:
/analyze [ваш отзыв] - проанализировать отзыв
/stats - посмотреть статистику
/myid - узнать ваш ID

Пример:
/analyze Сервис хороший, но долго ждал
                """.strip()
                send_telegram_message(chat_id, help_text)
        
        # Обработка callback-запросов (нажатия кнопок)
        elif "callback_query" in update_data:
            query = update_data["callback_query"]
            chat_id = query["message"]["chat"]["id"]
            callback_data = query.get("data", "")
            
            # Ответ на callback (чтобы убрать "часики" у кнопки)
            telegram_api_request("answerCallbackQuery", {"callback_query_id": query["id"]})
            
            if callback_data == "help":
                help_text = """
📋 *Как пользоваться ботом*

1. Отправьте команду /analyze и ваш отзыв
   Пример: /analyze Мастера молодцы, все сделали качественно!

2. Бот проанализирует отзыв и покажет:
   • Рейтинг от 1 до 5 звезд
   • Настроение отзыва
   • Категории (цена, качество и т.д.)
   • Рекомендацию по ответу

3. Статистику можно посмотреть командой /stats

4. Все отзывы сохраняются в базу данных
                """.strip()
                send_telegram_message(chat_id, help_text)
            
            elif callback_data == "stats_btn":
                stats = get_review_stats()
                stats_text = f"📊 *Статистика:* {stats['total_reviews']} отзывов, средний рейтинг {stats['average_rating']}/5"
                send_telegram_message(chat_id, stats_text)
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}")
        return {"ok": False, "error": str(e)}

# ========== ЗАПУСК СЕРВЕРА ==========
@app.on_event("startup")
async def startup_event():
    """Действия при запуске сервера"""
    logger.info("=" * 50)
    logger.info("🚀 Запуск Telegram Review Analyzer Bot v3.0")
    logger.info("=" * 50)
    
    # Выводим информацию о конфигурации
    logger.info(f"📱 Сервис: {SERVICE_NAME}")
    logger.info(f"📞 Телефон: {SERVICE_PHONE}")
    logger.info(f"📍 Адрес: {SERVICE_ADDRESS}")
    logger.info(f"🌐 Домен: {DOMAIN or 'не определен'}")
    logger.info(f"🔑 Telegram токен: {'установлен' if TELEGRAM_TOKEN else 'НЕ установлен!'}")
    logger.info(f"🤖 OpenAI ключ: {'установлен' if OPENAI_API_KEY else 'не установлен'}")
    logger.info(f"📊 Отчеты в чаты: {REPORT_CHAT_IDS if REPORT_CHAT_IDS else 'не настроены'}")
    logger.info(f"💾 База данных: {DB_PATH}")
    
    # Предупреждения если что-то не настроено
    if not TELEGRAM_TOKEN:
        logger.error("❌ ВНИМАНИЕ: TELEGRAM_TOKEN не установлен! Бот не будет работать.")
        logger.info("💡 Установите переменную окружения TELEGRAM_BOT_TOKEN")
    
    if not OPENAI_API_KEY:
        logger.warning("⚠️ OPENAI_API_KEY не установлен, ChatGPT анализ недоступен")
        logger.info("💡 Будут использоваться только простые алгоритмы анализа")
    
    if not DOMAIN:
        logger.warning("⚠️ Домен не определен, вебхук нужно настроить вручную")
    
    # Автоматическая настройка вебхука
    await auto_configure_webhook()
    
    logger.info("=" * 50)
    logger.info("✅ Сервер готов к работе!")
    logger.info(f"📡 API доступно по адресу: http://0.0.0.0:{PORT}")
    if DOMAIN:
        logger.info(f"🌐 Вебхук: {DOMAIN}/webhook")
    logger.info("=" * 50)

@app.on_event("shutdown")
async def shutdown_event():
    """Действия при остановке сервера"""
    logger.info("🛑 Сервер останавливается...")

# ========== ТОЧКА ВХОДА ==========
if __name__ == "__main__":
    import uvicorn
    
    # Для локального запуска
    logger.info("🏃 Запуск в локальном режиме...")
    
    # Если локально и нет домена - показываем инструкцию
    if not DOMAIN and not os.getenv("RAILWAY_STATIC_URL"):
        logger.info("💡 Для локального тестирования используйте ngrok:")
        logger.info("   1. Установите ngrok: https://ngrok.com/")
        logger.info("   2. Запустите: ngrok http 8000")
        logger.info("   3. Скопируйте HTTPS URL и настройте вебхук через /set_webhook")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        access_log=True
    )