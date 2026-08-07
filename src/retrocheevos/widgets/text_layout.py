"""Fit text into a fixed-width box by wrapping first, eliding only as a
last resort.

`QLabel.setWordWrap(True)` in a fixed-height box can clip, because how many
lines a string needs isn't knowable in advance. Eliding to one line never
clips but throws away words that would have fitted on a second line. This
does what a person would: fill line after line, up to a limit, and only put
an "…" on the final line if there is still text left over.

Returns the lines, so the caller can size the box from `len(lines)` and be
certain the text fits.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics


def wrap_lines(
    text: str, metrics: QFontMetrics, width: int, max_lines: int
) -> list[str]:
    """Greedy word wrap to at most `max_lines`, last line elided if needed.

    `metrics` must come from a **polished** widget — before that, `font()`
    reports the default rather than the stylesheet's, and everything measured
    against it is too generous by exactly the amount that makes text overflow.
    """
    words = text.split()
    if not words:
        return [""]

    # Wrap without a limit first, then decide what to do with the overflow —
    # simpler to get right than trying to spot the last line mid-loop.
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and metrics.horizontalAdvance(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)

    if len(lines) > max_lines:
        # Everything that didn't fit collapses onto the final allowed line
        # and is elided as one, so the "…" stands for all the missing words.
        kept = lines[: max_lines - 1]
        kept.append(
            metrics.elidedText(
                " ".join(lines[max_lines - 1 :]), Qt.TextElideMode.ElideRight, width
            )
        )
        lines = kept

    # A single word wider than the box can't be wrapped, only elided.
    return [
        line
        if metrics.horizontalAdvance(line) <= width
        else metrics.elidedText(line, Qt.TextElideMode.ElideRight, width)
        for line in lines
    ]
