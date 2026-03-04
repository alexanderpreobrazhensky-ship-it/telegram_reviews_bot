import unittest

from bots.client_bot.main import build_logger, create_flask_app


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.app = create_flask_app("dummy:token", build_logger("Europe/Moscow"))
        self.client = self.app.test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("service"), "client-bot")
        self.assertIn(payload.get("mode"), {"webhook", "polling"})


if __name__ == "__main__":
    unittest.main()
