from __future__ import annotations

from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QLineEdit, QWidget


class WheelSafeLineEdit(QLineEdit):
    """数据库等关键配置使用的防滚轮文本输入框。

    文本输入本身不需要通过滚轮改变值。这里显式忽略滚轮事件，让外层
    QScrollArea 继续滚动页面，同时保证鼠标悬停/输入框获得焦点时不会消费
    滚轮事件。键盘输入、粘贴、选择和密码回显等正常编辑能力保持不变。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTipDuration(8000)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API name
        event.ignore()
