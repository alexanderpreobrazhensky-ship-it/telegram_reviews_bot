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

TELEGRAM_BOT_TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER"

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

    response = (
        "📝 Получен отзыв:\n\n"
        f"{review_text}\n\n"
        "✅ Бот работает корректно.\n"
        "GPT подключим позже."
    )

    await update.message.reply_text(response)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я понимаю только команды.\n"
        "Напиши /start или /review"
    )

# =====================
# ЗАПУСК БОТА
# =====================

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    logging.info("Бот запущен и ожидает сообщения")
    app.run_polling()

# 🔴 ВАЖНО: ОБРАТИ ВНИМАНИЕ НА ПОДЧЁРКИВАНИЯ
if name == "__main__":
    main()
