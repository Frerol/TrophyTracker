"""The API key travels as a query parameter, so it is inside every URL this
client builds — and urllib3 puts the failing URL into its exception message.
These tests exist because that put the key in plaintext in the log file on
every network failure, under a class docstring promising the opposite.
"""

import io
import logging
import unittest

import requests

from retrocheevos.api import client as api_client
from retrocheevos.api.exceptions import RetroAchievementsAPIError

# 32 characters, the length RetroAchievements issues.
REALISTIC_KEY = "Ab3dEf6hIj9lMn2pQr5tUv8xYz1cDe4g"


class RedactCredentialsTests(unittest.TestCase):
    def test_secret_is_replaced(self):
        text = f"url: /API/X.php?z=someone&y={REALISTIC_KEY}"
        redacted = api_client.redact_credentials(text, REALISTIC_KEY)
        self.assertNotIn(REALISTIC_KEY, redacted)
        self.assertIn(api_client.REDACTED, redacted)

    def test_username_is_left_alone(self):
        """Usernames are public on RetroAchievements and are what makes a log
        readable when several accounts are involved."""
        text = f"?z=someone&y={REALISTIC_KEY}"
        self.assertIn("someone", api_client.redact_credentials(text, REALISTIC_KEY))

    def test_empty_secret_is_a_noop(self):
        self.assertEqual(api_client.redact_credentials("abc", ""), "abc")

    def test_short_secret_is_not_substituted(self):
        """Replacing a 3-character string would mangle unrelated text far
        more than it protects. Real keys are well past the threshold."""
        self.assertEqual(api_client.redact_credentials("abcabc", "abc"), "abcabc")


class RequestFailureTests(unittest.TestCase):
    def setUp(self):
        self._original_base = api_client.BASE_URL
        api_client.BASE_URL = "https://no-such-host.invalid/API"
        self._logger = logging.getLogger("retrocheevos.api.client")
        self._buffer = io.StringIO()
        self._handler = logging.StreamHandler(self._buffer)
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.DEBUG)

    def tearDown(self):
        api_client.BASE_URL = self._original_base
        self._logger.removeHandler(self._handler)

    def _failing_request(self):
        client = api_client.RetroAchievementsClient("someone", REALISTIC_KEY, timeout=2)
        with self.assertRaises(RetroAchievementsAPIError) as caught:
            client.get("API_GetUserSummary.php")
        return caught.exception

    def test_key_never_reaches_the_log(self):
        self._failing_request()
        self.assertNotIn(REALISTIC_KEY, self._buffer.getvalue())

    def test_key_never_reaches_the_raised_message(self):
        """`ServiceWorker.failed` emits `str(error)` straight into the UI."""
        self.assertNotIn(REALISTIC_KEY, str(self._failing_request()))

    def test_no_cause_chain(self):
        """`raise ... from error` would keep the original as `__cause__`, and
        `main.py::_log_uncaught_exception` logs with `exc_info` — which prints
        the cause's traceback, URL and all, straight past the redaction."""
        self.assertIsNone(self._failing_request().__cause__)

    def test_the_error_is_still_diagnosable(self):
        message = str(self._failing_request())
        self.assertIn("API_GetUserSummary.php", message)
        self.assertIn("ConnectionError", message)


if __name__ == "__main__":
    unittest.main()
