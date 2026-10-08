from __future__ import annotations

import sys
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QHBoxLayout, QSizePolicy, QLineEdit, QMessageBox,
)

from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
    DEFAULT_RMU_PROTECTION_SCOPE,
)
from dmm.config.constants import (
    RMU_RELAY_SIGNAL_CODE,
    RMU_RELAY_SIGNAL_DOMAIN,
    RMU_RELAY_SIGNAL_TABLE_ID,
)
from dmm.i18n import tr


def _resource_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "dmm" / "resources"
    return Path(__file__).resolve().parents[2] / "resources"

SPIN_UP_ICON = (_resource_dir() / "spin_up.png").as_posix()
SPIN_DOWN_ICON = (_resource_dir() / "spin_down.png").as_posix()


class NoWheelSpinBox(QSpinBox):
    """原生 SpinBox：支持输入和上下按钮，但鼠标滚轮不修改数值。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.setKeyboardTracking(False)
        self.setWrapping(False)
        self.setSingleStep(1)
        self.setAccelerated(False)
        self.setStyleSheet(f"""
            QSpinBox {{
                padding-right: 30px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 28px;
                background: #006B52;
                border-left: 1px solid #005640;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: #00966E;
            }}
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
                background: #004D3A;
            }}
            QSpinBox::up-arrow {{
                image: url("{SPIN_UP_ICON}");
                width: 14px;
                height: 10px;
            }}
            QSpinBox::down-arrow {{
                image: url("{SPIN_DOWN_ICON}");
                width: 14px;
                height: 10px;
            }}
        """)
        self.setFocusPolicy(self.focusPolicy())

    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    """禁止滚轮误切换选项，仍允许点击下拉框。"""

    def wheelEvent(self, event):
        event.ignore()


class RmuSettingsWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "RMU 环网柜只有在矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 时才识别。"
            "环网柜名称始终以 RMU 矩形框为基准，只允许识别完整位于矩形框外、且在矩形框上方的 Text；右侧、左侧、下方和全局兜底全部禁用。上方找不到名称即判定环网柜名称识别失败。"
            "设备命名规则固定使用图上文字，不再读取三类设备 XML 的 p_NameString："
            "CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。"
            "RMU 内保护/EFI 图元只认图元管理中的 RMU_PWBH_EFI 分类标记：可同时标记多个图元文件，默认按环网柜 ID 查询 13533 dms_relay_sig，"
            "仅 CODE=EFI INDICATOR 才参与关联，默认回写 value 域 keyid1（域号 40）；设备表号和域号属于固定工程规则，不允许用户修改。"
            "单线图中的环网柜关联会先按 G 文件名唯一确定图级馈线，并只在该 FEEDER_ID 下选择同名环网柜；其它馈线上的同名记录不会阻断。合成图和环网图保持原 RMU 逻辑；同一 G 图内环网柜名称重复时仍按原规则阻断。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        # ------------------------------------------------------------------
        # 第一行：RMU 识别 + 数据库表/域配置并排展示。
        # 避免纵向堆叠导致小分辨率下控件被压扁。
        # ------------------------------------------------------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        recog = QGroupBox("RMU 环网柜识别")
        recog.setMinimumWidth(330)
        recog.setMinimumHeight(355)
        rg = QGridLayout(recog)
        rg.setContentsMargins(14, 18, 14, 14)
        rg.setHorizontalSpacing(18)
        rg.setVerticalSpacing(10)
        rg.addWidget(QLabel("环网柜名称位置"), 0, 0)

        self.name_detection_mode = NoWheelComboBox()
        self.name_detection_mode.addItem("按指定方向", "FIXED")
        saved_mode = str(
            config.get(
                "rmu_name_detection_mode",
                DEFAULT_RMU_NAME_DETECTION_MODE,
            )
            or DEFAULT_RMU_NAME_DETECTION_MODE
        ).strip().upper()
        mode_index = self.name_detection_mode.findData(saved_mode)
        self.name_detection_mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        rg.addWidget(self.name_detection_mode, 0, 1)

        labels = {"top": "上方（固定）", "right": "右侧（禁用）", "left": "左侧（禁用）", "bottom": "下方（禁用）"}
        self.pos_checks = {}
        for idx, pos in enumerate(("top", "right", "left", "bottom")):
            cb = QCheckBox(labels[pos])
            cb.setChecked(pos == "top")
            cb.setEnabled(False)
            rg.addWidget(cb, 1 + idx // 2, idx % 2)
            self.pos_checks[pos] = cb

        rg.addWidget(QLabel("环网柜名称排除字符串"), 3, 0, 1, 2)
        self.name_exclusions_edit = QLineEdit()
        saved_exclusions = config.get("rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS)
        if isinstance(saved_exclusions, str):
            saved_exclusions_text = saved_exclusions
        else:
            saved_exclusions_text = ", ".join(str(x) for x in saved_exclusions or [])
        self.name_exclusions_edit.setText(saved_exclusions_text)
        self.name_exclusions_edit.setPlaceholderText("例如：N.O.P, NOP, SFI, DAS/OK")
        rg.addWidget(self.name_exclusions_edit, 4, 0, 1, 2)

        rg.addWidget(QLabel("保护 / EFI 关联范围"), 5, 0)
        self.protection_scope = NoWheelComboBox()
        self.protection_scope.addItem("所有环网柜都关联保护 / EFI", "ALL")
        self.protection_scope.addItem("仅 SMART 智能环网柜关联保护 / EFI", "SMART_ONLY")
        saved_scope = str(
            config.get("rmu_protection_scope", DEFAULT_RMU_PROTECTION_SCOPE)
            or DEFAULT_RMU_PROTECTION_SCOPE
        ).strip().upper()
        scope_index = self.protection_scope.findData(saved_scope)
        self.protection_scope.setCurrentIndex(scope_index if scope_index >= 0 else 0)
        rg.addWidget(self.protection_scope, 5, 1)

        rg.addWidget(QLabel("环网柜名称来源"), 6, 0)
        fixed_source = QLabel("框外图上文字：仅上方（固定）")
        fixed_source.setStyleSheet(
            "font-weight:700;color:#006B52;"
            "background:#EAF8F2;border:1px solid #B9DACD;"
            "border-radius:6px;padding:7px 9px;"
        )
        rg.addWidget(fixed_source, 6, 1)

        note = QLabel(
            "吉达现场环网柜名称始终以 RMU 矩形框为几何基准，只允许使用完整位于矩形框外、且在矩形框上方的 Text。右侧、左侧、下方和全局兜底全部禁用；上方找不到有效 Text 就直接判定环网柜名称识别失败。框内 Text 永远不能作为环网柜名称。"
            "开关名称不再读取 XML p_NameString。CBreakerDis 仅使用环网柜内"
            "图上文字；接地刀闸逻辑名称=配对开关名+D；BusDis 固定为 BUS。"
            "保护/EFI 不绑定具体图元文件名；凡图元管理分类标记为 RMU_PWBH_EFI 的 pwbh 图元都按固定 CODE=EFI INDICATOR 关联；数据库表号和域号为固定工程规则。"
            "当选择“仅 SMART”时，NORMAL 环网柜不会新增保护/EFI关联；如果已有 EFI KeyID，执行关联时会自动清除关联值，"
            "保留原属性键，回到现场未关联 EFI 的属性状态。"
            "图上名称无法唯一识别，或与数据库 CODE 校验失败时，会明确告警对应环网柜。"
            "单线图必须先由 G 文件名唯一确定图级馈线，并校验目标环网柜属于该 FEEDER_ID；数据库其它馈线上的同名环网柜会被忽略。当前馈线下没有同名环网柜，或当前馈线下仍有多条同名记录时禁止关联；facID 不作为环网柜名称匹配条件。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        rg.addWidget(note, 7, 0, 1, 2)
        rg.setRowStretch(8, 1)

        logic_box = QGroupBox("RMU 自动关联完整逻辑（只读说明）")
        logic_box.setMinimumWidth(590)
        # 右侧逻辑说明按内容自然高度显示，不再被左侧识别区/工作区高度拉伸。
        # 即使外层布局还有剩余高度，也只留在卡片列表底部，步骤之间保持紧凑。
        logic_box.setMinimumHeight(0)
        logic_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        logic = QVBoxLayout(logic_box)
        logic.setContentsMargins(7, 10, 7, 7)
        logic.setSpacing(3)
        logic.setAlignment(Qt.AlignTop)

        def add_logic(title, text, accent=False):
            label = QLabel(f"<b>{title}：</b> {text}")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            # Keep the explanatory step card at a compact visual height; do not
            # let spare workspace height turn the label background into a large box.
            label.setMinimumHeight(0)
            label.setMaximumHeight(64)
            # All five logic steps have the same information level. Keep their
            # background, text and border styling identical.
            label.setStyleSheet(
                "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;"
                "border-radius:6px;padding:4px 7px;line-height:1.22;"
            )
            logic.addWidget(label)

        add_logic(
            "1. 环网柜如何识别",
            "只有矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 才识别为 RMU。"
            "RMU 名称只从完整位于矩形框外、且在矩形框上方的 Text 获取；不允许右侧、左侧、下方或全局兜底。上方没有有效名称时直接 FAIL；框内 Text 永不作为柜名。"
            "同一 G 图内 RMU 名称重复时，重复名称对应的环网柜全部阻断自动关联。",
            True,
        )
        add_logic(
            "2. 柜内设备如何命名",
            "CBreakerDis 只使用柜内图上文字，不读取 XML p_NameString；"
            "ZhaiWaiJieDiDaoZha 的逻辑名称=配对开关名称+D；BusDis 的逻辑名称固定为 BUS。"
            "保护/EFI 只认【图元管理】分类标记 RMU_PWBH_EFI，并按固定 CODE=EFI INDICATOR 处理。"
            "保护范围仍由左侧“保护 / EFI 关联范围”选项控制。",
        )
        add_logic(
            "3. 数据库怎样校验",
            "先用 RMU 名称定位 13501 环网柜；单线图先按图级 FEEDER_ID 过滤同名记录，只有当前馈线内唯一记录才继续。柜内 CBreakerDis 对应固定 13502 / Domain 40，"
            "接地刀闸对应 13514 / Domain 40，BusDis 对应 13506 / Domain 1；"
            "这些设备按数据库 CODE 与图上逻辑名称校验，并要求目标设备属于当前 RMU。"
            "RMU_PWBH_EFI 使用 13533 / dms_relay_sig，固定 CODE=EFI INDICATOR、Domain 40。"
            "数据库 0 条、多条、CODE 不一致、设备归属不一致、BV_ID/Expected KeyID 无效时均禁止自动关联。",
        )
        add_logic(
            "4. 当前 KeyID 如何判断",
            "当前 KeyID 只用于判断 PASS / UNLINKED / RELINK / RMU_RELINK。"
            "当前关联已正确则保持不动；旧设备 ID、旧 KeyID、旧表号/域号已经过期，但数据库当前目标唯一且属于本 RMU 时，"
            "允许安全重关联。单线图还必须满足目标 RMU 的 FEEDER_ID 与图级馈线一致；facID 不作为 RMU 名称匹配条件。",
        )
        add_logic(
            "5. 真正执行时回写哪些字段",
            "CBreakerDis / ZhaiWaiJieDiDaoZha：app=6500000、voltype=数据库 BV_ID、p_ReportType=1、state=41、keyid=Expected KeyID。"
            "BusDis：app=6500000、voltype=数据库 BV_ID、p_ReportType=1、state=15、keyid=Expected KeyID。"
            "RMU_PWBH_EFI：app/app1=6500000、voltype1=0、p_ReportType1=1、state1=41、keyid1=Expected KeyID。"
            "选择“仅 SMART”时，NORMAL RMU 已有关联的 EFI 按既有策略清回未关联属性状态。"
            "所有修改只写 Workspace 安全副本，原始 G 文件不修改。",
        )

        # 把任何多余的纵向空间压到列表底部，绝不平均摊到五个说明卡片之间。
        logic.addStretch(1)

        top_row.addWidget(recog, 4)
        top_row.addWidget(logic_box, 7, alignment=Qt.AlignTop)
        root.addLayout(top_row)

    def restore_defaults(self):
        for pos, value in DEFAULT_NAME_POSITIONS.items():
            self.pos_checks[pos].setChecked(bool(value))
        default_index = self.name_detection_mode.findData(
            DEFAULT_RMU_NAME_DETECTION_MODE
        )
        self.name_detection_mode.setCurrentIndex(max(default_index, 0))
        self.name_exclusions_edit.setText(", ".join(DEFAULT_RMU_NAME_EXCLUSIONS))
        scope_index = self.protection_scope.findData(DEFAULT_RMU_PROTECTION_SCOPE)
        self.protection_scope.setCurrentIndex(max(scope_index, 0))

    def collect_settings(self):
        positions = {
            "top": True,
            "right": True,
            "left": False,
            "bottom": False,
        }
        detection_mode = "FIXED"

        saved_rules = {}
        runtime_rules = {}

        # RMU database mappings are fixed engineering rules.  Ignore any stale
        # user/workspace values from older versions and always persist/use the
        # bundled definitions so UI settings cannot alter association behavior.
        for tag, default in DEFAULT_DEVICE_RULES.items():
            table_id = int(default["table_id"])
            domain = int(default["domain"])

            saved_rules[tag] = {
                "table_id": table_id,
                "domain": domain,
            }

            runtime_rules[tag] = {
                "table_id": table_id,
                "domain": domain,
                "match_mode": default["match_mode"],
                "description": default["description"],
            }

        relay_table_id = int(RMU_RELAY_SIGNAL_TABLE_ID)
        relay_domain = int(RMU_RELAY_SIGNAL_DOMAIN)
        saved_rules["pwbh"] = {
            "table_id": relay_table_id,
            "domain": relay_domain,
        }
        runtime_rules["pwbh"] = {
            "table_id": relay_table_id,
            "domain": relay_domain,
            "match_mode": "ELEMENT_CLASSIFICATION_EFI_INDICATOR",
            "description": (
                "element classification RMU_PWBH_EFI -> "
                "dms_relay_sig.CODE=EFI INDICATOR"
            ),
            "fixed_code": RMU_RELAY_SIGNAL_CODE,
            "voltype_required": False,
        }

        exclusion_text = self.name_exclusions_edit.text()
        exclusion_values = [
            item.strip()
            for item in re.split(r"[,;\n\r]+", exclusion_text)
            if item.strip()
        ]

        return {
            "rmu_name_positions": positions,
            "rmu_name_detection_mode": detection_mode,
            "rmu_name_exclusions": exclusion_values,
            "rmu_protection_scope": str(self.protection_scope.currentData() or DEFAULT_RMU_PROTECTION_SCOPE),
            "breaker_name_source": "GRAPHICAL_TEXT",
            "device_rules": saved_rules,
            "_runtime_rules": runtime_rules,
        }
