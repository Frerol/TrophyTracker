"""Cover lookup is based on platform and title, including newly added systems."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from PIL import Image

from retrocheevos.library import thumbnail_catalog as catalog
from retrocheevos.models.library import InstalledRom
from retrocheevos.services import image_service


def response(content: bytes):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = 200
    result.iter_content.return_value = [content]
    return result


def listing(names: list[str], directories: bool = False) -> bytes:
    return ''.join(f'<a href="{quote(name, safe="")}{"/" if directories else ""}">entry</a>' for name in names).encode()


class ThumbnailCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for patcher in (
            patch.object(catalog, 'INDEX_CACHE', self.root / 'indexes'),
            patch.object(catalog, 'COVER_CACHE', self.root / 'covers'),
            patch.dict(catalog._RETRY_AFTER, {}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        data = io.BytesIO()
        Image.new('RGB', (40, 60), 'green').save(data, 'PNG')
        self.png = data.getvalue()

    def test_multiple_consoles_and_future_platforms_use_the_discovered_catalog(self) -> None:
        platforms = {
            'Nintendo - Nintendo Entertainment System': 'Super Mario Bros. (World).png',
            'Sony - PlayStation 2': 'Final Fantasy X (USA).png',
            'Nintendo - Game Boy Advance': 'Metroid Fusion (USA).png',
            'Acme - GameStation': 'Future Game (World).png',
        }
        descriptors = [
            {'name': name.replace(' ', '_'), 'default_branch': 'master'}
            for name in platforms
        ]
        def get(url, **_kwargs):
            if url == catalog.API_URL + '/orgs/libretro-thumbnails/repos?per_page=100&page=1':
                return response(json.dumps(descriptors).encode())
            for platform, filename in platforms.items():
                repo = platform.replace(' ', '_')
                prefix = catalog.API_URL + '/repos/libretro-thumbnails/' + repo + '/git/trees/'
                if url == prefix + 'master':
                    return response(json.dumps({'tree': [{'path': 'Named_Boxarts', 'type': 'tree', 'sha': 'boxarts'}]}).encode())
                if url == prefix + 'boxarts':
                    return response(json.dumps({'tree': [{'path': filename, 'type': 'blob'}]}).encode())
                image_url = catalog.RAW_URL + repo + '/master/Named_Boxarts/' + quote(filename, safe='')
                if url == image_url:
                    return response(self.png)
            raise AssertionError(f'Unexpected URL: {url}')
        cases = (
            ('Super Mario Bros.', 7, 'Nintendo Entertainment System'),
            ('Final Fantasy X', 21, 'PlayStation 2'),
            ('Metroid Fusion', 5, 'Game Boy Advance'),
            ('Future Game', 999, 'GameStation'),
        )
        with patch.object(catalog.requests, 'get', side_effect=get) as fetch:
            for title, console_id, console_name in cases:
                with self.subTest(console=console_name):
                    cover = catalog.ensure_named_cover_cached(title, console_id, console_name)
                    self.assertTrue(cover.is_file())
                    self.assertEqual(cover.read_bytes(), self.png)
                    calls = fetch.call_count
                    self.assertEqual(catalog.ensure_named_cover_cached(title, console_id, console_name), cover)
                    self.assertEqual(fetch.call_count, calls)

    def test_similar_console_names_do_not_cross_platforms(self) -> None:
        platforms = ['Nintendo - Nintendo 3DS', 'Nintendo - Game Boy Color', 'Sony - PlayStation 2', 'Nintendo - Wii U']
        for console_id, name in ((18, 'Nintendo DS'), (4, 'Game Boy'), (12, 'PlayStation'), (19, 'Wii')):
            self.assertEqual(catalog.select_platforms(console_id, name, platforms), [])

    def test_platform_aliases_handle_combined_regional_system_names(self) -> None:
        platforms = ['Sega - Master System - Mark III', 'Sega - Mega-CD - Sega CD']
        self.assertEqual(catalog.select_platforms(11, 'Master System', platforms), [platforms[0]])
        self.assertEqual(catalog.select_platforms(9, 'Sega CD', platforms), [platforms[1]])

    def test_name_matching_handles_tags_accents_and_articles(self) -> None:
        self.assertEqual(catalog.select_cover('Pokemon Emerald', ['Pokémon Emerald (USA).png']), 'Pokémon Emerald (USA).png')
        self.assertEqual(catalog.select_cover('The Legend of Zelda', ['Legend of Zelda, The (USA).png']), 'Legend of Zelda, The (USA).png')
        self.assertEqual(catalog.select_cover('Super Mario Bros. (Europe)', ['Super Mario Bros. (USA).png', 'Super Mario Bros. (Europe).png']), 'Super Mario Bros. (Europe).png')

    def test_numbered_and_roman_numeral_sequels_are_not_substituted(self) -> None:
        self.assertIsNone(catalog.select_cover('Super Mario Galaxy 2', ['Super Mario Galaxy (USA).png']))
        self.assertIsNone(catalog.select_cover('Final Fantasy VIII', ['Final Fantasy VII (USA).png']))
        self.assertIsNone(catalog.select_cover('Unrelated Game', ['Super Mario Bros. (World).png']))

    def test_non_latin_titles_remain_distinct(self) -> None:
        files = ['スーパーマリオ (Japan).png', 'ゼルダの伝説 (Japan).png']
        self.assertEqual(catalog.select_cover('ゼルダの伝説', files), files[1])
        self.assertIsNone(catalog.select_cover('無関係なゲーム', files))

    def test_unmatched_non_nintendo_rom_uses_name_lookup(self) -> None:
        cover = self.root / 'cover.png'
        cover.write_bytes(self.png)
        rom = InstalledRom('/roms/Crash Bandicoot (USA).bin', '', 12, id=1)
        with patch.object(image_service, 'cached_local_cover_path', return_value=self.root / 'missing.png'), patch.object(image_service, 'find_local_artwork', return_value=None), patch.object(image_service, 'ensure_disc_cover_cached', return_value=None), patch.object(image_service, 'ensure_named_cover_cached', return_value=cover) as find:
            self.assertEqual(image_service.ensure_rom_image_cached(rom), cover)
        find.assert_called_once_with('Crash Bandicoot', 12, 'PlayStation')

    def test_stale_index_remains_usable_when_offline(self) -> None:
        cache = catalog.INDEX_CACHE / 'platforms.json'
        cache.parent.mkdir()
        cache.write_text('["Sony - PlayStation"]')
        import os
        os.utime(cache, (0, 0))
        with patch.object(catalog.requests, 'get', side_effect=OSError('offline')):
            self.assertEqual(catalog._cached_json('platforms', lambda: catalog._api_get(catalog.API_URL)), ['Sony - PlayStation'])
