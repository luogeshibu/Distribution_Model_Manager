from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from dmm.application.modules.transformer import (
    TRANSFORMER_DOMAIN,
    TRANSFORMER_TABLE_ID,
)


class NoWheelComboBox(QComboBox):
    """Prevent page scrolling from changing the selected filter."""

    def wheelEvent(self, event):
        event.ignore()


class TransformerSettingsWidget(QGroupBox):
    """Rules and hard name filters for the pole-transformer model."""

    def __init__(self, config):
        super().__init__("柱上变压器识别与关联")
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(9)

        intro = QLabel(
            "柱上变压器只识别图元管理中标记为 Transformer_OH 的图元；被标记的图元直接视为变压器，"
            "不依赖现场图元文件名或 TransformerDis 名称。名称在柱上变压器范围内，直接取整张 G 图中距离最近的 Text。"
            "每个设备独立解析最近名称。支持纯数字名称，例如 97803；"
            "不读取 DText、key_name 或 XML p_NameString。下面的名称格式、颜色和背景选项"
            "是 Text 的强制筛选条件，颜色分为白色和其他颜色两类，默认白色。"
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
            config.get("transformer_name_format") or ""
        ).strip().upper()
        if not saved_format:
            saved_format = (
                "NUMERIC"
                if bool(config.get("transformer_name_numeric", True))
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
        saved_colors = config.get("transformer_name_colors", ["WHITE"]) or []
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
            1 if bool(config.get("transformer_name_has_background", False)) else 0
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

        topology = QLabel(
            "模型关联不分析 RMU、ConnectLine、node_area 或其他拓扑关系。"
            "每个已标记变压器独立取距离最近的合规 Text，多个设备可以解析到同一个 Text。"
            "馈线固定优先使用 G 根节点 facID 精确查询 13500 / dms_feeder_device；"
            "facID 查不到时仅使用唯一 facName 兜底。"
        )
        topology.setWordWrap(True)
        topology.setStyleSheet(
            "background:#EAF8F2;border:1px solid #B9DACD;"
            "border-radius:6px;padding:8px;color:#006B52;"
        )
        layout.addWidget(topology)

        db_rule = QLabel(
            f"数据库链路：Text 名称 + 馈线 ID → dms_tr_device（表 {TRANSFORMER_TABLE_ID}，"
            f"NAME 和 FEEDER_ID 精确匹配）→ 取 13505.ID，按 Domain={TRANSFORMER_DOMAIN} 计算 KeyID。"
        )
        db_rule.setWordWrap(True)
        layout.addWidget(db_rule)

        writeback = QLabel(
            "TransformerDis 回写两组并行字段：app1/app2、voltype1/voltype2、"
            "p_ReportType1/p_ReportType2、state1/state2、keyid1/keyid2。"
            "原始 G 文件不修改，只写入 Workspace 安全副本。"
        )
        writeback.setWordWrap(True)
        writeback.setStyleSheet("color:#60756d;")
        layout.addWidget(writeback)

    def collect_settings(self):
        name_format = str(self.format_combo.currentData() or "NUMERIC")
        numeric = name_format == "NUMERIC"
        has_background = bool(self.background_combo.currentData())
        return {
            "transformer_table_id": TRANSFORMER_TABLE_ID,
            "transformer_domain": TRANSFORMER_DOMAIN,
            "name_format": name_format,
            "name_numeric": numeric,
            "name_colors": [str(self.color_combo.currentData() or "WHITE")],
            "name_has_background": has_background,
            "transformer_name_numeric": numeric,
            "transformer_name_format": name_format,
            "transformer_name_colors": [str(self.color_combo.currentData() or "WHITE")],
            "transformer_name_has_background": has_background,
        }
