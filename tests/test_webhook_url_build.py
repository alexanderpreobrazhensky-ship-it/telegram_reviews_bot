import os
import unittest
from unittest.mock import patch

from bots.client_bot.main import normalize_webapp_url, resolve_webhook_url


class WebhookUrlBuildTests(unittest.TestCase):
    @patch.dict(os.environ, {"WEBHOOK_URL": "https://a.example", "BOT_PATH_SECRET": "s"}, clear=True)
    def test_webhook_url_priority_webhook_url(self):
        url, source = resolve_webhook_url()
        self.assertEqual(url, "https://a.example/webhook/s")
        self.assertEqual(source, "WEBHOOK_URL")

    @patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://b.example", "BOT_PATH_SECRET": "s"}, clear=True)
    def test_webhook_url_priority_public_base_url(self):
        url, source = resolve_webhook_url()
        self.assertEqual(url, "https://b.example/webhook/s")
        self.assertEqual(source, "PUBLIC_BASE_URL")

    @patch.dict(os.environ, {"DOMAIN": "c.example", "BOT_PATH_SECRET": "s"}, clear=True)
    def test_webhook_url_priority_domain(self):
        url, source = resolve_webhook_url()
        self.assertEqual(url, "https://c.example/webhook/s")
        self.assertEqual(source, "DOMAIN")

    def test_url_normalization_fixes_double_protocol_and_trailing_slash(self):
        self.assertEqual(normalize_webapp_url(" https://https://A.EXAMPLE/path/ "), "https://a.example/path")
        self.assertEqual(normalize_webapp_url("https://http://b.example"), "https://b.example")

    def test_invalid_url_returns_none(self):
        self.assertIsNone(normalize_webapp_url("https:///"))


if __name__ == "__main__":
    unittest.main()
