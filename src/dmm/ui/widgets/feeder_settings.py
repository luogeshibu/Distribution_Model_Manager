from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGroupBox,
    QSizePolicy,
    QCheckBox,
)


def _logic_label(title: str, text: str, accent: bool = False) -> QLabel:
    label = QLabel(f"<b>{title}：</b> {text}")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    # Match the Jeddah v4.1.96 logic-card geometry exactly.
    label.setMinimumHeight(0)
    label.setMaximumHeight(64)
    label.setStyleSheet(
        ("background:#EAF8F2;color:#17372E;border:1px solid #B9DACD;" if accent else
         "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;")
        + "border-radius:6px;padding:4px 7px;line-height:1.22;"
    )
    return label


class FeederSettingsWidget(QWidget):
    DEFAULT_FEEDER_TABLE_ID = 13500
    DEFAULT_SECTION_TABLE_ID = 13503
    DEFAULT_SECTION_DOMAIN = 1

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        box = QGroupBox("麦加馈线自动关联逻辑（只读说明）")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(box)
        # Same display geometry as Jeddah v4.1.96.
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        def step(title: str, text: str, accent: bool = False):
            layout.addWidget(_logic_label(title, text, accent))

        layout.addWidget(_logic_label(
            "1. 扫描当前环网图全部主网馈线",
            "扫描所有最内层且框内含 CBreaker 的主网 Bay 框；在 Bay 框附近按现有标题规则寻找最近的无背景合法馈线 Text（颜色不限），例如 GVCM-AH304、SHM1-AH341_X。后缀 _X/_Y 属于馈线编号本身，必须保留；每个标题只允许归属一个 Bay。",
            True,
        ))
        layout.addWidget(_logic_label(
            "2. 唯一确认变电站和馈线",
            "把标题拆成变电站和馈线号。先在 405/substation 按 NAME 唯一确认变电站，再用该 ST_ID 到 13500/dms_feeder_device 按 NAME/CODE 唯一确认馈线并取得 FEEDER_ID；本图所有确认成功的馈线都会保留。",
        ))
        layout.addWidget(_logic_label(
            "3. 先识别每条 FeedLine 的所属馈线",
            "复用【图形工作区 → 馈线段所属馈线分析】的同一套拓扑：从主网 CBreaker 出发，沿 link/node_area 与严格几何补链传播；遇红色 NOP 对应 Y*/Q* 开关时只停止该支路。只有唯一主网馈线可达的 FeedLine 才允许继续。",
        ))
        layout.addWidget(_logic_label(
            "4. 按所属馈线校验已有 13503",
            "逐条解析 FeedLine 当前 KeyID。只有当前 13503.FEEDER_ID 与该 FeedLine 拓扑识别出的所属馈线一致，才判定正确；如果只是 Domain 不为 1，保持原 13503.ID，仅修正 Domain。",
        ))
        layout.addWidget(_logic_label(
            "5. 只复用自己馈线下的空闲段",
            "每条 FeedLine 只从自己所属 FEEDER_ID 下查询并分配未占用的 13503/dms_section_device；不再把多条馈线的空闲 13503 混成统一资源池，也不会跨馈线随机分配。",
        ))
        layout.addWidget(_logic_label(
            "6. 不足时在各自馈线下创建 13503",
            f"某条所属馈线现有空闲 13503 不足时，只在该 FEEDER_ID 下创建实际缺少数量，并按 Domain {self.DEFAULT_SECTION_DOMAIN} 完成关联；不同馈线分别建库。原始 G 不修改，只写 Workspace/g_output 安全副本。",
        ))
        layout.addWidget(_logic_label(
            "7. 冲突/未确定不猜测",
            "若 FeedLine 拓扑结果为 CONFLICT 或 UNRESOLVED，或图形馈线无法唯一映射到 13500，则该 FeedLine 阻断自动关联/建库。HTML/CSV 同时列出拓扑所属馈线、目标 FEEDER_ID、最终 13503 和处理结果。",
        ))

        self.auto_create_missing_sections = QCheckBox("麦加固定规则：按 FeedLine 拓扑所属馈线分别复用/创建 13503，不跨馈线分配")
        self.auto_create_missing_sections.setChecked(True)
        self.auto_create_missing_sections.setEnabled(False)
        layout.addWidget(self.auto_create_missing_sections)
        root.addWidget(box)

    def _sync_manual_enabled(self):
        return None

    def _on_resolution_mode_changed(self, _index=None):
        return None

    def set_facid_lock(self, facid=None):
        return None

    def restore_defaults(self):
        self.auto_create_missing_sections.setChecked(True)

    def collect_settings(self):
        return {
            "feeder_table_id": self.DEFAULT_FEEDER_TABLE_ID,
            "section_table_id": self.DEFAULT_SECTION_TABLE_ID,
            "section_domain": self.DEFAULT_SECTION_DOMAIN,
            "feeder_resolution_mode": "MAKKAH_RING_FIRST_CONFIRMED_FEEDER",
            "manual_feeder_name": "",
            "feeder_station_hint": "",
            "allow_feeder_override": True,
            "feeder_drawing_mode": "MULTI",
            "auto_create_missing_sections": True,
        }
