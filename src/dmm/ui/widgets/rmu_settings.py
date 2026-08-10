from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QHBoxLayout, QSizePolicy,
)

from dmm.config.defaults import DEFAULT_DEVICE_RULES, DEFAULT_NAME_POSITIONS

def _resource_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "dmm" / "resources"
    return Path(__file__).resolve().parents[2] / "resources"

SPIN_UP_ICON = (_resource_dir() / "spin_up.png").as_posix()
SPIN_DOWN_ICON = (_resource_dir() / "spin_down.png").as_posix()


class NoWheelSpinBox(QSpinBox):
    """原生 SpinBox：支持输入和上下按钮，但鼠标滚轮不修改数值。"""

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
        self.setFocusPolicy(self.focusPolicy())

    def wheelEvent(self, event):
        event.ignore()

class NoWheelComboBox(QComboBox):
    """禁止滚轮误切换选项，仍允许点击下拉框。"""

    def wheelEvent(self, event):
        event.ignore()


class RmuSettingsWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "RMU 环网柜通过 G 文件结构自动识别。开关设备名称可选择使用 "
            "p_NameString，或使用环网柜内部、紧邻 CBreakerDis 的图上文字。"
            "选择图上文字时，后续校验不再读取三类设备 XML 的 p_NameString："
            "CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        # ------------------------------------------------------------------
        # 第一行：RMU 识别 + 数据库表/域配置并排展示。
        # 避免纵向堆叠导致小分辨率下控件被压扁。
        # ------------------------------------------------------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        recog = QGroupBox("RMU 环网柜识别")
        recog.setMinimumWidth(330)
        recog.setMinimumHeight(285)
        rg = QGridLayout(recog)
        rg.setContentsMargins(14, 18, 14, 14)
        rg.setHorizontalSpacing(18)
        rg.setVerticalSpacing(10)
        rg.addWidget(QLabel("环网柜名称位置"), 0, 0, 1, 2)

        labels = {"top": "上方", "right": "右侧", "left": "左侧", "bottom": "下方"}
        self.pos_checks = {}
        saved_pos = config.get("rmu_name_positions", DEFAULT_NAME_POSITIONS)
        for idx, pos in enumerate(("top", "right", "left", "bottom")):
            cb = QCheckBox(labels[pos])
            cb.setChecked(bool(saved_pos.get(pos, False)))
            rg.addWidget(cb, 1 + idx // 2, idx % 2)
            self.pos_checks[pos] = cb

        rg.addWidget(QLabel("开关名称来源"), 3, 0)
        self.breaker_source = NoWheelComboBox()
        self.breaker_source.addItem("使用 p_NameString", "P_NAME_STRING")
        self.breaker_source.addItem("使用环网柜内图上文字", "GRAPHICAL_TEXT")
        saved_source = config.get("breaker_name_source", "P_NAME_STRING")
        index = self.breaker_source.findData(saved_source)
        self.breaker_source.setCurrentIndex(index if index >= 0 else 0)
        rg.addWidget(self.breaker_source, 3, 1)

        note = QLabel(
            "图上文字模式使用框内文字与 CBreakerDis 的最近唯一空间关系；"
            "无法唯一确定时直接报错。该模式下 CBreakerDis 的逻辑 p_NameString=图上名称，"
            "接地刀闸=开关名+D，BusDis=BUS。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        rg.addWidget(note, 4, 0, 1, 2)
        rg.setRowStretch(5, 1)

        rules_box = QGroupBox("RMU 设备数据库表与域配置")
        rules_box.setMinimumWidth(590)
        rules_box.setMinimumHeight(285)
        rules = QGridLayout(rules_box)
        rules.setContentsMargins(14, 18, 14, 14)
        rules.setHorizontalSpacing(12)
        rules.setVerticalSpacing(9)
        rules.setColumnStretch(0, 2)
        rules.setColumnStretch(1, 3)
        rules.setColumnStretch(2, 3)
        rules.addWidget(QLabel("G 图元类型"), 0, 0)
        rules.addWidget(QLabel("表号（Table ID）"), 0, 1)
        rules.addWidget(QLabel("域号（Domain）"), 0, 2)

        self.table_spins = {}
        self.domain_spins = {}
        saved_rules = config.get("device_rules", {})
        for row, (tag, default) in enumerate(DEFAULT_DEVICE_RULES.items(), start=1):
            vals = dict(default)
            vals.update(saved_rules.get(tag, {}))
            rules.addWidget(QLabel(tag), row, 0)

            table = NoWheelSpinBox()
            table.setRange(0, 999999)
            table.setValue(int(vals["table_id"]))
            table.setMinimumHeight(36)

            domain = NoWheelSpinBox()
            domain.setRange(0, 999999)
            domain.setValue(int(vals["domain"]))
            domain.setMinimumHeight(36)

            rules.addWidget(table, row, 1)
            rules.addWidget(domain, row, 2)
            self.table_spins[tag] = table
            self.domain_spins[tag] = domain

        reset = QPushButton("恢复 RMU 默认配置")
        reset.setMinimumHeight(36)
        reset.clicked.connect(self.restore_defaults)
        rules.addWidget(reset, len(DEFAULT_DEVICE_RULES) + 1, 0, 1, 3)

        top_row.addWidget(recog, 4)
        top_row.addWidget(rules_box, 7)
        root.addLayout(top_row)

    def restore_defaults(self):
        for tag, rule in DEFAULT_DEVICE_RULES.items():
            self.table_spins[tag].setValue(int(rule["table_id"]))
            self.domain_spins[tag].setValue(int(rule["domain"]))
        for pos, value in DEFAULT_NAME_POSITIONS.items():
            self.pos_checks[pos].setChecked(bool(value))
        self.breaker_source.setCurrentIndex(0)

    def collect_settings(self):
        positions = {
            key: checkbox.isChecked()
            for key, checkbox in self.pos_checks.items()
        }
        if not any(positions.values()):
            raise ValueError("请至少选择一个环网柜名称位置。")

        saved_rules = {}
        runtime_rules = {}

        for tag, default in DEFAULT_DEVICE_RULES.items():
            table_id = self.table_spins[tag].value()
            domain = self.domain_spins[tag].value()

            saved_rules[tag] = {
                "table_id": table_id,
                "domain": domain,
            }

            runtime_rules[tag] = {
                "table_id": table_id,
                "domain": domain,
                "match_mode": default["match_mode"],
                "description": default["description"],
            }

        return {
            "rmu_name_positions": positions,
            "breaker_name_source": self.breaker_source.currentData(),
            "device_rules": saved_rules,
            "_runtime_rules": runtime_rules,
        }

