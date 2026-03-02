import json
import tempfile
import unittest
from pathlib import Path

from services.reviews_bot_service.app.posts_queue import ensure_posts_queue_storage


class PostsQueueOwnershipTestCase(unittest.TestCase):
    def test_client_bot_starts_posts_queue_worker(self) -> None:
        content = Path("bots/client_bot/main.py").read_text(encoding="utf-8")
        self.assertIn("target=posts_queue_worker", content)

    def test_reviews_bot_queue_migrates_from_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            legacy = data_dir / "posts_queue.jsonl"
            legacy.write_text('{"post_id": "p1", "status": "queued"}\n', encoding="utf-8")

            from services.reviews_bot_service.app import posts_queue as pq

            old_root = pq.REPO_ROOT
            old_data = pq.DATA_DIR
            old_json = pq.QUEUE_JSON
            old_jsonl = pq.LEGACY_JSONL
            try:
                pq.REPO_ROOT = root
                pq.DATA_DIR = data_dir
                pq.QUEUE_JSON = data_dir / "posts_queue.json"
                pq.LEGACY_JSONL = legacy

                path = ensure_posts_queue_storage()
                self.assertEqual(path, pq.QUEUE_JSON)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(len(payload.get("posts", [])), 1)
                self.assertEqual(payload["posts"][0]["post_id"], "p1")
            finally:
                pq.REPO_ROOT = old_root
                pq.DATA_DIR = old_data
                pq.QUEUE_JSON = old_json
                pq.LEGACY_JSONL = old_jsonl


if __name__ == "__main__":
    unittest.main()
