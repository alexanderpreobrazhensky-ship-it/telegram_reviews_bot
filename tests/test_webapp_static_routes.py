import logging
import unittest

from flask import Flask

from bots.client_bot.main import register_webapp_routes


class WebAppStaticRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        register_webapp_routes(app, token="TEST", logger=logging.getLogger("test"))
        self.client = app.test_client()

    def test_static_routes_200(self) -> None:
        for path in ("/WEBAPP", "/assets/webapp.bundle.js", "/assets/webapp.bundle.css", "/app.js", "/app.css"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
