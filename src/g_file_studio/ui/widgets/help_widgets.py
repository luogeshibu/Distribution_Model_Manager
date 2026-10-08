from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from g_file_studio.ui.help_content import APP_HELP, APP_HELP_EN

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class HelpDialog(QDialog):
    def __init__(self, title: str, html: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout.addWidget(title_label)
        layout.addWidget(browser, 1)
        layout.addWidget(buttons)


class HelpButton(QToolButton):
    def __init__(
        self,
        title: str,
        help_text: str,
        parent: QWidget | None = None,
        *,
        page_button: bool = False,
    ) -> None:
        super().__init__(parent)
        self.help_title = title
        self.help_text = help_text
        self.setText("帮助" if page_button else "?")
        self.setObjectName("pageHelpButton" if page_button else "helpButton")
        self.setToolTip(help_text if not page_button else f"查看“{title}”说明")
        self.setStatusTip(self.toolTip())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self.show_help)

    def show_help(self) -> None:
        window = self.window()
        manager = getattr(window, "language_manager", None)
        title = manager.text(self.help_title) if manager is not None else self.help_title
        help_text = manager.runtime_text(self.help_text) if manager is not None else self.help_text
        if manager is not None and manager.is_english:
            # Help bodies are long-form content. Use the curated English payload
            # rather than sentence-fragment fallback translation.
            for key, (zh_title, zh_html) in APP_HELP.items():
                if self.help_title == zh_title and self.help_text == zh_html and key in APP_HELP_EN:
                    title, help_text = APP_HELP_EN[key]
                    break
        dialog = HelpDialog(title, help_text, window)
        if manager is not None:
            manager.translate_widget_tree(dialog)
        dialog.exec()


class PageHeader(QWidget):
    helpRequested = Signal()

    def __init__(
        self,
        title: str,
        description: str,
        help_title: str,
        help_html: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(16)

        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        description_label = QLabel(description)
        description_label.setObjectName("pageDescription")
        description_label.setWordWrap(True)
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        help_button = HelpButton(help_title, help_html, page_button=True)
        help_button.setText("页面帮助")

        layout.addWidget(text_box, 1)
        layout.addWidget(help_button, 0, Qt.AlignmentFlag.AlignTop)


class InfoBanner(QFrame):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("infoBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(9)

        icon = QLabel("i")
        icon.setObjectName("infoIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel(text)
        self.label.setObjectName("infoText")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.label, 1)

    def set_text(self, text: str) -> None:
        self.label.setText(text)


class HelpLabel(QWidget):
    def __init__(self, text: str, help_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout.addWidget(label)
        if help_text:
            layout.addWidget(HelpButton(text, f"<p>{help_text}</p>"))
        layout.addStretch(1)


def _repolish_button(button: QWidget) -> None:
    button.style().unpolish(button)
    button.style().polish(button)


def set_primary(button: QWidget) -> None:
    """Apply the shared primary-action appearance to a button."""
    button.setProperty("secondary", False)
    button.setProperty("danger", False)
    button.setProperty("actionRole", "primary")
    _repolish_button(button)


def set_secondary(button: QWidget) -> None:
    """Apply the shared auxiliary-action appearance to a button."""
    button.setProperty("secondary", True)
    button.setProperty("danger", False)
    button.setProperty("actionRole", "secondary")
    _repolish_button(button)


def set_danger(button: QWidget) -> None:
    """Apply the shared destructive-action appearance to a button."""
    button.setProperty("secondary", False)
    button.setProperty("danger", True)
    button.setProperty("actionRole", "danger")
    _repolish_button(button)
