from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QGridLayout, QSpinBox, QPushButton, QSizePolicy,
    QAbstractSpinBox, QComboBox, QCheckBox, QLineEdit,
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


class NoWheelComboBox(QComboBox):
    """禁止鼠标滚轮误切换选项，仍允许点击下拉和键盘操作。"""

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
            "馈线模型仅支持三种馈线确定方式：G 根节点 facID、文件名、人工输入。"
            "三种方式最终都必须唯一匹配到 13500 / dms_feeder_device；"
            "如果不能唯一确认，则直接报错并阻断，不再使用 RMU、连接拓扑或 "
            "FEEDER_ID 反推馈线。确认馈线后，程序可按需补齐缺失的 "
            "dms_section_device，再按原有规则关联 FeedLine。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        root.addWidget(info)

        resolution_box = QGroupBox("馈线识别与数据库补齐")
        resolution_grid = QGridLayout(resolution_box)
        resolution_grid.setContentsMargins(14, 18, 14, 14)
        resolution_grid.setHorizontalSpacing(12)
        resolution_grid.setVerticalSpacing(10)

        resolution_grid.addWidget(QLabel("馈线识别方式"), 0, 0)
        self.feeder_resolution_mode = NoWheelComboBox()
        self.feeder_resolution_mode.addItem(
            "自动：facID → 文件名 → 人工输入",
            "AUTO",
        )
        self.feeder_resolution_mode.addItem(
            "仅使用 G 根节点 facID",
            "FACID",
        )
        self.feeder_resolution_mode.addItem(
            "仅使用文件名",
            "FILENAME",
        )
        self.feeder_resolution_mode.addItem(
            "人工输入",
            "MANUAL",
        )
        saved_mode = str(
            config.get("feeder_resolution_mode", "AUTO") or "AUTO"
        ).upper()
        mode_index = self.feeder_resolution_mode.findData(saved_mode)
        self.feeder_resolution_mode.setCurrentIndex(
            mode_index if mode_index >= 0 else 0
        )
        self.feeder_resolution_mode.setMinimumHeight(36)
        resolution_grid.addWidget(
            self.feeder_resolution_mode,
            0,
            1,
            1,
            2,
        )

        resolution_grid.addWidget(QLabel("人工馈线名称"), 1, 0)
        self.manual_feeder_name = QLineEdit(
            str(config.get("manual_feeder_name", "") or "")
        )
        self.manual_feeder_name.setPlaceholderText(
            "例如：JED CTL ADF 16"
        )
        self.manual_feeder_name.setMinimumHeight(36)
        resolution_grid.addWidget(
            self.manual_feeder_name,
            1,
            1,
            1,
            2,
        )

        self.auto_create_missing_sections = QCheckBox(
            "执行模型关联时自动创建数据库中缺失的馈线段"
        )
        self.auto_create_missing_sections.setChecked(
            bool(config.get("auto_create_missing_sections", True))
        )
        self.auto_create_missing_sections.setToolTip(
            "仅 INSERT DMS_SECTION_DEVICE 中确实不存在的记录；"
            "不会 UPDATE / DELETE 已有记录。创建成功后会重新查询数据库，"
            "再计算 Expected KeyID 并修改本地 G 输出副本。"
        )
        resolution_grid.addWidget(
            self.auto_create_missing_sections,
            2,
            0,
            1,
            3,
        )

        db_notice = QLabel(
            "数据库写入边界：仅在此选项启用且执行【模型关联】时，"
            "允许 INSERT 缺失的 DMS_SECTION_DEVICE。"
            "模型校验阶段不写数据库；已有馈线段绝不重复创建。"
        )
        db_notice.setWordWrap(True)
        db_notice.setStyleSheet(
            "background:#FFF7E6;color:#8A5A00;"
            "border:1px solid #F1D59B;border-radius:6px;padding:7px 9px;"
        )
        resolution_grid.addWidget(db_notice, 3, 0, 1, 3)
        resolution_grid.setColumnStretch(1, 1)
        root.addWidget(resolution_box)

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
        self.section_table.setValue(self.DEFAULT_SECTION_TABLE_ID)
        self.section_domain.setValue(self.DEFAULT_SECTION_DOMAIN)
        self.feeder_resolution_mode.setCurrentIndex(0)
        self.manual_feeder_name.clear()
        self.auto_create_missing_sections.setChecked(True)

    def collect_settings(self):
        # 馈线主表 13500 是程序内部固定业务表，不再作为用户配置项显示。
        return {
            "feeder_table_id": self.DEFAULT_FEEDER_TABLE_ID,
            "section_table_id": int(self.section_table.value()),
            "section_domain": int(self.section_domain.value()),
            "feeder_resolution_mode": str(
                self.feeder_resolution_mode.currentData() or "AUTO"
            ),
            "manual_feeder_name": self.manual_feeder_name.text().strip(),
            "auto_create_missing_sections": bool(
                self.auto_create_missing_sections.isChecked()
            ),
        }
