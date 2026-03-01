import os
import unittest
from unittest.mock import patch

from services.client_bot_service.app.config import ClientBotConfig
import bots.client_bot.main as client_main


class BotHostContractTestCase(unittest.TestCase):
    def test_entrypoint_imports_service_main(self) -> None:
        with open("main.py", "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("from services.client_bot_service.app.main import main", content)
        self.assertNotIn("window", content)

    def test_port_resolution_port_has_priority(self) -> None:
        with patch.dict(os.environ, {"PORT": "9000", "CLIENT_SERVICE_PORT": "7000"}, clear=False):
            self.assertEqual(ClientBotConfig.resolve_port(), 9000)

    def test_port_resolution_fallback_client_service_port(self) -> None:
        with patch.dict(os.environ, {"PORT": "", "CLIENT_SERVICE_PORT": "7000"}, clear=False):
            self.assertEqual(ClientBotConfig.resolve_port(), 7000)

    def test_token_resolution_fallback_chain(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_BOT_TOKEN": "tg-token",
                "BOT_API_TOKEN": "bot-token",
                "API_TOKEN": "api-token",
            },
            clear=False,
        ):
            token, source = ClientBotConfig.resolve_token()
        self.assertEqual(token, "tg-token")
        self.assertEqual(source, "TELEGRAM_BOT_TOKEN")

    def test_domain_and_webapp_url_sanitization(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_WEBAPP_URL": "",
                "WEBAPP_URL": "",
                "DOMAIN": "https://BOT_123.BOTHOST.RU/",
                "WEBAPP_PATH": "/WEBAPP",
            },
            clear=False,
        ):
            self.assertEqual(client_main.sanitize_domain(os.getenv("DOMAIN")), "bot_123.bothost.ru")
            self.assertEqual(client_main.resolve_webapp_public_url(), "https://bot_123.bothost.ru/WEBAPP")


if __name__ == "__main__":
    unittest.main()
