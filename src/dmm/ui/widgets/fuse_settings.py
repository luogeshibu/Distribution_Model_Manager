from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QVBoxLayout

from dmm.application.modules.fuse import FUSE_DOMAIN, FUSE_TABLE_ID


def _logic_label(title: str, text: str, accent: bool = False) -> QLabel:
    label = QLabel(f"<b>{title}：</b> {text}")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    # Keep each step card visually compact.  The surrounding workspace can be
    # much taller than the text, so cap the card itself instead of allowing
    # Qt to distribute spare vertical space into the QLabel background.
    label.setMinimumHeight(0)
    label.setMaximumHeight(64)
    label.setStyleSheet(
        # All steps are peer-level read-only instructions. Use one neutral
        # background/border for every card; step 1 is not a special status.
        "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;"
        "border-radius:6px;padding:4px 7px;line-height:1.22;"
    )
    return label


class FuseSettingsWidget(QGroupBox):
    """Fixed Jeddah rules for Fuse recognition and association."""

    def __init__(self, config):
        super().__init__("熔断器自动关联完整逻辑（只读说明）")
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        layout.addWidget(_logic_label(
            "1. 识别哪些设备",
            "只识别【图元管理】中分类标记为 FUSE 的图元；不会根据 devref 文件名、key_name 或 p_NameString 猜测熔断器类型。",
            True,
        ))
        layout.addWidget(_logic_label(
            "2. 先找最近柱上变压器",
            "每个 FUSE 只提名几何位置最近的 TRANSFORMER_OH。一个柱上变压器最多只能分给一个 FUSE；"
            "多个 FUSE 同时指向同一变压器时，距离更近的 FUSE 获得，其他 FUSE 只统计、不关联，也不会再改找第二近变压器。",
        ))
        layout.addWidget(_logic_label(
            "3. 怎样得到熔断器名称",
            "成功独占柱上变压器后，完全复用柱上变压器模块的名称规则：全图纯数字、白色、无背景 Text，"
            "TOP → RIGHT → GLOBAL，设备矩形框到 Text 矩形框按最小边缘距离计算，最大 300，Text 一对一；不再使用中心点距离。"
            "柱上变压器图上名称保留，即使数据库后续不唯一也不会把已经识别出的图形名称清空。"
            "熔断器业务名称固定为 FUSE + 柱上变压器名称，例如 971765 → FUSE971765。",
        ))
        layout.addWidget(_logic_label(
            "4. 数据库和馈线校验",
            f"图级馈线沿用统一规则：唯一来源为严格 JED 文件名 → 405.NAME → 普通 NN 生成 AH3NN / AGNN 生成 AG4NN → 13500.ST_ID+NAME；图中设备不参与馈线判定。"
            f"用派生 NAME + 图级 FEEDER_ID 查询 {FUSE_TABLE_ID} / dms_disconnector_device，必须唯一；"
            "目标记录 FEEDER_ID 必须等于图级馈线，ID/BV_ID 必须有效。"
            f"再按 Domain={FUSE_DOMAIN} 计算 Expected KeyID 并反解校验。无法确定图级馈线或数据库不唯一时禁止关联。",
        ))
        layout.addWidget(_logic_label(
            "5. 真正执行时回写哪些字段",
            "只修改 Workspace 安全副本，不修改原始 G 文件。回写 app=6500000、voltype=目标 13513.BV_ID、"
            "p_ReportType=1、state=41、keyid=Expected KeyID。当前 KeyID 已正确则保持不变；旧 KeyID 可在目标唯一且安全校验通过后重关联。",
        ))

    def collect_settings(self):
        return {
            "fuse_table_id": FUSE_TABLE_ID,
            "fuse_domain": FUSE_DOMAIN,
        }
