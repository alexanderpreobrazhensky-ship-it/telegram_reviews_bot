from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Токен твоего бота
TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает 👍")

# Обработчик команды /review
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Тестовый ответ без GPT
    await update.message.reply_text("Тестовый ответ на отзыв: " + update.message.text)

# Создаем приложение бота
app = ApplicationBuilder().token(TOKEN).build()

# Регистрируем обработчики
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("review", handle_review))

# Запуск бота
app.run_polling()
