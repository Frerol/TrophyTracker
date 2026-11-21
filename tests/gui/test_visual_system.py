"""R17 visual system: bundled fonts, token contrast, components and preview."""

import importlib.util
import unittest
from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from retrocheevos.gui import components as c
from retrocheevos.gui import styles
from retrocheevos.gui.assets import FONT_FILES, assets_dir, fonts_dir, load_bundled_fonts

_app = QApplication.instance() or QApplication([])

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / 'tools' / 'preview' / 'component_preview.py'

TEXT_TOKENS = ('TEXT_PRIMARY', 'TEXT_SECONDARY', 'ACCENT_GOLD', 'ACCENT_TURQUOISE', 'STATUS_DANGER')
TEXT_SURFACES = ('SURFACE_APP', 'SURFACE_SIDEBAR', 'SURFACE_PANEL', 'SURFACE_RAISED', 'SURFACE_INPUT')


class BundledFontTests(unittest.TestCase):
    def test_font_files_and_licenses_are_present(self) -> None:
        for name in FONT_FILES + ('Inter-OFL.txt', 'SpaceGrotesk-OFL.txt'):
            self.assertTrue((fonts_dir() / name).is_file(), name)

    def test_inter_and_space_grotesk_register_with_qt(self) -> None:
        families = load_bundled_fonts()
        self.assertIn(styles.FONT_UI, families)
        self.assertIn(styles.FONT_DISPLAY, families)


class TokenContrastTests(unittest.TestCase):
    def test_text_tokens_meet_normal_text_contrast_on_every_surface(self) -> None:
        for text in TEXT_TOKENS:
            for surface in TEXT_SURFACES:
                ratio = styles.contrast_ratio(getattr(styles, text), getattr(styles, surface))
                with self.subTest(text=text, surface=surface):
                    self.assertGreaterEqual(ratio, 4.5)

    def test_text_on_gold_meets_normal_text_contrast(self) -> None:
        for gold in ('ACCENT_GOLD', 'ACCENT_GOLD_HOVER', 'ACCENT_GOLD_PRESSED'):
            with self.subTest(gold=gold):
                self.assertGreaterEqual(
                    styles.contrast_ratio(styles.TEXT_ON_ACCENT, getattr(styles, gold)), 4.5)

    def test_control_outline_meets_boundary_contrast(self) -> None:
        for surface in ('SURFACE_APP', 'SURFACE_PANEL', 'SURFACE_INPUT'):
            with self.subTest(surface=surface):
                self.assertGreaterEqual(
                    styles.contrast_ratio(styles.OUTLINE_CONTROL, getattr(styles, surface)), 3.0)

    def test_progress_fill_is_distinguishable_from_its_track(self) -> None:
        for fill in (styles.PROGRESS_HARDCORE, styles.PROGRESS_SOFTCORE):
            self.assertGreaterEqual(styles.contrast_ratio(fill, styles.PROGRESS_TRACK), 3.0)

    def test_legacy_aliases_point_at_tokens(self) -> None:
        self.assertEqual(styles.BG, styles.SURFACE_APP)
        self.assertEqual(styles.LINK, styles.ACCENT_TURQUOISE)
        self.assertEqual(styles.TEXT_DIM, styles.TEXT_SECONDARY)


class ComponentStateTests(unittest.TestCase):
    def test_unknown_progress_is_not_zero(self) -> None:
        unknown = c.ModeProgress(c.MODE_HARDCORE)
        zero = c.ModeProgress(c.MODE_HARDCORE)
        zero.set_progress(0, 24)
        self.assertEqual(unknown.label_text(), 'Hardcore · Progress unavailable')
        self.assertFalse(unknown.bar_visible())
        self.assertEqual(zero.label_text(), 'Hardcore · 0/24 achievements')
        self.assertTrue(zero.bar_visible())

    def test_progress_labels_its_mode(self) -> None:
        softcore = c.ModeProgress(c.MODE_SOFTCORE)
        softcore.set_progress(21, 58)
        self.assertEqual(softcore.label_text(), 'Softcore · 21/58 achievements')
        self.assertEqual(softcore.accessibleName(), 'Softcore · 21/58 achievements')

    def test_metric_card_unknown_and_known_values(self) -> None:
        card = c.MetricCard('Points', 'Selected account')
        self.assertEqual(card.value_text(), c.UNKNOWN_VALUE)
        self.assertEqual(card.accessibleName(), 'Points: unavailable')
        card.set_value(12480)
        self.assertEqual(card.value_text(), '12,480')

    def test_game_card_explains_unavailable_play(self) -> None:
        card = c.GameCard('Chrono Trigger', 'Super Nintendo')
        self.assertTrue(card.play_enabled())
        card.set_play_unavailable('Configure an emulator')
        self.assertFalse(card.play_enabled())
        card.set_play_unavailable(None)
        self.assertTrue(card.play_enabled())

    def test_achievement_state_is_carried_by_text(self) -> None:
        row = c.AchievementRow('No Pause', 'Finish fast', 50)
        self.assertEqual(row.pill.text(), 'Locked')
        row.set_state(c.STATE_HARDCORE)
        self.assertEqual(row.pill.text(), 'Unlocked · Hardcore')
        self.assertEqual(row.pill.property('pill'), 'hardcore')
        self.assertEqual(row.accessibleName(), 'No Pause: Unlocked · Hardcore')


class BrandAssetTests(unittest.TestCase):
    """Decision D1: pixel-trophy icon A at every size, crisp at 16/24 px."""

    def test_every_icon_size_exists_with_exact_dimensions(self) -> None:
        for size in (16, 24, 32, 48, 64, 128, 256):
            image = QImage(str(assets_dir() / 'icons' / f'trophytracker-{size}.png'))
            with self.subTest(size=size):
                self.assertFalse(image.isNull())
                self.assertEqual((image.width(), image.height()), (size, size))
        self.assertEqual(QImage(str(assets_dir() / 'icon.png')).width(), 512)
        self.assertEqual(QImage(str(assets_dir() / 'logo.png')).width(), 128)

    def test_small_icons_use_whole_pixels_for_the_trophy(self) -> None:
        # Same placement as tools/brand/generate_icons.py: the 10x9-unit
        # trophy (starting at grid unit 1) is centred at an integer scale.
        for size, scale in ((16, 1), (24, 2)):
            origin_x = (size - 10 * scale) // 2 - scale
            origin_y = (size - 9 * scale) // 2 - scale
            image = QImage(str(assets_dir() / 'icons' / f'trophytracker-{size}.png'))

            def unit(x: int, y: int) -> str:
                return image.pixelColor(origin_x + x * scale, origin_y + y * scale).name()

            with self.subTest(size=size):
                self.assertEqual(unit(4, 3), QColor(styles.ACCENT_GOLD).name())   # cup
                self.assertEqual(unit(5, 2), QColor(styles.SURFACE_APP).name())   # opening
                self.assertEqual(unit(5, 7), QColor(styles.ACCENT_GOLD).name())   # stem

    def test_icons_have_a_transparent_background_and_a_dark_outline(self) -> None:
        for size in (16, 24, 32, 48, 64, 128, 256):
            image = QImage(str(assets_dir() / 'icons' / f'trophytracker-{size}.png'))
            with self.subTest(size=size):
                for x, y in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
                    self.assertEqual(image.pixelColor(x, y).alpha(), 0)
                # Walk in from the left edge along the stem's row: the first
                # opaque pixel must be the outline, never gold.
                row = size // 2
                first = next(image.pixelColor(x, row) for x in range(size)
                             if image.pixelColor(x, row).alpha() > 0)
                self.assertEqual(first.name(), QColor(styles.SURFACE_APP).name())

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location('component_preview', PREVIEW)
        cls.preview = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.preview)

    def test_component_preview_renders(self) -> None:
        content = self.preview.build_preview()
        content.setFixedWidth(self.preview.PREVIEW_WIDTH)
        content.adjustSize()
        image = content.grab()
        self.assertFalse(image.isNull())
        self.assertGreater(image.height(), 1000)
        content.deleteLater()

    def test_brand_sheet_renders_every_concept(self) -> None:
        for _name, file_name in self.preview.BRAND_CONCEPTS:
            self.assertTrue((self.preview.BRAND_DIR / file_name).is_file(), file_name)
        self.assertFalse(self.preview.build_brand_sheet().isNull())


if __name__ == '__main__':
    unittest.main()
