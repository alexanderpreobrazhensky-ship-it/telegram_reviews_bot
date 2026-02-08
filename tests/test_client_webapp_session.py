import logging
import os
import unittest

from flask import Flask

from bots.client_bot.main import register_webapp_routes


class ClientWebAppSessionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_test_mode = os.environ.get("CLIENT_WEBAPP_TEST_MODE")
        os.environ["CLIENT_WEBAPP_TEST_MODE"] = "1"
        self.app = Flask(__name__)
        register_webapp_routes(self.app, token="TEST_TOKEN", logger=logging.getLogger("test"))
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        if self._prev_test_mode is None:
            os.environ.pop("CLIENT_WEBAPP_TEST_MODE", None)
        else:
            os.environ["CLIENT_WEBAPP_TEST_MODE"] = self._prev_test_mode

    def test_session_endpoint_ok(self) -> None:
        response = self.client.post("/api/webapp/session", json={"initData": "TEST_VALID"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertTrue(payload.get("ok"))
        self.assertTrue(payload.get("token"))

    def test_session_endpoint_invalid(self) -> None:
        response = self.client.post("/api/webapp/session", json={"initData": ""})
        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("error"), "SESSION_INVALID")

    def test_submit_with_session_token(self) -> None:
        session_response = self.client.post("/api/webapp/session", json={"initData": "TEST_VALID"})
        self.assertEqual(session_response.status_code, 200)
        session_payload = session_response.get_json()
        self.assertIsNotNone(session_payload)
        token = session_payload.get("token")
        self.assertTrue(token)
        form = {
            "carPlate": "A123AA",
            "description": "Тестовая заявка",
            "phone": "+79990000000",
            "car_known": True,
        }
        response = self.client.post("/api/webapp/submit", json={"sessionToken": token, "form": form})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        self.assertTrue(payload.get("ok"))


if __name__ == "__main__":
    unittest.main()
