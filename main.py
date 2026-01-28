from telegram.ext import ApplicationBuilder, CommandHandler

TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

async def start(update, context):
    await update.message.reply_text("✅ Бот работает! Команды: /test /review")

async def test(update, context):
    """Обработчик команды /test"""
    user = update.effective_user
    await update.message.reply_text(
        f"🏓 ПОНГ! Бот активен!\n"
        f"👤 Пользователь: {user.first_name}\n"
        f"🆔 ID: {user.id}"
    )

async def review(update, context):
    if not context.args:
        await update.message.reply_text("Напишите: /review ваш текст")
        return
    
    text = " ".join(context.args)
    await update.message.reply_text(f"📝 Отзыв: '{text[:50]}...' принят!")

# СОЗДАЕМ И РЕГИСТРИРУЕМ ВСЕ КОМАНДЫ
print("🤖 Регистрирую команды...")
app = ApplicationBuilder().token(TOKEN).build()

# ВАЖНО: Все 3 команды регистрируем
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("test", test))    # ← ЭТОЙ СТРОКИ НЕ БЫЛО!
app.add_handler(CommandHandler("review", review))

print("✅ Команды зарегистрированы")
print("🚀 Запускаю бота...")

app.run_polling(drop_pending_updates=True)
