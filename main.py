import os
import re
import json
import csv
import io
import hashlib
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
# OpenAI SDK (required for DeepSeek gateways)
# -----------------------------
try:
    from openai import OpenAI  # type: ignore
    OPENAI_SDK_AVAILABLE = True
except Exception:
    OPENAI_SDK_AVAILABLE = False
    OpenAI = None  # type: ignore

# -----------------------------
# Env / Config
# -----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN (or TELEGRAM_TOKEN) is required")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is required (e.g. https://xxx.up.railway.app)")

BOT_PATH_SECRET = os.getenv("BOT_PATH_SECRET", "").strip()
if not BOT_PATH_SECRET:
    BOT_PATH_SECRET = TELEGRAM_BOT_TOKEN[-12:]
    logger.warning("BOT_PATH_SECRET not set. Using fallback based on token suffix.")

WEBHOOK_PATH = f"/webhook/{BOT_PATH_SECRET}"
WEBHOOK_FULL_URL = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"

PORT = int(os.getenv("PORT", "8000"))

AI_ENGINE = (os.getenv("AI_ENGINE") or "deepseek").strip().lower()
CX_PROMPT_MODE = (os.getenv("CX_PROMPT_MODE") or "full").strip().lower()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_KEY")
DEEPSEEK_BASE_URL = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.artemox.com/v1").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
DEEPSEEK_URL = f"{DEEPSEEK_BASE_URL}/chat/completions"

# allow requests fallback for deepseek (Cloudflare can block it)
DEEPSEEK_ALLOW_REQUESTS_FALLBACK = (os.getenv("DEEPSEEK_ALLOW_REQUESTS_FALLBACK") or "0").strip() == "1"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_BASE_URL = (os.getenv("GROK_BASE_URL") or "").rstrip("/")
GROK_MODEL = os.getenv("GROK_MODEL") or "grok-beta"

REPORT_CHAT_IDS = os.getenv("REPORT_CHAT_IDS", "").strip()
ADMIN_CHAT_IDS = sorted({int(x) for x in re.findall(r"\d+", REPORT_CHAT_IDS)})
ADMIN_MODE = "allowlist" if ADMIN_CHAT_IDS else "closed"
if ADMIN_CHAT_IDS:
    logger.info("Admins parsed: count=%s sample=%s", len(ADMIN_CHAT_IDS), ADMIN_CHAT_IDS[:3])
else:
    logger.warning("Admins parsed: count=0 (REPORT_CHAT_IDS is empty or invalid)")

SUPERADMIN_ID_RAW = (os.getenv("SUPERADMIN_ID") or "").strip()
SUPERADMIN_ID = int(SUPERADMIN_ID_RAW) if SUPERADMIN_ID_RAW.isdigit() else None
if SUPERADMIN_ID is None and ADMIN_CHAT_IDS:
    SUPERADMIN_ID = ADMIN_CHAT_IDS[0]
    logger.warning("SUPERADMIN_ID not set. Using REPORT_CHAT_IDS fallback=%s", SUPERADMIN_ID)
if SUPERADMIN_ID is None:
    logger.critical("SUPERADMIN_ID not set and REPORT_CHAT_IDS empty. Bot starts in closed mode.")

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL_INTERNAL")

CRON_TOKEN = os.getenv("CRON_TOKEN", "").strip()
DIAG_TOKEN = os.getenv("DIAG_TOKEN", "").strip()

TG_TIMEOUT = float(os.getenv("TG_TIMEOUT", "10"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "40"))
SET_WEBHOOK_ON_START = (os.getenv("SET_WEBHOOK_ON_START") or "1").strip() not in ("0", "false", "no")

SERVICE_NAME = "Автоцентр Лира"
SERVICE_ADDRESS = "Нижний Новгород, ул. Удмуртская, д. 10"
SERVICE_HOURS = "Пн–Пт 09:00–19:00; Сб–Вс выходной"
SERVICE_PHONES = ["+7 (831) 214-00-50", "+7 (967) 711-50-50"]
DEFAULT_BUSINESS_CONTEXT = (
    "Автоцентр Лира (автосервис/СТО, Нижний Новгород, ул. Удмуртская, д. 10). "
    "Контакты: +7 (831) 214-00-50, +7 (967) 711-50-50. "
    "Режим работы: Пн–Пт 09:00–19:00, Сб–Вс выходной. "
    "Услуги: диагностика, ремонт, ТО, приёмка автомобиля, запись на обслуживание, "
    "ожидание в зоне клиента, парковка, коммуникация мастеров, сроки работ, "
    "согласование стоимости, качество ремонта и сервиса."
)
UI_VERSION = "2025-02-15"

# -----------------------------
# Flask
# -----------------------------
app = Flask(__name__)

# -----------------------------
# Redaction
# -----------------------------
def _redact(s: str) -> str:
    if not s:
        return s
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
# Telegram helpers
# -----------------------------
def tg_api(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

def send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(tg_api("sendMessage"), json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error(
                "sendMessage failed status=%s chat_id=%s text=%s body=%s",
                r.status_code,
                chat_id,
                _redact(text[:200]),
                _redact(r.text[:900]),
            )
    except Exception as e:
        logger.exception("sendMessage exception chat_id=%s text=%s err=%s", chat_id, _redact(text[:200]), e)

def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False) -> None:
    payload = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
    try:
        r = requests.post(tg_api("answerCallbackQuery"), json=payload, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("answerCallbackQuery failed status=%s body=%s", r.status_code, _redact(r.text[:500]))
    except Exception:
        logger.exception("answerCallbackQuery exception")

def send_document(chat_id: int, filename: str, content: bytes) -> None:
    files = {"document": (filename, content)}
    data = {"chat_id": chat_id}
    try:
        r = requests.post(tg_api("sendDocument"), data=data, files=files, timeout=TG_TIMEOUT)
        if r.status_code != 200:
            logger.error("sendDocument failed status=%s body=%s", r.status_code, _redact(r.text[:900]))
    except Exception:
        logger.exception("sendDocument exception")

def get_user_role(user_id: Optional[int]) -> str:
    if user_id is None:
        return "none"
    if SUPERADMIN_ID is not None and user_id == SUPERADMIN_ID:
        return "owner"
    if not DB_OK:
        return "none"
    conn = _db_connect()
    if not conn:
        return "none"
    try:
        with conn.cursor() as cur:
            _ensure_access_columns(cur)
            user_id_col = _access_user_id_column()
            if not user_id_col:
                return "none"
            active_clause = " AND is_active=true" if DB_ACCESS_HAS_IS_ACTIVE else ""
            cur.execute(
                f"SELECT role FROM access_users WHERE {user_id_col}=%s{active_clause}",
                (user_id,),
            )
            row = cur.fetchone()
            return row[0] if row else "none"
    except Exception:
        logger.exception("get_user_role failed")
        return "none"
    finally:
        try:
            conn.close()
        except Exception:
            pass

def can_use_bot(user_id: Optional[int]) -> bool:
    return get_user_role(user_id) in ("owner", "staff", "user")

def can_manage_access(user_id: Optional[int]) -> bool:
    return get_user_role(user_id) == "owner"

def _display_name(user: dict) -> str:
    username = (user.get("username") or "").strip()
    first_name = (user.get("first_name") or "").strip()
    if username:
        return f"@{username}"
    if first_name:
        return first_name
    return "друг"

# -----------------------------
# Webhook setup (per process)
# -----------------------------
_webhook_set_once = False
_webhook_lock = threading.Lock()

def set_webhook_once() -> None:
    global _webhook_set_once
    if not SET_WEBHOOK_ON_START:
        logger.info("setWebhook skipped (SET_WEBHOOK_ON_START=0)")
        return
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
DB_LAST_ERROR: Optional[str] = None
DB_HAS_TEXT = False
DB_HAS_REVIEW_TEXT = False
DB_ACCESS_HAS_USER_ID = False
DB_ACCESS_HAS_CHAT_ID = False
DB_ACCESS_HAS_IS_ACTIVE = False
DB_ACCESS_HAS_NOTE = False
DB_ACCESS_HAS_CREATED_AT = False
DB_ACCESS_HAS_ADDED_AT = False

def _db_connect():
    global DB_LAST_ERROR
    if not DATABASE_URL:
        return None
    try:
        import psycopg  # type: ignore
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        return conn
    except Exception as e:
        DB_LAST_ERROR = str(e)[:500]
        logger.error("DB connect failed: %s", e)
        return None

def _refresh_review_columns(cur) -> None:
    global DB_HAS_TEXT, DB_HAS_REVIEW_TEXT
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reviews'
        """
    )
    cols = {row[0] for row in (cur.fetchall() or [])}
    DB_HAS_TEXT = "text" in cols
    DB_HAS_REVIEW_TEXT = "review_text" in cols
    logger.info("reviews columns: has_text=%s has_review_text=%s", DB_HAS_TEXT, DB_HAS_REVIEW_TEXT)

def _ensure_review_columns(cur) -> None:
    if not (DB_HAS_TEXT or DB_HAS_REVIEW_TEXT):
        _refresh_review_columns(cur)

def _review_text_expr(prefix: str = "") -> str:
    if DB_HAS_REVIEW_TEXT and DB_HAS_TEXT:
        return f"COALESCE({prefix}review_text, {prefix}text)"
    if DB_HAS_REVIEW_TEXT:
        return f"{prefix}review_text"
    if DB_HAS_TEXT:
        return f"{prefix}text"
    return "NULL"

def _refresh_access_columns(cur) -> None:
    global DB_ACCESS_HAS_USER_ID, DB_ACCESS_HAS_CHAT_ID, DB_ACCESS_HAS_IS_ACTIVE, DB_ACCESS_HAS_NOTE
    global DB_ACCESS_HAS_CREATED_AT, DB_ACCESS_HAS_ADDED_AT
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='access_users'
        """
    )
    cols = {row[0] for row in (cur.fetchall() or [])}
    DB_ACCESS_HAS_USER_ID = "user_id" in cols
    DB_ACCESS_HAS_CHAT_ID = "chat_id" in cols
    DB_ACCESS_HAS_IS_ACTIVE = "is_active" in cols
    DB_ACCESS_HAS_NOTE = "note" in cols
    DB_ACCESS_HAS_CREATED_AT = "created_at" in cols
    DB_ACCESS_HAS_ADDED_AT = "added_at" in cols
    logger.info(
        "access_users columns: user_id=%s chat_id=%s is_active=%s note=%s created_at=%s added_at=%s",
        DB_ACCESS_HAS_USER_ID,
        DB_ACCESS_HAS_CHAT_ID,
        DB_ACCESS_HAS_IS_ACTIVE,
        DB_ACCESS_HAS_NOTE,
        DB_ACCESS_HAS_CREATED_AT,
        DB_ACCESS_HAS_ADDED_AT,
    )

def _ensure_access_columns(cur) -> None:
    if not (DB_ACCESS_HAS_USER_ID or DB_ACCESS_HAS_CHAT_ID):
        _refresh_access_columns(cur)

def _access_user_id_column() -> Optional[str]:
    if DB_ACCESS_HAS_USER_ID:
        return "user_id"
    if DB_ACCESS_HAS_CHAT_ID:
        return "chat_id"
    return None

def _access_created_at_column() -> Optional[str]:
    if DB_ACCESS_HAS_CREATED_AT:
        return "created_at"
    if DB_ACCESS_HAS_ADDED_AT:
        return "added_at"
    return None

def db_init() -> None:
    """
    Safe migration for mixed schemas.
    Your DB has old column `text` (NOT NULL) — we keep compatibility by:
      - ensuring both `text` and `review_text` exist
      - backfilling each other
    """
    global DB_OK, DB_LAST_ERROR
    conn = _db_connect()
    if not conn:
        DB_OK = False
        logger.warning("DB init skipped (DATABASE_URL not set or connect failed)")
        return

    try:
        with conn.cursor() as cur:
            # Required SQL blocks (kept for compatibility and audit):
            # -- Access list for bot users
            # CREATE TABLE IF NOT EXISTS access_users (
            #   user_id BIGINT PRIMARY KEY,
            #   role TEXT NOT NULL DEFAULT 'user',
            #   added_by BIGINT,
            #   created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            # );
            #
            # -- Optional: helper indexes for reviews
            # CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at);
            # CREATE INDEX IF NOT EXISTS idx_reviews_platform ON reviews(platform);
            # CREATE INDEX IF NOT EXISTS idx_reviews_review_hash ON reviews(review_hash);

            # baseline (minimal tables)
            cur.execute("CREATE TABLE IF NOT EXISTS public.reviews (id BIGSERIAL PRIMARY KEY);")
            cur.execute("CREATE TABLE IF NOT EXISTS public.review_analyses (id BIGSERIAL PRIMARY KEY);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.settings (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.user_sessions (
                    chat_id BIGINT PRIMARY KEY,
                    state TEXT NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            # ---- reviews columns (compat)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.reviews (
                  id BIGSERIAL PRIMARY KEY,
                  platform TEXT,
                  source TEXT NOT NULL DEFAULT 'manual',
                  rating INT,
                  text TEXT NOT NULL,
                  review_hash TEXT,
                  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS platform TEXT;")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS rating INT;")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS review_hash TEXT;")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb;")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS review_text TEXT;")
            cur.execute("ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS text TEXT;")
            cur.execute("UPDATE public.reviews SET review_text = text WHERE review_text IS NULL AND text IS NOT NULL;")
            cur.execute("UPDATE public.reviews SET text = review_text WHERE text IS NULL AND review_text IS NOT NULL;")
            cur.execute("UPDATE public.reviews SET text = '' WHERE text IS NULL;")
            cur.execute("ALTER TABLE public.reviews ALTER COLUMN text SET NOT NULL;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON public.reviews(created_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reviews_review_hash ON public.reviews(review_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reviews_platform ON public.reviews(platform);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reviews_platform_rating_created ON public.reviews(platform, rating, created_at);")
            _refresh_review_columns(cur)

            # ---- review_analyses columns
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.review_analyses (
                  id BIGSERIAL PRIMARY KEY,
                  review_id BIGINT UNIQUE,
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
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS review_id BIGINT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS platform TEXT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS rating INT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS review_text TEXT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS result_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS error TEXT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS model TEXT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS engine TEXT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS created_by BIGINT;")
            cur.execute("ALTER TABLE public.review_analyses ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();")
            cur.execute("UPDATE public.review_analyses SET review_text = '' WHERE review_text IS NULL;")
            cur.execute("ALTER TABLE public.review_analyses ALTER COLUMN review_text SET NOT NULL;")
            cur.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'review_analyses_review_id_key'
                      AND conrelid = 'public.review_analyses'::regclass
                  ) THEN
                    ALTER TABLE public.review_analyses
                      ADD CONSTRAINT review_analyses_review_id_key UNIQUE (review_id);
                  END IF;
                END $$;
            """)

            # ---- access control table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.access_users (
                  user_id BIGINT PRIMARY KEY,
                  role TEXT NOT NULL DEFAULT 'user',
                  added_by BIGINT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS chat_id BIGINT;")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS user_id BIGINT;")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS added_by BIGINT;")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS note TEXT;")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ NOT NULL DEFAULT now();")
            cur.execute("ALTER TABLE public.access_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;")
            cur.execute("ALTER TABLE public.access_users ALTER COLUMN role SET DEFAULT 'user';")
            cur.execute("UPDATE public.access_users SET role='user' WHERE role IS NULL;")
            cur.execute("UPDATE public.access_users SET user_id = chat_id WHERE user_id IS NULL AND chat_id IS NOT NULL;")
            cur.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'access_users_user_id_key'
                      AND conrelid = 'public.access_users'::regclass
                  ) THEN
                    ALTER TABLE public.access_users
                      ADD CONSTRAINT access_users_user_id_key UNIQUE (user_id);
                  END IF;
                END $$;
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_access_users_active ON public.access_users(is_active);")
            _refresh_access_columns(cur)

            if SUPERADMIN_ID is not None:
                user_id_col = _access_user_id_column() or "user_id"
                cur.execute(
                    f"""
                    INSERT INTO public.access_users ({user_id_col}, role, added_by, is_active)
                    VALUES (%s, 'owner', %s, TRUE)
                    ON CONFLICT ({user_id_col})
                    DO UPDATE SET role='owner', is_active=TRUE
                    """,
                    (SUPERADMIN_ID, SUPERADMIN_ID),
                )

            cur.execute(
                """
                INSERT INTO public.settings (key, value)
                SELECT 'business_context', %s::jsonb
                WHERE NOT EXISTS (SELECT 1 FROM public.settings WHERE key='business_context')
                """,
                (json.dumps({"value": DEFAULT_BUSINESS_CONTEXT}, ensure_ascii=False),),
            )

        DB_OK = True
        DB_LAST_ERROR = None
        logger.info("DB init OK (postgres=True)")
    except Exception as e:
        DB_OK = False
        DB_LAST_ERROR = str(e)[:500]
        logger.exception("DB init failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_insert_review(source: str, rating: Optional[int], review_text: str, meta: dict,
                     platform: Optional[str] = None, review_hash: Optional[str] = None) -> Optional[int]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            _ensure_review_columns(cur)
            column_parts = [
                ("source", "%s", source),
                ("rating", "%s", rating),
                ("meta", "%s::jsonb", json.dumps(meta, ensure_ascii=False)),
                ("platform", "%s", platform),
                ("review_hash", "%s", review_hash),
            ]
            if DB_HAS_REVIEW_TEXT:
                column_parts.append(("review_text", "%s", review_text))
            if DB_HAS_TEXT:
                column_parts.append(("text", "%s", review_text))
            if not (DB_HAS_REVIEW_TEXT or DB_HAS_TEXT):
                logger.error("reviews table has no text columns; insert skipped")
                return None

            columns = ", ".join([col for col, _, _ in column_parts])
            placeholders = ", ".join([ph for _, ph, _ in column_parts])
            values = [val for _, _, val in column_parts]
            cur.execute(
                f"""
                INSERT INTO reviews ({columns})
                VALUES ({placeholders})
                RETURNING id
                """,
                tuple(values),
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
            _ensure_review_columns(cur)
            cur.execute(
                f"""
                SELECT id, source, rating,
                       {_review_text_expr()} AS review_text,
                       meta, created_at, platform, review_hash
                FROM reviews
                WHERE id=%s
                """,
                (review_id,),
            )
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
                "platform": row[6],
                "review_hash": row[7],
            }
    except Exception:
        logger.exception("db_get_review failed")
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

def db_get_analysis_by_review_id(review_id: int) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, review_id, platform, rating, review_text, result_json, error, model, engine, created_by, created_at FROM review_analyses WHERE review_id=%s",
                (review_id,),
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
        logger.exception("db_get_analysis_by_review_id failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_find_duplicate_review(review_hash: str, days: int = 14) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at
                FROM reviews
                WHERE review_hash = %s
                  AND created_at >= now() - (%s || ' days')::interval
                ORDER BY id DESC
                LIMIT 1
                """,
                (review_hash, days),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {"id": int(row[0]), "created_at": str(row[1])}
    except Exception:
        logger.exception("db_find_duplicate_review failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_find_reviews(platform: Optional[str], rating: Optional[int], days: int, limit: int, offset: int) -> List[dict]:
    conn = _db_connect()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            _ensure_review_columns(cur)
            clauses = ["created_at >= now() - (%s || ' days')::interval"]
            params: List[Any] = [days]
            if platform and platform != "all":
                clauses.append("platform = %s")
                params.append(platform)
            if rating is not None:
                clauses.append("rating = %s")
                params.append(rating)
            where = " AND ".join(clauses)
            params.extend([limit, offset])
            cur.execute(
                f"""
                SELECT id, platform, rating,
                       left({_review_text_expr()}, 80) as preview,
                       created_at
                FROM reviews
                WHERE {where}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            rows = cur.fetchall() or []
            out = []
            for r in rows:
                out.append({
                    "id": int(r[0]),
                    "platform": r[1],
                    "rating": r[2],
                    "preview": r[3],
                    "created_at": str(r[4]),
                })
            return out
    except Exception:
        logger.exception("db_find_reviews failed")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_export_reviews(days: int = 30, limit: int = 500) -> List[dict]:
    conn = _db_connect()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            _ensure_review_columns(cur)
            cur.execute(
                f"""
                SELECT
                  r.id,
                  r.created_at,
                  r.platform,
                  r.rating,
                  {_review_text_expr("r.")} as review_text,
                  r.meta->>'source_url' as source_url,
                  r.meta->>'author_name' as author_name,
                  a.created_at as analysis_created_at,
                  a.result_json
                FROM reviews r
                LEFT JOIN review_analyses a ON a.review_id = r.id
                WHERE r.created_at >= now() - (%s || ' days')::interval
                ORDER BY r.id DESC
                LIMIT %s
                """,
                (days, limit),
            )
            rows = cur.fetchall() or []
            out = []
            for r in rows:
                result_json = r[8] if isinstance(r[8], dict) else (json.loads(r[8]) if r[8] else {})
                sentiment = result_json.get("sentiment") or {}
                public_reply = result_json.get("public_reply") or {}
                complaint = result_json.get("complaint") or {}
                out.append({
                    "id": int(r[0]),
                    "created_at": str(r[1]),
                    "platform": r[2],
                    "rating": r[3],
                    "review_text": r[4],
                    "source_url": r[5],
                    "author_name": r[6],
                    "analysis_created_at": str(r[7]) if r[7] else None,
                    "sentiment_label": sentiment.get("label"),
                    "sentiment_score": sentiment.get("score"),
                    "public_reply_text": public_reply.get("text") if isinstance(public_reply, dict) else None,
                    "complaint_needed": complaint.get("needed") if isinstance(complaint, dict) else None,
                    "complaint_text": complaint.get("text") if isinstance(complaint, dict) else None,
                })
            return out
    except Exception:
        logger.exception("db_export_reviews failed")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_get_setting(key: str) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
            row = cur.fetchone()
            if not row:
                return None
            val = row[0]
            return val if isinstance(val, dict) else (json.loads(val) if val else {})
    except Exception:
        logger.exception("db_get_setting failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_set_setting(key: str, value: dict) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (key)
                DO UPDATE SET value=EXCLUDED.value, updated_at=now()
                """,
                (key, json.dumps(value, ensure_ascii=False)),
            )
    except Exception:
        logger.exception("db_set_setting failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_upsert_access_user(chat_id: int, role: str, added_by: Optional[int], note: Optional[str] = None) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            _ensure_access_columns(cur)
            user_id_col = _access_user_id_column() or "user_id"
            columns = [user_id_col, "role", "added_by"]
            placeholders = ["%s", "%s", "%s"]
            values: List[Any] = [chat_id, role, added_by]
            if DB_ACCESS_HAS_CHAT_ID and user_id_col != "chat_id":
                columns.append("chat_id")
                placeholders.append("%s")
                values.append(chat_id)
            if DB_ACCESS_HAS_NOTE:
                columns.append("note")
                placeholders.append("%s")
                values.append(note)
            if DB_ACCESS_HAS_IS_ACTIVE:
                columns.append("is_active")
                placeholders.append("TRUE")
            if DB_ACCESS_HAS_CREATED_AT:
                columns.append("created_at")
                placeholders.append("now()")
            if DB_ACCESS_HAS_ADDED_AT:
                columns.append("added_at")
                placeholders.append("now()")
            col_list = ", ".join(columns)
            ph_list = ", ".join(placeholders)
            set_parts = ["role=EXCLUDED.role", "added_by=EXCLUDED.added_by"]
            if DB_ACCESS_HAS_ADDED_AT:
                set_parts.append("added_at=now()")
            if DB_ACCESS_HAS_NOTE:
                set_parts.append("note=EXCLUDED.note")
            if DB_ACCESS_HAS_IS_ACTIVE:
                set_parts.append("is_active=TRUE")
            cur.execute(
                f"""
                INSERT INTO access_users ({col_list})
                VALUES ({ph_list})
                ON CONFLICT ({user_id_col})
                DO UPDATE SET {', '.join(set_parts)}
                """,
                tuple(values),
            )
    except Exception:
        logger.exception("db_upsert_access_user failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_deactivate_access_user(chat_id: int) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            _ensure_access_columns(cur)
            user_id_col = _access_user_id_column() or "user_id"
            if DB_ACCESS_HAS_IS_ACTIVE:
                cur.execute(
                    f"UPDATE access_users SET is_active=false WHERE {user_id_col}=%s",
                    (chat_id,),
                )
            else:
                cur.execute(
                    f"DELETE FROM access_users WHERE {user_id_col}=%s",
                    (chat_id,),
                )
    except Exception:
        logger.exception("db_deactivate_access_user failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_list_access_users(active_only: bool = True) -> List[dict]:
    conn = _db_connect()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            _ensure_access_columns(cur)
            user_id_col = _access_user_id_column() or "user_id"
            created_at_col = _access_created_at_column() or "now()"
            note_col = ", note" if DB_ACCESS_HAS_NOTE else ""
            is_active_expr = "is_active" if DB_ACCESS_HAS_IS_ACTIVE else "TRUE as is_active"
            active_clause = " WHERE is_active=true" if active_only and DB_ACCESS_HAS_IS_ACTIVE else ""
            cur.execute(
                f"SELECT {user_id_col}, role, added_by, {created_at_col}, {is_active_expr}{note_col} FROM access_users{active_clause} "
                f"ORDER BY role DESC, {created_at_col} ASC"
            )
            rows = cur.fetchall() or []
            return [
                {
                    "chat_id": int(r[0]),
                    "role": r[1],
                    "added_by": r[2],
                    "added_at": r[3],
                    "is_active": bool(r[4]),
                    "note": r[5] if DB_ACCESS_HAS_NOTE and len(r) > 5 else None,
                }
                for r in rows
            ]
    except Exception:
        logger.exception("db_list_access_users failed")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_count_access_users(active_only: bool = True) -> int:
    conn = _db_connect()
    if not conn:
        return 0
    try:
        with conn.cursor() as cur:
            _ensure_access_columns(cur)
            if active_only and DB_ACCESS_HAS_IS_ACTIVE:
                cur.execute("SELECT count(*) FROM access_users WHERE is_active=true")
            else:
                cur.execute("SELECT count(*) FROM access_users")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        logger.exception("db_count_access_users failed")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_get_session(chat_id: int) -> Optional[dict]:
    conn = _db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state, payload, updated_at FROM user_sessions WHERE chat_id=%s", (chat_id,))
            row = cur.fetchone()
            if not row:
                return None
            payload = row[1] if isinstance(row[1], dict) else (json.loads(row[1]) if row[1] else {})
            return {"state": row[0], "payload": payload, "updated_at": row[2]}
    except Exception:
        logger.exception("db_get_session failed")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_set_session(chat_id: int, state: str, payload: dict) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_sessions (chat_id, state, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (chat_id)
                DO UPDATE SET state=EXCLUDED.state, payload=EXCLUDED.payload, updated_at=now()
                """,
                (chat_id, state, json.dumps(payload, ensure_ascii=False)),
            )
    except Exception:
        logger.exception("db_set_session failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def db_clear_session(chat_id: int) -> None:
    conn = _db_connect()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE chat_id=%s", (chat_id,))
    except Exception:
        logger.exception("db_clear_session failed")
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
            if review_id is not None:
                cur.execute(
                    """
                    INSERT INTO review_analyses
                    (review_id, platform, rating, review_text, result_json, error, model, engine, created_by)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
                    ON CONFLICT (review_id)
                    DO UPDATE SET
                        platform=EXCLUDED.platform,
                        rating=EXCLUDED.rating,
                        review_text=EXCLUDED.review_text,
                        result_json=EXCLUDED.result_json,
                        error=EXCLUDED.error,
                        model=EXCLUDED.model,
                        engine=EXCLUDED.engine,
                        created_by=EXCLUDED.created_by,
                        created_at=now()
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
            else:
                cur.execute(
                    """
                    INSERT INTO review_analyses
                    (review_id, platform, rating, review_text, result_json, error, model, engine, created_by)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
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
                  count(*) FILTER (WHERE error IS NOT NULL) as with_error,
                  avg(rating) as avg_rating
                FROM review_analyses
                WHERE created_at >= now() - (%s || ' days')::interval
                """,
                (days,),
            )
            row = cur.fetchone() or (0, 0, None)
            total = int(row[0])
            with_error = int(row[1])
            avg_rating = float(row[2]) if row[2] is not None else None

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
            pain_points_counter: Dict[str, int] = {}
            recommendations_counter: Dict[str, int] = {}

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

                pains = obj.get("pain_points") or []
                if isinstance(pains, list):
                    for p in pains:
                        item = (p or {}).get("item")
                        if item and isinstance(item, str):
                            key = item.strip().lower()
                            pain_points_counter[key] = pain_points_counter.get(key, 0) + 1

                recs = obj.get("recommendations") or []
                if isinstance(recs, list):
                    for rec in recs:
                        action = (rec or {}).get("action")
                        if action and isinstance(action, str):
                            key = action.strip().lower()
                            recommendations_counter[key] = recommendations_counter.get(key, 0) + 1

            top_aspects = sorted(aspects_counter.items(), key=lambda x: x[1], reverse=True)[:10]
            top_pain_points = sorted(pain_points_counter.items(), key=lambda x: x[1], reverse=True)[:10]
            top_recommendations = sorted(recommendations_counter.items(), key=lambda x: x[1], reverse=True)[:10]

            return {
                "ok": True,
                "days": days,
                "total": total,
                "with_error": with_error,
                "avg_rating": avg_rating,
                "sentiments": sentiments,
                "complaints_needed": complaints_needed,
                "top_aspects": top_aspects,
                "top_pain_points": top_pain_points,
                "top_recommendations": top_recommendations,
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

БИЗНЕС: автосервис/СТО, Автоцентр Лира (Нижний Новгород).

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

ШАГ 2. ГЛУБОБОКИЙ АНАЛИЗ ОТЗЫВА
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

SESSION_TTL_MINUTES = 15

def _current_engine() -> str:
    override = db_get_setting("ai_engine_override") or {}
    val = (override.get("value") or "").strip().lower()
    if val:
        return val
    return (os.getenv("AI_ENGINE") or AI_ENGINE).strip().lower()

def _business_context() -> Optional[str]:
    ctx = db_get_setting("business_context") or {}
    val = (ctx.get("value") or "").strip()
    if val:
        return val
    return DEFAULT_BUSINESS_CONTEXT

def _get_active_session(chat_id: int) -> Optional[dict]:
    sess = db_get_session(chat_id)
    if not sess:
        return None
    updated_at = sess.get("updated_at")
    if isinstance(updated_at, datetime):
        current = datetime.now(updated_at.tzinfo or timezone.utc)
        if updated_at < current - timedelta(minutes=SESSION_TTL_MINUTES):
            db_clear_session(chat_id)
            return None
    return sess

def _hash_review(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

def _guess_platform_from_url(url: str) -> str:
    lower = url.lower()
    if "yandex" in lower or "yandex.ru/maps" in lower:
        return "yandex"
    if "2gis" in lower or "2gis.ru" in lower or "2gis.com" in lower:
        return "2gis"
    return "unknown"

# -----------------------------
# AI clients
# -----------------------------
def ai_chat(messages: List[Dict[str, str]]) -> str:
    engine = _current_engine()

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

    if OPENAI_SDK_AVAILABLE and OpenAI is not None:
        try:
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                temperature=0.2,
                timeout=AI_TIMEOUT,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning("DeepSeek via OpenAI SDK failed. err=%s", str(e)[:200])
            if not DEEPSEEK_ALLOW_REQUESTS_FALLBACK:
                raise RuntimeError("DeepSeek SDK failed (requests fallback disabled).")

    if not DEEPSEEK_ALLOW_REQUESTS_FALLBACK:
        raise RuntimeError("DeepSeek requests fallback disabled (set DEEPSEEK_ALLOW_REQUESTS_FALLBACK=1).")

    payload = {"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.2, "stream": False}
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
    logger.info("DeepSeek status=%s body=%s", resp.status_code, _redact(resp.text[:900]))

    if "<html" in resp.text.lower() or "just a moment" in resp.text.lower():
        raise RuntimeError(f"DeepSeek gateway returned HTML (likely Cloudflare). status={resp.status_code}")

    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        err_obj = data.get("error") or {}
        err_msg = err_obj.get("message") or err_obj.get("error") or str(err_obj)
        raise RuntimeError(f"DeepSeek API error: {err_msg}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek API returned no choices")
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()

def call_openai(messages: List[Dict[str, str]]) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    if OPENAI_SDK_AVAILABLE and OpenAI is not None:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            timeout=AI_TIMEOUT,
        )
        return (resp.choices[0].message.content or "").strip()

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

    joined = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in messages])
    payload = {"contents": [{"role": "user", "parts": [{"text": joined}]}]}
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
    raise RuntimeError("GROK engine not configured yet (set GROK_BASE_URL/GROK_API_KEY)")

# -----------------------------
# JSON extraction
# -----------------------------
def extract_first_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    if not text:
        return None, "empty_ai_response"
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj, None
        return None, "json_is_not_object"
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj, None
            return None, "json_is_not_object"
        except Exception as e:
            return None, f"json_parse_failed: {str(e)[:120]}"

    return None, "no_json_object_found"

def cx_analyze(input_obj: dict) -> Tuple[Optional[dict], str]:
    messages = [
        {"role": "system", "content": get_cx_prompt()},
        {"role": "user", "content": json.dumps(input_obj, ensure_ascii=False)},
    ]
    raw = ai_chat(messages)
    parsed, err = extract_first_json(raw)
    if parsed is None:
        raise RuntimeError(f"AI returned invalid JSON. err={err}")
    return parsed, raw

# -----------------------------
# Inline keyboard helpers
# -----------------------------
def analysis_keyboard(analysis_id: int, include_reanalyze: bool = False, review_id: Optional[int] = None) -> dict:
    rows = [
        [
            {"text": "✍️ Ответ", "callback_data": f"reply:{analysis_id}"},
            {"text": "⚠️ Жалоба", "callback_data": f"complaint:{analysis_id}"},
        ],
        [
            {"text": "📌 Ответ + жалоба", "callback_data": f"both:{analysis_id}"},
            {"text": "🧾 JSON", "callback_data": f"json:{analysis_id}"},
        ],
    ]
    if include_reanalyze and review_id is not None:
        rows.append([{"text": "🔄 Пересчитать", "callback_data": f"reanalyze_review:{review_id}"}])
    return {"inline_keyboard": rows}

# -----------------------------
# UI texts
# -----------------------------
HELP_TEXT = (
    "Команды:\n"
    "/start — меню\n"
    "/help — помощь\n"
    "/myid — ваш ID\n"
    "/engine — текущий AI_ENGINE\n"
    "/setengine — выбрать движок (кнопки)\n"
    "/setcontext — задать бизнес-контекст (текст)\n"
    "/addreview — добавить отзыв (пошагово)\n"
    "/review <id> — показать отзыв\n"
    "/analyze <текст> — анализ текста (без сохранения)\n"
    "/analyzereview <id> — анализ сохранённого отзыва\n"
    "/find — поиск отзывов (пошагово)\n"
    "/weeklyreport — недельный отчёт\n"
    "/exportcsv — экспорт CSV\n"
    "/contacts — контакты сервиса\n"
    "/diag — самодиагностика\n"
    "/cancel — сброс состояния\n"
)

INSTRUCTION_TEXT = (
    f"🤖 Бот для **{SERVICE_NAME}**.\n\n"
    "**Как пользоваться (очень просто):**\n\n"
    "1. Нажми **➕ Добавить отзыв**\n"
    "2. Выбери метод: **✍️ Ручной ввод** или **🔗 По ссылке**\n"
    "3. Следуй подсказкам бота (площадка, рейтинг, автор, текст)\n"
    "4. Бот сохранит отзыв и предложит **🧠 Проанализировать**\n"
    "5. После анализа появятся кнопки:\n"
    "   **✍️ Ответ** — готовый публичный ответ клиенту\n"
    "   **⚠️ Жалоба** — текст жалобы (если отзыв нарушает правила или ⭐1)\n"
    "   **🧾 JSON** — полный результат анализа (для выгрузки/отчётов)\n\n"
    "**О сервисе 🛠️**\n"
    f"- {SERVICE_NAME}\n"
    f"- Адрес: {SERVICE_ADDRESS}\n"
    f"- Режим работы: {SERVICE_HOURS}\n"
    f"- Телефоны: {', '.join(SERVICE_PHONES)}\n\n"
    "**Если что-то не работает:** нажми **🛠 Самодиагностика** и пришли результат разработчику."
)

UI = {
    "instruction": "📘 Инструкция",
    "help": "📋 Список команд",
    "myid": "🆔 Мой ID",
    "diag": "🛠 Самодиагностика",
    "add_review": "➕ Добавить отзыв",
    "analyze_id": "🧠 Анализ по ID",
    "find": "🔍 Поиск отзывов",
    "weekly": "📊 Недельный отчёт",
    "export": "📤 Экспорт CSV",
    "settings": "⚙️ Настройки",
    "contacts": "☎️ Контакты",
}

LEGACY_LABELS = {
    "instruction": {"Инструкция"},
    "help": {"Список команд", "Команды"},
    "myid": {"Мой ID", "Мой Id"},
    "diag": {"Самодиагностика", "Диагностика"},
    "add_review": {"Добавить отзыв", "Добавить Отзыв"},
    "analyze_id": {"Анализ по ID", "Анализ по Id"},
    "find": {"Поиск", "Поиск отзывов"},
    "weekly": {"Недельный отчет", "Недельный отчёт"},
    "export": {"Экспорт CSV", "Экспорт Csv"},
    "settings": {"Настройки"},
    "contacts": {"Контакты", "📞 Контакты", SERVICE_NAME},
}

def _matches_label(key: str, text_clean: str, text_norm: str) -> bool:
    if text_clean == UI.get(key):
        return True
    for legacy in LEGACY_LABELS.get(key, set()):
        if text_clean == legacy or text_norm == legacy:
            return True
    return False

def contacts_text() -> str:
    phones = "\n".join([f"- {p}" for p in SERVICE_PHONES])
    return (
        f"🚗 {SERVICE_NAME}\n"
        f"📍 Адрес: {SERVICE_ADDRESS}\n"
        f"🕒 Режим работы: {SERVICE_HOURS}\n"
        f"☎️ Телефоны:\n{phones}"
    )

def main_menu_keyboard() -> dict:
    return {
        "keyboard": [
            [UI["instruction"], UI["help"], UI["myid"]],
            [UI["diag"], UI["add_review"], UI["analyze_id"]],
            [UI["find"], UI["weekly"], UI["export"]],
            [UI["contacts"], UI["settings"]],
        ],
        "resize_keyboard": True,
    }

def settings_keyboard(can_manage: bool = False) -> dict:
    rows = [
        [{"text": "Выбор ИИ", "callback_data": "settings:engine"}],
        [{"text": "Бизнес-контекст", "callback_data": "settings:context"}],
    ]
    if can_manage:
        rows.append([{"text": "👥 Управление доступами", "callback_data": "settings:access"}])
    return {"inline_keyboard": rows}

def access_manage_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "📋 Список пользователей", "callback_data": "access:list"}],
            [{"text": "➕ Добавить пользователя", "callback_data": "access:add"}],
            [{"text": "➖ Удалить пользователя", "callback_data": "access:remove"}],
            [{"text": "⬅️ Назад", "callback_data": "access:back"}],
        ]
    }

def engine_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "DeepSeek", "callback_data": "setengine:deepseek"}],
            [{"text": "OpenAI", "callback_data": "setengine:openai"}],
            [{"text": "Gemini", "callback_data": "setengine:gemini"}],
        ]
    }

def rating_keyboard(prefix: str = "rating") -> dict:
    rows = []
    for rating in range(5, 0, -1):
        rows.append([{"text": f"⭐{rating}", "callback_data": f"{prefix}:{rating}"}])
    return {"inline_keyboard": rows}

def link_rating_keyboard() -> dict:
    rows = [[{"text": "Не указан", "callback_data": "link_rating:none"}]]
    for rating in range(5, 0, -1):
        rows.append([{"text": f"⭐{rating}", "callback_data": f"link_rating:{rating}"}])
    return {"inline_keyboard": rows}

def review_method_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✍️ Ручной ввод", "callback_data": "review_method:manual"}],
            [{"text": "🔗 По ссылке", "callback_data": "review_method:link"}],
            [{"text": "❌ Отмена", "callback_data": "review_method:cancel"}],
        ]
    }

def link_platform_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🟡 Яндекс", "callback_data": "link_platform:yandex"}],
            [{"text": "🟢 2ГИС", "callback_data": "link_platform:2gis"}],
            [{"text": "❓ Другое", "callback_data": "link_platform:unknown"}],
        ]
    }

def find_rating_keyboard() -> dict:
    rows = [[{"text": "Любой", "callback_data": "find_rating:any"}]]
    for rating in range(5, 0, -1):
        rows.append([{"text": f"⭐{rating}", "callback_data": f"find_rating:{rating}"}])
    return {"inline_keyboard": rows}

def find_days_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "7 дней", "callback_data": "find_days:7"}],
            [{"text": "30 дней", "callback_data": "find_days:30"}],
            [{"text": "90 дней", "callback_data": "find_days:90"}],
        ]
    }

def _log_route(route: str, chat_id: Optional[int], user_id: Optional[int], detail: str = "") -> None:
    logger.info("route=%s chat_id=%s user_id=%s %s", route, chat_id, user_id, detail)

STATE_NONE = "NONE"
STATE_WAIT_REVIEW_TEXT = "WAIT_REVIEW_TEXT"
STATE_WAIT_REVIEW_METHOD = "WAIT_REVIEW_METHOD"
STATE_WAIT_REVIEW_LINK = "WAIT_REVIEW_LINK"
STATE_WAIT_LINK_PLATFORM = "WAIT_LINK_PLATFORM"
STATE_WAIT_LINK_RATING = "WAIT_LINK_RATING"
STATE_WAIT_LINK_AUTHOR = "WAIT_LINK_AUTHOR"
STATE_WAIT_LINK_TEXT = "WAIT_LINK_TEXT"
STATE_WAIT_PLATFORM = "WAIT_PLATFORM"
STATE_WAIT_RATING = "WAIT_RATING"
STATE_WAIT_DUP_CONFIRM = "WAIT_DUP_CONFIRM"
STATE_WAIT_ANALYZE_ID = "WAIT_ANALYZE_ID"
STATE_WAIT_CONTEXT = "WAIT_CONTEXT"
STATE_FIND_PLATFORM = "FIND_PLATFORM"
STATE_FIND_RATING = "FIND_RATING"
STATE_FIND_DAYS = "FIND_DAYS"
STATE_ACCESS_ADD = "ACCESS_ADD"
STATE_ACCESS_REMOVE = "ACCESS_REMOVE"

def _reset_state(chat_id: int) -> None:
    db_clear_session(chat_id)

def parse_kv_args(text: str) -> Tuple[Dict[str, str], str]:
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
# Background analysis
# -----------------------------
def format_analysis_brief(result_json: dict) -> str:
    sentiment = result_json.get("sentiment") or {}
    sentiment_label = sentiment.get("label") or "unknown"
    sentiment_score = sentiment.get("score")
    summary = (result_json.get("review_summary") or "").strip()
    lines = [f"Тональность: {sentiment_label}"]
    if sentiment_score is not None:
        lines.append(f"Скор: {sentiment_score}")
    if summary:
        lines.append("")
        lines.append(f"Кратко: {summary}")
    return "\n".join(lines)

def notify_admins(text: str) -> None:
    ids = {SUPERADMIN_ID} if SUPERADMIN_ID is not None else set()
    if DB_OK:
        for user in db_list_access_users(active_only=True):
            if user.get("role") in ("owner", "staff"):
                ids.add(user["chat_id"])
    ids.update(ADMIN_CHAT_IDS)
    for cid in sorted({i for i in ids if i is not None}):
        send_message(int(cid), text)

def background_analyze(chat_id: int, user_id: int, review_text: str, platform_hint: str = "unknown",
                      rating: Optional[int] = None, review_id: Optional[int] = None) -> None:
    engine = _current_engine()
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
        "business_context": _business_context(),
        "branch/city": None,
        "meta": {},
    }

    try:
        parsed, _raw = cx_analyze(input_obj)
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
        )
        if analysis_id is None:
            send_message(chat_id, "❌ Не удалось сохранить анализ в БД. Проверь DATABASE_URL и миграции.")
            return

        brief = format_analysis_brief(parsed)
        send_message(
            chat_id,
            f"✅ Анализ готов. ID: {analysis_id}\n\n{brief}",
            reply_markup=analysis_keyboard(analysis_id, include_reanalyze=bool(review_id), review_id=review_id),
        )
    except Exception as e:
        err_text = str(e)
        logger.error("AI exception: %s", err_text)
        logger.exception("AI exception traceback")

        fallback_json = {"_error": "AI failed or returned invalid JSON (see logs)", "engine": engine}
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
        )
        if analysis_id is None:
            send_message(chat_id, "❌ Не удалось сохранить анализ в БД. Проверь DATABASE_URL и миграции.")
            return

        error_type = "unknown"
        if "Cloudflare" in err_text or "returned HTML" in err_text or "just a moment" in err_text.lower():
            error_type = "cloudflare_block"
        elif "status=403" in err_text:
            error_type = "http_403"
        elif "status=429" in err_text:
            error_type = "http_429"
        elif "json" in err_text.lower():
            error_type = "parse_error"

        if error_type == "cloudflare_block":
            msg = "❌ ИИ недоступен: блокировка шлюза (Cloudflare). Попробуй позже или переключи движок."
        else:
            msg = "❌ Не удалось получить валидный JSON от ИИ. Анализ сохранён с ошибкой. ID: %d\nПопробуй ещё раз или переключи CX_PROMPT_MODE=lite." % analysis_id

        send_message(chat_id, msg, reply_markup=analysis_keyboard(analysis_id, include_reanalyze=bool(review_id), review_id=review_id))
        notify_admins("⚠️ Ошибка ИИ при анализе #%s\nengine=%s model=%s\nтип=%s\nоткрой самодиагностику: /diag"
                      % (review_id or analysis_id, engine, model_name or "-", error_type))

# -----------------------------
# Find flow
# -----------------------------
def start_add_review(chat_id: int) -> None:
    if not DB_OK:
        send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
        return
    _reset_state(chat_id)
    db_set_session(chat_id, STATE_WAIT_REVIEW_METHOD, {})
    send_message(chat_id, "Выберите способ добавления отзыва:", reply_markup=review_method_keyboard())

def _clean_meta(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if v is not None}

def _manual_meta(payload: dict, user_id: int) -> dict:
    meta = dict(payload.get("meta") or {})
    meta.setdefault("added_by", user_id)
    meta.setdefault("input_method", "manual")
    return _clean_meta(meta)

def _link_meta(payload: dict) -> dict:
    meta = {
        "source_url": payload.get("source_url"),
        "platform_guess": payload.get("platform_guess"),
        "author_name": payload.get("author_name"),
        "rating_source": "user_confirmed",
        "added_by": payload.get("added_by"),
        "input_method": "link",
    }
    return _clean_meta(meta)

def _insert_link_review(payload: dict) -> Optional[int]:
    review_text = (payload.get("review_text") or "").strip()
    if not review_text:
        return None
    review_hash = payload.get("review_hash") or _hash_review(review_text)
    platform = payload.get("platform") or payload.get("platform_guess") or "unknown"
    return db_insert_review(
        source="link",
        rating=payload.get("rating"),
        review_text=review_text,
        meta=_link_meta(payload),
        platform=platform,
        review_hash=review_hash,
    )

def start_find_flow(chat_id: int) -> None:
    _reset_state(chat_id)
    db_set_session(chat_id, STATE_FIND_PLATFORM, {})
    send_message(
        chat_id,
        "Площадка:",
        reply_markup={
            "inline_keyboard": [
                [{"text": "Все", "callback_data": "find_platform:all"}],
                [{"text": "Яндекс", "callback_data": "find_platform:yandex"}],
                [{"text": "2ГИС", "callback_data": "find_platform:2gis"}],
            ]
        },
    )

def send_find_results(chat_id: int, payload: dict) -> None:
    platform = payload.get("platform")
    rating = payload.get("rating")
    days = int(payload.get("days") or 7)
    offset = int(payload.get("offset") or 0)
    items = db_find_reviews(platform=platform, rating=rating, days=days, limit=10, offset=offset)
    if not items:
        send_message(chat_id, "Ничего не найдено.")
        return
    lines = []
    for it in items:
        lines.append(f"#{it['id']} | {it['created_at'][:10]} | {it.get('platform') or '-'} | ⭐{it.get('rating') or '-'} | {it['preview']}")
    action_rows = []
    for it in items:
        action_rows.append([
            {"text": f"Открыть #{it['id']}", "callback_data": f"open_review:{it['id']}"},
            {"text": f"Анализ #{it['id']}", "callback_data": f"analyze_review:{it['id']}"},
        ])
    action_rows.append([{"text": "⬅️ Назад", "callback_data": "find_page:prev"},
                        {"text": "➡️ Далее", "callback_data": "find_page:next"}])
    send_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": action_rows})

def build_csv_export(rows: List[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "created_at", "platform", "rating", "review_text",
        "source_url", "author_name",
        "analysis_created_at", "sentiment_label", "sentiment_score",
        "public_reply_text", "complaint_needed", "complaint_text",
    ])
    for row in rows:
        writer.writerow([
            row.get("id"),
            row.get("created_at"),
            row.get("platform"),
            row.get("rating"),
            row.get("review_text"),
            row.get("source_url"),
            row.get("author_name"),
            row.get("analysis_created_at"),
            row.get("sentiment_label"),
            row.get("sentiment_score"),
            row.get("public_reply_text"),
            row.get("complaint_needed"),
            row.get("complaint_text"),
        ])
    return output.getvalue().encode("utf-8")

def diag_text(current_user_id: Optional[int] = None) -> str:
    engine = _current_engine()
    prompt_mode = (os.getenv("CX_PROMPT_MODE") or CX_PROMPT_MODE).strip().lower()
    base_url = DEEPSEEK_BASE_URL if engine == "deepseek" else None
    role_current = get_user_role(current_user_id) if current_user_id is not None else None
    allowlist_empty = "yes" if not ADMIN_CHAT_IDS else "no"
    access_count = db_count_access_users(active_only=True) if DB_OK else 0
    review_text_col = "yes" if DB_HAS_TEXT else "no"
    review_review_text_col = "yes" if DB_HAS_REVIEW_TEXT else "no"
    return (
        "Самодиагностика:\n"
        f"- webhook_path: {WEBHOOK_PATH}\n"
        f"- engine: {engine}\n"
        f"- prompt_mode: {prompt_mode}\n"
        f"- deepseek_base_url: {base_url}\n"
        f"- deepseek_key_set: {'yes' if DEEPSEEK_API_KEY else 'no'}\n"
        f"- openai_key_set: {'yes' if OPENAI_API_KEY else 'no'}\n"
        f"- gemini_key_set: {'yes' if GEMINI_API_KEY else 'no'}\n"
        f"- db: {'postgres' if DB_OK else 'disabled'}\n"
        f"- db_last_error: {DB_LAST_ERROR}\n"
        f"- openai_sdk: {OPENAI_SDK_AVAILABLE}\n"
        f"- admin_mode: {ADMIN_MODE}\n"
        f"- admins_count: {len(ADMIN_CHAT_IDS)}\n"
        f"- allowlist_empty: {allowlist_empty}\n"
        f"- role_current_user: {role_current}\n"
        f"- access_users_count_active: {access_count}\n"
        f"- owner_chat_id_detected: {SUPERADMIN_ID}\n"
        f"- ui_labels_version: {UI_VERSION}\n"
        f"- reviews.text_exists: {review_text_col}\n"
        f"- reviews.review_text_exists: {review_review_text_col}\n"
    )

# -----------------------------
# HTTP routes
# -----------------------------
@app.get("/")
def health():
    return jsonify({
        "ok": True,
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "ai_engine": _current_engine(),
        "prompt_mode": (os.getenv("CX_PROMPT_MODE") or CX_PROMPT_MODE).strip().lower(),
        "admin_mode": ADMIN_MODE,
        "db": "postgres" if DB_OK else "disabled",
        "deepseek_url": DEEPSEEK_URL,
        "openai_sdk": OPENAI_SDK_AVAILABLE,
    })

@app.get("/diag/ai")
def diag_ai():
    if DIAG_TOKEN:
        token = request.args.get("token", "").strip()
        if token != DIAG_TOKEN:
            return jsonify({"ok": False, "error": "forbidden"}), 403

    engine = _current_engine()
    prompt_mode = (os.getenv("CX_PROMPT_MODE") or CX_PROMPT_MODE).strip().lower()

    messages = [{"role": "system", "content": "Reply with exactly: OK"}, {"role": "user", "content": "ping"}]
    try:
        raw = ai_chat(messages)
        return jsonify({"ok": True, "engine": engine, "prompt_mode": prompt_mode, "raw_preview": raw[:300]})
    except Exception as e:
        return jsonify({"ok": False, "engine": engine, "prompt_mode": prompt_mode, "error": str(e)[:700]}), 500

@app.get("/cron/weekly")
def cron_weekly():
    if not CRON_TOKEN:
        return jsonify({"ok": False, "error": "CRON_TOKEN not set"}), 400
    token = request.args.get("token", "").strip()
    if token != CRON_TOKEN:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "note": "weekly endpoint kept (implement sending here if needed)"})

# -----------------------------
# Webhook main handler (shortened: your existing logic can stay)
# -----------------------------
@app.post(WEBHOOK_PATH)
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    update_id = update.get("update_id")
    chat_id = None
    user_id = None

    try:
        logger.info("Update: %s", _redact(json.dumps(update, ensure_ascii=False)[:1200]))

        # callback
        if "callback_query" in update:
            cq = update["callback_query"]
            cq_id = cq.get("id", "")
            msg = cq.get("message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            user = cq.get("from") or {}
            user_id = user.get("id")
            data = (cq.get("data") or "").strip()
            sess = _get_active_session(chat_id) if chat_id else None
            logger.info(
                "Trace callback: update_id=%s chat_id=%s user_id=%s data=%r session_state=%s",
                update_id,
                chat_id,
                user_id,
                data,
                sess.get("state") if sess else None,
            )

            if not can_use_bot(user_id):
                _log_route("blocked_callback", chat_id, user_id)
                if chat_id:
                    send_message(chat_id, "⛔ Доступ запрещён. Обратитесь к администратору.")
                if cq_id:
                    answer_callback_query(cq_id, "Доступ запрещён", show_alert=True)
                return "ok"

            if data.startswith("settings:engine"):
                _log_route("settings_engine", chat_id, user_id)
                send_message(chat_id, "Выберите движок ИИ:", reply_markup=engine_keyboard())
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("settings:context"):
                _log_route("settings_context", chat_id, user_id)
                if chat_id:
                    db_set_session(chat_id, STATE_WAIT_CONTEXT, {})
                    send_message(chat_id, "Пришли новый бизнес-контекст одним сообщением.")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("settings:access"):
                _log_route("settings_access", chat_id, user_id)
                if not can_manage_access(user_id):
                    if cq_id:
                        answer_callback_query(cq_id, "Только владелец", show_alert=True)
                    return "ok"
                if chat_id:
                    send_message(chat_id, "Управление доступами:", reply_markup=access_manage_keyboard())
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("setengine:"):
                engine = data.split(":", 1)[1].strip().lower()
                _log_route(f"setengine:{engine}", chat_id, user_id)
                if engine in ("deepseek", "openai", "gemini"):
                    db_set_setting("ai_engine_override", {"value": engine})
                    send_message(chat_id, f"Движок обновлён: {engine}")
                else:
                    send_message(chat_id, "Неизвестный движок.")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("review_method:"):
                method = data.split(":", 1)[1]
                _log_route(f"review_method:{method}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                if method == "cancel":
                    _reset_state(chat_id)
                    send_message(chat_id, "Ок, отменено.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                payload = {"flow": method, "added_by": user_id}
                if method == "manual":
                    payload["meta"] = {"added_by": user_id, "input_method": "manual"}
                    db_set_session(chat_id, STATE_WAIT_REVIEW_TEXT, payload)
                    send_message(chat_id, "Вставь текст отзыва одним сообщением и отправь.\n(Если передумал — напиши /cancel)")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                if method == "link":
                    db_set_session(chat_id, STATE_WAIT_REVIEW_LINK, payload)
                    send_message(chat_id, "Вставь ссылку на отзыв одним сообщением.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"

            if data.startswith("access:"):
                action = data.split(":", 1)[1]
                _log_route(f"access:{action}", chat_id, user_id)
                if not can_manage_access(user_id):
                    if cq_id:
                        answer_callback_query(cq_id, "Только владелец", show_alert=True)
                    return "ok"
                if not chat_id:
                    return "ok"
                if action == "list":
                    if not DB_OK:
                        send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                        answer_callback_query(cq_id, "OK")
                        return "ok"
                    users = db_list_access_users(active_only=True)
                    lines = ["👥 Активные пользователи:"]
                    for u in users:
                        added_at = u.get("added_at")
                        date_str = added_at.strftime("%Y-%m-%d") if isinstance(added_at, datetime) else str(added_at)[:10]
                        added_by = u.get("added_by") or "-"
                        note = f" | {u['note']}" if u.get("note") else ""
                        lines.append(f"- {u['chat_id']} | {u['role']} | добавил: {added_by} | {date_str}{note}")
                    send_message(chat_id, "\n".join(lines))
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                if action == "add":
                    if not DB_OK:
                        send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                        answer_callback_query(cq_id, "OK")
                        return "ok"
                    db_set_session(chat_id, STATE_ACCESS_ADD, {})
                    send_message(chat_id, "Пришли ID пользователя (числом) или пересланное сообщение от пользователя.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                if action == "remove":
                    if not DB_OK:
                        send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                        answer_callback_query(cq_id, "OK")
                        return "ok"
                    users = [u for u in db_list_access_users(active_only=True) if u.get("role") != "owner"]
                    if not users:
                        send_message(chat_id, "Нет активных пользователей для удаления.")
                        answer_callback_query(cq_id, "OK")
                        return "ok"
                    db_set_session(chat_id, STATE_ACCESS_REMOVE, {})
                    rows = []
                    for u in users:
                        label = f"Удалить {u['chat_id']}"
                        rows.append([{"text": label, "callback_data": f"access_remove:{u['chat_id']}"}])
                    send_message(chat_id, "Выбери пользователя для удаления или отправь ID:", reply_markup={"inline_keyboard": rows})
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                if action == "back":
                    send_message(chat_id, "Настройки:", reply_markup=settings_keyboard(can_manage_access(user_id)))
                    answer_callback_query(cq_id, "OK")
                    return "ok"

            if data.startswith("access_remove:"):
                user_raw = data.split(":", 1)[1]
                _log_route(f"access_remove:{user_raw}", chat_id, user_id)
                if not can_manage_access(user_id):
                    if cq_id:
                        answer_callback_query(cq_id, "Только владелец", show_alert=True)
                    return "ok"
                if not chat_id:
                    return "ok"
                try:
                    target_id = int(user_raw)
                except Exception:
                    send_message(chat_id, "Некорректный ID.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                if SUPERADMIN_ID is not None and target_id == SUPERADMIN_ID:
                    send_message(chat_id, "Нельзя удалить владельца.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                if not DB_OK:
                    send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                db_deactivate_access_user(target_id)
                _reset_state(chat_id)
                logger.info("access_remove: owner=%s target=%s", user_id, target_id)
                send_message(chat_id, f"✅ Пользователь {target_id} отключён.")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("link_platform:"):
                platform = data.split(":", 1)[1]
                _log_route(f"link_platform:{platform}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                payload["platform"] = platform
                db_set_session(chat_id, STATE_WAIT_LINK_RATING, payload)
                send_message(chat_id, "Укажи рейтинг:", reply_markup=link_rating_keyboard())
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("link_rating:"):
                rating_raw = data.split(":", 1)[1]
                _log_route(f"link_rating:{rating_raw}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                if rating_raw == "none":
                    payload["rating"] = None
                else:
                    try:
                        payload["rating"] = int(rating_raw)
                    except Exception:
                        payload["rating"] = None
                db_set_session(chat_id, STATE_WAIT_LINK_AUTHOR, payload)
                send_message(chat_id, "Укажи автора (например: инкогнито 1234).")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("platform:"):
                platform = data.split(":", 1)[1]
                _log_route(f"platform:{platform}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                payload["platform"] = platform
                db_set_session(chat_id, STATE_WAIT_RATING, payload)
                send_message(chat_id, "Оцени отзыв:", reply_markup=rating_keyboard())
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("rating:"):
                rating_val = data.split(":", 1)[1]
                _log_route(f"rating:{rating_val}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                review_text = (payload.get("review_text") or "").strip()
                if not review_text:
                    send_message(chat_id, "Текст отзыва не найден. Начни заново: /addreview")
                    _reset_state(chat_id)
                    return "ok"
                try:
                    rating = int(rating_val)
                except Exception:
                    send_message(chat_id, "Некорректный рейтинг. Попробуй снова.")
                    return "ok"
                review_hash = payload.get("review_hash") or _hash_review(review_text)
                review_id = db_insert_review(
                    source="manual",
                    rating=rating,
                    review_text=review_text,
                    meta=_manual_meta(payload, user_id),
                    platform=payload.get("platform"),
                    review_hash=review_hash,
                )
                _reset_state(chat_id)
                if review_id:
                    send_message(
                        chat_id,
                        f"✅ Отзыв добавлен. Номер: #{review_id}",
                        reply_markup={"inline_keyboard": [[{"text": "🧠 Проанализировать", "callback_data": f"analyze_review:{review_id}"}]]},
                    )
                else:
                    send_message(chat_id, "❌ Не удалось сохранить отзыв в БД. Проверь DATABASE_URL, миграции и /diag.")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("dup_confirm:"):
                decision = data.split(":", 1)[1]
                _log_route(f"dup_confirm:{decision}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                if decision == "no":
                    _reset_state(chat_id)
                    send_message(chat_id, "Ок, дубликат не сохраняем.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                if payload.get("flow") == "link":
                    review_id = _insert_link_review(payload)
                    _reset_state(chat_id)
                    if review_id:
                        send_message(
                            chat_id,
                            f"✅ Отзыв добавлен. Номер: #{review_id}",
                            reply_markup={"inline_keyboard": [[{"text": "🧠 Проанализировать", "callback_data": f"analyze_review:{review_id}"}]]},
                        )
                    else:
                        send_message(chat_id, "❌ Не удалось сохранить отзыв в БД. Проверь DATABASE_URL, миграции и /diag.")
                    answer_callback_query(cq_id, "OK")
                    return "ok"
                db_set_session(chat_id, STATE_WAIT_PLATFORM, payload)
                send_message(
                    chat_id,
                    "Дубликат подтверждён. Выбери площадку:",
                    reply_markup={"inline_keyboard": [
                        [{"text": "🟡 Яндекс", "callback_data": "platform:yandex"}],
                        [{"text": "🟢 2ГИС", "callback_data": "platform:2gis"}],
                    ]},
                )
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("find_platform:"):
                platform = data.split(":", 1)[1]
                _log_route(f"find_platform:{platform}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                payload["platform"] = platform
                db_set_session(chat_id, STATE_FIND_RATING, payload)
                send_message(chat_id, "Рейтинг:", reply_markup=find_rating_keyboard())
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("find_rating:"):
                rating_raw = data.split(":", 1)[1]
                _log_route(f"find_rating:{rating_raw}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                if rating_raw == "any":
                    payload["rating"] = None
                else:
                    try:
                        payload["rating"] = int(rating_raw)
                    except Exception:
                        payload["rating"] = None
                db_set_session(chat_id, STATE_FIND_DAYS, payload)
                send_message(chat_id, "Период:", reply_markup=find_days_keyboard())
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("find_days:"):
                days_raw = data.split(":", 1)[1]
                _log_route(f"find_days:{days_raw}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                try:
                    payload["days"] = int(days_raw)
                except Exception:
                    payload["days"] = 7
                payload["offset"] = 0
                db_set_session(chat_id, STATE_FIND_DAYS, payload)
                send_find_results(chat_id, payload)
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("find_page:"):
                action = data.split(":", 1)[1]
                _log_route(f"find_page:{action}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                payload = (sess or {}).get("payload") or {}
                offset = int(payload.get("offset") or 0)
                if action == "next":
                    offset += 10
                elif action == "prev":
                    offset = max(0, offset - 10)
                payload["offset"] = offset
                db_set_session(chat_id, STATE_FIND_DAYS, payload)
                send_find_results(chat_id, payload)
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("open_review:"):
                review_id_raw = data.split(":", 1)[1]
                _log_route(f"open_review:{review_id_raw}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                try:
                    review_id = int(review_id_raw)
                except Exception:
                    send_message(chat_id, "Некорректный ID.")
                    return "ok"
                review = db_get_review(review_id)
                if not review:
                    send_message(chat_id, "Отзыв не найден.")
                    return "ok"
                send_message(
                    chat_id,
                    f"#{review['id']} | {review.get('platform') or '-'} | ⭐{review.get('rating') or '-'}\n{review.get('review_text') or ''}",
                )
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("analyze_review:"):
                review_id_raw = data.split(":", 1)[1]
                _log_route(f"analyze_review:{review_id_raw}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                try:
                    review_id = int(review_id_raw)
                except Exception:
                    send_message(chat_id, "Некорректный ID.")
                    return "ok"
                review = db_get_review(review_id)
                if not review:
                    send_message(chat_id, "Отзыв не найден.")
                    return "ok"
                threading.Thread(
                    target=background_analyze,
                    args=(chat_id, user_id, review.get("review_text") or "", review.get("platform") or "unknown", review.get("rating"), review_id),
                    daemon=True,
                ).start()
                send_message(chat_id, "⏳ Анализ запущен, подожди пару секунд…")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith("reanalyze_review:"):
                review_id_raw = data.split(":", 1)[1]
                _log_route(f"reanalyze_review:{review_id_raw}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                try:
                    review_id = int(review_id_raw)
                except Exception:
                    send_message(chat_id, "Некорректный ID.")
                    return "ok"
                review = db_get_review(review_id)
                if not review:
                    send_message(chat_id, "Отзыв не найден.")
                    return "ok"
                threading.Thread(
                    target=background_analyze,
                    args=(chat_id, user_id, review.get("review_text") or "", review.get("platform") or "unknown", review.get("rating"), review_id),
                    daemon=True,
                ).start()
                send_message(chat_id, "🔄 Пересчёт запущен.")
                answer_callback_query(cq_id, "OK")
                return "ok"

            if data.startswith(("reply:", "complaint:", "both:", "json:")):
                _log_route(f"analysis_action:{data}", chat_id, user_id)
                if not chat_id:
                    return "ok"
                action, analysis_id_raw = data.split(":", 1)
                try:
                    analysis_id = int(analysis_id_raw)
                except Exception:
                    send_message(chat_id, "Некорректный ID анализа.")
                    return "ok"
                analysis = db_get_analysis(analysis_id)
                if not analysis:
                    send_message(chat_id, "Анализ не найден.")
                    return "ok"
                result_json = analysis.get("result_json") or {}
                public_reply = (result_json.get("public_reply") or {}).get("text")
                complaint = (result_json.get("complaint") or {}).get("text")
                if action == "reply":
                    send_message(chat_id, public_reply or "Ответ не найден.")
                elif action == "complaint":
                    send_message(chat_id, complaint or "Жалоба не найдена.")
                elif action == "both":
                    send_message(chat_id, f"Ответ:\n{public_reply or '-'}\n\nЖалоба:\n{complaint or '-'}")
                else:
                    send_message(chat_id, json.dumps(result_json, ensure_ascii=False)[:3500])
                answer_callback_query(cq_id, "OK")
                return "ok"

            answer_callback_query(cq_id, "OK")
            return "ok"

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        user = message.get("from") or {}
        user_id = user.get("id")
        text = message.get("text")
        text = text if isinstance(text, str) else ""
        text_clean = text.strip()
        text_norm = re.sub(r"\s+", " ", text_clean)
        sess = _get_active_session(chat_id) if chat_id else None
        logger.info(
            "Trace message: update_id=%s chat_id=%s user_id=%s text=%r len=%s session_state=%s",
            update_id,
            chat_id,
            user_id,
            text_clean,
            len(text_clean),
            sess.get("state") if sess else None,
        )

        if not chat_id or not user_id:
            return "ok"
        if not can_use_bot(user_id):
            _log_route("blocked_message", chat_id, user_id)
            send_message(chat_id, "⛔ Доступ запрещён. Обратитесь к администратору.")
            return "ok"

        if text_clean == "OK":
            _log_route("ignore_ok", chat_id, user_id)
            return "ok"

        cmd_token = text_clean.split()[0] if text_clean else ""
        cmd = cmd_token.split("@")[0].lower() if cmd_token.startswith("/") else ""
        cmd_args = text_clean[len(cmd_token):].strip() if cmd_token else ""

        if _matches_label("instruction", text_clean, text_norm):
            _log_route("menu_instruction", chat_id, user_id)
            send_message(chat_id, INSTRUCTION_TEXT, parse_mode="Markdown")
            return "ok"
        if _matches_label("help", text_clean, text_norm):
            _log_route("menu_help", chat_id, user_id)
            send_message(chat_id, HELP_TEXT)
            return "ok"
        if _matches_label("myid", text_clean, text_norm):
            _log_route("menu_myid", chat_id, user_id)
            send_message(chat_id, f"Ваш ID: {user_id}")
            return "ok"
        if _matches_label("diag", text_clean, text_norm):
            _log_route("menu_diag", chat_id, user_id)
            send_message(chat_id, diag_text(user_id))
            return "ok"
        if _matches_label("add_review", text_clean, text_norm):
            _log_route("menu_addreview", chat_id, user_id)
            start_add_review(chat_id)
            return "ok"
        if _matches_label("analyze_id", text_clean, text_norm):
            _log_route("menu_analyze_id", chat_id, user_id)
            db_set_session(chat_id, STATE_WAIT_ANALYZE_ID, {})
            send_message(chat_id, "Введи ID отзыва для анализа.")
            return "ok"
        if _matches_label("find", text_clean, text_norm):
            _log_route("menu_find", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            start_find_flow(chat_id)
            return "ok"
        if _matches_label("weekly", text_clean, text_norm):
            _log_route("menu_weekly", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            report = db_weekly_summary()
            if not report.get("ok"):
                send_message(chat_id, f"❌ {report.get('error')}")
                return "ok"
            avg_rating = report.get("avg_rating")
            sentiments = report.get("sentiments") or {}
            msg = (
                f"Недельный отчёт ({report.get('days')} дн.):\n"
                f"- всего анализов: {report.get('total')}\n"
                f"- с ошибкой: {report.get('with_error')}\n"
                f"- средний рейтинг: {avg_rating if avg_rating is not None else 'n/a'}\n"
                f"- тональности: {sentiments}\n"
            )
            send_message(chat_id, msg)
            return "ok"
        if _matches_label("export", text_clean, text_norm):
            _log_route("menu_export", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            rows = db_export_reviews()
            if not rows:
                send_message(chat_id, "Нет данных для экспорта.")
                return "ok"
            send_document(chat_id, "reviews_export.csv", build_csv_export(rows))
            return "ok"
        if _matches_label("settings", text_clean, text_norm):
            _log_route("menu_settings", chat_id, user_id)
            send_message(chat_id, "Настройки:", reply_markup=settings_keyboard(can_manage_access(user_id)))
            return "ok"
        if _matches_label("contacts", text_clean, text_norm):
            _log_route("menu_contacts", chat_id, user_id)
            send_message(chat_id, contacts_text())
            return "ok"

        if cmd == "/start":
            _log_route("start", chat_id, user_id)
            logger.info("Dispatch: matched=/start")
            _reset_state(chat_id)
            name = _display_name(user)
            send_message(
                chat_id,
                (
                    f"Привет, {name}! Бот для {SERVICE_NAME} 🛠️.\n\n"
                    "🛠️ О сервисе:\n"
                    f"- Адрес: {SERVICE_ADDRESS}\n"
                    f"- Режим работы: {SERVICE_HOURS}\n"
                    f"- Телефоны: {', '.join(SERVICE_PHONES)}\n\n"
                    "Выбери действие в меню ниже."
                ),
                reply_markup=main_menu_keyboard(),
            )
            return "ok"

        if cmd == "/help":
            _log_route("help", chat_id, user_id)
            send_message(chat_id, HELP_TEXT)
            return "ok"

        if cmd == "/myid":
            _log_route("myid", chat_id, user_id)
            send_message(chat_id, f"Ваш ID: {user_id}")
            return "ok"

        if cmd == "/contacts":
            _log_route("contacts", chat_id, user_id)
            send_message(chat_id, contacts_text())
            return "ok"

        if cmd == "/diag":
            _log_route("diag", chat_id, user_id)
            send_message(chat_id, diag_text(user_id))
            return "ok"

        if cmd == "/cancel":
            _log_route("cancel", chat_id, user_id)
            _reset_state(chat_id)
            send_message(chat_id, "Состояние сброшено.")
            return "ok"

        if cmd == "/engine":
            _log_route("engine", chat_id, user_id)
            send_message(chat_id, f"Текущий движок: {_current_engine()}")
            return "ok"

        if cmd == "/setengine":
            _log_route("setengine", chat_id, user_id)
            send_message(chat_id, "Выберите движок ИИ:", reply_markup=engine_keyboard())
            return "ok"

        if cmd == "/setcontext":
            _log_route("setcontext", chat_id, user_id)
            db_set_session(chat_id, STATE_WAIT_CONTEXT, {})
            send_message(chat_id, "Пришли новый бизнес-контекст одним сообщением.")
            return "ok"

        if cmd == "/addreview":
            _log_route("addreview", chat_id, user_id)
            start_add_review(chat_id)
            return "ok"

        if cmd == "/find":
            _log_route("find", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            start_find_flow(chat_id)
            return "ok"

        if cmd == "/weeklyreport":
            _log_route("weeklyreport", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            report = db_weekly_summary()
            if not report.get("ok"):
                send_message(chat_id, f"❌ {report.get('error')}")
                return "ok"
            avg_rating = report.get("avg_rating")
            sentiments = report.get("sentiments") or {}
            msg = (
                f"Недельный отчёт ({report.get('days')} дн.):\n"
                f"- всего анализов: {report.get('total')}\n"
                f"- с ошибкой: {report.get('with_error')}\n"
                f"- средний рейтинг: {avg_rating if avg_rating is not None else 'n/a'}\n"
                f"- тональности: {sentiments}\n"
            )
            send_message(chat_id, msg)
            return "ok"

        if cmd == "/exportcsv":
            _log_route("exportcsv", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            rows = db_export_reviews()
            if not rows:
                send_message(chat_id, "Нет данных для экспорта.")
                return "ok"
            send_document(chat_id, "reviews_export.csv", build_csv_export(rows))
            return "ok"

        if cmd == "/review":
            _log_route("review", chat_id, user_id)
            try:
                review_id = int(cmd_args.split()[0])
            except Exception:
                send_message(chat_id, "Укажи ID отзыва: /review 123")
                return "ok"
            review = db_get_review(review_id)
            if not review:
                send_message(chat_id, "Отзыв не найден.")
                return "ok"
            send_message(
                chat_id,
                f"#{review['id']} | {review.get('platform') or '-'} | ⭐{review.get('rating') or '-'}\n{review.get('review_text') or ''}",
            )
            return "ok"

        if cmd == "/analyze":
            _log_route("analyze", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            review_text = cmd_args
            if not review_text:
                send_message(chat_id, "Укажи текст: /analyze <текст>")
                return "ok"
            threading.Thread(
                target=background_analyze,
                args=(chat_id, user_id, review_text, "unknown", None, None),
                daemon=True,
            ).start()
            send_message(chat_id, "⏳ Анализ запущен, подожди пару секунд…")
            return "ok"

        if cmd == "/analyzereview":
            _log_route("analyzereview", chat_id, user_id)
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                return "ok"
            try:
                review_id = int(cmd_args.split()[0])
            except Exception:
                send_message(chat_id, "Укажи ID: /analyzereview 123")
                return "ok"
            review = db_get_review(review_id)
            if not review:
                send_message(chat_id, "Отзыв не найден.")
                return "ok"
            threading.Thread(
                target=background_analyze,
                args=(chat_id, user_id, review.get("review_text") or "", review.get("platform") or "unknown", review.get("rating"), review_id),
                daemon=True,
            ).start()
            send_message(chat_id, "⏳ Анализ запущен, подожди пару секунд…")
            return "ok"

        if sess and sess.get("state") == STATE_WAIT_REVIEW_TEXT:
            _log_route("state_wait_review_text", chat_id, user_id)
            if not text_clean:
                send_message(chat_id, "Текст пустой. Пришли отзыв одним сообщением.")
                return "ok"
            review_text = text_clean
            review_hash = _hash_review(review_text)
            payload = sess.get("payload") or {}
            payload["review_text"] = review_text
            payload["review_hash"] = review_hash
            payload["added_by"] = user_id
            duplicate = db_find_duplicate_review(review_hash) if DB_OK else None
            if duplicate:
                db_set_session(chat_id, STATE_WAIT_DUP_CONFIRM, payload)
                send_message(
                    chat_id,
                    f"⚠️ Найден дубликат #{duplicate['id']} от {duplicate['created_at'][:10]}. Сохранить всё равно?",
                    reply_markup={"inline_keyboard": [
                        [{"text": "Да, сохранить", "callback_data": "dup_confirm:yes"}],
                        [{"text": "Нет", "callback_data": "dup_confirm:no"}],
                    ]},
                )
                return "ok"
            db_set_session(chat_id, STATE_WAIT_PLATFORM, payload)
            send_message(
                chat_id,
                "Выбери площадку:",
                reply_markup={"inline_keyboard": [
                    [{"text": "🟡 Яндекс", "callback_data": "platform:yandex"}],
                    [{"text": "🟢 2ГИС", "callback_data": "platform:2gis"}],
                ]},
            )
            return "ok"

        if sess and sess.get("state") == STATE_WAIT_REVIEW_LINK:
            _log_route("state_wait_review_link", chat_id, user_id)
            if not text_clean:
                send_message(chat_id, "Ссылка пустая. Пришли ссылку одним сообщением.")
                return "ok"
            payload = sess.get("payload") or {}
            payload["source_url"] = text_clean
            payload["platform_guess"] = _guess_platform_from_url(text_clean)
            db_set_session(chat_id, STATE_WAIT_LINK_PLATFORM, payload)
            send_message(chat_id, "Выбери площадку (или оставь «Другое»):", reply_markup=link_platform_keyboard())
            return "ok"

        if sess and sess.get("state") == STATE_WAIT_LINK_AUTHOR:
            _log_route("state_wait_link_author", chat_id, user_id)
            if not text_clean:
                send_message(chat_id, "Укажи автора текста (можно «неизвестно»).")
                return "ok"
            payload = sess.get("payload") or {}
            payload["author_name"] = text_clean
            db_set_session(chat_id, STATE_WAIT_LINK_TEXT, payload)
            send_message(chat_id, "Вставь текст отзыва (обязательно).")
            return "ok"

        if sess and sess.get("state") == STATE_WAIT_LINK_TEXT:
            _log_route("state_wait_link_text", chat_id, user_id)
            if not text_clean:
                send_message(chat_id, "Текст отзыва пустой. Пришли текст одним сообщением.")
                return "ok"
            payload = sess.get("payload") or {}
            payload["review_text"] = text_clean
            payload["review_hash"] = _hash_review(text_clean)
            payload["added_by"] = user_id
            duplicate = db_find_duplicate_review(payload["review_hash"]) if DB_OK else None
            if duplicate:
                db_set_session(chat_id, STATE_WAIT_DUP_CONFIRM, payload)
                send_message(
                    chat_id,
                    f"⚠️ Найден дубликат #{duplicate['id']} от {duplicate['created_at'][:10]}. Сохранить всё равно?",
                    reply_markup={"inline_keyboard": [
                        [{"text": "Да, сохранить", "callback_data": "dup_confirm:yes"}],
                        [{"text": "Нет", "callback_data": "dup_confirm:no"}],
                    ]},
                )
                return "ok"
            review_id = _insert_link_review(payload)
            _reset_state(chat_id)
            if review_id:
                send_message(
                    chat_id,
                    f"✅ Отзыв добавлен. Номер: #{review_id}",
                    reply_markup={"inline_keyboard": [[{"text": "🧠 Проанализировать", "callback_data": f"analyze_review:{review_id}"}]]},
                )
            else:
                send_message(chat_id, "❌ Не удалось сохранить отзыв в БД. Проверь DATABASE_URL, миграции и /diag.")
            return "ok"

        if sess and sess.get("state") == STATE_WAIT_ANALYZE_ID:
            _log_route("state_wait_analyze_id", chat_id, user_id)
            try:
                review_id = int(re.findall(r"\d+", text_clean)[0])
            except Exception:
                send_message(chat_id, "Укажи числовой ID отзыва.")
                return "ok"
            review = db_get_review(review_id)
            if not review:
                send_message(chat_id, "Отзыв не найден.")
                return "ok"
            threading.Thread(
                target=background_analyze,
                args=(chat_id, user_id, review.get("review_text") or "", review.get("platform") or "unknown", review.get("rating"), review_id),
                daemon=True,
            ).start()
            _reset_state(chat_id)
            send_message(chat_id, "⏳ Анализ запущен, подожди пару секунд…")
            return "ok"

        if sess and sess.get("state") == STATE_ACCESS_ADD:
            _log_route("state_access_add", chat_id, user_id)
            if not can_manage_access(user_id):
                send_message(chat_id, "⛔ Доступ запрещён.")
                _reset_state(chat_id)
                return "ok"
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                _reset_state(chat_id)
                return "ok"
            target_id = None
            forward_from = message.get("forward_from") or {}
            if forward_from.get("id"):
                target_id = int(forward_from["id"])
            if target_id is None:
                match = re.findall(r"\d+", text_clean)
                if match:
                    target_id = int(match[0])
            if target_id is None:
                send_message(chat_id, "Не смог определить ID. Пришли число или пересланное сообщение.")
                return "ok"
            role = "staff"
            db_upsert_access_user(target_id, role, user_id)
            logger.info("access_add: owner=%s target=%s role=%s", user_id, target_id, role)
            _reset_state(chat_id)
            send_message(chat_id, f"✅ Пользователь {target_id} добавлен как {role}.")
            return "ok"

        if sess and sess.get("state") == STATE_ACCESS_REMOVE:
            _log_route("state_access_remove", chat_id, user_id)
            if not can_manage_access(user_id):
                send_message(chat_id, "⛔ Доступ запрещён.")
                _reset_state(chat_id)
                return "ok"
            if not DB_OK:
                send_message(chat_id, "DB disabled. Проверь DATABASE_URL или /diag.")
                _reset_state(chat_id)
                return "ok"
            match = re.findall(r"\d+", text_clean)
            if not match:
                send_message(chat_id, "Пришли числовой ID пользователя.")
                return "ok"
            target_id = int(match[0])
            if SUPERADMIN_ID is not None and target_id == SUPERADMIN_ID:
                send_message(chat_id, "Нельзя удалить владельца.")
                _reset_state(chat_id)
                return "ok"
            db_deactivate_access_user(target_id)
            logger.info("access_remove: owner=%s target=%s", user_id, target_id)
            _reset_state(chat_id)
            send_message(chat_id, f"✅ Пользователь {target_id} отключён.")
            return "ok"

        if sess and sess.get("state") == STATE_WAIT_CONTEXT:
            _log_route("state_wait_context", chat_id, user_id)
            db_set_setting("business_context", {"value": text_clean})
            _reset_state(chat_id)
            send_message(chat_id, "Бизнес-контекст обновлён.")
            return "ok"

        if sess and sess.get("state") in (
            STATE_WAIT_REVIEW_METHOD,
            STATE_WAIT_PLATFORM,
            STATE_WAIT_RATING,
            STATE_WAIT_DUP_CONFIRM,
            STATE_FIND_PLATFORM,
            STATE_FIND_RATING,
            STATE_FIND_DAYS,
            STATE_WAIT_LINK_PLATFORM,
            STATE_WAIT_LINK_RATING,
        ):
            _log_route(f"state_pending_buttons:{sess.get('state')}", chat_id, user_id)
            send_message(chat_id, "Используй кнопки под сообщением или /cancel.")
            return "ok"

        _log_route("fallback", chat_id, user_id)
        if text_clean:
            send_message(chat_id, "Не понимаю команду. Открой меню или /help.")
        return "ok"

    except Exception:
        logger.exception("telegram_webhook exception")
        if chat_id and can_use_bot(user_id):
            send_message(chat_id, "⚠️ Ошибка обработки. См. /diag")
        notify_admins("⚠️ Ошибка обработки. См. /diag")
        return "ok"

# -----------------------------
# Startup
# -----------------------------
db_init()
set_webhook_once()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
