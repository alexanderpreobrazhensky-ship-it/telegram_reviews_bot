import importlib
import json
import sys
from datetime import datetime, timezone


def load_bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "testtoken1234567890")
    monkeypatch.setenv("WEBHOOK_URL", "https://example.com")
    monkeypatch.setenv("SET_WEBHOOK_ON_START", "0")
    monkeypatch.setenv("SUPERADMIN_ID", "738627185")
    monkeypatch.setenv("REPORT_CHAT_IDS", "")
    monkeypatch.setenv("DATABASE_URL", "")
    if "main" in sys.modules:
        del sys.modules["main"]
    module = importlib.import_module("main")
    return module


def setup_bot(monkeypatch):
    module = load_bot(monkeypatch)
    sent = []

    def fake_post(url, json=None, data=None, files=None, timeout=None):
        sent.append({"url": url, "json": json, "data": data, "files": files})

        class Resp:
            status_code = 200
            text = '{"ok":true}'

            def json(self):
                return {"ok": True}

        return Resp()

    def fake_get(url, params=None, timeout=None):
        class Resp:
            status_code = 200
            text = '{"ok":true,"result":{"url":"https://example.com/webhook","pending_update_count":0}}'

            def json(self):
                return {"ok": True, "result": {"url": "https://example.com/webhook", "pending_update_count": 0}}

        return Resp()

    monkeypatch.setattr(module.requests, "post", fake_post)
    monkeypatch.setattr(module.requests, "get", fake_get)

    sessions = {}

    def db_set_session(chat_id, state, payload):
        sessions[chat_id] = {"state": state, "payload": payload, "updated_at": datetime.now(timezone.utc)}

    def db_get_session(chat_id):
        return sessions.get(chat_id)

    def db_clear_session(chat_id):
        sessions.pop(chat_id, None)

    monkeypatch.setattr(module, "db_set_session", db_set_session)
    monkeypatch.setattr(module, "db_get_session", db_get_session)
    monkeypatch.setattr(module, "db_clear_session", db_clear_session)

    roles = {module.SUPERADMIN_ID: "owner"}

    def get_user_role(user_id):
        return roles.get(user_id, "none")

    monkeypatch.setattr(module, "get_user_role", get_user_role)
    monkeypatch.setattr(module, "can_use_bot", lambda uid: get_user_role(uid) in ("owner", "staff", "user"))
    monkeypatch.setattr(module, "can_manage_access", lambda uid: get_user_role(uid) == "owner")

    module.DB_OK = True
    monkeypatch.setattr(module, "db_count_access_users", lambda active_only=True: len(roles))

    return module, sent, sessions, roles


def post_update(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_start_menu(monkeypatch):
    module, sent, _, _ = setup_bot(monkeypatch)
    client = module.app.test_client()
    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": module.SUPERADMIN_ID}, "text": "/start"}},
    )
    assert sent
    assert sent[-1]["json"]["reply_markup"]["keyboard"]


def test_instruction_menu(monkeypatch):
    module, sent, _, _ = setup_bot(monkeypatch)
    client = module.app.test_client()
    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 2, "message": {"chat": {"id": 2}, "from": {"id": module.SUPERADMIN_ID}, "text": "📘 Инструкция"}},
    )
    assert "Автоцентр Лира" in sent[-1]["json"]["text"]
    assert "🛠️🚗" in sent[-1]["json"]["text"]


def test_manual_review_flow(monkeypatch):
    module, sent, _, _ = setup_bot(monkeypatch)
    client = module.app.test_client()
    insert_calls = []
    monkeypatch.setattr(module, "db_insert_review", lambda **kwargs: insert_calls.append(kwargs) or 101)
    monkeypatch.setattr(module, "db_find_duplicate_review", lambda review_hash: None)

    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 3, "message": {"chat": {"id": 10}, "from": {"id": module.SUPERADMIN_ID}, "text": "➕ Добавить отзыв"}},
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 4,
            "callback_query": {
                "id": "cb1",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 10}},
                "data": "review_method:manual",
            },
        },
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 5, "message": {"chat": {"id": 10}, "from": {"id": module.SUPERADMIN_ID}, "text": "На дороге сломалась машина..."}},
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 6,
            "callback_query": {
                "id": "cb2",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 10}},
                "data": "platform:yandex",
            },
        },
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 7,
            "callback_query": {
                "id": "cb3",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 10}},
                "data": "rating:1",
            },
        },
    )
    assert insert_calls
    assert insert_calls[0]["rating"] == 1


def test_link_review_fallback(monkeypatch):
    module, sent, _, _ = setup_bot(monkeypatch)
    client = module.app.test_client()
    monkeypatch.setattr(
        module,
        "fetch_review_from_link",
        lambda url: {"parse_status": "blocked", "platform": None, "rating": None, "author_name": None, "review_text": None},
    )
    monkeypatch.setattr(module, "db_insert_review", lambda **kwargs: 55)

    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 10, "message": {"chat": {"id": 20}, "from": {"id": module.SUPERADMIN_ID}, "text": "➕ Добавить отзыв"}},
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 11,
            "callback_query": {
                "id": "cb4",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 20}},
                "data": "review_method:link",
            },
        },
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 12,
            "message": {
                "chat": {"id": 20},
                "from": {"id": module.SUPERADMIN_ID},
                "text": "https://yandex.ru/maps/org/lira/1014791361/reviews",
            },
        },
    )
    assert ("Выбери площадку" in sent[-1]["json"]["text"]) or ("Укажи рейтинг" in sent[-1]["json"]["text"])

    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 13,
            "callback_query": {
                "id": "cb5",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 20}},
                "data": "link_platform:yandex",
            },
        },
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 14,
            "callback_query": {
                "id": "cb6",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 20}},
                "data": "link_rating:5",
            },
        },
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 15, "message": {"chat": {"id": 20}, "from": {"id": module.SUPERADMIN_ID}, "text": "инкогнито 8919"}},
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 16,
            "message": {
                "chat": {"id": 20},
                "from": {"id": module.SUPERADMIN_ID},
                "text": "отличный автосервис, делают быстро и качественно",
            },
        },
    )
    assert "Проверь данные" in sent[-1]["json"]["text"]

    post_update(
        client,
        module.WEBHOOK_PATH,
        {
            "update_id": 17,
            "callback_query": {
                "id": "cb7",
                "from": {"id": module.SUPERADMIN_ID},
                "message": {"chat": {"id": 20}},
                "data": "link_confirm:yes",
            },
        },
    )
    last_message = next(item for item in reversed(sent) if item["url"].endswith("sendMessage"))
    assert "Отзыв добавлен" in last_message["json"]["text"]


def test_access_invite_kick(monkeypatch):
    module, sent, _, roles = setup_bot(monkeypatch)
    client = module.app.test_client()

    def upsert(chat_id, role, added_by, note=None):
        roles[int(chat_id)] = role

    def deactivate(chat_id):
        roles.pop(int(chat_id), None)

    monkeypatch.setattr(module, "db_upsert_access_user", upsert)
    monkeypatch.setattr(module, "db_deactivate_access_user", deactivate)

    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 20, "message": {"chat": {"id": 30}, "from": {"id": module.SUPERADMIN_ID}, "text": "/invite 123"}},
    )
    assert "добавлен" in sent[-1]["json"]["text"]

    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 21, "message": {"chat": {"id": 31}, "from": {"id": 123}, "text": "/start"}},
    )
    assert sent[-1]["json"]["text"].startswith("Привет")

    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 22, "message": {"chat": {"id": 30}, "from": {"id": module.SUPERADMIN_ID}, "text": "/kick 123"}},
    )
    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 23, "message": {"chat": {"id": 31}, "from": {"id": 123}, "text": "/start"}},
    )
    assert "Доступ запрещён" in sent[-1]["json"]["text"]


def test_diag_contains_webhook(monkeypatch):
    module, sent, _, _ = setup_bot(monkeypatch)
    client = module.app.test_client()
    post_update(
        client,
        module.WEBHOOK_PATH,
        {"update_id": 30, "message": {"chat": {"id": 40}, "from": {"id": module.SUPERADMIN_ID}, "text": "/diag"}},
    )
    assert "webhook_pending" in sent[-1]["json"]["text"]
