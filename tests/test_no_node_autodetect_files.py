import os
import unittest


class NoNodeAutodetectFilesTestCase(unittest.TestCase):
    def test_no_node_entrypoint_files_in_repo_root(self) -> None:
        forbidden = {"package.json", "index.js", "app.js", "server.js"}
        root_files = set(os.listdir("."))
        self.assertTrue(forbidden.isdisjoint(root_files))

    def test_dockerfile_python_only(self) -> None:
        with open("Dockerfile", "r", encoding="utf-8") as fh:
            content = fh.read().lower()
        self.assertIn('cmd ["python", "main.py"]', content)
        self.assertNotIn("npm", content)
        self.assertNotIn("node", content)


if __name__ == "__main__":
    unittest.main()
