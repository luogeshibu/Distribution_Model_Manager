from __future__ import annotations

from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QWidget


class WheelSafeComboBox(QComboBox):
    """不会在收起状态下被鼠标滚轮意外修改的下拉选择框。

    设计规则：
    - 下拉列表未展开时，滚轮事件交还给父级滚动区域，当前选项保持不变；
    - 下拉列表已展开时，允许使用滚轮浏览列表选项；
    - 用户仍可通过展开列表、键盘选择，或在可编辑下拉框中直接输入来修改值。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTipDuration(8000)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API name
        if self.view().isVisible():
            super().wheelEvent(event)
            return

        # 不接受事件，让上层 QScrollArea 继续处理页面滚动。
        event.ignore()
