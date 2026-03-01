import unittest
from unittest.mock import patch

from bots.client_bot.main import get_pinned_message_id


class ClientPinStorageTestCase(unittest.TestCase):
    def test_get_pinned_message_id_accepts_int_and_str(self) -> None:
        with patch("bots.client_bot.main.get_core_setting", return_value=123):
            self.assertEqual(get_pinned_message_id(), 123)
        with patch("bots.client_bot.main.get_core_setting", return_value="123"):
            self.assertEqual(get_pinned_message_id(), 123)


if __name__ == "__main__":
    unittest.main()
