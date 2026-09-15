from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from dmm.application.modules.pole_switch import (
    POLE_SWITCH_DEVREFS,
    POLE_SWITCH_DOMAIN,
    POLE_SWITCH_TABLE_ID,
)


class PoleSwitchSettingsWidget(QGroupBox):
    """Read-only business rules for the standalone pole-switch module."""

    def __init__(self, config):
        super().__init__("柱上开关识别与关联")
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(9)

        intro = QLabel(
            "柱上开关仅识别环网柜外的 CBreakerDis。设备型号只根据 devref "
            "属性精确匹配四类模板，图上设备名称只取最近的 Text；"
            "不会使用 key_name 或 p_NameString 作为设备名称，也不会用它们代替 devref 判断型号。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        devrefs = QLabel(
            "目标 devref：\n"
            + "\n".join(
                f"{model}：{devref}"
                for devref, model in POLE_SWITCH_DEVREFS.items()
            )
        )
        devrefs.setWordWrap(True)
        devrefs.setStyleSheet(
            "background:#EAF8F2;border:1px solid #B9DACD;"
            "border-radius:6px;padding:8px;color:#006B52;"
        )
        layout.addWidget(devrefs)

        db_rule = QLabel(
            f"数据库链路：图上名称 → dms_combined_device（表 13501，先按 NAME 精确匹配，"
            f"未命中再按 CODE 精确匹配）→ 取 13501.ID → dms_cb_device（表 {POLE_SWITCH_TABLE_ID}，"
            f"WHERE combined_id=13501.ID）→ 使用 13502.ID 按 Domain={POLE_SWITCH_DOMAIN} 计算 KeyID。"
        )
        db_rule.setWordWrap(True)
        layout.addWidget(db_rule)

        topology = QLabel(
            "拓扑分析仅用于判断设备是否位于环网柜内部，并辅助设备识别与校验；"
            "程序解析 ConnectLine / node_area 连接关系，环网柜内部同类 CBreakerDis"
            "会被排除，不参与柱上开关模块。拓扑明细不输出到报告。"
        )
        topology.setWordWrap(True)
        topology.setStyleSheet("color:#60756d;")
        layout.addWidget(topology)

    def collect_settings(self):
        return {
            "pole_switch_table_id": POLE_SWITCH_TABLE_ID,
            "pole_switch_domain": POLE_SWITCH_DOMAIN,
            "pole_switch_devrefs": list(POLE_SWITCH_DEVREFS),
        }
