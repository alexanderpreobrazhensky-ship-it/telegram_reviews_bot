import logging
import unittest
from unittest.mock import patch

from bots.client_bot import main as client_main


class TestClientBotUtils(unittest.TestCase):
    def test_get_pinned_message_id_int(self):
        with patch.object(client_main, "get_core_setting", return_value=21):
            self.assertEqual(client_main.get_pinned_message_id(), 21)

    def test_get_pinned_message_id_str(self):
        with patch.object(client_main, "get_core_setting", return_value="21"):
            self.assertEqual(client_main.get_pinned_message_id(), 21)

    def test_get_pinned_message_id_invalid(self):
        with patch.object(client_main, "get_core_setting", return_value="abc"):
            self.assertIsNone(client_main.get_pinned_message_id())

    def test_normalize_webapp_url_uppercase(self):
        self.assertEqual(
            client_main.normalize_webapp_url("HTTPS://example.com/WEBAPP"),
            "https://example.com/WEBAPP",
        )

    def test_normalize_webapp_url_double_scheme(self):
        self.assertEqual(
            client_main.normalize_webapp_url("https://HTTPS://example.com/WEBAPP"),
            "https://example.com/WEBAPP",
        )

    def test_normalize_webapp_url_double_http_scheme(self):
        self.assertEqual(
            client_main.normalize_webapp_url("https://http://example.com/WEBAPP"),
            "https://example.com/WEBAPP",
        )

    def test_normalize_webapp_url_missing_scheme(self):
        self.assertEqual(
            client_main.normalize_webapp_url(" example.com/WEBAPP "),
            "https://example.com/WEBAPP",
        )


if __name__ == "__main__":
    unittest.main()


class TicketTtlAndPostponedTestCase(unittest.TestCase):
    def test_find_active_ticket_honors_env_ttl(self) -> None:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        import bots.client_bot.main as m

        now = datetime.now(ZoneInfo("Europe/Moscow"))
        storage = {"tickets": [
            {"ticket_id": "T1", "client_chat_id": 10, "status": "new", "updated_at": (now - timedelta(hours=13)).isoformat()},
            {"ticket_id": "T2", "client_chat_id": 10, "status": "new", "updated_at": (now - timedelta(hours=1)).isoformat()},
        ]}
        ticket = m.find_active_ticket(storage, 10, "Europe/Moscow")
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.get("ticket_id"), "T2")

    def test_postponed_auto_return_switches_to_new(self) -> None:
        import bots.client_bot.main as m
        storage = {"tickets": [{"ticket_id": "P1", "status": "postponed", "postponed_until": "2000-01-01T00:00:00+00:00", "client_chat_id": 1}], "settings": {}}
        with unittest.mock.patch("bots.client_bot.main.deliver_ticket") as deliver, unittest.mock.patch("bots.client_bot.main.save_storage"):
            m.check_reminders("T", storage, "Europe/Moscow", [], logging.getLogger("test"))
        self.assertEqual(storage["tickets"][0]["status"], "new")
        self.assertTrue(deliver.called)


class PinIdParsingTestCase(unittest.TestCase):
    def test_parse_int_maybe_handles_string_int(self) -> None:
        import bots.client_bot.main as m
        self.assertEqual(m.parse_int_maybe(" 123 "), 123)
        self.assertIsNone(m.parse_int_maybe("12a"))
