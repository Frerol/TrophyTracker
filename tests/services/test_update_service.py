import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from retrocheevos.services import update_service


def _response(status=200, payload=None, json_error=None):
    def _json():
        if json_error:
            raise json_error
        return payload

    return SimpleNamespace(
        status_code=status, json=_json, raise_for_status=lambda: None
    )


class VersionComparisonTests(unittest.TestCase):
    def test_double_digit_minor_beats_single_digit(self):
        """The reason this isn't a string compare. Lexically "1.10.0" sorts
        *below* "1.9.0", so a naive version of this would stop reporting
        updates at exactly the tenth release and never say why."""
        self.assertTrue(update_service.is_newer("1.10.0", "1.9.0"))
        self.assertFalse(update_service.is_newer("1.9.0", "1.10.0"))

    def test_tag_prefix_and_suffix_are_tolerated(self):
        self.assertTrue(update_service.is_newer("v1.2.0", "1.1.0"))
        self.assertTrue(update_service.is_newer("v1.3.0-beta", "1.2.0"))

    def test_equal_versions_are_not_newer(self):
        self.assertFalse(update_service.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(update_service.is_newer("1.2", "1.2.0"))

    def test_unparseable_reads_as_no_update(self):
        """Never the other way round: a banner raised by a tag nobody can
        parse can't be cleared by updating."""
        self.assertFalse(update_service.is_newer("latest", "1.0.0"))
        self.assertFalse(update_service.is_newer("", "1.0.0"))


class DismissalTests(unittest.TestCase):
    def test_nothing_dismissed_yet(self):
        self.assertTrue(update_service.should_notify("v1.4.0", None))
        self.assertTrue(update_service.should_notify("v1.4.0", ""))

    def test_same_version_stays_dismissed(self):
        self.assertFalse(update_service.should_notify("v1.4.0", "v1.4.0"))

    def test_a_newer_release_notifies_again(self):
        """The point of storing the version instead of a boolean."""
        self.assertTrue(update_service.should_notify("v1.5.0", "v1.4.0"))
        self.assertTrue(update_service.should_notify("v2.0.0", "v1.9.0"))
        self.assertTrue(update_service.should_notify("v1.10.0", "v1.9.0"))

    def test_older_release_does_not_resurrect_the_banner(self):
        """A release being deleted or replaced shouldn't re-nag about a
        version already waved away."""
        self.assertFalse(update_service.should_notify("v1.3.0", "v1.4.0"))

    def test_equivalent_but_differently_written_version(self):
        self.assertFalse(update_service.should_notify("1.4.0", "v1.4.0"))

    def test_unreadable_dismissal_does_not_silence_forever(self):
        """Opposite bias to `is_newer` on purpose: a stored value nobody can
        parse must not suppress every future update, because the symptom
        would be nothing happening at all."""
        self.assertTrue(update_service.should_notify("v1.4.0", "corrupted"))

    def test_unreadable_dismissal_still_matches_itself(self):
        self.assertFalse(update_service.should_notify("nightly", "nightly"))


class CheckForUpdateTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("GITHUB_OWNER", "test-owner"), ("GITHUB_REPO", "test-repo")):
            patcher = patch.object(update_service, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unconfigured_source_does_not_make_a_request(self):
        with patch.object(update_service, "GITHUB_OWNER", ""), patch.object(
            update_service.requests, "get"
        ) as get:
            self.assertIsNone(update_service.check_for_update())
        get.assert_not_called()

    def test_every_failure_is_silent(self):
        """Being offline must not surface anything. This runs at startup."""
        for label, patched in {
            "offline": {"side_effect": requests.ConnectionError("no route")},
            "timeout": {"side_effect": requests.Timeout("slow")},
            "no releases": {"return_value": _response(status=404)},
            "not json": {"return_value": _response(json_error=ValueError("html"))},
            "wrong type": {"return_value": _response(payload=["nope"])},
            "empty": {"return_value": _response(payload={})},
        }.items():
            with self.subTest(label):
                with patch.object(update_service.requests, "get", **patched):
                    self.assertIsNone(update_service.check_for_update("1.0.0"))

    def test_current_version_reports_nothing(self):
        payload = {"tag_name": "v1.0.0", "html_url": "https://example/1"}
        with patch.object(
            update_service.requests, "get", return_value=_response(payload=payload)
        ):
            self.assertIsNone(update_service.check_for_update("1.0.0"))

    def test_newer_release_is_reported(self):
        payload = {"tag_name": "v1.4.0", "html_url": "https://example/1.4.0"}
        with patch.object(
            update_service.requests, "get", return_value=_response(payload=payload)
        ):
            available = update_service.check_for_update("1.0.0")
        self.assertEqual(available.version, "v1.4.0")
        self.assertEqual(available.url, "https://example/1.4.0")

    def test_missing_url_falls_back_to_releases_page(self):
        with patch.object(
            update_service.requests,
            "get",
            return_value=_response(payload={"tag_name": "v2.0.0"}),
        ):
            available = update_service.check_for_update("1.0.0")
        self.assertEqual(available.url, update_service.RELEASES_PAGE_URL)

    def test_no_credentials_are_sent_to_github(self):
        """The app holds a RetroAchievements API key. It must never ride
        along on a request to a different host."""
        captured = {}

        def _capture(*args, **kwargs):
            captured.update(kwargs)
            return _response(payload={})

        with patch.object(update_service.requests, "get", side_effect=_capture):
            update_service.check_for_update("1.0.0")

        self.assertNotIn("params", captured)
        headers = {key.lower() for key in captured.get("headers", {})}
        self.assertNotIn("authorization", headers)
        self.assertEqual(captured.get("timeout"), update_service.REQUEST_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
