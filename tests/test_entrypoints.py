import unittest


@unittest.skip('Legacy Python test suite is excluded from Node-first production narrative.')
class LegacyEntrypointTests(unittest.TestCase):
    def test_legacy_placeholder(self):
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
