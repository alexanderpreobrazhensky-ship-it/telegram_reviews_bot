import os
import json
import sqlite3
import logging
from collections import Counter
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
print("🤖 БОТ АВТОСЕРВИСА «ЛИРА» - WEBHOOK ДЛЯ BOTHOST")
print("=" * 70)

# ================== КОНФИГУРАЦИЯ ==================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
SERVICE_NAME = "ЛИРА"
SERVICE_ADDRESS = "Нижний Новгород, ул. Удмуртская, 10"
SERVICE_PHONE = "+7 (XXX) XXX-XX-XX"

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не найден")
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

logger.info("✅ TELEGRAM_TOKEN найден")

# ================== FASTAPI ПРИЛОЖЕНИЕ ==================
app = FastAPI(title="Telegram Bot Webhook", version="3.0.0")

# ================== ТЕЛЕГРАМ API ФУНКЦИИ ==================
def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Отправка сообщения через Telegram Bot API"""
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"📤 Отправлено сообщение в chat_id {chat_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")
        return False

def send_keyboard(chat_id: int, text: str, buttons: List[List[dict]]) -> bool:
    """Отправка сообщения с инлайн-клавиатурой"""
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": buttons}
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки клавиатуры: {e}")
        return False

def edit_message(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Редактирование существующего сообщения"""
    try:
        url = f"{TELEGRAM_API_URL}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")
        return False

def answer_callback(callback_query_id: str, text: Optional[str] = None) -> bool:
    """Ответ на callback query"""
    try:
        url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        response = requests.post(url, json=payload, timeout=5)
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
            platform TEXT DEFAULT 'manual',
            text TEXT NOT NULL,
            user_rating INTEGER,
            detected_rating INTEGER,
            sentiment TEXT,
            categories TEXT,
            employee_mentions TEXT,
            violations TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            response_sent BOOLEAN DEFAULT FALSE,
            response_text TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

init_db()

# ================== АНАЛИЗ ОТЗЫВОВ ==================
def analyze_review(text: str) -> dict:
    """Анализ текста отзыва"""
    text_lower = text.lower()
    
    # Категории
    categories = []
    if any(w in text_lower for w in ['ремонт', 'почин', 'диагност', 'мастер', 'техник']):
        categories.append('quality')
    if any(w in text_lower for w in ['обслуживан', 'приёмк', 'администратор', 'консультац']):
        categories.append('service')
    if any(w in text_lower for w in ['время', 'ждал', 'долго', 'ожидан', 'быстро', 'скорост']):
        categories.append('time')
    if any(w in text_lower for w in ['цена', 'стоимост', 'дорог', 'дешев', 'переплат']):
        categories.append('price')
    if any(w in text_lower for w in ['чист', 'гряз', 'парковк', 'уборк', 'порядок']):
        categories.append('cleanliness')

    # Определение тональности
    negative_words = ['плох', 'ужас', 'кошмар', 'отврат', 'не рекоменд', 'разочарован', 
                     'никогда', 'отвратительн', 'ужасн', 'плохо', 'ужасно']
    positive_words = ['хорош', 'отличн', 'супер', 'рекоменд', 'спасиб', 'доволен',
                     'благодар', 'отлично', 'хорошо', 'замечательн', 'прекрасн']

    neg = sum(1 for w in negative_words if w in text_lower)
    pos = sum(1 for w in positive_words if w in text_lower)

    if neg > pos:
        detected = 1 if neg > 3 else 2
        sentiment = "negative"
    elif pos > neg:
        detected = 5 if pos > 3 else 4
        sentiment = "positive"
    else:
        detected = 3
        sentiment = "neutral"

    # Упоминания сотрудников
    employees = ['иван', 'алексей', 'сергей', 'анна', 'мария', 'ольга', 'дима', 'саня']
    mentions = [e.title() for e in employees if e in text_lower]
    
    # Нарушения
    violations = []
    offensive_words = ['урод', 'дебил', 'идиот', 'дурак', 'мудак', 'кретин']
    violations = [w for w in offensive_words if w in text_lower]

    return {
        "detected_rating": detected,
        "sentiment": sentiment,
        "categories": categories,
        "employee_mentions": mentions,
        "violations": violations,
        "suitable_for_dialogue": len(violations) == 0
    }

# ================== ОБРАБОТЧИКИ КОМАНД ==================
async def handle_start(chat_id: int):
    """Команда /start"""
    text = f"""🤖 *Бот автосервиса «{SERVICE_NAME}»*

📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

🚀 *Версия:* Чистый Webhook для Bothost

Используйте /help для списка команд"""
    send_message(chat_id, text)

async def handle_help(chat_id: int):
    """Команда /help"""
    text = """📖 *СПИСОК КОМАНД:*

/start - старт бота
/help - эта справка
/test - проверка работы
/myid - ваш Telegram ID

*Анализ отзывов:*
/analyze <текст> - анализ отзыва
/report - отчёт за неделю
/stats - общая статистика
/lastreviews [N] - последние отзывы (по умолчанию 5)

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

async def handle_test(chat_id: int):
    """Команда /test"""
    send_message(chat_id, "✅ Бот работает корректно!")

async def handle_myid(chat_id: int, user: dict):
    """Команда /myid"""
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    username = user.get('username', 'нет')
    text = f"""👤 *ВАШИ ДАННЫЕ:*

🆔 Chat ID: `{chat_id}`
👤 Имя: {name}
📛 Username: @{username}

*Использование:*
Этот ID можно добавить в переменную REPORT_CHAT_IDS в настройках Bothost для получения автоматических отчётов."""
    send_message(chat_id, text)

# ================== ОБРАБОТКА /ANALYZE ==================
async def handle_analyze(chat_id: int, command_text: str):
    """Команда /analyze"""
    # Извлекаем текст отзыва из команды
    review_text = command_text.replace("/analyze", "", 1).strip()
    
    if len(review_text) < 10:
        send_message(chat_id, "❌ Текст отзыва слишком короткий. Минимум 10 символов.")
        return
    
    send_message(chat_id, "🧠 *Анализирую отзыв...*")
    
    try:
        # Анализируем отзыв
        analysis = analyze_review(review_text)
        
        # Сохраняем в базу
        conn = sqlite3.connect('reviews.db')
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO reviews (chat_id, text, detected_rating, sentiment, categories, violations) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, review_text, analysis['detected_rating'], analysis['sentiment'],
             json.dumps(analysis['categories']), json.dumps(analysis['violations']))
        )
        review_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        # Формируем ответ
        stars = "⭐" * analysis['detected_rating'] + "☆" * (5 - analysis['detected_rating'])
        
        response = f"""{stars}
📊 *РЕЗУЛЬТАТ АНАЛИЗА*

📝 *Текст:* {review_text[:150]}...

🎯 *Оценка:* {analysis['detected_rating']}/5
🎭 *Тональность:* {analysis['sentiment']}"""
        
        if analysis['categories']:
            response += f"\n🏷 *Категории:* {', '.join(analysis['categories'])}"
        
        if analysis['violations']:
            response += f"\n🚨 *Нарушения:* {', '.join(analysis['violations'])}"
        
        response += f"\n\n💬 *Диалог возможен:* {'✅ Да' if analysis['suitable_for_dialogue'] else '❌ Нет'}"
        
        # Создаем кнопки
        buttons = []
        
        if analysis['suitable_for_dialogue'] and analysis['detected_rating'] <= 3:
            buttons.append([{"text": "📝 Сформировать ответ", "callback_data": f"response_{review_id}"}])
        
        if analysis['violations'] and analysis['detected_rating'] <= 2:
            buttons.append([{"text": "⚠️ Сформировать жалобу", "callback_data": f"complaint_{review_id}"}])
        
        if analysis['detected_rating'] >= 4:
            buttons.append([{"text": "🙏 Ответить с благодарностью", "callback_data": f"thanks_{review_id}"}])
        
        if not buttons:
            buttons.append([{"text": "📊 Показать детали", "callback_data": f"details_{review_id}"}])
        
        send_keyboard(chat_id, response, buttons)
        
    except Exception as e:
        error_msg = f"❌ Ошибка при анализе: {str(e)[:100]}"
        send_message(chat_id, error_msg)
        logger.error(f"Ошибка анализа: {e}")

# ================== ОБРАБОТКА CALLBACK КНОПОК ==================
async def handle_callback(callback_data: str, chat_id: int, message_id: int, callback_id: str):
    """Обработка нажатий на кнопки"""
    answer_callback(callback_id, "Обрабатываю...")
    
    if callback_data.startswith("response_"):
        review_id = callback_data.replace("response_", "")
        text = f"""📝 *ОТВЕТ ДЛЯ ПЛОЩАДКИ*

Благодарим за обратную связь. Для решения вопроса просим предоставить номер и дату заказ-наряда. Готовы связаться с вами для урегулирования ситуации.

С уважением, команда автосервиса «{SERVICE_NAME}»
📞 {SERVICE_PHONE}
📍 {SERVICE_ADDRESS}

👉 *Как использовать:*
1. Скопируйте текст выше
2. Вставьте в ответ на отзыв
3. Нажмите 'Опубликовать'"""
        edit_message(chat_id, message_id, text)
    
    elif callback_data.startswith("thanks_"):
        review_id = callback_data.replace("thanks_", "")
        text = f"""🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*

Рады, что остались довольны обслуживанием! 😊
Спасибо за тёплые слова в адрес наших мастеров — обязательно передадим им вашу благодарность.

Будем ждать вас снова в автосервисе «{SERVICE_NAME}»!
Всегда готовы помочь с вашим автомобилем.

С наилучшими пожеланиями,
команда автосервиса «{SERVICE_NAME}»

👉 *Как использовать:*
1. Скопируйте текст выше
2. Вставьте в ответ на отзыв
3. Нажмите 'Опубликовать'"""
        edit_message(chat_id, message_id, text)
    
    elif callback_data.startswith("complaint_"):
        review_id = callback_data.replace("complaint_", "")
        text = f"""⚠️ *ТЕКСТ ЖАЛОБЫ ДЛЯ ЯНДЕКС*

Уважаемая администрация Яндекс.Карт,

Просим рассмотреть отзыв на предмет удаления в связи с нарушением правил площадки.

Отзыв содержит оскорбительные выражения и нецензурную лексику.

Просим удалить данный отзыв как нарушающий правила сообщества.

С уважением,
{SERVICE_NAME}
{SERVICE_ADDRESS}
{datetime.now().strftime('%d.%m.%Y')}

👉 *Как использовать:*
1. Скопируйте текст выше
2. Перейдите на страницу отзыва
3. Нажмите 'Пожаловаться'
4. Вставьте текст и отправьте"""
        edit_message(chat_id, message_id, text)
    
    elif callback_data.startswith("details_"):
        review_id = callback_data.replace("details_", "")
        conn = sqlite3.connect('reviews.db')
        cur = conn.cursor()
        cur.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
        row = cur.fetchone()
        conn.close()
        
        if row:
            text = f"""🔍 *ДЕТАЛИ ОТЗЫВА*

🆔 ID: {row[0]}
👤 Chat ID: {row[1]}
📝 Текст: {row[3][:200]}...
⭐ Рейтинг: {row[5]}
🎭 Тональность: {row[6]}
🏷 Категории: {row[7] or 'нет'}
🚨 Нарушения: {row[9] or 'нет'}
📅 Создан: {row[10]}"""
        else:
            text = "❌ Отзыв не найден."
        
        edit_message(chat_id, message_id, text)

# ================== СТАТИСТИЧЕСКИЕ КОМАНДЫ ==================
async def handle_report(chat_id: int):
    """Команда /report - отчет за неделю"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    
    # Основная статистика
    cur.execute("""
        SELECT COUNT(*), AVG(detected_rating) 
        FROM reviews 
        WHERE created_at >= datetime('now', '-7 days')
    """)
    total, avg_rating = cur.fetchone()
    
    if not total or total == 0:
        send_message(chat_id, "📊 *ОТЧЁТ ЗА НЕДЕЛЮ*\n\nЗа последнюю неделю отзывов не было.")
        conn.close()
        return
    
    # Распределение по рейтингам
    cur.execute("""
        SELECT detected_rating, COUNT(*) 
        FROM reviews 
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY detected_rating 
        ORDER BY detected_rating DESC
    """)
    rating_dist = cur.fetchall()
    
    # Частые категории
    cur.execute("SELECT categories FROM reviews WHERE created_at >= datetime('now', '-7 days')")
    all_categories = []
    for row in cur.fetchall():
        if row[0]:
            try:
                cats = json.loads(row[0])
                all_categories.extend(cats)
            except:
                pass
    
    common_issues = Counter(all_categories).most_common(3)
    
    # Формируем отчет
    report = f"""📊 *ОТЧЁТ ЗА НЕДЕЛЮ*
Автосервис «{SERVICE_NAME}»
────────────────────
📈 Всего отзывов: {total}
⭐ Средний рейтинг: {avg_rating:.1f}/5

🎯 *Распределение:*"""
    
    for rating_val, count in rating_dist:
        bars = "█" * min(count, 10)
        percentage = (count / total) * 100
        report += f"\n{rating_val}★: {bars} {count} ({percentage:.0f}%)"
    
    report += f"""
    
📊 *Категории:*
• Положительные (4-5★): {sum(1 for r, _ in rating_dist if r >= 4)}
• Нейтральные (3★): {sum(1 for r, _ in rating_dist if r == 3)}
• Негативные (1-2★): {sum(1 for r, _ in rating_dist if r <= 2)}"""
    
    if common_issues:
        report += "\n\n⚠️ *Частые проблемы:*"
        for issue, count in common_issues:
            report += f"\n• {issue}: {count} раз"
    
    report += "\n────────────────────"
    
    conn.close()
    send_message(chat_id, report)

async def handle_stats(chat_id: int):
    """Команда /stats - общая статистика"""
    conn = sqlite3.connect('reviews.db')
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*), AVG(detected_rating) FROM reviews")
    total, avg_rating = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) FROM reviews WHERE detected_rating <= 2")
    negative = cur.fetchone()[0] or 0
    
    text = f"""📊 *ОБЩАЯ СТАТИСТИКА*
Автосервис «{SERVICE_NAME}»

📈 Всего отзывов: {total or 0}
⭐ Средний рейтинг: {avg_rating:.1f if avg_rating else 0}/5
⚠️ Негативных отзывов: {negative}

🚀 *Версия:* Чистый Webhook для Bothost

Используйте /analyze для анализа отзывов"""
    
    conn.close()
    send_message(chat_id, text)

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
    
    text = "📝 *Последние отзывы:*\n\n"
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
    
    counter = Counter(all_categories).most_common(5)
    conn.close()
    
    if not counter:
        send_message(chat_id, "❌ Нет данных для анализа.")
        return
    
    text = "📊 *Топ проблем по категориям:*\n\n"
    for category, count in counter:
        text += f"• {category}: {count}\n"
    
    send_message(chat_id, text)

# ================== ГЛАВНЫЙ WEBHOOK ОБРАБОТЧИК ==================
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
            
            # Определяем команду
            if text.startswith("/start"):
                await handle_start(chat_id)
            elif text.startswith("/help"):
                await handle_help(chat_id)
            elif text.startswith("/test"):
                await handle_test(chat_id)
            elif text.startswith("/myid") or text.startswith("/id"):
                await handle_myid(chat_id, user)
            elif text.startswith("/analyze"):
                await handle_analyze(chat_id, text)
            elif text.startswith("/report"):
                await handle_report(chat_id)
            elif text.startswith("/stats") or text.startswith("/statistics"):
                await handle_stats(chat_id)
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
Текст: {row[3][:200]}...
Рейтинг: {row[5]}
Тональность: {row[6]}
Категории: {row[7] or 'нет'}
Нарушения: {row[9] or 'нет'}
Создан: {row[10]}"""
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
            callback = update["callback_query"]
            callback_id = callback["id"]
            chat_id = callback["message"]["chat"]["id"]
            message_id = callback["message"]["message_id"]
            callback_data = callback.get("data", "")
            
            logger.info(f"🔘 Callback от {chat_id}: {callback_data}")
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
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "service": "telegram-bot",
        "version": "3.0.0",
        "timestamp": datetime.now().isoformat(),
        "bot": SERVICE_NAME
    })

@app.get("/")
async def root():
    """Корневой endpoint"""
    return JSONResponse({
        "message": "Telegram Bot Webhook Service",
        "service": SERVICE_NAME,
        "version": "3.0.0",
        "endpoints": {
            "webhook": "POST /api/bots/update",
            "health": "GET /api/bots/health"
        },
        "architecture": "Pure FastAPI + Telegram Bot API"
    })

# ================== ЗАПУСК ==================
@app.on_event("startup")
async def startup_event():
    """Запуск приложения"""
    logger.info("🚀 Бот запущен и готов к работе!")
    logger.info(f"✅ Webhook endpoint: POST /api/bots/update")
    logger.info(f"✅ Health check: GET /api/bots/health")

# ================== ТОЧКА ВХОДА ==================
if __name__ == "__main__":
    # Локальный запуск для тестирования
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🌍 Локальный запуск на порту {port}")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
