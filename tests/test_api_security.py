import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.security import create_session_token, read_session_token, require_internal_api_key


class ApiSecurityTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as error:
                require_internal_api_key(None)
            self.assertEqual(error.exception.status_code, 503)

    def test_key_is_required_and_compared(self):
        with patch.dict(os.environ, {"BLASTEX_API_KEY": "secret"}, clear=True):
            with self.assertRaises(HTTPException) as error:
                require_internal_api_key("wrong")
            self.assertEqual(error.exception.status_code, 401)
            self.assertIsNone(require_internal_api_key("secret"))

    def test_signed_session_round_trip(self):
        with patch.dict(os.environ, {"BLASTEX_SESSION_SECRET": "session-secret"}, clear=True):
            token = create_session_token("admin@example.ru", "admin", "default", 4_102_444_800)
            payload = read_session_token(token)
            self.assertEqual(payload["sub"], "admin@example.ru")
            self.assertIsNone(read_session_token(token + "broken"))


if __name__ == "__main__":
    unittest.main()
