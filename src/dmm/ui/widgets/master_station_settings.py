from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES
from dmm.ui.widgets.rmu_settings import NoWheelSpinBox


class MasterStationSettingsWidget(QWidget):
    """Settings for the strict, non-topological master-station matcher."""

    def __init__(self, config):
        super().__init__()
        self.config = config or {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        info = QLabel(
            "配网主站设备关联以每个 CBreaker 为锚点，先找它最近的 RMU 矩形框，"
            "只检查该框内部设备或保护信号的已有 KeyID，再直接查询 13501 环网柜表，"
            "使用 RMU 的 FEEDER_ID 反查厂站和馈线。"
            "没有 RMU，或最近 RMU 框内没有有效关联时，直接提示该图环网柜请手动关联；"
            "不会扫描整张图，也不分析拓扑。"
            "CBreaker / Disconnector / GroundDisconnector 默认使用 407 / 408 / 409，域号默认 40；"
            "Bus 的表号请按现场数据库配置。"
            "回写沿用现有安全副本与原子替换流程，不删除属性，既有回写规则保持不变。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        box = QGroupBox("配网主站设备数据库表与域配置（可编辑）")
        grid = QGridLayout(box)
        grid.setContentsMargins(14, 18, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("G 图元类型"), 0, 0)
        grid.addWidget(QLabel("表号（Table ID）"), 0, 1)
        grid.addWidget(QLabel("域号（Domain）"), 0, 2)
        grid.addWidget(QLabel("数据库表说明"), 0, 3)

        saved = self.config.get("master_station_rules", {}) or {}
        self.table_spins = {}
        self.domain_spins = {}
        self.table_labels = {}
        for row, (tag, default) in enumerate(DEFAULT_MASTER_STATION_RULES.items(), 1):
            values = dict(default)
            values.update(saved.get(tag, {}) or {})
            grid.addWidget(QLabel(tag), row, 0)

            table_spin = NoWheelSpinBox()
            table_spin.setRange(0, 999999)
            table_spin.setValue(int(values.get("table_id", 0) or 0))
            table_spin.setMinimumHeight(34)
            domain_spin = NoWheelSpinBox()
            domain_spin.setRange(0, 999999)
            domain_spin.setValue(int(values.get("domain", 40) or 0))
            domain_spin.setMinimumHeight(34)
            table_label = QLabel(str(values.get("table_name", "") or "未配置"))

            grid.addWidget(table_spin, row, 1)
            grid.addWidget(domain_spin, row, 2)
            grid.addWidget(table_label, row, 3)
            self.table_spins[tag] = table_spin
            self.domain_spins[tag] = domain_spin
            self.table_labels[tag] = table_label

        note = QLabel(
            "识别对象：Bus、CBreaker、GroundDisconnector；同时支持 SQL 中明确给出的 "
            "Disconnector。Bus 表号为 0 时只报告已识别，不执行数据库关联或回写。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        grid.addWidget(note, len(DEFAULT_MASTER_STATION_RULES) + 1, 0, 1, 4)

        reset = QPushButton("恢复主站设备默认配置")
        reset.setMinimumHeight(34)
        reset.clicked.connect(self.restore_defaults)
        grid.addWidget(reset, len(DEFAULT_MASTER_STATION_RULES) + 2, 0, 1, 4)
        root.addWidget(box)

    def restore_defaults(self):
        for tag, rule in DEFAULT_MASTER_STATION_RULES.items():
            self.table_spins[tag].setValue(int(rule.get("table_id", 0)))
            self.domain_spins[tag].setValue(int(rule.get("domain", 40)))

    def collect_settings(self):
        rules = {}
        for tag in DEFAULT_MASTER_STATION_RULES:
            default = DEFAULT_MASTER_STATION_RULES[tag]
            rules[tag] = {
                "table_id": int(self.table_spins[tag].value()),
                "domain": int(self.domain_spins[tag].value()),
                "table_name": str(default.get("table_name", "") or ""),
                "description": str(default.get("description", "") or ""),
            }
        return {
            "master_station_rules": rules,
            "element_catalog": self.config.get("element_catalog", {}),
        }
