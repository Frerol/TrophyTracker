"""Shared pacing must serialize callers and remain cancellable under penalties."""

import threading
import time
import unittest
from unittest.mock import Mock, patch

from retrocheevos.api.client import RequestPacer, RetroAchievementsClient
from retrocheevos.api.exceptions import RateLimitError
from retrocheevos.services.sync_service import _with_rate_limit_retry, MAX_RATE_LIMIT_RETRIES
from retrocheevos.utils.cancellation import OperationCancelled, cancellation_scope


class RequestPacingTests(unittest.TestCase):
    def test_cancelled_penalty_does_not_block_another_waiter_or_send_http(self):
        pacer = RequestPacer(0.01)
        pacer.penalize(120)
        cancel = threading.Event()
        entered = threading.Event()
        stopped = threading.Event()
        outcomes = []
        client = RetroAchievementsClient('synthetic', 'synthetic-key')
        client._session.get = Mock()

        def request():
            with cancellation_scope(cancel.is_set):
                entered.set()
                try:
                    client.get('synthetic.php')
                except OperationCancelled:
                    outcomes.append('cancelled')
                finally:
                    stopped.set()

        with patch('retrocheevos.api.client.pacer', pacer):
            thread = threading.Thread(target=request)
            thread.start()
            self.assertTrue(entered.wait(1))
            # Neither cancellation nor reset should wait on the pacing lock.
            cancel.set()
            self.assertTrue(stopped.wait(1))
            thread.join(1)
        self.assertEqual(outcomes, ['cancelled'])
        client._session.get.assert_not_called()
        pacer.reset()
        pacer.wait()

    def test_concurrent_requests_share_spacing(self):
        pacer = RequestPacer(0.02)
        barrier = threading.Barrier(4)
        times = []
        def request():
            barrier.wait()
            pacer.wait()
            times.append(time.monotonic())
        threads = [threading.Thread(target=request) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        times.sort()
        self.assertEqual(len(times), 4)
        self.assertTrue(all(b - a >= 0.015 for a, b in zip(times, times[1:])))

    def test_retry_guidance_bounded_exhaustion_and_success(self):
        call = Mock(side_effect=[RateLimitError('limited', retry_after=3), 42])
        with patch('retrocheevos.services.sync_service.interruptible_sleep') as sleep:
            self.assertEqual(_with_rate_limit_retry('test', call), 42)
        sleep.assert_called_once_with(3, None)
        call = Mock(side_effect=RateLimitError('limited', retry_after=3))
        with patch('retrocheevos.services.sync_service.interruptible_sleep') as sleep:
            with self.assertRaises(RateLimitError):
                _with_rate_limit_retry('test', call)
        self.assertEqual(call.call_count, MAX_RATE_LIMIT_RETRIES)
        self.assertEqual(sleep.call_count, MAX_RATE_LIMIT_RETRIES - 1)

    def test_retry_backoff_cancels_before_second_call(self):
        cancel = threading.Event()
        def limited():
            cancel.set()
            raise RateLimitError('limited', retry_after=120)
        call = Mock(side_effect=limited)
        with self.assertRaises(OperationCancelled):
            _with_rate_limit_retry('test', call, should_cancel=cancel.is_set)
        self.assertEqual(call.call_count, 1)
