import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# -------------------------------
# Переменная окружения Telegram
# -------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# -------------------------------
# Настройка логирования
# -------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# -------------------------------
# Команды бота
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет 👋\n"
        "Я бот техцентра «Лира».\n"
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

    # Заглушка вместо GPT
    gpt_reply = "✅ Бот работает без GPT. Ответ готов позже."

    await update.message.reply_text(
        f"📝 Получен отзыв:\n{review_text}\n\n"
        f"💡 Подготовленный ответ:\n{gpt_reply}"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я понимаю только команды.\n"
        "Напиши /start или /review"
    )

# -------------------------------
# Основная функция
# -------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logging.info("Бот запущен и ожидает сообщений")
    app.run_polling()

# -------------------------------
# Запуск бота
# -------------------------------
if name == "__main__":
    main()