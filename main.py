import os
import json
import logging
import threading
import re
from datetime import datetime, timedelta
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
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "15"))

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
# Business context (optional)
# -------------------------
BUSINESS_CONTEXT = (os.getenv("BUSINESS_CONTEXT") or "").strip() or None
BRANCH_CITY = (os.getenv("BRANCH_CITY") or "").strip() or None

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

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")

DEEPSEEK_BASE_URL = (os.getenv("DEEPSEEK_BASE_URL") or "").strip()
if DEEPSEEK_BASE_URL:
    DEEPSEEK_URL = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
else:
    DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")

GROK_URL = os.getenv("GROK_URL", "https://api.x.ai/v1/chat/completions")

# -------------------------
# Cron (weekly report)
# -------------------------
CRON_TOKEN = (os.getenv("CRON_TOKEN") or "").strip()  # required for /cron endpoint security

# -------------------------
# DB (Postgres on Railway or SQLite fallback)
# -------------------------
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")
SQL_PARAM = "%s" if USE_POSTGRES else "?"

if USE_POSTGRES:
    try:
        import psycopg
        from psycopg.types.json import Json
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
    # reviews table (as before)
    if USE_POSTGRES:
        ddl_reviews = """
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
        ddl_analyses = """
        CREATE TABLE IF NOT EXISTS review_analyses (
          id           SERIAL PRIMARY KEY,
          review_id    BIGINT NULL,
          ai_engine    TEXT NOT NULL,
          input_json   JSONB NOT NULL,
          result_json  JSONB NOT NULL,
          created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_review_analyses_created_at ON review_analyses(created_at);
        CREATE INDEX IF NOT EXISTS idx_review_analyses_review_id ON review_analyses(review_id);
        """
    else:
        ddl_reviews = """
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
        ddl_analyses = """
        CREATE TABLE IF NOT EXISTS review_analyses (
          id           INTEGER PRIMARY KEY AUTOINCREMENT,
          review_id    INTEGER NULL,
          ai_engine    TEXT NOT NULL,
          input_json   TEXT NOT NULL,
          result_json  TEXT NOT NULL,
          created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """

    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(ddl_reviews)
        if USE_POSTGRES:
            # ddl_analyses contains multiple statements
            for stmt in [s.strip() for s in ddl_analyses.split(";") if s.strip()]:
                cur.execute(stmt + ";")
        else:
            cur.execute(ddl_analyses)
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
    for key in [GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, GROK_API_KEY, BOT_TOKEN, CRON_TOKEN]:
        if key and key in s:
            s = s.replace(key, "***REDACTED***")
    return s

# -------------------------
# Telegram API helpers
# -------------------------
def tg_api(method: str, payload: Dict[str, Any]) -> Optional[requests.Response]:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        return requests.post(url, json=payload, timeout=TG_TIMEOUT)
    except Exception as e:
        logger.exception("Telegram API exception %s: %s", method, e)
        return None

def tg_send_message(chat_id: int, text: str, reply_to: Optional[int] = None,
                    reply_markup: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    resp = tg_api("sendMessage", payload)
    if resp is not None and resp.status_code != 200:
        logger.error("sendMessage failed: %s", _redact(resp.text[:800]))

def tg_answer_callback_query(callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> None:
    payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    payload["show_alert"] = bool(show_alert)

    resp = tg_api("answerCallbackQuery", payload)
    if resp is not None and resp.status_code != 200:
        logger.error("answerCallbackQuery failed: %s", _redact(resp.text[:400]))

def set_webhook() -> None:
    full_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
    logger.info("Setting webhook: %s", full_url)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json={"url": full_url},
            timeout=TG_TIMEOUT,
        )
        if r.status_code == 429:
            logger.warning("setWebhook got 429 (ignored): %s", _redact(r.text[:400]))
            return
        if r.status_code != 200:
            logger.error("setWebhook failed status=%s body=%s", r.status_code, _redact(r.text[:800]))
        else:
            logger.info("setWebhook OK: %s", _redact(r.text[:400]))
    except Exception as e:
        logger.exception("set_webhook exception: %s", e)

if os.getenv("DISABLE_WEBHOOK_SETUP", "0") != "1":
    set_webhook()

# -------------------------
# DB operations: reviews (existing)
# -------------------------
def parse_kv_args(arg_str: str) -> Tuple[Dict[str, str], str]:
    tokens = arg_str.strip().split()
    kv: Dict[str, str] = {}
    rest_tokens: List[str] = []
    for t in tokens:
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

def db_insert_review(source: str, text: str, rating: Optional[int], author: Optional[str],
                     url: Optional[str], published_at: Optional[datetime],
                     added_by_user_id: Optional[int], added_by_chat_id: Optional[int]) -> int:
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
                (source, rating, author, url,
                 published_at.isoformat() if published_at else None,
                 text, added_by_user_id, added_by_chat_id),
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
        if USE_POSTGRES:
            cols = [d[0] for d in cur.description]
            return [{cols[i]: r[i] for i in range(len(cols))} for r in rows]
        return [dict(r) for r in rows]
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

# -------------------------
# DB operations: analyses
# -------------------------
def db_insert_analysis(review_id: Optional[int], ai_engine: str,
                       input_obj: Dict[str, Any], result_obj: Dict[str, Any]) -> int:
    conn = db_connect()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                f"""
                INSERT INTO review_analyses (review_id, ai_engine, input_json, result_json)
                VALUES ({SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM})
                RETURNING id
                """,
                (review_id, ai_engine, Json(input_obj), Json(result_obj)),
            )
            new_id = cur.fetchone()[0]
        else:
            cur.execute(
                f"""
                INSERT INTO review_analyses (review_id, ai_engine, input_json, result_json)
                VALUES ({SQL_PARAM},{SQL_PARAM},{SQL_PARAM},{SQL_PARAM})
                """,
                (review_id, ai_engine, json.dumps(input_obj, ensure_ascii=False),
                 json.dumps(result_obj, ensure_ascii=False)),
            )
            new_id = cur.lastrowid
        conn.commit()
        return int(new_id)
    finally:
        conn.close()

def db_get_analysis(analysis_id: int) -> Optional[Dict[str, Any]]:
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM review_analyses WHERE id={SQL_PARAM}", (analysis_id,))
        row = cur.fetchone()
        if not row:
            return None
        if USE_POSTGRES:
            cols = [d[0] for d in cur.description]
            obj = {cols[i]: row[i] for i in range(len(cols))}
            return obj
        obj = dict(row)
        # sqlite: parse json fields
        try:
            obj["input_json"] = json.loads(obj.get("input_json") or "{}")
        except Exception:
            obj["input_json"] = {}
        try:
            obj["result_json"] = json.loads(obj.get("result_json") or "{}")
        except Exception:
            obj["result_json"] = {}
        return obj
    finally:
        conn.close()

def db_list_analyses_since(dt: datetime) -> List[Dict[str, Any]]:
    conn = db_connect()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                f"SELECT * FROM review_analyses WHERE created_at >= {SQL_PARAM} ORDER BY id DESC",
                (dt,),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [{cols[i]: r[i] for i in range(len(cols))} for r in rows]
        else:
            cur.execute(
                f"SELECT * FROM review_analyses WHERE created_at >= {SQL_PARAM} ORDER BY id DESC",
                (dt.isoformat(),),
            )
            rows = cur.fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["result_json"] = json.loads(d.get("result_json") or "{}")
                except Exception:
                    d["result_json"] = {}
                out.append(d)
            return out
    finally:
        conn.close()

# -------------------------
# CX System prompt (your contract) - STRICT JSON output
# -------------------------
SYSTEM_PROMPT_CX = r"""
ТЫ — аналитический модуль для Telegram-бота контроля качества сервиса (CX/Service Quality). Бот работает в мессенджере Telegram и получает отзывы клиентов с площадок (сейчас: 2ГИС и Яндекс Карты), с перспективой подключения других источников. Модель ИИ по умолчанию — DeepSeek, но логика должна быть универсальной и независимой от провайдера.

ТВОЯ ЗАДАЧА (строго):
1) Определить площадку (2ГИС / Яндекс) если не указана.
2) Дать ГЛУБОКИЙ анализ отзыва: причины, сбои бизнес-процессов, повторяющиеся проблемы (на уровне конкретных аспектов сервиса), риски, рекомендации и метрики.
3) Проверить отзыв на соответствие правилам площадки (по чек-листу ниже).
4) Сгенерировать публичный ответ на отзыв (разный стиль для позитивного/негативного/сомнительного).
5) Если есть нарушения правил площадки ИЛИ рейтинг < 2 (т.е. 1 звезда) — подготовить жалобу на отзыв:
   - Для 2ГИС: текст жалобы строго ≤ 450 символов (включая пробелы).
   - Для Яндекса: жалоба краткая, по делу (без лимита, но не “простыня”).

ВХОДНЫЕ ДАННЫЕ (используй только то, что передано; НЕ выдумывай факты):
- platform: "2gis" | "yandex" | "unknown" (может отсутствовать)
- rating: 1..5 (может отсутствовать)
- review_text: текст отзыва (обязательно)
- review_date: дата отзыва (может отсутствовать)
- business_context: описание бизнеса/услуг/регламента (может отсутствовать)
- branch/city: филиал/город (может отсутствовать)
- meta: любые доп. поля (язык, имя автора, ссылка, уже существующий ответ и т.п.)

ОБЩИЕ ПРИНЦИПЫ КАЧЕСТВА:
- Никаких выдуманных деталей (заказы, даты, суммы, имена сотрудников), если их нет во входе.
- Если данных мало — формулируй гипотезы + уровень уверенности.
- Цитаты из отзыва делай короткими: до 12 слов.
- Пиши на русском, вежливо, без токсичности.
- Никогда не публикуй и не повторяй персональные данные.
- Не упоминай публично “мы подадим жалобу” и не угрожай автору.

ШАГ 1. ОПРЕДЕЛЕНИЕ ПЛОЩАДКИ (если platform отсутствует/unknown)
Верни platform_detected.value: "2gis" | "yandex" | "unknown", confidence 0..1, signals 2–5.

ШАГ 2. ГЛУБОКИЙ АНАЛИЗ ОТЗЫВА
Сформируй блоки: review_summary, sentiment, emotions, aspects, facts_vs_opinions, pain_points,
root_cause_hypotheses, business_process_flags, risks, recommendations, clarifying_questions.

ШАГ 3. ПРОВЕРКА ПО ПРАВИЛАМ ПЛОЩАДКИ (policy_check)
Верни has_possible_violations, possible_violations (confidence+evidence), notes.

ШАГ 4. ПУБЛИЧНЫЙ ОТВЕТ НА ОТЗЫВ (public_reply)
2–8 предложений, человечно, без канцелярита, без ПДн, без угроз, нейтрально.

ШАГ 5. ЖАЛОБА НА ОТЗЫВ (complaint)
complaint.needed=true если:
a) rating < 2 (если rating отсутствует — не использовать)
ИЛИ b) policy_check.has_possible_violations=true и ключевая причина confidence ≥0.6
ИЛИ c) сильный сигнал “нет признаков реального визита” (как гипотеза)

Для 2ГИС: complaint.text ≤ 450 символов; верни complaint.char_count.

ВЫХОДНОЙ ФОРМАТ (СТРОГО: вернуть ТОЛЬКО JSON, без markdown, без пояснений вокруг)
{
  "platform_detected": {"value":"2gis|yandex|unknown","confidence":0.0,"signals":["..."]},
  "review_summary":"...",
  "sentiment":{"label":"negative|mixed|neutral|positive","score":0},
  "emotions":[{"name":"...","intensity":0}],
  "aspects":[{"name":"...","weight":0,"evidence":["..."]}],
  "facts_vs_opinions":{"facts":["..."],"opinions":["..."]},
  "pain_points":[{"item":"...","severity":"low|medium|high","evidence":["..."]}],
  "root_cause_hypotheses":[{"hypothesis":"...","confidence":0.0,"evidence":["..."],"process_stage":"..."}],
  "business_process_flags":[{"stage":"...","issue":"...","why_it_matters":"..."}],
  "risks":[{"type":"reputation|ops|finance","level":"low|medium|high","why":"..."}],
  "recommendations":[{"priority":"P0|P1|P2","action":"...","expected_effect":"...","effort":"S|M|L","metric":"..."}],
  "clarifying_questions":["..."],
  "policy_check":{
    "has_possible_violations":true,
    "possible_violations":[{"category":"...","confidence":0.0,"evidence":["..."]}],
    "notes":"..."
  },
  "public_reply":{"tone":"...","text":"..."},
  "complaint":{"needed":false,"reasons":["..."],"text":"...","char_count":0}
}

ДОП. ТЕХТРЕБОВАНИЯ:
- JSON валидный: двойные кавычки, без trailing commas.
- Если блок не применим — верни пустые массивы/false, но структура должна сохраняться.
""".strip()

# -------------------------
# AI transport (provider-agnostic)
# -------------------------
def call_deepseek(messages: List[Dict[str, str]]) -> str:
    if not DEEPSEEK_API_KEY:
        return "❌ DEEPSEEK_API_KEY не задан."
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
    logger.info("DeepSeek status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return ""
    msg = choices[0].get("message", {}) or {}
    return (msg.get("content") or "").strip()

def call_openai(messages: List[Dict[str, str]]) -> str:
    if not OPENAI_API_KEY:
        return "❌ OPENAI_API_KEY не задан."
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(OPENAI_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
    logger.info("OpenAI status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return ""
    return ((choices[0].get("message", {}) or {}).get("content") or "").strip()

def call_gemini(messages: List[Dict[str, str]]) -> str:
    # Gemini expects a single user prompt; we concatenate system+user
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY не задан."
    combined = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            combined.append("ИНСТРУКЦИИ:\n" + content)
        elif role == "user":
            combined.append("ВХОД:\n" + content)
        else:
            combined.append(content)
    prompt = "\n\n".join(combined).strip()

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
    }
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
        return ""
    parts = (candidates[0].get("content", {}) or {}).get("parts", []) or []
    return ((parts[0].get("text") if parts else "") or "").strip()

def call_grok(messages: List[Dict[str, str]]) -> str:
    if not GROK_API_KEY:
        return "❌ GROK_API_KEY (или XAI_API_KEY) не задан."
    payload = {
        "model": GROK_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(GROK_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
    logger.info("Grok status=%s body=%s", resp.status_code, _redact(resp.text[:900]))
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return ""
    return ((choices[0].get("message", {}) or {}).get("content") or "").strip()

def ai_chat(messages: List[Dict[str, str]]) -> str:
    engine = (AI_ENGINE or "deepseek").lower()
    if engine in ("deepseek", "deep_seek", "ds"):
        return call_deepseek(messages)
    if engine in ("openai", "gpt", "chatgpt"):
        return call_openai(messages)
    if engine == "gemini":
        return call_gemini(messages)
    if engine in ("grok", "xai"):
        return call_grok(messages)
    return ""

# -------------------------
# JSON extraction + minimal validation
# -------------------------
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)

def extract_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.strip()
    # Fast path
    if t.startswith("{") and t.endswith("}"):
        return t
    # Try greedy match { ... }
    m = _JSON_OBJ_RE.search(t)
    if m:
        return m.group(0).strip()
    return None

def ensure_2gis_complaint_limit(obj: Dict[str, Any]) -> Dict[str, Any]:
    try:
        platform = (((obj.get("platform_detected") or {}).get("value")) or "unknown").lower()
        complaint = obj.get("complaint") or {}
        text = (complaint.get("text") or "")
        if platform == "2gis" and text:
            if len(text) > 450:
                complaint["text"] = text[:450].rstrip()
            complaint["char_count"] = len(complaint.get("text") or "")
            obj["complaint"] = complaint
    except Exception:
        pass
    return obj

def minimal_shape_fix(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure keys exist with sane defaults (to keep downstream stable)
    def dflt(k, v):
        if k not in obj or obj[k] is None:
            obj[k] = v

    dflt("platform_detected", {"value": "unknown", "confidence": 0.0, "signals": []})
    dflt("review_summary", "")
    dflt("sentiment", {"label": "neutral", "score": 0})
    dflt("emotions", [])
    dflt("aspects", [])
    dflt("facts_vs_opinions", {"facts": [], "opinions": []})
    dflt("pain_points", [])
    dflt("root_cause_hypotheses", [])
    dflt("business_process_flags", [])
    dflt("risks", [])
    dflt("recommendations", [])
    dflt("clarifying_questions", [])
    dflt("policy_check", {"has_possible_violations": False, "possible_violations": [], "notes": ""})
    dflt("public_reply", {"tone": "", "text": ""})
    dflt("complaint", {"needed": False, "reasons": [], "text": "", "char_count": 0})
    return obj

# -------------------------
# Build CX request
# -------------------------
def build_cx_input(
    review_text: str,
    platform: str = "unknown",
    rating: Optional[int] = None,
    review_date: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "platform": platform or "unknown",
        "rating": rating,
        "review_text": review_text,
        "review_date": review_date,
        "business_context": BUSINESS_CONTEXT,
        "branch/city": BRANCH_CITY,
        "meta": meta or {},
    }

def cx_analyze(input_obj: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Returns: (parsed_json_or_none, raw_text)
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_CX},
        {"role": "user", "content": json.dumps(input_obj, ensure_ascii=False)},
    ]
    raw = ""
    try:
        raw = ai_chat(messages)
    except Exception as e:
        logger.exception("AI transport exception: %s", e)
        return None, raw

    raw = (raw or "").strip()
    json_text = extract_json_object(raw)
    if not json_text:
        return None, raw

    try:
        obj = json.loads(json_text)
        if not isinstance(obj, dict):
            return None, raw
        obj = minimal_shape_fix(obj)
        obj = ensure_2gis_complaint_limit(obj)
        return obj, raw
    except Exception as e:
        logger.warning("JSON parse failed: %s", e)
        return None, raw

# -------------------------
# Telegram formatting + inline keyboard
# -------------------------
def analysis_keyboard(analysis_id: int) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✍️ Сформировать ответ", "callback_data": f"reply:{analysis_id}"},
                {"text": "⚠️ Жалоба", "callback_data": f"complaint:{analysis_id}"},
            ],
            [
                {"text": "📌 Ответ + жалоба", "callback_data": f"both:{analysis_id}"},
                {"text": "🧾 JSON", "callback_data": f"json:{analysis_id}"},
            ],
        ]
    }

def safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def format_analysis_summary(obj: Dict[str, Any], analysis_id: int) -> str:
    platform = safe_get(obj, ["platform_detected", "value"], "unknown")
    pconf = safe_get(obj, ["platform_detected", "confidence"], 0.0)
    sentiment = safe_get(obj, ["sentiment", "label"], "neutral")
    sscore = safe_get(obj, ["sentiment", "score"], 0)

    summary = (obj.get("review_summary") or "").strip()
    if len(summary) > 500:
        summary = summary[:500] + "…"

    # Top aspects
    aspects = obj.get("aspects") or []
    top_aspects = []
    if isinstance(aspects, list):
        try:
            aspects_sorted = sorted(
                [a for a in aspects if isinstance(a, dict)],
                key=lambda x: int(x.get("weight") or 0),
                reverse=True,
            )
            for a in aspects_sorted[:3]:
                name = (a.get("name") or "").strip()
                w = a.get("weight")
                if name:
                    top_aspects.append(f"{name}({w})")
        except Exception:
            pass

    complaint_needed = bool(safe_get(obj, ["complaint", "needed"], False))
    policy_bad = bool(safe_get(obj, ["policy_check", "has_possible_violations"], False))

    flags = []
    if complaint_needed:
        flags.append("жалоба: да")
    if policy_bad:
        flags.append("возможные нарушения: да")

    head = [
        f"✅ Анализ готов. ID: {analysis_id}",
        f"Площадка: {platform} (conf={pconf:.2f})",
        f"Тональность: {sentiment} ({sscore})",
    ]
    if top_aspects:
        head.append("Топ-аспекты: " + ", ".join(top_aspects))
    if flags:
        head.append("Флаги: " + ", ".join(flags))

    return "\n".join(head) + "\n\n" + summary

def format_public_reply(obj: Dict[str, Any]) -> str:
    txt = (safe_get(obj, ["public_reply", "text"], "") or "").strip()
    if not txt:
        return "Не удалось сформировать публичный ответ (пусто)."
    return "Публичный ответ:\n\n" + txt

def format_complaint(obj: Dict[str, Any]) -> str:
    needed = bool(safe_get(obj, ["complaint", "needed"], False))
    text = (safe_get(obj, ["complaint", "text"], "") or "").strip()
    char_count = int(safe_get(obj, ["complaint", "char_count"], 0) or 0)
    reasons = safe_get(obj, ["complaint", "reasons"], []) or []
    if not needed:
        return "Жалоба не требуется по текущей оценке."
    out = ["Жалоба (черновик):"]
    if reasons and isinstance(reasons, list):
        out.append("Причины: " + "; ".join([str(x) for x in reasons[:3]]))
    if text:
        out.append("")
        out.append(text)
    if char_count:
        out.append("")
        out.append(f"Длина: {char_count} символов")
    return "\n".join(out).strip()

def format_json_for_chat(obj: Dict[str, Any]) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), indent=2)
    if len(raw) > 3500:
        raw = raw[:3500] + "\n... (обрезано)\n"
    return raw

# -------------------------
# Weekly report
# -------------------------
def build_weekly_report(days: int = 7) -> str:
    since = datetime.utcnow() - timedelta(days=days)
    rows = db_list_analyses_since(since)

    # Normalize rows' result_json for postgres (already dict) / sqlite (dict after parsing)
    results: List[Dict[str, Any]] = []
    for r in rows:
        rj = r.get("result_json")
        if isinstance(rj, dict):
            results.append(rj)

    total = len(results)
    if total == 0:
        return f"Еженедельный отчёт (за {days} дн.): анализов нет."

    # Sentiment distribution
    sent_count: Dict[str, int] = {"positive": 0, "neutral": 0, "mixed": 0, "negative": 0}
    complaint_needed = 0
    policy_flags = 0

    aspect_sum: Dict[str, int] = {}
    pain_sum: Dict[str, int] = {}
    viol_sum: Dict[str, int] = {}

    for obj in results:
        label = (safe_get(obj, ["sentiment", "label"], "neutral") or "neutral").lower()
        if label not in sent_count:
            sent_count[label] = 0
        sent_count[label] += 1

        if bool(safe_get(obj, ["complaint", "needed"], False)):
            complaint_needed += 1
        if bool(safe_get(obj, ["policy_check", "has_possible_violations"], False)):
            policy_flags += 1

        aspects = obj.get("aspects") or []
        if isinstance(aspects, list):
            for a in aspects:
                if not isinstance(a, dict):
                    continue
                name = (a.get("name") or "").strip().lower()
                if not name:
                    continue
                w = int(a.get("weight") or 0)
                aspect_sum[name] = aspect_sum.get(name, 0) + w

        pains = obj.get("pain_points") or []
        if isinstance(pains, list):
            for p in pains:
                if not isinstance(p, dict):
                    continue
                item = (p.get("item") or "").strip().lower()
                if not item:
                    continue
                sev = (p.get("severity") or "low").lower()
                # weighted severity
                score = 1 if sev == "low" else 2 if sev == "medium" else 3
                pain_sum[item] = pain_sum.get(item, 0) + score

        viols = safe_get(obj, ["policy_check", "possible_violations"], []) or []
        if isinstance(viols, list):
            for v in viols:
                if not isinstance(v, dict):
                    continue
                cat = (v.get("category") or "").strip().lower()
                if not cat:
                    continue
                conf = float(v.get("confidence") or 0.0)
                if conf >= 0.6:
                    viol_sum[cat] = viol_sum.get(cat, 0) + 1

    def top_items(d: Dict[str, int], n: int = 5) -> List[str]:
        items = sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]
        return [f"{k} ({v})" for k, v in items]

    lines = []
    lines.append(f"Еженедельный отчёт (за {days} дн.)")
    lines.append(f"Всего анализов: {total}")
    lines.append("")
    lines.append("Тональность:")
    lines.append(f"  позитив: {sent_count.get('positive', 0)}")
    lines.append(f"  нейтр:   {sent_count.get('neutral', 0)}")
    lines.append(f"  микс:    {sent_count.get('mixed', 0)}")
    lines.append(f"  негатив: {sent_count.get('negative', 0)}")
    lines.append("")
    lines.append(f"Жалоба нужна (complaint.needed=true): {complaint_needed}")
    lines.append(f"Есть возможные нарушения правил: {policy_flags}")
    lines.append("")
    ta = top_items(aspect_sum, 6)
    if ta:
        lines.append("Топ-аспекты (сумма весов):")
        for s in ta:
            lines.append("  - " + s)
        lines.append("")
    tp = top_items(pain_sum, 6)
    if tp:
        lines.append("Топ pain-points (вес по severity):")
        for s in tp:
            lines.append("  - " + s)
        lines.append("")
    tv = top_items(viol_sum, 6)
    if tv:
        lines.append("Топ нарушений (confidence≥0.6):")
        for s in tv:
            lines.append("  - " + s)

    msg = "\n".join(lines).strip()
    if len(msg) > 3800:
        msg = msg[:3800] + "\n... (обрезано)\n"
    return msg

def send_weekly_report(days: int = 7) -> None:
    text = build_weekly_report(days=days)
    # Send to all admins in allowlist mode; if allowlist empty, do nothing to avoid spamming random users
    if not ADMIN_CHAT_IDS:
        logger.warning("Weekly report not sent: ADMIN_CHAT_IDS empty.")
        return
    for cid in ADMIN_CHAT_IDS:
        tg_send_message(cid, text)

# -------------------------
# Background workers
# -------------------------
def background_analyze(chat_id: int, reply_to: int,
                      input_obj: Dict[str, Any], review_id: Optional[int]) -> None:
    try:
        parsed, raw = cx_analyze(input_obj)
        if not parsed:
            # store an error result for traceability
            err_obj = minimal_shape_fix({
                "platform_detected": {"value": "unknown", "confidence": 0.0, "signals": []},
                "review_summary": "",
                "sentiment": {"label": "neutral", "score": 0},
                "policy_check": {"has_possible_violations": False, "possible_violations": [], "notes": "analysis_failed"},
                "public_reply": {"tone": "", "text": ""},
                "complaint": {"needed": False, "reasons": [], "text": "", "char_count": 0},
                "_error": "AI returned invalid JSON",
                "_raw": (raw or "")[:2000],
            })
            analysis_id = db_insert_analysis(review_id, AI_ENGINE, input_obj, err_obj)
            tg_send_message(
                chat_id,
                f"❌ Не удалось получить валидный JSON от ИИ. Анализ сохранён с ошибкой. ID: {analysis_id}\n"
                f"Попробуй ещё раз или сменить AI_ENGINE.",
                reply_to=reply_to,
                reply_markup=analysis_keyboard(analysis_id),
            )
            return

        analysis_id = db_insert_analysis(review_id, AI_ENGINE, input_obj, parsed)

        msg = format_analysis_summary(parsed, analysis_id)
        tg_send_message(chat_id, msg, reply_to=reply_to, reply_markup=analysis_keyboard(analysis_id))

    except Exception as e:
        logger.exception("background_analyze failed: %s", e)
        tg_send_message(chat_id, "❌ Внутренняя ошибка анализа. Попробуй позже.", reply_to=reply_to)

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
        "has_cron_token": bool(CRON_TOKEN),
    }, 200

@app.get("/cron/weekly")
def cron_weekly():
    token = (request.args.get("token") or "").strip()
    days_s = (request.args.get("days") or "7").strip()
    if not CRON_TOKEN or token != CRON_TOKEN:
        return {"ok": False, "error": "unauthorized"}, 401
    try:
        days = int(days_s)
        days = max(1, min(30, days))
    except Exception:
        days = 7
    send_weekly_report(days=days)
    return {"ok": True, "sent_to": ADMIN_CHAT_IDS, "days": days}, 200

@app.post(WEBHOOK_PATH)
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    logger.info("Update: %s", _redact(json.dumps(update)[:1400]))

    # Handle inline button clicks
    if "callback_query" in update:
        cq = update.get("callback_query") or {}
        cq_id = cq.get("id")
        data = (cq.get("data") or "").strip()
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")

        if cq_id:
            tg_answer_callback_query(cq_id)

        if not chat_id or not data:
            return "ok", 200

        # Expected: action:analysis_id
        try:
            action, sid = data.split(":", 1)
            analysis_id = int(sid)
        except Exception:
            tg_send_message(int(chat_id), "Некорректная кнопка/данные.", reply_to=None)
            return "ok", 200

        row = db_get_analysis(analysis_id)
        if not row:
            tg_send_message(int(chat_id), f"Анализ #{analysis_id} не найден.", reply_to=None)
            return "ok", 200

        result_obj = row.get("result_json")
        # Postgres returns dict for JSONB; SQLite parsed earlier
        if not isinstance(result_obj, dict):
            try:
                result_obj = json.loads(result_obj or "{}")
            except Exception:
                result_obj = {}

        if action == "reply":
            tg_send_message(int(chat_id), format_public_reply(result_obj))
        elif action == "complaint":
            tg_send_message(int(chat_id), format_complaint(result_obj))
        elif action == "both":
            tg_send_message(int(chat_id), format_public_reply(result_obj))
            tg_send_message(int(chat_id), format_complaint(result_obj))
        elif action == "json":
            tg_send_message(int(chat_id), format_json_for_chat(result_obj))
        else:
            tg_send_message(int(chat_id), "Неизвестное действие.", reply_to=None)

        return "ok", 200

    # Handle normal messages
    message = update.get("message") or update.get("edited_message")
    if not message:
        return "ok", 200

    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    msg_id = message.get("message_id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return "ok", 200

    if not text:
        tg_send_message(int(chat_id), "Я принимаю только текст 🙂", reply_to=msg_id)
        return "ok", 200

    logger.info("Parsed: chat_id=%s user_id=%s text=%r", chat_id, user_id, text)

    # Base commands
    if text.startswith("/start"):
        tg_send_message(
            int(chat_id),
            "Привет! Я бот для хранения и анализа отзывов.\n\n"
            "Команды:\n"
            "/help — помощь\n"
            "/myid — ваш user_id/chat_id\n"
            "/engine — текущий AI_ENGINE\n"
            "/analyze <текст> — анализ текста (с кнопками)\n"
            "/analyzereview <id> — анализ сохранённого отзыва\n"
            "/weeklyreport [days=7] — отчёт (админы)\n\n"
            "Отзывы (админы):\n"
            "/addreview source=yandex|2gis rating=1..5 url=https://... date=YYYY-MM-DD Текст...\n"
            "/listreviews n=10 [source=yandex|2gis]\n"
            "/review <id>\n"
            "/deletereview <id>\n",
            reply_to=msg_id,
        )
        return "ok", 200

    if text.startswith("/help"):
        tg_send_message(
            int(chat_id),
            "Анализ:\n"
            "/analyze <текст>\n"
            "/analyzereview <id>\n\n"
            "После анализа будут кнопки: Ответ / Жалоба / Оба / JSON.\n\n"
            "Отзывы (админы):\n"
            "/addreview source=yandex rating=5 Отличный сервис!\n"
            "/listreviews n=10\n"
            "/review 12\n"
            "/deletereview 12\n\n"
            "Отчёт (админы):\n"
            "/weeklyreport days=7\n\n"
            f"AI_ENGINE сейчас: {AI_ENGINE}",
            reply_to=msg_id,
        )
        return "ok", 200

    if text.startswith("/myid"):
        tg_send_message(int(chat_id), f"user_id: {user_id}\nchat_id: {chat_id}", reply_to=msg_id)
        return "ok", 200

    if text.startswith("/engine"):
        tg_send_message(
            int(chat_id),
            f"Текущий AI_ENGINE: {AI_ENGINE}\nDeepSeek endpoint: {DEEPSEEK_URL}",
            reply_to=msg_id,
        )
        return "ok", 200

    # Admin gate
    admin_cmds = ("/addreview", "/listreviews", "/review", "/deletereview", "/weeklyreport")
    if any(text.startswith(cmd) for cmd in admin_cmds):
        if not is_admin(int(chat_id)):
            tg_send_message(int(chat_id), "⛔ Команда доступна только админам.", reply_to=msg_id)
            return "ok", 200

    # Review commands (admin)
    if text.startswith("/addreview"):
        rest = text.replace("/addreview", "", 1).strip()
        reply = message.get("reply_to_message") or {}
        reply_text = (reply.get("text") or "").strip()

        kv, remaining = parse_kv_args(rest)
        review_text = remaining or reply_text
        if not review_text:
            tg_send_message(
                int(chat_id),
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
        tg_send_message(int(chat_id), f"✅ Отзыв сохранён: #{new_id}\nsource={source}", reply_to=msg_id)
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
            tg_send_message(int(chat_id), "Пока нет отзывов в базе.", reply_to=msg_id)
            return "ok", 200

        lines = [f"Последние отзывы (n={len(rows)})" + (f", source={source}" if source else "") + ":"]
        for r in rows:
            lines.append(review_preview(r))
            lines.append("")
        tg_send_message(int(chat_id), "\n".join(lines).strip(), reply_to=msg_id)
        return "ok", 200

    if text.startswith("/review"):
        parts = text.split()
        if len(parts) < 2:
            tg_send_message(int(chat_id), "Используй: /review <id>", reply_to=msg_id)
            return "ok", 200
        try:
            rid = int(parts[1])
        except Exception:
            tg_send_message(int(chat_id), "id должен быть числом.", reply_to=msg_id)
            return "ok", 200

        r = db_get_review(rid)
        if not r:
            tg_send_message(int(chat_id), f"Отзыв #{rid} не найден.", reply_to=msg_id)
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
        tg_send_message(int(chat_id), "\n".join(full), reply_to=msg_id)
        return "ok", 200

    if text.startswith("/deletereview"):
        parts = text.split()
        if len(parts) < 2:
            tg_send_message(int(chat_id), "Используй: /deletereview <id>", reply_to=msg_id)
            return "ok", 200
        try:
            rid = int(parts[1])
        except Exception:
            tg_send_message(int(chat_id), "id должен быть числом.", reply_to=msg_id)
            return "ok", 200

        ok = db_delete_review(rid)
        tg_send_message(int(chat_id), "✅ Удалено." if ok else "Не найдено.", reply_to=msg_id)
        return "ok", 200

    # Weekly report (admin)
    if text.startswith("/weeklyreport"):
        rest = text.replace("/weeklyreport", "", 1).strip()
        kv, _ = parse_kv_args(rest)
        days = 7
        if "days" in kv:
            try:
                days = max(1, min(30, int(kv["days"])))
            except Exception:
                days = 7
        tg_send_message(int(chat_id), build_weekly_report(days=days), reply_to=msg_id)
        return "ok", 200

    # Analysis commands (anyone)
    if text.startswith("/analyze"):
        analyze_text = text.replace("/analyze", "", 1).strip()
        if not analyze_text:
            tg_send_message(int(chat_id), "Используй: /analyze <текст>", reply_to=msg_id)
            return "ok", 200

        tg_send_message(int(chat_id), "Принял ✅ Готовлю анализ…", reply_to=msg_id)

        input_obj = build_cx_input(
            review_text=analyze_text,
            platform="unknown",
            rating=None,
            review_date=None,
            meta={"via": "command_analyze"},
        )
        threading.Thread(
            target=background_analyze,
            args=(int(chat_id), int(msg_id), input_obj, None),
            daemon=True,
        ).start()
        return "ok", 200

    if text.startswith("/analyzereview"):
        parts = text.split()
        if len(parts) < 2:
            tg_send_message(int(chat_id), "Используй: /analyzereview <id>", reply_to=msg_id)
            return "ok", 200
        try:
            rid = int(parts[1])
        except Exception:
            tg_send_message(int(chat_id), "id должен быть числом.", reply_to=msg_id)
            return "ok", 200

        r = db_get_review(rid)
        if not r:
            tg_send_message(int(chat_id), f"Отзыв #{rid} не найден.", reply_to=msg_id)
            return "ok", 200

        # map source -> platform if possible
        source = (r.get("source") or "unknown").lower()
        platform = "unknown"
        if "2gis" in source or "2гис" in source:
            platform = "2gis"
        elif "yandex" in source or "янд" in source:
            platform = "yandex"

        rating = r.get("rating")
        try:
            rating = int(rating) if rating is not None else None
        except Exception:
            rating = None

        published_at = r.get("published_at")
        review_date = None
        if published_at:
            review_date = str(published_at)

        meta = {
            "via": "saved_review",
            "author": r.get("author"),
            "url": r.get("url"),
            "review_id": rid,
            "source": source,
        }

        tg_send_message(int(chat_id), f"Принял ✅ Анализирую отзыв #{rid}…", reply_to=msg_id)

        input_obj = build_cx_input(
            review_text=(r.get("text") or "").strip(),
            platform=platform,
            rating=rating,
            review_date=review_date,
            meta=meta,
        )
        threading.Thread(
            target=background_analyze,
            args=(int(chat_id), int(msg_id), input_obj, rid),
            daemon=True,
        ).start()
        return "ok", 200

    # default
    tg_send_message(
        int(chat_id),
        "Команды:\n"
        "/analyze <текст> — анализ (с кнопками)\n"
        "/analyzereview <id> — анализ сохранённого отзыва\n"
        "/help — помощь",
        reply_to=msg_id,
    )
    return "ok", 200
