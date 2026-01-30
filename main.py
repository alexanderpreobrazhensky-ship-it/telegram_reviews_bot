import os
import re
import json
import logging
import sqlite3
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

# ----------------------
# Настройки
# ----------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEFAULT_AI_ENGINE = os.getenv("DEFAULT_AI_ENGINE", "gptfree")  # gptfree | openai | deepseek | gemini
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ----------------------
# Логи
# ----------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------
# SQLite DB
# ----------------------
DB_FILE = "reviews.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            rating INTEGER,
            ai_analysis TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

# ----------------------
# Zero-width cleanup
# ----------------------
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return ZERO_WIDTH_PATTERN.sub("", text)

# ----------------------
# Telegram message utils
# ----------------------
def split_long_message(text: str, limit: int = 4000):
    chunks = []
    while len(text) > limit:
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = limit
        chunks.append(text[:split_pos])
        text = text[split_pos:]
    chunks.append(text)
    return chunks

def send_telegram_message(chat_id: int, text: str):
    text = clean_text(text)
    chunks = split_long_message(text)

    for chunk in chunks:
        data = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
            "parse_mode": "Markdown"
        }
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=data,
            timeout=10
        )
        if response.status_code != 200:
            logger.warning(f"Markdown failed, trying plain text: {response.text}")
            data.pop("parse_mode")
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json=data,
                timeout=10
            )
            if response.status_code != 200:
                logger.error(f"Telegram send error: {response.text}")

# ----------------------
# AI движки с авто-переключением
# ----------------------
AI_PRIORITY = ["gptfree", "openai", "deepseek", "gemini"]

def analyze_review_ai(text: str, engine=None):
    text = clean_text(text)
    engines = AI_PRIORITY if not engine else [engine]
    analysis = "Нет ответа"
    rating = 3

    for eng in engines:
        try:
            if eng == "gptfree":
                # Пример бесплатного API
                url = "https://gptfreeapi.example.com/analyze"
                resp = requests.post(url, json={"text": text}, timeout=5)
                if resp.ok:
                    data = resp.json()
                    analysis = data.get("analysis", text[:300])
                    rating = data.get("rating", 3)
                    return analysis, max(1, min(5, int(rating)))

            elif eng == "openai" and OPENAI_API_KEY:
                import openai
                openai.api_key = OPENAI_API_KEY
                resp = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": text}],
                    temperature=0.7
                )
                analysis = resp.choices[0].message.content
                rating_match = re.search(r"[1-5]", analysis)
                rating = int(rating_match.group()) if rating_match else 3
                return analysis, max(1, min(5, int(rating)))

            elif eng == "deepseek" and DEEPSEEK_API_KEY:
                url = "https://api.deepseek.com/analyze"
                headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
                resp = requests.post(url, headers=headers, json={"text": text}, timeout=5)
                if resp.ok:
                    data = resp.json()
                    analysis = data.get("summary", text[:300])
                    rating = data.get("rating", 3)
                    return analysis, max(1, min(5, int(rating)))

            elif eng == "gemini" and GEMINI_API_KEY:
                url = "https://geminiapi.example.com/analyze"
                headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
                resp = requests.post(url, headers=headers, json={"text": text}, timeout=5)
                if resp.ok:
                    data = resp.json()
                    analysis = data.get("analysis", text[:300])
                    rating = data.get("rating", 3)
                    return analysis, max(1, min(5, int(rating)))

        except Exception as e:
            logger.warning(f"AI engine {eng} failed: {e}")
            continue

    # Если ничего не сработало
    return analysis, rating

# ----------------------
# Handlers
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для анализа отзывов. Используй /analyze <текст>."
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"Твой ID: {update.message.from_user.id}\nUsername: @{update.message.from_user.username}"
    await update.message.reply_text(msg)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Отправь /analyze <текст отзыва>")
        return

    analysis, rating = analyze_review_ai(text)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO reviews (user_id, username, text, rating, ai_analysis, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (update.message.from_user.id,
         update.message.from_user.username,
         text,
         rating,
         analysis,
         datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🔹 AI анализ: {analysis}\n🔹 Рейтинг: {rating}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), AVG(rating) FROM reviews")
    total, avg_rating = c.fetchone()
    conn.close()
    await update.message.reply_text(f"Всего отзывов: {total}\nСредний рейтинг: {avg_rating:.2f}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, text, rating FROM reviews ORDER BY created_at DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    msg = "\n\n".join([f"#{r[0]} | {r[2]}⭐\n{r[1]}" for r in rows])
    await update.message.reply_text(msg or "Нет отзывов")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Debug OK ✅")

# ----------------------
# Main
# ----------------------
def main():
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("debug", debug))

    logger.info("Bot started with multi-AI fallback")
    app.run_polling()

if __name__ == "__main__":
    main()