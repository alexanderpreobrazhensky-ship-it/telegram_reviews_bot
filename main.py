import os
import sys

print("=" * 60)
print("🤖 ЛЕГКИЙ БОТ ДЛЯ BOTHOST (оптимизированный)")
print("=" * 60)

# Пытаемся импортировать torch
try:
    import torch
    print(f"✅ PyTorch: {torch.__version__}")
    print(f"🎯 Память: {torch.cuda.is_available()}")
except ImportError:
    print("❌ PyTorch не установлен")
    sys.exit(1)

# Используем ЛЁГКУЮ модель
try:
    from transformers import pipeline
    print("✅ Transformers загружены")
    
    # КОМПАКТНАЯ модель (вместо 500MB → 40MB)
    model_name = "cointegrated/rubert-tiny-sentiment"  # Всего 40MB!
    print(f"📦 Загружаю: {model_name}")
    
    sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model=model_name,
        tokenizer=model_name,
        device=-1  # Только CPU
    )
    
    # Тест
    test_text = "Тест работы"
    result = sentiment_analyzer(test_text[:128])[0]  # Ограничиваем длину
    print(f"🧪 Тест: '{test_text}' → {result['label']}")
    
except Exception as e:
    print(f"⚠️ Нейросеть не загрузилась: {e}")
    print("🔄 Использую fallback-анализ")

# Telegram бот
from telegram.ext import ApplicationBuilder, CommandHandler

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4")

async def start(update, context):
    await update.message.reply_text("🤖 Бот работает! /analyze <текст>")

async def analyze(update, context):
    if not context.args:
        await update.message.reply_text("Напишите: /analyze ваш текст")
        return
    
    text = " ".join(context.args)
    
    try:
        # Пробуем нейросеть
        result = sentiment_analyzer(text[:256])[0]
        response = f"🧠 Анализ: {result['label']}\n📊 Уверенность: {result['score']:.0%}"
    except:
        # Fallback если нейросеть не работает
        response = f"📝 Текст: {text[:100]}...\n✅ Принято к обработке"
    
    await update.message.reply_text(response)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("analyze", analyze))

print("=" * 60)
print("🚀 БОТ ЗАПУЩЕН!")
print("=" * 60)

app.run_polling(drop_pending_updates=True)
