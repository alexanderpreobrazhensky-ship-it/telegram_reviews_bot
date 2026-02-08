import logging
import unittest

from flask import Flask

from bots.client_bot.main import register_webapp_routes


class ClientWebAppSubmitInvalidTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        register_webapp_routes(self.app, token="TEST_TOKEN", logger=logging.getLogger("test"))
        self.client = self.app.test_client()

    def test_submit_without_init_data(self) -> None:
        response = self.client.post("/api/webapp/submit", json={"form": {}})
        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertEqual(payload.get("error"), "invalid_init_data")


if __name__ == "__main__":
    unittest.main()
