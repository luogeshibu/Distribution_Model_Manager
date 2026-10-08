from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.ui.widgets.help_widgets import HelpButton


class RuleCard(QFrame):
    """可扩展的处理规则卡片。

    新增基础处理功能时，可以继续创建新的 RuleCard，而不需要把所有字段
    混在一个巨大表单中。
    """

    def __init__(
        self,
        title: str,
        description: str,
        help_html: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ruleCard")
        self.setProperty("enabledRule", True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(9)
        self.enabled = QCheckBox()
        self.enabled.setChecked(True)
        self.enabled.setToolTip(f"启用或关闭规则：{title}")

        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("ruleTitle")
        desc_label = QLabel(description)
        desc_label.setObjectName("ruleDescription")
        desc_label.setWordWrap(True)
        text_layout.addWidget(title_label)
        text_layout.addWidget(desc_label)

        header.addWidget(self.enabled, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(text_box, 1)
        header.addWidget(HelpButton(title, help_html), 0, Qt.AlignmentFlag.AlignTop)

        self.options = QWidget()
        self.options_layout = QVBoxLayout(self.options)
        self.options_layout.setContentsMargins(29, 0, 0, 0)
        self.options_layout.setSpacing(8)

        root.addLayout(header)
        root.addWidget(self.options)
        self.enabled.toggled.connect(self._set_enabled)

    def _set_enabled(self, enabled: bool) -> None:
        self.options.setEnabled(enabled)
        self.setProperty("enabledRule", enabled)
        self.style().unpolish(self)
        self.style().polish(self)
