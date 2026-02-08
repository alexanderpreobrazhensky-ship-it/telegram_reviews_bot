import unittest

from bots.client_bot.main import parse_int_maybe


class ParseIntMaybeTestCase(unittest.TestCase):
    def test_parse_int_maybe_values(self) -> None:
        self.assertEqual(parse_int_maybe("19"), 19)
        self.assertEqual(parse_int_maybe(19), 19)
        self.assertEqual(parse_int_maybe(" 19 "), 19)
        self.assertIsNone(parse_int_maybe("abc"))
        self.assertIsNone(parse_int_maybe(None))
        self.assertIsNone(parse_int_maybe({"x": 1}))


if __name__ == "__main__":
    unittest.main()
