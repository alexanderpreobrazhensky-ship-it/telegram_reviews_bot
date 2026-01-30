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
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    """Создание подключения к базе данных"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Инициализация таблиц базы данных"""
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
    
    # Создаем индекс для быстрого поиска по дате
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
    """Безопасное получение переменной окружения с логированием"""
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
DEEPSEEK_API_KEY = safe_getenv("DEEPSEEK_API_KEY", is_secret=True)
REPORT_CHAT_IDS = safe_getenv("REPORT_CHAT_IDS", "")
PORT = int(safe_getenv("PORT", "8000"))

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ========== ОПРЕДЕЛЕНИЕ RAILWAY URL ==========
def get_railway_url() -> str:
    """Определение публичного URL Railway"""
    # Проверяем переменные Railway
    env_vars = [
        ("RAILWAY_STATIC_URL", "Railway Static URL"),
        ("RAILWAY_PUBLIC_DOMAIN", "Railway Public Domain"),
        ("RAILWAY_PRODUCTION_URL", "Railway Production URL"),
        ("RAILWAY_URL", "Railway URL")
    ]
    
    for var_name, desc in env_vars:
        url = os.getenv(var_name)
        if url:
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            logger.info(f"🌐 {desc} найден: {url}")
            return url
    
    # Fallback: генерируем URL из имени проекта
    project_name = os.getenv("RAILWAY_PROJECT_NAME")
    if project_name:
        url = f"https://{project_name}-production.up.railway.app"
        logger.info(f"🌐 Сгенерирован URL из имени проекта: {url}")
        return url
    
    # Локальная разработка
    if os.getenv("LOCAL_DEV") or "pytest" in sys.modules:
        logger.info("🌐 Локальный режим разработки")
        return "http://localhost:8000"
    
    logger.error("❌ Не удалось определить Railway URL")
    return ""

RAILWAY_URL = get_railway_url()
WEBHOOK_URL = f"{RAILWAY_URL}/webhook" if RAILWAY_URL else ""

logger.info(f"🔧 Конфигурация бота:")
logger.info(f"   • Telegram API: {'✅ Настроен' if TELEGRAM_TOKEN else '❌ Отсутствует токен'}")
logger.info(f"   • DeepSeek API: {'✅ Настроен' if DEEPSEEK_API_KEY else '⚠️ Будет простой анализ'}")
logger.info(f"   • Railway URL: {RAILWAY_URL or '❌ Не найден'}")
logger.info(f"   • Webhook URL: {WEBHOOK_URL or '❌ Не настроен'}")
logger.info(f"   • Порт сервера: {PORT}")

# ========== TELEGRAM API ФУНКЦИИ ==========
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Универсальный запрос к Telegram API"""
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
    except requests.exceptions.Timeout:
        logger.error(f"❌ Таймаут при запросе {method}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка сети в {method}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в {method}: {e}")
        return None

def send_telegram_message(chat_id: int, text: str, 
                         parse_mode: str = "Markdown",
                         keyboard: List[List[Dict]] = None) -> bool:
    """Отправка сообщения в Telegram с возможной клавиатурой"""
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

# ========== DEEPSEEK API ИНТЕГРАЦИЯ ==========
def test_deepseek_api() -> Dict[str, Any]:
    """Тестирование подключения к DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        return {
            "status": "error",
            "message": "DEEPSEEK_API_KEY не установлен",
            "available": False
        }
    
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        test_data = {
            "model": "deepseek-chat",
            "messages": [{
                "role": "user", 
                "content": "Ответь одним словом: 'работает'"
            }],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=test_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            return {
                "status": "success",
                "message": "API работает нормально",
                "available": True,
                "response": answer.strip()[:50],
                "model": result.get("model", "unknown")
            }
        elif response.status_code == 401:
            return {
                "status": "error",
                "message": "Неверный API ключ",
                "available": False,
                "status_code": 401
            }
        else:
            return {
                "status": "error",
                "message": f"Ошибка API: {response.status_code}",
                "available": False,
                "status_code": response.status_code,
                "response": response.text[:200]
            }
            
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Таймаут подключения к DeepSeek API",
            "available": False
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error", 
            "message": "Ошибка подключения к DeepSeek API",
            "available": False
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Неожиданная ошибка: {str(e)}",
            "available": False
        }

def analyze_with_deepseek(text: str) -> Optional[Dict[str, Any]]:
    """Анализ отзыва через DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        logger.warning("⚠️ DeepSeek API ключ не установлен, используется простой анализ")
        return None
    
    api_test = test_deepseek_api()
    if not api_test.get("available"):
        logger.warning(f"⚠️ DeepSeek API недоступен: {api_test.get('message')}")
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""Ты — опытный менеджер автосервиса. Проанализируй отзыв клиента и верни ТОЛЬКО JSON без пояснений.

Структура JSON:
{{
    "rating": 1-5 (1-очень плохо, 5-отлично),
    "sentiment": "negative/neutral/positive/very_negative/very_positive",
    "categories": ["quality", "service", "time", "price", "cleanliness", "diagnostics", "professionalism"],
    "requires_response": true/false (нужно ли отвечать на отзыв),
    "response_type": "apology" или "thanks" или "clarification"
}}

Отзыв для анализа: "{text[:1000]}"

Верни ТОЛЬКО JSON объект."""
        
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3
        }
        
        logger.info(f"🤖 Запрос к DeepSeek API для анализа отзыва")
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Извлекаем JSON из ответа
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            analysis_result = json.loads(json_match.group())
            logger.info(f"✅ DeepSeek анализ завершен: рейтинг {analysis_result.get('rating', 'N/A')}")
            return analysis_result
        else:
            logger.error(f"❌ Не удалось извлечь JSON из ответа DeepSeek")
            logger.debug(f"Ответ DeepSeek: {content[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("❌ Таймаут запроса к DeepSeek API")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON от DeepSeek: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка DeepSeek API: {e}")
        return None

def simple_text_analysis(text: str) -> Dict[str, Any]:
    """Простой анализ текста если DeepSeek недоступен"""
    text_lower = text.lower()
    
    # Отрицательные индикаторы
    negative_words = ["плохо", "ужас", "кошмар", "отврат", "не рекоменд", "никогда", "хуже", "жалоба"]
    # Положительные индикаторы
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
    
    # Определяем категории
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
    """Основная функция анализа текста отзыва"""
    # Пробуем DeepSeek
    deepseek_result = analyze_with_deepseek(text)
    if deepseek_result:
        deepseek_result["source"] = "deepseek"
        return deepseek_result
    
    # Fallback на простой анализ
    return simple_text_analysis(text)

# ========== БАЗА ДАННЫХ ОПЕРАЦИИ ==========
def save_review_to_db(chat_id: int, text: str, analysis: Dict[str, Any]) -> bool:
    """Сохранение отзыва в базу данных"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reviews 
            (chat_id, text, rating, sentiment, categories, analysis_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id,
            text,
            analysis.get("rating", 3),
            analysis.get("sentiment", "neutral"),
            json.dumps(analysis.get("categories", []), ensure_ascii=False),
            json.dumps(analysis, ensure_ascii=False),
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"💾 Отзыв сохранен в БД: chat_id={chat_id}, rating={analysis.get('rating')}")
        return True
        
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ Отзыв уже существует в БД: {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения отзыва: {e}")
        return False

def get_review_stats() -> Dict[str, Any]:
    """Получение статистики отзывов"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM reviews")
        total_stats = cursor.fetchone()
        
        cursor.execute("SELECT rating, COUNT(*) as count FROM reviews GROUP BY rating ORDER BY rating")
        rating_stats = cursor.fetchall()
        
        cursor.execute("""
            SELECT COUNT(*) as weekly_count 
            FROM reviews 
            WHERE created_at >= datetime('now', '-7 days')
        """)
        weekly_stats = cursor.fetchone()
        
        conn.close()
        
        return {
            "total_reviews": total_stats["total"] if total_stats else 0,
            "average_rating": round(total_stats["avg_rating"], 2) if total_stats and total_stats["avg_rating"] else 0,
            "weekly_reviews": weekly_stats["weekly_count"] if weekly_stats else 0,
            "rating_distribution": [
                {"rating": row["rating"], "count": row["count"]} 
                for row in rating_stats
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {
            "total_reviews": 0,
            "average_rating": 0,
            "weekly_reviews": 0,
            "rating_distribution": []
        }

def get_weekly_report() -> List[Dict[str, Any]]:
    """Получение отчета за неделю"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        cursor.execute("""
            SELECT rating, COUNT(*) as count, 
                   GROUP_CONCAT(DISTINCT substr(text, 1, 100)) as samples
            FROM reviews 
            WHERE created_at >= ? 
            GROUP BY rating 
            ORDER BY rating
        """, (week_ago,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                "rating": row["rating"],
                "count": row["count"],
                "samples": row["samples"].split(",") if row["samples"] else []
            }
            for row in results
        ]
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения недельного отчета: {e}")
        return []

# ========== УТИЛИТЫ ДЛЯ ЧАТОВ ==========
def get_report_chat_ids() -> List[int]:
    """Получение списка chat_id для отправки отчетов"""
    if not REPORT_CHAT_IDS:
        return []
    
    chat_ids = []
    for item in REPORT_CHAT_IDS.split(","):
        item = item.strip()
        if item and (item.isdigit() or (item.startswith('-') and item[1:].isdigit())):
            chat_ids.append(int(item))
    
    logger.info(f"📊 Загружено {len(chat_ids)} chat_id для отчетов")
    return chat_ids

def format_stars(rating: int) -> str:
    """Форматирование рейтинга в звездочки"""
    return "⭐" * rating + "☆" * (5 - rating)

def generate_response_template(response_type: str) -> str:
    """Генерация шаблона ответа"""
    templates = {
        "apology": f"""📋 *ОТВЕТ НА НЕГАТИВНЫЙ ОТЗЫВ*

Уважаемый клиент,

Благодарим за обратную связь и приносим извинения за предоставленные неудобства.
Для детального разбора ситуации просим предоставить номер заказ-наряда и дату обращения.

Наша команда готова связаться с вами для решения вопроса.

📍 *{SERVICE_NAME}*
📞 {SERVICE_PHONE}
{SERVICE_ADDRESS}""",

        "thanks": f"""🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*

Спасибо за тёплые слова и высокую оценку нашей работы! 😊
Мы рады, что вы остались довольны обслуживанием.

Ваш отзыв очень важен для нас и мотивирует команду становиться лучше.

Ждём вас снова!

📍 *С уважением, команда {SERVICE_NAME}*""",

        "clarification": f"""❓ *ЗАПРОС УТОЧНЕНИЯ*

Спасибо за ваш отзыв!

Для более точного понимания вашего опыта могли бы вы уточнить:
1. Что именно вам понравилось/не понравилось?
2. Какой именно сервис/услугу вы получили?

Эта информация поможет нам стать лучше.

📍 *{SERVICE_NAME}*"""
    }
    
    return templates.get(response_type, templates["clarification"])

# ========== FASTAPI ПРИЛОЖЕНИЕ ==========
app = FastAPI(title="Telegram Reviews Bot", version="2.0")

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    logger.info("=" * 60)
    logger.info("🚀 Запуск Telegram Reviews Bot")
    logger.info("=" * 60)
    
    # Проверка конфигурации
    if not TELEGRAM_TOKEN:
        logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    # Тестирование DeepSeek API
    deepseek_status = test_deepseek_api()
    if DEEPSEEK_API_KEY:
        if deepseek_status.get("available"):
            logger.info(f"✅ DeepSeek API: {deepseek_status.get('message')}")
        else:
            logger.warning(f"⚠️ DeepSeek API: {deepseek_status.get('message')}")
    
    # Установка вебхука
    if WEBHOOK_URL:
        try:
            result = telegram_api_request("setWebhook", {"url": WEBHOOK_URL})
            if result:
                logger.info(f"✅ Вебхук установлен: {WEBHOOK_URL}")
                
                # Проверка вебхука
                webhook_info = telegram_api_request("getWebhookInfo", {})
                if webhook_info:
                    info = webhook_info.get("result", {})
                    logger.info(f"ℹ️ Информация о вебхуке: URL={info.get('url')}, Pending={info.get('pending_update_count')}")
            else:
                logger.error("❌ Не удалось установить вебхук")
        except Exception as e:
            logger.error(f"❌ Ошибка установки вебхука: {e}")
    else:
        logger.warning("⚠️ WEBHOOK_URL не настроен, вебхук не установлен")
    
    logger.info("=" * 60)

# ========== API ЭНДПОИНТЫ ==========
@app.get("/")
async def root():
    """Корневой endpoint для проверки здоровья"""
    return {
        "status": "online",
        "service": "telegram-reviews-bot",
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/health",
            "debug": "/debug",
            "deepseek_test": "/test-deepseek",
            "stats": "/stats",
            "set_webhook": "/set-webhook"
        }
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    deepseek_status = test_deepseek_api() if DEEPSEEK_API_KEY else {"available": False, "message": "API ключ не установлен"}
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "telegram": bool(TELEGRAM_TOKEN),
            "deepseek": deepseek_status,
            "database": os.path.exists(DB_PATH),
            "webhook": bool(WEBHOOK_URL)
        },
        "environment": {
            "railway_url": RAILWAY_URL,
            "webhook_url": WEBHOOK_URL,
            "port": PORT
        }
    }

@app.get("/debug")
async def debug_info():
    """Детальная отладочная информация"""
    stats = get_review_stats()
    deepseek_status = test_deepseek_api() if DEEPSEEK_API_KEY else {"available": False, "message": "API ключ не установлен"}
    
    return {
        "config": {
            "telegram_token_set": bool(TELEGRAM_TOKEN),
            "deepseek_key_set": bool(DEEPSEEK_API_KEY),
            "report_chat_ids": get_report_chat_ids(),
            "railway_url": RAILWAY_URL,
            "webhook_url": WEBHOOK_URL,
            "service_name": SERVICE_NAME
        },
        "status": {
            "deepseek_api": deepseek_status,
            "database": {
                "exists": os.path.exists(DB_PATH),
                "size_bytes": os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
                "total_reviews": stats.get("total_reviews", 0)
            }
        },
        "statistics": stats,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/test-deepseek")
async def test_deepseek_endpoint():
    """Тестирование DeepSeek API (как запрашивали)"""
    result = test_deepseek_api()
    
    return {
        "test": "deepseek_api_connection",
        "timestamp": datetime.utcnow().isoformat(),
        "result": result
    }

@app.get("/stats")
async def statistics():
    """Статистика отзывов"""
    stats = get_review_stats()
    weekly = get_weekly_report()
    
    return {
        "statistics": stats,
        "weekly_report": weekly,
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/set-webhook")
async def manual_set_webhook():
    """Ручная установка вебхука"""
    if not WEBHOOK_URL:
        return {"error": "WEBHOOK_URL не настроен"}
    
    result = telegram_api_request("setWebhook", {"url": WEBHOOK_URL})
    
    if result:
        return {
            "success": True,
            "message": "Вебхук установлен",
            "url": WEBHOOK_URL,
            "response": result
        }
    else:
        return {
            "success": False,
            "message": "Не удалось установить вебхук",
            "url": WEBHOOK_URL
        }

# ========== TELEGRAM WEBHOOK ОБРАБОТЧИК ==========
@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Основной обработчик вебхуков от Telegram"""
    try:
        # Получаем и логируем запрос
        update_data = await request.json()
        update_id = update_data.get("update_id", "unknown")
        logger.info(f"📨 Получен вебхук update_id: {update_id}")
        
        # Обработка callback_query (нажатие на кнопки)
        if "callback_query" in update_data:
            callback = update_data["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            
            logger.info(f"🔘 Callback от {chat_id}: {data}")
            
            # Обработка разных типов callback
            if data.startswith("response_"):
                parts = data.split("_")
                if len(parts) >= 2:
                    response_type = parts[1]
                    template = generate_response_template(response_type)
                    send_telegram_message(chat_id, template)
                    
                    # Отвечаем на callback
                    telegram_api_request("answerCallbackQuery", {
                        "callback_query_id": callback["id"],
                        "text": "Ответ сформирован"
                    })
            
            return {"ok": True}
        
        # Обработка обычных сообщений
        if "message" not in update_data:
            logger.debug("Вебхук без сообщения")
            return {"ok": True}
        
        message = update_data["message"]
        chat_id = message["chat"]["id"]
        message_text = message.get("text", "").strip()
        
        if not message_text:
            send_telegram_message(chat_id, "Пожалуйста, отправьте текстовое сообщение.")
            return {"ok": True}
        
        logger.info(f"💬 Сообщение от {chat_id}: {message_text[:100]}...")
        
        # Обработка команд
        if message_text.startswith("/start"):
            welcome_message = f"""🤖 *Бот автосервиса «{SERVICE_NAME}»*

📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

*Основные команды:*
▫️ `/analyze текст` — анализ отзыва
▫️ `/stats` — статистика отзывов
▫️ `/myid` — ваш идентификатор
▫️ `/report` — отчет за неделю (только для администраторов)

*Пример использования:*
`/analyзе Отличный сервис, быстро починили!`

*Анализ включает:* 
• Оценку от 1 до 5 ⭐
• Определение тональности
• Категоризацию проблем
• Рекомендации по ответу"""
            
            send_telegram_message(chat_id, welcome_message)
        
        elif message_text.startswith("/myid"):
            send_telegram_message(chat_id, f"🆔 *Ваш Chat ID:* `{chat_id}`")
        
        elif message_text.startswith("/analyze"):
            # Извлекаем текст отзыва
            review_text = message_text.replace("/analyze", "", 1).strip()
            
            if not review_text:
                send_telegram_message(chat_id, "Пожалуйста, укажите текст отзыва:\n`/analyze Ваш текст отзыва здесь`")
                return {"ok": True}
            
            if len(review_text) < 5:
                send_telegram_message(chat_id, "Текст отзыва слишком короткий. Пожалуйста, напишите подробнее.")
                return {"ok": True}
            
            # Анализируем отзыв
            logger.info(f"🔍 Анализ отзыва от {chat_id}, длина: {len(review_text)} символов")
            analysis_result = analyze_review_text(review_text)
            
            # Сохраняем в БД
            save_review_to_db(chat_id, review_text, analysis_result)
            
            # Формируем ответ
            rating = analysis_result.get("rating", 3)
            sentiment = analysis_result.get("sentiment", "neutral")
            categories = analysis_result.get("categories", [])
            requires_response = analysis_result.get("requires_response", False)
            response_type = analysis_result.get("response_type", "clarification")
            source = analysis_result.get("source", "unknown")
            
            stars = format_stars(rating)
            
            response_message = f"""{stars}
📊 *РЕЗУЛЬТАТ АНАЛИЗА*

📝 *Отзыв:* {review_text[:150]}...

🎯 *Оценка:* **{rating}/5**
🎭 *Тональность:* {sentiment}
🔧 *Источник анализа:* {source}"""
            
            if categories:
                response_message += f"\n🏷 *Категории:* {', '.join(categories)}"
            
            # Добавляем рекомендацию по ответу
            if requires_response:
                response_templates = {
                    "apology": "⚠️ *Рекомендуется ответить с извинениями*",
                    "thanks": "✅ *Можно ответить с благодарностью*",
                    "clarification": "❓ *Рекомендуется запросить уточнения*"
                }
                response_message += f"\n\n{response_templates.get(response_type, '')}"
            
            response_message += f"\n\n📍 *{SERVICE_NAME}*"
            
            # Создаем кнопки если требуется ответ
            buttons = []
            if requires_response and response_type in ["apology", "thanks"]:
                buttons.append([
                    {"text": "📝 Сформировать ответ", "callback_data": f"response_{response_type}"}
                ])
            
            # Отправляем сообщение
            send_telegram_message(chat_id, response_message, keyboard=buttons if buttons else None)
        
        elif message_text.startswith("/stats"):
            stats = get_review_stats()
            
            if stats["total_reviews"] == 0:
                send_telegram_message(chat_id, "📊 *Статистика пуста*\nПока нет ни одного отзыва.")
                return {"ok": True}
            
            stats_message = f"""📊 *СТАТИСТИКА ОТЗЫВОВ*

📈 Всего отзывов: {stats['total_reviews']}
⭐ Средний рейтинг: {stats['average_rating']}/5
📅 За неделю: {stats['weekly_reviews']} отзывов

*Распределение по оценкам:*"""
            
            for dist in stats["rating_distribution"]:
                stars = format_stars(dist["rating"])
                percentage = (dist["count"] / stats["total_reviews"]) * 100
                stats_message += f"\n{stars} {dist['count']} шт. ({percentage:.1f}%)"
            
            send_telegram_message(chat_id, stats_message)
        
        elif message_text.startswith("/report"):
            allowed_chats = get_report_chat_ids()
            
            if chat_id not in allowed_chats:
                send_telegram_message(chat_id, "⚠️ *Доступ запрещен*\nУ вас нет прав для просмотра отчетов.")
                return {"ok": True}
            
            weekly_report = get_weekly_report()
            
            if not weekly_report:
                send_telegram_message(chat_id, "📊 *Отчет за неделю*\nЗа последние 7 дней отзывов не было.")
                return {"ok": True}
            
            report_message = "📊 *ОТЧЕТ ЗА НЕДЕЛЮ*\n\n"
            total_reviews = sum(item["count"] for item in weekly_report)
            
            for item in weekly_report:
                stars = format_stars(item["rating"])
                percentage = (item["count"] / total_reviews) * 100 if total_reviews > 0 else 0
                bar = "█" * min(int(percentage / 10), 10)
                report_message += f"{stars} {bar} {item['count']} шт. ({percentage:.1f}%)\n"
            
            report_message += f"\n📍 *Всего отзывов за неделю:* {total_reviews}"
            
            send_telegram_message(chat_id, report_message)
        
        else:
            # Если сообщение не команда
            help_message = """🤖 *Доступные команды:*

/start — информация о боте
/analyze [текст] — анализ отзыва
/stats — статистика отзывов
/myid — ваш идентификатор
/report — отчет за неделю (администраторам)

*Пример:*
`/analyзе Быстро и качественно починили тормозную систему!`"""
            
            send_telegram_message(chat_id, help_message)
        
        return {"ok": True}
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка декодирования JSON: {e}")
        return {"ok": False, "error": "Invalid JSON"}
    except KeyError as e:
        logger.error(f"❌ Ошибка ключа в данных: {e}")
        return {"ok": False, "error": f"Missing key: {e}"}
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка в вебхуке: {e}")
        return {"ok": False, "error": str(e)}

# ========== ЗАПУСК СЕРВЕРА ==========
if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        access_log=True
    )
