from pathlib import Path
import unittest


class PostsQueueOwnershipTestCase(unittest.TestCase):
    def test_client_bot_starts_posts_queue_worker(self) -> None:
        content = Path("bots/client_bot/main.py").read_text(encoding="utf-8")
        self.assertIn("target=posts_queue_worker", content)

    def test_posts_queue_file_in_client_data_dir(self) -> None:
        content = Path("bots/client_bot/main.py").read_text(encoding="utf-8")
        self.assertIn('"posts_queue.json"', content)
        self.assertIn('os.path.join(base_dir, "data", "posts_queue.json")', content)


if __name__ == "__main__":
    unittest.main()
