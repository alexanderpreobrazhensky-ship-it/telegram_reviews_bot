import os
import json
import sqlite3
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import requests
from fastapi import FastAPI, Request

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DOMAIN = os.getenv("DOMAIN") or os.getenv("RAILWAY_STATIC_URL") or "http://localhost:8000"
PORT = int(os.getenv("PORT", 8000))
REPORT_CHAT_IDS = os.getenv("REPORT_CHAT_IDS", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ""
DB_PATH = "reviews.db"

# ========== ДАННЫЕ АВТОСЕРВИСА "ЛИРА" ==========
SERVICE_NAME = "Автосервис 'ЛИРА'"
SERVICE_ADDRESS = "г. Н.Новгород, ул. Удмуртская, 10"
SERVICE_PHONE = "+7 (831) 214-00-50"
SERVICE_WEBSITE = "https://lira-nn.ru"
SERVICE_TELEGRAM = "@liraavto"
SERVICE_EMAIL = "info@lira-nn.ru"

# ========== DeepSeek API конфигурация ==========
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# ========== КОНСТАНТЫ ДЛЯ ЖАЛОБ ==========
PLATFORM_COMPLAIN_TEMPLATES = {
    "google": {
        "url": "https://support.google.com/business/contact/reviews",
        "reasons": {
            "spam": "Отзыв является спамом или рекламой",
            "fake": "Фальшивый отзыв или конкурентная атака",
            "offensive": "Оскорбительный или нецензурный контент",
            "personal": "Раскрытие персональных данных",
            "irrelevant": "Не относится к нашему бизнесу"
        }
    },
    "yandex": {
        "url": "https://yandex.ru/support/business-new/reviews/reviews-moderation.html",
        "reasons": {
            "spam": "Спам или реклама",
            "fake": "Написан не клиентом",
            "offensive": "Ненормативная лексика",
            "conflict": "Конфликт интересов",
            "incorrect": "Не соответствует действительности"
        }
    },
    "2gis": {
        "url": "https://help.2gis.ru/legal/moderation_rules_reviews",
        "reasons": {
            "spam": "Коммерческое предложение или спам",
            "fake": "Отзыв написан не клиентом",
            "offensive": "Грубость или оскорбления",
            "private": "Личная информация",
            "irrelevant": "Не относится к заведению"
        }
    }
}

# ========== FastAPI ==========
app = FastAPI(title="Telegram Reviews Bot - Автосервис ЛИРА", version="1.0")

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
    
    # Таблица для жалоб
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            review_text TEXT NOT NULL,
            platform TEXT NOT NULL,
            reason TEXT NOT NULL,
            complaint_text TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_database()

# ========== TELEGRAM ==========
def telegram_api_request(method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен!")
        return None
    
    # Проверка что токен валидный
    if len(TELEGRAM_TOKEN) < 30 or "ВАШ_ТОКЕН" in TELEGRAM_TOKEN:
        logger.error(f"❌ НЕВЕРНЫЙ TELEGRAM_TOKEN: {TELEGRAM_TOKEN[:20]}...")
        return None
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
        
        response = requests.post(url, json=data, timeout=15)
        response.raise_for_status()
        
        result = response.json()
        if not result.get("ok"):
            logger.error(f"❌ Telegram API ошибка {method}: {result}")
            return None
        
        return result
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            logger.error(f"❌ 400 Bad Request: Проблема с данными запроса")
            # Логируем только первые 50 символов текста для диагностики
            if 'text' in data:
                logger.error(f"❌ Текст сообщения: {data['text'][:50]}...")
        elif e.response.status_code == 404:
            logger.error(f"❌ 404 Not Found: Проверьте TELEGRAM_TOKEN!")
        else:
            logger.error(f"❌ HTTP ошибка Telegram API {method}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram API {method}: {e}")
        return None

def send_telegram_message(chat_id: int, text: str, keyboard: List[List[Dict]] = None):
    """Отправка сообщения в Telegram БЕЗ форматирования"""
    # Убираем ВСЕ специальные символы которые могут вызвать проблемы
    safe_text = text
    
    # Убираем эмодзи
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    
    safe_text = emoji_pattern.sub(r'', safe_text)
    
    # Убираем звезды
    safe_text = safe_text.replace('⭐', '*').replace('☆', '_')
    
    # Убираем HTML/Маркдаун символы
    for char in ['<', '>', '&', '*', '_', '[', ']', '(', ')', '~', '`', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        safe_text = safe_text.replace(char, '')
    
    # Ограничиваем длину
    safe_text = safe_text[:4000]
    
    data = {
        "chat_id": chat_id, 
        "text": safe_text,
        "disable_web_page_preview": True
    }
    # НИКАКОГО parse_mode!
    
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    
    result = telegram_api_request("sendMessage", data)
    
    # Если не сработало, пробуем еще более простой вариант
    if not result:
        logger.warning("⚠️ Первая попытка не удалась, пробую упрощенную версию...")
        # Пробуем отправить только первые 100 символов
        minimal_text = safe_text[:100] + "..." if len(safe_text) > 100 else safe_text
        minimal_data = {
            "chat_id": chat_id, 
            "text": minimal_text,
            "disable_web_page_preview": True
        }
        return telegram_api_request("sendMessage", minimal_data)
    
    return result

# ========== DEEPSEEK API ==========
def analyze_with_deepseek(text: str) -> Optional[Dict[str, Any]]:
    if not DEEPSEEK_API_KEY:
        logger.warning("⚠️ DEEPSEEK_API_KEY не установлен")
        return None
    
    try:
        prompt = f"""Ты — опытный менеджер автосервиса "ЛИРА" в Нижнем Новгороде. Проанализируй отзыв клиента максимально детально и критично.
        
Наша информация для контекста:
- Название: Автосервис "ЛИРА"
- Адрес: г. Н.Новгород, ул. Удмуртская, 10
- Телефон: +7 (831) 214-00-50
- Сайт: lira-nn.ru
- Telegram: @liraavto
- Специализация: ремонт всех марок автомобилей, диагностика, ТО

Верни ТОЛЬКО JSON без пояснений. Структура JSON:

{{
    "rating": 1-5,
    "sentiment": "very_negative/negative/neutral/positive/very_positive",
    "categories": ["качество_ремонта","обслуживание","время","цена","чистота","диагностика","профессионализм","коммуникация","запчасти"],
    "requires_response": true/false,
    "response_type": "срочные_извинения/извинения/благодарность/уточнение/дополнительный_контакт",
    "key_issues": ["список конкретных проблем из отзыва"],
    "sentiment_details": {{
        "основная_эмоция": "гнев/разочарование/удовлетворение/радость/безразличие",
        "интенсивность": 1-10,
        "есть_сарказм": true/false,
        "эмоциональный_тон": "агрессивный/жалобный/нейтральный/благодарный"
    }},
    "рекомендации_менеджеру": {{
        "срочные_действия": ["конкретные действий для немедленного реагирования"],
        "долгосрочные_улучшения": ["предложения для долгосрочного улучшения"],
        "шаблон_ответа": "детальный шаблон ответа клиенту с извинениями/благодарностью и конкретными решениями",
        "требуется_доп_контакт": true/false,
        "инструкции_по_дальнейшему_взаимодействию": "инструкции по дальнейшему взаимодействию"
    }},
    "требуется_жалоба": true/false,
    "причина_жалобы": "обоснование для жалобы на отзыв, если он некорректен или оскорбителен",
    "уровень_срочности": "низкий/средний/высокий/критический",
    "автомобиль_марка": "марка автомобиля если упомянута",
    "вид_работ": "вид выполненных работ если упомянут"
}}

Отзыв клиента: "{text[:1500]}"

Проанализируй глубоко:
1. Определи реальный рейтинг (1-5) на основе содержания, а не слов
2. Выдели ВСЕ проблемы, даже если они упомянуты косвенно
3. Оцени эмоциональный настрой клиента объективно
4. Предложи КОНКРЕТНЫЕ действия для менеджеера автосервиса ЛИРА
5. Если отзыв негативный, предложи шаблон извинения с КОНКРЕТНЫМИ решениями и контактами нашего сервиса
6. Если отзыв позитивный, предложи шаблон благодарности с приглашением вернуться и ссылками на наш сайт/Telegram
7. Определи, нужна ли жалоба на отзыв (если он содержит ложь, оскорбления или явную клевету)
8. Укажи уровень срочности реакции
9. Отметь марку автомобиля и вид работ если они упомянуты
10. Учти наш адрес и контакты при составлении рекомендаций"""

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": """Ты менеджер автосервиса "ЛИРА" в Нижнем Новгороде. 
                Твой автосервис находится по адресу: ул. Удмуртская, 10. 
                Контакты: +7 (831) 214-00-50, сайт lira-nn.ru, Telegram @liraavto.
                Ты профессионально анализируешь отзывы и предлагаешь конкретные решения."""},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2000,
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            analysis_result = json.loads(json_match.group())
            analysis_result["source"] = "deepseek"
            return analysis_result
        
        logger.error(f"❌ Не удалось извлечь JSON из ответа DeepSeek: {content[:200]}")
        return None
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("❌ Ошибка аутентификации DeepSeek API: неверный API ключ")
        elif e.response.status_code == 429:
            logger.error("❌ Превышен лимит запросов DeepSeek API: проверьте баланс")
        elif e.response.status_code == 402:
            logger.error("❌ Недостаточно средств на счету DeepSeek API: пополните баланс")
            return None
        else:
            logger.error(f"❌ HTTP ошибка DeepSeek API: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка парсинга JSON от DeepSeek: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка DeepSeek API: {e}")
        return None

def test_deepseek_api() -> Dict[str, Any]:
    if not DEEPSEEK_API_KEY:
        return {"status": "error", "available": False, "message": "DEEPSEEK_API_KEY не установлен"}
    
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": "Привет! Ответь коротко: работает ли API?"}],
            "max_tokens": 20,
            "temperature": 0
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        answer = result["choices"][0]["message"]["content"].strip()
        
        return {
            "status": "success", 
            "available": True, 
            "response": answer,
            "model": DEEPSEEK_MODEL
        }
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.text[:100]}"
        return {"status": "error", "available": False, "message": error_msg}
    except Exception as e:
        return {"status": "error", "available": False, "message": str(e)}

# ========== ПРОСТОЙ АНАЛИЗ (резервный) ==========
def simple_text_analysis(text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    
    very_negative_words = ["ужас", "кошмар", "отвратительно", "никогда", "ненавижу", "развод", "воры", "обманщики", "кидалы"]
    negative_words = ["плохо", "не рекомендую", "жалоба", "разочарован", "недоволен", "переплатил", "обман", "сломал", "испортил"]
    positive_words = ["хорошо", "отлично", "спасибо", "доволен", "рекомендую", "качественно", "профессионально", "быстро", "четко"]
    very_positive_words = ["прекрасно", "супер", "великолепно", "лучший", "восхищен", "идеально", "блестяще", "мастера", "спасли"]
    
    vneg_count = sum(1 for w in very_negative_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)
    pos_count = sum(1 for w in positive_words if w in text_lower)
    vpos_count = sum(1 for w in very_positive_words if w in text_lower)
    
    total_neg = vneg_count * 2 + neg_count
    total_pos = vpos_count * 2 + pos_count
    
    if total_neg > total_pos:
        if vneg_count > 0:
            rating = 1
            sentiment = "very_negative"
        else:
            rating = 2
            sentiment = "negative"
        requires_response = True
        response_type = "срочные_извинения" if vneg_count > 0 else "извинения"
    elif total_pos > total_neg:
        if vpos_count > 0:
            rating = 5
            sentiment = "very_positive"
        else:
            rating = 4
            sentiment = "positive"
        requires_response = True
        response_type = "благодарность"
    else:
        rating = 3
        sentiment = "neutral"
        requires_response = False
        response_type = "уточнение"
    
    categories = []
    category_keywords = {
        "качество_ремонта": ["ремонт", "почини", "поломк", "брак", "качеств", "гаранти", "работа", "сделал", "исправил"],
        "обслуживание": ["обслуживан", "прием", "мастер", "менеджер", "сотрудник", "персонал", "отношение"],
        "цена": ["цена", "дорог", "дешев", "стоимость", "переплат", "обоснован", "чеков", "оплат"],
        "время": ["ждал", "долго", "быстро", "время", "срок", "оператив", "задерж", "опоздан"],
        "чистота": ["чистот", "гряз", "порядок", "уборк", "санитар", "помещен"],
        "диагностика": ["диагност", "проверк", "ошибк", "компьютер", "сканер", "электроник"],
        "профессионализм": ["профессионал", "квалификац", "опыт", "знани", "умени", "компетент"],
        "коммуникация": ["общение", "объясни", "консультац", "информац", "связь", "ответ", "звонк"],
        "запчасти": ["запчасть", "деталь", "оригинал", "аналог", "комплектующ", "масло", "фильтр"]
    }
    
    for category, keywords in category_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            categories.append(category)
    
    car_brands = ["лада", "lada", "ваз", "киа", "kia", "хендай", "hyundai", "тойота", "toyota", 
                  "форд", "ford", "реноН", "renault", "шкода", "skoda", "фольксваген", "volkswagen", 
                  "бмв", "bmw", "мерседес", "mercedes", "ауди", "audi", "ниссан", "nissan", "митсубиси", "mitsubishi"]
    
    car_brand = None
    for brand in car_brands:
        if brand in text_lower:
            car_brand = brand.capitalize()
            break
    
    return {
        "rating": rating,
        "sentiment": sentiment,
        "categories": categories,
        "requires_response": requires_response,
        "response_type": response_type,
        "source": "simple_analysis",
        "key_issues": ["Базовый анализ: используйте DeepSeek API для детального разбора"],
        "уровень_срочности": "средний",
        "автомобиль_марка": car_brand,
        "вид_работ": "ремонт" if any(w in text_lower for w in ["ремонт", "почин", "замен"]) else "диагностика" if "диагност" in text_lower else "ТО"
    }

def analyze_review_text(text: str) -> Dict[str, Any]:
    result = analyze_with_deepseek(text)
    if result:
        logger.info("✅ Использован DeepSeek анализ")
        return result
    
    logger.info("⚠️ Использован простой анализ (DeepSeek недоступен)")
    return simple_text_analysis(text)

# ========== ФОРМАТИРОВАНИЕ ОТВЕТА ==========
def format_star_rating(rating: int) -> str:
    # Простые символы вместо эмодзи
    return "*" * rating + "_" * (5 - rating)

def format_analysis_response(analysis: Dict[str, Any], review_text: str) -> str:
    stars = format_star_rating(analysis.get("rating", 3))
    
    # САМЫЙ ПРОСТОЙ ТЕКСТ
    response = f"Рейтинг: {analysis.get('rating', 3)}/5 {stars}\n"
    response += f"Настроение: {analysis.get('sentiment', 'neutral')}\n"
    response += f"Категории: {', '.join(analysis.get('categories', []))}\n\n"
    
    response += f"Анализ завершен. Отзыв сохранен в базе данных.\n\n"
    
    response += f"Сервис: {SERVICE_NAME}\n"
    response += f"Адрес: {SERVICE_ADDRESS}\n"
    response += f"Телефон: {SERVICE_PHONE}\n"
    
    return response

# ========== ФУНКЦИИ ДЛЯ ЖАЛОБ ==========
def generate_complaint_text(review_text: str, platform: str, reason_type: str, additional_info: str = "") -> str:
    platform_info = PLATFORM_COMPLAIN_TEMPLATES.get(platform, PLATFORM_COMPLAIN_TEMPLATES["google"])
    reason = platform_info["reasons"].get(reason_type, "Нарушение правил платформы")
    
    complaint_template = f"""Жалоба на отзыв

Информация о бизнесе:
- Название: {SERVICE_NAME}
- Адрес: {SERVICE_ADDRESS}
- Телефон: {SERVICE_PHONE}

Детали отзыва для проверки:
{review_text[:500]}

Причина жалобы: {reason}

Обоснование:
1. Отзыв не соответствует действительности
2. {additional_info or 'Нарушает правила публикации отзывов на платформе'}
3. Содержит недостоверную информацию о качестве наших услуг

Прошу:
1. Проверить отзыв на соответствие правилам платформы
2. При необходимости удалить отзыв
3. Принять меры к автору за нарушение правил

Контактная информация для связи:
- Email: {SERVICE_EMAIL}
- Телефон: {SERVICE_PHONE}

Дата: {datetime.now().strftime('%d.%m.%Y')}
Подпись: Представитель {SERVICE_NAME}
"""
    return complaint_template

def save_complaint_to_db(chat_id: int, review_text: str, platform: str, reason: str, complaint_text: str) -> int:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO complaints (chat_id, review_text, platform, reason, complaint_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            chat_id,
            review_text[:1000],
            platform,
            reason,
            complaint_text,
            datetime.utcnow().isoformat()
        ))
        
        complaint_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"📝 Жалоба сохранена: ID={complaint_id}, платформа={platform}")
        return complaint_id
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения жалобы: {e}")
        return -1

def get_complaint_stats() -> Dict[str, Any]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='complaints'")
        if not cursor.fetchone():
            conn.close()
            return {"total": 0, "by_platform": {}, "by_status": {}}
        
        cursor.execute("SELECT COUNT(*) as total FROM complaints")
        total = cursor.fetchone()["total"]
        
        cursor.execute("SELECT platform, COUNT(*) as count FROM complaints GROUP BY platform")
        by_platform = {row["platform"]: row["count"] for row in cursor.fetchall()}
        
        cursor.execute("SELECT status, COUNT(*) as count FROM complaints GROUP BY status")
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        cursor.execute("SELECT COUNT(*) as pending FROM complaints WHERE status = 'draft'")
        pending = cursor.fetchone()["pending"]
        
        conn.close()
        
        return {
            "total_complaints": total,
            "by_platform": by_platform,
            "by_status": by_status,
            "pending_complaints": pending
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики жалоб: {e}")
        return {"total": 0, "by_platform": {}, "by_status": {}}

# ========== БАЗА ДАННЫХ (операции) ==========
def save_review_to_db(chat_id: int, text: str, analysis: Dict[str, Any]) -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reviews (chat_id, text, rating, sentiment, categories, analysis_data, created_at)
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
        return {
            "total_reviews": total_stats["total"] if total_stats else 0,
            "average_rating": round(total_stats["avg_rating"], 2) if total_stats and total_stats["avg_rating"] else 0,
            "weekly_reviews": weekly_stats["weekly_count"] if weekly_stats else 0,
            "rating_distribution": [{"rating": r["rating"], "count": r["count"]} for r in rating_stats]
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {"total_reviews": 0, "average_rating": 0, "weekly_reviews": 0, "rating_distribution": []}

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
        return [{
            "rating": r["rating"], 
            "count": r["count"], 
            "samples": r["samples"].split(",") if r["samples"] else []
        } for r in results]
    except Exception as e:
        logger.error(f"❌ Ошибка недельного отчета: {e}")
        return []

# ========== ВЕБХУК АВТОМАТИЧЕСКАЯ НАСТРОЙКА ==========
async def auto_set_webhook():
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен, вебхук не настроен")
        return False
    
    if not DOMAIN or DOMAIN == "http://localhost:8000":
        logger.warning("⚠️ Домен не настроен, вебхук не установлен")
        return False
    
    webhook_url = f"{DOMAIN}/webhook"
    
    if not DOMAIN.startswith("https://"):
        if DOMAIN.startswith("http://"):
            secure_domain = DOMAIN.replace("http://", "https://")
            webhook_url = f"{secure_domain}/webhook"
            logger.info(f"🔄 Исправляю URL на HTTPS: {webhook_url}")
    
    logger.info(f"🔧 Настраиваю вебхук: {webhook_url}")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
                json={
                    "url": webhook_url,
                    "max_connections": 100,
                    "allowed_updates": ["message", "callback_query"]
                },
                timeout=10
            )
            
            result = response.json()
            
            if response.status_code == 200 and result.get("ok"):
                logger.info(f"✅ Вебхук успешно установлен (попытка {attempt + 1}/{max_retries})")
                logger.info(f"ℹ️ Описание: {result.get('description', 'без описания')}")
                return True
            else:
                error_msg = result.get('description', 'неизвестная ошибка')
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries}: {error_msg}")
                
                if "Conflict" in error_msg:
                    logger.info("🔄 Обнаружен конфликт, удаляю старый вебхук...")
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                        timeout=5
                    )
        
        except requests.exceptions.ConnectionError:
            logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries}: Ошибка подключения")
        except Exception as e:
            logger.error(f"❌ Попытка {attempt + 1}/{max_retries}: {str(e)[:100]}")
        
        if attempt < max_retries - 1:
            import time
            time.sleep(2)
    
    logger.error("❌ Не удалось установить вебхук после всех попыток")
    return False

# ========== ФУНКЦИИ ДИАГНОСТИКИ ==========
async def perform_diagnostics(chat_id: int):
    # Упрощенная диагностика без HTML
    diagnostics = []
    
    diagnostics.append("1. Проверка Telegram токена:")
    if not TELEGRAM_TOKEN:
        diagnostics.append("ОШИБКА: Токен не установлен")
    else:
        token_preview = f"{TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-5:]}"
        diagnostics.append(f"OK: Токен установлен ({len(TELEGRAM_TOKEN)} символов)")
        diagnostics.append(f"Префикс: {token_preview}")
    
    diagnostics.append("")
    
    diagnostics.append("2. Проверка DeepSeek API:")
    if not DEEPSEEK_API_KEY:
        diagnostics.append("ОШИБКА: Ключ не установлен")
    else:
        diagnostics.append(f"OK: Ключ установлен")
        
        deepseek_status = test_deepseek_api()
        if deepseek_status.get("available"):
            diagnostics.append(f"OK: API доступен")
        else:
            error_msg = deepseek_status.get("message", "неизвестная ошибка")
            if "402" in error_msg:
                diagnostics.append("ОШИБКА: Недостаточно средств на счету")
                diagnostics.append("Подсказка: Пополните баланс на platform.deepseek.com")
    
    diagnostics.append("")
    
    diagnostics.append("3. Проверка вебхука:")
    if not DOMAIN or DOMAIN == "http://localhost:8000":
        diagnostics.append("ОШИБКА: Домен не настроен")
    else:
        diagnostics.append(f"OK: Домен: {DOMAIN}")
    
    diagnostics.append("")
    
    diagnostics.append("4. Проверка базы данных:")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) as count FROM reviews")
            total_reviews = cursor.fetchone()["count"]
            diagnostics.append(f"OK: База данных работает")
            diagnostics.append(f"Отзывов в базе: {total_reviews}")
        else:
            diagnostics.append("ОШИБКА: Таблица reviews не найдена")
        
        conn.close()
    except Exception as e:
        diagnostics.append(f"ОШИБКА БД: {str(e)[:50]}")
    
    diagnostics.append("")
    
    diagnostics.append("5. Проверка сервера:")
    diagnostics.append(f"OK: Порт: {PORT}")
    diagnostics.append(f"OK: Сервис: {SERVICE_NAME}")
    diagnostics.append(f"OK: Адрес: {SERVICE_ADDRESS}")
    
    diagnostics.append("")
    diagnostics.append("ИТОГ ДИАГНОСТИКИ:")
    
    error_count = sum(1 for line in diagnostics if "ОШИБКА" in line)
    
    if error_count == 0:
        diagnostics.append("ВСЕ СИСТЕМЫ РАБОТАЮТ НОРМАЛЬНО!")
    else:
        diagnostics.append(f"НАЙДЕНО ПРОБЛЕМ: {error_count} ошибок")
        diagnostics.append("Исправьте отмеченные проблемы для полной работоспособности")
    
    report_text = "\n".join(diagnostics)
    send_telegram_message(chat_id, report_text)
    
    return error_count

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 50)
    logger.info("🚀 Запуск Telegram Review Analyzer Bot - Автосервис ЛИРА")
    logger.info("=" * 50)
    
    logger.info(f"📱 Сервис: {SERVICE_NAME}")
    logger.info(f"📍 Адрес: {SERVICE_ADDRESS}")
    logger.info(f"📞 Телефон: {SERVICE_PHONE}")
    logger.info(f"📱 Telegram: {SERVICE_TELEGRAM}")
    logger.info(f"🌐 Сайт: {SERVICE_WEBSITE}")
    logger.info(f"📧 Email: {SERVICE_EMAIL}")
    logger.info(f"🌐 Домен бота: {DOMAIN}")
    
    config_ok = True
    
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен! Бот не будет работать.")
        config_ok = False
    else:
        logger.info(f"🔑 Telegram токен: установлен ({len(TELEGRAM_TOKEN)} символов)")
    
    if not DEEPSEEK_API_KEY:
        logger.warning("⚠️ DEEPSEEK_API_KEY не установлен, глубокий анализ недоступен")
    else:
        logger.info(f"🤖 DeepSeek ключ: установлен")
    
    if config_ok:
        logger.info("🔄 Настраиваю вебхук...")
        webhook_success = await auto_set_webhook()
        if not webhook_success:
            logger.warning("⚠️ Вебхук не настроен автоматически")
            logger.info("💡 Используйте команду /setup_webhook в боте для ручной настройки")
    else:
        logger.error("❌ Пропускаю настройку вебхука из-за ошибок конфигурации")
    
    logger.info("=" * 50)
    logger.info("✅ Сервер готов к работе! Автосервис ЛИРА")
    logger.info("=" * 50)

# ========== FastAPI эндпоинты ==========
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "telegram-reviews-bot-deepseek",
        "service_name": SERVICE_NAME,
        "service_phone": SERVICE_PHONE,
        "service_address": SERVICE_ADDRESS,
        "timestamp": datetime.utcnow().isoformat(),
        "deepseek_available": bool(DEEPSEEK_API_KEY)
    }

@app.get("/health")
async def health_check():
    deepseek_status = test_deepseek_api()
    return {
        "status": "healthy",
        "telegram": bool(TELEGRAM_TOKEN),
        "deepseek": deepseek_status,
        "database": os.path.exists(DB_PATH),
        "webhook": DOMAIN,
        "service": {
            "name": SERVICE_NAME,
            "phone": SERVICE_PHONE,
            "address": SERVICE_ADDRESS,
            "website": SERVICE_WEBSITE
        }
    }

@app.get("/test-deepseek")
async def test_deepseek():
    return test_deepseek_api()

@app.get("/stats")
async def stats():
    stats_data = get_review_stats()
    return {
        "service": {
            "name": SERVICE_NAME,
            "phone": SERVICE_PHONE,
            "address": SERVICE_ADDRESS
        },
        "statistics": stats_data,
        "weekly_report": get_weekly_report(),
        "generated_at": datetime.utcnow().isoformat()
    }

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

    # Обработка команд
    if message_text.startswith("/start"):
        welcome = f"Бот анализа отзывов {SERVICE_NAME}\n\n"
        welcome += f"Адрес: {SERVICE_ADDRESS}\n"
        welcome += f"Телефон: {SERVICE_PHONE}\n"
        welcome += f"Сайт: {SERVICE_WEBSITE}\n\n"
        welcome += "Основные команды:\n"
        welcome += "/analyze [текст] - анализ отзыва\n"
        welcome += "/stats - статистика\n"
        welcome += "/myid - ваш ID\n"
        welcome += "/diagnostics - диагностика\n\n"
        welcome += "Просто отправьте текст отзыва для анализа!"
        
        send_telegram_message(chat_id, welcome)
        return {"ok": True}

    if message_text.startswith("/test_simple"):
        # Самый простой тест
        test_text = "Тестовое сообщение 123"
        result = send_telegram_message(chat_id, test_text)
        return {"ok": True}

    if message_text.startswith("/contacts"):
        contacts = f"Контакты Автосервиса ЛИРА\n\n"
        contacts += f"Адрес: {SERVICE_ADDRESS}\n"
        contacts += f"Телефон: {SERVICE_PHONE}\n"
        contacts += f"Telegram: {SERVICE_TELEGRAM}\n"
        contacts += f"Сайт: {SERVICE_WEBSITE}\n"
        contacts += f"Email: {SERVICE_EMAIL}\n\n"
        contacts += "Как проехать:\n"
        contacts += "От метро Автозаводская - 10 минут\n"
        contacts += "Остановка Ул. Удмуртская\n"
        contacts += "Есть собственная парковка\n\n"
        contacts += "Записывайтесь заранее!"
        
        send_telegram_message(chat_id, contacts)
        return {"ok": True}

    if message_text.startswith("/myid"):
        send_telegram_message(chat_id, f"Ваш Chat ID: {chat_id}")
        return {"ok": True}

    if message_text.startswith("/test"):
        deepseek_status = test_deepseek_api()
        if deepseek_status.get("available"):
            send_telegram_message(chat_id, f"DeepSeek API работает. Модель: {deepseek_status.get('model')}")
        else:
            send_telegram_message(chat_id, f"DeepSeek API недоступен. Ошибка: {deepseek_status.get('message')}")
        return {"ok": True}

    if message_text.startswith("/diagnostics") or message_text.startswith("/diag"):
        send_telegram_message(chat_id, "Запускаю диагностику системы...")
        error_count = await perform_diagnostics(chat_id)
        return {"ok": True}

    if message_text.startswith("/setup_webhook"):
        send_telegram_message(chat_id, "Настраиваю вебхук...")
        success = await auto_set_webhook()
        if success:
            send_telegram_message(chat_id, "Вебхук успешно настроен!")
        else:
            send_telegram_message(chat_id, "Не удалось настроить вебхук. Используйте /diagnostics для подробной диагностики")
        return {"ok": True}

    if message_text.startswith("/analyze"):
        review_text = message_text.replace("/analyze", "", 1).strip()
        if not review_text:
            send_telegram_message(chat_id, "Введите текст отзыва после команды /analyze. Например: /analyze Отличный сервис, быстро починили двигатель!")
            return {"ok": True}
        
        send_telegram_message(chat_id, "Анализирую отзыв...")
        
        analysis = analyze_review_text(review_text)
        
        save_review_to_db(chat_id, review_text, analysis)
        
        response_text = format_analysis_response(analysis, review_text)
        send_telegram_message(chat_id, response_text)
        
        logger.info(f"✅ Проанализирован отзыв: chat_id={chat_id}, рейтинг={analysis.get('rating')}")
        return {"ok": True}

    if message_text.startswith("/quick"):
        review_text = message_text.replace("/quick", "", 1).strip()
        if not review_text:
            send_telegram_message(chat_id, "Введите текст отзыва после команды /quick")
            return {"ok": True}
        
        analysis = simple_text_analysis(review_text)
        save_review_to_db(chat_id, review_text, analysis)
        
        response = f"Быстрый анализ:\n"
        response += f"Рейтинг: {analysis.get('rating')}/5\n"
        response += f"Настроение: {analysis.get('sentiment')}\n"
        response += f"Категории: {', '.join(analysis.get('categories', []))}"
        
        send_telegram_message(chat_id, response)
        return {"ok": True}

    if message_text.startswith("/stats"):
        stats_data = get_review_stats()
        response = f"Статистика отзывов {SERVICE_NAME}:\n\n"
        response += f"Всего отзывов: {stats_data['total_reviews']}\n"
        response += f"Средний рейтинг: {stats_data['average_rating']}\n"
        response += f"За неделю: {stats_data['weekly_reviews']}\n\n"
        response += "Распределение по рейтингам:\n"
        
        for dist in stats_data['rating_distribution']:
            stars = "*" * dist['rating'] + "_" * (5 - dist['rating'])
            response += f"{stars} - {dist['count']} отзывов\n"
        
        response += f"\n{SERVICE_NAME}\n{SERVICE_PHONE}"
        
        send_telegram_message(chat_id, response)
        return {"ok": True}

    # Автоматический анализ любого текста
    if len(message_text) > 10 and not message_text.startswith("/"):
        send_telegram_message(chat_id, "Анализирую ваш отзыв...")
        analysis = analyze_review_text(message_text)
        save_review_to_db(chat_id, message_text, analysis)
        response_text = format_analysis_response(analysis, message_text)
        send_telegram_message(chat_id, response_text)
        return {"ok": True}

    send_telegram_message(chat_id, f"Команда не распознана. Используйте /start для списка команд. Или отправьте текст отзыва для анализа.\n\n{SERVICE_NAME}\n{SERVICE_PHONE}")
    return {"ok": True}

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
