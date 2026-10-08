from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QLineEdit, QWidget


class CurrentDateEdit(QDateEdit):
    """日历日期输入框，默认使用运行当天日期。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("yyyy-MM-dd")
        self.setMinimumDate(QDate(1900, 1, 1))
        self.setMaximumDate(QDate(2999, 12, 31))
        self.setDate(QDate.currentDate())
        self.setToolTip("默认使用当前日期；点击右侧日历按钮可选择其他日期。")

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        """忽略鼠标滚轮，避免滚动页面时意外改变日期。"""
        event.ignore()

    def text_value(self) -> str:
        return self.date().toString("yyyy-MM-dd")

    def set_text_value(self, value: str) -> None:
        text = (value or "").strip()
        if not text:
            self.setDate(QDate.currentDate())
            return

        parsed = QDate.fromString(text, "yyyy-MM-dd")
        if not parsed.isValid():
            # 兼容早期配置中可能使用的 yyyy-M-d 格式。
            parsed = QDate.fromString(text, "yyyy-M-d")
        self.setDate(parsed if parsed.isValid() else QDate.currentDate())


class PersonEditor(QWidget):
    def __init__(self, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name_edit = QLineEdit()
        self.date_edit = CurrentDateEdit()
        self.name_edit.setPlaceholderText(f"{role} 姓名")
        self.name_edit.setToolTip(f"填写 {role} 姓名")
        self.date_edit.setToolTip(f"{role} 日期默认是当前日期；点击日历按钮可修改。")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.name_edit, 2)
        layout.addWidget(self.date_edit, 1)

    def name(self) -> str:
        return self.name_edit.text().strip()

    def date(self) -> str:
        return self.date_edit.text_value()

    def set_values(self, name: str, date: str) -> None:
        self.name_edit.setText(name)
        self.date_edit.set_text_value(date)
