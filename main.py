import os
import re
import json
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, request, jsonify

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("telegram_reviews_bot")

# -----------------------------
# Optional OpenAI SDK (highly recommended for DeepSeek gateways)
# -----------------------------
try:
    from openai import OpenAI  # type: ignore
    OPENAI_SDK_AVAILABLE = True
except Exception:
    OPENAI_SDK_AVAILABLE = False

# -----------------------------
# Env / Config
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN (or TELEGRAM_TOKEN) is required")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is required (e.g. https://xxx.up.railway.app)")

# secret part of webhook path (hook123)
BOT_PATH_SECRET = os.getenv("BOT_PATH_SECRET", "").strip()
if not BOT_PATH_SECRET:
    # fallback: last 12 chars of token (not ideal, but prevents 404)
    BOT_PATH_SECRET = TELEGRAM_BOT_TOKEN[-12:]
    logger.warning("BOT_PATH_SECRET not set. Using fallback based on token suffix.")

WEBHOOK_PATH = f"/webhook/{BOT_PATH_SECRET}"
WEBHOOK_FULL_URL = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"

PORT = int(os.getenv("PORT", "8000"))

AI_ENGINE = (os.getenv("AI_ENGINE") or "deepseek").strip().lower()  # default deepseek
CX_PROMPT_MODE = (os.getenv("CX_PROMPT_MODE") or "full").strip().lower()  # full|lite

# DeepSeek / Artemox
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_KEY")
DEEPSEEK_BASE_URL = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.artemox.com/v1").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
DEEPSEEK_URL = f"{DEEPSEEK_BASE_URL}/chat/completions"

# OpenAI (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

# Gemini (optional)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Grok/xAI placeholder (optional)
GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_BASE_URL = (os.getenv("GROK_BASE_URL") or "").rstrip("/")
GROK_MODEL = os.getenv("GROK_MODEL") or "grok-beta"

# Admin allowlist: comma-separated chat_ids
REPORT_CHAT_IDS = os.getenv("REPORT_CHAT_IDS", "").strip()
ADMIN_CHAT_IDS: List[int] = []
if REPORT_CHAT_IDS:
    for x in REPORT_CHAT_IDS.split(","):
        x = x.strip()
        if x:
            try:
                ADMIN_CHAT_IDS.append(int(x))
            except Exception:
                pass

ADMIN_MODE = "allowlist" if ADMIN_CHAT_IDS else "open"

# DB
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL_INTERNAL")

# Cron token (protect /cron/weekly)
CRON_TOKEN = os.getenv("CRON_TOKEN", "").strip()

# Diagnostics token (optional) - if set, /diag/ai requires ?token=
DIAG_TOKEN = os.getenv("DIAG_TOKEN", "").strip()

# Timeouts
TG_TIMEOUT = float(os.getenv("TG_TIMEOUT", "10"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "40"))

# -----------------------------
# Flask
# -----------------------------
app = Flask(__name__)

# -----------------------------
# Telegram helpers
# -----------------------------
def tg_api(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

def send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(tg_api("sendMessage"), json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("sendMessage failed status=%s body=%s", r.status_code, _redact(r.text[:900]))
    except Exception as e:
        logger.exception("sendMessage exception: %s", e)

def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False) -> None:
    payload = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
    try:
        r = requests.post(tg_api("answerCallbackQuery"), json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("answerCallbackQuery failed status=%s body=%s", r.status_code, _redact(r.text[:500]))
    except Exception:
        logger.exception("answerCallbackQuery exception")

def _is_admin(chat_id: Optional[int]) -> bool:
    if chat_id is None:
        return False
    if not ADMIN_CHAT_IDS:
        return True  # open mode
    return chat_id in ADMIN_CHAT_IDS

# -----------------------------
# Webhook setup (per process)
# -----------------------------
_webhook_set_once = False
_webhook_lock = threading.Lock()

def set_webhook_once() -> None:
    global _webhook_set_once
    with _webhook_lock:
        if _webhook_set_once:
            return
        _webhook_set_once = True

    try:
        logger.info("Setting webhook: %s", WEBHOOK_FULL_URL)
        r = requests.get(
            tg_api("setWebhook"),
            params={"url": WEBHOOK_FULL_URL},
            timeout=TG_TIMEOUT,
        )
        # 429 часто бывает из-за нескольких воркеров — не критично
        if r.status_code == 200:
            logger.info("setWebhook OK: %s", _redact(r.text[:500]))
        elif r.status_code == 429:
            logger.warning("setWebhook got 429 (ignored): %s", _redact(r.text[:500]))
        else:
            logger.error("setWebhook failed status=%s body=%s", r.status_code, _redact(r.text[:900]))
    except Exception:
        logger.exception("setWebhook exception")

# -----------------------------
# DB layer (psycopg v3 recommended)
# -----------------------------
DB_OK = False

def _db_connect():
    """
    Returns psycopg connection, or None if not configured.
    """
    if not DATABASE_URL:
        return None
    try:
        import psycopg  # type: ignore
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        return conn
    except Exception as e:
        logger.error("DB connect failed: %s", e)
        return None

def db_init() -> None:
    global DB_OK
    conn = _db_connect()
    if not conn:
        DB_OK = False
        logger.warning("DB init skipped (DATABASE_URL not set or connect failed)")
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id BIGSERIAL PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'manual',
                    rating INT,
                    review_text TEXT NOT NULL,
                    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS review_analyses (
                    id BIGSERIAL PRIMARY KEY,
                    review_id BIGINT,
                    platform TEXT,
                    rating INT,
                    review_text TEXT NOT NULL,
                    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    error TEXT,
                    model TEXT,
                    engine TEXT,
                    created_by BIGINT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
        DB_OK = True
        logger.info("DB init OK (postgres=True)")
    except Exception:
        DB_OK = False
        logger.exception("DB init failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_insert_review(source: str, rating: Optional[int], review_text: str, meta: dict) -> Optional[int]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reviews (source, rating, review_text, meta) VALUES (%s, %s, %s, %s) RETURNING id",
                (source, rating, review_text, json.dumps(meta, ensure_ascii=False)),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception:
        logger.exception("db_insert_review failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_get_review(review_id: int) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, source, rating, review_text, meta, created_at FROM reviews WHERE id=%s", (review_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": int(row[0]),
                "source": row[1],
                "rating": row[2],
                "review_text": row[3],
                "meta": row[4] if isinstance(row[4], dict) else (json.loads(row[4]) if row[4] else {}),
                "created_at": str(row[5]),
            }
    except Exception:
        logger.exception("db_get_review failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_list_reviews(n: int = 10, source: Optional[str] = None) -> List[dict]:
    conn = _db_connect()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            if source:
                cur.execute(
                    "SELECT id, source, rating, left(review_text, 140), created_at FROM reviews WHERE source=%s ORDER BY id DESC LIMIT %s",
                    (source, n),
                )
            else:
                cur.execute(
                    "SELECT id, source, rating, left(review_text, 140), created_at FROM reviews ORDER BY id DESC LIMIT %s",
                    (n,),
                )
            rows = cur.fetchall() or []
            out = []
            for r in rows:
                out.append({
                    "id": int(r[0]),
                    "source": r[1],
                    "rating": r[2],
                    "preview": r[3],
                    "created_at": str(r[4]),
                })
            return out
    except Exception:
        logger.exception("db_list_reviews failed")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_delete_review(review_id: int) -> bool:
    conn = _db_connect()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM reviews WHERE id=%s", (review_id,))
        return True
    except Exception:
        logger.exception("db_delete_review failed")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_insert_analysis(
    review_id: Optional[int],
    platform: Optional[str],
    rating: Optional[int],
    review_text: str,
    result_json: dict,
    error: Optional[str],
    model: str,
    engine: str,
    created_by: Optional[int],
) -> Optional[int]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_analyses
                (review_id, platform, rating, review_text, result_json, error, model, engine, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    review_id,
                    platform,
                    rating,
                    review_text,
                    json.dumps(result_json, ensure_ascii=False),
                    error,
                    model,
                    engine,
                    created_by,
                ),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception:
        logger.exception("db_insert_analysis failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_get_analysis(analysis_id: int) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, review_id, platform, rating, review_text, result_json, error, model, engine, created_by, created_at FROM review_analyses WHERE id=%s",
                (analysis_id,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return {
                "id": int(r[0]),
                "review_id": r[1],
                "platform": r[2],
                "rating": r[3],
                "review_text": r[4],
                "result_json": r[5] if isinstance(r[5], dict) else (json.loads(r[5]) if r[5] else {}),
                "error": r[6],
                "model": r[7],
                "engine": r[8],
                "created_by": r[9],
                "created_at": str(r[10]),
            }
    except Exception:
        logger.exception("db_get_analysis failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_weekly_summary(days: int = 7) -> dict:
    conn = _db_connect()
    if not conn:
        return {"ok": False, "error": "DB not configured"}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  count(*) as total,
                  count(*) FILTER (WHERE error IS NOT NULL) as with_error
                FROM review_analyses
                WHERE created_at >= now() - (%s || ' days')::interval
                """,
                (days,),
            )
            row = cur.fetchone() or (0, 0)
            total = int(row[0])
            with_error = int(row[1])

            # sentiment distribution (best-effort from stored json)
            cur.execute(
                """
                SELECT result_json
                FROM review_analyses
                WHERE created_at >= now() - (%s || ' days')::interval
                """,
                (days,),
            )
            rows = cur.fetchall() or []
            sentiments = {"negative": 0, "mixed": 0, "neutral": 0, "positive": 0, "unknown": 0}
            complaints_needed = 0
            aspects_counter: Dict[str, int] = {}

            for (rj,) in rows:
                obj = rj if isinstance(rj, dict) else (json.loads(rj) if rj else {})
                s = (obj.get("sentiment") or {}).get("label") or "unknown"
                if s not in sentiments:
                    s = "unknown"
                sentiments[s] += 1

                comp = (obj.get("complaint") or {})
                if comp.get("needed") is True:
                    complaints_needed += 1

                aspects = obj.get("aspects") or []
                if isinstance(aspects, list):
                    for a in aspects:
                        name = (a or {}).get("name")
                        if name and isinstance(name, str):
                            key = name.strip().lower()
                            aspects_counter[key] = aspects_counter.get(key, 0) + 1

            top_aspects = sorted(aspects_counter.items(), key=lambda x: x[1], reverse=True)[:10]

            return {
                "ok": True,
                "days": days,
                "total": total,
                "with_error": with_error,
                "sentiments": sentiments,
                "complaints_needed": complaints_needed,
                "top_aspects": top_aspects,
            }
    except Exception:
        logger.exception("db_weekly_summary failed")
        return {"ok": False, "error": "db_weekly_summary failed"}
    finally:
        try:
            conn.close()
        except Exception:
            pass

# -----------------------------
# Prompt (FULL + LITE)
# -----------------------------
CX_PROMPT_FULL = r"""
ТЫ — аналитический модуль для Telegram-бота контроля качества сервиса (CX/Service Quality). Бот получает отзывы клиентов с площадок (сейчас: 2ГИС и Яндекс Карты), с перспективой подключения других источников. Модель ИИ по умолчанию — DEEPSEEK, но логика должна быть универсальной и независимой от провайдера.

ТВОЯ ЗАДАЧА (строго):
1) Определить площадку (2ГИС / Яндекс) если не указана.
2) Дать ГЛУБОКИЙ анализ отзыва: причины, сбои бизнес-процессов, повторяющиеся проблемы (на уровне конкретных аспектов сервиса), риски, рекомендации и метрики.
3) Проверить отзыв на соответствие правилам площадки (по чек-листу ниже).
4) Сгенерировать публичный ответ на отзыв (разный стиль для позитивного/негативного/сомнительного).
5) Если есть нарушения правил площадки ИЛИ рейтинг < 2 (т.е. 1 звезда) — подготовить жалобу на отзыв:
   - Для 2ГИС: текст жалобы строго ≤ 450 символов (включая пробелы).
   - Для Яндекса: жалоба краткая, по делу.

ВХОДНЫЕ ДАННЫЕ (используй только то, что передано; НЕ выдумывай факты):
- platform: "2gis" | "yandex" | "unknown" (может отсутствовать)
- rating: 1..5 (может отсутствовать)
- review_text: текст отзыва (обязательно)
- review_date: дата отзыва (может отсутствовать)
- business_context: описание бизнеса/услуг/регламента (может отсутствовать)
- branch/city: филиал/город (может отсутствовать)
- meta: любые доп. поля (язык, имя автора, ссылка, уже существующий ответ и т.п.)

ОБЩИЕ ПРИНЦИПЫ КАЧЕСТВА:
- Никаких выдуманных деталей, если их нет во входе.
- Если данных мало — формулируй гипотезы + уровень уверенности.
- Цитаты из отзыва делай короткими: до 12 слов.
- Пиши на русском, вежливо, без токсичности.
- Никогда не публикуй и не повторяй персональные данные.
- Не упоминай публично “мы подадим жалобу” и не угрожай автору.

ШАГ 1. ОПРЕДЕЛЕНИЕ ПЛОЩАДКИ (если platform отсутствует/unknown)
Верни:
- platform_detected.value: "2gis" | "yandex" | "unknown"
- confidence 0..1
- signals: 2–5 признаков
Если нет уверенных признаков — "unknown" и confidence ≤0.4.

ШАГ 2. ГЛУБОКИЙ АНАЛИЗ ОТЗЫВА
Сформируй:
A) review_summary
B) sentiment.label negative/mixed/neutral/positive + score -100..+100
C) emotions 1–3
D) aspects 3–8 (name, weight 0..100, evidence)
E) facts_vs_opinions
F) pain_points 1–5
G) root_cause_hypotheses 1–3 (process_stage)
H) business_process_flags (этапы)
I) risks (reputation/ops/finance)
J) recommendations 4–10 (priority P0/P1/P2, action, expected_effect, effort S/M/L, metric)
K) clarifying_questions 0–3

ШАГ 3. CHECK-LIST НАРУШЕНИЙ (policy_check)
Верни:
- has_possible_violations
- possible_violations (category, confidence, evidence)
- notes

2ГИС чек-лист:
1) не личный опыт/со слов/давно >1 года
2) упоминание конкурентов
3) дубликаты/копипаст (гипотеза)
4) ответ на другой отзыв
5) реклама/накрутка/ссылки
6) капслок/символы
7) работодатель/собеседование
8) мат/оскорбления/угрозы/дискриминация
9) персональные данные/документы/мед.

Яндекс чек-лист:
1) не личный опыт
2) неверный объект/дублирование
3) персональные данные/документы/мед
4) фото/видео сотрудников без согласия (если упоминается)
5) отзыв как работника
6) реклама/спам/ссылки/конкуренты
7) недостоверный/накрученный (гипотеза)
8) угрозы/дискриминация/18+

ШАГ 4. public_reply
2–8 предложений, человечески, без ПДн, без угроз.

ШАГ 5. complaint
complaint.needed=true если:
a) rating < 2 (если rating есть)
или b) violations с confidence >=0.6
или c) сильный сигнал “не было визита” (гипотеза)
Для 2ГИС: complaint.text <= 450 символов + верни char_count.

ВЫХОДНОЙ ФОРМАТ (СТРОГО: вернуть ТОЛЬКО JSON)
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
    "has_possible_violations":false,
    "possible_violations":[{"category":"...","confidence":0.0,"evidence":["..."]}],
    "notes":"..."
  },
  "public_reply":{"tone":"...","text":"..."},
  "complaint":{"needed":false,"reasons":["..."],"text":"...","char_count":0}
}
"""

CX_PROMPT_LITE = r"""
Верни ТОЛЬКО валидный JSON по схеме:
platform_detected, review_summary, sentiment, emotions, aspects, facts_vs_opinions, pain_points,
root_cause_hypotheses, business_process_flags, risks, recommendations, clarifying_questions,
policy_check, public_reply, complaint.
Никаких markdown, никаких пояснений.
Если данных мало — гипотезы + confidence.
"""

def get_cx_prompt() -> str:
    return CX_PROMPT_LITE if CX_PROMPT_MODE == "lite" else CX_PROMPT_FULL

# -----------------------------
# Redaction
# -----------------------------
def _redact(s: str) -> str:
    if not s:
        return s
    # hide bot token and api keys if accidentally appear
    s = s.replace(TELEGRAM_BOT_TOKEN, "***TG_TOKEN***")
    if DEEPSEEK_API_KEY:
        s = s.replace(DEEPSEEK_API_KEY, "***DEEPSEEK_KEY***")
    if OPENAI_API_KEY:
        s = s.replace(OPENAI_API_KEY, "***OPENAI_KEY***")
    if GEMINI_API_KEY:
        s = s.replace(GEMINI_API_KEY, "***GEMINI_KEY***")
    if GROK_API_KEY:
        s = s.replace(GROK_API_KEY, "***GROK_KEY***")
    return s

# -----------------------------
# AI clients
# -----------------------------
def ai_chat(messages: List[Dict[str, str]]) -> str:
    engine = (os.getenv("AI_ENGINE") or AI_ENGINE).strip().lower()

    if engine in ("deepseek", "deep-seek", "ds"):
        return call_deepseek(messages)

    if engine in ("openai", "gpt"):
        return call_openai(messages)

    if engine in ("gemini", "google"):
        return call_gemini(messages)

    if engine in ("grok", "xai"):
        return call_grok(messages)

    raise RuntimeError(f"Unknown AI_ENGINE: {engine}")

def call_deepseek(messages: List[Dict[str, str]]) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    # 1) Prefer OpenAI SDK if available (often helps with gateways/proxies)
    if OPENAI_SDK_AVAILABLE:
        try:
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                temperature=0.2,
                timeout=AI_TIMEOUT,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text
        except Exception as e:
            logger.warning("DeepSeek via OpenAI SDK failed, fallback to requests. err=%s", str(e)[:200])

    # 2) Fallback: requests with browser-like headers
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; telegramreviewsbot/1.0; Railway)",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }

    resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)

    body_preview = _redact(resp.text[:900])
    logger.info("DeepSeek status=%s body=%s", resp.status_code, body_preview)

    # Cloudflare / anti-bot HTML
    if "<html" in resp.text.lower() or "just a moment" in resp.text.lower():
        raise RuntimeError(f"DeepSeek gateway returned HTML (likely Cloudflare). status={resp.status_code}")

    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()

def call_openai(messages: List[Dict[str, str]]) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")

    if OPENAI_SDK_AVAILABLE:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            timeout=AI_TIMEOUT,
        )
        return (resp.choices[0].message.content or "").strip()

    # fallback requests
    url = f"{OPENAI_BASE_URL}/chat/completions"
    payload = {"model": OPENAI_MODEL, "messages": messages, "temperature": 0.2}
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=AI_TIMEOUT)
    logger.info("OpenAI status=%s body=%s", resp.status_code, _redact(resp.text[:700]))
    resp.raise_for_status()
    data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()

def call_gemini(messages: List[Dict[str, str]]) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    # Convert messages to Gemini format (simple)
    joined = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in messages])
    payload = {
        "contents": [{"role": "user", "parts": [{"text": joined}]}]
    }
    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    resp = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=AI_TIMEOUT)
    logger.info("Gemini status=%s body=%s", resp.status_code, _redact(resp.text[:700]))
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    if not parts:
        return ""
    return (parts[0].get("text") or "").strip()

def call_grok(messages: List[Dict[str, str]]) -> str:
    # Placeholder: implement when you have xAI endpoint details
    raise RuntimeError("GROK engine not configured yet (set GROK_BASE_URL/GROK_API_KEY)")

# -----------------------------
# JSON extraction from LLM response
# -----------------------------
def extract_first_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Returns (json_obj, error). Tries to parse JSON even if wrapped in text/code fences.
    """
    if not text:
        return None, "empty_ai_response"

    # remove code fences
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # try direct
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj, None
        return None, "json_is_not_object"
    except Exception:
        pass

    # try find first {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end+1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj, None
            return None, "json_is_not_object"
        except Exception as e:
            return None, f"json_parse_failed: {str(e)[:120]}"

    return None, "no_json_object_found"

# -----------------------------
# CX analyze (build prompt -> call ai -> parse json)
# -----------------------------
def cx_analyze(input_obj: dict) -> Tuple[Optional[dict], str]:
    """
    Returns (parsed_json_or_none, raw_text)
    """
    system_prompt = get_cx_prompt()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(input_obj, ensure_ascii=False)},
    ]

    raw = ai_chat(messages)
    parsed, err = extract_first_json(raw)
    if parsed is None:
        raise RuntimeError(f"AI returned invalid JSON. err={err}")
    return parsed, raw

# -----------------------------
# Inline keyboard
# -----------------------------
def analysis_keyboard(analysis_id: int) -> dict:
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

# -----------------------------
# Commands
# -----------------------------
HELP_TEXT = (
    "/start — приветствие\n"
    "/help — помощь\n"
    "/myid — user_id/chat_id\n"
    "/engine — текущий AI_ENGINE\n"
    "\n"
    "Админ-команды:\n"
    "/addreview source=yandex|2gis rating=1..5 <текст>\n"
    "/listreviews n=10 [source=yandex|2gis]\n"
    "/review <id>\n"
    "/deletereview <id>\n"
    "/analyzereview <id>\n"
    "/exports csv [n=100]\n"
    "/weeklyreport days=7\n"
    "\n"
    "Анализ:\n"
    "/analyze <текст>\n"
)

def parse_kv_args(text: str) -> Tuple[Dict[str, str], str]:
    """
    Parses leading key=value tokens.
    Returns (kv, rest_text)
    """
    parts = text.strip().split()
    kv: Dict[str, str] = {}
    rest_start = 0
    for i, p in enumerate(parts):
        if "=" in p and not p.startswith("http"):
            k, v = p.split("=", 1)
            if k and v:
                kv[k.strip().lower()] = v.strip()
                rest_start = i + 1
                continue
        break
    rest = " ".join(parts[rest_start:])
    return kv, rest

# -----------------------------
# Background analysis (to keep webhook fast)
# -----------------------------
def background_analyze(chat_id: int, user_id: int, review_text: str, platform_hint: str = "unknown", rating: Optional[int] = None, review_id: Optional[int] = None) -> None:
    engine = (os.getenv("AI_ENGINE") or AI_ENGINE).strip().lower()
    model_name = ""
    if engine == "deepseek":
        model_name = DEEPSEEK_MODEL
    elif engine == "openai":
        model_name = OPENAI_MODEL
    elif engine == "gemini":
        model_name = GEMINI_MODEL
    elif engine == "grok":
        model_name = GROK_MODEL

    input_obj = {
        "platform": platform_hint,
        "rating": rating,
        "review_text": review_text,
        "review_date": None,
        "business_context": None,
        "branch/city": None,
        "meta": {},
    }

    try:
        parsed, raw = cx_analyze(input_obj)

        analysis_id = db_insert_analysis(
            review_id=review_id,
            platform=parsed.get("platform_detected", {}).get("value") if isinstance(parsed.get("platform_detected"), dict) else platform_hint,
            rating=rating,
            review_text=review_text,
            result_json=parsed,
            error=None,
            model=model_name,
            engine=engine,
            created_by=user_id,
        ) or 0

        send_message(chat_id, f"✅ Анализ готов. ID: {analysis_id}", reply_markup=analysis_keyboard(analysis_id))

    except Exception as e:
        err_text = str(e)
        logger.error("AI exception: %s", err_text)
        logger.exception("AI exception traceback")

        # Store error + minimal result_json
        fallback_json = {
            "_error": "AI failed or returned invalid JSON (see logs)",
            "engine": engine,
        }
        analysis_id = db_insert_analysis(
            review_id=review_id,
            platform=platform_hint,
            rating=rating,
            review_text=review_text,
            result_json=fallback_json,
            error=err_text[:800],
            model=model_name,
            engine=engine,
            created_by=user_id,
        ) or 0

        # Human-readable message
        if "Cloudflare" in err_text or "returned HTML" in err_text or "status=403" in err_text:
            msg = "❌ AI недоступен: шлюз вернул HTML/403 (похоже Cloudflare/защита). Нужна диагностика /diag/ai и проверка заголовков/доступа."
        else:
            msg = "❌ Не удалось получить валидный JSON от ИИ. Анализ сохранён с ошибкой. ID: %d\nПопробуй ещё раз или переключи CX_PROMPT_MODE=lite." % analysis_id

        send_message(chat_id, msg, reply_markup=analysis_keyboard(analysis_id))

# -----------------------------
# HTTP routes
# -----------------------------
@app.get("/")
def health():
    set_webhook_once()
    return jsonify({
        "ok": True,
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "ai_engine": (os.getenv("AI_ENGINE") or AI_ENGINE).strip().lower(),
        "prompt_mode": (os.getenv("CX_PROMPT_MODE") or CX_PROMPT_MODE).strip().lower(),
        "admin_mode": ADMIN_MODE,
        "db": "postgres" if DB_OK else "disabled",
        "deepseek_url": DEEPSEEK_URL,
        "openai_sdk": OPENAI_SDK_AVAILABLE,
    })

@app.get("/diag/ai")
def diag_ai():
    # optional protection
    if DIAG_TOKEN:
        token = request.args.get("token", "").strip()
        if token != DIAG_TOKEN:
            return jsonify({"ok": False, "error": "forbidden"}), 403

    engine = (os.getenv("AI_ENGINE") or AI_ENGINE).strip().lower()
    prompt_mode = (os.getenv("CX_PROMPT_MODE") or CX_PROMPT_MODE).strip().lower()

    messages = [
        {"role": "system", "content": "Reply with exactly: OK"},
        {"role": "user", "content": "ping"},
    ]
    try:
        raw = ai_chat(messages)
        return jsonify({
            "ok": True,
            "engine": engine,
            "prompt_mode": prompt_mode,
            "deepseek_url": DEEPSEEK_URL if engine == "deepseek" else None,
            "raw_preview": raw[:300],
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "engine": engine,
            "prompt_mode": prompt_mode,
            "deepseek_url": DEEPSEEK_URL if engine == "deepseek" else None,
            "error": str(e)[:700],
        }), 500

@app.get("/cron/weekly")
def cron_weekly():
    if not CRON_TOKEN:
        return jsonify({"ok": False, "error": "CRON_TOKEN not set"}), 400

    token = request.args.get("token", "").strip()
    if token != CRON_TOKEN:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    days = int(request.args.get("days", "7"))
    summary = db_weekly_summary(days=days)
    if not summary.get("ok"):
        return jsonify(summary), 500

    # send to all admins
    sent_to = []
    text = format_weekly_report(summary)
    for cid in ADMIN_CHAT_IDS:
        send_message(cid, text)
        sent_to.append(cid)

    return jsonify({"ok": True, "days": days, "sent_to": sent_to})

@app.post(WEBHOOK_PATH)
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    logger.info("Update: %s", _redact(json.dumps(update, ensure_ascii=False)[:1200]))

    # callback
    if "callback_query" in update:
        cq = update["callback_query"]
        cq_id = cq.get("id", "")
        msg = cq.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        data = (cq.get("data") or "").strip()

        try:
            handle_callback(chat_id, cq_id, data)
        except Exception:
            logger.exception("handle_callback failed")
            if cq_id:
                answer_callback_query(cq_id, "Ошибка", show_alert=True)
        return "ok"

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    user = message.get("from") or {}
    user_id = user.get("id")
    text = (message.get("text") or "").strip()

    logger.info("Parsed: chat_id=%s user_id=%s text=%r", chat_id, user_id, text[:220])

    if not chat_id or not user_id:
        return "ok"

    # commands
    if text.startswith("/start"):
        send_message(chat_id, "Привет! Я бот для анализа отзывов.\nНапиши /help.")
        return "ok"

    if text.startswith("/help"):
        send_message(chat_id, HELP_TEXT)
        return "ok"

    if text.startswith("/myid"):
        send_message(chat_id, f"Ваш ID: {chat_id}")
        return "ok"

    if text.startswith("/engine"):
        send_message(chat_id, f"Текущий AI_ENGINE: {(os.getenv('AI_ENGINE') or AI_ENGINE).strip().lower()}")
        return "ok"

    # admin commands
    if text.startswith("/addreview"):
        if not _is_admin(chat_id):
            send_message(chat_id, "⛔ Команда доступна только админам.")
            return "ok"

        args = text[len("/addreview"):].strip()
        kv, rest = parse_kv_args(args)

        source = (kv.get("source") or "manual").strip().lower()
        rating = kv.get("rating")
        rating_int = int(rating) if rating and rating.isdigit() else None
        review_text = rest.strip()

        if not review_text:
            send_message(chat_id, "Формат: /addreview source=yandex rating=5 <текст>")
            return "ok"

        rid = db_insert_review(source=source, rating=rating_int, review_text=review_text, meta={"added_by": user_id})
        if not rid:
            send_message(chat_id, "❌ Не удалось сохранить отзыв (DB?).")
            return "ok"

        send_message(chat_id, f"✅ Отзыв сохранён: #{rid}\nЧтобы проанализировать: /analyzereview {rid}")
        return "ok"

    if text.startswith("/listreviews"):
        if not _is_admin(chat_id):
            send_message(chat_id, "⛔ Команда доступна только админам.")
            return "ok"

        args = text[len("/listreviews"):].strip()
        kv, _ = parse_kv_args(args)
        n = int(kv.get("n", "10"))
        source = kv.get("source")
        items = db_list_reviews(n=n, source=source)

        if not items:
            send_message(chat_id, "Пока нет отзывов.")
            return "ok"

        lines = []
        for it in items:
            lines.append(f"#{it['id']} [{it['source']}] ⭐{it['rating'] or '-'} — {it['preview']}")
        send_message(chat_id, "\n\n".join(lines))
        return "ok"

    if text.startswith("/review"):
        if not _is_admin(chat_id):
            send_message(chat_id, "⛔ Команда доступна только админам.")
            return "ok"

        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            send_message(chat_id, "Формат: /review <id>")
            return "ok"
        rid = int(parts[1])
        r = db_get_review(rid)
        if not r:
            send_message(chat_id, "❌ Отзыв не найден.")
            return "ok"
        send_message(chat_id, f"#{r['id']} [{r['source']}] ⭐{r['rating'] or '-'}\n\n{r['review_text']}")
        return "ok"

    if text.startswith("/deletereview"):
        if not _is_admin(chat_id):
            send_message(chat_id, "⛔ Команда доступна только админам.")
            return "ok"

        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            send_message(chat_id, "Формат: /deletereview <id>")
            return "ok"
        rid = int(parts[1])
        ok = db_delete_review(rid)
        send_message(chat_id, "✅ Удалено." if ok else "❌ Не удалось удалить.")
        return "ok"

    if text.startswith("/analyzereview"):
        if not _is_admin(chat_id):
            send_message(chat_id, "⛔ Команда доступна только админам.")
            return "ok"

        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            send_message(chat_id, "Формат: /analyzereview <id>")
            return "ok"

        rid = int(parts[1])
        r = db_get_review(rid)
        if not r:
            send_message(chat_id, "❌ Отзыв не найден.")
            return "ok"

        send_message(chat_id, "Принял ✅ Готовлю анализ...")
        threading.Thread(
            target=background_analyze,
            args=(chat_id, user_id, r["review_text"], r.get("source") or "unknown", r.get("rating"), rid),
            daemon=True,
        ).start()
        return "ok"

    if text.startswith("/weeklyreport"):
        if not _is_admin(chat_id):
            send_message(chat_id, "⛔ Команда доступна только админам.")
            return "ok"

        args = text[len("/weeklyreport"):].strip()
        kv, _ = parse_kv_args(args)
        days = int(kv.get("days", "7"))
        summary = db_weekly_summary(days=days)
        if not summary.get("ok"):
            send_message(chat_id, "❌ Не удалось построить отчёт (DB?).")
            return "ok"
        send_message(chat_id, format_weekly_report(summary))
        return "ok"

    # /analyze - works for everyone
    if text.startswith("/analyze"):
        analyze_text = text[len("/analyze"):].strip()
        if not analyze_text:
            send_message(chat_id, "Формат: /analyze <текст отзыва>")
            return "ok"

        send_message(chat_id, "Принял ✅ Готовлю анализ...")
        threading.Thread(
            target=background_analyze,
            args=(chat_id, user_id, analyze_text, "unknown", None, None),
            daemon=True,
        ).start()
        return "ok"

    # If plain text, you can decide to ignore or treat as analyze:
    # send_message(chat_id, "Напиши /help. Для анализа: /analyze <текст>")

    return "ok"

# -----------------------------
# Callback handler
# -----------------------------
def handle_callback(chat_id: Optional[int], callback_query_id: str, data: str) -> None:
    if not chat_id:
        answer_callback_query(callback_query_id, "Нет chat_id", show_alert=True)
        return

    # data = action:analysis_id
    if ":" not in data:
        answer_callback_query(callback_query_id, "Неверная кнопка", show_alert=True)
        return

    action, sid = data.split(":", 1)
    if not sid.isdigit():
        answer_callback_query(callback_query_id, "Неверный ID", show_alert=True)
        return

    analysis_id = int(sid)
    a = db_get_analysis(analysis_id)
    if not a:
        answer_callback_query(callback_query_id, "Анализ не найден", show_alert=True)
        return

    obj = a.get("result_json") or {}
    err = a.get("error")

    if err:
        answer_callback_query(callback_query_id, "Анализ с ошибкой — смотри сообщение", show_alert=False)

    if action == "json":
        answer_callback_query(callback_query_id, "Отправляю JSON")
        send_message(chat_id, json.dumps(obj, ensure_ascii=False)[:3800])
        return

    public_reply = (obj.get("public_reply") or {}).get("text") if isinstance(obj.get("public_reply"), dict) else None
    complaint_obj = obj.get("complaint") or {}
    complaint_needed = bool(complaint_obj.get("needed"))
    complaint_text = complaint_obj.get("text") if isinstance(complaint_obj, dict) else None
    complaint_count = complaint_obj.get("char_count") if isinstance(complaint_obj, dict) else None

    if action == "reply":
        answer_callback_query(callback_query_id, "Готово")
        if public_reply:
            send_message(chat_id, f"✍️ Публичный ответ:\n\n{public_reply}")
        else:
            send_message(chat_id, "❌ В анализе нет public_reply.text")
        return

    if action == "complaint":
        answer_callback_query(callback_query_id, "Готово")
        if not complaint_needed:
            send_message(chat_id, "⚠️ Жалоба не требуется по условиям (complaint.needed=false).")
        else:
            extra = f"\n\nДлина: {complaint_count}" if complaint_count is not None else ""
            send_message(chat_id, f"⚠️ Жалоба:\n\n{complaint_text or '(пусто)'}{extra}")
        return

    if action == "both":
        answer_callback_query(callback_query_id, "Готово")
        if public_reply:
            send_message(chat_id, f"✍️ Публичный ответ:\n\n{public_reply}")
        else:
            send_message(chat_id, "❌ В анализе нет public_reply.text")

        if not complaint_needed:
            send_message(chat_id, "⚠️ Жалоба не требуется по условиям (complaint.needed=false).")
        else:
            extra = f"\n\nДлина: {complaint_count}" if complaint_count is not None else ""
            send_message(chat_id, f"⚠️ Жалоба:\n\n{complaint_text or '(пусто)'}{extra}")
        return

    answer_callback_query(callback_query_id, "Неизвестное действие", show_alert=True)

# -----------------------------
# Weekly report formatting
# -----------------------------
def format_weekly_report(summary: dict) -> str:
    days = summary.get("days", 7)
    total = summary.get("total", 0)
    with_error = summary.get("with_error", 0)
    sentiments = summary.get("sentiments", {})
    complaints_needed = summary.get("complaints_needed", 0)
    top_aspects = summary.get("top_aspects", [])

    lines = []
    lines.append(f"📊 Отчёт по анализам за {days} дней")
    lines.append(f"Всего анализов: {total}")
    lines.append(f"С ошибками: {with_error}")
    lines.append(f"Жалоб требуется: {complaints_needed}")
    lines.append("")
    lines.append("Тональность:")
    for k in ["negative", "mixed", "neutral", "positive", "unknown"]:
        lines.append(f" - {k}: {sentiments.get(k, 0)}")

    if top_aspects:
        lines.append("")
        lines.append("Топ аспектов (частота):")
        for name, cnt in top_aspects[:10]:
            lines.append(f" - {name}: {cnt}")

    return "\n".join(lines)

# -----------------------------
# Startup
# -----------------------------
db_init()
set_webhook_once()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
