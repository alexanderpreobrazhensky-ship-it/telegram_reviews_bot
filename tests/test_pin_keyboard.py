import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def load_main():
    os.environ["TELEGRAM_BOT_TOKEN"] = "testtoken1234567890"
    os.environ["WEBHOOK_URL"] = "https://example.com"
    os.environ["SET_WEBHOOK_ON_START"] = "0"
    os.environ["SUPERADMIN_ID"] = "738627185"
    os.environ["REPORT_CHAT_IDS"] = ""
    os.environ["DATABASE_URL"] = ""
    if "main" in sys.modules:
        del sys.modules["main"]
    module = importlib.import_module("main")
    return module


class ChannelPinKeyboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = load_main()

    def test_keyboard_has_only_url_buttons(self):
        keyboard = self.main._channel_pin_keyboard()
        for row in keyboard["inline_keyboard"]:
            for button in row:
                self.assertIn("url", button)
                self.assertNotIn("web_app", button)
                self.assertNotIn("callback_data", button)

    def test_route_button_toggle(self):
        original = self.main.ROUTE_URL
        try:
            self.main.ROUTE_URL = ""
            keyboard = self.main._channel_pin_keyboard()
            texts = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
            self.assertNotIn("📍 Как доехать", texts)

            self.main.ROUTE_URL = "https://example.com/route"
            keyboard = self.main._channel_pin_keyboard()
            texts = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
            self.assertIn("📍 Как доехать", texts)
        finally:
            self.main.ROUTE_URL = original


if __name__ == "__main__":
    unittest.main()
