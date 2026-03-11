import unittest


@unittest.skip('Legacy Python health checks are historical-only and not part of current deploy contract.')
class LegacyHealthTests(unittest.TestCase):
    def test_legacy_placeholder(self):
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
