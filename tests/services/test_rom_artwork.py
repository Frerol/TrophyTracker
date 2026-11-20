"""ROM cover art must work without an achievement/catalog match."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from retrocheevos.library import rom_artwork as art
from retrocheevos.models.library import InstalledRom
from retrocheevos.services import image_service


def png_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new('RGB', (32, 48), 'blue').save(stream, 'PNG')
    return stream.getvalue()


def disc_header(disc_id: str, disc_type: int = 2) -> bytes:
    header = bytearray(art.DISC_HEADER_OFFSET + art.DISC_ID_SIZE)
    header[:4] = b'RVZ\x01'
    header[0x48:0x4C] = disc_type.to_bytes(4, 'big')
    header[art.DISC_HEADER_OFFSET:] = disc_id.encode('ascii')
    return bytes(header)


class RomArtworkTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rom = self.root / 'Super Mario Galaxy (USA).rvz'
        self.rom.write_bytes(disc_header('RMGE01'))
        self.image = png_bytes()
        for patcher in (
            patch.object(art, 'ROM_ART_CACHE', self.root / 'cache'),
            patch.object(art, '_dolphin_cached_cover', return_value=None),
            patch.dict(art._RETRY_AFTER, {}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.status_code = 200
        self.response.iter_content.return_value = [self.image]

    def test_rvz_id_is_read_without_decompressing_or_using_filename(self) -> None:
        self.assertEqual(art.disc_id_for_rom(self.rom, 19), 'RMGE01')
        self.assertIsNone(art.disc_id_for_rom(self.rom, 16))
        self.rom.write_bytes(disc_header('../bad'))
        self.assertIsNone(art.disc_id_for_rom(self.rom, 19))
        self.rom.write_bytes(b'invalid')
        self.assertIsNone(art.disc_id_for_rom(self.rom, 19))

    def test_gametdb_cover_is_downloaded_once_and_cached_by_disc_id(self) -> None:
        with patch.object(art.requests, 'get', return_value=self.response) as get:
            result = art.ensure_disc_cover_cached(self.rom, 19)
            self.assertTrue(art.is_readable_image(result))
            self.assertEqual(art.ensure_disc_cover_cached(self.rom, 19), result)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], 'https://art.gametdb.com/wii/cover/US/RMGE01.png')

    def test_european_disc_uses_english_cover(self) -> None:
        self.rom.write_bytes(disc_header('SOUP01'))
        with patch.object(art.requests, 'get', return_value=self.response) as get:
            self.assertIsNotNone(art.ensure_disc_cover_cached(self.rom, 19))
        self.assertIn('/EN/SOUP01.png', get.call_args.args[0])

    def test_missing_art_is_cached_instead_of_requested_on_every_refresh(self) -> None:
        self.response.status_code = 404
        with patch.object(art.requests, 'get', return_value=self.response) as get:
            self.assertIsNone(art.ensure_disc_cover_cached(self.rom, 19))
            calls = get.call_count
            self.assertGreater(calls, 0)
            self.assertIsNone(art.ensure_disc_cover_cached(self.rom, 19))
            self.assertEqual(get.call_count, calls)

    def test_corrupt_cached_cover_is_replaced(self) -> None:
        destination = art.ROM_ART_CACHE / 'RMGE01.png'
        destination.parent.mkdir()
        destination.write_bytes(b'not an image')
        with patch.object(art.requests, 'get', return_value=self.response):
            self.assertEqual(art.ensure_disc_cover_cached(self.rom, 19), destination)
        self.assertTrue(art.is_readable_image(destination))

    def test_invalid_image_response_is_not_cached_and_is_throttled(self) -> None:
        self.response.iter_content.return_value = [b'<html>not a cover</html>']
        with patch.object(art.requests, 'get', return_value=self.response) as get:
            self.assertIsNone(art.ensure_disc_cover_cached(self.rom, 19))
            self.assertIsNone(art.ensure_disc_cover_cached(self.rom, 19))
            self.assertEqual(get.call_count, 1)
        self.assertEqual(list(art.ROM_ART_CACHE.iterdir()), [])

    def test_local_sidecar_and_manual_images_take_priority(self) -> None:
        sidecar = self.root / 'images' / (self.rom.stem + '-image.png')
        sidecar.parent.mkdir()
        sidecar.write_bytes(self.image)
        manual = self.root / 'manual.png'
        rom = InstalledRom(str(self.rom), '', 19, id=1)
        with patch.object(image_service, 'cached_local_cover_path', return_value=manual), patch.object(image_service, 'ensure_disc_cover_cached') as fetch:
            self.assertEqual(image_service.ensure_rom_image_cached(rom), sidecar)
            manual.write_bytes(self.image)
            self.assertEqual(image_service.ensure_rom_image_cached(rom), manual)
            fetch.assert_not_called()

    def test_ra_corrupt_cache_is_retried(self) -> None:
        from retrocheevos.models.game import Game
        destination = self.root / 'ra.png'
        destination.write_bytes(b'')
        def download(_url, path):
            path.write_bytes(self.image)
        with patch.object(image_service, 'cached_image_path', return_value=destination), patch.object(image_service, 'download_image', side_effect=download) as fetch:
            self.assertEqual(image_service.ensure_game_image_cached(Game(1, 'Game', 19, True, image_path='/Images/test.png')), destination)
            fetch.assert_called_once()
