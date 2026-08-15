import unittest

from cost.auth import hash_password, verify_password


class PasswordHashTests(unittest.TestCase):
    def test_round_trip(self):
        encoded = hash_password("correct horse battery staple", salt=b"0123456789abcdef")
        self.assertTrue(verify_password("correct horse battery staple", encoded))
        self.assertFalse(verify_password("wrong", encoded))

    def test_malformed_hash_is_rejected(self):
        self.assertFalse(verify_password("password", "broken"))


if __name__ == "__main__":
    unittest.main()
