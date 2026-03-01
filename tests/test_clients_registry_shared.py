import json
import os
import tempfile
import unittest

from shared.clients_registry import upsert_client


class SharedClientsRegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.NamedTemporaryFile(delete=False)
        self.temp.close()
        os.environ["CLIENTS_REGISTRY_PATH"] = self.temp.name

    def tearDown(self) -> None:
        os.environ.pop("CLIENTS_REGISTRY_PATH", None)
        try:
            os.unlink(self.temp.name)
        except FileNotFoundError:
            pass

    def test_create_and_merge_arrays(self) -> None:
        upsert_client(
            {
                "telegram_user_id": 1,
                "telegram_username": "user",
                "full_name": "User Name",
                "phones": ["+79990000000"],
            },
            source_tag="telegram_client_bot",
        )
        upsert_client(
            {
                "telegram_user_id": 1,
                "telegram_username": "user",
                "phones": ["+79991111111", "+79990000000"],
            },
            source_tag="webapp",
        )

        with open(self.temp.name, "r", encoding="utf-8") as fh:
            lines = [json.loads(line) for line in fh if line.strip()]

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["telegram_username"], "user")
        self.assertEqual(lines[0]["phones"], ["+79990000000", "+79991111111"])
        self.assertIn("telegram_client_bot", lines[0]["source_tags"])
        self.assertIn("webapp", lines[0]["source_tags"])

    def test_fallback_username_key_and_created_at_kept(self) -> None:
        first = upsert_client({"telegram_username": "onlyname", "phones": ["+70000000000"]}, source_tag="a")
        second = upsert_client({"telegram_username": "onlyname", "phones": ["+71111111111"]}, source_tag="b")
        self.assertEqual(first["created_at"], second["created_at"])
        self.assertNotEqual(first["updated_at"], second["updated_at"])
        self.assertEqual(second["phones"], ["+70000000000", "+71111111111"])


if __name__ == "__main__":
    unittest.main()
