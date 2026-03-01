import logging
import unittest

from flask import Flask

from bots.client_bot import main as client_main
from bots.client_bot.main import register_webapp_routes


class WebAppSubmitValidationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        register_webapp_routes(self.app, token="TEST_TOKEN", logger=logging.getLogger("test"))
        self.client = self.app.test_client()

    def test_submit_without_init_data(self) -> None:
        response = self.client.post("/api/webapp/submit", json={"form": {}})
        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload.get("error"), "invalid_init_data")
        self.assertEqual(payload.get("reason"), "missing")

    def test_submit_phone_required_with_valid_session_token(self) -> None:
        secret = client_main.get_webapp_session_secret("TEST_TOKEN")
        session_token = client_main.build_webapp_session_token(42, secret, 3600)
        response = self.client.post("/api/webapp/submit", json={"form": {"name": "John"}, "session_token": session_token})
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertEqual(payload.get("error"), "phone_required")


if __name__ == "__main__":
    unittest.main()
