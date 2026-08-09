"""Recent Activity must not hammer RetroAchievements' API.

One refresh is ~63 requests: one for the follow list, then two per user
(summary + game progress) across self plus up to 30 followed accounts, paced
0.3s apart. At the original 30-second interval that was ~126 requests a
minute for as long as Home stayed open — heavier than the hash backfill, and
unlike the backfill it never finished.

The visible symptom was Recent Activity failing for the whole duration of a
catalog sync, the two competing for the same burst limiter. But retrying at
full cadence into a limiter is what turns one rate-limited call into an
hour of them, and the feed was over-fetching before any sync started.

These exercise the pacing logic directly rather than through a real
`HomePage`, which would need an account, a database and a live API. What is
worth locking down is the arithmetic: the base cadence, that failures back
off, that success recovers, and that the one path which can bypass the
backoff — arriving on Home — respects it.
"""

import unittest
from unittest.mock import MagicMock, patch

from retrocheevos.gui.pages.home_page import (
    ACTIVITY_BACKOFF_CEILING_MS,
    ACTIVITY_REFRESH_INTERVAL_MS,
    HomePage,
)


class _Pacing:
    """A bare object carrying just the state the pacing methods touch, with
    those methods bound to it. Avoids constructing a real `HomePage`.
    """

    def __init__(self) -> None:
        self._activity_retry_interval_ms = ACTIVITY_REFRESH_INTERVAL_MS
        self._activity_last_attempt = None
        self._activity_refresh_timer = MagicMock()

    back_off = HomePage._back_off_activity_refresh
    reset = HomePage._reset_activity_refresh_interval
    is_due = HomePage._activity_refresh_is_due


class ActivityRefreshPacingTests(unittest.TestCase):
    def test_base_interval_is_three_minutes(self) -> None:
        """Guards the number itself: 30s was ~126 requests/minute sustained."""
        self.assertEqual(ACTIVITY_REFRESH_INTERVAL_MS, 180_000)

    def test_each_failure_doubles_the_interval(self) -> None:
        pacing = _Pacing()
        pacing.back_off()
        self.assertEqual(pacing._activity_retry_interval_ms, 360_000)
        pacing.back_off()
        self.assertEqual(pacing._activity_retry_interval_ms, 720_000)

    def test_backoff_stops_at_the_ceiling(self) -> None:
        pacing = _Pacing()
        for _ in range(20):
            pacing.back_off()
        self.assertEqual(pacing._activity_retry_interval_ms, ACTIVITY_BACKOFF_CEILING_MS)

    def test_backoff_is_applied_to_the_timer(self) -> None:
        pacing = _Pacing()
        pacing.back_off()
        pacing._activity_refresh_timer.setInterval.assert_called_once_with(360_000)

    def test_success_restores_the_base_cadence(self) -> None:
        """Without this a bad patch of network leaves the feed on a
        25-minute timer for the rest of the session.
        """
        pacing = _Pacing()
        for _ in range(5):
            pacing.back_off()
        pacing.reset()
        self.assertEqual(pacing._activity_retry_interval_ms, ACTIVITY_REFRESH_INTERVAL_MS)
        pacing._activity_refresh_timer.setInterval.assert_called_with(
            ACTIVITY_REFRESH_INTERVAL_MS
        )

    def test_success_while_already_at_base_touches_nothing(self) -> None:
        pacing = _Pacing()
        pacing.reset()
        pacing._activity_refresh_timer.setInterval.assert_not_called()

    def test_first_ever_refresh_is_due(self) -> None:
        self.assertTrue(_Pacing().is_due())

    def test_arriving_on_home_again_immediately_is_not_due(self) -> None:
        """Bouncing between Home and Library would otherwise fire 63 requests
        each way, regardless of any backoff in force.
        """
        pacing = _Pacing()
        with patch("retrocheevos.gui.pages.home_page.time.monotonic", return_value=1000.0):
            pacing._activity_last_attempt = 1000.0
            self.assertFalse(pacing.is_due())

    def test_due_again_once_the_interval_has_passed(self) -> None:
        pacing = _Pacing()
        pacing._activity_last_attempt = 1000.0
        with patch("retrocheevos.gui.pages.home_page.time.monotonic", return_value=1180.1):
            self.assertTrue(pacing.is_due())

    def test_a_backed_off_interval_also_gates_arrival(self) -> None:
        """Three minutes after a failure that stretched the wait to six, an
        arrival on Home must still wait.
        """
        pacing = _Pacing()
        pacing.back_off()  # 360s
        pacing._activity_last_attempt = 1000.0
        with patch("retrocheevos.gui.pages.home_page.time.monotonic", return_value=1200.0):
            self.assertFalse(pacing.is_due())
        with patch("retrocheevos.gui.pages.home_page.time.monotonic", return_value=1400.0):
            self.assertTrue(pacing.is_due())


if __name__ == "__main__":
    unittest.main()
