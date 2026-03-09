from pathlib import Path
import unittest


class EntrypointTests(unittest.TestCase):
    def test_root_has_no_node_entrypoint_markers(self):
        forbidden = ["index.js", "app.js", "server.js", "main.js", "package.json", "package-lock.json"]
        for name in forbidden:
            self.assertFalse(Path(name).exists(), msg=f"{name} must not exist in repo root")

    def test_legacy_node_wrapper_is_moved_out_of_root(self):
        self.assertTrue(Path("legacy/index.js").exists())

    def test_dockerfile_runs_python_main(self):
        content = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn('FROM python:3.11-slim', content)
        self.assertIn('CMD ["python", "main.py"]', content)
        self.assertNotIn("npm", content.lower())
        self.assertNotIn("node", content.lower())

    def test_root_main_imports_client_service_only(self):
        main_path = Path("main.py")
        self.assertTrue(main_path.exists())
        content = main_path.read_text(encoding="utf-8")
        self.assertIn("from services.client_bot_service.app.main import main as service_main", content)
        self.assertIn("LIRA client-bot starting (root main.py)", content)


if __name__ == "__main__":
    unittest.main()
