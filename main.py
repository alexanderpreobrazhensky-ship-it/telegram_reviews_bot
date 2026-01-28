from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os

# Токен бота Telegram
TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

# Обработчик команды /review
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    rating = 1  # заглушка, можно позже автоматизировать
    # Формируем простой ответ (без GPT)
    answer = f"Принято! Мы получили ваш отзыв: \"{text}\". Спасибо за обратную связь."
    await update.message.reply_text(answer)

# Создаём приложение бота
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("review", handle_review))  # команда /review <текст>

# Запуск бота
if name == "__main__":
    app.run_polling()
