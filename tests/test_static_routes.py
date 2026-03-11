import unittest


@unittest.skip('Legacy Python static route checks are historical-only and not part of current deploy contract.')
class LegacyStaticRoutesTests(unittest.TestCase):
    def test_legacy_placeholder(self):
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
