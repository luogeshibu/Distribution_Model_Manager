from __future__ import annotations

import sys
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QHBoxLayout, QSizePolicy, QLineEdit, QMessageBox,
)

from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
)
from dmm.config.constants import (
    RMU_RELAY_SIGNAL_CODE,
    RMU_RELAY_SIGNAL_DOMAIN,
    RMU_RELAY_SIGNAL_TABLE_ID,
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
            "RMU 环网柜只有在矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 时才识别。"
            "开关设备名称固定使用环网柜内图上文字；麦加现场默认读取图框上方名称。"
            "允许多选名称方向，多选时只保留所选方向中距离最近的一个 Text。"
            "设备命名规则固定使用图上文字，不再读取三类设备 XML 的 p_NameString："
            "CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。"
            "RMU 内 NariPd_Normal.pwbh.icn.g 为固定 EFI 信号：默认按环网柜 ID 查询 13533 dms_relay_sig，"
            "仅 CODE=EFI INDICATOR 才参与关联，默认回写 value 域 keyid1（域号 40）；表号和域号可在右侧调整。"
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
        rg.addWidget(self.name_detection_mode, 0, 1)

        labels = {"top": "上方", "right": "右侧", "left": "左侧", "bottom": "下方"}
        self.pos_checks = {}
        saved_pos = config.get("rmu_name_positions", DEFAULT_NAME_POSITIONS)
        if not any(bool(saved_pos.get(pos, False)) for pos in labels):
            saved_pos = DEFAULT_NAME_POSITIONS
        for idx, pos in enumerate(("top", "right", "left", "bottom")):
            cb = QCheckBox(labels[pos])
            cb.setChecked(bool(saved_pos.get(pos, DEFAULT_NAME_POSITIONS.get(pos, False))))
            rg.addWidget(cb, 1 + idx // 2, idx % 2)
            self.pos_checks[pos] = cb

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

        rg.addWidget(QLabel("环网柜名称来源"), 5, 0)
        fixed_source = QLabel("环网柜内图上文字（固定）")
        fixed_source.setStyleSheet(
            "font-weight:700;color:#006B52;"
            "background:#EAF8F2;border:1px solid #B9DACD;"
            "border-radius:6px;padding:7px 9px;"
        )
        rg.addWidget(fixed_source, 5, 1)

        note = QLabel(
            "默认勾选上方；允许同时勾选多个方向。多选时程序只保留所选方向中距离最近的一个 Text，"
            "开关名称不再读取 XML p_NameString。CBreakerDis 仅使用环网柜内"
            "图上文字；接地刀闸逻辑名称=配对开关名+D；BusDis 固定为 BUS。"
            "NariPd_Normal.pwbh.icn.g 仍按固定 CODE=EFI INDICATOR 关联，但其表号和域号也可在右侧直接调整。"
            "图上名称无法唯一识别，或与数据库 CODE 校验失败时，会明确告警对应环网柜。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        rg.addWidget(note, 6, 0, 1, 2)
        rg.setRowStretch(7, 1)

        rules_box = QGroupBox("RMU 设备数据库表与域配置（可编辑）")
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

        fixed_row = len(DEFAULT_DEVICE_RULES) + 1
        rules.addWidget(QLabel("pwbh（NariPd_Normal / EFI）"), fixed_row, 0)
        relay_saved = saved_rules.get("pwbh", {})

        self.relay_table_spin = NoWheelSpinBox()
        self.relay_table_spin.setRange(0, 999999)
        self.relay_table_spin.setValue(
            int(relay_saved.get("table_id", RMU_RELAY_SIGNAL_TABLE_ID))
        )
        self.relay_table_spin.setMinimumHeight(36)

        self.relay_domain_spin = NoWheelSpinBox()
        self.relay_domain_spin.setRange(0, 999999)
        self.relay_domain_spin.setValue(
            int(relay_saved.get("domain", RMU_RELAY_SIGNAL_DOMAIN))
        )
        self.relay_domain_spin.setMinimumHeight(36)

        rules.addWidget(self.relay_table_spin, fixed_row, 1)
        rules.addWidget(self.relay_domain_spin, fixed_row, 2)

        relay_note = QLabel(
            f"固定匹配：NariPd_Normal.pwbh.icn.g / CODE={RMU_RELAY_SIGNAL_CODE}；"
            "只允许修改表号和域号，回写仍使用 value 域 keyid1。"
        )
        relay_note.setWordWrap(True)
        relay_note.setStyleSheet("color:#60756d;")
        rules.addWidget(relay_note, fixed_row + 1, 0, 1, 3)

        reset = QPushButton("恢复 RMU 默认配置")
        reset.setMinimumHeight(36)
        reset.clicked.connect(self.restore_defaults)
        rules.addWidget(reset, fixed_row + 2, 0, 1, 3)

        top_row.addWidget(recog, 4)
        top_row.addWidget(rules_box, 7)
        root.addLayout(top_row)

    def restore_defaults(self):
        for tag, rule in DEFAULT_DEVICE_RULES.items():
            self.table_spins[tag].setValue(int(rule["table_id"]))
            self.domain_spins[tag].setValue(int(rule["domain"]))
        self.relay_table_spin.setValue(RMU_RELAY_SIGNAL_TABLE_ID)
        self.relay_domain_spin.setValue(RMU_RELAY_SIGNAL_DOMAIN)
        for pos, value in DEFAULT_NAME_POSITIONS.items():
            self.pos_checks[pos].setChecked(bool(value))
        default_index = self.name_detection_mode.findData(
            DEFAULT_RMU_NAME_DETECTION_MODE
        )
        self.name_detection_mode.setCurrentIndex(max(default_index, 0))
        self.name_exclusions_edit.setText(", ".join(DEFAULT_RMU_NAME_EXCLUSIONS))

    def collect_settings(self):
        positions = {
            key: checkbox.isChecked()
            for key, checkbox in self.pos_checks.items()
        }
        detection_mode = "FIXED"
        if not any(positions.values()):
            raise ValueError(tr("请至少选择一个环网柜名称位置。", self.config.get("language", "zh_CN")))
        if sum(1 for enabled in positions.values() if enabled) > 1:
            QMessageBox.information(
                self,
                "RMU 名称方向提示",
                "已选择多个名称方向。每个环网柜最终只保留一个名称，"
                "程序将在这些方向的候选 Text 中选择距离最近的一个。",
            )

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

        relay_table_id = self.relay_table_spin.value()
        relay_domain = self.relay_domain_spin.value()
        saved_rules["pwbh"] = {
            "table_id": relay_table_id,
            "domain": relay_domain,
        }
        runtime_rules["pwbh"] = {
            "table_id": relay_table_id,
            "domain": relay_domain,
            "match_mode": "FIXED_GFILE_EFI_INDICATOR",
            "description": (
                "NariPd_Normal.pwbh.icn.g -> "
                "dms_relay_sig.CODE=EFI INDICATOR"
            ),
            "fixed_code": RMU_RELAY_SIGNAL_CODE,
            "voltype_required": False,
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
