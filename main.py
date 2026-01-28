import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Токен Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4")

# ✅ Проверка наличия токена при запуске
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот техцентра «Лира».\n"
        "Команды:\n"
        "/review <текст отзыва>"
    )

async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❗ Используй команду так:\n"
            "/review Диагност не понравился, сервис отвратительный"
        )
        return

    review_text = " ".join(context.args)
    logger.info(f"Получен отзыв: {review_text}")
    
    # Простой анализ тональности
    sentiment = analyze_sentiment(review_text)
    
    # Подготовка ответа в зависимости от тональности
    if sentiment == "негативный":
        response = "⚠️ Получен негативный отзыв. Рекомендуем:\n1. Извиниться перед клиентом\n2. Предложить компенсацию\n3. Исправить ошибки"
    elif sentiment == "положительный":
        response = "✅ Получен положительный отзыв! Благодарим клиента и предлагаем бонусы за лояльность."
    else:
        response = "📋 Получен нейтральный отзыв. Можно уточнить детали и улучшить сервис."

    await update.message.reply_text(
        f"📝 Отзыв: {review_text}\n\n"
        f"📊 Анализ: {sentiment.upper()}\n\n"
        f"💡 Рекомендации:\n{response}"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info(f"Получено сообщение: {user_text}")
    await update.message.reply_text(
        "Я понимаю только команды.\nНапиши /start или /review <текст отзыва>"
    )

def analyze_sentiment(text: str) -> str:
    """Простой анализ тональности текста"""
    text_lower = text.lower()
    
    negative_words = ['плохо', 'ужасно', 'отвратительно', 'не понравился', 'кошмар', 
                     'говно', 'гадость', 'мерзость', 'хреново', 'отстой', 'долго', 'дорого']
    positive_words = ['хорошо', 'отлично', 'супер', 'понравилось', 'рекомендую', 
                     'спасибо', 'благодарю', 'доволен', 'довольна', 'быстро', 'качественно']
    
    neg_count = sum(1 for word in negative_words if word in text_lower)
    pos_count = sum(1 for word in positive_words if word in text_lower)
    
    if neg_count > pos_count:
        return "негативный"
    elif pos_count > neg_count:
        return "положительный"
    else:
        return "нейтральный"

def main():
    try:
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("review", review))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
        
        logger.info("Бот запущен и ожидает сообщений")
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        raise

# ✅ ИСПРАВЛЕННАЯ СТРОКА - обратите внимание на ДВА подчеркивания с каждой стороны
if __name__ == "__main__":
    main()
