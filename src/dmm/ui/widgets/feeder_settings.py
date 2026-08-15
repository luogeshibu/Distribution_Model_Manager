from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QGridLayout, QSpinBox, QPushButton, QSizePolicy,
    QAbstractSpinBox, QComboBox,
)


def _resource_dir():
    if getattr(sys, "frozen", False):
        return (
            Path(
                getattr(
                    sys,
                    "_MEIPASS",
                    Path(sys.executable).resolve().parent,
                )
            )
            / "dmm"
            / "resources"
        )
    return Path(__file__).resolve().parents[2] / "resources"


SPIN_UP_ICON = (_resource_dir() / "spin_up.png").as_posix()
SPIN_DOWN_ICON = (_resource_dir() / "spin_down.png").as_posix()


class NoWheelSpinBox(QSpinBox):
    """
    与 RMU 模块完全一致的数字输入框：
    - 深绿色上下调节按钮；
    - 支持直接输入；
    - 鼠标滚轮不误修改数值。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.setKeyboardTracking(False)
        self.setWrapping(False)
        self.setSingleStep(1)
        self.setAccelerated(False)
        self.setStyleSheet(f"""
            QSpinBox {{
                padding-right: 30px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 28px;
                background: #006B52;
                border-left: 1px solid #005640;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: #00966E;
            }}
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
                background: #004D3A;
            }}
            QSpinBox::up-arrow {{
                image: url("{SPIN_UP_ICON}");
                width: 14px;
                height: 10px;
            }}
            QSpinBox::down-arrow {{
                image: url("{SPIN_DOWN_ICON}");
                width: 14px;
                height: 10px;
            }}
        """)

    def wheelEvent(self, event):
        event.ignore()


class FeederSettingsWidget(QWidget):
    DEFAULT_FEEDER_TABLE_ID = 13500
    DEFAULT_SECTION_TABLE_ID = 13503
    DEFAULT_SECTION_DOMAIN = 1

    def __init__(self, config):
        super().__init__()
        self.config = config

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Maximum,
        )
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "馈线模型支持自动识别单馈线图和多馈线组合大图。"
            "组合图会利用 Bus 上方馈线名称锚点及馈线之间的空间间隔"
            "对 FeedLine 分区；详细规则请点击【当前模型帮助】。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        root.addWidget(info)

        mode_box = QGroupBox("图纸类型识别")
        mode_grid = QGridLayout(mode_box)
        mode_grid.setContentsMargins(14, 18, 14, 14)
        mode_grid.addWidget(QLabel("处理模式"), 0, 0)
        self.drawing_mode = QComboBox()
        self.drawing_mode.addItem("RMU 拓扑自动识别（固定）", "AUTO")
        self.drawing_mode.setCurrentIndex(0)
        self.drawing_mode.setEnabled(False)
        self.drawing_mode.setToolTip(
            "单馈线图和组合大图统一使用 RMU + 连接拓扑 + FEEDER_ID 识别，"
            "不再依赖馈线名称或人工指定图纸类型。"
        )
        self.drawing_mode.setMinimumHeight(36)
        mode_grid.addWidget(self.drawing_mode, 0, 1)
        mode_grid.setColumnStretch(1, 1)
        root.addWidget(mode_box)

        mapping = QGroupBox("馈线段数据库表与域配置")
        mapping.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        grid = QGridLayout(mapping)
        grid.setContentsMargins(14, 18, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 3)

        grid.addWidget(QLabel("用途"), 0, 0)
        grid.addWidget(QLabel("表号（Table ID）"), 0, 1)
        grid.addWidget(QLabel("域号（Domain）"), 0, 2)

        grid.addWidget(QLabel("馈线段 dms_section_device"), 1, 0)

        self.section_table = NoWheelSpinBox()
        self.section_table.setRange(1, 999999)
        self.section_table.setMinimumHeight(36)
        self.section_table.setValue(
            int(
                config.get(
                    "section_table_id",
                    self.DEFAULT_SECTION_TABLE_ID,
                )
            )
        )
        grid.addWidget(self.section_table, 1, 1)

        self.section_domain = NoWheelSpinBox()
        self.section_domain.setRange(0, 999999)
        self.section_domain.setMinimumHeight(36)
        self.section_domain.setValue(
            int(
                config.get(
                    "section_domain",
                    self.DEFAULT_SECTION_DOMAIN,
                )
            )
        )
        grid.addWidget(self.section_domain, 1, 2)

        restore = QPushButton("恢复馈线默认配置")
        restore.setMinimumHeight(36)
        restore.clicked.connect(self.restore_defaults)
        grid.addWidget(restore, 2, 0, 1, 3)

        root.addWidget(mapping)

    def restore_defaults(self):
        self.drawing_mode.setCurrentIndex(0)
        self.section_table.setValue(self.DEFAULT_SECTION_TABLE_ID)
        self.section_domain.setValue(self.DEFAULT_SECTION_DOMAIN)

    def collect_settings(self):
        # 馈线主表 13500 是程序内部固定业务表，不再作为用户配置项显示。
        return {
            "feeder_table_id": self.DEFAULT_FEEDER_TABLE_ID,
            "section_table_id": int(self.section_table.value()),
            "section_domain": int(self.section_domain.value()),
            "drawing_mode": str(self.drawing_mode.currentData() or "AUTO"),
        }
