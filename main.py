import os
import json
from telegram.ext import ApplicationBuilder, CommandHandler

print("=" * 60)
print("🤖 ЗАПУСК БОТА С DEEPSEEK И ПЕРЕМЕННЫМИ ОКРУЖЕНИЯ")
print("=" * 60)

# ================== БЕЗОПАСНАЯ ЗАГРУЗКА КЛЮЧЕЙ ==================
# Получаем из переменных окружения Bothost
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

# Проверяем что загрузилось
print(f"TELEGRAM_TOKEN: {'✅ Найден' if TELEGRAM_TOKEN else '❌ НЕ найден'}")
print(f"DEEPSEEK_API_KEY: {'✅ Найден' if DEEPSEEK_API_KEY else '❌ НЕ найден'}")

if not TELEGRAM_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN не загружен!")
    print("Проверьте переменные окружения в Bothost")
    exit(1)

# Настройка DeepSeek
USE_DEEPSEEK = False
deepseek_client = None

if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.startswith("sk-"):
    try:
        from openai import OpenAI
        deepseek_client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        USE_DEEPSEEK = True
        print("✅ DeepSeek API инициализирован")
    except Exception as e:
        print(f"⚠️ Ошибка DeepSeek: {e}")
else:
    print("⚠️ DeepSeek отключен. Использую простой анализ.")

# ================== ПРОСТОЙ АНАЛИЗ (FALLBACK) ==================
def simple_analyze(text):
    """Простой анализ по ключевым словам"""
    text_lower = text.lower()
    
    negative = ['плох', 'ужас', 'кошмар', 'отврат', 'не рекоменд']
    positive = ['хорош', 'отличн', 'супер', 'рекоменд', 'спасиб']
    
    neg = sum(1 for word in negative if word in text_lower)
    pos = sum(1 for word in positive if word in text_lower)
    
    if neg > pos:
        return {"sentiment": "negative", "score": neg/(neg+pos)}
    elif pos > neg:
        return {"sentiment": "positive", "score": pos/(neg+pos)}
    else:
        return {"sentiment": "neutral", "score": 0.5}

# ================== DEEPSEEK АНАЛИЗ ==================
async def analyze_with_deepseek(text, platform="yandex"):
    """Анализ через DeepSeek API"""
    if not USE_DEEPSEEK or not deepseek_client:
        print("DeepSeek недоступен, использую простой анализ")
        return simple_analyze(text)
    
    try:
        prompt = f"""Анализируй отзыв для {platform.upper()}:
"{text}"

Верни JSON:
{{"sentiment": "positive/negative/neutral", "score": 0.95}}"""
        
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        print(f"✅ DeepSeek анализ: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Ошибка DeepSeek: {e}")
        return simple_analyze(text)

# ================== КОМАНДЫ БОТА ==================
async def start(update, context):
    """Команда /start"""
    status = "с DeepSeek" if USE_DEEPSEEK else "с простым анализом"
    
    await update.message.reply_text(
        f"🤖 *Бот техцентра «Лира» ({status})*\n\n"
        "Я анализирую отзывы и ищу нарушения правил.\n\n"
        "*Команды:*\n"
        "▫️ /start - это сообщение\n"
        "▫️ /analyze <текст> - анализ отзыва\n"
        "▫️ /test - проверка работы\n"
        "▫️ /status - статус системы\n\n"
        "Пример:\n"
        "`/analyze Отличный сервис, быстро починили!`",
        parse_mode="Markdown"
    )

async def analyze(update, context):
    """Анализ отзыва"""
    if not context.args:
        await update.message.reply_text("Напишите: /analyze ваш текст")
        return
    
    text = " ".join(context.args)
    
    # Показываем статус
    if USE_DEEPSEEK:
        await update.message.reply_text("🧠 *Анализирую через DeepSeek...*", parse_mode="Markdown")
        result = await analyze_with_deepseek(text)
    else:
        await update.message.reply_text("📊 *Анализирую...*", parse_mode="Markdown")
        result = simple_analyze(text)
    
    # Формируем ответ
    emoji = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}.get(result["sentiment"], "⚪")
    
    await update.message.reply_text(
        f"{emoji} *РЕЗУЛЬТАТ АНАЛИЗА*\n\n"
        f"📝 *Текст:* {text[:100]}...\n\n"
        f"📊 *Тональность:* {result['sentiment']}\n"
        f"🎯 *Уверенность:* {result.get('score', 0.5):.0%}\n\n"
        f"🤖 *Аналитик:* {'DeepSeek AI' if USE_DEEPSEEK else 'Простая система'}",
        parse_mode="Markdown"
    )

async def test(update, context):
    """Проверка работы"""
    status = "✅ DeepSeek активен" if USE_DEEPSEEK else "⚠️ DeepSeek недоступен"
    
    await update.message.reply_text(
        f"🧪 *ТЕСТ СИСТЕМЫ*\n\n"
        f"{status}\n"
        f"🤖 Бот работает\n"
        f"🔑 Переменные загружены\n\n"
        f"Проверьте: /analyze тестовый отзыв",
        parse_mode="Markdown"
    )

async def status(update, context):
    """Статус системы"""
    await update.message.reply_text(
        f"📊 *СТАТУС СИСТЕМЫ*\n\n"
        f"🤖 Бот: {'🟢 Работает' if TELEGRAM_TOKEN else '🔴 Ошибка'}\n"
        f"🧠 DeepSeek: {'🟢 Активен' if USE_DEEPSEEK else '🟡 Отключен'}\n"
        f"🔑 Переменные: {'🟢 Загружены' if DEEPSEEK_API_KEY else '🟡 Нет ключа'}\n\n"
        f"Используйте /analyze для анализа отзывов.",
        parse_mode="Markdown"
    )

# ================== ЗАПУСК БОТА ==================
print("🔄 Создаю приложение Telegram...")
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

print("🔄 Регистрирую команды...")
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("test", test))
app.add_handler(CommandHandler("status", status))

print("=" * 60)
print("🚀 БОТ ЗАПУСКАЕТСЯ...")
print("=" * 60)

app.run_polling(drop_pending_updates=True)
