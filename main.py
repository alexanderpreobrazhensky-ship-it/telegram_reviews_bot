import os
import json
import sqlite3
import logging
from fastapi import FastAPI, Request
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "reviews.db"

def db():
    """Безопасное подключение к SQLite с учетом многопоточности FastAPI"""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            text TEXT NOT NULL,
            rating INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}"

SERVICE_NAME = "Автосервис"
SERVICE_ADDRESS = "г. Москва"
SERVICE_PHONE = "+7 999 000-00-00"

def detect_railway_url():
    """Определение URL Railway с дополнительными проверками"""
    for var in ["RAILWAY_STATIC_URL", "RAILWAY_PUBLIC_DOMAIN", "RAILWAY_PRODUCTION_URL"]:
        url = os.getenv(var)
        if url:
            # Убираем пробелы и проверяем формат
            url = url.strip()
            if url.startswith("http"):
                return url
            else:
                # Если нет протокола, добавляем https://
                return f"https://{url}"
    
    proj = os.getenv("RAILWAY_PROJECT_NAME")
    if proj:
        return f"https://{proj}-production.up.railway.app"
    
    # Локальная разработка
    if os.getenv("LOCAL_DEV"):
        return "http://localhost:8000"
    
    return None

RAILWAY_URL = detect_railway_url()
WEBHOOK_URL = f"{RAILWAY_URL}/webhook" if RAILWAY_URL else None

def send_message(chat_id, text):
    """Безопасная отправка сообщения с обработкой ошибок"""
    if not TOKEN:
        logger.error("Не удалось отправить сообщение: TELEGRAM_BOT_TOKEN не установлен")
        return None
    
    try:
        response = requests.post(
            f"{API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения {chat_id}: {e}")
        return None

def analyze_text(text):
    """Улучшенный анализ текста отзыва"""
    if not text or not isinstance(text, str):
        return 3  # нейтральный по умолчанию
    
    text_l = text.lower()
    
    # Отрицательные слова (с приоритетом)
    negative = ["плохо", "ужас", "кошмар", "отврат", "не рекоменд", "не нормально", "не норм"]
    if any(word in text_l for word in negative):
        return 1
    
    # Положительные слова
    positive = ["хорошо", "отличн", "супер", "класс", "спасибо", "рекомендую"]
    if any(word in text_l for word in positive):
        return 5
    
    # Нейтральные/средние
    neutral = ["нормальн", "средн", "обычн", "норм"]
    if any(word in text_l for word in neutral):
        return 3
    
    return 3  # по умолчанию

def save_review(chat_id, text, rating):
    """Безопасное сохранение отзыва с использованием контекстного менеджера"""
    try:
        with db() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO reviews (chat_id, text, rating, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, text, rating, datetime.utcnow().isoformat())
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения отзыва: {e}")

def load_report_chat_ids():
    """Безопасная загрузка chat_id для отчетов"""
    ids = os.getenv("REPORT_CHAT_IDS", "")
    if not ids:
        return []
    
    result = []
    for item in ids.split(","):
        item = item.strip()
        if item and item.lstrip('-').isdigit():  # Разрешаем отрицательные ID (группы)
            result.append(int(item))
    
    return result

app = FastAPI()

@app.on_event("startup")
async def set_webhook():
    """Установка вебхука при запуске"""
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен, вебхук не настроен")
        return
    
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL не определен, вебхук не установлен")
        return
    
    try:
        logger.info(f"Устанавливаю вебхук: {WEBHOOK_URL}")
        response = requests.get(
            f"{API}/setWebhook",
            params={"url": WEBHOOK_URL},
            timeout=15
        )
        data = response.json()
        
        if data.get("ok"):
            logger.info(f"Вебхук установлен успешно: {data}")
        else:
            logger.error(f"Ошибка установки вебхука: {data}")
    except Exception as e:
        logger.error(f"Ошибка при установке вебхука: {e}")

@app.get("/")
def root():
    return {"status": "ok", "service": "telegram-bot"}

@app.get("/set-webhook")
def manual_set_webhook():
    """Ручная установка вебхука (как рекомендовал GPT)"""
    if not TOKEN or not WEBHOOK_URL:
        return {"error": "Токен или URL не установлены"}
    
    try:
        response = requests.get(
            f"{API}/setWebhook",
            params={"url": WEBHOOK_URL},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug")
def debug():
    """Отладочная информация"""
    return {
        "telegram_token_set": bool(TOKEN),
        "railway_url": RAILWAY_URL,
        "webhook_url": WEBHOOK_URL,
        "report_chat_ids": load_report_chat_ids(),
        "database_exists": os.path.exists(DB_PATH)
    }

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Исправленный обработчик вебхука"""
    try:
        # Логируем только update_id для скорости
        update = await request.json()
        update_id = update.get("update_id", "unknown")
        logger.info(f"📨 Webhook update_id: {update_id}")
        
        if "message" not in update:
            return {"ok": True}

        msg = update["message"]
        chat_id = msg["chat"]["id"]
        
        # Безопасное получение текста (исправление GPT)
        text = msg.get("text")
        if not text:
            # Если не текстовое сообщение (фото, стикер и т.д.)
            send_message(chat_id, "Пожалуйста, отправьте текстовое сообщение.")
            return {"ok": True}
        
        text = text.strip()

        if text.startswith("/start"):
            start_text = f"""🤖 *Бот автосервиса «{SERVICE_NAME}»*

📍 {SERVICE_ADDRESS}
📞 {SERVICE_PHONE}

*Команды:*
▫️ `/analyze текст` - анализ отзыва
▫️ `/stats` - статистика
▫️ `/myid` - ваш chat_id
▫️ `/report` - отчёт за неделю

*Пример:*
`/analyze Отличный сервис, быстро починили!`"""
            send_message(chat_id, start_text)

        elif text.startswith("/myid"):
            send_message(chat_id, f"Ваш chat_id: `{chat_id}`")

        elif text.startswith("/analyze"):
            review = text.replace("/analyze", "", 1).strip()
            if not review:
                send_message(chat_id, "Введите текст: `/analyze ваш отзыв`")
                return {"ok": True}

            rating = analyze_text(review)
            save_review(chat_id, review, rating)
            send_message(chat_id, f"Оценка отзыва: *{rating}/5*")

        elif text.startswith("/stats"):
            with db() as conn:
                c = conn.cursor()
                c.execute("SELECT rating, COUNT(*) as cnt FROM reviews GROUP BY rating")
                rows = c.fetchall()

            if not rows:
                send_message(chat_id, "Нет данных")
                return {"ok": True}

            out = "*Статистика отзывов:*\n\n"
            for r in rows:
                out += f"⭐ {r[0]}: {r[1]} шт.\n"
            send_message(chat_id, out)

        elif text.startswith("/report"):
            allowed = load_report_chat_ids()
            # Исправление GPT: убираем лишнюю проверку chat_id > 0
            if chat_id not in allowed:
                send_message(chat_id, "⚠️ У вас нет прав на просмотр отчетов")
                return {"ok": True}

            with db() as conn:
                c = conn.cursor()
                week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
                c.execute(
                    "SELECT rating, COUNT(*) FROM reviews WHERE created_at >= ? GROUP BY rating",
                    (week_ago,)
                )
                rows = c.fetchall()

            if not rows:
                send_message(chat_id, "За неделю нет отзывов")
                return {"ok": True}

            out = "*Отчет за неделю:*\n\n"
            for r in rows:
                out += f"⭐ {r[0]}: {r[1]} шт.\n"

            send_message(chat_id, out)
        
        else:
            # Если сообщение не команда
            send_message(chat_id, "Используйте команды: /start, /analyze, /stats, /myid")

    except Exception as e:
        logger.error(f"Ошибка в вебхуке: {e}")
        return {"ok": False}

    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)