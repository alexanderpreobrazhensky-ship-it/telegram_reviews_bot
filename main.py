import os
import json
import logging
import threading
import csv
import io
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

import requests
from flask import Flask, request

# -------------------------
# Logging
# -------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telegram-reviews-bot")

# -------------------------
# Telegram env
# -------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("Missing WEBHOOK_URL")

BOT_PATH_SECRET = os.getenv("BOT_PATH_SECRET", "hook")
WEBHOOK_PATH = f"/webhook/{BOT_PATH_SECRET}"

TG_TIMEOUT = float(os.getenv("TG_TIMEOUT", "10"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "12"))

# -------------------------
# Admins
# -------------------------
REPORT_CHAT_IDS_RAW = (os.getenv("REPORT_CHAT_IDS") or "").strip()

def parse_admin_ids(raw: str) -> List[int]:
    if not raw:
        return []
    out: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except Exception:
            logger.warning("Invalid REPORT_CHAT_IDS entry: %r", part)
    return out

ADMIN_CHAT_IDS = parse_admin_ids(REPORT_CHAT_IDS_RAW)
if not ADMIN_CHAT_IDS:
    logger.warning("REPORT_CHAT_IDS is empty -> admin commands allowed for everyone (NOT recommended).")

def is_admin(chat_id: int) -> bool:
    return (not ADMIN_CHAT_IDS) or (chat_id in ADMIN_CHAT_IDS)

# -------------------------
# AI multi-engine env
# -------------------------
AI_ENGINE = (os.getenv("AI_ENGINE") or "deepseek").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-beta")

# Endpoints
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")

# DeepSeek via proxy base
DEEPSEEK_BASE_URL = (os.getenv("DEEPSEEK_BASE_URL") or "").strip()
if DEEPSEEK_BASE_URL:
    DEEPSEEK_URL = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
else:
    DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")

GROK_URL = os.getenv("GROK_URL", "https://api.x.ai/v1/chat/completions")

# -------------------------
# DB (Postgres on Railway or SQLite fallback)
# -------------------------
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")
SQL_PARAM = "%s" if USE_POSTGRES else "?"

# psycopg v3 (binary wheels) — не требует libpq.so.5 в системе
if USE_POSTGRES:
    try:
        import psycopg
    except Exception as e:
        raise RuntimeError(
            "Postgres detected (DATABASE_URL set) but psycopg is not available. "
            "Install psycopg[binary]==3.x in requirements.txt"
        ) from e

def db_connect():
    if USE_POSTGRES:
        return psycopg.connect(DATABASE_URL)
    else:
        import sqlite3
        conn = sqlite3.connect("reviews.db")
        conn.row_factory = sqlite3.Row
        return conn

def db_init():
    if USE_POSTGRES:
        ddl = """
        CREATE TABLE IF NOT EXISTS reviews (
          id               SERIAL PRIMARY KEY,
          source           TEXT NOT NULL,
          rating           INTEGER NULL,
          author           TEXT NULL,
          url              TEXT NULL,
          published_at     TIMESTAMP NULL,
          text             TEXT NOT NULL,
          added_by_user_id BIGINT NULL,
          added_by_chat_id BIGINT NULL,
          created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    else:
        ddl = """
        CREATE TABLE IF NOT EXISTS reviews (
          id               INTEGER PRIMARY KEY AUTOINCREMENT,
          source           TEXT NOT NULL,
          rating           INTEGER NULL,
          author           TEXT NULL,
          url              TEXT NULL,
          published_at     TEXT NULL,
          text             TEXT NOT NULL,
          added_by_user_id INTEGER NULL,
          added_by_chat_id INTEGER NULL,
          created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(ddl)
        conn.commit()
        logger.info("DB init OK (postgres=%s)", USE_POSTGRES)
    finally:
        conn.close()

db_init()

# -------------------------
# Flask
# -------------------------
app = Flask(__name__)

# -------------------------
# Helpers: redact secrets in logs
# -------------------------
def _redact(s: str) -> str:
    if not s:
        return s
    for key in [GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, GROK_API_KEY]:
        if key and key in s:
            s = s.replace(key, "***REDACTED***")
    return s

# -------------------------
# Telegram API
# -------------------------
def tg_send_message(chat_id: int, text: str, reply_to: Optional[int] = None) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

    try:
        r = requests.post(url, json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("Telegram sendMessage failed: %s", _redact(r.text[:800]))
    except Exception as e:
        logger.exception("Telegram sendMessage exception: %s", e)

def set_webhook() -> None:
    full_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
    logger.info("Setting webhook: %s", full_url)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": full_url},
            timeout=TG_TIMEOUT,
        )
        # 429 возможен, если два gunicorn worker одновременно ставят webhook
        if r.status_code == 429:
            logger.warning("setWebhook got 429 (ignored): %s", _redact(r.text[:400]))
            return
        if r.status_code != 200:
            logger.error("setWebhook failed status=%s body=%s", r.status_code, _redact(r.text[:800]))
        else:
            logger.info("setWebhook OK: %s", _redact(r.text[:400]))
    except Exception as e:
        logger.exception("set_webhook exception: %s", e)

# Auto webhook on boot (can disable via env)
if os.getenv("DISABLE_WEBHOOK_SETUP", "0") != "1":
    set_webhook()

# -------------------------
# Review helpers + DB ops
# -------------------------
def parse_kv_args(arg_str: str) -> Tuple[Dict[str, str], str]:
    """
    Parses tokens like key=value from the beginning; returns (kv, remaining_text).
    Example:
      'source=yandex rating=5 url=https://... Текст...' -> ({...}, 'Текст...')
    """
    tokens = arg_str.strip().split()
    kv: Dict[str, str] = {}
    rest_tokens: List[str] = []

    for t in tokens:
        # keep URLs intact
        if "=" in t and not t.lower().startswith("http"):
            k, v = t.split("=", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            if k and v:
                kv[k] = v
                continue
        rest_tokens.append(t)

    return kv, " ".join(rest_tokens).strip()

def parse_date(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def db_insert_review(
    source: str,
    text: str,
    rating: Optional[int],
    author: Optional[str],
    url: Optional[str],
    published_at: Optional[datetime],
    added_by_user_id: Optional[int],
    added_by_chat_id: Optional[int],
) -> int:
    conn = db_connect()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                f"""
                INSERT INTO reviews (source, rating, author, url, published_at, text, added_by_user_id, added_by_chat_id)
                VALUES ({SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM})
                RETURNING id
                """,
                (source, rating, author, url, published_at, text, added_by_user_id, added_by_chat_id),
            )
            new_id = cur.fetchone()[0]
        else:
            cur.execute(
                f"""
                INSERT INTO reviews (source, rating, author, url, published_at, text, added_by_user_id, added_by_chat_id)
                VALUES ({SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM})
                """,
                (
                    source,
                    rating,
                    author,
                    url,
                    published_at.isoformat() if published_at else None,
                    text,
                    added_by_user_id,
                    added_by_chat_id,
                ),
            )
            new_id = cur.lastrowid
        conn.commit()
        return int(new_id)
    finally:
        conn.close()

def db_get_review(review_id: int) -> Optional[Dict[str, Any]]:
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM reviews WHERE id={SQL_PARAM}", (review_id,))
        row = cur.fetchone()
        if not row:
            return None

        if USE_POSTGRES:
            cols = [d[0] for d in cur.description]
            return {cols[i]: row[i] for i in range(len(cols))}
        else:
            return dict(row)
    finally:
        conn.close()

def db_list_reviews(limit: int = 10, source: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = db_connect()
    try:
        cur = conn.cursor()
        if source:
            cur.execute(
                f"SELECT * FROM reviews WHERE source={SQL_PARAM} ORDER BY id DESC LIMIT {int(limit)}",
                (source,),
            )
        else:
            cur.execute(f"SELECT * FROM reviews ORDER BY id DESC LIMIT {int(limit)}")

        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []

        if USE_POSTGRES:
            cols = [d[0] for d in cur.description]
            for r in rows:
                out.append({cols[i]: r[i] for i in range(len(cols))})
        else:
            out = [dict(r) for r in rows]

        return out
    finally:
        conn.close()

def db_delete_review(review_id: int) -> bool:
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM reviews WHERE id={SQL_PARAM}", (review_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

def review_preview(r: Dict[str, Any], max_len: int = 220) -> str:
    text = (r.get("text") or "").strip().replace("\n", " ")
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    parts = [
        f"#{r.get('id')} [{r.get('source')}]",
        f"rating={r.get('rating')}" if r.get("rating") is not None else None,
        f"url={r.get('url')}" if r.get("url") else None,
    ]
    head = " ".join([p for p in parts if p])
    return f"{head}\n{text}"

def export_csv(reviews: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "source", "rating", "author", "url", "published_at", "text", "created_at"])
    for r in reviews:
        writer.writerow([
            r.get("id"),
            r.get("source"),
            r.get("rating"),
            r.get("author"),
            r.get("url"),
            r.get("published_at"),
            (r.get("text") or "").replace("\n", "\\n"),
            r.get("created_at"),
        ])
    return buf.getvalue()

# -------------------------
# AI prompt + engines
# -------------------------
def build_review_prompt(text: str) -> str:
    return (
        "Ты — аналитик клиентских отзывов. Проанализируй отзыв и верни:\n"
        "1) Тональность (позитив/нейтр/негатив)\n"
        "2) Основные темы (список)\n"
        "3) Ключевые проблемы (если есть)\n"
        "4) Рекомендации бизнесу (2-5 пунктов)\n"
        "5) Короткое резюме в 1-2 предложения\n\n"
        f"Отзыв:\n{text}"
    )

def call_deepseek(prompt: str) -> str:
    if not DEEPSEEK_API_KEY:
        return "❌ DEEPSEEK_API_KEY не задан."

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for analyzing customer reviews."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
        logger.info("DeepSeek status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return "❌ DeepSeek вернул пустой ответ (нет choices)"
        msg = choices[0].get("message", {})
        txt = (msg.get("content") or "").strip()
        return txt or "❌ DeepSeek прислал пустой текст"
    except requests.exceptions.HTTPError:
        if resp.status_code == 429:
            return "⚠️ DeepSeek: лимиты/квота (429). Попробуй позже."
        return f"❌ DeepSeek HTTP {resp.status_code}. Проверь ключ/URL."
    except Exception as e:
        logger.exception("DeepSeek exception: %s", e)
        return "❌ Ошибка при обращении к DeepSeek."

def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY не задан."

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }

    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=AI_TIMEOUT,
        )
        logger.info("Gemini status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return "❌ Gemini вернул пустой ответ (нет candidates)"
        parts = candidates[0].get("content", {}).get("parts", [])
        txt = ((parts[0].get("text") if parts else "") or "").strip()
        return txt or "❌ Gemini прислал пустой текст"

    except requests.exceptions.HTTPError:
        # не логируем traceback — в URL есть key
        if resp.status_code == 429:
            return "⚠️ Gemini: лимиты/квота (429). Попробуй позже."
        return f"❌ Gemini HTTP {resp.status_code}. Проверь ключ/доступ."
    except Exception as e:
        logger.exception("Gemini exception: %s", e)
        return "❌ Ошибка при обращении к Gemini."

def call_openai(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "❌ OPENAI_API_KEY не задан."

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for analyzing customer reviews."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(OPENAI_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
        logger.info("OpenAI status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        txt = (((choices[0].get("message", {}) or {}).get("content") if choices else "") or "").strip()
        return txt or "❌ OpenAI прислал пустой текст"
    except requests.exceptions.HTTPError:
        if resp.status_code == 429:
            return "⚠️ OpenAI: лимиты/квота (429). Попробуй позже."
        return f"❌ OpenAI HTTP {resp.status_code}. Проверь ключ/модель."
    except Exception as e:
        logger.exception("OpenAI exception: %s", e)
        return "❌ Ошибка при обращении к OpenAI."

def call_grok(prompt: str) -> str:
    if not GROK_API_KEY:
        return "❌ GROK_API_KEY (или XAI_API_KEY) не задан."

    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for analyzing customer reviews."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(GROK_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
        logger.info("Grok status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        txt = (((choices[0].get("message", {}) or {}).get("content") if choices else "") or "").strip()
        return txt or "❌ Grok прислал пустой текст"
    except requests.exceptions.HTTPError:
        if resp.status_code == 429:
            return "⚠️ Grok: лимиты/квота (429). Попробуй позже."
        return f"❌ Grok HTTP {resp.status_code}. Проверь ключ/модель."
    except Exception as e:
        logger.exception("Grok exception: %s", e)
        return "❌ Ошибка при обращении к Grok."

def analyze_text(text: str) -> str:
    prompt = build_review_prompt(text)
    engine = (AI_ENGINE or "deepseek").lower()

    if engine in ("deepseek", "deep_seek", "ds"):
        return call_deepseek(prompt)
    if engine == "gemini":
        return call_gemini(prompt)
    if engine in ("openai", "gpt", "chatgpt"):
        return call_openai(prompt)
    if engine in ("grok", "xai"):
        return call_grok(prompt)

    return f"❌ Неизвестный AI_ENGINE='{engine}'. Допустимо: deepseek|gemini|openai|grok."

def background_analyze_and_reply(chat_id: int, text: str) -> None:
    try:
        result = analyze_text(text)
        tg_send_message(chat_id, result, reply_to=None)
    except Exception as e:
        logger.exception("Background analyze failed: %s", e)
        tg_send_message(chat_id, "❌ Внутренняя ошибка при анализе. Попробуй позже.", reply_to=None)

# -------------------------
# Routes
# -------------------------
@app.get("/")
def health():
    return {
        "ok": True,
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "ai_engine": AI_ENGINE,
        "db": "postgres" if USE_POSTGRES else "sqlite",
        "deepseek_url": DEEPSEEK_URL,
        "admin_mode": "allowlist" if ADMIN_CHAT_IDS else "open",
    }, 200

@app.post(WEBHOOK_PATH)
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    logger.info("Update: %s", _redact(json.dumps(update)[:1200]))

    message = update.get("message") or update.get("edited_message")
    if not message:
        return "ok", 200

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    msg_id = message.get("message_id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return "ok", 200

    logger.info("Parsed: chat_id=%s user_id=%s text=%r", chat_id, user_id, text)

    if not text:
        tg_send_message(chat_id, "Я принимаю только текст 🙂", reply_to=msg_id)
        return "ok", 200

    # -------- base commands --------
    if text.startswith("/start"):
        tg_send_message(
            chat_id,
            "Привет! Я бот для хранения и анализа отзывов.\n\n"
            "Команды:\n"
            "/help — помощь\n"
            "/myid — user_id/chat_id\n"
            "/engine — текущий AI_ENGINE\n"
            "/addreview ... — добавить отзыв (админы)\n"
            "/listreviews [n=10] [source=yandex|2gis] — список (админы)\n"
            "/review <id> — показать отзыв (админы)\n"
            "/deletereview <id> — удалить (админы)\n"
            "/exportcsv [n=100] — CSV (админы)\n"
            "/analyze <текст> — анализ текста\n"
            "/analyzereview <id> — анализ сохранённого отзыва\n",
            reply_to=msg_id,
        )
        return "ok", 200

    if text.startswith("/help"):
        tg_send_message(
            chat_id,
            "Добавить отзыв:\n"
            "/addreview source=yandex rating=5 url=https://... date=2026-01-31 ТЕКСТ\n"
            "или ответом на сообщение с текстом отзыва: /addreview source=2gis rating=4\n\n"
            "Просмотр:\n"
            "/listreviews n=10\n"
            "/review 12\n"
            "/exportcsv n=100\n\n"
            "Анализ:\n"
            "/analyze текст\n"
            "/analyzereview 12\n\n"
            f"AI_ENGINE сейчас: {AI_ENGINE}",
            reply_to=msg_id,
        )
        return "ok", 200

    if text.startswith("/myid"):
        tg_send_message(chat_id, f"user_id: {user_id}\nchat_id: {chat_id}", reply_to=msg_id)
        return "ok", 200

    if text.startswith("/engine"):
        tg_send_message(
            chat_id,
            f"Текущий AI_ENGINE: {AI_ENGINE}\n"
            f"DeepSeek endpoint: {DEEPSEEK_URL}",
            reply_to=msg_id,
        )
        return "ok", 200

    # -------- admin gate --------
    admin_cmds = ("/addreview", "/listreviews", "/review", "/deletereview", "/exportcsv")
    if any(text.startswith(cmd) for cmd in admin_cmds):
        if not is_admin(int(chat_id)):
            tg_send_message(chat_id, "⛔ Команда доступна только админам.", reply_to=msg_id)
            return "ok", 200

    # -------- review commands --------
    if text.startswith("/addreview"):
        rest = text.replace("/addreview", "", 1).strip()

        reply = message.get("reply_to_message") or {}
        reply_text = (reply.get("text") or "").strip()

        kv, remaining = parse_kv_args(rest)
        review_text = remaining or reply_text

        if not review_text:
            tg_send_message(
                chat_id,
                "Нужно указать текст.\nПример: /addreview source=yandex rating=5 Отличный сервис!",
                reply_to=msg_id,
            )
            return "ok", 200

        source = (kv.get("source") or "manual").lower()
        author = kv.get("author")
        url = kv.get("url")
        published_at = parse_date(kv.get("date") or kv.get("published_at") or "")

        rating: Optional[int] = None
        if "rating" in kv:
            try:
                r = int(kv["rating"])
                if 1 <= r <= 5:
                    rating = r
            except Exception:
                rating = None

        new_id = db_insert_review(
            source=source,
            text=review_text,
            rating=rating,
            author=author,
            url=url,
            published_at=published_at,
            added_by_user_id=int(user_id) if user_id else None,
            added_by_chat_id=int(chat_id) if chat_id else None,
        )

        tg_send_message(chat_id, f"✅ Отзыв сохранён: #{new_id}\nsource={source}", reply_to=msg_id)
        return "ok", 200

    if text.startswith("/listreviews"):
        rest = text.replace("/listreviews", "", 1).strip()
        kv, _ = parse_kv_args(rest)

        limit = 10
        if "n" in kv:
            try:
                limit = max(1, min(50, int(kv["n"])))
            except Exception:
                limit = 10

        source = (kv.get("source") or "").strip().lower() or None
        rows = db_list_reviews(limit=limit, source=source)

        if not rows:
            tg_send_message(chat_id, "Пока нет отзывов в базе.", reply_to=msg_id)
            return "ok", 200

        lines = [f"Последние отзывы (n={len(rows)})" + (f", source={source}" if source else "") + ":"]
        for r in rows:
            lines.append(review_preview(r))
            lines.append("")
        tg_send_message(chat_id, "\n".join(lines).strip(), reply_to=msg_id)
        return "ok", 200

    if text.startswith("/review"):
        parts = text.split()
        if len(parts) < 2:
            tg_send_message(chat_id, "Используй: /review <id>", reply_to=msg_id)
            return "ok", 200
        try:
            rid = int(parts[1])
        except Exception:
            tg_send_message(chat_id, "id должен быть числом.", reply_to=msg_id)
            return "ok", 200

        r = db_get_review(rid)
        if not r:
            tg_send_message(chat_id, f"Отзыв #{rid} не найден.", reply_to=msg_id)
            return "ok", 200

        full = [
            f"Отзыв #{r.get('id')}",
            f"source: {r.get('source')}",
            f"rating: {r.get('rating')}" if r.get("rating") is not None else "rating: —",
            f"author: {r.get('author') or '—'}",
            f"url: {r.get('url') or '—'}",
            f"published_at: {r.get('published_at') or '—'}",
            "",
            (r.get("text") or "").strip(),
        ]
        tg_send_message(chat_id, "\n".join(full), reply_to=msg_id)
        return "ok", 200

    if text.startswith("/deletereview"):
        parts = text.split()
        if len(parts) < 2:
            tg_send_message(chat_id, "Используй: /deletereview <id>", reply_to=msg_id)
            return "ok", 200
        try:
            rid = int(parts[1])
        except Exception:
            tg_send_message(chat_id, "id должен быть числом.", reply_to=msg_id)
            return "ok", 200

        ok = db_delete_review(rid)
        tg_send_message(chat_id, "✅ Удалено." if ok else "Не найдено.", reply_to=msg_id)
        return "ok", 200

    if text.startswith("/exportcsv"):
        rest = text.replace("/exportcsv", "", 1).strip()
        kv, _ = parse_kv_args(rest)

        limit = 100
        if "n" in kv:
            try:
                limit = max(1, min(500, int(kv["n"])))
            except Exception:
                limit = 100

        source = (kv.get("source") or "").strip().lower() or None
        rows = db_list_reviews(limit=limit, source=source)
        if not rows:
            tg_send_message(chat_id, "Нет данных для экспорта.", reply_to=msg_id)
            return "ok", 200

        csv_text = export_csv(rows)
        if len(csv_text) > 3500:
            csv_text = csv_text[:3500] + "\n... (обрезано; при необходимости добавим отправку файлом)\n"
        tg_send_message(chat_id, "CSV:\n" + csv_text, reply_to=msg_id)
        return "ok", 200

    # -------- analysis commands --------
    if text.startswith("/analyze"):
        analyze_text_raw = text.replace("/analyze", "", 1).strip()
        if not analyze_text_raw:
            tg_send_message(chat_id, "Используй: /analyze <текст>", reply_to=msg_id)
            return "ok", 200
        tg_send_message(chat_id, "Принял ✅ Анализирую…", reply_to=msg_id)
        threading.Thread(target=background_analyze_and_reply, args=(chat_id, analyze_text_raw), daemon=True).start()
        return "ok", 200

    if text.startswith("/analyzereview"):
        parts = text.split()
        if len(parts) < 2:
            tg_send_message(chat_id, "Используй: /analyzereview <id>", reply_to=msg_id)
            return "ok", 200
        try:
            rid = int(parts[1])
        except Exception:
            tg_send_message(chat_id, "id должен быть числом.", reply_to=msg_id)
            return "ok", 200

        r = db_get_review(rid)
        if not r:
            tg_send_message(chat_id, f"Отзыв #{rid} не найден.", reply_to=msg_id)
            return "ok", 200

        review_text = (r.get("text") or "").strip()
        tg_send_message(chat_id, f"Принял ✅ Анализирую отзыв #{rid}…", reply_to=msg_id)
        threading.Thread(target=background_analyze_and_reply, args=(chat_id, review_text), daemon=True).start()
        return "ok", 200

    # default
    tg_send_message(
        chat_id,
        "Могу сохранять отзывы и анализировать текст.\n"
        "Добавить: /addreview source=yandex rating=5 Текст...\n"
        "Список: /listreviews n=10\n"
        "Анализ: /analyze Текст",
        reply_to=msg_id,
    )
    return "ok", 200
