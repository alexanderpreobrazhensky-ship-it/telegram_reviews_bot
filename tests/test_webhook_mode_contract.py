import unittest
from unittest.mock import patch

from services.client_bot_service.app.main import main


class WebhookModeContractTestCase(unittest.TestCase):
    def test_webhook_mode_calls_delete_before_set(self) -> None:
        order: list[str] = []

        def mark_delete(*args, **kwargs):
            order.append("delete")

        def mark_set(*args, **kwargs):
            order.append("set")
            return True

        class DummyApp:
            def __init__(self):
                self.config = {}

            def run(self, **_):
                return None

            def get(self, *_args, **_kwargs):
                def decorator(func):
                    return func
                return decorator

        app = DummyApp()
        env = {
            "CLIENT_TELEGRAM_BOT_TOKEN": "test-token",
            "CLIENT_BOT_MODE": "webhook",
            "PUBLIC_BASE_URL": "https://bot.example.com",
            "BOT_PATH_SECRET": "secret123",
        }
        with patch.dict("os.environ", env, clear=False), patch(
            "services.client_bot_service.app.main.ClientBotConfig.resolve_token",
            return_value=("test-token", "CLIENT_TELEGRAM_BOT_TOKEN"),
        ), patch("services.client_bot_service.app.main.create_flask_app", return_value=app), patch(
            "services.client_bot_service.app.main.configure_telegram"
        ), patch("services.client_bot_service.app.main.delete_webhook", side_effect=mark_delete) as delete_mock, patch(
            "services.client_bot_service.app.main.set_webhook", side_effect=mark_set
        ) as set_mock:
            main()

        delete_mock.assert_called_once_with("test-token", unittest.mock.ANY, drop_pending_updates=True)
        set_mock.assert_called_once_with("test-token", unittest.mock.ANY, "https://bot.example.com/webhook/secret123")
        self.assertEqual(order, ["delete", "set"])


if __name__ == "__main__":
    unittest.main()
