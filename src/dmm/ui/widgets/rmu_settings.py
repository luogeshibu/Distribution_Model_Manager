from __future__ import annotations

import sys
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QHBoxLayout, QSizePolicy, QLineEdit,
)

from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
)
from dmm.i18n import tr

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
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "RMU 环网柜通过 G 文件结构自动识别。开关设备名称可选择使用 "
            "环网柜内部、紧邻 CBreakerDis 的图上文字。"
            "设备命名规则固定使用图上文字，不再读取三类设备 XML 的 p_NameString："
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
        recog.setMinimumHeight(355)
        rg = QGridLayout(recog)
        rg.setContentsMargins(14, 18, 14, 14)
        rg.setHorizontalSpacing(18)
        rg.setVerticalSpacing(10)
        rg.addWidget(QLabel("环网柜名称位置"), 0, 0)

        self.name_detection_mode = NoWheelComboBox()
        self.name_detection_mode.addItem("自动识别（推荐）", "AUTO")
        self.name_detection_mode.addItem("按指定方向", "FIXED")
        saved_mode = str(
            config.get(
                "rmu_name_detection_mode",
                DEFAULT_RMU_NAME_DETECTION_MODE,
            )
            or DEFAULT_RMU_NAME_DETECTION_MODE
        ).strip().upper()
        mode_index = self.name_detection_mode.findData(saved_mode)
        self.name_detection_mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self.name_detection_mode.currentIndexChanged.connect(
            self._update_name_direction_controls
        )
        rg.addWidget(self.name_detection_mode, 0, 1)

        labels = {"top": "上方", "right": "右侧", "left": "左侧", "bottom": "下方"}
        self.pos_checks = {}
        saved_pos = config.get("rmu_name_positions", DEFAULT_NAME_POSITIONS)
        for idx, pos in enumerate(("top", "right", "left", "bottom")):
            cb = QCheckBox(labels[pos])
            cb.setChecked(bool(saved_pos.get(pos, False)))
            rg.addWidget(cb, 1 + idx // 2, idx % 2)
            self.pos_checks[pos] = cb

        self._update_name_direction_controls()

        rg.addWidget(QLabel("环网柜名称排除字符串"), 3, 0, 1, 2)
        self.name_exclusions_edit = QLineEdit()
        saved_exclusions = config.get("rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS)
        if isinstance(saved_exclusions, str):
            saved_exclusions_text = saved_exclusions
        else:
            saved_exclusions_text = ", ".join(str(x) for x in saved_exclusions or [])
        self.name_exclusions_edit.setText(saved_exclusions_text)
        self.name_exclusions_edit.setPlaceholderText("例如：N.O.P, NOP, SFI, DAS/OK")
        rg.addWidget(self.name_exclusions_edit, 4, 0, 1, 2)

        rg.addWidget(QLabel("开关名称来源"), 5, 0)
        fixed_source = QLabel("环网柜内图上文字（固定）")
        fixed_source.setStyleSheet(
            "font-weight:700;color:#006B52;"
            "background:#EAF8F2;border:1px solid #B9DACD;"
            "border-radius:6px;padding:7px 9px;"
        )
        rg.addWidget(fixed_source, 5, 1)

        note = QLabel(
            "自动识别模式会综合搜索名称附近的上、下、左、右方向；"
            "指定方向模式仅搜索用户勾选的方向。"
            "开关名称不再读取 XML p_NameString。CBreakerDis 仅使用环网柜内"
            "图上文字；接地刀闸逻辑名称=配对开关名+D；BusDis 固定为 BUS。"
            "图上名称无法唯一识别，或与数据库 CODE 校验失败时，会明确告警对应环网柜。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        rg.addWidget(note, 6, 0, 1, 2)
        rg.setRowStretch(7, 1)

        rules_box = QGroupBox("RMU 设备数据库表与域配置")
        rules_box.setMinimumWidth(590)
        rules_box.setMinimumHeight(355)
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
        default_index = self.name_detection_mode.findData(
            DEFAULT_RMU_NAME_DETECTION_MODE
        )
        self.name_detection_mode.setCurrentIndex(max(default_index, 0))
        self.name_exclusions_edit.setText(", ".join(DEFAULT_RMU_NAME_EXCLUSIONS))

    def _update_name_direction_controls(self, *_args):
        """Disable legacy direction filters while automatic mode is active."""
        fixed_mode = self.name_detection_mode.currentData() == "FIXED"
        for checkbox in self.pos_checks.values():
            checkbox.setEnabled(fixed_mode)

    def collect_settings(self):
        positions = {
            key: checkbox.isChecked()
            for key, checkbox in self.pos_checks.items()
        }
        detection_mode = self.name_detection_mode.currentData() or "AUTO"
        if detection_mode == "FIXED" and not any(positions.values()):
            raise ValueError(tr("请至少选择一个环网柜名称位置。", self.config.get("language", "zh_CN")))

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

        exclusion_text = self.name_exclusions_edit.text()
        exclusion_values = [
            item.strip()
            for item in re.split(r"[,;\n\r]+", exclusion_text)
            if item.strip()
        ]

        return {
            "rmu_name_positions": positions,
            "rmu_name_detection_mode": detection_mode,
            "rmu_name_exclusions": exclusion_values,
            "breaker_name_source": "GRAPHICAL_TEXT",
            "device_rules": saved_rules,
            "_runtime_rules": runtime_rules,
        }
