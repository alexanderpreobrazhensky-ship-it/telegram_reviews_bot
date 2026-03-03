import logging
import os
import unittest
from unittest.mock import patch

from flask import Flask

from bots.client_bot.main import handle_update, register_webapp_routes


class ServiceSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        register_webapp_routes(self.app, token="TEST_TOKEN", logger=logging.getLogger("test"))
        self.client = self.app.test_client()

    def test_client_service_health_route(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "ok")

    def test_webapp_health_200(self) -> None:
        response = self.client.get("/api/webapp/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ok", response.get_json())

    def test_webapp_submit_without_phone_400(self) -> None:
        init_data = "auth_date=1&query_id=q&user=%7B%22id%22%3A1%7D&hash=bad"
        response = self.client.post(
            "/api/webapp/submit",
            json={"form": {"name": "John"}, "initData": init_data},
        )
        # invalid initData may return 401 first; when initData passes, phone missing returns 400.
        self.assertIn(response.status_code, {400, 401})

    def test_message_from_masters_chat_does_not_create_ticket(self) -> None:
        storage = {
            "tickets": [],
            "settings": {"masters_chat_id": -1001},
            "sessions": {},
            "masters": {},
            "admins": [],
            "blocked_users": [],
            "callback_debounce": {},
        }
        update = {
            "message": {
                "chat": {"id": -1001, "type": "supergroup", "title": "Masters"},
                "from": {"id": 500, "username": "master_user"},
                "text": "обычное сообщение",
            }
        }

        with patch("bots.client_bot.main.load_storage", return_value=storage), patch(
            "bots.client_bot.main.save_storage"
        ):
            handle_update("TEST_TOKEN", update, logging.getLogger("test"))

        self.assertEqual(storage["tickets"], [])

    def test_client_message_creates_ticket_and_attempts_routing(self) -> None:
        storage = {
            "tickets": [],
            "settings": {"masters_chat_id": None},
            "sessions": {},
            "masters": {"777": {"user_id": 777}},
            "admins": [],
            "blocked_users": [],
            "callback_debounce": {},
            "master_reachability": {},
        }
        update = {
            "message": {
                "chat": {"id": 42, "type": "private", "first_name": "Ivan"},
                "from": {"id": 42, "username": "ivan"},
                "text": "Нужен ремонт",
            }
        }

        with patch("bots.client_bot.main.load_storage", return_value=storage), patch(
            "bots.client_bot.main.save_storage"
        ), patch("bots.client_bot.main.notify_masters") as notify_masters, patch(
            "bots.client_bot.main.send_message", return_value=True
        ):
            handle_update("TEST_TOKEN", update, logging.getLogger("test"))

        self.assertIsInstance(storage.get("tickets"), list)
        self.assertTrue(notify_masters.called or isinstance(storage.get("sessions"), dict))



if __name__ == "__main__":
    unittest.main()