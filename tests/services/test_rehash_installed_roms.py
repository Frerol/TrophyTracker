"""Re-hashing ROMs that are already recorded.

The gap this closes: `scan_rom_folder` skips files already in
`installed_roms` — deliberately, because hashing is the expensive part — so a
ROM keeps whatever hash the app computed the day it was first scanned. Every
later improvement to the hashing (RAHasher, the PSP and CISO readers) had no
effect at all on an existing library, and there was no way to apply one short
of removing and re-adding every folder.

Three real ROMs were provably stale when this was written: two NES files
whose iNES header the old whole-file MD5 never stripped, and a Dreamcast
`.gdi` where it hashed the text index instead of the disc.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import retrocheevos.database.connection as connection_module
from retrocheevos.database.repositories.console_repository import ConsoleRepository
from retrocheevos.database.repositories.game_repository import GameRepository
from retrocheevos.database.repositories.library_repository import LibraryRepository
from retrocheevos.models.console import Console
from retrocheevos.models.game import Game
from retrocheevos.models.library import InstalledRom
from retrocheevos.services import library_service
from retrocheevos.utils.enums import GameType

CONSOLE_ID = 7
OLD_HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
NEW_HASH = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
OTHER_HASH = "cccccccccccccccccccccccccccccccc"


class RehashInstalledRomsTests(unittest.TestCase):
    def setUp(self) -> None:
        from retrocheevos.database.migrations import initialize_database

        self.tmpdir = Path(tempfile.mkdtemp())
        self.path = self.tmpdir / "library.db"
        real_create = connection_module.create_connection
        patcher = patch.object(
            connection_module,
            "create_connection",
            lambda database_path=None: real_create(self.path),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        initialize_database(self.path).close()

        with connection_module.get_connection() as conn:
            ConsoleRepository(conn).upsert(Console(id=CONSOLE_ID, name="NES/Famicom"))

    def _add_game(self, game_id: int, title: str, hashes: list[str]) -> None:
        with connection_module.get_connection() as conn:
            GameRepository(conn).upsert_game(
                Game(
                    id=game_id, title=title, console_id=CONSOLE_ID,
                    has_achievements=True, image_path="/x.png",
                    game_type=GameType.RETAIL, retroachievements_url="https://x",
                )
            )
        with connection_module.get_connection() as conn:
            GameRepository(conn).replace_hashes(game_id, hashes)

    def _add_rom(self, name: str, rom_hash: str, game_id=None, create_file=True) -> int:
        path = self.tmpdir / name
        if create_file:
            path.write_bytes(b"rom bytes")
        with connection_module.get_connection() as conn:
            rom = LibraryRepository(conn).add_installed_rom(
                InstalledRom(
                    file_path=str(path), hash=rom_hash,
                    console_id=CONSOLE_ID, game_id=game_id,
                )
            )
        return rom.id

    def _rom(self, rom_id: int) -> InstalledRom:
        with connection_module.get_connection() as conn:
            rom = LibraryRepository(conn).get_by_id(rom_id)
        assert rom is not None
        return rom

    def test_stale_hash_is_replaced_and_the_rom_matches(self) -> None:
        """The whole point: a hash written by an older hasher gets corrected,
        and the correction is what finds the game.
        """
        self._add_game(1, "Some Game", [NEW_HASH])
        rom_id = self._add_rom("game.nes", OLD_HASH)

        with patch.object(library_service, "compute_rom_hash", return_value=NEW_HASH):
            result = library_service.rehash_installed_roms()

        self.assertEqual(result.changed, 1)
        self.assertEqual(result.newly_matched, 1)
        self.assertEqual(self._rom(rom_id).hash, NEW_HASH)
        self.assertEqual(self._rom(rom_id).game_id, 1)

    def test_unchanged_hash_is_not_rewritten(self) -> None:
        self._add_rom("game.nes", OLD_HASH)

        with patch.object(library_service, "compute_rom_hash", return_value=OLD_HASH):
            result = library_service.rehash_installed_roms()

        self.assertEqual(result.checked, 1)
        self.assertEqual(result.changed, 0)
        self.assertEqual(result.newly_matched, 0)

    def test_second_run_is_a_no_op(self) -> None:
        self._add_game(1, "Some Game", [NEW_HASH])
        self._add_rom("game.nes", OLD_HASH)

        with patch.object(library_service, "compute_rom_hash", return_value=NEW_HASH):
            first = library_service.rehash_installed_roms()
            second = library_service.rehash_installed_roms()

        self.assertEqual(first.changed, 1)
        self.assertEqual(second.changed, 0)
        self.assertEqual(second.newly_matched, 0)

    def test_unmatched_rom_with_a_correct_hash_still_gets_rematched(self) -> None:
        """Covers the ordinary case after the hash backfill finally reaches a
        console: the hash was right all along, only the catalog was empty.
        """
        rom_id = self._add_rom("game.nes", OLD_HASH)
        self._add_game(1, "Some Game", [OLD_HASH])

        with patch.object(library_service, "compute_rom_hash", return_value=OLD_HASH):
            result = library_service.rehash_installed_roms()

        self.assertEqual(result.changed, 0)
        self.assertEqual(result.newly_matched, 1)
        self.assertEqual(self._rom(rom_id).game_id, 1)

    def test_an_existing_match_is_never_cleared(self) -> None:
        """A manual "Match to Game…" must survive a re-hash that finds
        nothing — the user's own answer beats an empty lookup.
        """
        self._add_game(1, "Hand Picked", [OTHER_HASH])
        rom_id = self._add_rom("game.nes", OLD_HASH, game_id=1)

        with patch.object(library_service, "compute_rom_hash", return_value=NEW_HASH):
            library_service.rehash_installed_roms()

        self.assertEqual(self._rom(rom_id).hash, NEW_HASH)
        self.assertEqual(self._rom(rom_id).game_id, 1)

    def test_a_changed_hash_can_correct_a_wrong_match(self) -> None:
        self._add_game(1, "Wrong Game", [OLD_HASH])
        self._add_game(2, "Right Game", [NEW_HASH])
        rom_id = self._add_rom("game.nes", OLD_HASH, game_id=1)

        with patch.object(library_service, "compute_rom_hash", return_value=NEW_HASH):
            result = library_service.rehash_installed_roms()

        self.assertEqual(result.newly_matched, 1)
        self.assertEqual(self._rom(rom_id).game_id, 2)

    def test_missing_file_is_reported_and_left_alone(self) -> None:
        rom_id = self._add_rom("gone.nes", OLD_HASH, create_file=False)

        with patch.object(library_service, "compute_rom_hash", return_value=NEW_HASH):
            result = library_service.rehash_installed_roms()

        self.assertEqual(len(result.missing), 1)
        self.assertEqual(result.changed, 0)
        self.assertEqual(self._rom(rom_id).hash, OLD_HASH)

    def test_one_unhashable_rom_does_not_end_the_pass(self) -> None:
        self._add_rom("bad.nes", OLD_HASH)
        good_id = self._add_rom("good.nes", OLD_HASH)

        def flaky(path, console_id=None):
            if Path(path).name == "bad.nes":
                raise OSError("unreadable")
            return NEW_HASH

        with patch.object(library_service, "compute_rom_hash", side_effect=flaky):
            result = library_service.rehash_installed_roms()

        self.assertEqual(len(result.failed), 1)
        self.assertEqual(result.changed, 1)
        self.assertEqual(self._rom(good_id).hash, NEW_HASH)

    def test_progress_is_reported_for_every_rom(self) -> None:
        for index in range(3):
            self._add_rom(f"game{index}.nes", OLD_HASH)

        seen = []
        with patch.object(library_service, "compute_rom_hash", return_value=OLD_HASH):
            library_service.rehash_installed_roms(
                progress_callback=lambda done, total, path: seen.append((done, total))
            )

        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])

    def test_console_id_is_passed_to_the_hasher(self) -> None:
        """Without it `compute_rom_hash` skips RAHasher entirely and falls
        back to a whole-file MD5 — the exact bug being fixed.
        """
        self._add_rom("game.nes", OLD_HASH)

        with patch.object(
            library_service, "compute_rom_hash", return_value=OLD_HASH
        ) as hasher:
            library_service.rehash_installed_roms()

        self.assertEqual(hasher.call_args.args[1], CONSOLE_ID)


if __name__ == "__main__":
    unittest.main()
