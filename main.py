import os
import logging
import requests
from flask import Flask, request, jsonify

# ================== Настройка логирования ==================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ================== Проверка переменных среды ==================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
ADMIN_ID = os.environ.get("ADMIN_ID")
AI_ENGINE = os.environ.get("AI_ENGINE", "gemini")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("TELEGRAM_BOT_TOKEN и WEBHOOK_URL должны быть установлены в переменных среды!")

# ================== Flask App ==================
app = Flask(__name__)

# ================== Вспомогательные функции ==================
def tg_send(chat_id, text):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text})
    if not resp.ok:
        logger.error(f"Ошибка отправки сообщения: {resp.text}")
    return resp

def ai_analyze(text):
    """Обработка текста AI (Gemini)"""
    if AI_ENGINE.lower() != "gemini":
        return f"[{AI_ENGINE} AI] Ваш текст: {text}"
    
    # Пример запроса к Gemini AI
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    data = {"prompt": text, "max_tokens": 200}
    try:
        resp = requests.post("https://api.gemini.ai/v1/generate", headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        return result.get("text", "[AI ответ пуст]")
    except Exception as e:
        logger.error(f"Ошибка Gemini AI: {e}")
        return "[AI недоступен]"

# ================== Вебхук ==================
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    logger.info(f"Получен update: {update}")

    message = update.get("message")
    if not message:
        return jsonify({"ok": True})

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    logger.info(f"Сообщение от {chat_id}: {text}")

    # Обработка команд
    if text.startswith("/"):
        if text == "/start":
            reply = "Привет! Я готов обрабатывать ваши отзывы."
        elif text == "/myid":
            reply = f"Ваш chat_id: {chat_id}"
        elif text.startswith("/analyze"):
            user_text = text[len("/analyze"):].strip()
            reply = ai_analyze(user_text)
        else:
            reply = "Неизвестная команда."
    else:
        # Все обычные сообщения обрабатывает AI
        reply = ai_analyze(text)

    tg_send(chat_id, reply)
    logger.info(f"Ответ отправлен: {reply}")

    return jsonify({"ok": True})

# ================== Автоматическая настройка вебхука ==================
@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}")
    logger.info(f"Установлен вебхук: {resp.text}")
    return resp.text

@app.route("/remove_webhook", methods=["GET"])
def remove_webhook():
    resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
    logger.info(f"Удалён вебхук: {resp.text}")
    return resp.text

@app.route("/debug", methods=["GET"])
def debug():
    """Проверка текущего вебхука"""
    resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo")
    return resp.text

# ================== Запуск ==================
if __name__ == "__main__":
    logger.info("Бот запущен")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
