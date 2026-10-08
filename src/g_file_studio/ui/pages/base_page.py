from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from g_file_studio.ui.widgets.help_widgets import PageHeader


class BasePage(QScrollArea):
    def __init__(
        self,
        title: str,
        description: str,
        help_title: str,
        help_html: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageScroll")
        self.setWidgetResizable(True)

        self.body = QWidget()
        self.body.setObjectName("contentRoot")
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(28, 24, 28, 28)
        self.layout.setSpacing(16)
        self.layout.addWidget(PageHeader(title, description, help_title, help_html))
        self.setWidget(self.body)
