import os
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

print("=" * 70)
print("🤖 БОТ АВТОСЕРВИСА «ЛИРА» - ПОЛНАЯ ВЕРСИЯ")
print("=" * 70)

# ================== КОНФИГУРАЦИЯ ==================
# Получаем переменные из окружения Bothost
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
REPORT_CHAT_IDS = os.environ.get("REPORT_CHAT_IDS", "")

# Настройки автосервиса
SERVICE_NAME = "ЛИРА"
SERVICE_ADDRESS = "Нижний Новгород, ул. Удмуртская, 10"
SERVICE_PHONE = "+7 (XXX) XXX-XX-XX"

# Проверка конфигурации
if not TELEGRAM_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не найден!")
    print("Добавьте TELEGRAM_BOT_TOKEN в переменные окружения Bothost")
    exit(1)

print(f"✅ TELEGRAM_TOKEN: Найден")
print(f"✅ DEEPSEEK_API_KEY: {'Найден' if DEEPSEEK_API_KEY else 'Нет (простой анализ)'}")

# ================== БАЗА ДАННЫХ ==================
def init_database():
    """Инициализация базы данных SQLite"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    # Таблица отзывов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # Индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON reviews(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rating ON reviews(detected_rating)')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

init_database()

# Глобальный список получателей отчётов
if REPORT_CHAT_IDS:
    report_recipients = [int(cid.strip()) for cid in REPORT_CHAT_IDS.split(',') if cid.strip()]
else:
    report_recipients = []
    print("⚠️ REPORT_CHAT_IDS не указаны, отчёты отправляться не будут")

# ================== АНАЛИЗ ОТЗЫВОВ ==================
class ReviewAnalyzer:
    """Анализатор отзывов"""
    
    def __init__(self):
        self.use_deepseek = False
        self.deepseek_client = None
        
        if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.startswith("sk-"):
            try:
                from openai import OpenAI
                self.deepseek_client = OpenAI(
                    api_key=DEEPSEEK_API_KEY,
                    base_url="https://api.deepseek.com"
                )
                self.use_deepseek = True
                print("✅ DeepSeek API подключен")
            except Exception as e:
                print(f"⚠️ Ошибка DeepSeek: {e}")
        else:
            print("⚠️ DeepSeek отключен, будет использован простой анализ")
    
    def simple_analyze(self, text: str) -> dict:
        """Простой анализ по ключевым словам"""
        text_lower = text.lower()
        
        # Категории
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
        negative_words = ['плох', 'ужас', 'кошмар', 'отврат', 'не рекоменд', 'разочарован', 
                         'никогда', 'отвратительн', 'ужасн', 'плохо', 'ужасно']
        positive_words = ['хорош', 'отличн', 'супер', 'рекоменд', 'спасиб', 'доволен',
                         'благодар', 'отлично', 'хорошо', 'замечательн', 'прекрасн']
        
        neg_score = sum(1 for word in negative_words if word in text_lower)
        pos_score = sum(1 for word in positive_words if word in text_lower)
        
        # Определение рейтинга
        if neg_score > pos_score:
            detected_rating = 1 if neg_score > 3 else 2
            sentiment = "negative"
        elif pos_score > neg_score:
            detected_rating = 5 if pos_score > 3 else 4
            sentiment = "positive"
        else:
            detected_rating = 3
            sentiment = "neutral"
        
        # Упоминания сотрудников
        employees = ['иван', 'алексей', 'сергей', 'анна', 'мария', 'ольга', 'дима', 'саня']
        mentioned_employees = []
        for emp in employees:
            if emp in text_lower:
                mentioned_employees.append(emp.title())
        
        # Нарушения
        violations = []
        if any(word in text_lower for word in ['урод', 'дебил', 'идиот', 'дурак', 'мудак', 'кретин']):
            violations.append("insults")
        
        return {
            "detected_rating": detected_rating,
            "sentiment": sentiment,
            "confidence": max(pos_score, neg_score) / (pos_score + neg_score + 1),
            "categories": categories,
            "employee_mentions": mentioned_employees,
            "violations": violations,
            "key_phrases": text_lower.split()[:5],
            "analysis_method": "simple",
            "suitable_for_dialogue": len(violations) == 0
        }
    
    async def analyze_with_deepseek(self, text: str, platform: str = "manual") -> dict:
        """Анализ через DeepSeek"""
        if not self.use_deepseek or not self.deepseek_client:
            return self.simple_analyze(text)
        
        try:
            prompt = f"""Ты — аналитик отзывов для автосервиса "ЛИРА" (Нижний Новгород, ул. Удмуртская 10).

Проанализируй отзыв и верни JSON:
{{
  "detected_rating": 1-5,
  "sentiment": "very_negative/negative/neutral/positive/very_positive",
  "categories": ["quality", "service", "time", "price", "cleanliness"],
  "employee_mentions": [],
  "violations": [],
  "suitable_for_dialogue": true,
  "key_issues": [],
  "summary": "краткое резюме"
}}

Отзыв: "{text}"
"""
            
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {**result, "analysis_method": "deepseek"}
            
        except Exception as e:
            print(f"❌ Ошибка DeepSeek: {e}")
            return self.simple_analyze(text)
    
    async def analyze(self, text: str, platform: str = "manual") -> dict:
        """Основной метод анализа"""
        if self.use_deepseek:
            return await self.analyze_with_deepseek(text, platform)
        else:
            return self.simple_analyze(text)

# Создаём анализатор
analyzer = ReviewAnalyzer()

# ================== ШАБЛОНЫ ОТВЕТОВ ==================
class ResponseTemplates:
    """Шаблоны ответов и жалоб"""
    
    @staticmethod
    def get_negative_response():
        """Ответ на негативный отзыв"""
        return f"""
Благодарим за обратную связь. Для решения вопроса просим предоставить номер и дату заказ-наряда. Готовы связаться с вами для урегулирования ситуации.

С уважением, команда автосервиса «{SERVICE_NAME}»
📞 {SERVICE_PHONE}
📍 {SERVICE_ADDRESS}
"""
    
    @staticmethod
    def get_positive_response():
        """Ответ на положительный отзыв"""
        responses = [
            f"""
Рады, что остались довольны обслуживанием! 😊
Спасибо за тёплые слова в адрес наших мастеров — обязательно передадим им вашу благодарность.

Будем ждать вас снова в автосервисе «{SERVICE_NAME}»!
Всегда готовы помочь с вашим автомобилем.

С наилучшими пожеланиями,
команда автосервиса «{SERVICE_NAME}»
""",
            f"""
Большое спасибо за отличный отзыв! 🌟
Очень приятно знать, что наша работа была оценена по достоинству.

Ждём вас снова в автосервисе «{SERVICE_NAME}»!
Ваш автомобиль в надёжных руках.

С уважением,
команда автосервиса «{SERVICE_NAME}»
""",
        ]
        import random
        return random.choice(responses)
    
    @staticmethod
    def get_neutral_response():
        """Ответ на нейтральный отзыв"""
        return f"""
Спасибо за ваш отзыв! Мы ценим любое мнение о нашей работе.

Постараемся учесть ваши замечания для улучшения сервиса.

Ждём вас снова в автосервиса «{SERVICE_NAME}»!

С уважением,
команда автосервиса «{SERVICE_NAME}»
"""
    
    @staticmethod
    def get_yandex_complaint(review_text: str, violations: list):
        """Жалоба для Яндекс"""
        violations_text = "\n".join([f"{i+1}. {viol}" for i, viol in enumerate(violations)])
        
        return f"""
Уважаемая администрация Яндекс.Карт,

Просим рассмотреть отзыв на предмет удаления в связи с нарушением правил площадки.

Отзыв содержит следующие нарушения:
{violations_text}

Просим удалить данный отзыв как нарушающий правила сообщества.

С уважением,
{SERVICE_NAME}
{SERVICE_ADDRESS}
{datetime.now().strftime('%d.%m.%Y')}
"""

templates = ResponseTemplates()

# ================== КОМАНДЫ БОТА ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        f"🤖 *Бот автосервиса «{SERVICE_NAME}»*\n\n"
        f"📍 {SERVICE_ADDRESS}\n"
        f"📞 {SERVICE_PHONE}\n\n"
        "*Функционал:*\n"
        "▫️ Анализ отзывов с определением рейтинга\n"
        "▫️ Формирование ответов для площадок\n"
        "▫️ Статистика и отчёты\n\n"
        "*Команды:*\n"
        "▫️ /analyze текст - анализ отзыва\n"
        "▫️ /report - отчёт за неделю\n"
        "▫️ /stats - общая статистика\n"
        "▫️ /myid - ваш chat_id\n"
        "▫️ /addreport - подписаться на отчёты\n\n"
        "*Примеры:*\n"
        "`/analyze Отличный сервис, быстро починили!`\n"
        "`/analyze Ужасное обслуживание, не рекомендую`",
        parse_mode="Markdown"
    )

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /analyze"""
    if not context.args:
        await update.message.reply_text(
            "📝 *Использование:*\n"
            "`/analyze ваш текст отзыва`\n\n"
            "*Пример:*\n"
            "`/analyze Отличный сервис, быстро починили!`",
            parse_mode="Markdown"
        )
        return
    
    text = " ".join(context.args)
    
    if len(text) < 10:
        await update.message.reply_text("❌ Текст отзыва слишком короткий. Минимум 10 символов.")
        return
    
    await update.message.reply_text("🧠 *Анализирую отзыв...*", parse_mode="Markdown")
    
    try:
        # Анализируем отзыв
        analysis = await analyzer.analyze(text)
        rating = analysis.get("detected_rating", 3)
        sentiment = analysis.get("sentiment", "neutral")
        categories = analysis.get("categories", [])
        violations = analysis.get("violations", [])
        suitable = analysis.get("suitable_for_dialogue", True)
        
        # Сохраняем в базу
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO reviews (platform, text, detected_rating, sentiment, 
                categories, violations) VALUES (?, ?, ?, ?, ?, ?)""",
            ("manual", text, rating, sentiment, 
             json.dumps(categories), json.dumps(violations))
        )
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Формируем ответ
        stars = "⭐" * rating + "☆" * (5 - rating)
        
        response = (
            f"{stars}\n"
            f"📊 *РЕЗУЛЬТАТ АНАЛИЗА*\n\n"
            f"📝 *Текст:* {text[:150]}...\n\n"
            f"🎯 *Оценка:* {rating}/5 звезд\n"
            f"🎭 *Тональность:* {sentiment}\n"
            f"🧠 *Метод:* {analysis.get('analysis_method', 'unknown')}\n"
        )
        
        if categories:
            response += f"🏷 *Категории:* {', '.join(categories)}\n"
        
        if violations:
            response += f"🚨 *Нарушения:* {', '.join(violations)}\n"
        
        response += f"\n💬 *Диалог возможен:* {'✅ Да' if suitable else '❌ Нет'}"
        
        # Кнопки действий
        keyboard = []
        
        if suitable and rating <= 3:
            keyboard.append([InlineKeyboardButton("📝 Сформировать ответ", callback_data=f"response_{review_id}")])
        
        if violations and rating <= 2:
            keyboard.append([InlineKeyboardButton("⚠️ Сформировать жалобу", callback_data=f"complaint_{review_id}")])
        
        if rating >= 4:
            keyboard.append([InlineKeyboardButton("🙏 Ответить с благодарностью", callback_data=f"thanks_{review_id}")])
        
        if not keyboard:
            keyboard.append([InlineKeyboardButton("📊 Показать детали", callback_data=f"details_{review_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await update.message.reply_text(
            response,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при анализе: {str(e)}")
        print(f"Ошибка анализа: {e}")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /report - отчёт за неделю"""
    conn = sqlite3.connect('reviews.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Статистика за 7 дней
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            AVG(detected_rating) as avg_rating,
            SUM(CASE WHEN detected_rating >= 4 THEN 1 ELSE 0 END) as positive,
            SUM(CASE WHEN detected_rating = 3 THEN 1 ELSE 0 END) as neutral,
            SUM(CASE WHEN detected_rating <= 2 THEN 1 ELSE 0 END) as negative
        FROM reviews 
        WHERE created_at >= datetime('now', '-7 days')
    ''')
    
    stats = cursor.fetchone()
    
    if not stats or stats['total'] == 0:
        await update.message.reply_text("📊 *ОТЧЁТ*\n\nЗа последнюю неделю отзывов не было.")
        return
    
    # Распределение по рейтингам
    cursor.execute('''
        SELECT detected_rating, COUNT(*) as count
        FROM reviews 
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY detected_rating
        ORDER BY detected_rating DESC
    ''')
    
    rating_dist = cursor.fetchall()
    
    # Частые категории
    cursor.execute('''
        SELECT categories FROM reviews 
        WHERE created_at >= datetime('now', '-7 days')
    ''')
    
    all_categories = []
    for row in cursor.fetchall():
        if row['categories']:
            cats = json.loads(row['categories'])
            all_categories.extend(cats)
    
    common_issues = []
    if all_categories:
        counter = Counter(all_categories)
        common_issues = counter.most_common(3)
    
    # Формируем отчёт
    report = f"""
📊 *ОТЧЁТ ЗА НЕДЕЛЮ*
Автосервис «{SERVICE_NAME}»
────────────────────
📈 Всего отзывов: {stats['total']}
⭐ Средний рейтинг: {stats['avg_rating']:.1f}/5

🎯 Распределение:
"""
    
    for row in rating_dist:
        bars = "█" * min(row['count'], 10)
        percentage = (row['count'] / stats['total']) * 100
        report += f"{row['detected_rating']}★: {bars} {row['count']} ({percentage:.0f}%)\n"
    
    report += f"""
📊 Категории:
• Положительные (4-5★): {stats['positive']}
• Нейтральные (3★): {stats['neutral']}
• Негативные (1-2★): {stats['negative']}
"""
    
    if common_issues:
        report += "\n⚠️ Частые проблемы:\n"
        for issue, count in common_issues:
            report += f"• {issue}: {count} раз\n"
    
    report += "────────────────────"
    
    conn.close()
    await update.message.reply_text(report, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats - общая статистика"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM reviews")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(detected_rating) FROM reviews")
    avg_rating = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE detected_rating <= 2")
    negative = cursor.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 *ОБЩАЯ СТАТИСТИКА*\n"
        f"Автосервис «{SERVICE_NAME}»\n\n"
        f"📈 Всего отзывов: {total}\n"
        f"⭐ Средний рейтинг: {avg_rating:.1f}/5\n"
        f"⚠️ Негативных отзывов: {negative}\n\n"
        f"🧠 Аналитик: {'DeepSeek AI' if analyzer.use_deepseek else 'Простая система'}\n\n"
        f"Используйте /analyze для анализа отзывов",
        parse_mode="Markdown"
    )
    
    conn.close()

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /myid"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    await update.message.reply_text(
        f"👤 *Ваши данные:*\n\n"
        f"🆔 Chat ID: `{chat_id}`\n"
        f"👤 Имя: {user.first_name or ''} {user.last_name or ''}\n"
        f"📛 Username: @{user.username if user.username else 'нет'}\n\n"
        f"Этот ID можно использовать для получения отчётов.",
        parse_mode="Markdown"
    )

async def addreport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addreport - подписаться на отчёты"""
    chat_id = update.effective_chat.id
    
    if chat_id not in report_recipients:
        report_recipients.append(chat_id)
        await update.message.reply_text(
            f"✅ *Вы подписаны на отчёты!*\n\n"
            f"📊 Ваш Chat ID: `{chat_id}`\n"
            f"⏰ Отчёты будут приходить в понедельник в 8:00\n\n"
            f"Чтобы отписаться: /stopreport",
            parse_mode="Markdown"
        )
        
        # Сохраняем в базу или файл для персистентности
        try:
            with open('report_recipients.txt', 'w') as f:
                for rid in report_recipients:
                    f.write(f"{rid}\n")
        except:
            pass
    else:
        await update.message.reply_text("✅ Вы уже подписаны на отчёты")

async def stopreport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stopreport - отписаться от отчётов"""
    chat_id = update.effective_chat.id
    
    if chat_id in report_recipients:
        report_recipients.remove(chat_id)
        await update.message.reply_text("✅ Вы отписаны от получения отчётов")
        
        # Сохраняем изменения
        try:
            with open('report_recipients.txt', 'w') as f:
                for rid in report_recipients:
                    f.write(f"{rid}\n")
        except:
            pass
    else:
        await update.message.reply_text("❌ Вы не были подписаны на отчёты")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("response_"):
        # Ответ на негативный отзыв
        review_id = data.replace("response_", "")
        
        # Получаем данные отзыва из базы
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute("SELECT text, detected_rating FROM reviews WHERE id = ?", (review_id,))
        review = cursor.fetchone()
        conn.close()
        
        if review:
            text, rating = review
            response_text = templates.get_negative_response()
            
            await query.edit_message_text(
                f"📝 *ОТВЕТ ДЛЯ ПЛОЩАДКИ*\n\n"
                f"{response_text}\n\n"
                f"👉 *Как использовать:*\n"
                f"1. Скопируйте текст выше\n"
                f"2. Вставьте в ответ на отзыв\n"
                f"3. Нажмите 'Опубликовать'\n\n"
                f"📊 *Оценка отзыва:* {rating}/5",
                parse_mode="Markdown"
            )
    
    elif data.startswith("thanks_"):
        # Ответ на положительный отзыв
        review_id = data.replace("thanks_", "")
        
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute("SELECT detected_rating FROM reviews WHERE id = ?", (review_id,))
        rating = cursor.fetchone()[0]
        conn.close()
        
        response_text = templates.get_positive_response()
        
        await query.edit_message_text(
            f"🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*\n\n"
            f"{response_text}\n\n"
            f"👉 *Как использовать:*\n"
            f"1. Скопируйте текст выше\n"
            f"2. Вставьте в ответ на отзыв\n"
            f"3. Нажмите 'Опубликовать'\n\n"
            f"📊 *Оценка отзыва:* {rating}/5",
            parse_mode="Markdown"
        )
    
    elif data.startswith("complaint_"):
        # Формирование жалобы
        review_id = data.replace("complaint_", "")
        
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute("SELECT text, violations FROM reviews WHERE id = ?", (review_id,))
        review = cursor.fetchone()
        conn.close()
        
        if review:
            text, violations_json = review
            violations = json.loads(violations_json) if violations_json else []
            
            complaint_text = templates.get_yandex_complaint(text, violations)
            
            await query.edit_message_text(
                f"⚠️ *ТЕКСТ ЖАЛОБЫ ДЛЯ ЯНДЕКС*\n\n"
                f"{complaint_text}\n\n"
                f"👉 *Как использовать:*\n"
                f"1. Скопируйте текст выше\n"
                f"2. Перейдите на страницу отзыва\n"
                f"3. Нажмите 'Пожаловаться'\n"
                f"4. Вставьте текст и отправьте",
                parse_mode="Markdown"
            )
    
    elif data.startswith("details_"):
        # Показать детали
        review_id = data.replace("details_", "")
        
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
        review = cursor.fetchone()
        conn.close()
        
        if review:
            details = f"ID: {review[0]}\nТекст: {review[2][:200]}...\nОценка: {review[4]}\n"
            await query.edit_message_text(
                f"🔍 *ДЕТАЛИ ОТЗЫВА*\n\n{details}",
                parse_mode="Markdown"
            )

async def send_weekly_report():
    """Отправка еженедельного отчёта (упрощённая версия)"""
    print("📅 Проверка необходимости отправки отчёта...")
    
    # В упрощённой версии просто логируем
    print(f"👥 Получателей отчётов: {len(report_recipients)}")
    
    # Можно добавить реальную отправку позже
    return

# ================== ЗАПУСК БОТА ==================
def main():
    """Основная функция запуска"""
    print("🔄 Создаю приложение Telegram...")
    
    try:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        # Регистрация команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("analyze", analyze_command))
        app.add_handler(CommandHandler("report", report_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("statistics", stats_command))
        app.add_handler(CommandHandler("myid", myid_command))
        app.add_handler(CommandHandler("id", myid_command))
        app.add_handler(CommandHandler("addreport", addreport_command))
        app.add_handler(CommandHandler("stopreport", stopreport_command))
        
        # Обработчик кнопок
        app.add_handler(CallbackQueryHandler(button_handler))
        
        print("✅ Бот настроен")
        print("🚀 Запускаю polling...")
        print("=" * 70)
        
        # Упрощённый планировщик отчётов (без APScheduler)
        async def check_reports():
            """Проверка необходимости отправки отчётов"""
            while True:
                now = datetime.now()
                # Проверяем понедельник 8:00
                if now.weekday() == 0 and now.hour == 8 and now.minute == 0:
                    await send_weekly_report()
                await asyncio.sleep(60)  # Проверяем каждую минуту
        
        # Запускаем в фоне
        asyncio.create_task(check_reports())
        
        # Запускаем бота
        app.run_polling(
            drop_pending_updates=True,
            timeout=30,
            pool_timeout=30
        )
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        
        # Держим процесс активным для просмотра ошибки
        print("⏳ Ожидание 300 секунд перед завершением...")
        import time
        time.sleep(300)

if __name__ == "__main__":
    main()
