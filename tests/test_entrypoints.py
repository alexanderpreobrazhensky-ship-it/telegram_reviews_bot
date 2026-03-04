from pathlib import Path
import unittest


class EntrypointTests(unittest.TestCase):
    def test_index_js_runs_python_main(self):
        content = Path("index.js").read_text(encoding="utf-8")
        self.assertIn("spawn('python'", content)
        self.assertIn("['main.py']", content)

    def test_root_main_imports_client_service_only(self):
        content = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("from services.client_bot_service.app.main import main as service_main", content)
        self.assertNotIn("reviews", content.lower())


if __name__ == "__main__":
    unittest.main()
