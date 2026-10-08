from __future__ import annotations

# 电网图形工作台主题：深海军蓝用于运行区，电网绿用于主操作与状态，
# 青色用于拓扑/连接提示，暖黄色仅用于警告。避免使用具体企业商标配色。
APP_STYLE = r"""
QMainWindow, QDialog {
    background: #edf4f2;
}

QWidget {
    color: #17313a;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}

QLabel, QCheckBox, QRadioButton {
    background: transparent;
}

QWidget#contentRoot,
QScrollArea#pageScroll,
QScrollArea#pageScroll > QWidget > QWidget {
    background: #f3f7f6;
}

QWidget#sidebar {
    background: #0a1f29;
    border: none;
}

QFrame#brandBadge {
    background: #0b7a5a;
    border: 1px solid #21a27d;
    border-radius: 11px;
}

QLabel#brandLetter {
    color: #ffffff;
    font-size: 20px;
    font-weight: 800;
}

QLabel#brandTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 750;
}

QLabel#brandSubtitle {
    color: #a9c6c2;
    font-size: 12px;
}

QLabel#gridModeBadge {
    color: #8ee1c6;
    background: #10313b;
    border: 1px solid #1b5260;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#sidebarVersion {
    color: #6f9296;
    font-size: 11px;
}

QListWidget#navigation {
    background: transparent;
    border: none;
    color: #d4e2e2;
    outline: none;
    padding: 0;
}

QListWidget#navigation::item {
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
    margin: 3px 0;
    padding: 13px 16px;
}

QListWidget#navigation::item:hover {
    background: #123440;
    color: #ffffff;
    border-left-color: #2fa889;
}

QListWidget#navigation::item:selected {
    background: #0b7a5a;
    color: #ffffff;
    border-left-color: #84e2c3;
}

QLabel#pageTitle {
    color: #102d36;
    font-size: 24px;
    font-weight: 760;
}

QLabel#pageDescription {
    color: #60757c;
    font-size: 13px;
}

QFrame#infoBanner {
    background: #e9f7f2;
    border: 1px solid #b8dfd1;
    border-left: 4px solid #0b7a5a;
    border-radius: 9px;
}

QLabel#infoIcon {
    background: #0b7a5a;
    color: white;
    border-radius: 10px;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    font-weight: 700;
}

QLabel#infoText {
    color: #315c59;
}

QGroupBox {
    background: #ffffff;
    border: 1px solid #cfdfda;
    border-radius: 11px;
    margin-top: 0;
    padding: 38px 16px 14px 16px;
    font-weight: 680;
    color: #12343b;
}

QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 16px;
    top: 12px;
    padding: 0;
    color: #0a5e49;
    background: transparent;
}

QLabel#fieldLabel {
    color: #29464d;
    font-weight: 580;
}

QLabel#mutedText {
    color: #687c82;
}

QLineEdit,
QSpinBox,
QDateEdit,
QComboBox,
QPlainTextEdit,
QTextEdit,
QTableWidget,
QTreeWidget {
    background: #ffffff;
    border: 1px solid #c8d9d5;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #DDF4EB;
    selection-color: #123B32;
}

QLineEdit:hover,
QSpinBox:hover,
QDateEdit:hover,
QComboBox:hover {
    border-color: #80b9aa;
}

QLineEdit:focus,
QSpinBox:focus,
QDateEdit:focus,
QComboBox:focus,
QPlainTextEdit:focus,
QTextEdit:focus {
    border: 1px solid #0c8f69;
}

QLineEdit:disabled,
QSpinBox:disabled,
QDateEdit:disabled,
QComboBox:disabled {
    background: #eef3f2;
    color: #87999d;
}

QSpinBox::up-button,
QSpinBox::down-button {
    width: 24px;
    background: #f4f8f7;
    border-left: 1px solid #d2dfdc;
}

QCheckBox {
    color: #29464d;
    spacing: 8px;
    padding: 2px 0;
}

QCheckBox::indicator {
    width: 20px;
    height: 20px;
    background: #ffffff;
    border: 2px solid #708b8f;
    border-radius: 5px;
}

QCheckBox::indicator:hover {
    border-color: #0c8f69;
    background: #eff9f5;
}

QCheckBox::indicator:checked {
    background: #0b7a5a;
    border: 1px solid #0b7a5a;
    image: url("__CHECK_ICON__");
}

QCheckBox::indicator:disabled {
    background: #e9efee;
    border-color: #bdcbc8;
}

QCheckBox[optionChoice="true"] {
    background: #f8fbfa;
    border: 1px solid #c9dad6;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 28px;
    color: #29464d;
    font-weight: 620;
}

QCheckBox[optionChoice="true"]::indicator {
    width: 20px;
    height: 20px;
    border-radius: 5px;
}

QCheckBox[optionChoice="true"]:hover {
    background: #eef8f4;
    border-color: #72b39f;
}

QCheckBox[optionChoice="true"]:checked {
    background: #ddf3ea;
    border: 2px solid #0b7a5a;
    color: #075843;
}

QCheckBox[optionChoice="true"]:disabled {
    background: #eef3f2;
    border-color: #d2ddda;
    color: #87999d;
}


QRadioButton {
    color: #29464d;
    spacing: 8px;
    padding: 2px 0;
}

QRadioButton::indicator {
    width: 20px;
    height: 20px;
    background: #ffffff;
    border: 2px solid #708b8f;
    border-radius: 10px;
}

QRadioButton::indicator:hover {
    border-color: #0c8f69;
    background: #eff9f5;
}

QRadioButton::indicator:checked {
    background: transparent;
    border: none;
    border-radius: 10px;
    image: url("__RADIO_CHECKED_ICON__");
}

QRadioButton::indicator:disabled {
    background: #e9efee;
    border-color: #bdcbc8;
}

QRadioButton[optionChoice="true"] {
    background: #f8fbfa;
    border: 1px solid #c9dad6;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 28px;
    color: #29464d;
    font-weight: 620;
}

QRadioButton[optionChoice="true"]:hover {
    background: #eef8f4;
    border-color: #72b39f;
}

QRadioButton[optionChoice="true"]:checked {
    background: #ddf3ea;
    border: 2px solid #0b7a5a;
    color: #075843;
}

QRadioButton[optionChoice="true"]:disabled {
    background: #eef3f2;
    border-color: #d2ddda;
    color: #87999d;
}

QLabel#colorValue {
    color: #29464d;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-weight: 650;
}

QLabel#colorPreview {
    background: #ffffff;
    border: 1px solid #bcd0cb;
    border-radius: 5px;
}

QPushButton {
    background: #0b7a5a;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 22px;
    font-weight: 680;
}

QPushButton:hover {
    background: #08684d;
}

QPushButton:pressed {
    background: #07553f;
}

QPushButton:disabled {
    background: #a8b8b5;
    color: #edf3f1;
}

QPushButton[secondary="true"] {
    background: #e7efed;
    color: #29464d;
    border: 1px solid #cbdad6;
}

QPushButton[secondary="true"]:hover {
    background: #dbe9e5;
    border-color: #9fc3b8;
}

QPushButton[secondary="true"]:disabled {
    background: #edf2f1;
    color: #8a9a9d;
    border: 1px solid #d7e0de;
}

QPushButton[danger="true"] {
    background: #c94f50;
}

QPushButton[danger="true"]:hover {
    background: #b54042;
}

QToolButton#helpButton {
    background: #edf6f3;
    color: #286b5c;
    border: 1px solid #bdd6cf;
    border-radius: 10px;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    padding: 0;
    font-weight: 750;
}

QToolButton#helpButton:hover {
    background: #dff2eb;
    color: #075843;
    border-color: #73b7a3;
}

QToolButton#pageHelpButton {
    background: #ffffff;
    color: #0b7a5a;
    border: 1px solid #9fcbbb;
    border-radius: 7px;
    padding: 7px 12px;
    font-weight: 680;
}

QToolButton#pageHelpButton:hover {
    background: #e9f7f2;
}

QFrame#ruleCard,
QFrame#taskPanel {
    background: #ffffff;
    border: 1px solid #cfdfda;
    border-radius: 11px;
}

QFrame#ruleCard[enabledRule="false"] {
    background: #f0f4f3;
}

QLabel#ruleTitle,
QLabel#panelTitle {
    color: #12343b;
    font-size: 14px;
    font-weight: 720;
}

QLabel#ruleDescription {
    color: #687c82;
    font-size: 12px;
}

QProgressBar {
    background: #e8efed;
    border: 1px solid #ccd9d6;
    border-radius: 6px;
    text-align: center;
    color: #29464d;
    min-height: 16px;
}

QProgressBar::chunk {
    background: #0b7a5a;
    border-radius: 5px;
}

QHeaderView::section {
    background: #dfece8;
    color: #21434a;
    border: none;
    border-right: 1px solid #c8d9d5;
    border-bottom: 1px solid #c8d9d5;
    padding: 7px;
    font-weight: 680;
}

QTableWidget {
    gridline-color: #dbe6e3;
    alternate-background-color: #f6faf9;
}

QTableWidget::item {
    padding: 5px;
}

QTableWidget::item:selected {
    background: #DDF4EB;
    color: #123B32;
    border-top: 1px solid #79BBA5;
    border-bottom: 1px solid #79BBA5;
}

QTableWidget::item:selected:!active {
    background: #E8F7F2;
    color: #123B32;
}

QScrollArea {
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #adc2bd;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #87a9a1;
}

QStatusBar {
    background: #ffffff;
    border-top: 2px solid #0b7a5a;
    color: #4e686d;
}

QToolTip {
    color: #f4fffb;
    background: #12343b;
    border: 1px solid #2f7f70;
    padding: 5px;
}
"""


def build_app_style() -> str:
    """生成带绝对资源路径的样式，确保开发和打包后均能显示勾选图标。"""
    from g_file_studio.services.paths import resource_root

    check_icon = (resource_root() / "resources" / "icons" / "check.svg").as_posix()
    radio_checked_icon = (
        resource_root() / "resources" / "icons" / "radio_checked.svg"
    ).as_posix()
    return (
        APP_STYLE
        .replace("__CHECK_ICON__", check_icon)
        .replace("__RADIO_CHECKED_ICON__", radio_checked_icon)
    )
