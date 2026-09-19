from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from dmm.application.modules.pole_switch import (
    POLE_SWITCH_DEVREF_KEYWORDS,
    POLE_SWITCH_DOMAIN,
    POLE_SWITCH_TABLE_ID,
)


class NoWheelComboBox(QComboBox):
    """Prevent page scrolling from changing the selected filter."""

    def wheelEvent(self, event):
        event.ignore()


class PoleSwitchSettingsWidget(QGroupBox):
    """Business rules and hard name filters for pole switches."""

    def __init__(self, config):
        super().__init__("柱上开关识别与关联")
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(9)

        intro = QLabel(
            "柱上开关只识别 CBreakerDis。设备型号只根据图元管理中对对应图元文件的 LBS、SEC、AR 分类标记判断，"
            "不再从 devref 或文件名猜测类型；设备名称在当前模块识别出的设备范围内，直接取整张 G 图中距离最近的 Text；"
            "不会使用 key_name 或 p_NameString 作为设备名称，也不会用它们代替 devref 判断型号。"
            "下方名称格式、颜色和背景选项是 Text 的强制筛选条件，积攒现场默认使用其他颜色。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        preference_box = QGroupBox("设备名称筛选条件（强制过滤）")
        preference_layout = QGridLayout(preference_box)
        preference_layout.addWidget(QLabel("名称格式"), 0, 0)
        self.format_combo = NoWheelComboBox()
        self.format_combo.addItem("纯数字", "NUMERIC")
        self.format_combo.addItem("数字和字母混合", "ALPHANUMERIC_SPACE")
        saved_format = str(
            config.get("pole_switch_name_format") or ""
        ).strip().upper()
        if not saved_format:
            saved_format = (
                "NUMERIC"
                if bool(config.get("pole_switch_name_numeric", False))
                else "ALPHANUMERIC_SPACE"
            )
        self.format_combo.setCurrentIndex(
            max(0, self.format_combo.findData(saved_format))
        )
        preference_layout.addWidget(self.format_combo, 0, 1, 1, 2)

        preference_layout.addWidget(QLabel("名称颜色"), 1, 0)
        self.color_combo = NoWheelComboBox()
        self.color_combo.addItem("白色", "WHITE")
        self.color_combo.addItem("其他颜色", "OTHER")
        saved_colors = config.get("pole_switch_name_colors", ["OTHER"]) or []
        saved_color = str(saved_colors[0] if isinstance(saved_colors, (list, tuple)) else saved_colors).strip().upper()
        if saved_color not in {"WHITE", "OTHER"}:
            saved_color = "OTHER"
        self.color_combo.setCurrentIndex(
            max(0, self.color_combo.findData(saved_color))
        )
        preference_layout.addWidget(self.color_combo, 1, 1, 1, 2)

        preference_layout.addWidget(QLabel("名称背景"), 2, 0)
        self.background_combo = NoWheelComboBox()
        self.background_combo.addItem("无背景", False)
        self.background_combo.addItem("有背景", True)
        self.background_combo.setCurrentIndex(
            1 if bool(config.get("pole_switch_name_has_background", False)) else 0
        )
        preference_layout.addWidget(self.background_combo, 2, 1, 1, 2)
        preference_note = QLabel(
            "只有同时满足名称格式、颜色和背景条件的 Text 才会参与匹配；"
            "筛选后没有候选时，设备保持未匹配。"
        )
        preference_note.setWordWrap(True)
        preference_note.setStyleSheet("color:#60756d;")
        preference_layout.addWidget(preference_note, 3, 0, 1, 7)
        layout.addWidget(preference_box)

        devrefs = QLabel(
            "图元管理分类标记（对应图元文件，包含任一标记即可）：\n"
            + "、".join(POLE_SWITCH_DEVREF_KEYWORDS)
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
            "名称识别先扫描整张 G 图的有效 Text，当前模块的每个设备独立取最近名称，"
            "Text 中的换行名称（例如 AUTO RECLOSER 101601）会作为一个完整名称保留，"
            "kV、A、V 等单位文字会排除；"
            "当前模块不分析 RMU、ConnectLine、node_area 或其他拓扑关系；"
            "每个已标记设备独立取距离最近的合规 Text，多个设备可以解析到同一个 Text。"
            "拓扑明细不输出到报告。"
        )
        topology.setWordWrap(True)
        topology.setStyleSheet("color:#60756d;")
        layout.addWidget(topology)

    def collect_settings(self):
        name_format = str(self.format_combo.currentData() or "ALPHANUMERIC_SPACE")
        numeric = name_format == "NUMERIC"
        has_background = bool(self.background_combo.currentData())
        return {
            "pole_switch_table_id": POLE_SWITCH_TABLE_ID,
            "pole_switch_domain": POLE_SWITCH_DOMAIN,
            "pole_switch_devref_keywords": list(POLE_SWITCH_DEVREF_KEYWORDS),
            "name_format": name_format,
            "name_numeric": numeric,
            "name_colors": [str(self.color_combo.currentData() or "WHITE")],
            "name_has_background": has_background,
            "pole_switch_name_numeric": numeric,
            "pole_switch_name_format": name_format,
            "pole_switch_name_colors": [str(self.color_combo.currentData() or "WHITE")],
            "pole_switch_name_has_background": has_background,
        }
