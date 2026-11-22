"""The Library grid (R22): model, delegate, page states and handoffs."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListView, QMessageBox

import retrocheevos.database.connection as db
from retrocheevos.core.library_filter import STATUS_IN_PROGRESS, STATUS_MASTERED, STATUS_UNMATCHED
from retrocheevos.database.migrations import initialize_database
from retrocheevos.gui.delegates.library_card_delegate import LibraryCardDelegate
from retrocheevos.gui.main_window import MainWindow
from retrocheevos.gui.models import library_grid_model
from retrocheevos.gui.models.library_grid_model import (
    CaptionRole, LibraryGridModel, PlayReasonRole, ProgressRole,
)
from retrocheevos.gui.pages import library_page
from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom, LibraryEntry
from retrocheevos.widgets import rom_folder_editor
from retrocheevos.widgets.rom_folder_editor import RomFolderEditor
from tests.gui.test_navigation import close_window, patch_live_calls

_app = QApplication.instance() or QApplication([])


class FakeLoader(QObject):
    image_ready = Signal(int, object)
    rom_image_ready = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, game):
        self.requests.append(('game', game.id))

    def request_rom(self, rom, cover_game=None):
        self.requests.append(('rom', rom.id))


def game_entry(game_id, title='Game', unlocked=None, total=None, percent=None, emulator=True):
    return LibraryEntry('game', title, 3, [f'/roms/{game_id}.sfc'], game=Game(game_id, title, 3, True),
                        achievements_unlocked=unlocked, achievements_total=total,
                        percent_complete=percent, has_emulator=emulator)


class ModelAndDelegateTests(unittest.TestCase):
    def setUp(self):
        self.loader = FakeLoader()
        self.model = LibraryGridModel(self.loader)
        patcher = patch.object(library_grid_model, 'cached_local_cover_path', return_value=Path('/nonexistent.png'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_captions_never_show_unknown_as_zero(self):
        rom = InstalledRom('/roms/hack.sfc', 'abc', 3, id=9)
        self.model.set_entries([
            game_entry(1, unlocked=34, total=42, percent=81),
            game_entry(2, percent=50),
            game_entry(3),
            LibraryEntry('rom', 'hack', 3, [rom.file_path], rom=rom),
            game_entry(4, emulator=False),
        ], {3: 'SNES'})
        rows = [self.model.index(row) for row in range(5)]
        self.assertEqual([index.data(CaptionRole) for index in rows], [
            '34/42 achievements', '50% complete', 'Progress unavailable', 'No catalog match',
            'Progress unavailable',
        ])
        self.assertAlmostEqual(rows[0].data(ProgressRole), 34 / 42)
        self.assertIsNone(rows[2].data(ProgressRole))
        self.assertIsNone(rows[3].data(ProgressRole))
        self.assertIsNone(rows[0].data(PlayReasonRole))
        self.assertEqual(rows[4].data(PlayReasonRole), 'No emulator')
        self.assertIn('no emulator', rows[4].data(Qt.ItemDataRole.AccessibleTextRole))
        no_hash = InstalledRom('/roms/game.rvz', '', 19, id=10)
        self.model.set_entries([LibraryEntry('rom', 'game', 19, [no_hash.file_path], rom=no_hash)], {19: 'Wii'})
        self.assertEqual(self.model.index(0).data(CaptionRole), 'No hash for this format')
        self.assertIn('cannot read this format directly', self.model.index(0).data(Qt.ItemDataRole.ToolTipRole))

    def test_covers_load_only_for_painted_rows_within_the_budget(self):
        self.model.set_entries([game_entry(i) for i in range(1, 501)], {3: 'SNES'})
        for row in (0, 1, 2, 1):
            self.model.index(row).data(Qt.ItemDataRole.DecorationRole)
        self.assertEqual(self.loader.requests, [('game', 1), ('game', 2), ('game', 3)])
        image = QPixmap(300, 300)
        image.fill(Qt.GlobalColor.red)
        for game_id in range(1, 501):
            self.model.index(game_id - 1).data(Qt.ItemDataRole.DecorationRole)
            self.loader.image_ready.emit(game_id, image)
        self.assertLessEqual(self.model.cached_bytes(), library_grid_model.IMAGE_CACHE_BYTES)
        self.assertEqual(self.model.index(499).data(Qt.ItemDataRole.DecorationRole).width(),
                         library_grid_model.COVER_EDGE)

    def test_play_button_is_hit_tested_and_guarded(self):
        self.model.set_entries([game_entry(1), game_entry(2, emulator=False)], {3: 'SNES'})
        view = QListView()
        self.addCleanup(view.close)
        delegate = LibraryCardDelegate(view)
        view.setModel(self.model)
        view.setItemDelegate(delegate)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.resize(600, 400)
        view.show()
        QTest.qWait(20)
        played = []
        delegate.play_requested.connect(lambda index: played.append(index.row()))
        for row in (0, 1):
            rect = view.visualRect(self.model.index(row))
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=delegate.play_rect(rect).center())
            # A click on the cover is not Play.
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center() - QPoint(0, 60))
        self.assertEqual(played, [0])


def _wait(predicate, timeout=5.0):
    import time
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    return predicate()


class LibraryPageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.database = self.tmp / 'library.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.database).close()
        patch_live_calls(self)
        with db.get_connection(self.database) as c:
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
            c.execute("INSERT INTO consoles(id, name) VALUES(3, 'SNES')")
            c.execute("INSERT INTO consoles(id, name) VALUES(12, 'PlayStation')")
            c.execute("INSERT INTO emulator_configs(console_id, executable_path) VALUES(3, '/usr/bin/true')")
            for game_id in range(1, 13):
                console = 12 if game_id == 12 else 3
                c.execute("INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, ?, 1)",
                          (game_id, f'Game {game_id:02d}', console))
                path = self.tmp / f'{game_id}.rom'
                path.write_bytes(b'x')
                c.execute("INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id)"
                          " VALUES(?, ?, ?, ?, 1)", (game_id, str(path), f'h{game_id}', console))
            c.execute("INSERT INTO game_completion(account_id, game_id, percent_complete, achievements_unlocked,"
                      " achievements_total, highest_award_kind) VALUES(1, 1, 100, 10, 10, 'mastered')")
            c.execute("INSERT INTO game_completion(account_id, game_id, percent_complete, achievements_unlocked,"
                      " achievements_total) VALUES(1, 2, 30, 3, 10)")
            path = self.tmp / 'Mystery Hack.sfc'
            path.write_bytes(b'x')
            c.execute("INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id)"
                      " VALUES(NULL, ?, 'hx', 3, 1)", (str(path),))
        with patch.object(MainWindow, '_start_update_check', new=lambda self: None):
            self.window = MainWindow()
        self.addCleanup(close_window, self.window)
        self.window.showNormal()
        self.window.resize(1240, 780)
        self.window.navigate('library')
        QTest.qWait(30)
        self.page = self.window.destination('library')

    def titles(self):
        return [entry.title for entry in self.page._model.entries()]

    def test_header_filters_search_and_system(self):
        self.assertEqual(self.page._count_label.text(), '13 local ROMs indexed')
        self.assertEqual(len(self.titles()), 13)
        self.page._set_status(STATUS_MASTERED)
        self.assertEqual(self.titles(), ['Game 01'])
        self.page._set_status(STATUS_IN_PROGRESS)
        self.assertEqual(self.titles(), ['Game 02'])
        self.page._set_status(STATUS_UNMATCHED)
        self.assertEqual(self.titles(), ['Mystery Hack'])
        self.page._filter_chips['all'].click()
        self.page._search.setText('game 1')
        self.assertEqual(self.titles(), ['Game 10', 'Game 11', 'Game 12'])
        self.page._system_filter.setCurrentIndex(self.page._system_filter.findData(12))
        self.assertEqual(self.titles(), ['Game 12'])
        # Kept across a refresh (R18 view state).
        self.page.refresh()
        self.assertEqual(self.titles(), ['Game 12'])
        self.page._search.setText('nothing like this')
        self.assertEqual(self.page.message_text(), library_page.NO_MATCH_TEXT)

    def test_unmatched_filter_empty_state(self):
        with db.get_connection(self.database) as c:
            c.execute("DELETE FROM installed_roms WHERE game_id IS NULL")
        self.page.refresh()
        self.page._set_status(STATUS_UNMATCHED)
        self.assertEqual(self.page.message_text(), library_page.ALL_MATCHED_TEXT)

    def test_empty_library_offers_folders(self):
        with db.get_connection(self.database) as c:
            c.execute("DELETE FROM installed_roms")
        self.page.refresh()
        self.assertEqual(self.page.message_text(), library_page.EMPTY_LIBRARY_TEXT)
        self.assertFalse(self.page._add_folder_button.isHidden())
        self.assertEqual(self.page._count_label.text(), 'No ROMs indexed yet')

    def test_columns_adapt_to_the_window(self):
        self.assertEqual(self.page.columns(), 4)
        self.window.resize(1024, 720)
        QTest.qWait(50)
        self.assertEqual(self.page.columns(), 3)

    def test_grid_is_stable_at_the_minimum_width_with_one_full_row(self):
        # Regression: three cards at the minimum width made the scroll bar
        # toggle and the last card jump between rows endlessly.
        with db.get_connection(self.database) as c:
            c.execute("DELETE FROM installed_roms WHERE game_id > 3 OR game_id IS NULL")
        self.page.refresh()
        for width in range(1300, 1019, -8):
            self.window.resize(width, 720)
            QTest.qWait(2)
        QTest.qWait(50)
        changes = []
        original = self.page._grid.setGridSize
        with patch.object(self.page._grid, 'setGridSize', side_effect=lambda size: (changes.append(size), original(size))):
            QTest.qWait(300)
        self.assertEqual(changes, [])
        self.assertEqual(self.page._model.rowCount(), 3)
        tops = {self.page._grid.visualRect(self.page._model.index(row)).top() for row in range(3)}
        self.assertEqual(len(tops), 1)

    def test_context_menu_actions_per_kind(self):
        entries = {entry.title: entry for entry in self.page._model.entries()}
        game_actions = [a.text() for a in self.page.build_context_menu(entries['Game 02']).actions() if a.text()]
        rom_actions = [a.text() for a in self.page.build_context_menu(entries['Mystery Hack']).actions() if a.text()]
        self.assertEqual(game_actions, ['Play', 'Change match…', 'Configure emulator', 'Remove from Library'])
        self.assertEqual(rom_actions, ['Play', 'Match to game…', 'Choose cover…', 'Configure emulator',
                                       'Remove from Library'])
        no_emulator = self.page.build_context_menu(entries['Game 12']).actions()[0]
        self.assertFalse(no_emulator.isEnabled())
        self.page.build_context_menu(entries['Mystery Hack']).actions()[-1].trigger()
        self.assertNotIn('Mystery Hack', self.titles())

    def test_change_match_and_return_to_the_automatic_match(self):
        with db.get_connection(self.database) as c:
            c.execute("INSERT INTO game_hashes(game_id, hash) VALUES(2, 'h2')")
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 02')
        self.assertEqual(entry.manual_roms, [])

        class PickGame05:
            def __init__(self, *_args, **_kwargs):
                pass

            def exec(self):
                return library_page.QDialog.DialogCode.Accepted

            def selected_game_id(self):
                return 5

        with patch.object(library_page, 'MatchRomDialog', PickGame05):
            menu = self.page.build_context_menu(entry)
            next(a for a in menu.actions() if a.text() == library_page.CHANGE_MATCH_TEXT).trigger()
        entries = {e.title: e for e in self.page._model.entries()}
        self.assertEqual([r.manual_match for r in entries['Game 05'].roms], [True, False])
        self.assertNotIn('Game 02', entries)
        texts = [a.text() for a in self.page.build_context_menu(entries['Game 05']).actions()]
        self.assertIn(library_page.AUTOMATIC_MATCH_TEXT, texts)

        self.hash_files_as_stems()
        self.automatic_match(entries['Game 05'])
        entries = {e.title: e for e in self.page._model.entries()}
        self.assertIn('Game 02', entries)
        self.assertEqual(entries['Game 02'].manual_roms, [])
        self.assertIn('Back to the automatic match: Game 02', self.page._scan_status_label.text())

    def test_automatic_match_rehashes_a_stale_stored_hash(self):
        # The case found in use: the stored hash predates the current hasher,
        # so matching it alone could not find the game until Verify hashes.
        with db.get_connection(self.database) as c:
            c.execute("INSERT INTO game_hashes(game_id, hash) VALUES(2, 'h2')")
            c.execute("UPDATE installed_roms SET game_id = 5, manual_match = 1, hash = 'stale-md5' WHERE game_id = 2")
        self.page.refresh()
        self.hash_files_as_stems()
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 05')
        self.automatic_match(entry)
        entries = {e.title: e for e in self.page._model.entries()}
        self.assertIn('Game 02', entries)
        self.assertEqual(entries['Game 02'].roms[0].hash, 'h2')

    def test_automatic_match_without_a_hash_hit_returns_to_unmatched(self):
        with db.get_connection(self.database) as c:
            c.execute("UPDATE installed_roms SET manual_match = 1 WHERE game_id = 4")
            # SNES hashes are known, so the miss means a real "no match".
            c.execute("INSERT INTO game_hashes(game_id, hash) VALUES(1, 'other')")
        self.page.refresh()
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 04')
        self.hash_files_as_stems()
        self.automatic_match(entry)
        titles = self.titles()
        self.assertNotIn('Game 04', titles)
        self.assertIn('4', titles)  # the file name, now an unmatched card
        self.assertIn('Unmatched', self.page._scan_status_label.text())

    def test_change_match_asks_which_copy_when_there_are_several(self):
        with db.get_connection(self.database) as c:
            extra = self.tmp / 'second copy.rom'
            extra.write_bytes(b'x')
            c.execute("INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id)"
                      " VALUES(2, ?, 'h2b', 3, 1)", (str(extra),))
        self.page.refresh()
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 02')
        with patch.object(library_page.QInputDialog, 'getItem', return_value=('second copy.rom', True)) as ask, \
             patch.object(library_page, 'MatchRomDialog') as dialog:
            dialog.return_value.exec.return_value = library_page.QDialog.DialogCode.Rejected
            self.page.match_entry(entry)
        self.assertEqual(ask.call_args.args[3], ['2.rom', 'second copy.rom'])
        self.assertEqual(dialog.call_args.args[0], str(self.tmp / 'second copy.rom'))

    def test_unmatched_filter_explains_why_and_what_to_do(self):
        self.assertTrue(self.page._hint_row.isHidden())
        self.page._set_status(STATUS_UNMATCHED)
        self.assertFalse(self.page._hint_row.isHidden())
        # No SNES hashes yet: the hint says so and offers to fetch them.
        self.assertIn('SNES', self.page._unmatched_hint.text())
        self.assertIn('not been fetched', self.page._unmatched_hint.text())
        self.assertFalse(self.page._fetch_hashes_button.isHidden())
        with db.get_connection(self.database) as c:
            c.execute("INSERT INTO game_hashes(game_id, hash) VALUES(1, 'other')")
        self.page._apply_filters()
        self.assertIn('Match to game', self.page._unmatched_hint.text())
        self.assertTrue(self.page._fetch_hashes_button.isHidden())
        rom = next(e for e in self.page._model.entries() if e.kind == 'rom')
        tooltip = self.page._model.index(0).data(Qt.ItemDataRole.ToolTipRole)
        self.assertIn('hash is not in the synced catalog', tooltip)
        self.assertEqual(rom.title, 'Mystery Hack')

    def hash_files_as_stems(self):
        """Hashing a test ROM file gives 'h<file stem>', like the seeded rows."""
        patcher = patch.object(
            library_page.library_service, '_hash_recorded_rom',
            side_effect=lambda path, _console: f'h{Path(path).stem}',
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def automatic_match(self, entry):
        self.page.use_automatic_match(entry)
        self.assertTrue(_wait(lambda: not self.page.app_context.workers.has_key(library_page.WORKER_AUTOMATIC_MATCH)
                              and self.page._scan_button.isEnabled()))

    def fake_hash_sync(self, calls):
        """Stands in for the API: stores a hash for the unmatched ROM."""
        from retrocheevos.services.sync_service import ConsoleHashSync

        def sync(_client, console_ids, progress_callback=None, should_cancel=None):
            calls.append(list(console_ids))
            with db.get_connection(self.database) as c:
                c.execute("INSERT INTO game_hashes(game_id, hash) VALUES(7, 'hx')")
            matched = library_page.library_service.rematch_unmatched_roms()
            if progress_callback:
                progress_callback(1, 1)
            return ConsoleHashSync(len(console_ids), 1, 1, matched)
        return sync

    def test_scan_fetches_missing_catalog_hashes_once_and_matches(self):
        from retrocheevos.models.library import RomFolderScanResult
        from retrocheevos.services import job_coordinator as jobs
        calls = []
        with patch.object(library_page.sync_service, 'sync_console_hashes', side_effect=self.fake_hash_sync(calls)):
            self.page._on_scan_done(RomFolderScanResult(1, [], 0, [], []))
            QTest.qWait(20)
            self.assertTrue(_wait(lambda: 'matched automatically' in self.page._scan_status_label.text()))
            self.assertEqual(calls, [[3]])
            self.assertNotIn('Mystery Hack', self.titles())
            self.assertIsNone(jobs.active_job())
            self.assertTrue(self.page._scan_button.isEnabled())
            # Nothing left to fetch: a second scan makes no request.
            self.page._on_scan_done(RomFolderScanResult(1, [], 0, [], []))
            QTest.qWait(50)
            self.assertEqual(calls, [[3]])

    def test_fetch_button_and_failure_message(self):
        self.page._set_status(STATUS_UNMATCHED)
        with patch.object(library_page.sync_service, 'sync_console_hashes', side_effect=RuntimeError('offline')):
            self.page._fetch_hashes_button.click()
            self.assertTrue(_wait(lambda: "Couldn't fetch" in self.page._scan_status_label.text()))
        self.assertTrue(self.page._fetch_hashes_button.isEnabled())
        self.assertTrue(self.page._scan_button.isEnabled())
        calls = []
        with patch.object(library_page.sync_service, 'sync_console_hashes', side_effect=self.fake_hash_sync(calls)):
            # The button retries even though this console was already tried.
            self.page._fetch_hashes_button.click()
            self.assertTrue(_wait(lambda: 'matched automatically' in self.page._scan_status_label.text()))
        self.assertEqual(calls, [[3]])

    def test_missing_file_offers_removal(self):
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 03')
        Path(entry.file_paths[0]).unlink()
        with patch.object(library_page.QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes) as ask, \
             patch.object(library_page, 'ServiceWorker') as worker:
            self.page.play_entry(entry)
        self.assertIn('File not found', ask.call_args.args[1])
        worker.assert_not_called()
        self.assertNotIn('Game 03', self.titles())

    def test_missing_emulator_leads_to_settings_on_that_console(self):
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 12')
        with patch.object(library_page.QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), \
             patch.object(library_page, 'ServiceWorker') as worker:
            self.page.play_entry(entry)
        worker.assert_not_called()
        self.assertEqual(self.window.current_destination(), 'settings')
        settings = self.window.destination('settings')
        self.assertEqual(settings._emulator_console_selector.currentData(), 12)

    def test_play_launches_through_the_existing_service(self):
        entry = next(e for e in self.page._model.entries() if e.title == 'Game 02')
        with patch.object(library_page, 'ServiceWorker') as worker:
            self.page.play_entry(entry)
        worker.assert_called_once()
        self.assertEqual(worker.call_args.args[1], 2)

    def test_scan_cancel_requests_cancellation(self):
        self.page._begin_job()
        with patch.object(self.page.app_context.workers, 'cancel_key') as cancel:
            self.page._cancel_button.click()
        cancel.assert_any_call(library_page.WORKER_SCAN)
        self.page._on_job_cancelled()
        self.assertTrue(self.page._cancel_button.isHidden())
        self.assertTrue(self.page._scan_button.isEnabled())

    def test_scan_result_details_list_skipped_paths(self):
        from retrocheevos.models.library import RomFolderScanResult
        result = RomFolderScanResult(1, [], 2, ['/roms/odd.bin'], ['/roms/readme.txt'])
        self.page._on_scan_done(result)
        self.assertIn('1 ambiguous', self.page._scan_status_label.text())
        self.assertFalse(self.page._details_button.isHidden())
        self.assertIn('/roms/odd.bin', self.page._last_result_details)
        self.assertIn('/roms/readme.txt', self.page._last_result_details)


class FolderEditorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        database = self.tmp / 'folders.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(database))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(database).close()
        with db.get_connection(database) as c:
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
        self.editor = RomFolderEditor()
        self.addCleanup(self.editor.deleteLater)

    def test_add_remove_and_scan_requests(self):
        self.assertFalse(self.editor._hint.isHidden())
        self.assertFalse(self.editor._scan_button.isEnabled())
        with patch.object(rom_folder_editor.QFileDialog, 'getExistingDirectory', return_value=str(self.tmp)):
            self.editor._on_add()
        self.assertEqual(self.editor.folder_list.count(), 1)
        self.assertTrue(self.editor._hint.isHidden())
        self.editor.folder_list.setCurrentRow(0)
        scans = []
        self.editor.scan_requested.connect(scans.append)
        self.editor._scan_button.click()
        self.assertEqual(len(scans), 1)
        files = []
        self.editor.scan_file_requested.connect(lambda console, path: files.append((console, path)))
        with patch.object(rom_folder_editor.QFileDialog, 'getOpenFileName', return_value=('/roms/a.sfc', '')):
            self.editor._on_scan_file()
        self.assertEqual(files[0][1], '/roms/a.sfc')
        self.editor._remove_button.click()
        self.assertEqual(self.editor.folder_list.count(), 0)


if __name__ == '__main__':
    unittest.main()
