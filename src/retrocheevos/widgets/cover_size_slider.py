"""Slider controlling how big cover art is drawn.

Used by the Library grid and Home's Continue Playing. Emits a pixel size and
nothing else — the owning page decides what to do with it (rebuild the grid,
recompute how many columns fit), keeping this presentation-only like every
other widget here.

The size is **not persisted**: there is no settings table for view
preferences yet, and inventing one for a single slider would mean a schema
migration for something the user can redo with one drag. It resets to
`DEFAULT_SIZE` each run; if more view preferences appear, that's the moment
to add storage for all of them at once.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSlider, QWidget

DEFAULT_MIN_SIZE = 75
DEFAULT_MAX_SIZE = 160
DEFAULT_SIZE = 150
STEP = 10
# Compact on purpose. Stretched across the page the slider read as the
# section's main control rather than a small adjustment to it, and a
# full-width track makes a 40-160px range absurdly fine-grained per pixel.
SLIDER_WIDTH = 160


class CoverSizeSlider(QWidget):
    size_changed = Signal(int)  # cover edge in pixels

    def __init__(
        self,
        initial_size: int = DEFAULT_SIZE,
        label: str = "Cover size",
        max_size: int = DEFAULT_MAX_SIZE,
        min_size: int = DEFAULT_MIN_SIZE,
    ) -> None:
        """`min_size` is per-instance: the two grids have different floors —
        Continue Playing's cards are smaller to begin with, and the Library's
        captions need room to stay legible."""
        super().__init__()

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(min_size)
        self._slider.setMaximum(max_size)
        self._slider.setSingleStep(STEP)
        self._slider.setPageStep(STEP)
        self._slider.setTickInterval(STEP)
        self._slider.setValue(max(min_size, min(initial_size, max_size)))
        self._slider.setFixedWidth(SLIDER_WIDTH)
        # `valueChanged`, so the covers resize under the cursor as you drag.
        # This was `sliderReleased` to avoid rebuilding the grid per pixel;
        # `STEP` is what keeps that affordable — the value only lands on
        # multiples of 10, so a full drag rebuilds a dozen times, not
        # hundreds.
        self._slider.valueChanged.connect(self._on_value_changed)

        self._value_label = QLabel(f"{self._slider.value()}px")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addWidget(self._slider)
        layout.addWidget(self._value_label)
        # No trailing stretch here: it belongs to whatever row this sits in.
        # Held internally, the widget expanded to fill its row and shoved
        # anything placed beside it (the Refresh button) to the far edge.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def value(self) -> int:
        return self._slider.value()

    def set_value_silently(self, size: int) -> None:
        """Move the slider without emitting `size_changed`.

        Used when re-applying a stored preference on login: the value is
        being *restored*, not chosen, and letting it emit would have the page
        immediately write it straight back — harmless here, but it would also
        rebuild the grid a second time for nothing.
        """
        clamped = max(self._slider.minimum(), min(size, self._slider.maximum()))
        if clamped == self._slider.value():
            return
        self._slider.blockSignals(True)
        self._slider.setValue(clamped)
        self._slider.blockSignals(False)
        self._value_label.setText(f"{clamped}px")

    def _on_value_changed(self, value: int) -> None:
        self._value_label.setText(f"{value}px")
        self.size_changed.emit(value)
