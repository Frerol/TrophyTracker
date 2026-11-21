"""Library grid data (R22): entries, progress, mastery, emulators and filters."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as db
from retrocheevos.core.library_filter import (
    STATUS_ALL, STATUS_IN_PROGRESS, STATUS_MASTERED, STATUS_UNMATCHED, filter_entries,
)
from retrocheevos.database.migrations import initialize_database
from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom, LibraryEntry
from retrocheevos.services import library_service, lists_service, session_service


class LibraryEntriesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.path = self.tmp / 'library.db'
        create = db.create_connection
        patcher = patch.object(db, 'create_connection', lambda database_path=None: create(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()
        with db.get_connection(self.path) as c:
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(1, 'alice', '', 1)")
            c.execute("INSERT INTO accounts(id, username, api_key, is_active) VALUES(2, 'bob', '', 0)")
            c.execute("INSERT INTO consoles(id, name) VALUES(3, 'SNES')")
            c.execute("INSERT INTO consoles(id, name) VALUES(12, 'PlayStation')")
            c.execute("INSERT INTO emulator_configs(console_id, executable_path) VALUES(3, '/usr/bin/true')")
            games = [(1, 'Zelda', 3), (2, 'Axelay', 3), (3, 'Castlevania', 12), (4, 'Blocked', 3)]
            for game_id, title, console in games:
                c.execute("INSERT INTO games(id, title, console_id, has_achievements) VALUES(?, ?, ?, 1)",
                          (game_id, title, console))
            self.rom(c, 1, 1, 'zelda-a.sfc', played='2026-11-20T10:00:00')
            self.rom(c, 1, 1, 'zelda-b.sfc', played='2026-11-21T10:00:00')
            self.rom(c, 1, 2, 'axelay.sfc')
            self.rom(c, 1, 3, 'sotn.cue')
            self.rom(c, 1, 4, 'blocked.sfc')
            self.rom(c, 1, None, 'Mystery Hack (USA).sfc')
            self.rom(c, 2, 2, 'bob-axelay.sfc')
            c.execute("INSERT INTO game_completion(account_id, game_id, percent_complete, achievements_unlocked,"
                      " achievements_total, highest_award_kind) VALUES(1, 1, 100, 30, 30, 'mastered')")
            c.execute("INSERT INTO game_completion(account_id, game_id, percent_complete) VALUES(1, 2, 25)")

        blocked = next(d for d in lists_service.ensure_predefined_lists(1) if d.is_blocked)
        lists_service.add_to_list(1, 4, blocked.id)

    def rom(self, connection, account, game_id, name, played=None):
        path = self.tmp / name
        path.write_bytes(b'x')
        connection.execute(
            "INSERT INTO installed_roms(game_id, file_path, hash, console_id, account_id, last_played_at)"
            " VALUES(?, ?, ?, ?, ?, ?)",
            (game_id, str(path), name, 12 if name == 'sotn.cue' else 3, account, played),
        )

    def test_entries_are_account_scoped_with_progress_and_emulator_flags(self):
        entries = library_service.list_library_entries()
        self.assertEqual([e.title for e in entries], ['Axelay', 'Castlevania', 'Zelda', 'Mystery Hack'])
        by_title = {entry.title: entry for entry in entries}
        zelda = by_title['Zelda']
        self.assertEqual((zelda.achievements_unlocked, zelda.achievements_total), (30, 30))
        self.assertTrue(zelda.mastered)
        self.assertEqual(len(zelda.file_paths), 2)
        self.assertEqual(zelda.last_played_at, datetime(2026, 11, 21, 10))
        self.assertEqual(by_title['Axelay'].percent_complete, 25)
        self.assertIsNone(by_title['Axelay'].achievements_unlocked)
        self.assertIsNone(by_title['Castlevania'].percent_complete)
        self.assertFalse(by_title['Castlevania'].has_emulator)
        self.assertTrue(by_title['Axelay'].has_emulator)
        mystery = by_title['Mystery Hack']
        self.assertEqual(mystery.kind, 'rom')
        self.assertEqual(mystery.key, ('rom', mystery.rom.id))
        session_service.logout()
        self.assertEqual(library_service.list_library_entries(), [])


def entry(title, kind='game', console=3, unlocked=None, total=None, percent=None, mastered=False, path=None):
    game = Game(len(title), title, console, True) if kind == 'game' else None
    rom = InstalledRom(path or f'/roms/{title}.sfc', '', console, id=len(title)) if kind == 'rom' else None
    return LibraryEntry(kind, title, console, [path or f'/roms/{title}.sfc'], game=game, rom=rom,
                        achievements_unlocked=unlocked, achievements_total=total,
                        percent_complete=percent, mastered=mastered)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            entry('Started', unlocked=3, total=10, percent=30),
            entry('Percent only', percent=40),
            entry('Untouched'),
            entry('Zero', unlocked=0, total=10, percent=0),
            entry('Done', unlocked=10, total=10, percent=100, mastered=True),
            entry('Hack', kind='rom', path='C:\\roms\\Strange Hack (USA).sfc'),
            entry('Other system', console=12, percent=50),
        ]

    def titles(self, **kwargs):
        return [e.title for e in filter_entries(self.entries, **kwargs)]

    def test_statuses_never_treat_unknown_as_progress(self):
        self.assertEqual(len(self.titles(status=STATUS_ALL)), 7)
        self.assertEqual(self.titles(status=STATUS_IN_PROGRESS), ['Started', 'Percent only', 'Other system'])
        self.assertEqual(self.titles(status=STATUS_MASTERED), ['Done'])
        self.assertEqual(self.titles(status=STATUS_UNMATCHED), ['Hack'])

    def test_system_and_text_filters(self):
        self.assertEqual(self.titles(console_id=12), ['Other system'])
        self.assertEqual(self.titles(text='  STARTED '), ['Started'])
        # File names match too, with Windows separators.
        self.assertEqual(self.titles(text='strange hack'), ['Hack'])
        self.assertEqual(self.titles(text='roms'), [])
        self.assertEqual(self.titles(status=STATUS_IN_PROGRESS, console_id=3, text='per'), ['Percent only'])


if __name__ == '__main__':
    unittest.main()
