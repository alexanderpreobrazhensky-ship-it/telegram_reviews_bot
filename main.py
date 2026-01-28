from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import openai

# Токен вашего Telegram бота
TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

# Подключаем OpenAI через переменную среды
openai.api_key = os.environ["OPENAI_API_KEY"]

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает 👍")

# Команда /review
async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("/review", "").strip()  # убираем команду из текста
    if not text:
        await update.message.reply_text("Напишите текст отзыва после команды /review")
        return

    # Промпт для GPT
    prompt = f"""
Ты ассистент автосервиса. Нужно сделать два текста:
1) Вежливый ответ клиенту на отзыв: "{text}"
2) Если отзыв негативный (1-2 звезды), подготовь текст жалобы, который можно вставить на Яндекс/2ГИС.
Ответь в формате:
Ответ клиенту:
<текст ответа>

Жалоба:
<текст жалобы, если есть>
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Ошибка GPT: {e}")

# Создаём приложение бота
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("review", handle_review))

# Запуск бота
app.run_polling()