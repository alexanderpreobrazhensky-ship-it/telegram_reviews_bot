import csv
import importlib.util
import logging
import os
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from services.ai_service import AIService, normalize_date_string
from services.outgoing_queue import (
    enqueue_document,
    enqueue_message,
    get_last_queue_error,
    get_queue_stats,
    is_queue_enabled,
    process_outgoing_queue,
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

MENU_BOOKING = "🗓 Записаться на сервис"
MENU_LAST_VISIT = "🧾 Вопрос по прошлому визиту"
MENU_PARTS = "🧩 Запчасти"
MENU_REPAIR = "🔧 Ремонт"
MENU_OTHER = "❓ Другое"
MENU_MASTER = "👨‍🔧 Связаться с мастером / Написать мастеру"

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
        "keyboard": [
            [{"text": MENU_BOOKING}],
            [{"text": MENU_LAST_VISIT}],
            [{"text": MENU_PARTS}, {"text": MENU_REPAIR}],
            [{"text": MENU_OTHER}],
            [{"text": MENU_MASTER}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


def build_master_keyboard(master_username: str) -> dict:
    username = master_username.lstrip("@")
    return {
        "inline_keyboard": [
            [{"text": "Связаться с мастером", "url": f"https://t.me/{username}"}]
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


def parse_master_usernames() -> list[str]:
    raw = os.getenv("MASTER_USERNAMES", "")
    if not raw.strip():
        raise RuntimeError("MASTER_USERNAMES is required")
    usernames = []
    for item in raw.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        if not cleaned.startswith("@"):
            cleaned = f"@{cleaned}"
        usernames.append(cleaned)
    if not usernames:
        raise RuntimeError("MASTER_USERNAMES is required")
    return usernames


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


def get_env_value(primary: str, fallback: str, default: str = "") -> str:
    primary_value = os.getenv(primary)
    if primary_value is not None:
        return primary_value.strip()
    fallback_value = os.getenv(fallback)
    if fallback_value is None:
        return default
    return fallback_value.strip()


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
    env_admins = parse_csv_ints(os.getenv("CLIENT_ADMIN_IDS", ""))
    if env_admins:
        merged = {int(value) for value in storage.get("admins", []) if str(value).isdigit()}
        merged.update(env_admins)
        storage["admins"] = sorted(merged)
    settings = storage.setdefault("settings", {})
    settings.setdefault(
        "force_fallback",
        1 if get_env_value("CLIENT_FORCE_FALLBACK", "FORCE_FALLBACK", "0") == "1" else 0,
    )
    settings.setdefault(
        "ai_timeout_seconds",
        get_env_int("CLIENT_AI_TIMEOUT_SECONDS", "AI_TIMEOUT_SECONDS", 10),
    )
    settings.setdefault(
        "reminder_minutes",
        get_env_int("CLIENT_REMINDER_MINUTES", "REMINDER_MINUTES", 30),
    )


def get_settings(storage: dict) -> dict:
    ensure_storage_defaults(storage)
    settings = storage.get("settings", {})
    return {
        "force_fallback": int(settings.get("force_fallback", 0)),
        "ai_timeout_seconds": int(settings.get("ai_timeout_seconds", 10)),
        "reminder_minutes": int(settings.get("reminder_minutes", 30)),
    }


def get_admin_ids(storage: dict) -> set[int]:
    ensure_storage_defaults(storage)
    ids = {int(value) for value in storage.get("admins", []) if str(value).isdigit()}
    ids.update(parse_csv_ints(os.getenv("CLIENT_ADMIN_IDS", "")))
    return ids


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


def build_master_status_keyboard(ticket: dict) -> dict:
    keyboard: list[list[dict]] = []
    username = ticket.get("client_username")
    if username:
        keyboard.append(
            [{"text": "Связаться с клиентом", "url": f"https://t.me/{username.lstrip('@')}"}]
        )
    return {"inline_keyboard": keyboard} if keyboard else {}


def build_master_card(ticket: dict, timezone: str) -> str:
    created_at = ticket.get("created_at")
    created_display = "—"
    if created_at:
        try:
            created_display = (
                datetime.fromisoformat(created_at)
                .astimezone(ZoneInfo(timezone))
                .strftime("%Y-%m-%d %H:%M")
            )
        except ValueError:
            created_display = created_at
    username = ticket.get("client_username")
    tg_id = ticket.get("client_chat_id")
    contact = "—"
    if username and tg_id:
        contact = f"{username} (id {tg_id})"
    elif username:
        contact = username
    elif tg_id:
        contact = f"id {tg_id}"
    description = (
        ticket.get("problem_text")
        or ticket.get("parts_text")
        or ticket.get("last_visit_text")
        or "—"
    )
    booking = "—"
    if ticket.get("booking_date") or ticket.get("booking_time"):
        booking = f"{ticket.get('booking_date', '-')}, {ticket.get('booking_time', '-')}"
    car_bits = []
    if ticket.get("car_make_model"):
        car_bits.append(ticket["car_make_model"])
    if ticket.get("car_plate"):
        car_bits.append(f"Госномер: {ticket['car_plate']}")
    if ticket.get("vin"):
        car_bits.append(f"VIN: {ticket['vin']}")
    car_line = " / ".join(car_bits) if car_bits else "—"
    tldr = ticket.get("tldr") or "—"
    return "\n".join(
        [
            "КАРТОЧКА ЗАЯВКИ",
            f"Номер заявки: {ticket['ticket_id']}",
            f"Дата/время создания: {created_display}",
            f"Статус: {ticket.get('status', 'new')}",
            f"ФИО: {ticket.get('fio', '—')}",
            f"Телефон: {ticket.get('phone', '—')}",
            f"Telegram: {contact}",
            f"Был ранее: {format_was_here(ticket.get('was_here_before'))}",
            f"Авто: {car_line}",
            f"Тип обращения: {format_scenario(ticket.get('scenario_type'))}",
            f"Описание: {description}",
            f"Запись: {booking}",
            f"Вложения: {ticket.get('attachments_count', 0)}",
            f"TL;DR: {tldr}",
        ]
    )


def format_ticket_status(value: str | None) -> str:
    mapping = {"new": "Новая", "in_work": "В работе", "closed": "Закрыта"}
    return mapping.get(value or "", "—")


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


def build_admin_main_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🧪 Самодиагностика", "callback_data": "admin:diag"}],
            [{"text": "📋 Заявки", "callback_data": "admin:tickets"}],
            [{"text": "📤 Выгрузка заявок", "callback_data": "admin:export"}],
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
                {"text": "В работе", "callback_data": "admin:tickets:in_work:1"},
                {"text": "Закрытые", "callback_data": "admin:tickets:closed:1"},
            ],
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


def build_admin_ticket_detail_keyboard(ticket: dict) -> dict:
    ticket_id = ticket.get("ticket_id", "")
    rows = [
        [
            {"text": "✅ В работу", "callback_data": f"admin:ticket_status:{ticket_id}:in_work"},
            {"text": "✅ Закрыта", "callback_data": f"admin:ticket_status:{ticket_id}:closed"},
        ],
        [{"text": "↩️ Вернуть в новые", "callback_data": f"admin:ticket_status:{ticket_id}:new"}],
    ]
    username = ticket.get("client_username")
    if username:
        rows.append(
            [{"text": "👤 Связаться с клиентом", "url": f"https://t.me/{username.lstrip('@')}"}]
        )
    else:
        rows.append(
            [{"text": "👤 Показать tg_id", "callback_data": f"admin:ticket_contact:{ticket_id}"}]
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
                {"text": "В работе", "callback_data": "admin:export_status:in_work"},
                {"text": "Закрытые", "callback_data": "admin:export_status:closed"},
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
    return {
        "inline_keyboard": [
            [{"text": f"CLIENT_REMINDER_MINUTES = {reminder_minutes}", "callback_data": "admin:reminders"}],
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
    return [ticket for ticket in tickets if ticket.get("status", "new") == status]


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
                str(ticket.get("status", "")),
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
    status_counts = {"new": 0, "in_work": 0, "closed": 0}
    type_counts: dict[str, int] = {}
    for ticket in tickets:
        status = ticket.get("status", "new")
        status_counts[status] = status_counts.get(status, 0) + 1
        scenario = format_scenario(ticket.get("scenario_type"))
        type_counts[scenario] = type_counts.get(scenario, 0) + 1
    top_reason = "—"
    if type_counts:
        top_reason = max(type_counts.items(), key=lambda item: item[1])[0]
    type_distribution = ", ".join([f"{key}: {value}" for key, value in type_counts.items()]) or "—"
    return "\n".join(
        [
            f"Всего заявок: {total}",
            f"Сегодня: {len(today)}",
            f"7 дней: {len(last_7)}",
            f"Распределение по типам: {type_distribution}",
            (
                "Статусы: "
                f"новые {status_counts.get('new', 0)}, "
                f"в работе {status_counts.get('in_work', 0)}, "
                f"закрытые {status_counts.get('closed', 0)}"
            ),
            f"Топ-1 причина обращения: {top_reason}",
        ]
    )


def send_reminders_now(
    token: str,
    storage: dict,
    timezone: str,
    master_usernames: list[str],
    logger: logging.Logger,
) -> int:
    count = 0
    for ticket in storage.get("tickets", []):
        if ticket.get("status") != "new":
            continue
        text = f"Напоминание: заявка {ticket.get('ticket_id')} всё ещё новая"
        reminder_card = build_reminder_card(ticket)
        notify_masters(
            token,
            master_usernames,
            f"{text}\n{reminder_card}".strip(),
            logger,
            storage,
            timezone,
            "reminder",
        )
        ticket["reminded_at"] = now_iso(timezone)
        count += 1
    save_storage(storage)
    return count


def build_reminder_card(ticket: dict) -> str:
    booking = ""
    if ticket.get("booking_date") or ticket.get("booking_time"):
        booking = f"Запись: {ticket.get('booking_date', '-')}, {ticket.get('booking_time', '-')}"
    return "\n".join(
        [
            f"Заявка: {ticket.get('ticket_id', '—')}",
            f"ФИО: {ticket.get('fio', '—')}",
            f"Телефон: {ticket.get('phone', '—')}",
            f"Тип: {format_scenario(ticket.get('scenario_type'))}",
            booking,
        ]
    ).strip()


def send_master_contact(token: str, chat_id: int, master_username: str) -> None:
    send_message(
        token,
        chat_id,
        f"Мастер: {master_username}. Нажмите кнопку, чтобы написать мастеру.",
        reply_markup=build_master_keyboard(master_username),
    )


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
    master_username: str,
    filename: str,
    content: bytes,
    caption: str,
    storage: dict,
    timezone: str,
) -> bool:
    logger = logging.getLogger("client_bot")
    file_path = store_outgoing_file(content, filename)
    if is_queue_enabled():
        enqueue_document(storage, master_username, "media", file_path, caption, timezone=timezone)
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
    master_usernames: list[str],
    text: str,
    logger: logging.Logger,
    storage: dict,
    timezone: str,
    kind: str,
    reply_markup: dict | None = None,
    ticket_id: str | None = None,
) -> None:
    sanitized_markup = sanitize_reply_markup(reply_markup)
    if is_queue_enabled():
        for master in master_usernames:
            enqueue_message(
                storage,
                master,
                kind,
                text,
                reply_markup=sanitized_markup,
                disable_web_page_preview=True,
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


def run_tg_send_test(
    token: str,
    chat_id: int,
    storage: dict,
    timezone: str,
    master_usernames: list[str],
    logger: logging.Logger,
) -> None:
    total = 0
    queued = 0
    sent = 0
    failed = 0
    for index in range(5):
        text = f"TG SEND TEST {index + 1}/5 ({now_iso(timezone)})"
        if is_queue_enabled():
            for master in master_usernames:
                enqueue_message(storage, master, "test", text, timezone=timezone)
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
    logger.info("tg send test result total=%s queued=%s sent=%s failed=%s", total, queued, sent, failed)
    send_message(
        token,
        chat_id,
        f"Тест отправки: всего={total}, отправлено={sent}, в очереди={queued}, ошибки={failed}",
    )


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def parse_date_value(raw_text: str, timezone: str) -> tuple[date | None, str | None]:
    text = raw_text.strip().lower()
    if "сегодня" in text:
        return None, "Запись день-в-день недоступна. Минимальная дата — завтра."
    formats = ("%d.%m.%Y", "%d.%m.%y", "%d.%m")
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt).date()
            if fmt == "%d.%m":
                parsed = parsed.replace(year=datetime.now(ZoneInfo(timezone)).year)
            return parsed, None
        except ValueError:
            continue
    return None, "Не понял дату. Напишите в формате ДД.ММ.ГГГГ."


def validate_booking_date(value: date, timezone: str) -> str | None:
    today = datetime.now(ZoneInfo(timezone)).date()
    if value <= today:
        return "Запись день-в-день недоступна. Минимальная дата — завтра."
    if value.weekday() >= 5:
        return "Мы работаем только по будням (Пн–Пт). Выберите другой день."
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
        send_message(token, chat_id, "Кратко опишите цель визита.")
    elif stage == "booking_date":
        send_message(
            token,
            chat_id,
            "Укажите желаемую дату записи (ДД.ММ.ГГГГ). Минимум — следующий день.",
        )
    elif stage == "booking_time":
        send_message(
            token,
            chat_id,
            "Укажите желаемое время (например, 10:30). Работаем 09:00–19:00, "
            "последняя запись в 18:00.",
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
        send_message(token, chat_id, "Опишите вопрос по прошлому визиту.")
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
        send_message(token, chat_id, "Опишите симптомы или что беспокоит.")
    elif stage == "repair_offer_booking":
        send_message(
            token,
            chat_id,
            "Хотите записаться на сервис?",
            reply_markup=build_yes_no_keyboard(),
        )
    elif stage == "other_text":
        send_message(token, chat_id, "Кратко опишите ваш вопрос.")


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
        "status": "new",
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
    master_usernames: list[str],
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
    ai_result = ai_service.generate_reply(stage, missing_fields, known_fields, text)
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
    master_usernames: list[str],
    ai_service: AIService,
) -> None:
    ai_logger = logging.getLogger("ai")
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
    tldr_result = ai_service.generate_tldr(tldr_payload)
    ai_logger.info("ai_used=%s reason=%s", tldr_result.used, tldr_result.reason)
    ticket["tldr"] = tldr_result.reply or build_tldr_fallback(ticket)
    storage.setdefault("tickets", []).append(ticket)
    clear_session(storage, chat_id)
    save_storage(storage)
    summary = build_summary(ticket)
    send_message(token, chat_id, summary)
    send_message(token, chat_id, "Спасибо! Заявка сохранена.")
    ticket["last_master_notify_at"] = now_iso(timezone)
    save_storage(storage)
    notify_masters(
        token,
        master_usernames,
        build_master_card(ticket, timezone),
        logger,
        storage,
        timezone,
        "ticket",
        reply_markup=build_master_status_keyboard(ticket),
        ticket_id=ticket["ticket_id"],
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
    master_usernames: list[str],
    logger: logging.Logger,
) -> None:
    if not session.get("created_at"):
        session["created_at"] = now_iso(timezone)
    update_session_client_context(session, chat)
    draft_id = get_or_create_draft_id(session, chat_id, timezone)
    save_session(storage, chat_id, session)
    save_storage(storage)
    draft = build_draft_card(session, chat)
    notify_masters(token, master_usernames, draft, logger, storage, timezone, "draft")
    logger.info("sent draft to masters %s", draft_id)
    send_master_contact(token, chat_id, master_usernames[0])


def handle_attachment(
    token: str,
    chat_id: int,
    chat: dict,
    message: dict,
    session: dict,
    storage: dict,
    timezone: str,
    master_usernames: list[str],
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
    send_message(token, chat_id, "Пока не принимаем вложения. Опишите, пожалуйста, текстом.")
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
        ):
            logger.error("attachment forward failed master=%s draft=%s", master, draft_id)
    logger.info(
        "attachment received type=%s size=%s draft=%s",
        file_type,
        file_size,
        draft_id,
    )
    return True


def update_ticket_status(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
) -> None:
    admin_logger = logging.getLogger("admin")
    callback_id = callback.get("id")
    if not is_admin(callback.get("from", {}).get("id"), storage):
        if callback_id:
            answer_callback_query(token, callback_id, "Недостаточно прав доступа")
        return
    data = callback.get("data") or ""
    parts = data.split(":")
    if len(parts) != 3:
        return
    ticket_id = parts[1]
    new_status = parts[2]
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
    if callback_id:
        answer_callback_query(token, callback_id, f"Статус обновлён: {new_status}")
    send_message(token, callback.get("from", {}).get("id"), f"Статус заявки {ticket_id}: {new_status}")


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


def handle_admin_callback(
    token: str,
    callback: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    master_usernames: list[str],
) -> bool:
    data = callback.get("data") or ""
    if not data.startswith("admin:"):
        return False
    callback_id = callback.get("id")
    chat_id = callback.get("from", {}).get("id")
    if not is_admin(chat_id, storage):
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
    if data == "admin:tickets":
        send_message(token, chat_id, "Выберите фильтр:", reply_markup=build_admin_tickets_filter_keyboard())
        return True
    if data.startswith("admin:tickets:"):
        parts = data.split(":")
        if len(parts) != 4:
            return True
        status = parts[2]
        page = int(parts[3]) if parts[3].isdigit() else 1
        tickets = [
            ticket
            for ticket in storage.get("tickets", [])
            if ticket.get("status", "new") == status
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
        header = f"Заявки ({format_ticket_status(status)}) стр. {page}/{total_pages}"
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
        new_status = parts[3]
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
    if data.startswith("admin:export_range:"):
        range_value = data.split(":", 2)[2]
        session = get_admin_session(storage, chat_id)
        session["data"] = {"range": range_value}
        session["state"] = ADMIN_STATE_EXPORT_STATUS
        storage["admin_sessions"][str(chat_id)] = session
        save_storage(storage)
        send_message(token, chat_id, "Выберите статус:", reply_markup=build_admin_export_status_keyboard())
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
    data = callback.get("data") or ""
    master_usernames = parse_master_usernames()
    if handle_admin_callback(token, callback, storage, timezone, logger, master_usernames):
        return True
    if data.startswith("ticket:"):
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
    master_usernames: list[str],
    logger: logging.Logger,
) -> None:
    settings = get_settings(storage)
    reminder_minutes = settings.get("reminder_minutes", 30)
    now_value = datetime.now(ZoneInfo(timezone))
    for ticket in storage.get("tickets", []):
        if ticket.get("status") != "new":
            continue
        created_at = ticket.get("created_at")
        if not created_at:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at).astimezone(ZoneInfo(timezone))
        except ValueError:
            continue
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
        text = f"Напоминание: заявка {ticket.get('ticket_id')} всё ещё новая"
        reminder_card = build_reminder_card(ticket)
        notify_masters(
            token,
            master_usernames,
            f"{text}\n{reminder_card}".strip(),
            logger,
            storage,
            timezone,
            "reminder",
        )
        ticket["reminded_at"] = now_iso(timezone)
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
    master_usernames = parse_master_usernames()
    settings = get_settings(storage)
    ai_service = AIService(logging.getLogger("ai"), settings=settings)

    if process_callback(token, update, storage, timezone, logger):
        return

    if callback:
        return

    if not chat_id:
        return

    update_session_client_context(session, chat)

    if text.startswith("/admin"):
        if not is_admin(chat_id, storage):
            send_message(token, chat_id, "Недостаточно прав доступа")
            return
        send_message(token, chat_id, "Админ-меню:", reply_markup=build_admin_main_keyboard())
        return

    if text.startswith("/tgsendtest"):
        if not is_admin(chat_id, storage):
            send_message(token, chat_id, "Недостаточно прав доступа")
            return
        run_tg_send_test(token, chat_id, storage, timezone, master_usernames, logger)
        return

    if is_admin(chat_id, storage):
        admin_session = get_admin_session(storage, chat_id)
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
        send_message(token, chat_id, "Пока не принимаем вложения. Опишите, пожалуйста, текстом.")
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
        if session.get("stage"):
            send_message(
                token,
                chat_id,
                "У вас уже есть активная заявка. Давайте продолжим.",
            )
            ask_current_step(token, chat_id, session)
            return
        send_message(
            token,
            chat_id,
            "Привет! Выберите, пожалуйста, нужный пункт меню.",
            reply_markup=build_main_menu_keyboard(),
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

    if session.get("stage") and text in {
        MENU_BOOKING,
        MENU_LAST_VISIT,
        MENU_PARTS,
        MENU_REPAIR,
        MENU_OTHER,
    }:
        send_message(
            token,
            chat_id,
            "Сейчас у вас активная заявка. Продолжим её. Если нужно начать заново — /cancel.",
        )
        ask_current_step(token, chat_id, session)
        return

    if not session.get("stage"):
        if text in {
            MENU_BOOKING,
            MENU_LAST_VISIT,
            MENU_PARTS,
            MENU_REPAIR,
            MENU_OTHER,
        }:
            scenario_map = {
                MENU_BOOKING: "booking",
                MENU_LAST_VISIT: "last_visit",
                MENU_PARTS: "parts",
                MENU_REPAIR: "repair",
                MENU_OTHER: "other",
            }
            session = {
                "scenario": scenario_map[text],
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
            send_message(token, chat_id, "Отлично! Начнём. Как вас зовут? Укажите имя и фамилию.")
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
            send_message(token, chat_id, "Опишите цель визита.")
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
        parsed, error = parse_date_value(text, timezone)
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
            send_message(token, chat_id, "Опишите ваш вопрос.")
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
            send_message(token, chat_id, "Опишите симптомы.")
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
            send_message(token, chat_id, "Опишите вопрос.")
            return
        data["problem_text"] = normalize_text(text)
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        finalize_ticket(
            token, chat_id, session, storage, timezone, logger, master_usernames, ai_service
        )
        return

    send_message(token, chat_id, "Пожалуйста, следуйте подсказкам.")


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
    master_usernames = parse_master_usernames()
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
                check_reminders(token, storage, timezone, master_usernames, logger)
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
    logger.info(
        "client_bot config: ai_enabled=%s, force_fallback=%s, timeout=%s, model=%s, base_url=%s",
        ai_service.is_enabled(),
        int(ai_service.force_fallback),
        ai_service.timeout,
        ai_service.model,
        ai_service.base_url,
    )
    logger.info("client_bot starting (polling mode)")
    delete_webhook(token, logger, drop_pending_updates=False)
    poll_updates(token, logger)


if __name__ == "__main__":
    main()
