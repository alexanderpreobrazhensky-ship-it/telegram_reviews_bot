import os
import sys
import time

print("=" * 60)
print("🤖 ТЕСТОВЫЙ БОТ В BOTHOST")
print("=" * 60)

# Проверяем токен
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
print(f"TELEGRAM_BOT_TOKEN: {'✅ НАЙДЕН' if TOKEN else '❌ НЕ НАЙДЕН'}")

if not TOKEN:
    print("Добавьте TELEGRAM_BOT_TOKEN в настройках Bothost!")
    print("Жду 60 секунд...")
    time.sleep(60)
    sys.exit(1)

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    print("✅ Все библиотеки загружены")
except Exception as e:
    print(f"❌ Ошибка загрузки библиотек: {e}")
    time.sleep(60)
    sys.exit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🎉 *ТЕСТОВЫЙ БОТ РАБОТАЕТ!*\n\n"
        "Команды:\n"
        "▫️ /start - это сообщение\n"
        "▫️ /myid - ваш chat_id\n"
        "▫️ /ping - проверка связи",
        parse_mode="Markdown"
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /myid"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    await update.message.reply_text(
        f"👤 *Ваши данные:*\n\n"
        f"🆔 Chat ID: `{chat_id}`\n"
        f"👤 Имя: {user.first_name or '—'}\n"
        f"📛 Username: @{user.username if user.username else 'нет'}",
        parse_mode="Markdown"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ping"""
    await update.message.reply_text("🏓 Понг! Бот активен.")

def main():
    """Запуск бота"""
    print("🔄 Создаю приложение Telegram...")
    
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Регистрируем команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("myid", myid))
        app.add_handler(CommandHandler("id", myid))  # алиас
        app.add_handler(CommandHandler("ping", ping))
        
        print("✅ Бот настроен")
        print("🚀 Запускаю...")
        print("=" * 60)
        
        # Запускаем
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        print(f"❌ ОШИБКА ПРИ ЗАПУСКЕ: {e}")
        import traceback
        traceback.print_exc()
        print("⏳ Жду 300 секунд...")
        time.sleep(300)

if __name__ == "__main__":
    main()
