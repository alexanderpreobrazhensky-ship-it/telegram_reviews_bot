from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import openai

TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"
openai.api_key = os.environ["OPENAI_API_KEY"]

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем текст отзыва из сообщения
    text = update.message.text
    rating = 1  # можно позже автоматизировать определение рейтинга

    # Формируем промпт для GPT
    prompt = f"""
    Ты ассистент автосервиса. Дай:
    1) Вежливый ответ клиенту на отзыв: "{text}"
    2) Если рейтинг 1 или 2 звезды, подготовь текст жалобы, который можно вставить на Яндекс/2ГИС.
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
app.add_handler(CommandHandler("review", handle_review))  # команда /review <текст>

app.run_polling()
