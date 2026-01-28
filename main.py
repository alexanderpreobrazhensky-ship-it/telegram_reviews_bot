import os

print("=" * 60)
print("🤖 МИНИМАЛЬНЫЙ БОТ ДЛЯ BOTHOST")
print("=" * 60)

TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

try:
    import torch
    print(f"✅ Torch: {torch.__version__}")
except:
    print("❌ Torch не установлен")

try:
    from transformers import pipeline
    print("✅ Transformers загружены")
    
    # САМАЯ ЛЁГКАЯ модель
    analyzer = pipeline(
        "sentiment-analysis",
        model="cointegrated/rubert-tiny-sentiment",
        device=-1
    )
    print("✅ Модель загружена")
except Exception as e:
    print(f"⚠️ Нейросеть: {e}")

from telegram.ext import ApplicationBuilder, CommandHandler

async def start(update, context):
    await update.message.reply_text("✅ Бот работает!")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

print("🚀 Бот запущен")
app.run_polling()