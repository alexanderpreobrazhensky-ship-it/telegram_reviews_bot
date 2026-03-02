import importlib
import os
import unittest
from unittest.mock import patch


class PollingWebhookModeTestCase(unittest.TestCase):
    def test_polling_deletes_webhook_with_drop_pending_updates(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "test-token",
                "CLIENT_BOT_MODE": "polling",
            },
            clear=False,
        ):
            import bots.client_bot.main as client_main
            client_main = importlib.reload(client_main)
            with patch.object(client_main, "poll_updates") as poll_mock, patch.object(
                client_main, "delete_webhook"
            ) as delete_mock, patch.object(client_main, "db_init_settings"), patch.object(
                client_main, "ensure_persistent_defaults"
            ), patch.object(client_main, "ensure_core_settings_defaults"), patch.object(
                client_main, "set_bot_commands"
            ), patch.object(client_main, "get_master_contact_username", return_value=("", False, "")), patch.object(
                client_main, "get_admin_ids_with_source", return_value=([], "env")
            ), patch.object(client_main, "get_master_ids", return_value=([], "env")), patch.object(
                client_main, "is_queue_enabled", return_value=False
            ), patch.object(client_main, "load_storage", return_value={}), patch.object(
                client_main, "ensure_storage_defaults"
            ), patch.object(client_main, "migrate_storage_settings_to_db"), patch.object(
                client_main, "bootstrap_admins", return_value=False
            ), patch.object(client_main, "resolve_webapp_public_url", return_value="https://example.com/WEBAPP"), patch.object(
                client_main, "AIService"
            ), patch.object(client_main, "configure_telegram"), patch.object(client_main, "build_logger") as build_logger:
                logger = build_logger.return_value
                client_main.main()
                delete_mock.assert_called_once_with("test-token", logger, drop_pending_updates=True)
                poll_mock.assert_called_once()


    def test_webhook_mode_with_invalid_url_falls_back_to_polling(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CLIENT_TELEGRAM_BOT_TOKEN": "test-token",
                "CLIENT_BOT_MODE": "webhook",
                "WEBHOOK_URL": "javascript:alert(1)",
            },
            clear=False,
        ):
            import bots.client_bot.main as client_main
            client_main = importlib.reload(client_main)
            with patch.object(client_main, "poll_updates") as poll_mock, patch.object(
                client_main, "delete_webhook"
            ) as delete_mock, patch.object(client_main, "db_init_settings"), patch.object(
                client_main, "ensure_persistent_defaults"
            ), patch.object(client_main, "ensure_core_settings_defaults"), patch.object(
                client_main, "set_bot_commands"
            ), patch.object(client_main, "get_master_contact_username", return_value=("", False, "")), patch.object(
                client_main, "get_admin_ids_with_source", return_value=([], "env")
            ), patch.object(client_main, "get_master_ids", return_value=([], "env")), patch.object(
                client_main, "is_queue_enabled", return_value=False
            ), patch.object(client_main, "load_storage", return_value={}), patch.object(
                client_main, "ensure_storage_defaults"
            ), patch.object(client_main, "migrate_storage_settings_to_db"), patch.object(
                client_main, "bootstrap_admins", return_value=False
            ), patch.object(client_main, "resolve_webapp_public_url", return_value="https://example.com/WEBAPP"), patch.object(
                client_main, "AIService"
            ), patch.object(client_main, "configure_telegram"), patch.object(client_main, "build_logger") as build_logger:
                logger = build_logger.return_value
                client_main.main()
                delete_mock.assert_called_once_with("test-token", logger, drop_pending_updates=True)
                poll_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
