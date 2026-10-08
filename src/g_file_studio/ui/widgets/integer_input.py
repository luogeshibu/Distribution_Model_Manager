from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QAbstractSpinBox, QSpinBox, QWidget


class IntegerInput(QSpinBox):
    """只允许直接键盘输入的整数控件。

    保留 QSpinBox 的整数校验能力，但隐藏上下调节按钮，并忽略鼠标滚轮、
    上下方向键和 PageUp/PageDown，避免用户滚动页面时意外改变参数。
    """

    def __init__(
        self,
        value: int = 0,
        minimum: int = 0,
        maximum: int = 100000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(False)
        self.setAccelerated(False)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        """忽略鼠标滚轮，交给外层滚动页面处理。"""
        event.ignore()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        """禁止通过方向键或翻页键递增/递减，只允许直接编辑数字。"""
        if event.key() in {
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
        }:
            event.ignore()
            return
        super().keyPressEvent(event)
