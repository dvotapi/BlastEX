"""Единое правило «прогноз посчитан старой базой Kuz-Ram 1.0.0»."""
import unittest

from intelligence.calibration.old_base import is_old_base, version_major


class OldBaseRuleTests(unittest.TestCase):
    def test_version_major(self):
        cases = {"1.0.0": 1, "2": 2, "3.0.0": 3, "10.1": 10, "v2.0.0": None, "abc": None, "": None, "-1.0": None, "²": None}
        for version, expected in cases.items():
            with self.subTest(version=version):
                self.assertEqual(version_major(version), expected)

    def test_version_major_of_huge_number_is_not_recognized(self):
        self.assertIsNone(version_major("9" * 5000 + ".0"))

    def test_old_base(self):
        cases = (
            ("kuzram", "1.0.0", True),
            ("kuzram", "1", True),
            ("kuzram", "0.9", True),
            ("kuzram_legacy", "1.0.0", True),
            ("kuzram_legacy", "2.0.0", True),
            ("kuzram_legacy", "abc", True),
            ("swebrec_legacy", "", True),
            ("", "", True),
            ("", "2.0.0", True),
            ("kuzram", "2.0.0", False),
            ("kuzram", "2", False),
            ("kuzram", "3.0.0", False),
            ("kuzram", "20.0.0", False),
            ("kuzram", "v2.0.0", False),
            ("kuzram", "abc", False),
            ("kuzram", "", False),
            ("kuznetsov", "2.0.0", False),
        )
        for model, version, expected in cases:
            with self.subTest(model=model, version=version):
                self.assertIs(is_old_base(model, version), expected)


if __name__ == "__main__":
    unittest.main()
