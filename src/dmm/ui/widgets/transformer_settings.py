from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QVBoxLayout

from dmm.application.modules.transformer import (
    TRANSFORMER_DOMAIN,
    TRANSFORMER_TABLE_ID,
)


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


class TransformerSettingsWidget(QGroupBox):
    """Rules for pole-transformer recognition and association."""

    def __init__(self, config):
        super().__init__("柱上变压器自动关联完整逻辑（只读说明）")
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        layout.addWidget(_logic_label(
            "1. 识别哪些设备",
            "设备类型按两级优先级识别：① devref 精确指向 Transformer_OH.pb.icn.g 时直接认定为柱上变压器，"
            "不依赖【图元管理】分类；② 未命中该标准图元时，再检查图元管理中的 TRANSFORMER_OH 分类标记作为兜底。"
            "其它未命中标准图元且没有 TRANSFORMER_OH 分类的图元不进入柱上变压器模型。",
            True,
        ))
        layout.addWidget(_logic_label(
            "2. 怎样找柱上变压器名称",
            "全图扫描名称候选 Text，候选必须同时满足：纯数字、白色（含默认白色）、无背景。"
            "每台变压器严格按 上方 TOP → 右方 RIGHT → 全局 GLOBAL 的优先级选择；同一级别取最近。"
            "距离统一按设备矩形框与 Text 矩形框的最小边缘距离计算，方向按两个矩形的相对位置判断，最大距离 300；不再使用中心点距离。"
            "Text 在全部已识别柱上变压器之间一对一分配；多个变压器争用同一 Text 时，物理距离更近的设备获得，失败设备继续尝试下一候选。",
        ))
        layout.addWidget(_logic_label(
            "3. 数据库和馈线校验",
            f"图形名称确定后查询 {TRANSFORMER_TABLE_ID} / dms_tr_device，NAME 必须唯一。"
            "同时使用统一的图级馈线判定（唯一来源为严格 JED 文件名 → 405.NAME → 普通 NN 生成 AH3NN / AGNN 生成 AG4NN → 13500.ST_ID+NAME），目标 13505.FEEDER_ID 必须与当前图级 FEEDER_ID 一致。"
            "目标 13505.ID 有效后按 Domain=1 计算 Expected KeyID，并再次反解验证表号、设备 ID 和 Domain。",
        ))
        layout.addWidget(_logic_label(
            "4. 当前模型如何判断",
            "柱上变压器模型使用两组并行 KeyID 槽位，不依赖 XML 元素名称。只有 keyid1 和 keyid2 都等于当前 Expected KeyID 才视为 PASS；"
            "两者为空时属于可关联 UNLINKED；存在旧值但目标数据库设备已经唯一确定且校验通过时属于可重关联 RELINK。",
        ))
        layout.addWidget(_logic_label(
            "5. 真正执行时回写哪些字段",
            "只写 Workspace 安全副本，不修改原始 G 文件。两组槽位同时回写："
            "app1/app2=6500000、voltype1/voltype2=0、p_ReportType1/p_ReportType2=1、"
            "state1/state2=18、keyid1/keyid2=Expected KeyID。执行前重新检查数据库事实和输入快照。",
        ))

    def collect_settings(self):
        return {
            "transformer_table_id": TRANSFORMER_TABLE_ID,
            "transformer_domain": TRANSFORMER_DOMAIN,
        }
