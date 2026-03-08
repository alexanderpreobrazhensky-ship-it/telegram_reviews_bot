from pathlib import Path
import unittest


class EntrypointTests(unittest.TestCase):
    def test_dockerfile_runs_python_main(self):
        content = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn('CMD ["python", "main.py"]', content)
        self.assertNotIn("index.js", content)

    def test_root_main_imports_client_service_only(self):
        content = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("from services.client_bot_service.app.main import main as service_main", content)
        self.assertIn("LIRA client-bot starting (root main.py)", content)
        self.assertNotIn("reviews", content.lower())


if __name__ == "__main__":
    unittest.main()
