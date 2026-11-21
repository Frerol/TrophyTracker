# Brand exploration files

Vector copies of the brand concepts from the Brand board of the
[reviewed UI proposal](../ui-proposal-reviewed.html), extracted unchanged
except for English accessibility labels and explicit sizes. They are design
inputs for R17 and decision D1, not runtime assets: the shipped icon and logo
remain in `assets/` until D1 selects a concept.

| File | Concept |
| --- | --- |
| `concept-a-pixel-trophy.svg` | A: pixel trophy |
| `concept-b-trophy-dpad.svg` | B: trophy and D-pad (documented alternative) |
| `concept-c-cartridge-trophy.svg` | C: cartridge with pixel trophy |
| `wordmark.svg` | Pixel trophy, italic Space Grotesk Bold wordmark, turquoise progress underline and gold star |

The wordmark SVG references the Space Grotesk font by name; render it with the
bundled font from `assets/fonts/` installed or loaded.

The size comparison sheet is produced by the component preview:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/preview/component_preview.py --brand-sheet brand-sheet.png
```
