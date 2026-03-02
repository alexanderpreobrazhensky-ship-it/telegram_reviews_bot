from pathlib import Path
import unittest


class NoLegacyHostArtifactsTestCase(unittest.TestCase):
    def test_forbidden_files_absent(self) -> None:
        root = Path('.')
        self.assertFalse((root / 'legacy').exists())
        self.assertFalse((root / 'Procfile').exists())
        self.assertFalse((root / ('rail' + 'way.toml')).exists())

        forbidden_name = ('rail' + 'way').lower()
        this_file = Path(__file__).name
        for path in root.rglob('*'):
            if '.git' in path.parts or '__pycache__' in path.parts:
                continue
            if path.name == this_file:
                continue
            self.assertNotIn(forbidden_name, path.name.lower())

    def test_forbidden_strings_absent(self) -> None:
        legacy_word = 'rail' + 'way'
        legacy_domain = 'up.' + legacy_word + '.app'
        this_file = Path(__file__).name
        for path in Path('.').rglob('*'):
            if '.git' in path.parts or '__pycache__' in path.parts or not path.is_file():
                continue
            if path.name == this_file:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore').lower()
            self.assertNotIn(legacy_word, text)
            self.assertNotIn(legacy_domain, text)

    def test_bot_host_contract(self) -> None:
        dockerfile = Path('Dockerfile')
        entrypoint = Path('main.py')
        self.assertTrue(dockerfile.exists())
        self.assertTrue(entrypoint.exists())
        content = dockerfile.read_text(encoding='utf-8').lower()
        self.assertIn('cmd ["python", "main.py"]', content)


if __name__ == '__main__':
    unittest.main()
