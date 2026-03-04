import unittest

from bots.client_bot.main import build_logger, create_flask_app


class StaticRoutesTests(unittest.TestCase):
    def setUp(self):
        self.app = create_flask_app("dummy:token", build_logger("Europe/Moscow"))
        self.client = self.app.test_client()

    def test_static_routes(self):
        for path in [
            "/WEBAPP",
            "/WEBAPP/",
            "/assets/webapp.bundle.js",
            "/assets/webapp.bundle.css",
            "/app.js",
            "/app.css",
            "/WEBAPP/config.json",
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=path)


if __name__ == "__main__":
    unittest.main()
