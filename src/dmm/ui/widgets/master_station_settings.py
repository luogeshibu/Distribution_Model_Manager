from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES


def _logic_label(title: str, text: str, accent: bool = False) -> QLabel:
    label = QLabel(f"<b>{title}：</b> {text}")
    label.setWordWrap(True)
    # Keep each read-only logic card at its natural content height.  Without
    # this, a taller module stack may stretch QLabel vertically and create a
    # large blank panel around one or two lines of text.
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    # Keep each step card visually compact.  The surrounding workspace can be
    # much taller than the text, so cap the card itself instead of allowing
    # Qt to distribute spare vertical space into the QLabel background.
    label.setMinimumHeight(0)
    label.setMaximumHeight(64)
    label.setTextFormat(label.textFormat())
    # All steps are peer-level read-only instructions. Keep the same neutral
    # background/border for every card instead of visually emphasizing step 1.
    label.setStyleSheet(
        "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;"
        "border-radius:6px;padding:4px 7px;line-height:1.22;"
    )
    return label


class MasterStationSettingsWidget(QWidget):
    """Read-only explanation of the fixed master-station association workflow."""

    def __init__(self, config):
        super().__init__()
        self.config = config or {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        info = QLabel(
            "配网主站设备模块不提供表号、域号等工程定义的编辑入口。"
            "页面只说明程序实际执行的识别、数据库定位、安全校验和 G 文件回写流程；"
            "运行时仍使用吉达项目已经固定的业务规则。"
        )
        info.setWordWrap(True)
        # The banner is explanatory text only; never let it absorb the
        # remaining vertical space of the workspace.
        info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        box = QGroupBox("配网主站设备自动关联完整逻辑（只读说明）")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        layout.addWidget(_logic_label(
            "1. 识别哪些设备",
            "只处理 G 文件中的 CBreaker、Disconnector、GroundDisconnector；Bus 不属于本模块，"
            "不会进入校验、报告或回写。程序不使用这些图元的可见 CODE/NAME 去猜数据库对象。",
            True,
        ))
        layout.addWidget(_logic_label(
            "2. 怎样确定厂站 / 馈线 / 间隔",
            "主站设备不再通过附近 RMU、RMU 内已有 KeyID 或 13501.FEEDER_ID 反查馈线。"
            "图级馈线只按 G 文件名 → 405/substation.NAME → 13500/dms_feeder_device(ST_ID+NAME) 唯一确定；"
            "普通 NN 生成 AH3NN，AGNN 生成 AG4NN。然后保持原有主站 Bay 逻辑：使用该厂站和馈线名称/代码在 406/Bay 中定位唯一 BAY_ID。"
            "文件名、405、13500 或 406 任一步不唯一/不存在都直接阻断。",
        ))
        layout.addWidget(_logic_label(
            "3. 怎样从数据库选目标设备",
            "数据库目标只按已确定的 BAY_ID 读取：CBreaker 使用固定表 407 / Domain 40；"
            "Disconnector 使用固定表 408 / Domain 30；GroundDisconnector 使用固定表 409 / Domain 30。"
            "单个 CBreaker 或 GroundDisconnector 要求 BAY_ID 下数据库目标唯一。"
            "同一 BAY_ID 内有多个 Disconnector 时，G 图先按 Bus 侧左右顺序排列，数据库记录按 NAME 末尾 _1、_2、_T 排列；"
            "数量或标记不一致时拒绝猜测。",
        ))
        layout.addWidget(_logic_label(
            "4. 关联前安全校验",
            "目标数据库记录必须能唯一确定，设备 ID、BV_ID 必须有效；"
            "程序按目标设备 ID 和固定 Domain 计算 Expected KeyID，并再次反解校验表号、设备 ID 和 Domain。"
            "当前 KeyID 已正确则保持 PASS；未关联则进入 UNLINKED；已有旧 KeyID 但目标已唯一确定时进入 RELINK。",
        ))
        layout.addWidget(_logic_label(
            "5. 真正执行时回写哪些字段",
            "只修改 Workspace 安全副本，不修改原始 G 文件。CBreaker 回写 app=100000、voltype=数据库 BV_ID、"
            "p_ReportType=1、state=41、keyid=Expected KeyID；Disconnector 和 GroundDisconnector 回写"
            " app=100000、voltype=数据库 BV_ID、p_ReportType=1、state=31、keyid=Expected KeyID。"
            "执行前会重新检查数据库和目标有效性。",
        ))

        root.addWidget(box)

    def restore_defaults(self):
        """Kept for compatibility; fixed definitions have nothing to restore."""
        return None

    def collect_settings(self):
        # Keep the exact fixed engineering definitions used by v4.1.85.  The
        # UI is now prose-only, but association behavior is intentionally
        # unchanged.
        rules = {}
        for tag, default in DEFAULT_MASTER_STATION_RULES.items():
            rules[tag] = {
                "table_id": int(default["table_id"]),
                "domain": int(default["domain"]),
                "table_name": str(default.get("table_name", "") or ""),
                "description": str(default.get("description", "") or ""),
            }
        return {
            "master_station_rules": rules,
            "element_catalog": self.config.get("element_catalog", {}),
        }
