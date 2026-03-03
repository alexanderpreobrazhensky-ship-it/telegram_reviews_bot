import os
import unittest
from unittest.mock import patch

from services.client_bot_service.app.config import ClientBotConfig
import bots.client_bot.main as client_main


class BotHostContractTestCase(unittest.TestCase):
    def test_dockerfile_runs_python_main(self) -> None:
        with open("Dockerfile", "r", encoding="utf-8") as fh:
            content = fh.read().lower()
        self.assertIn('cmd ["python", "main.py"]', content)

    def test_root_has_only_node_bootstrap_entrypoint(self) -> None:
        forbidden = ["package.json", "app.js", "server.js", "main.js", "run.js", "yarn.lock", "package-lock.json"]
        root_files = set(os.listdir("."))
        self.assertIn("index.js", root_files)
        for name in forbidden:
            self.assertNotIn(name, root_files)

    def test_entrypoint_imports_service_main(self) -> None:
        with open("main.py", "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("from services.client_bot_service.app.main import main as client_main", content)

    def test_port_resolution_port_has_priority(self) -> None:
        with patch.dict(os.environ, {"PORT": "9000", "CLIENT_SERVICE_PORT": "7000"}, clear=False):
            self.assertEqual(ClientBotConfig.resolve_port(), 9000)

    def test_port_resolution_fallback_client_service_port(self) -> None:
        with patch.dict(os.environ, {"PORT": "", "CLIENT_SERVICE_PORT": "7000"}, clear=False):
            self.assertEqual(ClientBotConfig.resolve_port(), 7000)

    def test_token_resolution_fallback_chain_when_primary_empty(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_BOT_TOKEN": "tg-token",
                "BOT_API_TOKEN": "bot-token",
                "API_TOKEN": "api-token",
                "BOT_TOKEN": "bot-token2",
                "TOKEN": "token3",
            },
            clear=False,
        ):
            token, source = ClientBotConfig.resolve_token()
        self.assertEqual(token, "tg-token")
        self.assertEqual(source, "TELEGRAM_BOT_TOKEN")

    def test_token_resolution_primary_has_priority(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "primary-token",
                "TELEGRAM_BOT_TOKEN": "tg-token",
            },
            clear=False,
        ):
            token, source = ClientBotConfig.resolve_token()
        self.assertEqual(token, "primary-token")
        self.assertEqual(source, "CLIENT_TELEGRAM_BOT_TOKEN")

    def test_token_resolution_supports_bot_token_fallbacks(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_BOT_TOKEN": "",
                "BOT_API_TOKEN": "",
                "API_TOKEN": "",
                "BOT_TOKEN": "bot-token",
                "TOKEN": "token",
            },
            clear=False,
        ):
            token, source = ClientBotConfig.resolve_token()
        self.assertEqual(token, "bot-token")
        self.assertEqual(source, "BOT_TOKEN")

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

    def test_token_resolution_raises_without_any_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_BOT_TOKEN": "",
                "BOT_API_TOKEN": "",
                "API_TOKEN": "",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                ClientBotConfig.resolve_token()

    def test_normalize_webapp_url_removes_double_scheme(self) -> None:
        self.assertEqual(
            client_main.normalize_webapp_url("https://HTTPS://example.com/WEBAPP/"),
            "https://example.com/WEBAPP",
        )


if __name__ == "__main__":
    unittest.main()
