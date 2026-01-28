from telegram.ext import ApplicationBuilder, CommandHandler

# Токен (старый, но рабочий)
TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

async def start(update, context):
    await update.message.reply_text("✅ Бот работает! /test /review")

async def test(update, context):
    await update.message.reply_text("🏓 ПОНГ! Бот активен!")

async def review(update, context):
    if not context.args:
        await update.message.reply_text("Напишите: /review ваш текст")
        return
    
    text = " ".join(context.args)
    await update.message.reply_text(f"📝 Отзыв: '{text}' принят!")

# Запуск
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("test", test))
app.add_handler(CommandHandler("review", review))

print("🤖 Бот запускается...")
app.run_polling(drop_pending_updates=True)
