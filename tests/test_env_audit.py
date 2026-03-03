import unittest
from unittest.mock import patch

from services.client_bot_service.app.config import ClientBotConfig


class EnvAuditTestCase(unittest.TestCase):
    def test_aliases_and_priority(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "",
                "TELEGRAM_BOT_TOKEN": "fallback-token",
                "DOMAIN": "HTTPS://bot_123.bothost.ru/",
                "BOT_PATH_SECRET": "abc",
                "CLIENT_MASTER_IDS": "1,2",
                "CLIENT_CHAT_ID": "-100123",
                "PORT": "7777",
            },
            clear=False,
        ):
            cfg = ClientBotConfig.from_env()
            token, source = ClientBotConfig.resolve_token()

        self.assertEqual(token, "fallback-token")
        self.assertEqual(source, "TELEGRAM_BOT_TOKEN")
        self.assertEqual(cfg.public_base_url, "https://bot_123.bothost.ru")
        self.assertEqual(cfg.webhook_url, "https://bot_123.bothost.ru/webhook/abc")
        self.assertEqual(cfg.master_user_ids_raw, "1,2")
        self.assertEqual(cfg.masters_chat_id_raw, "-100123")
        self.assertEqual(cfg.port, 7777)


if __name__ == "__main__":
    unittest.main()
