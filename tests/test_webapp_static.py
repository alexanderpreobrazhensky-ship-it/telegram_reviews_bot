import importlib
import logging
import os
import sys
import unittest
from pathlib import Path

from flask import Flask

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def load_client_bot():
    os.environ["CLIENT_WEBAPP_ENABLED"] = "1"
    os.environ["WEBAPP_ENABLED"] = "1"
    if "bots.client_bot.main" in sys.modules:
        del sys.modules["bots.client_bot.main"]
    module = importlib.import_module("bots.client_bot.main")
    return module


class WebAppStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_bot = load_client_bot()

    def setUp(self):
        self.app = Flask(__name__)
        self.client_bot.register_webapp_routes(self.app, "test-token", logging.getLogger("test"))

    def test_static_routes(self):
        client = self.app.test_client()
        for path in ("/WEBAPP", "/app.css", "/webapp.css", "/app.js", "/webapp.js", "/WEBAPP/config.json"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200, msg=f"{path} expected 200, got {response.status_code}")
            response.close()


if __name__ == "__main__":
    unittest.main()
