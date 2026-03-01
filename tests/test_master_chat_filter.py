import logging
import unittest
from unittest.mock import patch

from bots.client_bot import main as client_main


class MasterChatFilterTestCase(unittest.TestCase):
    def test_plain_text_in_masters_chat_does_not_create_ticket(self) -> None:
        storage = {
            "tickets": [],
            "sessions": {},
            "settings": {"masters_chat_id": -1001234567890},
            "admins": [],
            "masters": [111],
        }
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": -1001234567890, "type": "supergroup", "title": "Masters"},
                "from": {"id": 111, "username": "master"},
                "text": "просто текст",
            },
        }

        with patch.object(client_main, "load_storage", return_value=storage), patch.object(
            client_main, "save_storage", return_value=None
        ), patch.object(client_main, "send_message", return_value=None):
            client_main.handle_update("TEST_TOKEN", update, logging.getLogger("test"))

        self.assertEqual(len(storage["tickets"]), 0)


if __name__ == "__main__":
    unittest.main()
