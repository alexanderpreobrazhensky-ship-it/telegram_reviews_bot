import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =====================
# НАСТРОЙКИ
# =====================

TELEGRAM_BOT_TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

# =====================
# ЛОГИ
# =====================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =====================
# КОМАНДЫ
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет 👋\n\n"
        "Я бот техцентра «Лира».\n\n"
        "Пока работаю в тестовом режиме.\n"
        "Команда:\n"
        "/review <текст отзыва>"
    )

async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❗️ Пришли отзыв так:\n"
            "/review Диагност не понравился, сервис отвратительный"
        )
        return

    review_text = " ".join(context.args)

    # Пока просто эхо-ответ
    answer = (
        "📝 Получен отзыв:\n\n"
        f"{review_text}\n\n"
        "✅ Бот работает.\n"
        "GPT подключим позже."
    )

    await update.message.reply_text(answer)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я понимаю только команды.\n"
        "Используй /start или /review"
    )

# =====================
# ЗАПУСК
# =====================

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logging.info("Бот запущен и ожидает сообщения")
    app.run_polling()

if name == "__main__":
    main()
