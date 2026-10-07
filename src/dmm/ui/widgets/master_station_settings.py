from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES


class MasterStationSettingsWidget(QWidget):
    """Read-only Makkah master-station association workflow."""

    def __init__(self, config):
        super().__init__()
        self.config = config or {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        saved = self.config.get("master_station_rules", {}) or {}
        self._fixed_rules = {}
        for tag, default in DEFAULT_MASTER_STATION_RULES.items():
            values = dict(default)
            values.update(saved.get(tag, {}) or {})
            if tag == "Bus":
                # v4.1.74 fixed rule; ignore stale table_id=0 saved by older versions.
                values.update({"table_id": 410, "domain": 40, "table_name": "busbarsection"})
            self._fixed_rules[tag] = {
                "table_id": int(values.get("table_id", default.get("table_id", 0)) or 0),
                "domain": int(values.get("domain", default.get("domain", 40)) or 0),
                "table_name": str(default.get("table_name", "") or ""),
                "description": str(default.get("description", "") or ""),
            }

        box = QGroupBox("配网主站设备自动关联逻辑（只读说明）")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        rules = self._fixed_rules
        def step(title: str, text: str, accent: bool = False):
            label = QLabel(f"<b>{title}：</b> {text}")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            label.setMinimumHeight(0)
            label.setMaximumHeight(64)
            label.setStyleSheet((
                "background:#EAF8F2;color:#17372E;border:1px solid #B9DACD;"
                if accent else
                "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;"
            ) + "border-radius:6px;padding:4px 7px;line-height:1.22;")
            layout.addWidget(label)

        step("固定数据库规则",
             f"CBreaker → 表 {rules['CBreaker']['table_id']} / Domain {rules['CBreaker']['domain']}；"
             f"Disconnector → 表 {rules['Disconnector']['table_id']} / Domain {rules['Disconnector']['domain']}；"
             f"GroundDisconnector → 表 {rules['GroundDisconnector']['table_id']} / Domain {rules['GroundDisconnector']['domain']}；"
             f"Bus → 表 {rules['Bus']['table_id']} / Domain {rules['Bus']['domain']}。", True)
        step("步骤 1｜识别主网 Bay 框",
             "扫描 G 图矩形框，只处理包含 CBreaker 的主网框；当前自动关联要求框内 CBreaker 唯一，否则无法唯一确定 Bay，直接阻断该框自动关联。")
        step("步骤 2｜识别馈线标题",
             "在该框附近查找无背景且格式合法的 Text，文字颜色不参与判断。设备框与 Text 框统一使用矩形最小边缘距离，不再计算中心点距离；标题格式类似 MNA4-12、ARF2-07、SHM1-AH341_X，所有 Bay 框与合法标题做全局最近一对一分配；同一个 Text ID 一旦被某个 Bay 使用，后续 Bay 不再重复使用。")
        step("步骤 3｜解析变电站和 Bay",
             "从标题拆出变电站名称与馈线/Bay 编号，例如 SHM1-AH341_X → 变电站 SHM1、Bay/馈线 AH341_X；先唯一匹配 substation，再在该变电站范围内唯一确定 Bay，并得到 BAY_ID。")
        step("步骤 4｜确认 CBreaker",
             "按 BAY_ID 查询 breaker；主网框内的 CBreaker 必须能唯一落到该 Bay 的数据库 breaker，其 ST_ID/BAY_ID 必须与标题解析结果一致。")
        step("步骤 5｜关联框内主网设备",
             "Bus 使用 410/busbarsection、Domain 40，但只检查已确认变电站 ST_ID，不检查 BAY_ID；同站 410 记录作为候选池，已有正确 Bus 关联优先保留，其余 Bus 任意一对一取未使用记录。CBreaker、Disconnector、GroundDisconnector 继续按唯一 BAY_ID 查询；Disconnector/GroundDisconnector 多记录时才允许用图上 key_name CODE 进一步消歧，仍不唯一就停止。")
        step("步骤 6｜真正执行时回写哪些字段",
             "只修改 Workspace/g_output 安全副本，不修改原始 G 文件。"
             "CBreaker 回写 app=100000、voltype=数据库 BV_ID、p_ReportType=1、state=41、keyid=Expected KeyID；"
             "Disconnector 和 GroundDisconnector 回写 app=100000、voltype=数据库 BV_ID、p_ReportType=1、state=31、keyid=Expected KeyID；"
             "Bus 回写 app=100000、voltype=数据库 BV_ID、p_ReportType=1、state=10、keyid=Expected KeyID。"
             "执行前会重新检查数据库和目标有效性；目标与校验阶段不一致时禁止写回。")
        step("边界说明",
             "主网设备关联以“主网框 + 无背景合法馈线标题（颜色不限） + 唯一 BAY_ID”为权威依据，不依赖全图拓扑，也不会用最近 RMU 猜 Bay。")
        root.addWidget(box)

    def restore_defaults(self):
        self._fixed_rules = {
            tag: {
                "table_id": int(rule.get("table_id", 0) or 0),
                "domain": int(rule.get("domain", 40) or 0),
                "table_name": str(rule.get("table_name", "") or ""),
                "description": str(rule.get("description", "") or ""),
            }
            for tag, rule in DEFAULT_MASTER_STATION_RULES.items()
        }

    def collect_settings(self):
        return {
            "master_station_rules": {tag: dict(rule) for tag, rule in self._fixed_rules.items()},
            "element_catalog": self.config.get("element_catalog", {}),
        }
