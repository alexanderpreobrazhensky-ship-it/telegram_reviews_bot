import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bots.client_bot.main as client_main


class PostsQueueSmokeTestCase(unittest.TestCase):
    def test_posts_queue_file_create_and_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue_file = Path(tmp) / "data" / "posts_queue.json"
            storage = {"posts": [], "post_settings": {"enabled": True}}

            with patch.object(client_main, "get_posts_queue_file_path", return_value=str(queue_file)):
                ok_init = client_main.ensure_posts_queue_file(storage, logging.getLogger("test"))
                self.assertTrue(ok_init)
                self.assertTrue(queue_file.exists())

                storage["posts"].append({"post_id": "1", "status": "queued"})
                ok_sync = client_main.sync_posts_queue_file(storage)
                self.assertTrue(ok_sync)

            payload = json.loads(queue_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["posts"][0]["post_id"], "1")


if __name__ == "__main__":
    unittest.main()
