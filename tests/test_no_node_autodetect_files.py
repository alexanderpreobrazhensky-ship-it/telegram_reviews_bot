import os
import unittest


class NoNodeAutodetectFilesTestCase(unittest.TestCase):
    def test_only_bootstrap_index_js_in_repo_root(self) -> None:
        forbidden = {"package.json", "app.js", "server.js", "main.js"}
        root_files = set(os.listdir("."))
        self.assertTrue(forbidden.isdisjoint(root_files))
        self.assertIn("index.js", root_files)

    def test_bootstrap_index_js_spawns_python_main(self) -> None:
        with open("index.js", "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('spawn("python", ["main.py"]', content)


if __name__ == "__main__":
    unittest.main()
