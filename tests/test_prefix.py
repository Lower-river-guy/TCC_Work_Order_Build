import unittest

from app.prefix import validate_prefix


class PrefixTests(unittest.TestCase):
    def test_default_when_blank(self):
        self.assertEqual(validate_prefix(""), "RK-")
        self.assertEqual(validate_prefix("   "), "RK-")

    def test_accepts_common_prefixes(self):
        self.assertEqual(validate_prefix("RK-"), "RK-")
        self.assertEqual(validate_prefix("MH-"), "MH-")
        self.assertEqual(validate_prefix("KL-"), "KL-")

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            validate_prefix("../RK-")
        with self.assertRaises(ValueError):
            validate_prefix("RK-/bad")
        with self.assertRaises(ValueError):
            validate_prefix("RK-\\bad")


if __name__ == "__main__":
    unittest.main()
