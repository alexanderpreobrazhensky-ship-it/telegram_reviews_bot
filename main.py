import os
import sys

print("=" * 60)
print("🤖 ТЕСТ: Загрузка нейросетей на Bothost Basic")
print("=" * 60)

try:
    # Проверяем основные библиотеки
    from telegram.ext import ApplicationBuilder, CommandHandler
    print("✅ python-telegram-bot загружен")
    
    # Пробуем загрузить нейросети
    print("🧠 Загружаю трансформеры...")
    from transformers import pipeline
    
    # Компактная модель для экономии RAM
    model_name = "cointegrated/rubert-tiny2-sentiment-balanced"
    print(f"📦 Загружаю модель: {model_name}")
    
    sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model=model_name,
        device=-1  # CPU mode
    )
    
    print("✅ Нейросеть загружена и готова к работе!")
    
    # Тестируем на примере
    test_text = "Отличный сервис, всем рекомендую!"
    result = sentiment_analyzer(test_text)[0]
    
    print(f"🧪 Тестовый анализ: '{test_text}'")
    print(f"📊 Результат: {result['label']} ({result['score']:.2f})")
    
    # Бот
    async def start(update, context):
        await update.message.reply_text("🤖 Бот с нейросетями работает!")
    
    async def analyze(update, context):
        if context.args:
            text = " ".join(context.args)
            result = sentiment_analyzer(text[:512])[0]
            await update.message.reply_text(
                f"🧠 Анализ нейросетью:\n\n"
                f"Текст: {text[:100]}...\n"
                f"Результат: {result['label']}\n"
                f"Уверенность: {result['score']:.0%}"
            )
    
    TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН!")
    print("💬 Ищите в Telegram: /start")
    print("🔍 Тест анализа: /analyze ваш текст")
    print("=" * 60)
    
    app.run_polling(drop_pending_updates=True)
    
except Exception as e:
    print(f"❌ ОШИБКА: {e}")
    print("\n🔧 Возможные решения:")
    print("1. Убедитесь, что requirements.txt без ошибок")
    print("2. Проверьте доступность RAM (должно быть 1GB на Basic)")
    print("3. Попробуйте более легкую модель")
    
    import traceback
    traceback.print_exc()
    
    # Ждём перед выходом чтобы увидеть ошибку
    import time
    time.sleep(30)
