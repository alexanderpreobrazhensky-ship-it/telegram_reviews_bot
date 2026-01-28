import os
import sys

print("=" * 60)
print("🤖 ТЕСТОВЫЙ ЗАПУСК НА BOTHOST")
print("=" * 60)

# Проверяем токен
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4")
print(f"✅ Токен: {TOKEN[:10]}...")

try:
    # Проверяем torch
    import torch
    print(f"✅ PyTorch: {torch.__version__}")
    print(f"✅ Доступно CUDA: {torch.cuda.is_available()}")
    
    # Проверяем transformers
    from transformers import pipeline
    print("✅ Transformers загружены")
    
    # Простая модель для теста
    model_name = "cointegrated/rubert-tiny2-sentiment-balanced"
    print(f"✅ Загружаю модель: {model_name}")
    
    analyzer = pipeline("sentiment-analysis", model=model_name)
    
    # Тест анализа
    test_text = "Отличный сервис!"
    result = analyzer(test_text)[0]
    print(f"🧪 Тест: '{test_text}' → {result['label']} ({result['score']:.2f})")
    
    # Telegram бот
    from telegram.ext import ApplicationBuilder, CommandHandler
    
    async def start(update, context):
        await update.message.reply_text("🤖 Бот работает! Нейросети загружены.")
    
    async def analyze(update, context):
        if context.args:
            text = " ".join(context.args)
            result = analyzer(text[:512])[0]
            await update.message.reply_text(
                f"🧠 Нейросеть: {result['label']}\n"
                f"📊 Уверенность: {result['score']:.0%}"
            )
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analyze", analyze))
    
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("💬 Telegram: /start")
    print("🔍 Анализ: /analyze <текст>")
    print("=" * 60)
    
    app.run_polling(drop_pending_updates=True)
    
except Exception as e:
    print(f"❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    
    # Ждем чтобы увидеть ошибку в логах
    import time
    time.sleep(30)
