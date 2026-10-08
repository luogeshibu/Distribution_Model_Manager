from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QVBoxLayout

from dmm.application.modules.pole_switch import (
    POLE_SWITCH_DEVREF_KEYWORDS,
    POLE_SWITCH_DOMAIN,
    POLE_SWITCH_TABLE_ID,
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


class PoleSwitchSettingsWidget(QGroupBox):
    """Business rules for pole-switch recognition and association."""

    def __init__(self, config):
        super().__init__("柱上开关自动关联完整逻辑（只读说明）")
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        layout.addWidget(_logic_label(
            "1. 识别哪些设备",
            "只认【图元管理】中的 LBS、SEC、AR 分类标记。只要某个 G 图元的 devref 对应到这些分类标记之一，"
            "该图元就是本模块的柱上开关目标；不限制它在 G 文件里使用 CBreakerDis、CBreaker 或其它 XML 元素。"
            "不会根据 XML 元素名、key_name、p_NameString 或文件名字符串猜测设备类型。",
            True,
        ))
        layout.addWidget(_logic_label(
            "2. 怎样找图上名称",
            "从整张 G 图扫描 Text。名称 Text 必须显式设置颜色并且不能是白色；颜色深浅不限。"
            "设备矩形框到 Text 矩形框统一按最小边缘距离计算，最大距离 200；不再使用中心点距离。方向优先级固定为 上方 TOP → 右侧 RIGHT → 全局 GLOBAL；"
            "同一优先级内取距离最近，Text 全局一对一分配。明显单位/注释文字会被排除。"
            "图上原始名称始终原样保留。",
        ))
        layout.addWidget(_logic_label(
            "3. 查询数据库前怎样处理名称",
            "只有真正查询数据库前才处理查询名称：普通名称仍删除点号、横杠和空白，例如 SEC-2385、SEC 2385、SEC.2385 都按 SEC2385 查询；但若分类为 AR/LBS/SEC，且图上名称本身严格符合“设备族+数字-数字”的复合格式（如 LBS96527-21240、LBS33513-97376），横杠属于业务名称，直接按原名查询。"
            "这个标准化只用于数据库查询，不会修改报告中的图上名称，也不会修改 G 文件 Text。",
        ))
        layout.addWidget(_logic_label(
            "4. 数据库关联链路",
            f"先用标准化后的名称查询 13501 / dms_combined_device：先按 NAME 精确匹配，未命中再按 CODE 精确匹配；"
            f"取得唯一 13501.ID 后，再查询 {POLE_SWITCH_TABLE_ID} / dms_cb_device，要求 combined_id=13501.ID。"
            "图级馈线唯一按 JED 文件名判定：普通 NN 形式生成 AH3NN，新增 AGNN 形式生成 AG4NN；均先用 405.NAME 精确找站，再用 13500 的 ST_ID+NAME 精确确认。环网柜、柱上开关、柱上变压器均不参与馈线判定。13501 与 13502 的 FEEDER_ID 必须一致，"
            "并且必须等于图级 FEEDER_ID。任何一步不唯一或馈线不一致都禁止自动关联。",
        ))
        layout.addWidget(_logic_label(
            "5. 真正执行时回写哪些字段",
            f"目标设备使用 13502.ID，Domain 固定为 {POLE_SWITCH_DOMAIN} 计算 Expected KeyID，并再次反解校验。"
            "真正执行时只修改 Workspace 安全副本，回写 app=6500000、voltype=目标 dms_cb_device.BV_ID、"
            "p_ReportType=1、state=41、keyid=Expected KeyID。当前 KeyID 正确则不重复写；旧关联可在目标唯一且校验通过时安全重关联。",
        ))
        layout.addWidget(_logic_label(
            "6. 模块边界",
            "柱上开关模块只处理图元管理中明确分类为 LBS/SEC/AR 的图元，XML 元素类型不作为过滤条件。"
            "不会为了给柱上开关找名字而锁定或修改 RMU、Bus、柱上变压器、熔断器等其它设备。"
            "批量关联调用本模块时，也复用完全相同的独立模块规则。",
        ))

    def collect_settings(self):
        return {
            "pole_switch_table_id": POLE_SWITCH_TABLE_ID,
            "pole_switch_domain": POLE_SWITCH_DOMAIN,
            "pole_switch_devref_keywords": list(POLE_SWITCH_DEVREF_KEYWORDS),
        }
