import logging
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

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

VERSION = "0.4.0"
POLLING_TIMEOUT = 30
POLLING_SLEEP_SECONDS = 1
TTL_HOURS = 24

MENU_BOOKING = "🗓 Записаться на сервис"
MENU_LAST_VISIT = "🧾 Вопрос по прошлому визиту"
MENU_PARTS = "🧩 Запчасти"
MENU_REPAIR = "🔧 Ремонт"
MENU_OTHER = "❓ Другое"
MENU_MASTER = "👨‍🔧 Связаться с мастером / Написать мастеру"

YES_OPTIONS = {"да", "yes", "ага"}
NO_OPTIONS = {"нет", "no"}


def build_logger(timezone: str) -> logging.Logger:
    logger = logging.getLogger("client_bot")
    logger.setLevel(logging.INFO)

    log_path = os.path.join(os.path.dirname(__file__), "logs", "client_bot.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    tz = ZoneInfo(timezone)

    def format_time(record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    formatter.formatTime = format_time

    if not logger.handlers:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


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


def send_message(token: str, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()


def answer_callback_query(token: str, callback_query_id: str, text: str | None = None) -> None:
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload: dict = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()


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
        "car_make_optional": "ожидаем марку/модель (опционально)",
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
    ticket_id = ticket["ticket_id"]
    username = ticket.get("client_username")
    if username:
        contact_button = {
            "text": "Связаться с клиентом",
            "url": f"https://t.me/{username.lstrip('@')}",
        }
    else:
        contact_button = {
            "text": "Связаться с клиентом",
            "callback_data": f"client:{ticket_id}",
        }
    return {
        "inline_keyboard": [
            [
                {"text": "В работу", "callback_data": f"status:{ticket_id}:in_work"},
                {"text": "Закрыть", "callback_data": f"status:{ticket_id}:closed"},
            ],
            [contact_button],
        ]
    }


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
            'TL;DR: "—"',
        ]
    )


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


def download_file(token: str, file_id: str) -> tuple[bytes, str]:
    url = f"https://api.telegram.org/bot{token}/getFile"
    response = requests.get(url, params={"file_id": file_id}, timeout=10)
    response.raise_for_status()
    file_path = response.json().get("result", {}).get("file_path")
    if not file_path:
        raise RuntimeError("Failed to get file path from Telegram")
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    file_response = requests.get(download_url, timeout=20)
    file_response.raise_for_status()
    filename = os.path.basename(file_path)
    return file_response.content, filename


def send_attachment_to_master(
    token: str, master_username: str, filename: str, content: bytes, caption: str
) -> None:
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    files = {"document": (filename, content)}
    data = {"chat_id": master_username, "caption": caption}
    response = requests.post(url, data=data, files=files, timeout=20)
    response.raise_for_status()


def notify_masters(
    token: str,
    master_usernames: list[str],
    text: str,
    reply_markup: dict | None = None,
) -> None:
    for master in master_usernames:
        send_message(token, master, text, reply_markup=reply_markup)


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
    elif stage == "car_make_optional":
        send_message(
            token,
            chat_id,
            "Если знаете, напишите марку и модель. Или отправьте '-' чтобы пропустить.",
        )
    elif stage == "car_vin":
        send_message(token, chat_id, "Укажите VIN автомобиля.")
    elif stage == "car_make_required":
        send_message(token, chat_id, "Укажите марку и модель автомобиля.")
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


def finalize_ticket(
    token: str,
    chat_id: int,
    session: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    master_usernames: list[str],
) -> None:
    ticket = build_ticket_from_session(session, timezone, storage)
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
        reply_markup=build_master_status_keyboard(ticket),
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
    notify_masters(token, master_usernames, draft)
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
    content, filename = download_file(token, file_id)
    caption = f"Вложение к заявке {draft_id} от {data.get('fio') or data.get('client_username') or chat_id}"
    for master in master_usernames:
        send_attachment_to_master(token, master, filename, content, caption)
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
    callback_id = callback.get("id")
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
    logger.info(
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
    if data.startswith("status:"):
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
    reminder_minutes = int(os.getenv("REMINDER_MINUTES", "30"))
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
        notify_masters(token, master_usernames, f"{text}\n{reminder_card}".strip())
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
    session = ensure_session(storage, chat_id, timezone)
    master_usernames = parse_master_usernames()

    if process_callback(token, update, storage, timezone, logger):
        return

    if callback:
        return

    if not chat_id:
        return

    update_session_client_context(session, chat)

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
        session["stage"] = "car_make_optional"
        update_session_ttl(session, timezone)
        save_session(storage, chat_id, session)
        save_storage(storage)
        ask_current_step(token, chat_id, session)
        return

    if stage == "car_make_optional":
        cleaned = normalize_text(text)
        if cleaned and cleaned not in {"-", "нет", "не знаю", "пропуск"}:
            data["car_make_model"] = cleaned
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
            send_message(token, chat_id, "Введите марку и модель.")
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
            token, chat_id, session, storage, timezone, logger, master_usernames
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
        if text not in {"Гарантия", "Повтор проблемы", "Документы", "Уточнение", "Другое"}:
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
            token, chat_id, session, storage, timezone, logger, master_usernames
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
            session["stage"] = "booking_purpose"
        elif lower in NO_OPTIONS:
            update_session_ttl(session, timezone)
            save_session(storage, chat_id, session)
            finalize_ticket(
                token, chat_id, session, storage, timezone, logger, master_usernames
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
            session["stage"] = "booking_purpose"
        elif lower in NO_OPTIONS:
            update_session_ttl(session, timezone)
            save_session(storage, chat_id, session)
            finalize_ticket(
                token, chat_id, session, storage, timezone, logger, master_usernames
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
            token, chat_id, session, storage, timezone, logger, master_usernames
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


def poll_updates(token: str, logger: logging.Logger) -> None:
    offset = 0
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    master_usernames = parse_master_usernames()
    last_reminder_check = 0.0

    logger.info("client_bot polling started (version=%s)", VERSION)

    while True:
        try:
            response = requests.get(
                url,
                params={"timeout": POLLING_TIMEOUT, "offset": offset},
                timeout=POLLING_TIMEOUT + 5,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                logger.warning("telegram response not ok: %s", payload)
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
            logger.exception("polling error: %s", exc)
            time.sleep(POLLING_SLEEP_SECONDS)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN_CLIENT")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN_CLIENT is required")

    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    logger = build_logger(timezone)
    logger.info("client_bot starting (polling mode)")
    poll_updates(token, logger)


if __name__ == "__main__":
    main()
