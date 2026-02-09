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

    def test_normalize_webapp_url_missing_scheme(self):
        self.assertEqual(
            client_main.normalize_webapp_url(" example.com/WEBAPP "),
            "https://example.com/WEBAPP",
        )


if __name__ == "__main__":
    unittest.main()
