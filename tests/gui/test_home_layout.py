"""The rebuilt Home (R19): header, metrics, Continue Playing rows and layout."""

import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

import retrocheevos.database.connection as db
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.pages import home_page
from retrocheevos.services import job_coordinator as jobs
from retrocheevos.services import notification_service
from retrocheevos.widgets.continue_playing_row import NO_EMULATOR_REASON, NO_MATCH_TEXT
from tests.gui.test_navigation import close_window, patch_live_calls

_app = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    return predicate()


class FormatLastSyncedTests(unittest.TestCase):
    def test_captions(self):
        now = datetime(2026, 11, 21, 12, 0)
        self.assertEqual(home_page.format_last_synced(None, now), 'Never synced')
        self.assertEqual(home_page.format_last_synced(now - timedelta(seconds=20), now), 'Last synced just now')
        self.assertEqual(home_page.format_last_synced(now - timedelta(minutes=5), now), 'Last synced 5 min ago')
        self.assertEqual(home_page.format_last_synced(now - timedelta(hours=3), now), 'Last synced 3 h ago')
        self.assertEqual(home_page.format_last_synced(now - timedelta(days=2), now), 'Last synced on 2026-11-19')


class HomeLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.database = self.tmp / 'home.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.database).close()
        patch_live_calls(self)
        jobs.reset()
        self.addCleanup(jobs.reset)

    def seed(self, *, stats=True, emulator=True):
        now = datetime.now()
        with db.get_connection(self.database) as c:
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
            c.execute("INSERT INTO consoles(id, name) VALUES(3, 'SNES')")
            if emulator:
                c.execute("INSERT INTO emulator_configs(console_id, executable_path) VALUES(3, '/usr/bin/true')")
            if stats:
                c.execute(
                    "INSERT INTO profile_stats(account_id, points, hardcore_points, games_beaten, games_mastered,"
                    " completion_percentage, last_synced_at, true_points, stats_revision)"
                    " VALUES(1, 12480, 12000, 27, 14, 42.3, ?, 18760, 99)",
                    ((now - timedelta(minutes=5)).isoformat(),),
                )
            for game_id, title, counts, percent in (
                (1, 'Counted', (34, 42), 80.9), (2, 'Percent only', None, 50.0), (3, 'Unknown', None, None),
            ):
                c.execute("INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, 3, 1)", (game_id, title))
                rom = self.tmp / f'{game_id}.rom'
                rom.write_bytes(b'x')
                c.execute(
                    "INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id, last_played_at)"
                    " VALUES(?, ?, ?, 3, 1, ?)", (game_id, str(rom), f'h{game_id}', (now - timedelta(hours=game_id)).isoformat()),
                )
                if percent is not None:
                    c.execute(
                        "INSERT INTO game_completion(account_id, game_id, percent_complete, achievements_unlocked,"
                        " achievements_total) VALUES(1, ?, ?, ?, ?)",
                        (game_id, percent, *(counts or (None, None))),
                    )
            rom = self.tmp / 'Mystery Hack (USA).sfc'
            rom.write_bytes(b'x')
            c.execute(
                "INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id) VALUES(NULL, ?, 'hx', 3, 1)",
                (str(rom),),
            )
            for index in range(5):
                c.execute(
                    "INSERT INTO badges(account_id, name, image_path, owned, is_event) VALUES(1, ?, ?, 1, ?)",
                    (f'Award {index}', f'/Images/{index}.png', 1 if index == 0 else 0),
                )

    def open_window(self):
        with patch.object(MainWindow, '_start_update_check', new=lambda self: None):
            window = MainWindow()
        self.addCleanup(close_window, window)
        window.showNormal()
        window.resize(1240, 780)
        QTest.qWait(30)
        return window, window.destination('home')

    def test_metrics_and_freshness_without_and_with_stats(self):
        self.seed(stats=False)
        window, home = self.open_window()
        self.assertEqual(home._metric_points.value_text(), '—')
        self.assertEqual(home._freshness_label.text(), 'Never synced')
        with db.get_connection(self.database) as c:
            c.execute(
                "INSERT INTO profile_stats(account_id, points, hardcore_points, games_beaten, games_mastered,"
                " completion_percentage, last_synced_at, true_points) VALUES(1, 12480, 0, 27, 14, 42.3, ?, 18760)",
                ((datetime.now() - timedelta(minutes=5)).isoformat(),),
            )
        home.refresh()
        self.assertEqual(
            [card.value_text() for card in (home._metric_points, home._metric_true_points,
                                            home._metric_beaten, home._metric_mastered)],
            ['12,480', '18,760', '27', '14'],
        )
        self.assertEqual(home._freshness_label.text(), 'Last synced 5 min ago')
        self.assertIn('42.3%', home._metric_mastered.toolTip())

    def test_continue_playing_rows_never_show_unknown_as_zero(self):
        self.seed()
        _window, home = self.open_window()
        rows = {row.title: row for row in home.continue_playing_rows()}
        self.assertEqual(rows['Counted'].progress_caption(), '34/42 achievements')
        self.assertEqual(rows['Percent only'].progress_caption(), '50% complete')
        self.assertEqual(rows['Unknown'].progress_caption(), 'Progress unavailable')
        self.assertFalse(rows['Unknown'].bar_visible())
        self.assertEqual(rows['Mystery Hack'].progress_caption(), NO_MATCH_TEXT)
        self.assertTrue(all(row.play_enabled() for row in rows.values()))

    def test_play_is_guarded_without_an_emulator(self):
        self.seed(emulator=False)
        _window, home = self.open_window()
        rows = home.continue_playing_rows()
        self.assertTrue(rows)
        for row in rows:
            self.assertFalse(row.play_enabled())
            self.assertEqual(row.play_unavailable_reason(), NO_EMULATOR_REASON)

    def test_unmatched_row_menu_removes_the_rom(self):
        self.seed()
        _window, home = self.open_window()
        row = next(row for row in home.continue_playing_rows() if row.rom is not None)
        texts = [action.text() for action in row.build_menu().actions()]
        self.assertEqual(texts, ['Choose cover…', 'Remove from Library'])
        row.build_menu().actions()[1].trigger()
        self.assertEqual(sum(1 for r in home.continue_playing_rows() if r.rom is not None), 0)

    def test_sync_now_waits_for_the_job_slot_and_refreshes(self):
        self.seed()
        _window, home = self.open_window()
        wait_until(lambda: home._sync_now_button.isEnabled())
        token = jobs.try_acquire(jobs.JOB_SCAN_FOLDER)
        home._update_sync_controls()
        self.assertFalse(home._sync_now_button.isEnabled())
        self.assertIn(jobs.JOB_SCAN_FOLDER, home._sync_status_label.text())
        jobs.release(token)
        home._update_sync_controls()
        self.assertTrue(home._sync_now_button.isEnabled())
        updated = []
        home.profile_updated.connect(lambda: updated.append(True))
        with patch('retrocheevos.services.sync_service.sync_profile', return_value=None) as sync:
            home._sync_now_button.click()
            self.assertFalse(home._sync_now_button.isEnabled())
            self.assertTrue(wait_until(lambda: jobs.active_job() is None and not home._sync_in_progress))
        sync.assert_called_once()
        self.assertEqual(updated, [True])
        self.assertTrue(home._sync_now_button.isEnabled())

    def test_sync_now_failure_keeps_cached_data(self):
        self.seed()
        _window, home = self.open_window()
        wait_until(lambda: home._sync_now_button.isEnabled())
        with patch('retrocheevos.services.sync_service.sync_profile', side_effect=RuntimeError('offline')):
            home._sync_now_button.click()
            self.assertTrue(wait_until(lambda: not home._sync_in_progress))
        self.assertIn('Sync failed', home._sync_status_label.text())
        self.assertEqual(home._metric_points.value_text(), '12,480')
        self.assertIsNone(jobs.active_job())

    def test_catalog_controls_only_show_while_exploring(self):
        self.seed()
        window, home = self.open_window()
        explorer = home._explorer_page
        self.assertTrue(explorer.isHidden())
        self.assertFalse(home._metrics.isHidden())
        explore = next(b for b in home.findChildren(QPushButton) if b.text() == 'Explore catalog')
        explore.click()
        self.assertFalse(explorer.isHidden())
        self.assertFalse(explorer._filter_bar.isHidden())
        self.assertFalse(explorer._sync_bar_widget.isHidden())
        self.assertTrue(home._metrics.isHidden())
        home.reset_to_root()
        self.assertTrue(explorer.isHidden())
        self.assertFalse(home._metrics.isHidden())
        lists = next(b for b in home.findChildren(QPushButton) if b.text() == 'Your lists')
        lists.click()
        self.assertEqual(window.current_destination(), 'lists')

    def test_awards_summary_counts_and_unread_events(self):
        self.seed()
        _window, home = self.open_window()
        self.assertEqual(home._awards_summary.text(), '4 badges · 1 event award')
        self.assertTrue(home._awards_unread.isHidden())
        with db.get_connection(self.database) as c:
            for game_id in (900, 901):
                c.execute("INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, 'Event', 3, 1)", (game_id,))
        notification_service.record_new_events(1, [(900, 'Event A'), (901, 'Event B')])
        home.refresh()
        self.assertEqual(home._awards_unread.text(), '2 new events')
        self.assertFalse(home._awards_unread.isHidden())

    def test_no_account_states(self):
        _window, home = self.open_window()
        self.assertEqual(home._freshness_label.text(), 'No account selected')
        self.assertFalse(home._sync_now_button.isEnabled())
        self.assertEqual(home._metric_points.value_text(), '—')
        self.assertEqual(home._awards_summary.text(), home_page.AWARDS_EMPTY_TEXT)
        self.assertEqual(home.continue_playing_rows(), [])

    def test_layout_stacks_and_fits_at_the_minimum_window(self):
        self.seed()
        window, home = self.open_window()
        self.assertFalse(home.is_stacked())
        window.resize(1024, 720)
        QTest.qWait(50)
        self.assertTrue(home.is_stacked())
        viewport = home._page_scroll.viewport()
        bounds = viewport.rect()
        widgets = [home._sync_now_button, home._search_input, *home.findChildren(QPushButton)]
        for row in home.continue_playing_rows():
            widgets.append(row._play)
        for widget in widgets:
            if not widget.isVisibleTo(home):
                continue
            left = widget.mapTo(viewport, widget.rect().topLeft()).x()
            self.assertGreaterEqual(left, 0, widget)
            self.assertLessEqual(left + widget.width(), bounds.width(), (widget, widget.text() if hasattr(widget, 'text') else ''))
        window.resize(1440, 900)
        QTest.qWait(50)
        self.assertFalse(home.is_stacked())


if __name__ == '__main__':
    unittest.main()
