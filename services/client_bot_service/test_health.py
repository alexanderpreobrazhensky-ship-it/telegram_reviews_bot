import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import build_app


class ClientServiceHealthTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ['CLIENT_TELEGRAM_BOT_TOKEN'] = 'token'

    def test_health(self) -> None:
        app, _ = build_app()
        client = app.test_client()
        response = client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json().get('status'), 'ok')


if __name__ == '__main__':
    unittest.main()
