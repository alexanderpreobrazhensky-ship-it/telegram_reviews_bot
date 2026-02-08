import logging
import unittest

from flask import Flask

from bots.client_bot.main import register_webapp_routes


class ClientWebAppStaticRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        register_webapp_routes(self.app, token="TEST_TOKEN", logger=logging.getLogger("test"))
        self.client = self.app.test_client()

    def test_static_routes(self) -> None:
        for path in ("/WEBAPP", "/app.css", "/app.js", "/WEBAPP/config.json"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=f"{path} expected 200")
            response.close()


if __name__ == "__main__":
    unittest.main()
