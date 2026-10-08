from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QProgressBar


class SmoothProgressBar(QProgressBar):
    """A determinate 0~100 progress bar that rises monotonically and smoothly.

    Worker callbacks may report large percentage jumps.  The bar keeps the latest
    target and advances the visible value in small steps so every page presents the
    same calm 0~100% progress behavior.  Calling ``setValue(0)`` starts a new run.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._target = 0
        self._display = 0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._advance)
        self.setRange(0, 100)
        QProgressBar.setValue(self, 0)

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt API naming
        value = max(0, min(100, int(value)))
        if value <= 0:
            self._timer.stop()
            self._target = 0
            self._display = 0
            QProgressBar.setValue(self, 0)
            return
        self._target = max(self._target, value)
        if self._display < self._target and not self._timer.isActive():
            self._timer.start()

    def _advance(self) -> None:
        if self._display >= self._target:
            self._timer.stop()
            return
        distance = self._target - self._display
        step = 2 if distance >= 18 else 1
        self._display = min(self._target, self._display + step)
        QProgressBar.setValue(self, self._display)
        if self._display >= self._target:
            self._timer.stop()
