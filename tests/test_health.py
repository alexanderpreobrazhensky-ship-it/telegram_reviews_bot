import unittest

from bots.client_bot.main import build_logger, create_flask_app


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.app = create_flask_app("dummy:token", build_logger("Europe/Moscow"))
        self.client = self.app.test_client()

    def test_health_endpoints(self):
        for path in ["/health", "/service-health"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIsInstance(payload, dict)
            self.assertEqual(payload.get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
