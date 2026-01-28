from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

async def start(update, context):
    await update.message.reply_text(
        "🤖 Бот техцентра «Лира»\n\n"
        "Команды:\n"
        "/start - это сообщение\n"
        "/review <текст> - анализ отзыва\n"
        "/test - проверка работы"
    )

async def test(update, context):
    await update.message.reply_text("✅ Бот активен и отвечает!")

async def review(update, context):
    """Обработчик команды /review"""
    if not context.args:
        await update.message.reply_text("Напишите текст отзыва: /review ваш текст здесь")
        return
    
    review_text = " ".join(context.args)
    
    # ПРОСТОЙ АНАЛИЗ БЕЗ НЕЙРОСЕТЕЙ (пока)
    if any(word in review_text.lower() for word in ['плох', 'ужас', 'кошмар', 'отврат']):
        sentiment = "негативный 👎"
    elif any(word in review_text.lower() for word in ['хорош', 'отличн', 'супер', 'рекоменд']):
        sentiment = "положительный 👍"
    else:
        sentiment = "нейтральный 🤔"
    
    await update.message.reply_text(
        f"📝 **Отзыв принят:**\n\n"
        f"_{review_text[:200]}_\n\n"
        f"📊 **Анализ:** {sentiment}\n\n"
        f"✅ Бот работает! Нейросети скоро будут добавлены."
    )

async def echo(update, context):
    """Обработка обычных сообщений"""
    await update.message.reply_text(
        "Я понимаю только команды:\n"
        "/start - помощь\n"
        "/review <текст> - анализ отзыва\n"
        "/test - проверка"
    )

# ЗАПУСК БОТА
app = ApplicationBuilder().token(TOKEN).build()

# Команды
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("test", test))
app.add_handler(CommandHandler("review", review))

# Обычные сообщения
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

app.run_polling(drop_pending_updates=True)
