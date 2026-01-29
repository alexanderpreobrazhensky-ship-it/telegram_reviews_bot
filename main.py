import os
import json
import sqlite3
import logging
import re
from datetime import datetime
from typing import List, Optional
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("=" * 70)
print("🤖 БОТ АВТОСЕРВИСА «ЛИРА» - FINAL WEBHOOK FOR BOTHOST")
print("=" * 70)

# ================== КОНФИГУРАЦИЯ ==================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
DEEPSEEK_API_URL = "https://api.deepseek.com"

SERVICE_NAME = "ЛИРА"
SERVICE_ADDRESS = "Нижний Новгород, ул. Удмуртская, 10"
SERVICE_PHONE = "+7 (XXX) XXX-XX-XX"

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не найден")
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

logger.info("✅ Telegram токен найден")
logger.info(f"🤖 DeepSeek: {'доступен' if DEEPSEEK_API_KEY else 'отключен'}")

# ================== FASTAPI ПРИЛОЖЕНИЕ ==================
app = FastAPI(title="Telegram Bot Webhook", version="5.0.0")

# ================== ТЕЛЕГРАМ API ФУНКЦИИ ==================
def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Отправка сообщения через Telegram Bot API"""
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            },
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"📤 Отправлено сообщение в chat_id {chat_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        return False

def send_keyboard(chat_id: int, text: str, buttons: List[List[dict]]) -> bool:
    """Отправка сообщения с инлайн-клавиатурой"""
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": {"inline_keyboard": buttons}
            },
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки клавиатуры: {e}")
        return False

def edit_message(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Редактирование существующего сообщения"""
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode
            },
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")
        return False

def answer_callback(callback_query_id: str, text: Optional[str] = None) -> bool:
    """Ответ на callback query"""
    try:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        
        response = requests.post(
            f"{TELEGRAM_API_URL}/answerCallbackQuery",
            json=payload,
            timeout=5
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка ответа на callback: {e}")
        return False

# ================== БАЗА ДАННЫХ SQLite ==================
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            text TEXT NOT NULL,
            detected_rating INTEGER,
            sentiment TEXT,
            categories TEXT,
            employee_mentions TEXT,
            violations TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_db()

# ================== ПРОСТОЙ АНАЛИЗ (FALLBACK) ==================
def simple_analyze(text: str) -> dict:
    """Простой анализ на основе ключевых слов (fallback)"""
    text_lower = text.lower()
    
    # Определение категорий
    categories = []
    if any(word in text_lower for word in ['ремонт', 'почин', 'диагност', 'мастер', 'техник']):
        categories.append('quality')
    if any(word in text_lower for word in ['обслуживан', 'приёмк', 'администратор', 'консультац']):
        categories.append('service')
    if any(word in text_lower for word in ['время', 'ждал', 'долго', 'ожидан', 'быстро', 'скорост']):
        categories.append('time')
    if any(word in text_lower for word in ['цена', 'стоимост', 'дорог', 'дешев', 'переплат']):
        categories.append('price')
    if any(word in text_lower for word in ['чист', 'гряз', 'парковк', 'уборк', 'порядок']):
        categories.append('cleanliness')
    
    # Определение тональности
    negative_words = ['плох', 'ужас', 'кошмар', 'отврат', 'не рекоменд', 'разочарован']
    positive_words = ['хорош', 'отличн', 'супер', 'рекоменд', 'спасиб', 'доволен']
    
    neg_score = sum(1 for word in negative_words if word in text_lower)
    pos_score = sum(1 for word in positive_words if word in text_lower)
    
    if neg_score > pos_score:
        detected_rating = 1 if neg_score > 3 else 2
        sentiment = "negative"
    elif pos_score > neg_score:
        detected_rating = 5 if pos_score > 3 else 4
        sentiment = "positive"
    else:
        detected_rating = 3
        sentiment = "neutral"
    
    # Определение нарушений
    violations = []
    offensive_words = ['урод', 'дебил', 'идиот', 'дурак', 'мудак', 'кретин']
    if any(word in text_lower for word in offensive_words):
        violations.append("insults")
    
    # Упоминания сотрудников
    employees = ['иван', 'алексей', 'сергей', 'анна', 'мария', 'ольга', 'дима', 'саня']
    mentioned = [emp.title() for emp in employees if emp in text_lower]
    
    return {
        "detected_rating": detected_rating,
        "sentiment": sentiment,
        "categories": categories,
        "employee_mentions": mentioned,
        "violations": violations,
        "suitable_for_dialogue": len(violations) == 0,
        "analysis_method": "simple"
    }

# ================== DEEPSEEK АНАЛИЗ ==================
def deepseek_analyze(text: str) -> dict:
    """Анализ отзыва через DeepSeek API"""
    
    # Если нет API ключа, используем простой анализ
    if not DEEPSEEK_API_KEY:
        logger.info("⚠️ DeepSeek API ключ не указан, использую простой анализ")
        return simple_analyze(text)
    
    try:
        prompt = f"""Ты — аналитик отзывов для автосервиса "{SERVICE_NAME}" ({SERVICE_ADDRESS}).

Проанализируй отзыв и верни JSON в следующем формате:
{{
    "detected_rating": 1-5,
    "sentiment": "very_negative/negative/neutral/positive/very_positive",
    "categories": ["quality", "service", "time", "price", "cleanliness"],
    "employee_mentions": [],
    "violations": [],
    "suitable_for_dialogue": true,
    "key_issues": [],
    "summary": "краткое резюме на русском"
}}

Отзыв: "{text[:1000]}"
"""
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "Ты аналитик отзывов. Всегда отвечай валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        response = requests.post(
            f"{DEEPSEEK_API_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Извлекаем JSON из ответа
        content = result["choices"][0]["message"]["content"]
        
        # Парсим JSON
        try:
            analysis = json.loads(content)
        except json.JSONDecodeError:
            # Если не JSON, пытаемся извлечь JSON из текста
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                logger.warning("⚠️ DeepSeek не вернул JSON, использую простой анализ")
                return simple_analyze(text)
        
        # Добавляем метаданные
        analysis["analysis_method"] = "deepseek"
        
        logger.info(f"✅ DeepSeek анализ выполнен: {analysis.get('sentiment')}, рейтинг {analysis.get('detected_rating')}")
        return analysis
        
    except Exception as e:
        logger.error(f"❌ Ошибка DeepSeek API: {e}")
        logger.info("🔄 Использую простой анализ как fallback")
        return simple_analyze(text)

# ================== ОБРАБОТЧИКИ КОМАНД ==================
async def handle_start(chat_id: int):
    """Команда /start"""
    text = f"""🤖 *Бот автосервиса «{SERVICE_NAME}»*

📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

🚀 *Версия:* Webhook для Bothost
🤖 *Анализ:* {'DeepSeek AI' if DEEPSEEK_API_KEY else 'Простая система'}

*Основные команды:*
/help - список всех команд
/analyze <текст> - анализ отзыва
/stats - статистика
/report - отчёт за неделю
/myid - ваш Telegram ID

*Пример:*
/analyze Отличный сервис, быстро починили!"""
    send_message(chat_id, text)

async def handle_help(chat_id: int):
    """Команда /help"""
    text = """📖 *ПОЛНЫЙ СПИСОК КОМАНД:*

*Основные:*
/start - информация о боте
/help - эта справка
/myid - ваш Telegram ID
/test - проверка работы бота

*Анализ отзывов:*
/analyze <текст> - анализ отзыва
/stats - общая статистика
/report - отчёт за неделю
/report_now - мгновенный отчёт
/lastreviews [N] - последние отзывы

*Управление отзывами:*
/categories - все категории
/violations - отзывы с нарушениями
/topissues - частые проблемы
/details <ID> - детали отзыва
/thanks <ID> - ответ с благодарностью
/complaint <ID> - жалоба на отзыв

*Настройки:*
/addreport - подписка на отчёты
/stopreport - отписка от отчётов"""
    send_message(chat_id, text)

async def handle_myid(chat_id: int, user: dict):
    """Команда /myid"""
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    username = user.get("username", "нет")
    
    text = f"""👤 *ВАШИ ДАННЫЕ:*

🆔 Chat ID: `{chat_id}`
👤 Имя: {name}
📛 Username: @{username}

*Использование:*
Этот ID можно добавить в переменную REPORT_CHAT_IDS в настройках Bothost для получения автоматических отчётов."""
    
    send_message(chat_id, text)

async def handle_analyze(chat_id: int, command_text: str):
    """Команда /analyze"""
    # Извлекаем текст отзыва
    review_text = command_text.replace("/analyze", "", 1).strip()
    
    if len(review_text) < 10:
        send_message(chat_id, "❌ Текст отзыва слишком короткий. Минимум 10 символов.")
        return
    
    send_message(chat_id, "🧠 *Анализирую отзыв...*")
    
    try:
        # Выбираем метод анализа
        if DEEPSEEK_API_KEY:
            analysis = deepseek_analyze(review_text)
        else:
            analysis = simple_analyze(review_text)
        
        # Сохраняем в базу
        conn = sqlite3.connect('reviews.db')
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO reviews (chat_id, text, detected_rating, sentiment, categories, violations) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, review_text, analysis.get("detected_rating", 3), 
             analysis.get("sentiment", "neutral"),
             json.dumps(analysis.get("categories", [])), 
             json.dumps(analysis.get("violations", [])))
        )
        review_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        # Формируем ответ
        stars = "⭐" * analysis.get("detected_rating", 3) + "☆" * (5 - analysis.get("detected_rating", 3))
        
        response = f"""{stars}
📊 *РЕЗУЛЬТАТ АНАЛИЗА*

📝 *Текст:* {review_text[:150]}...

🎯 *Оценка:* {analysis.get('detected_rating', 3)}/5
🎭 *Тональность:* {analysis.get('sentiment', 'neutral')}
🧠 *Метод:* {analysis.get('analysis_method', 'simple')}"""
        
        if analysis.get("categories"):
            response += f"\n🏷 *Категории:* {', '.join(analysis['categories'])}"
        
        if analysis.get("violations"):
            response += f"\n🚨 *Нарушения:* {', '.join(analysis['violations'])}"
        
        if analysis.get("summary"):
            response += f"\n📋 *Резюме:* {analysis['summary'][:100]}..."
        
        response += f"\n\n💬 *Диалог возможен:* {'✅ Да' if analysis.get('suitable_for_dialogue', True) else '❌ Нет'}"
        
        # Создаем кнопки
        buttons = []
        
        if analysis.get("suitable_for_dialogue", True) and analysis.get("detected_rating", 3) <= 3:
            buttons.append([{"text": "📝 Сформировать ответ", "callback_data": f"response_{review_id}"}])
        
        if analysis.get("violations") and analysis.get("detected_rating", 3) <= 2:
            buttons.append([{"text": "⚠️ Сформировать жалобу", "callback_data": f"complaint_{review_id}"}])
        
        if analysis.get("detected_rating", 3) >= 4:
            buttons.append([{"text": "🙏 Ответить с благодарностью", "callback_data": f"thanks_{review_id}"}])
        
        if not buttons:
            buttons.append([{"text": "📊 Показать детали", "callback_data": f"details_{review_id}"}])
        
        send_keyboard(chat_id, response, buttons)
        
    except Exception as e:
        error_msg = f"❌ Ошибка при анализе: {str(e)[:100]}"
        send_message(chat_id, error_msg)
        logger.error(f"Ошибка анализа: {e}")

async def handle_stats(chat_id: int):
    """Команда /stats"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*), AVG(detected_rating) FROM reviews")
    total, avg_rating = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) FROM reviews WHERE detected_rating <= 2")
    negative = cur.fetchone()[0] or 0
    
    conn.close()
    
    text = f"""📊 *ОБЩАЯ СТАТИСТИКА*
Автосервис «{SERVICE_NAME}»

📈 Всего отзывов: {total or 0}
⭐ Средний рейтинг: {avg_rating:.1f if avg_rating else 0}/5
⚠️ Негативных отзывов: {negative}

🤖 *Аналитик:* {'DeepSeek AI' if DEEPSEEK_API_KEY else 'Простая система'}

Используйте /analyze для анализа новых отзывов"""
    
    send_message(chat_id, text)

async def handle_report(chat_id: int, instant: bool = False):
    """Команда /report"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    
    if instant:
        cur.execute("SELECT text, detected_rating FROM reviews ORDER BY created_at DESC LIMIT 10")
        title = "📊 *МГНОВЕННЫЙ ОТЧЕТ*"
    else:
        cur.execute("SELECT text, detected_rating FROM reviews WHERE created_at >= datetime('now','-7 days')")
        title = "📊 *НЕДЕЛЬНЫЙ ОТЧЕТ*"
    
    reviews = cur.fetchall()
    conn.close()
    
    if not reviews:
        send_message(chat_id, f"{title}\n\nНет отзывов для отчета")
        return
    
    # Простая статистика
    total = len(reviews)
    avg_rating = sum(r for _, r in reviews) / total if reviews else 0
    
    # Распределение по рейтингам
    rating_counts = {}
    for _, rating in reviews:
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
    
    # Формируем отчет
    report = f"""{title}
Автосервис «{SERVICE_NAME}»
────────────────────
📈 Всего отзывов: {total}
⭐ Средний рейтинг: {avg_rating:.1f}/5

🎯 *Распределение рейтингов:*"""
    
    for rating in sorted(rating_counts.keys(), reverse=True):
        count = rating_counts[rating]
        bars = "█" * min(count, 10)
        percentage = (count / total) * 100
        report += f"\n{rating}★: {bars} {count} ({percentage:.0f}%)"
    
    report += "\n────────────────────"
    
    # Если есть DeepSeek, добавляем AI-анализ
    if DEEPSEEK_API_KEY and len(reviews) > 0:
        send_message(chat_id, f"{title}\n\n🧠 *Анализирую отзывы через DeepSeek...*")
        
        # Создаем сводку для анализа
        summary_text = "\n".join([f"{rating}★: {text[:100]}" for text, rating in reviews])
        analysis = deepseek_analyze(f"Сводка отзывов:\n{summary_text}")
        
        if analysis.get("categories"):
            report += f"\n\n🏷 *Основные темы:* {', '.join(analysis['categories'])}"
        
        if analysis.get("key_issues"):
            report += "\n\n⚠️ *Ключевые проблемы:*"
            for issue in analysis["key_issues"][:3]:
                report += f"\n• {issue}"
        
        if analysis.get("summary"):
            report += f"\n\n📋 *Выводы:* {analysis['summary']}"
    
    send_message(chat_id, report)

async def handle_lastreviews(chat_id: int, n: int = 5):
    """Команда /lastreviews"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    cur.execute("SELECT id, text, detected_rating FROM reviews ORDER BY created_at DESC LIMIT ?", (n,))
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        send_message(chat_id, "❌ Отзывов не найдено.")
        return
    
    text = f"📝 *Последние {len(rows)} отзывов:*\n\n"
    for i, (review_id, review_text, rating) in enumerate(rows, 1):
        text += f"{i}. ID:{review_id} {review_text[:50]}... ({rating}★)\n"
    
    send_message(chat_id, text)

async def handle_categories(chat_id: int):
    """Команда /categories"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    cur.execute("SELECT categories FROM reviews")
    
    all_categories = []
    for row in cur.fetchall():
        if row[0]:
            try:
                cats = json.loads(row[0])
                all_categories.extend(cats)
            except:
                pass
    
    # Подсчитываем категории
    from collections import Counter
    counter = Counter(all_categories).most_common()
    conn.close()
    
    if not counter:
        send_message(chat_id, "❌ Категории не найдены.")
        return
    
    text = "🏷 *Категории отзывов:*\n\n"
    for category, count in counter:
        text += f"• {category}: {count}\n"
    
    send_message(chat_id, text)

async def handle_violations(chat_id: int):
    """Команда /violations"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    cur.execute("SELECT id, text, violations FROM reviews WHERE violations IS NOT NULL AND violations != '[]'")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        send_message(chat_id, "✅ Отзывов с нарушениями не найдено.")
        return
    
    text = "⚠️ *Отзывы с нарушениями:*\n\n"
    for review_id, review_text, violations in rows:
        text += f"ID:{review_id} {review_text[:50]}...\nНарушения: {violations}\n\n"
    
    send_message(chat_id, text)

async def handle_topissues(chat_id: int):
    """Команда /topissues"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    cur.execute("SELECT categories FROM reviews")
    
    all_categories = []
    for row in cur.fetchall():
        if row[0]:
            try:
                cats = json.loads(row[0])
                all_categories.extend(cats)
            except:
                pass
    
    from collections import Counter
    counter = Counter(all_categories).most_common(5)
    conn.close()
    
    if not counter:
        send_message(chat_id, "❌ Нет данных для анализа.")
        return
    
    text = "📊 *Топ проблем по категориям:*\n\n"
    for category, count in counter:
        text += f"• {category}: {count}\n"
    
    send_message(chat_id, text)

# ================== ОБРАБОТКА CALLBACK КНОПОК ==================
async def handle_callback(callback_data: str, chat_id: int, message_id: int, callback_id: str):
    """Обработка нажатий на кнопки"""
    answer_callback(callback_id, "Обрабатываю...")
    
    if "_" not in callback_data:
        edit_message(chat_id, message_id, "❌ Неверный формат callback данных")
        return
    
    action, review_id_str = callback_data.split("_", 1)
    
    try:
        review_id = int(review_id_str)
    except ValueError:
        edit_message(chat_id, message_id, "❌ Неверный ID отзыва")
        return
    
    # Получаем данные отзыва
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    cur.execute("SELECT text, detected_rating FROM reviews WHERE id = ?", (review_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        edit_message(chat_id, message_id, "❌ Отзыв не найден")
        return
    
    text_orig, rating = row
    
    if action == "response":
        resp = f"""📝 *ОТВЕТ ДЛЯ КЛИЕНТА*

Благодарим за обратную связь. Для решения вопроса просим предоставить номер и дату заказ-наряда. Готовы связаться с вами для урегулирования ситуации.

С уважением, команда автосервиса «{SERVICE_NAME}»
📞 {SERVICE_PHONE}
📍 {SERVICE_ADDRESS}

*Оценка отзыва:* {rating}/5"""
        edit_message(chat_id, message_id, resp)
    
    elif action == "thanks":
        resp = f"""🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*

Спасибо за тёплые слова! Рады, что остались довольны обслуживанием.

Обязательно передадим вашу благодарность нашим мастерам.

Ждём вас снова в автосервисе «{SERVICE_NAME}»!

*Оценка отзыва:* {rating}/5"""
        edit_message(chat_id, message_id, resp)
    
    elif action == "complaint":
        resp = f"""⚠️ *ТЕКСТ ЖАЛОБЫ*

Уважаемая администрация,

Просим рассмотреть отзыв на предмет удаления в связи с нарушением правил площадки.

Отзыв содержит нарушения и не соответствует стандартам сообщества.

С уважением,
{SERVICE_NAME}
{SERVICE_ADDRESS}
{datetime.now().strftime('%d.%m.%Y')}

*Оценка отзыва:* {rating}/5"""
        edit_message(chat_id, message_id, resp)
    
    elif action == "details":
        edit_message(chat_id, message_id, f"🔍 *ДЕТАЛИ ОТЗЫВА*\n\nID: {review_id}\nРейтинг: {rating}/5\n\nТекст: {text_orig[:300]}...")

# ================== WEBHOOK ОБРАБОТЧИК ==================
@app.post("/api/bots/update")
async def webhook_handler(request: Request):
    """Основной endpoint для получения обновлений от Telegram"""
    try:
        update = await request.json()
        logger.info(f"📥 Получен update: {update.get('update_id')}")
        
        # Обработка текстового сообщения
        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()
            user = msg.get("from", {})
            
            logger.info(f"💬 Сообщение от {chat_id}: {text[:50]}...")
            
            if text.startswith("/start"):
                await handle_start(chat_id)
            elif text.startswith("/help"):
                await handle_help(chat_id)
            elif text.startswith("/test"):
                send_message(chat_id, "✅ Бот работает корректно!")
            elif text.startswith("/myid") or text.startswith("/id"):
                await handle_myid(chat_id, user)
            elif text.startswith("/analyze"):
                await handle_analyze(chat_id, text)
            elif text.startswith("/stats") or text.startswith("/statistics"):
                await handle_stats(chat_id)
            elif text.startswith("/report_now"):
                await handle_report(chat_id, instant=True)
            elif text.startswith("/report"):
                await handle_report(chat_id)
            elif text.startswith("/lastreviews"):
                parts = text.split()
                n = 5
                if len(parts) > 1:
                    try:
                        n = int(parts[1])
                        if n > 20:
                            n = 20
                    except:
                        pass
                await handle_lastreviews(chat_id, n)
            elif text.startswith("/categories"):
                await handle_categories(chat_id)
            elif text.startswith("/violations"):
                await handle_violations(chat_id)
            elif text.startswith("/topissues"):
                await handle_topissues(chat_id)
            elif text.startswith("/addreport"):
                send_message(chat_id, f"✅ Для подписки на отчёты добавьте ID `{chat_id}` в переменную REPORT_CHAT_IDS в Bothost.")
            elif text.startswith("/stopreport"):
                send_message(chat_id, "✅ Для отписки удалите ваш ID из переменной REPORT_CHAT_IDS в Bothost.")
            elif text.startswith("/thanks"):
                parts = text.split()
                if len(parts) > 1:
                    try:
                        review_id = int(parts[1])
                        send_message(chat_id, f"✅ Ответ с благодарностью для отзыва ID {review_id} сформирован.\n\nСпасибо за отзыв! Команда {SERVICE_NAME}")
                    except:
                        send_message(chat_id, "❌ Используйте: /thanks <ID_отзыва>")
                else:
                    send_message(chat_id, "❌ Используйте: /thanks <ID_отзыва>")
            elif text.startswith("/complaint"):
                parts = text.split()
                if len(parts) > 1:
                    try:
                        review_id = int(parts[1])
                        send_message(chat_id, f"⚠️ Жалоба на отзыв ID {review_id} сформирована.\n\nУважаемая администрация, просим удалить отзыв за нарушения.")
                    except:
                        send_message(chat_id, "❌ Используйте: /complaint <ID_отзыва>")
                else:
                    send_message(chat_id, "❌ Используйте: /complaint <ID_отзыва>")
            elif text.startswith("/details"):
                parts = text.split()
                if len(parts) > 1:
                    try:
                        review_id = int(parts[1])
                        conn = sqlite3.connect('reviews.db')
                        cur = conn.cursor()
                        cur.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
                        row = cur.fetchone()
                        conn.close()
                        if row:
                            details = f"""🔍 *ДЕТАЛИ ОТЗЫВА*

ID: {row[0]}
Текст: {row[2][:200]}...
Рейтинг: {row[3]}
Тональность: {row[4]}
Категории: {row[5] or 'нет'}
Нарушения: {row[7] or 'нет'}
Создан: {row[8]}"""
                        else:
                            details = "❌ Отзыв не найден."
                        send_message(chat_id, details)
                    except:
                        send_message(chat_id, "❌ Используйте: /details <ID_отзыва>")
                else:
                    send_message(chat_id, "❌ Используйте: /details <ID_отзыва>")
            elif text.startswith("/"):
                send_message(chat_id, "❌ Неизвестная команда. Используйте /help для списка команд.")
            else:
                send_message(chat_id, f"📝 Для анализа отзыва используйте команду:\n`/analyze {text[:100]}`")
        
        # Обработка callback query (нажатие кнопки)
        elif "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            message_id = cb["message"]["message_id"]
            callback_data = cb.get("data", "")
            callback_id = cb["id"]
            await handle_callback(callback_data, chat_id, message_id, callback_id)
        
        return JSONResponse({"status": "ok"}, status_code=200)
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )

# ================== HEALTH CHECK ==================
@app.get("/api/bots/health")
async def health_check():
    """Health check endpoint для мониторинга"""
    return JSONResponse({
        "status": "healthy",
        "service": "telegram-bot",
        "version": "5.0.0",
        "timestamp": datetime.now().isoformat(),
        "bot": SERVICE_NAME,
        "deepseek_available": bool(DEEPSEEK_API_KEY)
    })

@app.get("/")
async def root():
    """Корневой endpoint"""
    return JSONResponse({
        "message": "Telegram Bot Webhook Service",
        "service": SERVICE_NAME,
        "version": "5.0.0",
        "endpoints": {
            "webhook": "POST /api/bots/update",
            "health": "GET /api/bots/health"
        },
        "ai_provider": "DeepSeek" if DEEPSEEK_API_KEY else "Simple Analysis"
    })

# ================== ЗАПУСК ==================
@app.on_event("startup")
async def startup_event():
    """Запуск приложения"""
    logger.info("🚀 Бот запущен и готов к работе!")
    logger.info(f"✅ Webhook endpoint: POST /api/bots/update")
    logger.info(f"✅ Health check: GET /api/bots/health")
    logger.info(f"🤖 AI: {'DeepSeek' if DEEPSEEK_API_KEY else 'Simple Analysis'}")
    logger.info(f"🏢 Автосервис: {SERVICE_NAME}")

# ================== ТОЧКА ВХОДА ДЛЯ UVICORN ==================
if __name__ == "__main__":
    # Локальный запуск для тестирования
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🌍 Локальный запуск на порту {port}")
    uvicorn.run(
        "main:app",
        host="0
