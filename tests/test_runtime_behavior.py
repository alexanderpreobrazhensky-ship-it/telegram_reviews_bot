import os
import unittest
from contextlib import ExitStack
from unittest.mock import ANY, patch

from bots.client_bot import main as client_main


class RuntimeBehaviorTests(unittest.TestCase):
    def _patch_main_bootstrap(self):
        stack = ExitStack()
        stack.enter_context(patch.object(client_main, "build_logger", return_value=client_main.logging.getLogger("test")))
        stack.enter_context(patch.object(client_main, "db_init_settings"))
        stack.enter_context(patch.object(client_main, "ensure_persistent_defaults"))
        stack.enter_context(patch.object(client_main, "ensure_core_settings_defaults"))
        stack.enter_context(patch.object(client_main, "load_storage", return_value={"tickets": [], "sessions": {}, "settings": {}}))
        stack.enter_context(patch.object(client_main, "ensure_storage_defaults", side_effect=lambda s: s))
        stack.enter_context(patch.object(client_main, "migrate_storage_settings_to_db"))
        stack.enter_context(patch.object(client_main, "bootstrap_admins", return_value=False))
        stack.enter_context(patch.object(client_main, "save_storage"))
        stack.enter_context(patch.object(client_main, "set_bot_commands"))
        stack.enter_context(patch.object(client_main, "get_master_contact_username", return_value=(None, False, False)))
        stack.enter_context(patch.object(client_main, "get_admin_ids_with_source", return_value=([], "none")))
        stack.enter_context(patch.object(client_main, "get_master_ids", return_value=([], "none")))
        stack.enter_context(patch.object(client_main, "get_queue_stats", return_value={"pending": 0}))
        stack.enter_context(patch.object(client_main, "is_queue_enabled", return_value=False))
        stack.enter_context(patch.object(client_main, "threading"))
        stack.enter_context(patch.object(client_main, "AIService"))
        stack.enter_context(patch.object(client_main, "get_ai_config_source", return_value="test"))
        stack.enter_context(patch.object(client_main, "ensure_channel_pin", return_value=(True, "ok")))
        return stack

    @patch.dict(os.environ, {}, clear=True)
    def test_master_chat_plain_text_does_not_create_ticket(self):
        update = {
            "message": {
                "chat": {"id": -10055, "type": "supergroup", "title": "Masters"},
                "from": {"id": 999, "username": "user"},
                "text": "обычный текст",
            }
        }
        storage = {
            "settings": {"masters_chat_id": -10055},
            "tickets": [],
            "sessions": {},
            "pending_reply": {},
            "master_sessions": {},
            "masters": {},
        }
        with ExitStack() as stack:
            stack.enter_context(patch.object(client_main, "load_storage", return_value=storage))
            stack.enter_context(patch.object(client_main, "ensure_storage_defaults", side_effect=lambda s: s))
            stack.enter_context(patch.object(client_main, "ensure_session", return_value={}))
            stack.enter_context(patch.object(client_main, "get_settings", return_value={}))
            stack.enter_context(patch.object(client_main, "AIService"))
            stack.enter_context(patch.object(client_main, "process_callback", return_value=False))
            process_ticket = stack.enter_context(patch.object(client_main, "process_client_ticket_message"))
            send_message = stack.enter_context(patch.object(client_main, "send_message"))
            client_main.handle_update("dummy", update, client_main.build_logger("Europe/Moscow"))
        process_ticket.assert_not_called()
        send_message.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "CLIENT_TELEGRAM_BOT_TOKEN": "tkn",
            "BOT_PATH_SECRET": "secret",
            "WEBHOOK_URL": "https://bot.example",
            "CLIENT_BOT_MODE": "webhook",
        },
        clear=True,
    )
    def test_webhook_mode_calls_set_webhook(self):
        with self._patch_main_bootstrap() as stack:
            delete_webhook = stack.enter_context(patch.object(client_main, "delete_webhook"))
            set_webhook = stack.enter_context(patch.object(client_main, "set_webhook"))
            create_app = stack.enter_context(patch.object(client_main, "create_flask_app"))
            app = create_app.return_value
            app.run.side_effect = RuntimeError("stop")
            with self.assertRaises(RuntimeError):
                client_main.main()
        delete_webhook.assert_called_with("tkn", ANY, drop_pending_updates=True)
        set_webhook.assert_called_with("tkn", ANY, "https://bot.example/webhook/secret")

    @patch.dict(
        os.environ,
        {
            "CLIENT_TELEGRAM_BOT_TOKEN": "tkn",
            "BOT_PATH_SECRET": "secret",
            "CLIENT_BOT_MODE": "webhook",
        },
        clear=True,
    )
    def test_webhook_fallback_to_polling_deletes_webhook(self):
        with self._patch_main_bootstrap() as stack:
            delete_webhook = stack.enter_context(patch.object(client_main, "delete_webhook"))
            set_webhook = stack.enter_context(patch.object(client_main, "set_webhook"))
            poll_updates = stack.enter_context(patch.object(client_main, "poll_updates"))
            client_main.main()
        set_webhook.assert_not_called()
        delete_webhook.assert_called_with("tkn", ANY, drop_pending_updates=True)
        poll_updates.assert_called_once()


if __name__ == "__main__":
    unittest.main()
