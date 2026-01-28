import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import openai  # библиотека GPT

# ==========================
# Переменные окружения
# ==========================
TELEGRAM_BOT_TOKEN = os.environ.get("7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4")
OPENAI_API_KEY = os.environ.get("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")

# Настройка OpenAI
openai.api_key = OPENAI_API_KEY

# ==========================
# Логирование
# ==========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ==========================
# Команды бота
# ==========================
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

    # Отправляем текст в GPT для формирования ответа
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты помощник менеджера автосервиса, готовишь ответ на отзывы."},
                {"role": "user", "content": review_text}
            ],
            max_tokens=200
        )
        gpt_reply = response.choices[0].message.content
    except Exception as e:
        gpt_reply = f"Ошибка GPT: {e}"

    await update.message.reply_text(
        f"📝 Получен отзыв:\n{review_text}\n\n"
        f"💡 GPT подготовил ответ:\n{gpt_reply}"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я понимаю только команды.\n"
        "Напиши /start или /review"
    )

# ==========================
# Запуск бота
# ==========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    logging.info("Бот запущен и ожидает сообщений")
    app.run_polling()

# ✅ Важно: правильная проверка главного модуля
if name == "__main__":
    main()
