from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QSizePolicy


class CompactLogicLabel(QLabel):
    """Word-wrapped QLabel that hugs the rendered text vertically.

    QLabel's initial sizeHint can be calculated before the final layout width is
    known.  For long workflow descriptions that can leave a single-line label
    with the height of several wrapped lines.  Recomputing the height for the
    current width keeps each workflow card only as tall as its actual text.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        # QLabel implements the actual rich-text / word-wrap calculation.  Feed
        # it the real current width and keep a one-line floor for short cards.
        calculated = super().heightForWidth(max(1, int(width)))
        return max(self.fontMetrics().height() + 8, calculated)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        width = self.width()
        if width > 32:
            hint.setHeight(self.heightForWidth(width))
        return hint

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        width = self.width()
        if width > 32:
            hint.setHeight(self.heightForWidth(width))
        else:
            hint.setHeight(self.fontMetrics().height() + 8)
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A width change may reduce/increase wrapping, so ask the parent layout
        # to recompute our vertical geometry immediately.
        self.updateGeometry()
