import csv
import importlib.util
import io
import logging
import os
import re
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

from services.ai_service import AIService, normalize_date_string
from services.outgoing_queue import (
    clear_failed_messages,
    enqueue_document,
    enqueue_message,
    get_failed_messages,
    get_last_queue_error,
    get_outgoing_by_id,
    get_queue_stats,
    is_queue_enabled,
    process_outgoing_queue,
    retry_failed_messages,
    store_outgoing_file,
)
from services.telegram_api import (
    answer_callback_query as safe_answer_callback_query,
    configure_telegram,
    send_document as safe_send_document,
    send_message as safe_send_message,
    tg_request,
)
from storage import (
    clear_session,
    get_session,
    load_storage,
    next_ticket_id,
    now_iso,
    save_session,
    save_storage,
    ttl_iso,
)

CLIENT_BOT_BUILD = "build-2026-02-06-a"
print(f"[client_bot] build={CLIENT_BOT_BUILD}")

VERSION = "0.4.0"
POLLING_TIMEOUT = 30
POLLING_SLEEP_SECONDS = 1
TTL_HOURS = 24
OUTGOING_QUEUE_INTERVAL_SECONDS = 3

MENU_BOOKING = "📅 Записаться на сервис"
MENU_WARRANTY = "✅ Гарантия / повторная проблема"
MENU_REPAIR = "🔧 Ремонт (что беспокоит)"
MENU_PARTS = "🧩 Запчасти"
MENU_LAST_VISIT = "🧾 Вопрос по прошлому визиту"
MENU_OTHER = "❓ Другое"
MENU_DIRECTIONS = "📍 Как проехать"
MENU_MASTER = "👨‍🔧 Связаться с мастером / Написать мастеру"
UNIVERSAL_QUESTION = "Опишите, пожалуйста, коротко, с чем вы обращаетесь."
FALLBACK_AI_UNAVAILABLE = (
    "Я сейчас работаю в стандартном режиме. "
    "Задам несколько уточняющих вопросов и передам информацию мастеру."
)
FALLBACK_NOT_UNDERSTOOD = (
    "Я могу ошибиться. Напишите, пожалуйста, чуть подробнее — я передам это мастеру."
)
FALLBACK_OUT_OF_SCOPE = "Я передам ваш вопрос мастеру, он свяжется с вами."

YES_OPTIONS = {"да", "yes", "ага"}
NO_OPTIONS = {"нет", "no"}
ADMIN_PAGE_SIZE = 5
ADMIN_LOG_LINES = 200
ADMIN_STATE_NONE = "none"
ADMIN_STATE_ADD_ADMIN = "await_admin_id"
ADMIN_STATE_ADD_BLOCK = "await_block_id"
ADMIN_STATE_EXPORT_RANGE = "await_export_range"
ADMIN_STATE_EXPORT_STATUS = "await_export_status"
ADMIN_STATE_EXPORT_FORMAT = "await_export_format"
ADMIN_STATE_ASK_MORE_TEXT = "await_ask_more_text"
ADMIN_STATE_REPORT_RANGE = "await_report_range"
ADMIN_STATE_REPORT_TYPE = "await_report_type"
ADMIN_STATE_REPORT_WEEKEND = "await_report_weekend"

CALLBACK_DEBOUNCE_WINDOW_SECONDS = 2
CALLBACK_DEBOUNCE_TTL_SECONDS = 60
CALLBACK_DEBOUNCE_LIMIT = 5000

CALLBACK_DEBOUNCE_CACHE: dict[tuple[int, str], float] = {}

STATUS_NEW = "new"
STATUS_IN_PROGRESS = "in_progress"
STATUS_WAITING_CLIENT = "waiting_client"
STATUS_DONE = "done"
STATUS_CANONICAL = {
    "new": STATUS_NEW,
    "in_work": STATUS_IN_PROGRESS,
    "in_progress": STATUS_IN_PROGRESS,
    "waiting_client": STATUS_WAITING_CLIENT,
    "closed": STATUS_DONE,
    "done": STATUS_DONE,
}

AI_ASK_BLOCKLIST = {
    "pdn",
    "was_here",
    "parts_offer_booking",
    "repair_offer_booking",
    "booking_date",
    "booking_time",
    "last_visit_category",
}
LAST_VISIT_CATEGORIES = {"Гарантия", "Повтор проблемы", "Документы", "Уточнение", "Другое"}
ASK_MORE_OPTIONS = [
    ("vin", "VIN"),
    ("plate", "Госномер"),
    ("phone", "Телефон"),
    ("symptom", "Точный симптом/шум/условия"),
    ("booking", "Желаемое время/дата"),
    ("other", "Другое (свободный текст)"),
]
WEEKEND_DAYS = {5, 6}
WEEKDAY_ALIASES = {
    0: {"пн", "понедельник"},
    1: {"вт", "вторник"},
    2: {"ср", "среда"},
    3: {"чт", "четверг", "четв"},
    4: {"пт", "пятница"},
    5: {"сб", "суббота"},
    6: {"вс", "воскресенье"},
}

CLIENT_MENU_ACTIONS = {
    MENU_BOOKING: "booking",
    MENU_WARRANTY: "last_visit",
    MENU_REPAIR: "repair",
    MENU_PARTS: "parts",
    MENU_LAST_VISIT: "last_visit",
    MENU_OTHER: "other",
    MENU_DIRECTIONS: "directions",
}


def build_logger(timezone: str) -> logging.Logger:
    log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    tz = ZoneInfo(timezone)

    def format_time(record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    formatter.formatTime = format_time

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    for name in ("client_bot", "ai", "polling", "admin", "storage"):
        logging.getLogger(name).setLevel(logging.INFO)

    return logging.getLogger("client_bot")


def build_main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": MENU_BOOKING, "callback_data": "menu:booking"}],
            [{"text": MENU_WARRANTY, "callback_data": "menu:warranty"}],
            [
                {"text": MENU_REPAIR, "callback_data": "menu:repair"},
                {"text": MENU_PARTS, "callback_data": "menu:parts"},
            ],
            [
                {"text": MENU_LAST_VISIT, "callback_data": "menu:last_visit"},
                {"text": MENU_OTHER, "callback_data": "menu:other"},
            ],
            [{"text": MENU_DIRECTIONS, "callback_data": "menu:directions"}],
        ],
    }


def is_client_menu_text(text: str) -> bool:
    return text in CLIENT_MENU_ACTIONS


def resolve_menu_action(text: str) -> str | None:
    return CLIENT_MENU_ACTIONS.get(text)


def build_master_keyboard(master_username: str) -> dict:
    username = master_username.lstrip("@")
    return {
        "inline_keyboard": [
            [{"text": "Связаться с мастером", "url": f"https://t.me/{username}"}]
        ]
    }


def build_directions_keyboard() -> dict:
    address = "Удмуртская, 10"
    yandex_url = f"https://yandex.ru/maps/?text={requests.utils.quote(address)}"
    google_url = (
        "https://www.google.com/maps/search/?api=1&query="
        f"{requests.utils.quote(address)}"
    )
    return {
        "inline_keyboard": [
            [{"text": "🗺 Открыть в Яндекс Картах", "url": yandex_url}],
            [{"text": "🗺 Открыть в Google Maps", "url": google_url}],
        ]
    }


def build_pdn_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Согласен"}, {"text": "Не согласен"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def build_was_here_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Да"}, {"text": "Нет"}, {"text": "Не уверен"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def build_yes_no_keyboard() -> dict:
    return {
        "keyboard": [[{"text": "Да"}, {"text": "Нет"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def is_openpyxl_available() -> bool:
    return importlib.util.find_spec("openpyxl") is not None


def build_last_visit_category_keyboard() -> dict:
    return {
        "keyboard": [
            [{"text": "Гарантия"}, {"text": "Повтор проблемы"}],
            [{"text": "Документы"}, {"text": "Уточнение"}],
            [{"text": "Другое"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def sanitize_reply_markup(reply_markup: dict | None) -> dict | None:
    if not reply_markup or not isinstance(reply_markup, dict):
        return None
    if "inline_keyboard" in reply_markup:
        keyboard = reply_markup.get("inline_keyboard")
        if not isinstance(keyboard, list) or not keyboard:
            return None
        sanitized_rows: list[list[dict]] = []
        for row in keyboard:
            if not isinstance(row, list) or not row:
                return None
            sanitized_buttons: list[dict] = []
            for button in row:
                if not isinstance(button, dict):
                    return None
                text = button.get("text")
                if not isinstance(text, str) or not text:
                    return None
                if "url" in button:
                    url = button.get("url")
                    if not isinstance(url, str) or not url:
                        return None
                    sanitized_buttons.append({"text": text, "url": url})
                elif "callback_data" in button:
                    callback_data = button.get("callback_data")
                    if not isinstance(callback_data, str) or not callback_data:
                        return None
                    if len(callback_data) >= 64:
                        return None
                    sanitized_buttons.append({"text": text, "callback_data": callback_data})
                else:
                    return None
            sanitized_rows.append(sanitized_buttons)
        return {"inline_keyboard": sanitized_rows}
    if "keyboard" in reply_markup:
        keyboard = reply_markup.get("keyboard")
        if not isinstance(keyboard, list) or not keyboard:
            return None
        for row in keyboard:
            if not isinstance(row, list) or not row:
                return None
            for button in row:
                if not isinstance(button, dict):
                    return None
                text = button.get("text")
                if not isinstance(text, str) or not text:
                    return None
        return reply_markup
    return None


def send_message(token: str, chat_id: int, text: str, reply_markup: dict | None = None) -> bool:
    sanitized_markup = sanitize_reply_markup(reply_markup)
    return safe_send_message(chat_id, text, reply_markup=sanitized_markup)


def send_document(token: str, chat_id: int, file_path: str, caption: str | None = None) -> bool:
    return safe_send_document(chat_id, file_path, caption=caption)


def answer_callback_query(token: str, callback_query_id: str, text: str | None = None) -> None:
    safe_answer_callback_query(callback_query_id, text=text)


def is_duplicate_callback(storage: dict, callback_id: str | None, ttl_seconds: int = 30) -> bool:
    if not callback_id:
        return False
    ensure_storage_defaults(storage)
    entries: dict[str, float] = storage.setdefault("callback_debounce", {})
    now_value = time.time()
    expired = [key for key, value in entries.items() if now_value - value > ttl_seconds]
    for key in expired:
        entries.pop(key, None)
    if callback_id in entries:
        return True
    entries[callback_id] = now_value
    save_storage(storage)
    return False


def parse_master_usernames_with_meta(raw: str, logger: logging.Logger) -> tuple[list[str], bool, bool]:
    usernames = []
    has_numeric = False
    has_empty = False
    for item in raw.split(","):
        cleaned = item.strip()
        if not cleaned:
            has_empty = True
            logger.warning("[client_bot] MASTER_USERNAMES has empty entry")
            continue
        cleaned = cleaned.lstrip("@").strip()
        if not cleaned:
            has_empty = True
            logger.warning("[client_bot] MASTER_USERNAMES has empty entry")
            continue
        if cleaned.isdigit():
            has_numeric = True
            logger.warning("[client_bot] MASTER_USERNAMES entry is numeric; ignoring: %s", cleaned)
            continue
        usernames.append(f"@{cleaned}")
    return usernames, has_numeric, has_empty


def parse_master_usernames() -> list[str]:
    raw = os.getenv("MASTER_USERNAMES", "")
    if not raw.strip():
        return []
    logger = logging.getLogger("client_bot")
    usernames, _, _ = parse_master_usernames_with_meta(raw, logger)
    return usernames


def get_master_recipients(storage: dict) -> list[str | int]:
    usernames = parse_master_usernames()
    admin_ids = sorted(get_admin_ids(storage))
    combined: list[str | int] = []
    seen: set[str | int] = set()
    for item in usernames + admin_ids:
        if item in seen:
            continue
        seen.add(item)
        combined.append(item)
    return combined


def get_master_contact_username(logger: logging.Logger) -> tuple[str | None, bool, bool]:
    raw = os.getenv("MASTER_USERNAMES", "")
    if not raw.strip():
        return None, False, True
    usernames, has_numeric, has_empty = parse_master_usernames_with_meta(raw, logger)
    if usernames:
        return usernames[0], False, False
    if has_numeric:
        return None, True, False
    return None, False, has_empty


def parse_csv_ints(raw: str | None) -> list[int]:
    if not raw:
        return []
    values = []
    for item in raw.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            values.append(int(cleaned))
        except ValueError:
            continue
    return values


def parse_single_int(raw: str | None) -> list[int]:
    if not raw:
        return []
    cleaned = raw.strip()
    if cleaned.isdigit():
        return [int(cleaned)]
    return []


def get_env_value(primary: str, fallback: str, default: str = "") -> str:
    primary_value = os.getenv(primary)
    if primary_value is not None:
        return primary_value.strip()
    fallback_value = os.getenv(fallback)
    if fallback_value is None:
        return default
    return fallback_value.strip()


def get_client_env_value(primary: str, default: str = "") -> str:
    primary_value = os.getenv(primary)
    if primary_value is None:
        return default
    return primary_value.strip()


def get_client_env_int(primary: str, default: int) -> int:
    raw_value = get_client_env_value(primary, "")
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def get_ai_config_source() -> str:
    keys = [
        "CLIENT_DEEPSEEK_API_KEY",
        "CLIENT_DEEPSEEK_BASE_URL",
        "CLIENT_DEEPSEEK_MODEL",
        "CLIENT_AI_TIMEOUT_SECONDS",
        "CLIENT_FORCE_FALLBACK",
    ]
    if any(os.getenv(key) for key in keys):
        return "CLIENT_*"
    return "missing"


def get_env_int(primary: str, fallback: str, default: int) -> int:
    raw_value = get_env_value(primary, fallback, "")
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def ensure_storage_defaults(storage: dict) -> None:
    storage.setdefault("tickets", [])
    storage.setdefault("sessions", {})
    storage.setdefault("admin_sessions", {})
    storage.setdefault("admins", [])
    storage.setdefault("settings", {})
    storage.setdefault("blocklist", [])
    storage.setdefault("outgoing_messages", [])
    storage.setdefault("callback_debounce", {})
    settings = storage.setdefault("settings", {})
    force_fallback_env = get_env_value("CLIENT_FORCE_FALLBACK", "FORCE_FALLBACK", "0")
    settings.setdefault("force_fallback", 1 if force_fallback_env == "1" else 0)
    settings.setdefault(
        "ai_timeout_seconds",
        get_client_env_int("CLIENT_AI_TIMEOUT_SECONDS", 10),
    )
    settings.setdefault(
        "reminder_minutes",
        get_env_int("CLIENT_REMINDER_MINUTES", "REMINDER_MINUTES", 30),
    )
    settings.setdefault(
        "reaction_minutes",
        get_env_int("CLIENT_REACTION_MINUTES", "REACTION_MINUTES", 30),
    )
    settings.setdefault(
        "auto_reply_hours",
        get_env_int("CLIENT_AUTO_REPLY_HOURS", "AUTO_REPLY_HOURS", 6),
    )
    storage.setdefault("start_clicks", {})
    normalize_ticket_statuses(storage)


def get_settings(storage: dict) -> dict:
    ensure_storage_defaults(storage)
    settings = storage.get("settings", {})
    return {
        "force_fallback": int(settings.get("force_fallback", 0)),
        "ai_timeout_seconds": int(settings.get("ai_timeout_seconds", 10)),
        "reminder_minutes": int(settings.get("reminder_minutes", 30)),
        "reaction_minutes": int(settings.get("reaction_minutes", 30)),
        "auto_reply_hours": int(settings.get("auto_reply_hours", 6)),
    }


def get_admin_ids(storage: dict) -> set[int]:
    ensure_storage_defaults(storage)
    ids, _ = get_admin_ids_with_source()
    return ids


def get_admin_ids_with_source() -> tuple[set[int], str]:
    env_priority = (
        ("CLIENT_ADMIN_IDS", parse_csv_ints),
        ("ADMIN_IDS", parse_csv_ints),
        ("SUPERADMIN_ID", parse_single_int),
        ("SUPERADMIN_IDS", parse_csv_ints),
    )
    for env_name, parser in env_priority:
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        parsed = parser(raw_value)
        return set(parsed), env_name
    return set(), "none"


def record_start_click(storage: dict, payload: str, chat_id: int | None) -> None:
    if not payload:
        return
    storage.setdefault("start_clicks", {})
    stats = storage["start_clicks"].setdefault(payload, {"count": 0, "last_clicked_at": None})
    stats["count"] = int(stats.get("count", 0)) + 1
    stats["last_clicked_at"] = now_iso(os.getenv("TIMEZONE", "Europe/Moscow"))
    if chat_id:
        stats["last_chat_id"] = chat_id


def mask_username(username: str | None) -> str:
    if not username:
        return "@—"
    cleaned = username.lstrip("@")
    if not cleaned:
        return "@—"
    if len(cleaned) == 1:
        return f"@{cleaned}***"
    return f"@{cleaned[0]}***{cleaned[-1]}"


def log_admin_denied(
    logger: logging.Logger,
    user_id: int | None,
    username: str | None,
    admins_source: str,
    admins_count: int,
) -> None:
    logger.warning(
        "[client_bot] admin check denied: user_id=%s, username=%s, admins_source=%s, admins_count=%s",
        user_id,
        username or "—",
        admins_source,
        admins_count,
    )


def check_admin_access(
    chat_id: int | None,
    username: str | None,
    logger: logging.Logger,
) -> bool:
    admin_ids, admins_source = get_admin_ids_with_source()
    admins_count = len(admin_ids)
    if not admin_ids and admins_source == "none":
        logger.warning("[client_bot] admins list is empty (env not set)")
    if chat_id is None or chat_id not in admin_ids:
        log_admin_denied(logger, chat_id, username, admins_source, admins_count)
        return False
    return True


def is_admin(chat_id: int | None, storage: dict) -> bool:
    if chat_id is None:
        return False
    return chat_id in get_admin_ids(storage)


def get_admin_session(storage: dict, chat_id: int) -> dict:
    ensure_storage_defaults(storage)
    return storage.setdefault("admin_sessions", {}).get(str(chat_id), {"state": ADMIN_STATE_NONE})


def set_admin_session(storage: dict, chat_id: int, state: str, data: dict | None = None) -> None:
    ensure_storage_defaults(storage)
    payload = {"state": state, "data": data or {}}
    storage.setdefault("admin_sessions", {})[str(chat_id)] = payload


def clear_admin_session(storage: dict, chat_id: int) -> None:
    ensure_storage_defaults(storage)
    storage.setdefault("admin_sessions", {}).pop(str(chat_id), None)


def format_was_here(value: str | None) -> str:
    mapping = {"yes": "Да", "no": "Нет", "unknown": "Не уверен"}
    return mapping.get(value or "", "—")


def format_scenario(value: str | None) -> str:
    mapping = {
        "booking": "Запись",
        "last_visit": "Прошлый визит",
        "parts": "Запчасти",
        "repair": "Ремонт",
        "other": "Другое",
    }
    return mapping.get(value or "", "—")


def stage_description(stage: str | None) -> str:
    mapping = {
        "fio": "ожидаем ФИО",
        "phone": "ожидаем телефон",
        "pdn": "ожидаем согласие ПДн",
        "was_here": "ожидаем ответ про прошлые визиты",
        "car_plate": "ожидаем госномер",
        "car_vin": "ожидаем VIN",
        "car_make_required": "ожидаем марку/модель",
        "booking_purpose": "ожидаем цель визита",
        "booking_date": "ожидаем дату записи",
        "booking_time": "ожидаем время записи",
        "last_visit_date": "ожидаем дату прошлого визита",
        "last_visit_category": "ожидаем категорию вопроса",
        "last_visit_description": "ожидаем описание вопроса",
        "parts_text": "ожидаем запрос по запчастям",
        "parts_offer_booking": "ожидаем ответ о записи на сервис",
        "repair_text": "ожидаем описание проблемы",
        "repair_offer_booking": "ожидаем ответ о записи на сервис",
        "other_text": "ожидаем описание вопроса",
    }
    return mapping.get(stage or "", "ожидаем действие клиента")


def normalize_ticket_status(value: str | None) -> str:
    return STATUS_CANONICAL.get(value or "", STATUS_NEW)


def normalize_ticket_statuses(storage: dict) -> None:
    for ticket in storage.get("tickets", []):
        ticket["status"] = normalize_ticket_status(ticket.get("status"))


def parse_ticket_date(ticket: dict, timezone: str) -> datetime | None:
    booking_date = ticket.get("booking_date")
    if booking_date:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                parsed = datetime.strptime(str(booking_date), fmt)
                return parsed.replace(tzinfo=ZoneInfo(timezone))
            except ValueError:
                continue
    created_at = ticket.get("created_at")
    if created_at:
        try:
            return datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
        except ValueError:
            return None
    return None


def ticket_day_type(ticket: dict, timezone: str) -> str:
    parsed = parse_ticket_date(ticket, timezone)
    if not parsed:
        return "—"
    return "Выходной" if parsed.weekday() in WEEKEND_DAYS else "Будний"


def ticket_wait_minutes(ticket: dict, timezone: str) -> int:
    created_at = ticket.get("created_at")
    if not created_at:
        return 0
    try:
        created_dt = datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
    except ValueError:
        return 0
    delta = datetime.now(ZoneInfo(timezone)) - created_dt
    return max(0, int(delta.total_seconds() // 60))


def is_reaction_overdue(ticket: dict, timezone: str, reaction_minutes: int) -> bool:
    if normalize_ticket_status(ticket.get("status")) != STATUS_NEW:
        return False
    if reaction_minutes <= 0:
        return False
    return ticket_wait_minutes(ticket, timezone) >= reaction_minutes


def sort_tickets_smart_queue(tickets: list[dict], timezone: str) -> list[dict]:
    def sort_key(item: dict) -> tuple[int, int, int, str]:
        is_weekend = 1 if ticket_day_type(item, timezone) == "Выходной" else 0
        status = normalize_ticket_status(item.get("status"))
        is_new = 1 if status == STATUS_NEW else 0
        wait_minutes = ticket_wait_minutes(item, timezone)
        created_at = item.get("created_at") or ""
        return (-is_weekend, -is_new, -wait_minutes, created_at)

    return sorted(tickets, key=sort_key)


def build_master_status_keyboard(ticket: dict) -> dict:
    ticket_id = ticket.get("ticket_id", "")
    keyboard: list[list[dict]] = [
        [
            {"text": "▶️ В работу", "callback_data": f"ticket:{ticket_id}:{STATUS_IN_PROGRESS}"},
            {"text": "⏳ Ожидает клиента", "callback_data": f"ticket:{ticket_id}:{STATUS_WAITING_CLIENT}"},
        ],
        [
            {"text": "✅ Закрыть", "callback_data": f"ticket:{ticket_id}:{STATUS_DONE}"},
        ]
    ]
    row: list[dict] = []
    username = ticket.get("client_username")
    if username:
        row.append({"text": "💬 Написать клиенту", "url": f"https://t.me/{username.lstrip('@')}"})
    else:
        row.append({"text": "💬 Написать клиенту", "callback_data": f"client:{ticket_id}"})
    row.append({"text": "✍️ Запросить уточнение", "callback_data": f"ticket:{ticket_id}:ask_more"})
    keyboard.append(row)
    return {"inline_keyboard": keyboard}


def should_skip_ticket_reuse(text: str) -> bool:
    cleaned = text.strip().lower()
    if cleaned.startswith("/cancel"):
        return True
    if cleaned.startswith("/start") and "reset" in cleaned:
        return True
    return False


def _prune_debounce_cache(now_value: float) -> None:
    if len(CALLBACK_DEBOUNCE_CACHE) <= CALLBACK_DEBOUNCE_LIMIT:
        cutoff = now_value - CALLBACK_DEBOUNCE_TTL_SECONDS
        stale_keys = [key for key, timestamp in CALLBACK_DEBOUNCE_CACHE.items() if timestamp < cutoff]
        for key in stale_keys:
            CALLBACK_DEBOUNCE_CACHE.pop(key, None)
        return
    sorted_items = sorted(CALLBACK_DEBOUNCE_CACHE.items(), key=lambda item: item[1])
    for key, _ in sorted_items[: len(sorted_items) - CALLBACK_DEBOUNCE_LIMIT]:
        CALLBACK_DEBOUNCE_CACHE.pop(key, None)


def is_callback_debounced(callback: dict, logger: logging.Logger) -> bool:
    from_user = callback.get("from", {})
    user_id = from_user.get("id")
    data = callback.get("data") or ""
    if not user_id or not data:
        return False
    now_value = time.time()
    key = (int(user_id), data)
    last_seen = CALLBACK_DEBOUNCE_CACHE.get(key)
    if last_seen is not None and now_value - last_seen < CALLBACK_DEBOUNCE_WINDOW_SECONDS:
        logger.info("debounce_hit: callback_data=%s user_id=%s", data, user_id)
        return True
    CALLBACK_DEBOUNCE_CACHE[key] = now_value
    _prune_debounce_cache(now_value)
    return False


def build_master_card(ticket: dict, timezone: str) -> str:
    created_display = format_dt(ticket.get("created_at"), timezone)
    username = ticket.get("client_username")
    username_display = "нет username"
    if username:
        cleaned = username.lstrip("@")
        username_display = f"@{cleaned}" if cleaned else "нет username"
    tg_id = ticket.get("client_chat_id") or "—"
    description = (
        ticket.get("problem_text")
        or ticket.get("parts_text")
        or ticket.get("last_visit_text")
        or "—"
    )
    if len(description) > 800:
        description = f"{description[:797].rstrip()}..."
    booking_value = "—"
    if ticket.get("booking_date") or ticket.get("booking_time"):
        booking_value = f"{ticket.get('booking_date', '—')} {ticket.get('booking_time', '—')} (Europe/Moscow)"
    tldr = ticket.get("tldr") or "—"
    day_type = ticket_day_type(ticket, timezone)
    reaction_minutes = get_env_int("CLIENT_REACTION_MINUTES", "REACTION_MINUTES", 30)
    overdue_flag = "⚠️ просрочка реакции" if is_reaction_overdue(ticket, timezone, reaction_minutes) else "ок"
    wait_minutes = ticket_wait_minutes(ticket, timezone)
    return "\n".join(
        [
            f"🧾 Заявка {ticket.get('ticket_id', '—')} • {format_ticket_status(ticket.get('status'))}",
            f"TL;DR: {tldr}",
            f"👤 {ticket.get('fio') or '—'}",
            f"☎️ {ticket.get('phone') or '—'}",
            f"💬 {username_display} • id:{tg_id}",
            f"🚗 {ticket.get('car_make_model') or 'не указано'} • {ticket.get('car_plate') or '—'}",
            f"VIN: {ticket.get('vin') or '—'}",
            f"🧩 Тип: {format_scenario(ticket.get('scenario_type'))}",
            f"📝 {description}",
            f"🗓 {booking_value} • {day_type}",
            f"⏱️ В ожидании: {wait_minutes} мин • {overdue_flag}",
            f"📎 Вложения: {ticket.get('attachments_count', 0)}",
            f"⚙️ Источник: client_bot • created_at:{created_display}",
        ]
    )


def build_master_notification(ticket: dict) -> str:
    scenario = ticket.get("scenario_type")
    if scenario == "booking":
        scenario_label = "Запись на сервис"
    else:
        scenario_label = format_scenario(scenario)
    comment = (
        ticket.get("problem_text")
        or ticket.get("parts_text")
        or ticket.get("last_visit_text")
        or "—"
    )
    return "\n".join(
        [
            "📥 Новая заявка",
            "",
            f"Тип: {scenario_label}",
            f"Имя клиента: {ticket.get('fio') or '—'}",
            f"Телефон: {ticket.get('phone') or '—'}",
            f"Дата: {ticket.get('booking_date') or '—'}",
            f"Время: {ticket.get('booking_time') or '—'}",
            f"Комментарий: {comment}",
            "Источник: клиентский бот",
        ]
    )


def summarize_ticket_changes(fields_changed: list[str]) -> list[str]:
    summary: list[str] = []
    if "phone" in fields_changed:
        summary.append("телефон")
    if any(field in fields_changed for field in ("car_plate", "car_make_model", "vin")):
        summary.append("авто")
    if any(field in fields_changed for field in ("problem_text", "parts_text", "last_visit_text")):
        summary.append("описание")
    if any(field in fields_changed for field in ("booking_date", "booking_time")):
        summary.append("время")
    if "last_visit_category" in fields_changed:
        summary.append("категория")
    if "fio" in fields_changed:
        summary.append("фио")
    return summary


def build_ticket_update_card(ticket: dict, fields_changed: list[str], timezone: str) -> str:
    summary = summarize_ticket_changes(fields_changed)
    summary_text = ", ".join(summary) if summary else "—"
    card = build_master_card(ticket, timezone)
    return "\n".join(
        [
            f"UPDATE по заявке {ticket.get('ticket_id', '—')}",
            f"Изменения: {summary_text}",
            "",
            "Актуальная карточка:",
            card,
        ]
    ).strip()


def format_ticket_status(value: str | None) -> str:
    mapping = {
        STATUS_NEW: "Новая",
        STATUS_IN_PROGRESS: "В работе",
        STATUS_WAITING_CLIENT: "Ожидает клиента",
        STATUS_DONE: "Закрыта",
    }
    return mapping.get(normalize_ticket_status(value), "—")


def format_dt(value: str | None, timezone: str) -> str:
    if not value:
        return "—"
    try:
        return (
            datetime.fromisoformat(value)
            .astimezone(ZoneInfo(timezone))
            .strftime("%Y-%m-%d %H:%M")
        )
    except ValueError:
        return value


def build_ask_more_keyboard(ticket_id: str) -> dict:
    rows: list[list[dict]] = []
    for key, label in ASK_MORE_OPTIONS:
        rows.append([{"text": label, "callback_data": f"ticket:{ticket_id}:ask_more:{key}"}])
    return {"inline_keyboard": rows}


def build_admin_main_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🧪 Самодиагностика", "callback_data": "admin:diag"}],
            [{"text": "📨 Очередь отправки", "callback_data": "admin:queue"}],
            [{"text": "📋 Заявки", "callback_data": "admin:tickets"}],
            [{"text": "📤 Выгрузка заявок", "callback_data": "admin:export"}],
            [{"text": "🧾 Отчёт", "callback_data": "admin:report"}],
            [{"text": "📊 Статистика", "callback_data": "admin:stats"}],
            [{"text": "⚙️ Режимы работы (AI/Fallback)", "callback_data": "admin:modes"}],
            [{"text": "⏰ Напоминания", "callback_data": "admin:reminders"}],
            [{"text": "👥 Администраторы", "callback_data": "admin:admins"}],
            [{"text": "📄 Логи", "callback_data": "admin:logs"}],
            [{"text": "🚫 Блок-лист", "callback_data": "admin:blocklist"}],
            [{"text": "Закрыть", "callback_data": "admin:close"}],
        ]
    }


def build_admin_tickets_filter_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Новые", "callback_data": "admin:tickets:new:1"},
                {"text": "В работе", "callback_data": "admin:tickets:in_progress:1"},
                {"text": "Ожидает клиента", "callback_data": "admin:tickets:waiting_client:1"},
                {"text": "Закрытые", "callback_data": "admin:tickets:done:1"},
            ],
            [{"text": "🚦 Умная очередь", "callback_data": "admin:tickets:queue:1"}],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_ticket_list_keyboard(tickets: list[dict], status: str, page: int, total_pages: int) -> dict:
    rows: list[list[dict]] = []
    for ticket in tickets:
        ticket_id = ticket.get("ticket_id", "")
        rows.append([{"text": ticket_id, "callback_data": f"admin:ticket:{ticket_id}"}])
    nav_row: list[dict] = []
    if page > 1:
        nav_row.append({"text": "⬅️", "callback_data": f"admin:tickets:{status}:{page - 1}"})
    if page < total_pages:
        nav_row.append({"text": "➡️", "callback_data": f"admin:tickets:{status}:{page + 1}"})
    if nav_row:
        rows.append(nav_row)
    rows.append([{"text": "Назад", "callback_data": "admin:tickets"}])
    return {"inline_keyboard": rows}


def build_admin_queue_keyboard(failed_messages: list[dict]) -> dict:
    rows: list[list[dict]] = []
    if failed_messages:
        for message in failed_messages:
            message_id = message.get("id")
            rows.append(
                [
                    {
                        "text": f"Детали #{message_id}",
                        "callback_data": f"admin:queue:detail:{message_id}",
                    }
                ]
            )
        rows.append([{"text": "Повторить failed", "callback_data": "admin:queue:retry_failed"}])
        rows.append([{"text": "Очистить failed (архив)", "callback_data": "admin:queue:clear_failed"}])
    rows.append([{"text": "Назад", "callback_data": "admin:menu"}])
    return {"inline_keyboard": rows}


def build_admin_ticket_detail_keyboard(ticket: dict) -> dict:
    ticket_id = ticket.get("ticket_id", "")
    rows = [
        [
            {"text": "▶️ В работу", "callback_data": f"admin:ticket_status:{ticket_id}:{STATUS_IN_PROGRESS}"},
            {"text": "⏳ Ожидает клиента", "callback_data": f"admin:ticket_status:{ticket_id}:{STATUS_WAITING_CLIENT}"},
            {"text": "✅ Закрыта", "callback_data": f"admin:ticket_status:{ticket_id}:{STATUS_DONE}"},
        ],
        [{"text": "↩️ Вернуть в новые", "callback_data": f"admin:ticket_status:{ticket_id}:{STATUS_NEW}"}],
    ]
    username = ticket.get("client_username")
    if username:
        rows.append(
            [{"text": "💬 Написать клиенту", "url": f"https://t.me/{username.lstrip('@')}"}]
        )
    else:
        rows.append(
            [{"text": "💬 Показать tg_id", "callback_data": f"admin:ticket_contact:{ticket_id}"}]
        )
    rows.append([{"text": "Назад", "callback_data": "admin:tickets"}])
    return {"inline_keyboard": rows}


def build_admin_export_range_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Сегодня", "callback_data": "admin:export_range:today"},
                {"text": "7 дней", "callback_data": "admin:export_range:7"},
                {"text": "30 дней", "callback_data": "admin:export_range:30"},
            ],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_export_status_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Любой", "callback_data": "admin:export_status:any"},
                {"text": "Новые", "callback_data": "admin:export_status:new"},
                {"text": "В работе", "callback_data": "admin:export_status:in_progress"},
                {"text": "Ожидает клиента", "callback_data": "admin:export_status:waiting_client"},
                {"text": "Закрытые", "callback_data": "admin:export_status:done"},
            ],
            [{"text": "Назад", "callback_data": "admin:export"}],
        ]
    }


def build_admin_export_format_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "CSV", "callback_data": "admin:export_format:csv"},
                {"text": "XLSX", "callback_data": "admin:export_format:xlsx"},
            ],
            [{"text": "Назад", "callback_data": "admin:export"}],
        ]
    }


def build_admin_report_range_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Сегодня", "callback_data": "admin:report_range:today"},
                {"text": "7 дней", "callback_data": "admin:report_range:7"},
                {"text": "30 дней", "callback_data": "admin:report_range:30"},
            ],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_report_type_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Любой", "callback_data": "admin:report_type:any"},
                {"text": "Запись", "callback_data": "admin:report_type:booking"},
                {"text": "Прошлый визит", "callback_data": "admin:report_type:last_visit"},
            ],
            [
                {"text": "Запчасти", "callback_data": "admin:report_type:parts"},
                {"text": "Ремонт", "callback_data": "admin:report_type:repair"},
                {"text": "Другое", "callback_data": "admin:report_type:other"},
            ],
            [{"text": "Назад", "callback_data": "admin:report"}],
        ]
    }


def build_admin_report_weekend_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Любые дни", "callback_data": "admin:report_weekend:any"},
                {"text": "Только выходные", "callback_data": "admin:report_weekend:weekend"},
                {"text": "Только будни", "callback_data": "admin:report_weekend:weekday"},
            ],
            [{"text": "Назад", "callback_data": "admin:report"}],
        ]
    }


def build_admin_modes_keyboard(settings: dict) -> dict:
    force_fallback = "1" if settings.get("force_fallback") else "0"
    timeout = settings.get("ai_timeout_seconds")
    return {
        "inline_keyboard": [
            [{"text": f"CLIENT_FORCE_FALLBACK = {force_fallback}", "callback_data": "admin:modes"}],
            [{"text": f"CLIENT_AI_TIMEOUT_SECONDS = {timeout}", "callback_data": "admin:modes"}],
            [
                {"text": "Включить AI", "callback_data": "admin:modes:ai"},
                {"text": "Принудительный fallback", "callback_data": "admin:modes:fallback"},
            ],
            [
                {"text": "Таймаут 5", "callback_data": "admin:modes:timeout:5"},
                {"text": "10", "callback_data": "admin:modes:timeout:10"},
                {"text": "15", "callback_data": "admin:modes:timeout:15"},
                {"text": "20", "callback_data": "admin:modes:timeout:20"},
            ],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_reminders_keyboard(settings: dict) -> dict:
    reminder_minutes = settings.get("reminder_minutes")
    reaction_minutes = settings.get("reaction_minutes")
    auto_reply_hours = settings.get("auto_reply_hours")
    return {
        "inline_keyboard": [
            [{"text": f"CLIENT_REMINDER_MINUTES = {reminder_minutes}", "callback_data": "admin:reminders"}],
            [{"text": f"CLIENT_REACTION_MINUTES = {reaction_minutes}", "callback_data": "admin:reminders"}],
            [{"text": f"CLIENT_AUTO_REPLY_HOURS = {auto_reply_hours}", "callback_data": "admin:reminders"}],
            [
                {"text": "5", "callback_data": "admin:reminders:set:5"},
                {"text": "15", "callback_data": "admin:reminders:set:15"},
                {"text": "30", "callback_data": "admin:reminders:set:30"},
                {"text": "60", "callback_data": "admin:reminders:set:60"},
            ],
            [{"text": "Отправить напоминание сейчас", "callback_data": "admin:reminders:send_all"}],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_admins_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Добавить админа", "callback_data": "admin:admins:add"}],
            [{"text": "Удалить админа", "callback_data": "admin:admins:remove"}],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_admins_remove_keyboard(admin_ids: list[int]) -> dict:
    rows = [[{"text": str(admin_id), "callback_data": f"admin:admins:remove_id:{admin_id}"}] for admin_id in admin_ids]
    rows.append([{"text": "Назад", "callback_data": "admin:admins"}])
    return {"inline_keyboard": rows}


def build_admin_logs_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Всё", "callback_data": "admin:logs:filter:all"},
                {"text": "Ошибки", "callback_data": "admin:logs:filter:error"},
                {"text": "AI", "callback_data": "admin:logs:filter:ai"},
                {"text": "Polling", "callback_data": "admin:logs:filter:polling"},
            ],
            [{"text": "Выгрузить лог файлом", "callback_data": "admin:logs:download"}],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_blocklist_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Добавить в блок-лист", "callback_data": "admin:blocklist:add"}],
            [{"text": "Удалить из блок-листа", "callback_data": "admin:blocklist:remove"}],
            [{"text": "Назад", "callback_data": "admin:menu"}],
        ]
    }


def build_admin_blocklist_remove_keyboard(blocklist: list[int]) -> dict:
    rows = [[{"text": str(block_id), "callback_data": f"admin:blocklist:remove_id:{block_id}"}] for block_id in blocklist]
    rows.append([{"text": "Назад", "callback_data": "admin:blocklist"}])
    return {"inline_keyboard": rows}


def build_admin_ticket_card(ticket: dict, timezone: str) -> str:
    booking = "—"
    if ticket.get("booking_date") or ticket.get("booking_time"):
        booking = f"{ticket.get('booking_date', '-')}, {ticket.get('booking_time', '-')}"
    return "\n".join(
        [
            f"Заявка {ticket.get('ticket_id')}",
            f"Дата: {format_dt(ticket.get('created_at'), timezone)}",
            f"ФИО: {ticket.get('fio', '—')}",
            f"Телефон: {ticket.get('phone', '—')}",
            f"Тип: {format_scenario(ticket.get('scenario_type'))}",
            f"Запись: {booking}",
            f"Вложения: {ticket.get('attachments_count', 0)}",
            f"Статус: {format_ticket_status(ticket.get('status'))}",
        ]
    )


def filter_tickets_by_status(tickets: list[dict], status: str) -> list[dict]:
    if status == "any":
        return list(tickets)
    return [ticket for ticket in tickets if normalize_ticket_status(ticket.get("status")) == status]


def filter_tickets_by_days(tickets: list[dict], days: int | None, timezone: str) -> list[dict]:
    if days is None:
        return list(tickets)
    cutoff = datetime.now(ZoneInfo(timezone)) - timedelta(days=days)
    filtered = []
    for ticket in tickets:
        created_at = ticket.get("created_at")
        if not created_at:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
        except ValueError:
            continue
        if created_dt >= cutoff:
            filtered.append(ticket)
    return filtered


def build_export_rows(tickets: list[dict]) -> list[list[str]]:
    rows = []
    for ticket in tickets:
        rows.append(
            [
                str(ticket.get("ticket_id", "")),
                str(ticket.get("created_at", "")),
                str(normalize_ticket_status(ticket.get("status"))),
                str(ticket.get("fio", "")),
                str(ticket.get("phone", "")),
                str(ticket.get("client_chat_id", "")),
                str(ticket.get("client_username", "")),
                str(ticket.get("was_here_before", "")),
                str(ticket.get("car_plate", "")),
                str(ticket.get("car_make_model", "")),
                str(ticket.get("vin", "")),
                str(ticket.get("scenario_type", "")),
                str(ticket.get("problem_text", "")),
                str(ticket.get("booking_date", "")),
                str(ticket.get("booking_time", "")),
                str(ticket.get("attachments_count", "")),
                str(ticket.get("tldr", "")),
            ]
        )
    return rows


def build_export_files(
    tickets: list[dict],
    export_dir: str,
    filename_prefix: str,
) -> tuple[str, str]:
    os.makedirs(export_dir, exist_ok=True)
    headers = [
        "ticket_id",
        "created_at",
        "status",
        "fio",
        "phone",
        "tg_id",
        "username",
        "was_here_before",
        "plate",
        "make_model",
        "vin",
        "type",
        "description",
        "booking_date",
        "booking_time",
        "attachments_count",
        "tl_dr",
    ]
    rows = build_export_rows(tickets)
    csv_path = os.path.join(export_dir, f"{filename_prefix}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)
        writer.writerows(rows)
    xlsx_path = os.path.join(export_dir, f"{filename_prefix}.xlsx")
    try:
        from openpyxl import Workbook
    except ImportError:
        logging.getLogger("client_bot").warning("openpyxl missing; xlsx disabled")
        return csv_path, ""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(xlsx_path)
    return csv_path, xlsx_path


def read_log_lines(log_path: str, mode: str) -> list[str]:
    if not os.path.exists(log_path):
        return ["Лог файл не найден."]
    lines: deque[str] = deque(maxlen=ADMIN_LOG_LINES)
    with open(log_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            line = line.rstrip("\n")
            if mode == "error" and "ERROR" not in line and "Exception" not in line:
                continue
            if mode == "ai" and "ai_" not in line and "AI" not in line:
                continue
            if mode == "polling" and "polling" not in line:
                continue
            lines.append(line)
    if not lines:
        return ["Нет данных по фильтру."]
    return list(lines)


def get_last_error_line(log_path: str) -> str:
    if not os.path.exists(log_path):
        return "—"
    last_error = "—"
    with open(log_path, "r", encoding="utf-8") as log_file:
        for line in log_file:
            if "ERROR" in line or "Exception" in line:
                last_error = line.strip()
    return last_error


def build_stats(storage: dict, timezone: str) -> str:
    tickets = storage.get("tickets", [])
    total = len(tickets)
    today = filter_tickets_by_days(tickets, 1, timezone)
    last_7 = filter_tickets_by_days(tickets, 7, timezone)
    status_counts = {
        STATUS_NEW: 0,
        STATUS_IN_PROGRESS: 0,
        STATUS_WAITING_CLIENT: 0,
        STATUS_DONE: 0,
    }
    type_counts: dict[str, int] = {}
    weekend_count = 0
    for ticket in tickets:
        status = normalize_ticket_status(ticket.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        scenario = format_scenario(ticket.get("scenario_type"))
        type_counts[scenario] = type_counts.get(scenario, 0) + 1
        if ticket_day_type(ticket, timezone) == "Выходной":
            weekend_count += 1
    top_reason = "—"
    if type_counts:
        top_reason = max(type_counts.items(), key=lambda item: item[1])[0]
    type_distribution = ", ".join([f"{key}: {value}" for key, value in type_counts.items()]) or "—"
    start_clicks = storage.get("start_clicks", {})
    start_total = sum(int(item.get("count", 0)) for item in start_clicks.values())
    return "\n".join(
        [
            f"Всего заявок: {total}",
            f"Сегодня: {len(today)}",
            f"7 дней: {len(last_7)}",
            f"Выходные заявки: {weekend_count}",
            f"Распределение по типам: {type_distribution}",
            (
                "Статусы: "
                f"новые {status_counts.get(STATUS_NEW, 0)}, "
                f"в работе {status_counts.get(STATUS_IN_PROGRESS, 0)}, "
                f"ожидает клиента {status_counts.get(STATUS_WAITING_CLIENT, 0)}, "
                f"закрытые {status_counts.get(STATUS_DONE, 0)}"
            ),
            f"Клики /start=* всего: {start_total}",
            f"Топ-1 причина обращения: {top_reason}",
        ]
    )


def filter_tickets_by_scenario(tickets: list[dict], scenario: str) -> list[dict]:
    if scenario == "any":
        return list(tickets)
    return [ticket for ticket in tickets if ticket.get("scenario_type") == scenario]


def filter_tickets_by_weekend(tickets: list[dict], weekend_filter: str, timezone: str) -> list[dict]:
    if weekend_filter == "any":
        return list(tickets)
    if weekend_filter == "weekend":
        return [ticket for ticket in tickets if ticket_day_type(ticket, timezone) == "Выходной"]
    return [ticket for ticket in tickets if ticket_day_type(ticket, timezone) == "Будний"]


def build_admin_report(storage: dict, timezone: str, days: int | None, scenario: str, weekend_filter: str) -> str:
    tickets = storage.get("tickets", [])
    tickets = filter_tickets_by_days(tickets, days, timezone)
    tickets = filter_tickets_by_scenario(tickets, scenario)
    tickets = filter_tickets_by_weekend(tickets, weekend_filter, timezone)
    status_counts = {
        STATUS_NEW: 0,
        STATUS_IN_PROGRESS: 0,
        STATUS_WAITING_CLIENT: 0,
        STATUS_DONE: 0,
    }
    type_counts: dict[str, int] = {}
    weekend_count = 0
    for ticket in tickets:
        status = normalize_ticket_status(ticket.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        scenario_label = format_scenario(ticket.get("scenario_type"))
        type_counts[scenario_label] = type_counts.get(scenario_label, 0) + 1
        if ticket_day_type(ticket, timezone) == "Выходной":
            weekend_count += 1
    type_distribution = ", ".join([f"{key}: {value}" for key, value in type_counts.items()]) or "—"
    start_clicks = storage.get("start_clicks", {})
    start_total = sum(int(item.get("count", 0)) for item in start_clicks.values())
    top_start = "—"
    if start_clicks:
        top_start = max(start_clicks.items(), key=lambda item: int(item[1].get("count", 0)))[0]
    weekend_label = {
        "any": "любые дни",
        "weekend": "только выходные",
        "weekday": "только будни",
    }.get(weekend_filter, weekend_filter)
    return "\n".join(
        [
            "Отчёт по заявкам:",
            f"Период: {days or 'всё время'}",
            f"Тип: {format_scenario(scenario) if scenario != 'any' else 'любой'}",
            f"Фильтр дней: {weekend_label}",
            f"Всего заявок: {len(tickets)}",
            f"Выходные заявки: {weekend_count}",
            f"Распределение по типам: {type_distribution}",
            (
                "Статусы: "
                f"новые {status_counts.get(STATUS_NEW, 0)}, "
                f"в работе {status_counts.get(STATUS_IN_PROGRESS, 0)}, "
                f"ожидает клиента {status_counts.get(STATUS_WAITING_CLIENT, 0)}, "
                f"закрытые {status_counts.get(STATUS_DONE, 0)}"
            ),
            f"Клики /start=* всего: {start_total}",
            f"Топ кнопка /start: {top_start}",
        ]
    )


def build_queue_overview(storage: dict, timezone: str) -> tuple[str, list[dict]]:
    queue_stats = get_queue_stats(storage, timezone)
    failed_messages = get_failed_messages(storage, timezone)
    lines = [
        "Очередь отправки:",
        f"pending: {queue_stats['pending']}",
        f"failed: {queue_stats['failed']}",
    ]
    if failed_messages:
        lines.append("Последние failed:")
        for message in failed_messages:
            lines.append(
                " | ".join(
                    [
                        f"id={message.get('id')}",
                        f"ticket={message.get('ticket_id') or '—'}",
                        f"chat={message.get('target_chat_id')}",
                        f"attempts={message.get('attempts', 0)}",
                        f"error={message.get('last_error') or '—'}",
                    ]
                )
            )
    return "\n".join(lines), failed_messages


def send_reminders_now(
    token: str,
    storage: dict,
    timezone: str,
    master_usernames: list[str | int],
    logger: logging.Logger,
) -> int:
    count = 0
    for ticket in storage.get("tickets", []):
        if normalize_ticket_status(ticket.get("status")) != STATUS_NEW:
            continue
        reminder_index = int(ticket.get("reminder_count", 0)) + 1
        text = f"Напоминание: заявка {ticket.get('ticket_id')} всё ещё новая"
        reminder_card = build_reminder_card(ticket, timezone)
        notify_masters(
            token,
            master_usernames,
            f"{text}\n{reminder_card}".strip(),
            logger,
            storage,
            timezone,
            "reminder",
            ticket_id=ticket.get("ticket_id"),
            message_key=f"ticket:{ticket.get('ticket_id')}:reminder:{reminder_index}",
        )
        ticket["reminded_at"] = now_iso(timezone)
        ticket["reminder_count"] = reminder_index
        count += 1
    save_storage(storage)
    return count


def build_reminder_card(ticket: dict, timezone: str) -> str:
    return build_master_card(ticket, timezone)


def send_master_contact(token: str, chat_id: int, master_username: str) -> None:
    send_message(
        token,
        chat_id,
        f"Мастер: {master_username}. Нажмите кнопку, чтобы написать мастеру.",
        reply_markup=build_master_keyboard(master_username),
    )


def send_master_contact_from_env(
    token: str,
    chat_id: int,
    logger: logging.Logger,
) -> None:
    master_username, numeric_only, empty = get_master_contact_username(logger)
    if empty:
        logger.warning("[client_bot] MASTER_USERNAMES is empty (env not set)")
        send_message(
            token,
            chat_id,
            "Контакт мастера временно не настроен. Пожалуйста, позвоните в автоцентр.",
        )
        return
    if numeric_only:
        logger.error("[client_bot] MASTER_USERNAMES invalid (numeric). Fix env.")
        send_message(
            token,
            chat_id,
            "Связь с мастером временно недоступна. Пожалуйста, позвоните в автоцентр.",
        )
        return
    if not master_username:
        logger.warning("[client_bot] MASTER_USERNAMES empty. Fix env.")
        send_message(
            token,
            chat_id,
            "Контакт мастера временно не настроен. Пожалуйста, позвоните в автоцентр.",
        )
        return
    send_master_contact(token, chat_id, master_username)


def get_or_create_draft_id(session: dict, chat_id: int, timezone: str) -> str:
    data = session.setdefault("data", {})
    draft_id = data.get("draft_id")
    if draft_id:
        return draft_id
    created_at = session.get("created_at") or now_iso(timezone)
    timestamp = created_at.split("T")[0].replace("-", "")
    draft_id = f"DRAFT-{timestamp}-{chat_id}"
    data["draft_id"] = draft_id
    return draft_id


def build_draft_card(session: dict, chat: dict) -> str:
    data = session.get("data", {})
    draft_id = data.get("draft_id") or "DRAFT"
    username = chat.get("username")
    tg_id = chat.get("id")
    contact = "—"
    if username and tg_id:
        contact = f"@{username} (id {tg_id})"
    elif username:
        contact = f"@{username}"
    elif tg_id:
        contact = f"id {tg_id}"
    collected = []
    if data.get("fio"):
        collected.append(f"ФИО: {data['fio']}")
    if data.get("phone"):
        collected.append(f"Телефон: {data['phone']}")
    if data.get("car_plate"):
        collected.append(f"Госномер: {data['car_plate']}")
    if data.get("car_make_model"):
        collected.append(f"Марка/модель: {data['car_make_model']}")
    if data.get("vin"):
        collected.append(f"VIN: {data['vin']}")
    if data.get("problem_text"):
        collected.append(f"Описание: {data['problem_text']}")
    if data.get("parts_text"):
        collected.append(f"Запчасти: {data['parts_text']}")
    if data.get("last_visit_text"):
        collected.append(f"Вопрос: {data['last_visit_text']}")
    if data.get("booking_date") or data.get("booking_time"):
        collected.append(
            f"Запись: {data.get('booking_date', '-')} {data.get('booking_time', '-')}"
        )
    collected_text = "\n".join(collected) if collected else "—"
    return "\n".join(
        [
            "ЧЕРНОВИК ЗАЯВКИ",
            f"Номер: {draft_id}",
            f"Сценарий: {format_scenario(session.get('scenario'))}",
            f"Текущий шаг: {stage_description(session.get('stage'))}",
            f"Контакт клиента: {contact}",
            "Собранные поля:",
            collected_text,
        ]
    )


def generate_directions_image(address: str) -> bytes:
    width, height = 900, 500
    image = Image.new("RGB", (width, height), color=(250, 250, 250))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    title = "Схема проезда"
    subtitle = f"Адрес: {address}"
    draw.text((40, 40), title, fill=(20, 20, 20), font=font)
    draw.text((40, 80), subtitle, fill=(50, 50, 50), font=font)
    draw.rectangle([(60, 140), (840, 440)], outline=(160, 160, 160), width=3)
    draw.line([(100, 380), (760, 200)], fill=(80, 130, 200), width=6)
    draw.ellipse([(730, 180), (770, 220)], outline=(200, 80, 80), width=6)
    draw.text((780, 185), "📍", fill=(200, 80, 80), font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def send_directions(
    token: str,
    chat_id: int,
    storage: dict,
    timezone: str,
) -> None:
    address = "Удмуртская, 10"
    content = generate_directions_image(address)
    file_path = store_outgoing_file(content, "directions.png")
    caption = "Схема проезда"
    if is_queue_enabled():
        enqueue_document(
            storage,
            chat_id,
            "directions",
            file_path,
            caption,
            message_key=f"directions:{chat_id}",
            timezone=timezone,
        )
        save_storage(storage)
    else:
        send_document(token, chat_id, file_path, caption=caption)
        try:
            os.remove(file_path)
        except OSError:
            logging.getLogger("client_bot").warning(
                "failed to remove directions image path=%s", file_path
            )
    send_message(
        token,
        chat_id,
        f"Адрес: {address}",
        reply_markup=build_directions_keyboard(),
    )


def extract_attachment(message: dict) -> tuple[str, str, int | None] | None:
    if message.get("photo"):
        photo = message["photo"][-1]
        return "photo", photo.get("file_id"), photo.get("file_size")
    if message.get("document"):
        doc = message["document"]
        return "document", doc.get("file_id"), doc.get("file_size")
    if message.get("video"):
        video = message["video"]
        return "video", video.get("file_id"), video.get("file_size")
    if message.get("audio"):
        audio = message["audio"]
        return "audio", audio.get("file_id"), audio.get("file_size")
    if message.get("voice"):
        voice = message["voice"]
        return "voice", voice.get("file_id"), voice.get("file_size")
    return None


def download_file(token: str, file_id: str) -> tuple[bytes, str] | None:
    logger = logging.getLogger("client_bot")
    url = f"https://api.telegram.org/bot{token}/getFile"
    try:
        response = requests.get(url, params={"file_id": file_id}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("telegram getFile error file_id=%s error=%s", file_id, exc)
        return None
    file_path = response.json().get("result", {}).get("file_path")
    if not file_path:
        logger.error("telegram getFile missing file_path file_id=%s", file_id)
        return None
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    try:
        file_response = requests.get(download_url, timeout=20)
        file_response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("telegram file download error file_id=%s error=%s", file_id, exc)
        return None
    filename = os.path.basename(file_path)
    return file_response.content, filename


def send_attachment_to_master(
    token: str,
    master_username: str | int,
    filename: str,
    content: bytes,
    caption: str,
    storage: dict,
    timezone: str,
    message_key: str | None = None,
    ticket_id: str | None = None,
) -> bool:
    logger = logging.getLogger("client_bot")
    file_path = store_outgoing_file(content, filename)
    if is_queue_enabled():
        enqueue_document(
            storage,
            master_username,
            "media",
            file_path,
            caption,
            message_key=message_key,
            ticket_id=ticket_id,
            timezone=timezone,
        )
        save_storage(storage)
        return True
    sent = send_document(token, master_username, file_path, caption=caption)
    if not sent:
        logger.error(
            "telegram sendDocument error master=%s filename=%s",
            master_username,
            filename,
        )
    try:
        os.remove(file_path)
    except OSError:
        logger.warning("failed to remove temp attachment path=%s", file_path)
    return sent


def notify_masters(
    token: str,
    master_usernames: list[str | int],
    text: str,
    logger: logging.Logger,
    storage: dict,
    timezone: str,
    kind: str,
    reply_markup: dict | None = None,
    ticket_id: str | None = None,
    message_key: str | None = None,
) -> None:
    sanitized_markup = sanitize_reply_markup(reply_markup)
    if is_queue_enabled():
        for master in master_usernames:
            queue_key = f"{message_key}:to:{master}" if message_key else None
            enqueue_message(
                storage,
                master,
                kind,
                text,
                reply_markup=sanitized_markup,
                disable_web_page_preview=True,
                message_key=queue_key,
                ticket_id=ticket_id,
                timezone=timezone,
            )
            if ticket_id:
                logger.info("queued ticket %s for master %s", ticket_id, master)
        save_storage(storage)
        return

    for master in master_usernames:
        if ticket_id:
            logger.info("Sending ticket %s to master %s", ticket_id, master)
        success = send_message(token, master, text, reply_markup=sanitized_markup)
        if not success:
            logger.error("failed to send message to master %s ticket_id=%s", master, ticket_id)


def notify_ticket_update(
    token: str,
    master_usernames: list[str | int],
    ticket: dict,
    fields_changed: list[str],
    logger: logging.Logger,
    storage: dict,
    timezone: str,
) -> None:
    update_text = build_ticket_update_card(ticket, fields_changed, timezone)
    notify_masters(
        token,
        master_usernames,
        update_text,
        logger,
        storage,
        timezone,
        "ticket_update",
        reply_markup=build_master_status_keyboard(ticket),
        ticket_id=ticket.get("ticket_id"),
    )
    logger.info("ticket_update: fields_changed=%s", fields_changed)


def run_tg_send_test(
    token: str,
    chat_id: int,
    storage: dict,
    timezone: str,
    master_usernames: list[str | int],
    logger: logging.Logger,
) -> None:
    total = 0
    queued = 0
    sent = 0
    failed = 0
    for index in range(10):
        text = f"TG SEND TEST {index + 1}/10 ({now_iso(timezone)})"
        if is_queue_enabled():
            for master in master_usernames:
                queue_key = f"test:{chat_id}:{index}:to:{master}"
                enqueue_message(storage, master, "test", text, message_key=queue_key, timezone=timezone)
                queued += 1
            total += len(master_usernames)
        else:
            for master in master_usernames:
                total += 1
                if send_message(token, master, text):
                    sent += 1
                else:
                    failed += 1
    if is_queue_enabled():
        save_storage(storage)
    queue_stats = get_queue_stats(storage, timezone)
    logger.info("tg send test result total=%s queued=%s sent=%s failed=%s", total, queued, sent, failed)
    send_message(
        token,
        chat_id,
        (
            "Тест отправки: "
            f"queued={queued}, pending={queue_stats['pending']}, failed={queue_stats['failed']}"
        ),
    )


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def parse_ticket_expiry(ticket: dict, timezone: str) -> datetime | None:
    ttl_str = ticket.get("ttl_expires_at")
    if ttl_str:
        try:
            return datetime.fromisoformat(ttl_str).astimezone(ZoneInfo(timezone))
        except ValueError:
            return None
    created_at = ticket.get("created_at")
    if not created_at:
        return None
    try:
        created_dt = datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
    except ValueError:
        return None
    return created_dt + timedelta(hours=TTL_HOURS)


def is_ticket_active(ticket: dict, timezone: str) -> bool:
    status = normalize_ticket_status(ticket.get("status"))
    if status not in {STATUS_NEW, STATUS_IN_PROGRESS, STATUS_WAITING_CLIENT}:
        return False
    expires_at = parse_ticket_expiry(ticket, timezone)
    if not expires_at:
        return True
    return expires_at >= datetime.now(ZoneInfo(timezone))


def find_active_ticket(storage: dict, chat_id: int, timezone: str) -> dict | None:
    if not chat_id:
        return None
    for ticket in reversed(storage.get("tickets", [])):
        if ticket.get("client_chat_id") != chat_id:
            continue
        if is_ticket_active(ticket, timezone):
            return ticket
    return None


def build_last_visit_text_from_data(data: dict) -> str | None:
    last_visit_text = data.get("last_visit_text")
    last_visit_date = data.get("last_visit_date")
    if last_visit_date:
        if last_visit_text:
            return f"{last_visit_date}; {last_visit_text}"
        return last_visit_date
    return last_visit_text


def parse_phone_candidate(text: str) -> str | None:
    digits = "".join(symbol for symbol in text if symbol.isdigit() or symbol == "+")
    if sum(symbol.isdigit() for symbol in digits) < 9:
        return None
    return digits


def append_text(existing: str | None, extra: str) -> str:
    extra_value = normalize_text(extra)
    if not extra_value:
        return existing or ""
    if not existing:
        return extra_value
    if extra_value.lower() in existing.lower():
        return existing
    return f"{existing}; {extra_value}"


def apply_ticket_updates(ticket: dict, updates: dict, timezone: str) -> list[str]:
    fields_changed: list[str] = []
    for field, value in updates.items():
        if value is None or value == "":
            continue
        if ticket.get(field) != value:
            ticket[field] = value
            fields_changed.append(field)
    if fields_changed:
        ticket["updated_at"] = now_iso(timezone)
    return fields_changed


def build_updates_from_session(session: dict) -> dict:
    data = session.get("data", {})
    last_visit_text = build_last_visit_text_from_data(data)
    return {
        "fio": data.get("fio"),
        "phone": data.get("phone"),
        "pdn_consent": data.get("pdn_consent"),
        "was_here_before": data.get("was_here_before"),
        "car_plate": data.get("car_plate"),
        "car_make_model": data.get("car_make_model"),
        "vin": data.get("vin"),
        "problem_text": data.get("problem_text"),
        "parts_text": data.get("parts_text"),
        "last_visit_text": last_visit_text,
        "last_visit_category": data.get("last_visit_category"),
        "booking_date": data.get("booking_date"),
        "booking_time": data.get("booking_time"),
        "attachments_count": data.get("attachments_count"),
    }


def build_updates_from_text(text: str, ticket: dict, timezone: str) -> dict:
    normalized = normalize_text(text)
    lower = normalized.lower()
    updates: dict[str, str] = {}
    phone_candidate = parse_phone_candidate(normalized)
    if phone_candidate:
        updates["phone"] = phone_candidate
    parsed_date, date_error = parse_date_value(normalized, timezone)
    if parsed_date and not date_error:
        updates["booking_date"] = parsed_date.strftime("%Y-%m-%d")
    parsed_time, time_error = parse_time_value(normalized)
    if parsed_time and not time_error:
        updates["booking_time"] = parsed_time
    if "vin" in lower or "вин" in lower:
        cleaned = normalized.replace("vin", "").replace("VIN", "").replace("вин", "").strip()
        updates["vin"] = cleaned or normalized
    if "гос" in lower or "номер" in lower:
        updates["car_plate"] = normalized
    if "марка" in lower or "модель" in lower:
        updates["car_make_model"] = normalized
    if "фио" in lower:
        updates["fio"] = normalized
    if not updates:
        scenario = ticket.get("scenario_type")
        if scenario == "parts":
            updates["parts_text"] = append_text(ticket.get("parts_text"), normalized)
        elif scenario == "last_visit":
            updates["last_visit_text"] = append_text(ticket.get("last_visit_text"), normalized)
        else:
            updates["problem_text"] = append_text(ticket.get("problem_text"), normalized)
    return updates


def parse_date_value(
    raw_text: str,
    timezone: str,
    ai_service: AIService | None = None,
) -> tuple[date | None, str | None]:
    text = raw_text.strip().lower()
    today = datetime.now(ZoneInfo(timezone)).date()
    tokens = re.findall(r"[a-zа-яё]+", text, flags=re.IGNORECASE)
    if "сегодня" in tokens:
        return None, "Запись день-в-день недоступна. Минимальная дата — завтра."
    if "послезавтра" in tokens:
        return today + timedelta(days=2), None
    if "завтра" in tokens:
        return today + timedelta(days=1), None
    for token in tokens:
        for weekday, aliases in WEEKDAY_ALIASES.items():
            if token in aliases:
                days_ahead = (weekday - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                return today + timedelta(days=days_ahead), None
    formats = ("%d.%m.%Y", "%d.%m.%y", "%d.%m")
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt).date()
            if fmt == "%d.%m":
                parsed = parsed.replace(year=today.year)
            return parsed, None
        except ValueError:
            continue
    if ai_service and ai_service.is_enabled():
        ai_date = ai_service.parse_date(raw_text, today.strftime("%Y-%m-%d"))
        normalized = normalize_date_string(ai_date) if ai_date else None
        if normalized:
            try:
                parsed = datetime.strptime(normalized, "%Y-%m-%d").date()
            except ValueError:
                parsed = None
            if parsed:
                return parsed, None
    return None, "Не понял дату. Напишите дату (например, 12.03) или день недели (вт, среда)."


def validate_booking_date(value: date, timezone: str) -> str | None:
    today = datetime.now(ZoneInfo(timezone)).date()
    if value <= today:
        return "Запись день-в-день недоступна. Минимальная дата — завтра."
    if today.weekday() >= 5 and value.weekday() == 0:
        return "Понедельник недоступен. Выберите дату со вторника по пятницу."
    return None


def parse_time_value(raw_text: str) -> tuple[str | None, str | None]:
    text = raw_text.strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None, "Введите время в формате ЧЧ:ММ."
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None, "Введите время в формате ЧЧ:ММ."
    if minute not in {0, 30}:
        return None, "Шаг записи 30 минут. Выберите время с минутами 00 или 30."
    if hour < 9 or hour > 18:
        return None, "Время работы: 09:00–19:00. Последняя запись в 18:00."
    if hour == 18 and minute != 0:
        return None, "Последняя запись возможна только на 18:00."
    return f"{hour:02d}:{minute:02d}", None


def build_summary(ticket: dict) -> str:
    lines = [
        "ИТОГ ЗАЯВКИ",
        f"Номер: {ticket['ticket_id']}",
        f"Тип: {ticket.get('scenario_type', '-')}",
        f"ФИО: {ticket.get('fio', '-')}",
        f"Телефон: {ticket.get('phone', '-')}",
        f"Согласие ПДн: {'да' if ticket.get('pdn_consent') else 'нет'}",
        f"Были ранее: {ticket.get('was_here_before', '-')}",
    ]
    car_info = []
    if ticket.get("car_plate"):
        car_info.append(f"Госномер: {ticket['car_plate']}")
    if ticket.get("car_make_model"):
        car_info.append(f"Марка/модель: {ticket['car_make_model']}")
    if ticket.get("vin"):
        car_info.append(f"VIN: {ticket['vin']}")
    if car_info:
        lines.extend(car_info)
    if ticket.get("problem_text"):
        lines.append(f"Описание: {ticket['problem_text']}")
    if ticket.get("parts_text"):
        lines.append(f"Запчасти: {ticket['parts_text']}")
    if ticket.get("last_visit_text"):
        lines.append(f"Вопрос: {ticket['last_visit_text']}")
    if ticket.get("last_visit_category"):
        lines.append(f"Категория: {ticket['last_visit_category']}")
    if ticket.get("booking_date"):
        lines.append(f"Дата записи: {ticket['booking_date']}")
    if ticket.get("booking_time"):
        lines.append(f"Время записи: {ticket['booking_time']}")
    return "\n".join(lines)


def build_tldr_fallback(ticket: dict) -> str:
    parts = []
    scenario = format_scenario(ticket.get("scenario_type"))
    parts.append(f"{scenario}: {ticket.get('problem_text') or ticket.get('parts_text') or ticket.get('last_visit_text') or '—'}")
    car_bits = []
    if ticket.get("car_make_model"):
        car_bits.append(ticket["car_make_model"])
    if ticket.get("car_plate"):
        car_bits.append(f"госномер {ticket['car_plate']}")
    if ticket.get("vin"):
        car_bits.append(f"VIN {ticket['vin']}")
    if car_bits:
        parts.append(", ".join(car_bits))
    booking = []
    if ticket.get("booking_date"):
        booking.append(ticket["booking_date"])
    if ticket.get("booking_time"):
        booking.append(ticket["booking_time"])
    if booking:
        parts.append(f"Запись: {' '.join(booking)}")
    return "\n".join(parts[:3])


def ask_current_step(token: str, chat_id: int, session: dict) -> None:
    stage = session.get("stage")
    if stage == "fio":
        send_message(token, chat_id, "Как вас зовут? Укажите имя и фамилию.")
    elif stage == "phone":
        send_message(token, chat_id, "Напишите номер телефона для связи.")
    elif stage == "pdn":
        send_message(
            token,
            chat_id,
            "Согласие на обработку персональных данных. Согласны?",
            reply_markup=build_pdn_keyboard(),
        )
    elif stage == "was_here":
        send_message(
            token,
            chat_id,
            "Вы уже обслуживались у нас ранее с этим автомобилем?",
            reply_markup=build_was_here_keyboard(),
        )
    elif stage == "car_plate":
        send_message(token, chat_id, "Укажите госномер автомобиля.")
    elif stage == "car_vin":
        send_message(token, chat_id, "Укажите VIN автомобиля.")
    elif stage == "car_make_required":
        send_message(token, chat_id, "Подскажите, пожалуйста, марку и модель автомобиля")
    elif stage == "booking_purpose":
        send_message(token, chat_id, UNIVERSAL_QUESTION)
    elif stage == "booking_date":
        timezone = os.getenv("TIMEZONE", "Europe/Moscow")
        today = datetime.now(ZoneInfo(timezone)).date()
        if today.weekday() >= 5:
            send_message(
                token,
                chat_id,
                "Сейчас выходной день. Я приму заявку, мастер получит её в рабочее время "
                "и свяжется с вами для подтверждения записи.\n"
                "Укажите желаемую дату визита (доступны даты со вторника по пятницу; "
                "понедельник — день обработки заявок).",
            )
        else:
            send_message(
                token,
                chat_id,
                "Укажите желаемую дату визита (минимум — завтра).\n"
                "График работы: Пн–Пт с 09:00 до 19:00.",
            )
    elif stage == "booking_time":
        send_message(
            token,
            chat_id,
            "Укажите желаемое время визита (например, 10:30).",
        )
    elif stage == "last_visit_date":
        send_message(token, chat_id, "Укажите примерную дату или месяц визита.")
    elif stage == "last_visit_category":
        send_message(
            token,
            chat_id,
            "Выберите тип вопроса.",
            reply_markup=build_last_visit_category_keyboard(),
        )
    elif stage == "last_visit_description":
        send_message(token, chat_id, UNIVERSAL_QUESTION)
    elif stage == "parts_text":
        send_message(token, chat_id, "Какие запчасти нужны? Можно списком.")
    elif stage == "parts_offer_booking":
        send_message(
            token,
            chat_id,
            "Хотите записаться на сервис?",
            reply_markup=build_yes_no_keyboard(),
        )
    elif stage == "repair_text":
        send_message(token, chat_id, UNIVERSAL_QUESTION)
    elif stage == "repair_offer_booking":
        send_message(
            token,
            chat_id,
            "Хотите записаться на сервис?",
            reply_markup=build_yes_no_keyboard(),
        )
    elif stage == "other_text":
        send_message(token, chat_id, UNIVERSAL_QUESTION)


def build_ticket_from_session(session: dict, timezone: str, storage: dict) -> dict:
    now_value = now_iso(timezone)
    date_prefix = datetime.now(ZoneInfo(timezone)).strftime("%Y%m%d")
    ticket_id = next_ticket_id(storage, date_prefix)
    data = session.get("data", {})
    last_visit_text = data.get("last_visit_text")
    if data.get("last_visit_date"):
        if last_visit_text:
            last_visit_text = f"{data['last_visit_date']}; {last_visit_text}"
        else:
            last_visit_text = data["last_visit_date"]
    return {
        "ticket_id": ticket_id,
        "created_at": session.get("created_at", now_value),
        "updated_at": now_value,
        "scenario_type": session.get("scenario"),
        "fio": data.get("fio"),
        "phone": data.get("phone"),
        "pdn_consent": data.get("pdn_consent", False),
        "was_here_before": data.get("was_here_before"),
        "car_plate": data.get("car_plate"),
        "car_make_model": data.get("car_make_model"),
        "vin": data.get("vin"),
        "problem_text": data.get("problem_text"),
        "parts_text": data.get("parts_text"),
        "last_visit_text": last_visit_text,
        "last_visit_category": data.get("last_visit_category"),
        "booking_date": data.get("booking_date"),
        "booking_time": data.get("booking_time"),
        "attachments_count": data.get("attachments_count", 0),
        "status": STATUS_NEW,
        "client_username": data.get("client_username"),
        "client_chat_id": data.get("client_chat_id"),
        "reminded_at": None,
        "last_master_notify_at": None,
        "ttl_expires_at": data.get("ttl_expires_at", ttl_iso(timezone, TTL_HOURS)),
    }


def compute_next_stage(session: dict) -> str:
    data = session.get("data", {})
    if not data.get("fio"):
        return "fio"
    if not data.get("phone"):
        return "phone"
    if "pdn_consent" not in data:
        return "pdn"
    if not data.get("was_here_before"):
        return "was_here"
    if data.get("was_here_before") in {"yes", "unknown"}:
        if not data.get("car_plate"):
            return "car_plate"
    else:
        if not data.get("vin"):
            return "car_vin"
        if not data.get("car_make_model"):
            return "car_make_required"
    scenario = session.get("scenario")
    if scenario == "booking":
        if not data.get("problem_text"):
            return "booking_purpose"
        if not data.get("booking_date"):
            return "booking_date"
        if not data.get("booking_time"):
            return "booking_time"
        return "done"
    if scenario == "last_visit":
        if not data.get("last_visit_date"):
            return "last_visit_date"
        if not data.get("last_visit_category"):
            return "last_visit_category"
        if not data.get("last_visit_text"):
            return "last_visit_description"
        return "done"
    if scenario == "parts":
        if not data.get("parts_text"):
            return "parts_text"
        if data.get("wants_booking") is None:
            return "parts_offer_booking"
        if data.get("wants_booking"):
            if not data.get("problem_text"):
                return "booking_purpose"
            if not data.get("booking_date"):
                return "booking_date"
            if not data.get("booking_time"):
                return "booking_time"
        return "done"
    if scenario == "repair":
        if not data.get("problem_text"):
            return "repair_text"
        if data.get("wants_booking") is None:
            return "repair_offer_booking"
        if data.get("wants_booking"):
            if not data.get("booking_date"):
                return "booking_date"
            if not data.get("booking_time"):
                return "booking_time"
        return "done"
    if scenario == "other":
        if not data.get("problem_text"):
            return "other_text"
        return "done"
    return "done"


def list_missing_fields(session: dict) -> list[str]:
    data = session.get("data", {})
    missing = []
    if not data.get("fio"):
        missing.append("fio")
    if not data.get("phone"):
        missing.append("phone")
    if "pdn_consent" not in data:
        missing.append("pdn_consent")
    if not data.get("was_here_before"):
        missing.append("was_here_before")
    if data.get("was_here_before") in {"yes", "unknown"}:
        if not data.get("car_plate"):
            missing.append("car_plate")
    elif data.get("was_here_before") == "no":
        if not data.get("vin"):
            missing.append("vin")
        if not data.get("car_make_model"):
            missing.append("car_make_model")
    scenario = session.get("scenario")
    if scenario == "booking":
        if not data.get("problem_text"):
            missing.append("problem_text")
        if not data.get("booking_date"):
            missing.append("booking_date")
        if not data.get("booking_time"):
            missing.append("booking_time")
    if scenario == "last_visit":
        if not data.get("last_visit_date"):
            missing.append("last_visit_date")
        if not data.get("last_visit_category"):
            missing.append("last_visit_category")
        if not data.get("last_visit_text"):
            missing.append("last_visit_text")
    if scenario == "parts":
        if not data.get("parts_text"):
            missing.append("parts_text")
        if data.get("wants_booking") is None:
            missing.append("wants_booking")
        if data.get("wants_booking"):
            if not data.get("problem_text"):
                missing.append("problem_text")
            if not data.get("booking_date"):
                missing.append("booking_date")
            if not data.get("booking_time"):
                missing.append("booking_time")
    if scenario == "repair":
        if not data.get("problem_text"):
            missing.append("problem_text")
        if data.get("wants_booking") is None:
            missing.append("wants_booking")
        if data.get("wants_booking"):
            if not data.get("booking_date"):
                missing.append("booking_date")
            if not data.get("booking_time"):
                missing.append("booking_time")
    if scenario == "other":
        if not data.get("problem_text"):
            missing.append("problem_text")
    return missing


def apply_ai_fields(
    data: dict,
    fields: dict,
    timezone: str,
    logger: logging.Logger,
) -> None:
    for key, value in fields.items():
        if key == "fio" and not data.get("fio"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["fio"] = cleaned
        elif key == "phone" and not data.get("phone"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["phone"] = cleaned
        elif key == "pdn_consent" and "pdn_consent" not in data:
            if isinstance(value, bool):
                data["pdn_consent"] = value
            elif str(value).strip().lower() in {"true", "да", "согласен"}:
                data["pdn_consent"] = True
            elif str(value).strip().lower() in {"false", "нет", "не согласен"}:
                data["pdn_consent"] = False
        elif key == "was_here_before" and not data.get("was_here_before"):
            normalized = str(value).strip().lower()
            mapping = {"yes": "yes", "да": "yes", "no": "no", "нет": "no", "unknown": "unknown"}
            if normalized in mapping:
                data["was_here_before"] = mapping[normalized]
        elif key == "car_plate" and not data.get("car_plate"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["car_plate"] = cleaned
        elif key == "car_make_model" and not data.get("car_make_model"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["car_make_model"] = cleaned
        elif key == "vin" and not data.get("vin"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["vin"] = cleaned
        elif key == "problem_text" and not data.get("problem_text"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["problem_text"] = cleaned
        elif key == "parts_text" and not data.get("parts_text"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["parts_text"] = cleaned
        elif key == "last_visit_text" and not data.get("last_visit_text"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["last_visit_text"] = cleaned
        elif key == "last_visit_category" and not data.get("last_visit_category"):
            cleaned = normalize_text(str(value))
            if cleaned in LAST_VISIT_CATEGORIES:
                data["last_visit_category"] = cleaned
        elif key == "last_visit_date" and not data.get("last_visit_date"):
            cleaned = normalize_text(str(value))
            if cleaned:
                data["last_visit_date"] = cleaned
        elif key == "booking_date" and not data.get("booking_date"):
            normalized = normalize_date_string(str(value))
            if normalized:
                try:
                    parsed = datetime.strptime(normalized, "%Y-%m-%d").date()
                except ValueError:
                    parsed = None
                if parsed:
                    error = validate_booking_date(parsed, timezone)
                    if not error:
                        data["booking_date"] = parsed.strftime("%Y-%m-%d")
                    else:
                        logger.info("ai_booking_date_invalid reason=%s", error)
        elif key == "booking_time" and not data.get("booking_time"):
            value_str = normalize_text(str(value))
            parsed_time, error = parse_time_value(value_str)
            if parsed_time and not error:
                data["booking_time"] = parsed_time
            elif error:
                logger.info("ai_booking_time_invalid reason=%s", error)
        elif key == "wants_booking" and data.get("wants_booking") is None:
            if isinstance(value, bool):
                data["wants_booking"] = value
            elif str(value).strip().lower() in {"yes", "да", "true"}:
                data["wants_booking"] = True
            elif str(value).strip().lower() in {"no", "нет", "false"}:
                data["wants_booking"] = False


def handle_ai_message(
    token: str,
    chat_id: int,
    session: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    ai_service: AIService,
    text: str,
    master_usernames: list[str | int],
) -> bool:
    ai_logger = logging.getLogger("ai")
    stage = session.get("stage")
    if not stage:
        return False
    if stage in AI_ASK_BLOCKLIST:
        ai_logger.info("ai_used=%s reason=%s", False, "blocked_stage")
        return False
    missing_fields = list_missing_fields(session)
    known_fields = {
        key: value
        for key, value in session.get("data", {}).items()
        if key in {"fio", "phone", "pdn_consent", "was_here_before", "car_plate", "car_make_model", "vin"}
    }
    if session.get("ai_fallback"):
        ai_logger.info("ai_used=%s reason=%s", False, "session_fallback")
        return False
    ai_result = ai_service.generate_reply(stage, missing_fields, known_fields, text)
    if ai_result.reason == "unauthorized":
        session["ai_fallback"] = True
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ai_logger.warning("ai_fallback activated for session (401)")
        maybe_send_ai_fallback_notice(token, chat_id, session, storage, timezone, ai_service)
        return False
    ai_logger.info("ai_used=%s reason=%s", ai_result.used, ai_result.reason)
    if not ai_result.used:
        return False
    data = session.setdefault("data", {})
    if stage == "booking_purpose" and "problem_text" in ai_result.fields:
        cleaned = normalize_text(str(ai_result.fields["problem_text"]))
        if cleaned:
            if session.get("scenario") == "repair" and data.get("problem_text"):
                data["problem_text"] = f"{data['problem_text']}; Цель визита: {cleaned}"
                ai_result.fields.pop("problem_text", None)
    apply_ai_fields(data, ai_result.fields, timezone, logger)
    next_stage = compute_next_stage(session)
    if next_stage == "done":
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        finalize_ticket(
            token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
        )
        return True
    session["stage"] = next_stage
    update_session_ttl(session, timezone)
    save_session(storage, chat_id, session)
    save_storage(storage)
    if next_stage in AI_ASK_BLOCKLIST or not ai_result.reply:
        ask_current_step(token, chat_id, session)
        return True
    send_message(token, chat_id, ai_result.reply)
    return True



def finalize_ticket(
    token: str,
    chat_id: int,
    session: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    master_usernames: list[str | int],
    ai_service: AIService,
) -> None:
    ai_logger = logging.getLogger("ai")
    active_ticket = find_active_ticket(storage, chat_id, timezone)
    if active_ticket and (active_ticket.get("finalized_at") or active_ticket.get("last_master_notify_at")):
        updates = build_updates_from_session(session)
        fields_changed = apply_ticket_updates(active_ticket, updates, timezone)
        if fields_changed:
            active_ticket["last_master_notify_at"] = now_iso(timezone)
            save_storage(storage)
            notify_ticket_update(
                token,
                master_usernames,
                active_ticket,
                fields_changed,
                logger,
                storage,
                timezone,
            )
            send_message(token, chat_id, "Спасибо! Обновление передано мастеру.")
        else:
            send_message(
                token,
                chat_id,
                "Заявка уже отправлена мастеру. Если хотите — можете дополнить, я передам обновление.",
            )
        clear_session(storage, chat_id)
        save_storage(storage)
        return
    ticket = build_ticket_from_session(session, timezone, storage)
    tldr_payload = {
        "scenario": format_scenario(ticket.get("scenario_type")),
        "description": ticket.get("problem_text")
        or ticket.get("parts_text")
        or ticket.get("last_visit_text"),
        "car_make_model": ticket.get("car_make_model"),
        "car_plate": ticket.get("car_plate"),
        "vin": ticket.get("vin"),
        "booking_date": ticket.get("booking_date"),
        "booking_time": ticket.get("booking_time"),
    }
    if session.get("ai_fallback"):
        ai_logger.info("ai_used=%s reason=%s", False, "session_fallback")
        tldr_reply = ""
    else:
        tldr_result = ai_service.generate_tldr(tldr_payload)
        ai_logger.info("ai_used=%s reason=%s", tldr_result.used, tldr_result.reason)
        if tldr_result.reason == "unauthorized":
            session["ai_fallback"] = True
            ai_logger.warning("ai_fallback activated for session (401)")
        tldr_reply = tldr_result.reply
    ticket["tldr"] = tldr_reply or build_tldr_fallback(ticket)
    storage.setdefault("tickets", []).append(ticket)
    clear_session(storage, chat_id)
    save_storage(storage)
    summary = build_summary(ticket)
    send_message(token, chat_id, summary)
    now_value = datetime.now(ZoneInfo(timezone))
    if now_value.weekday() >= 5:
        send_message(
            token,
            chat_id,
            "Сейчас выходной день. Я приму заявку, мастер получит её в рабочее время "
            "и свяжется с вами для подтверждения записи.",
        )
    else:
        send_message(
            token,
            chat_id,
            "Я передал заявку мастеру. Он свяжется с вами для подтверждения записи.",
        )
    ticket["finalized_at"] = now_iso(timezone)
    ticket["last_master_notify_at"] = now_iso(timezone)
    save_storage(storage)
    notify_masters(
        token,
        master_usernames,
        build_master_notification(ticket),
        logger,
        storage,
        timezone,
        "ticket",
        reply_markup=build_master_status_keyboard(ticket),
        ticket_id=ticket["ticket_id"],
        message_key=f"ticket:{ticket['ticket_id']}:final",
    )
    logger.info("ticket created %s", ticket["ticket_id"])
    logger.info("sent master card %s", ticket["ticket_id"])


def ensure_session(storage: dict, chat_id: int, timezone: str) -> dict:
    session = get_session(storage, chat_id)
    if not session:
        return {}
    ttl_str = session.get("ttl_expires_at")
    if not ttl_str:
        return session
    try:
        ttl_value = datetime.fromisoformat(ttl_str)
    except ValueError:
        return session
    if ttl_value < datetime.now(ZoneInfo(timezone)):
        clear_session(storage, chat_id)
        save_storage(storage)
        return {}
    return session


def update_session_ttl(session: dict, timezone: str) -> None:
    session["updated_at"] = now_iso(timezone)
    session["ttl_expires_at"] = ttl_iso(timezone, TTL_HOURS)
    session.setdefault("data", {})["ttl_expires_at"] = session["ttl_expires_at"]


def update_session_client_context(session: dict, chat: dict) -> None:
    data = session.setdefault("data", {})
    if chat.get("username"):
        data["client_username"] = f"@{chat['username']}"
    if chat.get("id"):
        data["client_chat_id"] = chat["id"]


def process_master_request(
    token: str,
    chat_id: int,
    chat: dict,
    session: dict,
    storage: dict,
    timezone: str,
    master_usernames: list[str | int],
    logger: logging.Logger,
) -> None:
    if not session.get("created_at"):
        session["created_at"] = now_iso(timezone)
    update_session_client_context(session, chat)
    draft_id = get_or_create_draft_id(session, chat_id, timezone)
    save_session(storage, chat_id, session)
    save_storage(storage)
    draft = build_draft_card(session, chat)
    notify_masters(
        token,
        master_usernames,
        draft,
        logger,
        storage,
        timezone,
        "draft",
        message_key=f"draft:{draft_id}",
    )
    logger.info("sent draft to masters %s", draft_id)
    send_master_contact_from_env(token, chat_id, logger)


def handle_attachment(
    token: str,
    chat_id: int,
    chat: dict,
    message: dict,
    session: dict,
    storage: dict,
    timezone: str,
    master_usernames: list[str | int],
    logger: logging.Logger,
) -> bool:
    attachment = extract_attachment(message)
    if not attachment:
        return False
    file_type, file_id, file_size = attachment
    if not file_id:
        return False
    if not session.get("created_at"):
        session["created_at"] = now_iso(timezone)
    update_session_client_context(session, chat)
    draft_id = get_or_create_draft_id(session, chat_id, timezone)
    data = session.setdefault("data", {})
    data["attachments_count"] = data.get("attachments_count", 0) + 1
    save_session(storage, chat_id, session)
    save_storage(storage)
    send_message(
        token,
        chat_id,
        "Вложение получено, я передал его мастеру. "
        "Продублируйте, пожалуйста, суть проблемы текстом.",
    )
    download = download_file(token, file_id)
    if not download:
        logger.error("attachment download failed draft=%s file_id=%s", draft_id, file_id)
        return True
    content, filename = download
    caption = f"Вложение к заявке {draft_id} от {data.get('fio') or data.get('client_username') or chat_id}"
    for master in master_usernames:
        if not send_attachment_to_master(
            token,
            master,
            filename,
            content,
            caption,
            storage,
            timezone,
            message_key=f"draft:{draft_id}:media:{filename}:to:{master}",
        ):
            logger.error("attachment forward failed master=%s draft=%s", master, draft_id)
    logger.info(
        "attachment received type=%s size=%s draft=%s",
        file_type,
        file_size,
        draft_id,
    )
    return True


def build_freeform_notification(chat: dict, text: str) -> str:
    first_name = chat.get("first_name") or ""
    last_name = chat.get("last_name") or ""
    name = " ".join(part for part in [first_name, last_name] if part).strip() or "—"
    username = chat.get("username")
    if username and name == "—":
        name = f"@{username}"
    return "\n".join(
        [
            "📥 Новая заявка",
            "",
            "Тип: Другое обращение",
            f"Имя клиента: {name}",
            "Телефон: —",
            "Дата: —",
            "Время: —",
            f"Комментарий: {text.strip() or '—'}",
            "Источник: клиентский бот",
        ]
    )


def maybe_send_ai_fallback_notice(
    token: str,
    chat_id: int,
    session: dict,
    storage: dict,
    timezone: str,
    ai_service: AIService,
) -> None:
    if session.get("ai_fallback_notice"):
        return
    if ai_service.is_enabled() and not session.get("ai_fallback"):
        return
    send_message(token, chat_id, FALLBACK_AI_UNAVAILABLE)
    session["ai_fallback_notice"] = True
    update_session_ttl(session, timezone)
    save_session(storage, chat_id, session)
    save_storage(storage)


def start_client_scenario(
    token: str,
    chat_id: int,
    chat: dict,
    session: dict,
    storage: dict,
    timezone: str,
    ai_service: AIService,
    scenario: str,
) -> None:
    session = {
        "scenario": scenario,
        "stage": "fio",
        "created_at": now_iso(timezone),
        "updated_at": now_iso(timezone),
        "ttl_expires_at": ttl_iso(timezone, TTL_HOURS),
        "data": {},
    }
    update_session_client_context(session, chat)
    get_or_create_draft_id(session, chat_id, timezone)
    save_session(storage, chat_id, session)
    save_storage(storage)
    maybe_send_ai_fallback_notice(token, chat_id, session, storage, timezone, ai_service)
    send_message(token, chat_id, "Отлично! Начнём. Как вас зовут? Укажите имя и фамилию.")


def handle_client_menu_action(
    token: str,
    chat_id: int,
    chat: dict,
    session: dict,
    storage: dict,
    timezone: str,
    ai_service: AIService,
    active_ticket: dict | None,
    action: str,
    logger: logging.Logger,
) -> None:
    if action == "directions":
        send_directions(token, chat_id, storage, timezone)
        return
    if active_ticket and not session.get("stage"):
        send_message(
            token,
            chat_id,
            "У вас уже есть активная заявка. Напишите, что хотите дополнить, "
            "я передам обновление мастеру.",
        )
        return
    if session.get("stage"):
        send_message(
            token,
            chat_id,
            "Сейчас у вас активная заявка. Продолжим её. Если нужно начать заново — /cancel.",
        )
        ask_current_step(token, chat_id, session)
        return
    if action not in {"booking", "last_visit", "parts", "repair", "other"}:
        return
    start_client_scenario(
        token,
        chat_id,
        chat,
        session,
        storage,
        timezone,
        ai_service,
        action,
    )
    logger.info("client menu action started scenario=%s chat_id=%s", action, chat_id)


def update_ticket_status(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
) -> None:
    admin_logger = logging.getLogger("admin")
    callback_id = callback.get("id")
    from_user = callback.get("from", {})
    if not check_admin_access(
        from_user.get("id"),
        from_user.get("username"),
        logger,
    ):
        if callback_id:
            answer_callback_query(token, callback_id, "Недостаточно прав доступа")
        return
    if is_duplicate_callback(storage, callback_id):
        if callback_id:
            answer_callback_query(token, callback_id)
        return
    data = callback.get("data") or ""
    parts = data.split(":")
    if len(parts) != 3:
        return
    ticket_id = parts[1]
    new_status = normalize_ticket_status(parts[2])
    if new_status not in {STATUS_IN_PROGRESS, STATUS_WAITING_CLIENT, STATUS_DONE}:
        return
    ticket = next(
        (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
        None,
    )
    if not ticket:
        if callback_id:
            answer_callback_query(token, callback_id, "Заявка не найдена.")
        return
    ticket["status"] = new_status
    ticket["updated_at"] = now_iso(timezone)
    save_storage(storage)
    admin_logger.info(
        "status change ticket_id=%s by=%s status=%s",
        ticket_id,
        callback.get("from", {}).get("username"),
        new_status,
    )
    status_label = format_ticket_status(new_status)
    if callback_id:
        answer_callback_query(token, callback_id, f"Статус обновлён: {status_label}")
    send_message(
        token,
        callback.get("from", {}).get("id"),
        f"Статус заявки {ticket_id}: {status_label}",
    )


def handle_ask_more_request(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
) -> None:
    callback_id = callback.get("id")
    from_user = callback.get("from", {})
    if not check_admin_access(
        from_user.get("id"),
        from_user.get("username"),
        logger,
    ):
        if callback_id:
            answer_callback_query(token, callback_id, "Недостаточно прав доступа")
        return
    if is_duplicate_callback(storage, callback_id):
        if callback_id:
            answer_callback_query(token, callback_id)
        return
    data = callback.get("data") or ""
    parts = data.split(":")
    if len(parts) != 3:
        return
    ticket_id = parts[1]
    ticket = next(
        (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
        None,
    )
    if not ticket:
        if callback_id:
            answer_callback_query(token, callback_id, "Заявка не найдена.")
        return
    client_chat_id = ticket.get("client_chat_id")
    if not client_chat_id:
        if callback_id:
            answer_callback_query(token, callback_id, "Контакт клиента не найден.")
        return
    ticket["clarification_status"] = "selecting"
    ticket["clarification_requested_at"] = now_iso(timezone)
    ticket["status"] = STATUS_WAITING_CLIENT
    save_storage(storage)
    send_message(token, client_chat_id, "Уточните, пожалуйста: выберите/введите вопрос.")
    send_message(
        token,
        callback.get("from", {}).get("id"),
        "Выберите, что уточнить:",
        reply_markup=build_ask_more_keyboard(ticket_id),
    )
    if callback_id:
        answer_callback_query(token, callback_id)


def handle_ask_more_selection(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
) -> None:
    callback_id = callback.get("id")
    from_user = callback.get("from", {})
    if not check_admin_access(
        from_user.get("id"),
        from_user.get("username"),
        logger,
    ):
        if callback_id:
            answer_callback_query(token, callback_id, "Недостаточно прав доступа")
        return
    if is_duplicate_callback(storage, callback_id):
        if callback_id:
            answer_callback_query(token, callback_id)
        return
    data = callback.get("data") or ""
    parts = data.split(":")
    if len(parts) != 4:
        return
    ticket_id = parts[1]
    key = parts[3]
    ticket = next(
        (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
        None,
    )
    if not ticket:
        if callback_id:
            answer_callback_query(token, callback_id, "Заявка не найдена.")
        return
    client_chat_id = ticket.get("client_chat_id")
    if not client_chat_id:
        if callback_id:
            answer_callback_query(token, callback_id, "Контакт клиента не найден.")
        return
    if key == "other":
        set_admin_session(storage, from_user.get("id"), ADMIN_STATE_ASK_MORE_TEXT, {"ticket_id": ticket_id})
        save_storage(storage)
        send_message(token, from_user.get("id"), "Введите текст вопроса для клиента.")
        if callback_id:
            answer_callback_query(token, callback_id)
        return
    question_map = {
        "vin": "VIN",
        "plate": "Госномер",
        "phone": "Телефон",
        "symptom": "Точный симптом/шум/условия",
        "booking": "Желаемое время/дата",
    }
    question = question_map.get(key)
    if not question:
        return
    ticket["clarification_status"] = "waiting"
    ticket["clarification_key"] = key
    ticket["clarification_question"] = question
    ticket["clarification_requested_at"] = now_iso(timezone)
    ticket["status"] = STATUS_WAITING_CLIENT
    save_storage(storage)
    send_message(token, client_chat_id, f"Уточните, пожалуйста: {question}")
    send_message(token, from_user.get("id"), f"Запрос отправлен клиенту: {question}")
    if callback_id:
        answer_callback_query(token, callback_id)


def handle_ask_more_free_text(
    token: str,
    chat_id: int,
    text: str,
    storage: dict,
    timezone: str,
) -> bool:
    admin_session = get_admin_session(storage, chat_id)
    if admin_session.get("state") != ADMIN_STATE_ASK_MORE_TEXT:
        return False
    payload = admin_session.get("data", {})
    ticket_id = payload.get("ticket_id")
    question_text = text.strip()
    if not question_text:
        send_message(token, chat_id, "Введите текст вопроса для клиента.")
        return True
    ticket = next(
        (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
        None,
    )
    if not ticket:
        clear_admin_session(storage, chat_id)
        save_storage(storage)
        send_message(token, chat_id, "Заявка не найдена.")
        return True
    client_chat_id = ticket.get("client_chat_id")
    if not client_chat_id:
        clear_admin_session(storage, chat_id)
        save_storage(storage)
        send_message(token, chat_id, "Контакт клиента не найден.")
        return True
    ticket["clarification_status"] = "waiting"
    ticket["clarification_key"] = "other"
    ticket["clarification_question"] = question_text
    ticket["clarification_requested_at"] = now_iso(timezone)
    ticket["status"] = STATUS_WAITING_CLIENT
    clear_admin_session(storage, chat_id)
    save_storage(storage)
    send_message(token, client_chat_id, f"Уточните, пожалуйста: {question_text}")
    send_message(token, chat_id, "Запрос отправлен клиенту.")
    return True


def find_pending_clarification_ticket(storage: dict, chat_id: int) -> dict | None:
    candidates = [
        ticket
        for ticket in storage.get("tickets", [])
        if ticket.get("client_chat_id") == chat_id and ticket.get("clarification_status") == "waiting"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return candidates[0]


def handle_clarification_response(
    token: str,
    chat_id: int,
    text: str,
    storage: dict,
    timezone: str,
    master_usernames: list[str | int],
    logger: logging.Logger,
) -> bool:
    ticket = find_pending_clarification_ticket(storage, chat_id)
    if not ticket:
        return False
    key = ticket.get("clarification_key")
    question = ticket.get("clarification_question") or "Уточнение"
    answer = text.strip()
    if not answer:
        return False
    clarifications = ticket.setdefault("clarifications", [])
    clarifications.append(
        {
            "question": question,
            "answer": answer,
            "at": now_iso(timezone),
        }
    )
    if key == "vin":
        ticket["vin"] = answer
    elif key == "plate":
        ticket["car_plate"] = answer
    elif key == "phone":
        ticket["phone"] = answer
    elif key == "symptom":
        ticket["clarification_symptom"] = answer
    elif key == "booking":
        ticket["clarification_booking"] = answer
    else:
        ticket["clarification_other"] = answer
    ticket["clarification_status"] = "answered"
    ticket["clarification_answer_at"] = now_iso(timezone)
    ticket["updated_at"] = now_iso(timezone)
    if normalize_ticket_status(ticket.get("status")) == STATUS_WAITING_CLIENT:
        ticket["status"] = STATUS_IN_PROGRESS
    save_storage(storage)
    update_text = "\n".join(
        [
            f"UPDATE: получено уточнение от клиента ({question}).",
            build_master_card(ticket, timezone),
        ]
    )
    notify_masters(
        token,
        master_usernames,
        update_text,
        logger,
        storage,
        timezone,
        "ticket_update",
        reply_markup=build_master_status_keyboard(ticket),
        ticket_id=ticket.get("ticket_id"),
    )
    return True


def handle_client_contact_callback(token: str, callback: dict, storage: dict) -> None:
    callback_id = callback.get("id")
    data = callback.get("data") or ""
    parts = data.split(":")
    if len(parts) != 2:
        return
    ticket_id = parts[1]
    ticket = next(
        (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
        None,
    )
    if not ticket:
        if callback_id:
            answer_callback_query(token, callback_id, "Заявка не найдена.")
        return
    contact = ticket.get("client_chat_id")
    message = f"Контакт клиента: id {contact}" if contact else "Контакт клиента не найден."
    if callback_id:
        answer_callback_query(token, callback_id)
    send_message(token, callback.get("from", {}).get("id"), message)


def handle_client_menu_callback(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
) -> bool:
    data = callback.get("data") or ""
    if not data.startswith("menu:"):
        return False
    chat_id = callback.get("from", {}).get("id")
    callback_id = callback.get("id")
    if callback_id:
        answer_callback_query(token, callback_id)
    if not chat_id:
        return True
    action_key = data.split(":", 1)[1]
    action_map = {
        "booking": "booking",
        "warranty": "last_visit",
        "last_visit": "last_visit",
        "parts": "parts",
        "repair": "repair",
        "other": "other",
        "directions": "directions",
    }
    action = action_map.get(action_key)
    if not action:
        return True
    session = ensure_session(storage, chat_id, timezone)
    active_ticket = find_active_ticket(storage, chat_id, timezone)
    if active_ticket:
        if session.get("active_ticket_id") != active_ticket.get("ticket_id"):
            session["active_ticket_id"] = active_ticket.get("ticket_id")
            save_session(storage, chat_id, session)
            save_storage(storage)
    ai_service = AIService(logging.getLogger("ai"), settings=get_settings(storage))
    handle_client_menu_action(
        token,
        chat_id,
        callback.get("from", {}),
        session,
        storage,
        timezone,
        ai_service,
        active_ticket,
        action,
        logger,
    )
    return True


def handle_admin_callback(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    master_usernames: list[str | int],
) -> bool:
    data = callback.get("data") or ""
    if not data.startswith("admin:"):
        return False
    callback_id = callback.get("id")
    chat_id = callback.get("from", {}).get("id")
    if not check_admin_access(chat_id, callback.get("from", {}).get("username"), logger):
        if callback_id:
            answer_callback_query(token, callback_id, "Недостаточно прав доступа")
        return True
    ensure_storage_defaults(storage)
    if data == "admin:menu":
        send_message(token, chat_id, "Админ-меню:", reply_markup=build_admin_main_keyboard())
        return True
    if data == "admin:close":
        clear_admin_session(storage, chat_id)
        save_storage(storage)
        send_message(token, chat_id, "Админ-меню закрыто.")
        return True
    if data == "admin:diag":
        settings = get_settings(storage)
        ai_service = AIService(logging.getLogger("ai"), settings=settings)
        mode = "FORCED" if settings.get("force_fallback") else ("AI" if ai_service.is_enabled() else "FALLBACK")
        deepseek_status = "доступен" if ai_service.ping() else "недоступен"
        master_ids = parse_csv_ints(os.getenv("CLIENT_MASTER_CHAT_IDS", ""))
        masters_count = len(master_ids) if master_ids else len(master_usernames)
        log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
        last_error = get_last_error_line(log_path)
        queue_stats = get_queue_stats(storage, timezone)
        queue_last_error = get_last_queue_error(storage)
        text = "\n".join(
            [
                "Самодиагностика:",
                "client_bot: OK",
                "polling: OK",
                f"DeepSeek: {deepseek_status}",
                f"режим: {mode}",
                "storage: OK",
                f"masters configured: count={masters_count}",
                f"outgoing queue: enabled={int(is_queue_enabled())} pending={queue_stats['pending']} sent={queue_stats['sent']} failed={queue_stats['failed']}",
                f"queue last error: {queue_last_error}",
                f"последняя ошибка: {last_error}",
            ]
        )
        send_message(token, chat_id, text, reply_markup=build_admin_main_keyboard())
        return True
    if data == "admin:queue":
        text, failed_messages = build_queue_overview(storage, timezone)
        send_message(token, chat_id, text, reply_markup=build_admin_queue_keyboard(failed_messages))
        return True
    if data == "admin:queue:retry_failed":
        count = retry_failed_messages(storage, timezone, logger)
        text, failed_messages = build_queue_overview(storage, timezone)
        send_message(
            token,
            chat_id,
            f"Повтор запущен: {count}\n\n{text}",
            reply_markup=build_admin_queue_keyboard(failed_messages),
        )
        return True
    if data == "admin:queue:clear_failed":
        count = clear_failed_messages(storage, timezone, logger)
        text, failed_messages = build_queue_overview(storage, timezone)
        send_message(
            token,
            chat_id,
            f"Failed архивированы: {count}\n\n{text}",
            reply_markup=build_admin_queue_keyboard(failed_messages),
        )
        return True
    if data.startswith("admin:queue:detail:"):
        message_id = data.split(":")[3]
        if not message_id.isdigit():
            return True
        message = get_outgoing_by_id(storage, int(message_id))
        if not message:
            send_message(token, chat_id, "Сообщение не найдено.", reply_markup=build_admin_main_keyboard())
            return True
        payload = message.get("payload_json") or "{}"
        if len(payload) > 1000:
            payload = payload[:1000] + "..."
        detail_text = "\n".join(
            [
                f"ID: {message.get('id')}",
                f"Status: {message.get('status')}",
                f"Chat: {message.get('target_chat_id')}",
                f"Kind: {message.get('kind')}",
                f"Ticket: {message.get('ticket_id') or '—'}",
                f"Attempts: {message.get('attempts', 0)}",
                f"Last error: {message.get('last_error') or '—'}",
                f"Next retry: {message.get('next_retry_at') or '—'}",
                f"Payload: {payload}",
            ]
        )
        send_message(token, chat_id, detail_text, reply_markup=build_admin_main_keyboard())
        return True
    if data == "admin:tickets":
        send_message(token, chat_id, "Выберите фильтр:", reply_markup=build_admin_tickets_filter_keyboard())
        return True
    if data.startswith("admin:tickets:"):
        parts = data.split(":")
        if len(parts) != 4:
            return True
        status = parts[2]
        page = int(parts[3]) if parts[3].isdigit() else 1
        tickets = list(storage.get("tickets", []))
        if status == "queue":
            tickets = sort_tickets_smart_queue(tickets, timezone)
        else:
            tickets = [
                ticket
                for ticket in tickets
                if normalize_ticket_status(ticket.get("status")) == status
            ]
            tickets.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        total_pages = max(1, (len(tickets) + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
        page = max(1, min(page, total_pages))
        start = (page - 1) * ADMIN_PAGE_SIZE
        page_items = tickets[start : start + ADMIN_PAGE_SIZE]
        if not page_items:
            send_message(token, chat_id, "Заявок нет.", reply_markup=build_admin_tickets_filter_keyboard())
            return True
        lines = []
        for ticket in page_items:
            booking = "—"
            if ticket.get("booking_date") or ticket.get("booking_time"):
                booking = f"{ticket.get('booking_date', '-')}, {ticket.get('booking_time', '-')}"
            lines.append(
                " | ".join(
                    [
                        ticket.get("ticket_id", "—"),
                        format_dt(ticket.get("created_at"), timezone),
                        ticket.get("fio") or "—",
                        ticket.get("phone") or "—",
                        format_scenario(ticket.get("scenario_type")),
                        f"запись: {booking}",
                        f"вложений: {ticket.get('attachments_count', 0)}",
                        f"статус: {format_ticket_status(ticket.get('status'))}",
                    ]
                )
            )
        header = (
            f"Очередь (умная) стр. {page}/{total_pages}"
            if status == "queue"
            else f"Заявки ({format_ticket_status(status)}) стр. {page}/{total_pages}"
        )
        send_message(
            token,
            chat_id,
            "\n".join([header] + lines),
            reply_markup=build_admin_ticket_list_keyboard(page_items, status, page, total_pages),
        )
        return True
    if data.startswith("admin:ticket:"):
        ticket_id = data.split(":", 2)[2]
        ticket = next(
            (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
            None,
        )
        if not ticket:
            send_message(token, chat_id, "Заявка не найдена.")
            return True
        send_message(
            token,
            chat_id,
            build_admin_ticket_card(ticket, timezone),
            reply_markup=build_admin_ticket_detail_keyboard(ticket),
        )
        return True
    if data.startswith("admin:ticket_status:"):
        parts = data.split(":")
        if len(parts) != 4:
            return True
        ticket_id = parts[2]
        new_status = normalize_ticket_status(parts[3])
        if new_status not in {STATUS_NEW, STATUS_IN_PROGRESS, STATUS_WAITING_CLIENT, STATUS_DONE}:
            send_message(token, chat_id, "Недоступный статус.")
            return True
        ticket = next(
            (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
            None,
        )
        if not ticket:
            if callback_id:
                answer_callback_query(token, callback_id, "Заявка не найдена.")
            return True
        ticket["status"] = new_status
        ticket["updated_at"] = now_iso(timezone)
        save_storage(storage)
        if callback_id:
            answer_callback_query(token, callback_id, "Статус обновлён.")
        send_message(token, chat_id, build_admin_ticket_card(ticket, timezone))
        return True
    if data.startswith("admin:ticket_contact:"):
        ticket_id = data.split(":", 2)[2]
        ticket = next(
            (item for item in storage.get("tickets", []) if item.get("ticket_id") == ticket_id),
            None,
        )
        tg_id = ticket.get("client_chat_id") if ticket else None
        message = f"tg_id клиента: {tg_id}" if tg_id else "tg_id клиента не найден."
        send_message(token, chat_id, message)
        return True
    if data == "admin:export":
        set_admin_session(storage, chat_id, ADMIN_STATE_EXPORT_RANGE, {})
        save_storage(storage)
        send_message(token, chat_id, "Выберите период:", reply_markup=build_admin_export_range_keyboard())
        return True
    if data == "admin:report":
        set_admin_session(storage, chat_id, ADMIN_STATE_REPORT_RANGE, {})
        save_storage(storage)
        send_message(token, chat_id, "Выберите период для отчёта:", reply_markup=build_admin_report_range_keyboard())
        return True
    if data.startswith("admin:export_range:"):
        range_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        session["data"] = {"range": range_value}
        session["state"] = ADMIN_STATE_EXPORT_STATUS
        storage["admin_sessions"][str(chat_id)] = session
        save_storage(storage)
        send_message(token, chat_id, "Выберите статус:", reply_markup=build_admin_export_status_keyboard())
        return True
    if data.startswith("admin:report_range:"):
        range_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        session["data"] = {"range": range_value}
        session["state"] = ADMIN_STATE_REPORT_TYPE
        storage["admin_sessions"][str(chat_id)] = session
        save_storage(storage)
        send_message(token, chat_id, "Выберите тип заявок:", reply_markup=build_admin_report_type_keyboard())
        return True
    if data.startswith("admin:export_status:"):
        status_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        session["data"] = {**session.get("data", {}), "status": status_value}
        session["state"] = ADMIN_STATE_EXPORT_FORMAT
        storage["admin_sessions"][str(chat_id)] = session
        save_storage(storage)
        send_message(token, chat_id, "Выберите формат:", reply_markup=build_admin_export_format_keyboard())
        return True
    if data.startswith("admin:report_type:"):
        type_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        session["data"] = {**session.get("data", {}), "type": type_value}
        session["state"] = ADMIN_STATE_REPORT_WEEKEND
        storage["admin_sessions"][str(chat_id)] = session
        save_storage(storage)
        send_message(token, chat_id, "Выберите фильтр по дням:", reply_markup=build_admin_report_weekend_keyboard())
        return True
    if data.startswith("admin:export_format:"):
        format_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        range_value = session.get("data", {}).get("range", "today")
        status_value = session.get("data", {}).get("status", "any")
        days = {"today": 1, "7": 7, "30": 30}.get(range_value)
        tickets = filter_tickets_by_days(storage.get("tickets", []), days, timezone)
        tickets = filter_tickets_by_status(tickets, status_value)
        filename_prefix = f"tickets_{range_value}_{status_value}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        export_dir = os.path.join(os.path.dirname(__file__), "exports")
        csv_path, xlsx_path = build_export_files(tickets, export_dir, filename_prefix)
        if format_value == "csv":
            send_document(token, chat_id, csv_path, caption="Выгрузка CSV")
        else:
            if not xlsx_path:
                send_message(token, chat_id, "XLSX временно недоступен на сервере. Используйте CSV.")
            else:
                send_document(token, chat_id, xlsx_path, caption="Выгрузка XLSX")
        clear_admin_session(storage, chat_id)
        save_storage(storage)
        return True
    if data.startswith("admin:report_weekend:"):
        weekend_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        range_value = session.get("data", {}).get("range", "today")
        type_value = session.get("data", {}).get("type", "any")
        days = {"today": 1, "7": 7, "30": 30}.get(range_value)
        report = build_admin_report(storage, timezone, days, type_value, weekend_value)
        clear_admin_session(storage, chat_id)
        save_storage(storage)
        send_message(token, chat_id, report, reply_markup=build_admin_main_keyboard())
        return True
    if data == "admin:stats":
        send_message(token, chat_id, build_stats(storage, timezone), reply_markup=build_admin_main_keyboard())
        return True
    if data == "admin:modes":
        settings = get_settings(storage)
        send_message(token, chat_id, "Режимы работы:", reply_markup=build_admin_modes_keyboard(settings))
        return True
    if data == "admin:modes:ai":
        storage["settings"]["force_fallback"] = 0
        save_storage(storage)
        send_message(token, chat_id, "AI включён.", reply_markup=build_admin_modes_keyboard(get_settings(storage)))
        return True
    if data == "admin:modes:fallback":
        storage["settings"]["force_fallback"] = 1
        save_storage(storage)
        send_message(token, chat_id, "Принудительный fallback включён.", reply_markup=build_admin_modes_keyboard(get_settings(storage)))
        return True
    if data.startswith("admin:modes:timeout:"):
        timeout_value = data.split(":")[3]
        if timeout_value.isdigit():
            storage["settings"]["ai_timeout_seconds"] = int(timeout_value)
            save_storage(storage)
        send_message(token, chat_id, "Таймаут обновлён.", reply_markup=build_admin_modes_keyboard(get_settings(storage)))
        return True
    if data == "admin:reminders":
        settings = get_settings(storage)
        send_message(token, chat_id, "Напоминания:", reply_markup=build_admin_reminders_keyboard(settings))
        return True
    if data.startswith("admin:reminders:set:"):
        minutes_value = data.split(":")[3]
        if minutes_value.isdigit():
            storage["settings"]["reminder_minutes"] = int(minutes_value)
            save_storage(storage)
        send_message(token, chat_id, "Настройки напоминаний обновлены.", reply_markup=build_admin_reminders_keyboard(get_settings(storage)))
        return True
    if data == "admin:reminders:send_all":
        count = send_reminders_now(token, storage, timezone, master_usernames, logger)
        send_message(token, chat_id, f"Напоминания отправлены: {count}")
        return True
    if data == "admin:admins":
        admin_ids = sorted(get_admin_ids(storage))
        text = "Администраторы:\n" + "\n".join([str(admin_id) for admin_id in admin_ids])
        send_message(token, chat_id, text, reply_markup=build_admin_admins_keyboard())
        return True
    if data == "admin:admins:add":
        set_admin_session(storage, chat_id, ADMIN_STATE_ADD_ADMIN, {})
        save_storage(storage)
        send_message(token, chat_id, "Отправьте tg_id нового администратора (числом).")
        return True
    if data == "admin:admins:remove":
        admin_ids = sorted(get_admin_ids(storage))
        send_message(token, chat_id, "Выберите администратора для удаления:", reply_markup=build_admin_admins_remove_keyboard(admin_ids))
        return True
    if data.startswith("admin:admins:remove_id:"):
        admin_id = data.split(":")[3]
        admin_ids = sorted(get_admin_ids(storage))
        if admin_id.isdigit() and int(admin_id) in admin_ids:
            if len(admin_ids) <= 1:
                send_message(token, chat_id, "Нельзя удалить последнего администратора.")
                return True
            admin_ids.remove(int(admin_id))
            storage["admins"] = admin_ids
            save_storage(storage)
            send_message(token, chat_id, "Администратор удалён.")
        return True
    if data == "admin:logs":
        send_message(token, chat_id, "Логи:", reply_markup=build_admin_logs_keyboard())
        return True
    if data.startswith("admin:logs:filter:"):
        mode = data.split(":")[3]
        log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
        lines = read_log_lines(log_path, mode)
        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[-3500:]
        send_message(token, chat_id, text or "Нет данных.", reply_markup=build_admin_logs_keyboard())
        return True
    if data == "admin:logs:download":
        log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
        send_document(token, chat_id, log_path, caption="client_bot.log")
        return True
    if data == "admin:blocklist":
        blocklist = [int(item) for item in storage.get("blocklist", []) if str(item).isdigit()]
        text = "Блок-лист:\n" + ("\n".join([str(item) for item in blocklist]) if blocklist else "пусто")
        send_message(token, chat_id, text, reply_markup=build_admin_blocklist_keyboard())
        return True
    if data == "admin:blocklist:add":
        set_admin_session(storage, chat_id, ADMIN_STATE_ADD_BLOCK, {})
        save_storage(storage)
        send_message(token, chat_id, "Отправьте tg_id для блок-листа (числом).")
        return True
    if data == "admin:blocklist:remove":
        blocklist = [int(item) for item in storage.get("blocklist", []) if str(item).isdigit()]
        send_message(token, chat_id, "Выберите tg_id для удаления:", reply_markup=build_admin_blocklist_remove_keyboard(blocklist))
        return True
    if data.startswith("admin:blocklist:remove_id:"):
        block_id = data.split(":")[3]
        if block_id.isdigit():
            block_ids = [int(item) for item in storage.get("blocklist", []) if str(item).isdigit()]
            if int(block_id) in block_ids:
                block_ids.remove(int(block_id))
                storage["blocklist"] = block_ids
                save_storage(storage)
                send_message(token, chat_id, "Удалено из блок-листа.")
        return True
    return True


def process_callback(
    token: str,
    update: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
) -> bool:
    callback = update.get("callback_query")
    if not callback:
        return False
    if is_callback_debounced(callback, logger):
        callback_id = callback.get("id")
        if callback_id:
            answer_callback_query(token, callback_id)
        return True
    data = callback.get("data") or ""
    if handle_client_menu_callback(token, callback, storage, timezone, logger):
        return True
    master_usernames = get_master_recipients(storage)
    if handle_admin_callback(token, callback, storage, timezone, logger, master_usernames):
        return True
    if data.startswith("ticket:"):
        parts = data.split(":")
        if len(parts) >= 3 and parts[2] == "ask_more":
            if len(parts) == 3:
                handle_ask_more_request(token, callback, storage, timezone, logger)
            elif len(parts) == 4:
                handle_ask_more_selection(token, callback, storage, timezone, logger)
        else:
            update_ticket_status(token, callback, storage, timezone, logger)
        return True
    if data.startswith("client:"):
        handle_client_contact_callback(token, callback, storage)
        return True
    return False


def check_reminders(
    token: str,
    storage: dict,
    timezone: str,
    master_usernames: list[str | int],
    logger: logging.Logger,
) -> None:
    settings = get_settings(storage)
    reminder_minutes = settings.get("reminder_minutes", 30)
    auto_reply_hours = settings.get("auto_reply_hours", 6)
    now_value = datetime.now(ZoneInfo(timezone))
    for ticket in storage.get("tickets", []):
        if normalize_ticket_status(ticket.get("status")) != STATUS_NEW:
            continue
        created_at = ticket.get("created_at")
        if not created_at:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
        except ValueError:
            continue
        if auto_reply_hours > 0 and not ticket.get("auto_reply_at"):
            if created_dt <= now_value - timedelta(hours=auto_reply_hours):
                client_chat_id = ticket.get("client_chat_id")
                if client_chat_id:
                    send_message(
                        token,
                        client_chat_id,
                        "Мастер получил вашу заявку.\n"
                        "Ответ может занять немного времени.",
                    )
                    ticket["auto_reply_at"] = now_iso(timezone)
                    save_storage(storage)
        if created_dt > now_value - timedelta(minutes=reminder_minutes):
            continue
        reminded_at = ticket.get("reminded_at")
        if reminded_at:
            try:
                reminded_dt = datetime.fromisoformat(reminded_at).astimezone(ZoneInfo(timezone))
                if reminded_dt > now_value - timedelta(minutes=reminder_minutes):
                    continue
            except ValueError:
                pass
        reminder_index = int(ticket.get("reminder_count", 0)) + 1
        text = f"Напоминание: заявка {ticket.get('ticket_id')} всё ещё новая"
        reminder_card = build_reminder_card(ticket, timezone)
        notify_masters(
            token,
            master_usernames,
            f"{text}\n{reminder_card}".strip(),
            logger,
            storage,
            timezone,
            "reminder",
            ticket_id=ticket.get("ticket_id"),
            message_key=f"ticket:{ticket.get('ticket_id')}:reminder:{reminder_index}",
        )
        ticket["reminded_at"] = now_iso(timezone)
        ticket["reminder_count"] = reminder_index
        save_storage(storage)
        logger.info("reminder sent %s", ticket.get("ticket_id"))


def handle_update(token: str, update: dict, logger: logging.Logger) -> None:
    message = update.get("message") or {}
    callback = update.get("callback_query")
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    chat_id = chat.get("id")

    logger.info(
        "update_id=%s chat_id=%s message_id=%s text=%s",
        update.get("update_id"),
        chat_id,
        message.get("message_id"),
        text,
    )

    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    storage = load_storage()
    ensure_storage_defaults(storage)
    session = ensure_session(storage, chat_id, timezone)
    master_usernames = get_master_recipients(storage)
    settings = get_settings(storage)
    ai_service = AIService(logging.getLogger("ai"), settings=settings)
    if session.get("stage"):
        maybe_send_ai_fallback_notice(token, chat_id, session, storage, timezone, ai_service)
    active_ticket: dict | None = None
    if chat_id and not should_skip_ticket_reuse(text):
        active_ticket = find_active_ticket(storage, chat_id, timezone)
        if active_ticket:
            if session.get("active_ticket_id") != active_ticket.get("ticket_id"):
                session["active_ticket_id"] = active_ticket.get("ticket_id")
                save_session(storage, chat_id, session)
                save_storage(storage)
                logger.info(
                    "ticket_reuse: reused ticket_id=%s reason=ttl_active",
                    active_ticket.get("ticket_id"),
                )
        elif session.get("active_ticket_id"):
            session.pop("active_ticket_id", None)
            save_session(storage, chat_id, session)
            save_storage(storage)

    if process_callback(token, update, storage, timezone, logger):
        return

    if callback:
        return

    if not chat_id:
        return

    update_session_client_context(session, chat)

    if text.startswith("/whoami"):
        username = chat.get("username")
        username_display = f"@{username}" if username else "—"
        send_message(
            token,
            chat_id,
            f"Ваш user_id: {chat_id}\nUsername: {username_display}",
        )
        return

    if text.startswith("/admin"):
        if not check_admin_access(chat_id, chat.get("username"), logger):
            send_message(token, chat_id, "Недостаточно прав доступа")
            return
        send_message(token, chat_id, "Админ-меню:", reply_markup=build_admin_main_keyboard())
        return

    if text.startswith("/tgsendtest"):
        if not check_admin_access(chat_id, chat.get("username"), logger):
            send_message(token, chat_id, "Недостаточно прав доступа")
            return
        run_tg_send_test(token, chat_id, storage, timezone, master_usernames, logger)
        return

    if is_admin(chat_id, storage):
        admin_session = get_admin_session(storage, chat_id)
        if handle_ask_more_free_text(token, chat_id, text, storage, timezone):
            return
        if admin_session.get("state") == ADMIN_STATE_ADD_ADMIN:
            if not text.isdigit():
                send_message(token, chat_id, "tg_id должен быть числом. Повторите ввод.")
                return
            admin_ids = sorted(get_admin_ids(storage) | {int(text)})
            storage["admins"] = admin_ids
            clear_admin_session(storage, chat_id)
            save_storage(storage)
            send_message(token, chat_id, "Администратор добавлен.")
            return
        if admin_session.get("state") == ADMIN_STATE_ADD_BLOCK:
            if not text.isdigit():
                send_message(token, chat_id, "tg_id должен быть числом. Повторите ввод.")
                return
            block_ids = {int(value) for value in storage.get("blocklist", []) if str(value).isdigit()}
            block_ids.add(int(text))
            storage["blocklist"] = sorted(block_ids)
            clear_admin_session(storage, chat_id)
            save_storage(storage)
            send_message(token, chat_id, "Добавлено в блок-лист.")
            return

    if handle_attachment(
        token,
        chat_id,
        chat,
        message,
        session,
        storage,
        timezone,
        master_usernames,
        logger,
    ):
        return

    if not message.get("text") and message.get("message_id"):
        send_message(token, chat_id, "Продублируйте, пожалуйста, суть проблемы текстом.")
        return

    if text.startswith("/master"):
        process_master_request(
            token,
            chat_id,
            chat,
            session,
            storage,
            timezone,
            master_usernames,
            logger,
        )
        return

    if text.startswith("/help"):
        send_message(
            token,
            chat_id,
            "Выберите пункт меню и отвечайте на вопросы. "
            "В любой момент доступна команда /master. "
            "Чтобы отменить сценарий — /cancel.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    if text.startswith("/cancel"):
        clear_session(storage, chat_id)
        save_storage(storage)
        send_message(
            token,
            chat_id,
            "Сценарий отменён. Вернёмся в главное меню.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            record_start_click(storage, parts[1].strip(), chat_id)
            save_storage(storage)
        if session.get("stage") or active_ticket:
            send_message(
                token,
                chat_id,
                "У вас уже есть активная заявка. Давайте продолжим.",
            )
            if session.get("stage"):
                ask_current_step(token, chat_id, session)
            return
        send_message(
            token,
            chat_id,
            "Здравствуйте 👋\n"
            "Я онлайн-помощник автоцентра „Лира“.\n"
            "Помогу записаться на сервис, передать вопрос мастеру\n"
            "или уточнить информацию по прошлому визиту.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    if text and not text.startswith("/"):
        normalized = text.strip().lower()
        if "подтвер" in normalized and ("запис" in normalized or "заявк" in normalized):
            send_message(
                token,
                chat_id,
                "Подтверждение записи выполняет мастер. "
                "Я передаю информацию и помогаю с обработкой.",
            )
            return

    if text and not text.startswith("/"):
        if handle_clarification_response(
            token,
            chat_id,
            text,
            storage,
            timezone,
            master_usernames,
            logger,
        ):
            return

    if text and not text.startswith("/") and is_client_menu_text(text):
        action = resolve_menu_action(text)
        if action:
            handle_client_menu_action(
                token,
                chat_id,
                chat,
                session,
                storage,
                timezone,
                ai_service,
                active_ticket,
                action,
                logger,
            )
            return

    if text == MENU_MASTER:
        process_master_request(
            token,
            chat_id,
            chat,
            session,
            storage,
            timezone,
            master_usernames,
            logger,
        )
        return

    if active_ticket and not session.get("stage") and text and not text.startswith("/"):
        updates = build_updates_from_text(text, active_ticket, timezone)
        fields_changed = apply_ticket_updates(active_ticket, updates, timezone)
        if fields_changed:
            active_ticket["last_master_notify_at"] = now_iso(timezone)
            save_storage(storage)
            notify_ticket_update(
                token,
                master_usernames,
                active_ticket,
                fields_changed,
                logger,
                storage,
                timezone,
            )
            send_message(token, chat_id, "Спасибо! Обновление передано мастеру.")
        else:
            send_message(
                token,
                chat_id,
                "Заявка уже отправлена мастеру. Если хотите — можете дополнить, я передам обновление.",
            )
        return

    if not session.get("stage"):
        if text and not text.startswith("/") and is_client_menu_text(text):
            action = resolve_menu_action(text)
            if action:
                handle_client_menu_action(
                    token,
                    chat_id,
                    chat,
                    session,
                    storage,
                    timezone,
                    ai_service,
                    active_ticket,
                    action,
                    logger,
                )
                return
        if text and not text.startswith("/"):
            notify_masters(
                token,
                master_usernames,
                build_freeform_notification(chat, text),
                logger,
                storage,
                timezone,
                "freeform",
                message_key=f"freeform:{chat_id}:{now_iso(timezone)}",
            )
            send_message(token, chat_id, FALLBACK_OUT_OF_SCOPE)
            return
        send_message(
            token,
            chat_id,
            "Пожалуйста, выберите пункт меню.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    stage = session.get("stage")
    data = session.setdefault("data", {})

    if stage and handle_ai_message(
        token,
        chat_id,
        session,
        storage,
        timezone,
        logger,
        ai_service,
        text,
        master_usernames,
    ):
        return

    if stage == "fio":
        if not normalize_text(text):
            send_message(token, chat_id, "Введите имя и фамилию.")
            return
        data["fio"] = normalize_text(text)
        session["stage"] = "phone"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        send_message(token, chat_id, "Спасибо! Теперь напишите номер телефона.")
        return

    if stage == "phone":
        if not normalize_text(text):
            send_message(token, chat_id, "Введите номер телефона.")
            return
        data["phone"] = normalize_text(text)
        session["stage"] = "pdn"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        send_message(
            token,
            chat_id,
            "Согласие на обработку персональных данных. Согласны?",
            reply_markup=build_pdn_keyboard(),
        )
        return

    if stage == "pdn":
        lower = text.strip().lower()
        if lower.startswith("согласен"):
            data["pdn_consent"] = True
        elif "не согласен" in lower:
            data["pdn_consent"] = False
        else:
            send_message(token, chat_id, "Пожалуйста, выберите вариант кнопкой.")
            return
        session["stage"] = "was_here"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        send_message(
            token,
            chat_id,
            "Вы уже обслуживались у нас ранее с этим автомобилем?",
            reply_markup=build_was_here_keyboard(),
        )
        return

    if stage == "was_here":
        lower = text.strip().lower()
        if lower == "да":
            data["was_here_before"] = "yes"
            session["stage"] = "car_plate"
        elif lower == "нет":
            data["was_here_before"] = "no"
            session["stage"] = "car_vin"
        elif lower in {"не уверен", "не уверена"}:
            data["was_here_before"] = "unknown"
            session["stage"] = "car_plate"
        else:
            send_message(token, chat_id, "Пожалуйста, выберите вариант кнопкой.")
            return
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "car_plate":
        if not normalize_text(text):
            send_message(token, chat_id, "Введите госномер автомобиля.")
            return
        data["car_plate"] = normalize_text(text)
        if data.get("was_here_before") == "no":
            session["stage"] = "car_vin"
        else:
            session["stage"] = determine_next_stage_after_car(session)
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "car_make_optional":
        session["stage"] = determine_next_stage_after_car(session)
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "car_vin":
        if not normalize_text(text):
            send_message(token, chat_id, "Введите VIN.")
            return
        data["vin"] = normalize_text(text)
        session["stage"] = "car_make_required"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "car_make_required":
        if not normalize_text(text):
            send_message(token, chat_id, "Подскажите, пожалуйста, марку и модель автомобиля")
            return
        data["car_make_model"] = normalize_text(text)
        session["stage"] = determine_next_stage_after_car(session)
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "booking_purpose":
        if not normalize_text(text):
            send_message(token, chat_id, UNIVERSAL_QUESTION)
            return
        purpose = normalize_text(text)
        if session.get("scenario") == "repair" and data.get("problem_text"):
            data["problem_text"] = f"{data['problem_text']}; Цель визита: {purpose}"
        else:
            data["problem_text"] = purpose
        session["stage"] = "booking_date"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "booking_date":
        parsed, error = parse_date_value(text, timezone, ai_service)
        if error:
            send_message(token, chat_id, error)
            return
        validation_error = validate_booking_date(parsed, timezone)
        if validation_error:
            send_message(token, chat_id, validation_error)
            return
        data["booking_date"] = parsed.strftime("%Y-%m-%d")
        session["stage"] = "booking_time"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "booking_time":
        value, error = parse_time_value(text)
        if error:
            send_message(token, chat_id, error)
            return
        data["booking_time"] = value
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        finalize_ticket(
            token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
        )
        return

    if stage == "last_visit_date":
        if not normalize_text(text):
            send_message(token, chat_id, "Введите примерную дату или месяц визита.")
            return
        data["last_visit_date"] = normalize_text(text)
        session["stage"] = "last_visit_category"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "last_visit_category":
        if text not in LAST_VISIT_CATEGORIES:
            send_message(token, chat_id, "Пожалуйста, выберите вариант кнопкой.")
            return
        data["last_visit_category"] = text
        session["stage"] = "last_visit_description"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "last_visit_description":
        if not normalize_text(text):
            send_message(token, chat_id, UNIVERSAL_QUESTION)
            return
        data["last_visit_text"] = normalize_text(text)
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        finalize_ticket(
            token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
        )
        return

    if stage == "parts_text":
        if not normalize_text(text):
            send_message(token, chat_id, "Опишите, какие запчасти нужны.")
            return
        data["parts_text"] = normalize_text(text)
        session["stage"] = "parts_offer_booking"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "parts_offer_booking":
        lower = text.strip().lower()
        if lower in YES_OPTIONS:
            data["wants_booking"] = True
            session["stage"] = "booking_purpose"
        elif lower in NO_OPTIONS:
            data["wants_booking"] = False
            update_session_ttl(session, timezone)
            save_session(storage, chat_id, session)
            finalize_ticket(
                token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
            )
            return
        else:
            send_message(token, chat_id, "Пожалуйста, выберите вариант кнопкой.")
            return
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "repair_text":
        if not normalize_text(text):
            send_message(token, chat_id, UNIVERSAL_QUESTION)
            return
        data["problem_text"] = normalize_text(text)
        session["stage"] = "repair_offer_booking"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "repair_offer_booking":
        lower = text.strip().lower()
        if lower in YES_OPTIONS:
            data["wants_booking"] = True
            session["stage"] = "booking_purpose"
        elif lower in NO_OPTIONS:
            data["wants_booking"] = False
            update_session_ttl(session, timezone)
            save_session(storage, chat_id, session)
            finalize_ticket(
                token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
            )
            return
        else:
            send_message(token, chat_id, "Пожалуйста, выберите вариант кнопкой.")
            return
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "other_text":
        if not normalize_text(text):
            send_message(token, chat_id, UNIVERSAL_QUESTION)
            return
        data["problem_text"] = normalize_text(text)
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        finalize_ticket(
            token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
        )
        return

    send_message(token, chat_id, FALLBACK_NOT_UNDERSTOOD)


def determine_next_stage_after_car(session: dict) -> str:
    scenario = session.get("scenario")
    if scenario == "booking":
        return "booking_purpose"
    if scenario == "last_visit":
        return "last_visit_date"
    if scenario == "parts":
        return "parts_text"
    if scenario == "repair":
        return "repair_text"
    return "other_text"


def outgoing_queue_worker(timezone: str, logger: logging.Logger) -> None:
    while True:
        try:
            storage = load_storage()
            process_outgoing_queue(storage, timezone, logger)
        except Exception as exc:  # noqa: BLE001 - keep worker alive
            logger.exception("outgoing queue error: %s", exc)
        time.sleep(OUTGOING_QUEUE_INTERVAL_SECONDS)


def poll_updates(token: str, logger: logging.Logger) -> None:
    polling_logger = logging.getLogger("polling")
    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    last_reminder_check = 0.0

    polling_logger.info("polling started (version=%s)", VERSION)

    while True:
        try:
            response = requests.get(
                url,
                params={"timeout": POLLING_TIMEOUT, "offset": offset},
                timeout=POLLING_TIMEOUT + 5,
            )
            if response.status_code == 409:
                polling_logger.warning(
                    "polling 409 conflict: webhook is set; retrying after 5s"
                )
                delete_webhook(token, logger)
                time.sleep(5)
                continue
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                polling_logger.warning("telegram response not ok: %s", payload)
                time.sleep(POLLING_SLEEP_SECONDS)
                continue

            updates = payload.get("result", [])
            for update in updates:
                offset = max(offset, update.get("update_id", 0) + 1)
                handle_update(token, update, logger)
            if time.time() - last_reminder_check >= 60:
                storage = load_storage()
                check_reminders(
                    token,
                    storage,
                    timezone,
                    get_master_recipients(storage),
                    logger,
                )
                last_reminder_check = time.time()
        except Exception as exc:  # noqa: BLE001 - keep polling on errors
            polling_logger.exception("polling error: %s", exc)
            time.sleep(POLLING_SLEEP_SECONDS)


def get_client_token() -> tuple[str, str]:
    token = os.getenv("CLIENT_TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip(), "CLIENT_TELEGRAM_BOT_TOKEN"
    token = os.getenv("TELEGRAM_BOT_TOKEN_CLIENT")
    if token:
        return token.strip(), "TELEGRAM_BOT_TOKEN_CLIENT"
    raise RuntimeError(
        "CLIENT_TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN_CLIENT is required"
    )


def delete_webhook(
    token: str, logger: logging.Logger, drop_pending_updates: bool = False
) -> None:
    payload = {"drop_pending_updates": drop_pending_updates}
    result = tg_request("deleteWebhook", payload)
    if result.ok and result.response_json:
        logger.info(
            "client_bot deleteWebhook ok: result=%s",
            result.response_json.get("result"),
        )
    elif result.response_json:
        logger.warning("client_bot deleteWebhook failed: %s", result.response_json)
    else:
        logger.warning("client_bot deleteWebhook error: %s", result.error)


def main() -> None:
    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    logger = build_logger(timezone)
    logger.info("[client_bot] openpyxl available: %s", is_openpyxl_available())
    token, token_source = get_client_token()
    configure_telegram(token)
    logger.info("client_bot token source: %s", token_source)
    storage = load_storage()
    ensure_storage_defaults(storage)
    logging.getLogger("storage").info(
        "storage loaded tickets=%s sessions=%s",
        len(storage.get("tickets", [])),
        len(storage.get("sessions", {})),
    )
    master_username, numeric_only, _ = get_master_contact_username(logger)
    if numeric_only:
        logger.error("[client_bot] MASTER_USERNAMES invalid (numeric). Fix env.")
    logger.info("[client_bot] master username: %s", mask_username(master_username))
    admin_ids, admins_source = get_admin_ids_with_source()
    logger.info(
        "[client_bot] admins source=%s admins_count=%s",
        admins_source,
        len(admin_ids),
    )
    if not admin_ids and admins_source == "none":
        logger.warning("[client_bot] admins list is empty (env not set)")
    queue_stats = get_queue_stats(storage, timezone)
    logger.info(
        "outgoing queue: enabled=%s pending=%s",
        int(is_queue_enabled()),
        queue_stats.get("pending"),
    )
    if is_queue_enabled():
        worker = threading.Thread(
            target=outgoing_queue_worker,
            args=(timezone, logger),
            daemon=True,
        )
        worker.start()
    settings = get_settings(storage)
    ai_service = AIService(logging.getLogger("ai"), settings=settings)
    ai_config_source = get_ai_config_source()
    logger.info(
        "client_bot config: ai_enabled=%s, force_fallback=%s, timeout=%s, model=%s, base_url=%s, ai_config_source=%s",
        ai_service.is_enabled(),
        int(ai_service.force_fallback),
        ai_service.timeout,
        ai_service.model,
        ai_service.base_url,
        ai_config_source,
    )
    logger.info("client_bot starting (polling mode)")
    delete_webhook(token, logger, drop_pending_updates=False)
    poll_updates(token, logger)


if __name__ == "__main__":
    main()
