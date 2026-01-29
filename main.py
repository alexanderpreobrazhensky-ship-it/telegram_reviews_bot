import os
import json
import sqlite3
from datetime import datetime, timedelta
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

print("=" * 60)
print("🤖 БОТ ДЛЯ АНАЛИЗА ОТЗЫВОВ АВТОСЕРВИСА «ЛИРА»")
print("=" * 60)

# ================== КОНФИГУРАЦИЯ ==================
# Получаем переменные из Bothost
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
REPORT_CHAT_IDS = os.environ.get("REPORT_CHAT_IDS", "")

# Настройки автосервиса
SERVICE_NAME = "ЛИРА"
SERVICE_ADDRESS = "Нижний Новгород, ул. Удмуртская, 10"
SERVICE_PHONE = "+7 (XXX) XXX-XX-XX"

# Проверка конфигурации
if not TELEGRAM_TOKEN:
    print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден в переменных окружения Bothost!")
    print("Добавьте TELEGRAM_BOT_TOKEN в Bothost при создании бота")
    exit(1)

print(f"✅ TELEGRAM_TOKEN: {'Найден' if TELEGRAM_TOKEN else 'НЕ найден'}")
print(f"✅ DEEPSEEK_API_KEY: {'Найден' if DEEPSEEK_API_KEY else 'НЕ найден (будет простой анализ)'}")

# ================== БАЗА ДАННЫХ ==================
def init_database():
    """Инициализация SQLite базы данных"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    # Таблица отзывов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            text TEXT NOT NULL,
            detected_rating INTEGER,
            categories TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# Инициализируем БД при запуске
init_database()

# Глобальный список получателей отчётов (для динамического добавления)
if REPORT_CHAT_IDS:
    report_recipients = [int(cid.strip()) for cid in REPORT_CHAT_IDS.split(',') if cid.strip()]
else:
    report_recipients = []

# ================== АНАЛИЗ ОТЗЫВОВ ==================
class ReviewAnalyzer:
    def __init__(self):
        self.use_deepseek = False
        
        if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.startswith("sk-"):
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=DEEPSEEK_API_KEY,
                    base_url="https://api.deepseek.com"
                )
                self.use_deepseek = True
                print("✅ DeepSeek API подключен")
            except:
                print("⚠️ DeepSeek не подключен, будет простой анализ")
    
    def simple_analyze(self, text: str) -> dict:
        """Простой анализ по ключевым словам"""
        text_lower = text.lower()
        
        # Ключевые слова для категорий
        categories = []
        if any(word in text_lower for word in ['ремонт', 'почин', 'диагност', 'мастер']):
            categories.append('quality')
        if any(word in text_lower for word in ['обслуживан', 'приёмк', 'администратор']):
            categories.append('service')
        if any(word in text_lower for word in ['время', 'ждал', 'долго', 'ожидан']):
            categories.append('time')
        if any(word in text_lower for word in ['цена', 'дорог', 'стоимост']):
            categories.append('price')
        if any(word in text_lower for word in ['чист', 'гряз', 'парковк']):
            categories.append('cleanliness')
        
        # Определение рейтинга
        negative = ['плох', 'ужас', 'кошмар', 'отврат', 'не рекоменд', 'разочарован']
        positive = ['хорош', 'отличн', 'супер', 'рекоменд', 'спасиб', 'доволен']
        
        neg_count = sum(1 for word in negative if word in text_lower)
        pos_count = sum(1 for word in positive if word in text_lower)
        
        if neg_count > pos_count:
            rating = 1 if neg_count > 3 else 2
            sentiment = "negative"
        elif pos_count > neg_count:
            rating = 5 if pos_count > 3 else 4
            sentiment = "positive"
        else:
            rating = 3
            sentiment = "neutral"
        
        return {
            "detected_rating": rating,
            "sentiment": sentiment,
            "categories": categories,
            "analysis_method": "simple"
        }
    
    async def analyze_with_deepseek(self, text: str) -> dict:
        """Анализ через DeepSeek"""
        try:
            prompt = f"""Проанализируй отзыв для автосервиса и верни JSON:
{{
    "detected_rating": 1-5,
    "sentiment": "very_negative/negative/neutral/positive/very_positive",
    "categories": ["service", "quality", "time", "price", "cleanliness"],
    "key_issues": ["список проблем"],
    "summary": "краткое резюме"
}}

Отзыв: "{text}"
"""
            
            response = self.client.chat.completions.create(
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
    
    async def analyze(self, text: str) -> dict:
        """Основной метод анализа"""
        if self.use_deepseek:
            return await self.analyze_with_deepseek(text)
        return self.simple_analyze(text)

# Создаём анализатор
analyzer = ReviewAnalyzer()

# ================== КОМАНДЫ БОТА ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        f"🤖 *Бот автосервиса «{SERVICE_NAME}»*\n\n"
        f"📍 {SERVICE_ADDRESS}\n"
        f"📞 {SERVICE_PHONE}\n\n"
        "*Команды:*\n"
        "▫️ /analyze текст отзыва - анализ отзыва\n"
        "▫️ /report - отчёт за неделю\n"
        "▫️ /stats - текущая статистика\n"
        "▫️ /test - тестовый режим\n"
        "▫️ /myid - узнать ваш chat_id\n"
        "▫️ /addreport - получать отчёты\n\n"
        "*Пример:*\n"
        "`/analyze Отличный сервис, быстро починили!`",
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
    
    await update.message.reply_text("🧠 *Анализирую...*", parse_mode="Markdown")
    
    try:
        # Анализ
        analysis = await analyzer.analyze(text)
        rating = analysis['detected_rating']
        
        # Сохраняем в БД
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reviews (platform, text, detected_rating, categories) VALUES (?, ?, ?, ?)",
            ("manual", text, rating, json.dumps(analysis.get('categories', [])))
        )
        conn.commit()
        conn.close()
        
        # Формируем ответ
        emoji = "⭐️" * rating
        categories_text = ", ".join(analysis.get('categories', [])) if analysis.get('categories') else "не определены"
        
        response = (
            f"{emoji} *РЕЗУЛЬТАТ АНАЛИЗА*\n\n"
            f"📝 *Текст:* {text[:100]}...\n\n"
            f"📊 *Оценка:* {rating}/5 звезд\n"
            f"🎭 *Тональность:* {analysis.get('sentiment', 'neutral')}\n"
            f"🏷 *Категории:* {categories_text}\n"
            f"🧠 *Метод:* {analysis.get('analysis_method', 'unknown')}\n\n"
        )
        
        # Кнопки действий
        keyboard = []
        if rating <= 3:
            keyboard.append([InlineKeyboardButton("📝 Сформировать ответ", callback_data="gen_response")])
        if rating >= 4:
            keyboard.append([InlineKeyboardButton("🙏 Ответ с благодарностью", callback_data="gen_thanks")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await update.message.reply_text(response, parse_mode="Markdown", reply_markup=reply_markup)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /report"""
    conn = sqlite3.connect('reviews.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # За последние 7 дней
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
    
    if stats['total'] == 0:
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
    
    # Формируем отчёт
    report = f"""
📊 *ОТЧЁТ ЗА НЕДЕЛЮ*
────────────────────
📈 Всего отзывов: {stats['total']}
⭐ Средний рейтинг: {stats['avg_rating']:.1f}/5

🎯 Распределение:
"""
    
    for row in rating_dist:
        bars = "█" * row['count'] if row['count'] <= 10 else "█" * 10
        report += f"{row['detected_rating']}★: {bars} {row['count']}\n"
    
    report += f"""
📊 Категории:
• Положительные: {stats['positive']}
• Нейтральные: {stats['neutral']}
• Негативные: {stats['negative']}
────────────────────
"""
    
    conn.close()
    await update.message.reply_text(report, parse_mode="Markdown")

async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM reviews")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(detected_rating) FROM reviews")
    avg_rating = cursor.fetchone()[0] or 0
    
    await update.message.reply_text(
        f"📊 *ОБЩАЯ СТАТИСТИКА*\n\n"
        f"📈 Всего отзывов: {total}\n"
        f"⭐ Средний рейтинг: {avg_rating:.1f}/5\n"
        f"🤖 Аналитик: {'DeepSeek' if analyzer.use_deepseek else 'Простая система'}\n\n"
        f"Используйте /analyze для анализа",
        parse_mode="Markdown"
    )
    
    conn.close()

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test"""
    keyboard = [
        [InlineKeyboardButton("🧪 Тест 1: Положительный отзыв", callback_data="test_1")],
        [InlineKeyboardButton("🧪 Тест 2: Негативный отзыв", callback_data="test_2")],
        [InlineKeyboardButton("🧪 Тест 3: Нейтральный отзыв", callback_data="test_3")]
    ]
    
    await update.message.reply_text(
        "🧪 *ТЕСТОВЫЙ РЕЖИМ*\n\nВыберите тестовый отзыв:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /myid - узнать chat_id"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    await update.message.reply_text(
        f"👤 *Ваши данные в Telegram:*\n\n"
        f"🆔 *Chat ID:* `{chat_id}`\n"
        f"👤 *Имя:* {user.first_name or ''} {user.last_name or ''}\n"
        f"📛 *Username:* @{user.username if user.username else 'нет'}\n\n"
        f"Этот ID можно использовать в переменной REPORT_CHAT_IDS",
        parse_mode="Markdown"
    )

async def add_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addreport - добавить чат для получения отчётов"""
    chat_id = update.effective_chat.id
    
    if chat_id not in report_recipients:
        report_recipients.append(chat_id)
        await update.message.reply_text(
            f"✅ *Вы добавлены в список получателей отчётов!*\n\n"
            f"📊 Ваш Chat ID: `{chat_id}`\n"
            f"⏰ Отчёты будут приходить каждый *понедельник в 8:00 утра*\n\n"
            f"Чтобы отписаться, используйте команду /stopreport",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("✅ Вы уже в списке получателей отчётов")

async def stopreport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stopreport - отписаться от отчётов"""
    chat_id = update.effective_chat.id
    
    if chat_id in report_recipients:
        report_recipients.remove(chat_id)
        await update.message.reply_text(
            "✅ *Вы отписаны от получения отчётов*\n\n"
            "Чтобы снова подписаться, используйте /addreport"
        )
    else:
        await update.message.reply_text("❌ Вы не были подписаны на отчёты")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "gen_response":
        # Ответ на негативный отзыв
        response_text = f"""
Благодарим за обратную связь. Для решения вопроса просим предоставить номер и дату заказ-наряда. Готовы связаться с вами для урегулирования ситуации.

С уважением, команда автосервиса «{SERVICE_NAME}»
📞 {SERVICE_PHONE}
📍 {SERVICE_ADDRESS}
"""
        await query.edit_message_text(
            f"📝 *ОТВЕТ ДЛЯ ПЛОЩАДКИ*\n\n{response_text}\n\n"
            "Скопируйте этот текст и отправьте на площадке.",
            parse_mode="Markdown"
        )
    
    elif data == "gen_thanks":
        # Ответ на положительный отзыв
        response_text = f"""
Рады, что остались довольны обслуживанием! 😊
Спасибо за тёплые слова — обязательно передадим команде.

Ждём вас снова в автосервисе «{SERVICE_NAME}»!

С наилучшими пожеланиями,
команда автосервиса «{SERVICE_NAME}»
"""
        await query.edit_message_text(
            f"🙏 *ОТВЕТ С БЛАГОДАРНОСТЬЮ*\n\n{response_text}\n\n"
            "Скопируйте этот текст и отправьте на площадке.",
            parse_mode="Markdown"
        )
    
    elif data.startswith("test_"):
        # Тестовые отзывы
        tests = {
            "test_1": "Отличный сервис! Мастера профессионалы, всё сделали быстро и качественно. Рекомендую!",
            "test_2": "Ужасное обслуживание. Ждал диагноста 3 часа, потом сказали что детали нет. Не ходите сюда!",
            "test_3": "Нормально починили, но дороговато. Персонал вежливый, чисто в помещении."
        }
        
        test_text = tests.get(data, "")
        await query.edit_message_text(f"🧪 *Тестирую:* {test_text}\n\nАнализирую...", parse_mode="Markdown")
        
        # Анализируем тестовый отзыв
        analysis = await analyzer.analyze(test_text)
        rating = analysis['detected_rating']
        
        await query.edit_message_text(
            f"🧪 *РЕЗУЛЬТАТ ТЕСТА*\n\n"
            f"📝 Текст: {test_text[:100]}...\n\n"
            f"📊 Оценка: {rating}/5 звезд\n"
            f"🎭 Тональность: {analysis.get('sentiment', 'neutral')}\n\n"
            f"Для реального анализа используйте /analyze",
            parse_mode="Markdown"
        )

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Автоматическая отправка отчёта"""
    if not report_recipients:
        print("📭 Нет получателей для отправки отчёта")
        return
    
    try:
        # Генерируем отчёт
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                AVG(detected_rating) as avg_rating
            FROM reviews 
            WHERE created_at >= datetime('now', '-7 days')
        ''')
        
        stats = cursor.fetchone()
        conn.close()
        
        if stats[0] == 0:
            print("📭 Нет отзывов за неделю для отчёта")
            return
        
        report = (
            f"📊 *ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ*\n"
            f"Автосервис «{SERVICE_NAME}»\n\n"
            f"📈 Отзывов за неделю: {stats[0]}\n"
            f"⭐ Средний рейтинг: {stats[1]:.1f}/5\n\n"
            f"Полный отчёт: /report\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        # Отправляем всем получателям
        success_count = 0
        for chat_id in report_recipients:
            try:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=report,
                    parse_mode="Markdown"
                )
                success_count += 1
                print(f"✅ Отчёт отправлен в чат {chat_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки в чат {chat_id}: {e}")
        
        print(f"📤 Отправлено отчётов: {success_count}/{len(report_recipients)}")
                    
    except Exception as e:
        print(f"❌ Ошибка генерации отчёта: {e}")

# ================== ЗАПУСК БОТА ==================
def main():
    """Запуск бота"""
    print("🔄 Создаю приложение Telegram...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Регистрация команд - ТОЛЬКО ЛАТИНИЦА!
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("stats", statistics_command))
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("addreport", add_report_command))
    app.add_handler(CommandHandler("stopreport", stopreport_command))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Настройка планировщика для еженедельных отчётов
    try:
        scheduler = AsyncIOScheduler()
        # Каждый понедельник в 8:00 утра (по Москве)
        scheduler.add_job(
            send_weekly_report,
            CronTrigger(day_of_week='mon', hour=8, minute=0, timezone='Europe/Moscow'),
            args=[app]
        )
        scheduler.start()
        print("✅ Еженедельные отчёты настроены на понедельник 8:00 (МСК)")
        print(f"👥 Получатели отчётов: {len(report_recipients)} чел.")
    except Exception as e:
        print(f"⚠️ Не удалось настроить планировщик: {e}")
    
    print("=" * 60)
    print("🚀 БОТ ЗАПУСКАЕТСЯ В BOTHOST...")
    print("=" * 60)
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
