from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QSizePolicy,
    QCheckBox,
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


class FeederSettingsWidget(QWidget):
    DEFAULT_FEEDER_TABLE_ID = 13500
    DEFAULT_SECTION_TABLE_ID = 13503
    DEFAULT_SECTION_DOMAIN = 1

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.language = str(config.get("language", "zh_CN") or "zh_CN")

        # Preserve v4.1.85 runtime configuration values exactly.  The database
        # definition editor is removed from the UI only; business logic and
        # existing workspace settings remain unchanged.
        self._section_table_id = int(
            config.get("section_table_id", self.DEFAULT_SECTION_TABLE_ID)
        )
        self._section_domain = int(
            config.get("section_domain", self.DEFAULT_SECTION_DOMAIN)
        )

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "馈线模块不再展示可编辑的表号/域号表格。页面直接说明当前程序的完整自动识别、"
            "数据库补齐和 G 文件回写流程；原有馈线业务逻辑保持不变。"
        )
        info.setWordWrap(True)
        # Keep this one-line explanatory banner at its natural height.  QLabel's
        # default vertical policy is Preferred, so the parent workspace may give
        # it all remaining height and create a large empty panel.
        info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        logic_box = QGroupBox("馈线自动关联完整逻辑（只读说明）")
        logic_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        logic = QVBoxLayout(logic_box)
        logic.setContentsMargins(7, 10, 7, 7)
        logic.setSpacing(3)

        logic.addWidget(_logic_label(
            "1. 怎样判定当前图属于哪条馈线",
            "吉达馈线唯一以 G 文件名为标准，不再通过环网柜、柱上开关、柱上变压器或其它设备反推馈线。"
            "文件名支持两种严格格式：普通 JED-<三位区域代码>-<站名>-<两位馈线号>.sln.pic.g，"
            "例如 JED-NTH-ABH-03 会生成 AH303；新增 JED-<三位区域代码>-<站名>-AG<两位馈线号>.sln.pic.g，"
            "例如 JED-XXX-MDN-AG06 会取站名 MDN，并把 AG06 转成 AG406。"
            "程序先按站名精确查询 405/substation.NAME 得到唯一站 ID，再按 13500/dms_feeder_device.ST_ID=站ID 且 NAME=目标馈线名精确唯一确认。"
            "文件名不合规则直接报错要求修改；13500 中找不到目标馈线时直接提示馈线不存在并要求检查该图馈线是否已创建。"
            "所有其它设备只允许关联到这个 FEEDER_ID 下。",
            True,
        ))
        logic.addWidget(_logic_label(
            "2. 怎样处理 G 文件中的馈线段",
            "只处理 FeedLine。已经正确关联到当前馈线 13503 / dms_section_device 的 FeedLine 保持原关联，"
            "不会因为图形顺序变化而重新编号。未关联或旧关联失效的 FeedLine，先避开已经被正确 G 关联占用的数据库馈线段，"
            "再按现有数据库可用段分配；只有真实数量不足时才计划创建缺失馈线段。"
            "已经明确关联到错误馈线/错误对象的情况不会静默覆盖，而是报告阻断或要求人工确认。",
        ))
        logic.addWidget(_logic_label(
            "3. 数据库补齐边界",
            f"当前工程使用馈线主表 13500，馈线段表 {self._section_table_id}，馈线段 Domain={self._section_domain}。"
            "模型校验阶段只读数据库；只有勾选下面的“自动创建数据库中缺失的馈线段”，并真正执行模型关联时，"
            "才允许 INSERT 确实缺失的 DMS_SECTION_DEVICE。不会 UPDATE、DELETE 已有数据库记录，也不会重复创建已有馈线段。",
        ))
        logic.addWidget(_logic_label(
            "4. KeyID 与安全校验",
            "目标馈线段必须属于已判定的图级 FEEDER_ID；目标设备 ID、BV_ID 必须有效。"
            f"程序按馈线段设备 ID 和 Domain={self._section_domain} 计算 Expected KeyID，并再次反解校验表号、设备 ID 和 Domain。"
            "当前正确关联保持不动；旧 KeyID 失效但当前数据库目标能够安全确定时，按既有规则进入重关联。",
        ))
        logic.addWidget(_logic_label(
            "5. 真正执行时写什么",
            "解析出的图级 FEEDER_ID 会按现有规则写入 G 根节点 facID（仅在该根关联被判定需要回写时）。"
            "FeedLine 写回 app=6500000、p_ReportType=1、state=20、voltype=目标 dms_section_device.BV_ID、"
            "keyid=Expected KeyID。所有 G 修改只发生在 Workspace 安全副本；本地原始文件和 SSH 服务器文件都不会修改。",
        ))

        root.addWidget(logic_box)

        options = QGroupBox("馈线数据库补齐选项")
        # This card contains only one checkbox + one short notice.  Keep it at
        # its natural height so a taller module stack cannot stretch the
        # warning label into a large empty panel.
        options.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        option_layout = QVBoxLayout(options)
        option_layout.setContentsMargins(8, 12, 8, 8)
        option_layout.setSpacing(8)

        self.auto_create_missing_sections = QCheckBox(
            "执行模型关联时自动创建数据库中缺失的馈线段"
        )
        self.auto_create_missing_sections.setChecked(
            bool(config.get("auto_create_missing_sections", True))
        )
        self.auto_create_missing_sections.setToolTip(
            "仅 INSERT DMS_SECTION_DEVICE 中确实不存在的记录；"
            "不会 UPDATE / DELETE 已有记录。创建成功后会重新查询数据库，"
            "再计算 Expected KeyID 并修改本地 G 输出副本。"
        )
        option_layout.addWidget(self.auto_create_missing_sections)

        db_notice = QLabel(
            "数据库写入边界：模型校验永远不写数据库；真正执行关联时也只允许按该选项 INSERT 缺失馈线段。"
            "其它模型模块仍保持各自既有数据库只读/回写边界。"
        )
        db_notice.setWordWrap(True)
        db_notice.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        db_notice.setStyleSheet(
            "background:#FFF7E6;color:#8A5A00;"
            "border:1px solid #F1D59B;border-radius:6px;padding:7px 9px;"
        )
        option_layout.addWidget(db_notice)
        root.addWidget(options)

    def set_facid_lock(self, facid=None):
        """Backward-compatible hook used by MainWindow.

        G-root facID does not alter or lock feeder resolution settings.
        """
        return None

    def restore_defaults(self):
        self._section_table_id = self.DEFAULT_SECTION_TABLE_ID
        self._section_domain = self.DEFAULT_SECTION_DOMAIN
        self.auto_create_missing_sections.setChecked(True)

    def collect_settings(self):
        # Preserve the exact settings contract used in v4.1.85.  Only the UI
        # presentation changed from an editable table to a read-only workflow
        # explanation.
        return {
            "feeder_table_id": self.DEFAULT_FEEDER_TABLE_ID,
            "section_table_id": int(self._section_table_id),
            "section_domain": int(self._section_domain),
            "feeder_resolution_mode": "GRAPHICAL_AUTO",
            "manual_feeder_name": "",
            "feeder_station_hint": "",
            "allow_feeder_override": False,
            "feeder_drawing_mode": "SINGLE",
            "auto_create_missing_sections": bool(
                self.auto_create_missing_sections.isChecked()
            ),
        }
