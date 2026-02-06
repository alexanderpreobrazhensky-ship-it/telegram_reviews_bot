import logging
import os
import time
from datetime import date, datetime
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

VERSION = "0.3.0"
POLLING_TIMEOUT = 30
POLLING_SLEEP_SECONDS = 1
TTL_HOURS = 24

MENU_BOOKING = "🗓 Записаться на сервис"
MENU_LAST_VISIT = "🧾 Вопрос по прошлому визиту"
MENU_PARTS = "🧩 Запчасти"
MENU_REPAIR = "🔧 Ремонт"
MENU_OTHER = "❓ Другое"
MENU_MASTER = "👨‍🔧 Связаться с мастером"

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


def build_master_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Связаться с мастером", "url": "https://t.me/Liraavto"}]
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


def send_master_contact(token: str, chat_id: int) -> None:
    send_message(
        token,
        chat_id,
        "Связаться с мастером можно по кнопке ниже.",
        reply_markup=build_master_keyboard(),
    )


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
        "status": "new",
        "ttl_expires_at": data.get("ttl_expires_at", ttl_iso(timezone, TTL_HOURS)),
    }


def finalize_ticket(
    token: str,
    chat_id: int,
    session: dict,
    storage: dict,
    timezone: str,
    logger: logging.Logger,
    send_master: bool = False,
) -> None:
    ticket = build_ticket_from_session(session, timezone, storage)
    storage.setdefault("tickets", []).append(ticket)
    clear_session(storage, chat_id)
    save_storage(storage)
    summary = build_summary(ticket)
    send_message(token, chat_id, summary)
    send_message(token, chat_id, "Спасибо! Заявка сохранена.")
    if send_master:
        send_master_contact(token, chat_id)
    logger.info("ticket created %s", ticket["ticket_id"])


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


def handle_update(token: str, update: dict, logger: logging.Logger) -> None:
    message = update.get("message") or {}
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

    if not chat_id:
        return

    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    storage = load_storage()
    session = ensure_session(storage, chat_id, timezone)

    if not message.get("text") and message.get("message_id"):
        send_message(token, chat_id, "Пока могу принимать только текстовые сообщения.")
        return

    if text.startswith("/master"):
        send_master_contact(token, chat_id)
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
        send_master_contact(token, chat_id)
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
            token, chat_id, session, storage, timezone, logger, send_master=False
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
            token, chat_id, session, storage, timezone, logger, send_master=False
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
                token, chat_id, session, storage, timezone, logger, send_master=False
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
                token, chat_id, session, storage, timezone, logger, send_master=False
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
            token, chat_id, session, storage, timezone, logger, send_master=True
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
