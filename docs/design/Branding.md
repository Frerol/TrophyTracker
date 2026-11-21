# TrophyTracker visual identity

This document describes the visual system and the current runtime artwork. The
planned replacement artwork is defined by the
[reviewed UI proposal](ui-proposal-reviewed.html) and the
[desktop revamp roadmap](../planning/DevelopmentRoadmap.md#active-desktop-plan--interface-revamp-r16r27).
The preferred A/C concepts have not yet replaced the shipped icon/logo
(decision D1).

## Visual system (R17)

The application theme follows the reviewed proposal: dark purple surfaces,
gold for achievements, progress and primary actions, turquoise for secondary
highlights and keyboard focus.

- **Tokens:** `src/retrocheevos/gui/styles.py` defines semantic color,
  typography, shape, size and spacing tokens and the application stylesheet.
  Older color names (`BG`, `LINK`, ...) are aliases kept until each screen is
  converted.
- **Components:** `src/retrocheevos/gui/components.py` provides buttons
  (primary, secondary, ghost, danger; regular and compact), filter chips,
  sidebar items, search fields, per-mode progress, metric cards, game cards,
  achievement rows and status pills. Large grids paint with delegates that use
  the same tokens instead of one widget per item.
- **Preview:** `tools/preview/component_preview.py` shows every component state,
  the tokens with their contrast ratios and the brand size comparison.
- **Contrast adjustments:** the reference outline `#3A3555` reaches only
  1.5:1 against panels, so interactive control borders use the derived
  `OUTLINE_CONTROL` (`#726A99`, 3.4:1 on panels). The reference outline remains
  for decorative dividers. Text tokens reach at least 4.8:1 on every surface;
  `tests/gui/test_visual_system.py` enforces the thresholds.
- **Fonts:** Inter (Regular, Medium, SemiBold, Bold; v4.1) for interface text
  and Space Grotesk (Medium, Bold; upstream commit `03507d0`) for headings,
  metrics and branding. Both are under the SIL Open Font License 1.1; the
  files and license texts live in `assets/fonts/` and are bundled with the
  application. If a font cannot load, the stylesheet falls back to Noto Sans or
  Segoe UI.

## Brand exploration

Vector copies of concepts A, B and C and the wordmark are in
[brand-exploration/](brand-exploration/README.md). The preview's brand sheet
renders them at 16, 24, 32, 48, 64 and 128 px on dark and light taskbar
backgrounds. First observation on Linux: at 16 px, concept A remains
recognizable while C's trophy becomes too small to read; at 48 px and above
both work. This supports the recommendation of A as the small icon and C as a
larger variant, but D1 remains open until it is checked on Windows.

## Current runtime artwork

The application is now named TrophyTracker. The existing R-shaped controller,
achievement check and coral sparkle are retained from the Retrocheevos artwork. The shared header pairs
the emblem with a text wordmark, keeping the name sharp at different scales.

- `assets/logo.png`: header emblem.
- `assets/reference/retrocheevos-logo.jpeg`: historical source reference; not bundled.
- `assets/icon.png`: square desktop and AppImage icon, also resampled by Qt.
- The emblem's mint `#6ce7c4` and coral `#ff957f` belong to this pre-revamp
  artwork; the application theme no longer uses them.
- [Historical Retrocheevos 1.1.0 Home preview](previews/home-1.1.0.png) uses fictional account and progress data.

Persistent Home, Library, Lists and Settings navigation exposes the primary
destinations. Settings separates accounts, emulators and profile synchronization.
Scrollable pages retain access to content on shorter displays.

## Asset generation

Mode: built-in `image_gen`, iterative image editing. The final generated asset
is saved as both PNG paths above. The final prompt was:

> Finalize this same R/controller/checkmark/coral-spark emblem as an opaque desktop app icon. Replace ALL transparent regions and ALL black regions, including the controller's negative-space opening and surrounding canvas, with a single perfectly uniform solid dark ink background #101826. This opaque solid background is essential; there must be no transparency anywhere. Clean all speckled edge artifacts. Keep the emblem the same recognizable design but scale the whole emblem to 74 percent of the square so it has comfortable even margins. Use clean solid mint #6CE7C4 for the R and controls and solid coral #FF957F for the check and sparkle, no texture, grain, gradients, glow or shading. Smooth crisp vector-style edges. Flat premium app icon on a plain dark square. No text, no other objects, no mockup, no drop shadow. Square 1024x1024.
