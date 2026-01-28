from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    rating = 1  # можно позже автоматизировать определение рейтинга

    # Заглушка вместо GPT
    answer = f"Спасибо за ваш отзыв! Текст отзыва: \"{text}\""

    await update.message.reply_text(answer)

# Создаём приложение бота
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("review", handle_review))  # команда /review <текст>

app.run_polling()
