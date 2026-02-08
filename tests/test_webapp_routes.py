import logging
import unittest

from flask import Flask

from bots.client_bot.main import register_webapp_routes


class WebAppRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        register_webapp_routes(self.app, token="TEST_TOKEN", logger=logging.getLogger("test"))
        self.client = self.app.test_client()

    def test_webapp_static_routes(self) -> None:
        response = self.client.get("/WEBAPP")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/app.js")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/app.css")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
