from __future__ import annotations

import sys
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QHBoxLayout, QSizePolicy, QLineEdit,
)

from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_RMU_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
)
from dmm.config.constants import (
    RMU_RELAY_SIGNAL_CODE,
    RMU_RELAY_SIGNAL_DOMAIN,
    RMU_RELAY_SIGNAL_TABLE_ID,
    RMU_CHANNEL_STATUS_TABLE_ID,
    RMU_CHANNEL_STATUS_DOMAIN,
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
            "开关设备名称固定使用环网柜内图上文字；麦加环网柜名称固定按“右侧 RIGHT → 下方 BOTTOM → 全局 GLOBAL 兜底”一对一匹配。"
            "所有候选使用矩形最小边缘距离且必须在 200 以内；已分配 Text 不再参与其它 RMU 计算，RMU 仍保留专用排除规则。"
            "设备命名规则固定使用图上文字，不再读取三类设备 XML 的 p_NameString："
            "CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。"
            "RMU 内 EFI 图元由【图元管理】分类标记 RMU_PWBH_EFI 识别：程序使用该标记对应的图元定义文件名，"
            "只在当前环网柜框内查找匹配实例；找到后仍按环网柜 ID 查询 13533 dms_relay_sig，"
            "仅 CODE=EFI INDICATOR 才参与关联，默认回写 value 域 keyid1（域号 40）。"
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
        rg.addWidget(QLabel("环网柜名称匹配规则"), 0, 0)

        self.name_detection_mode = NoWheelComboBox()
        self.name_detection_mode.addItem("固定：RIGHT → BOTTOM → GLOBAL", "FIXED")
        saved_mode = str(
            config.get(
                "rmu_name_detection_mode",
                DEFAULT_RMU_NAME_DETECTION_MODE,
            )
            or DEFAULT_RMU_NAME_DETECTION_MODE
        ).strip().upper()
        mode_index = self.name_detection_mode.findData(saved_mode)
        self.name_detection_mode.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self.name_detection_mode.setEnabled(False)
        rg.addWidget(self.name_detection_mode, 0, 1)

        labels = {"top": "上方", "right": "右侧", "left": "左侧", "bottom": "下方"}
        self.pos_checks = {}
        saved_pos = config.get("rmu_name_positions", DEFAULT_RMU_NAME_POSITIONS)
        if not any(bool(saved_pos.get(pos, False)) for pos in labels):
            saved_pos = DEFAULT_RMU_NAME_POSITIONS
        for idx, pos in enumerate(("top", "right", "left", "bottom")):
            cb = QCheckBox(labels[pos])
            cb.setChecked(pos in ("top", "right"))
            cb.setEnabled(False)
            cb.setVisible(False)
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

        rg.addWidget(QLabel("环网柜名称来源"), 5, 0)
        fixed_source = QLabel("RIGHT → BOTTOM → GLOBAL fallback（固定）")
        fixed_source.setStyleSheet(
            "font-weight:700;color:#006B52;"
            "background:#EAF8F2;border:1px solid #B9DACD;"
            "border-radius:6px;padding:7px 9px;"
        )
        rg.addWidget(fixed_source, 5, 1)

        self.force_feeder_correction_check = QCheckBox(
            "强制修正已关联 RMU 所属馈线（修改 13501.FEEDER_ID）"
        )
        self.force_feeder_correction_check.setChecked(
            bool(config.get("force_rmu_feeder_correction", False))
        )
        self.force_feeder_correction_check.setToolTip(
            "默认关闭。仅当图形拓扑唯一确认 RMU 所属馈线，且现有 KeyID 已证明当前 13501 就是该 RMU，"
            "但其 FEEDER_ID 与拓扑结果不一致时，执行模型关联可安全更新 dms_combined_device.FEEDER_ID。"
        )
        self.force_feeder_correction_check.setStyleSheet(
            "QCheckBox{font-weight:700;color:#8A4B00;padding:6px 2px;}"
        )
        rg.addWidget(self.force_feeder_correction_check, 6, 0, 1, 2)

        note = QLabel(
            "麦加名称固定按 RIGHT → BOTTOM → GLOBAL fallback 匹配：名称 Text 中心必须位于所有已识别 RMU 外框之外；先使用右侧合法 Text，右侧没有再使用下方合法 Text，最后才在距离 300 G 单位以内按最近距离做全局兜底；同一个 Text ID 只能分配一次。"
            "开关名称不再读取 XML p_NameString。CBreakerDis 仅使用环网柜内"
            "图上文字；接地刀闸逻辑名称=配对开关名+D；BusDis 固定为 BUS。"
            "EFI 图元由图元管理分类 RMU_PWBH_EFI 对应的文件名识别；识别成功后仍按固定 CODE=EFI INDICATOR 关联。"
            "图上名称无法唯一识别，或与数据库 CODE 校验失败时，会明确告警对应环网柜。"
            "每个环网柜只使用一个名称；数据库中必须存在且只能存在一条同名环网柜记录，"
            "否则禁止自动关联。以上规则仅适用于环网柜，不改变馈线识别逻辑。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        rg.addWidget(note, 7, 0, 1, 2)
        rg.setRowStretch(8, 1)

        # Core database rules are intentionally read-only in the Makkah UI.
        # Existing persisted values are preserved for compatibility, but the
        # model page explains the business workflow instead of exposing raw
        # table/domain knobs to field operators.
        saved_rules = config.get("device_rules", {}) or {}
        self._fixed_device_rules = {}
        for tag, default in DEFAULT_DEVICE_RULES.items():
            vals = dict(default)
            vals.update(saved_rules.get(tag, {}) or {})
            self._fixed_device_rules[tag] = {
                "table_id": int(vals.get("table_id", default["table_id"])),
                "domain": int(vals.get("domain", default["domain"])),
            }
        relay_saved = saved_rules.get("pwbh", {}) or {}
        self._fixed_relay_rule = {
            "table_id": int(relay_saved.get("table_id", RMU_RELAY_SIGNAL_TABLE_ID)),
            "domain": int(relay_saved.get("domain", RMU_RELAY_SIGNAL_DOMAIN)),
        }

        rules_box = QGroupBox("RMU 自动关联逻辑（只读说明）")
        rules_box.setMinimumWidth(590)
        rules_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        rules_box.setMinimumHeight(355)
        rules = QVBoxLayout(rules_box)
        rules.setContentsMargins(7, 10, 7, 7)
        rules.setSpacing(3)

        active_rules = self._fixed_device_rules

        def workflow_card(title: str, text: str, accent: bool = False):
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
            rules.addWidget(label)

        workflow_card(
            "固定数据库规则",
            f"CBreakerDis → 表 {active_rules['CBreakerDis']['table_id']} / Domain {active_rules['CBreakerDis']['domain']}；"
            f"ZhaiWaiJieDiDaoZha → 表 {active_rules['ZhaiWaiJieDiDaoZha']['table_id']} / Domain {active_rules['ZhaiWaiJieDiDaoZha']['domain']}；"
            f"BusDis → 表 {active_rules['BusDis']['table_id']} / Domain {active_rules['BusDis']['domain']}；"
            f"PWBH EFI → 表 {self._fixed_relay_rule['table_id']} / Domain {self._fixed_relay_rule['domain']}；"
            f"Channel Status → 表 {RMU_CHANNEL_STATUS_TABLE_ID} / Domain {RMU_CHANNEL_STATUS_DOMAIN}。",
            True,
        )
        workflow_card(
            "步骤 1｜识别环网柜框",
            "扫描 G 图矩形框；框内必须同时存在 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha。存在嵌套时只保留满足条件的最内层框，避免把外部大框当成一个 RMU。",
        )
        workflow_card(
            "步骤 2｜确定环网柜名称",
            "扫描整张 G 图合法 Text。环网柜名称只从 RMU 框外寻找：Text 中心落在任意已识别 RMU 框内时直接排除，RIGHT / BOTTOM / GLOBAL 均不得使用。RMU 框与 Text 框统一使用矩形最小边缘距离；距离超过 300 G 单位直接排除。麦加名称按 RIGHT → BOTTOM → GLOBAL fallback 依次选择；纯小数、电话样式长数字、包含 '-' 的字符串和排除列表文字不参与计算。按 RIGHT → BOTTOM → GLOBAL 三阶段全图一对一分配：RIGHT 阶段不受其他 RMU 的全局最近距离抢占；仅最终 GLOBAL 兜底按最近距离分配。同一 Text ID 最终只使用一次。",
        )
        workflow_card(
            "步骤 3｜确认数据库 RMU",
            "先复用【环网柜馈线拓扑分析】唯一确定 RMU 所属馈线，并将主网馈线解析为 13500 FEEDER_ID。未关联 RMU 只允许在该 FEEDER_ID 下按 NAME 精确匹配 13501；本馈线下 0 条或多条都禁止自动关联，绝不跨馈线兜底。",
        )
        workflow_card(
            "步骤 4｜识别柜内设备",
            "CBreakerDis 使用柜内图上文字作为逻辑名称；接地刀闸逻辑名称=配对开关名+D；BusDis 固定逻辑名称为 BUS。设备必须位于当前 RMU 框内，并在该 RMU 的 COMBINED_ID 范围内查询对应数据库记录。",
        )
        workflow_card(
            "步骤 5｜识别 PWBH / EFI",
            f"先从图元管理读取分类 RMU_PWBH_EFI 对应的图元文件名，只在当前 RMU 框内找该实例；找到后按 dms_relay_sig.CODE={RMU_RELAY_SIGNAL_CODE} 和当前 RMU 归属继续原有匹配。",
        )
        workflow_card(
            "步骤 6｜关联 Channel Status 状态图元",
            f"在已唯一确定的当前 RMU 框内识别 Status 图元，devref 必须包含 channel_status.zt.icn.g；同一 RMU 内只能有 1 个，多个则阻断。以 RMU_ID 查询 dms_terminal_info.COMBINED_ID，并按 TERMINAL_ID 联查 dms_channel_info，排除 CHAN_NAME 以 DR 结尾的记录；数据库候选必须唯一。Expected KeyID = dms_channel_info.ID + (40 << 32)，并校验表 {RMU_CHANNEL_STATUS_TABLE_ID} / Domain {RMU_CHANNEL_STATUS_DOMAIN}。执行回写 Status：app=6600000、voltype=-1、p_ReportType=1、state=39、keyid=Expected KeyID；历史 app1/voltype1/p_ReportType1/state1/keyid1 残留字段同时清理。",
        )
        workflow_card(
            "步骤 7｜校验并回写",
            "所有目标数据库记录必须唯一，Expected KeyID 必须能反解回正确表号、设备 ID 和 Domain。若现有 KeyID 已证明当前 13501 就是该 RMU，但 13501.FEEDER_ID 与拓扑馈线不一致，默认只报告；只有勾选【强制修正已关联 RMU 所属馈线】才允许用带旧值条件的 UPDATE 修正 FEEDER_ID。执行关联仍只修改 Workspace/g_output 安全副本，原始 G 文件不修改。",
        )
        top_row.addWidget(recog, 4)
        top_row.addWidget(rules_box, 7)
        root.addLayout(top_row)

    def restore_defaults(self):
        # Only recognition controls remain editable on the RMU page.
        for pos, value in DEFAULT_RMU_NAME_POSITIONS.items():
            self.pos_checks[pos].setChecked(bool(value))
        default_index = self.name_detection_mode.findData(
            DEFAULT_RMU_NAME_DETECTION_MODE
        )
        self.name_detection_mode.setCurrentIndex(max(default_index, 0))
        self.name_exclusions_edit.setText(", ".join(DEFAULT_RMU_NAME_EXCLUSIONS))
        self.force_feeder_correction_check.setChecked(False)

    def collect_settings(self):
        positions = {
            key: checkbox.isChecked()
            for key, checkbox in self.pos_checks.items()
        }
        detection_mode = "FIXED"
        if not any(positions.values()):
            raise ValueError(tr("请至少选择一个环网柜名称位置。", self.config.get("language", "zh_CN")))
        saved_rules = {}
        runtime_rules = {}
        for tag, default in DEFAULT_DEVICE_RULES.items():
            fixed = self._fixed_device_rules[tag]
            table_id = int(fixed["table_id"])
            domain = int(fixed["domain"])
            saved_rules[tag] = {"table_id": table_id, "domain": domain}
            runtime_rules[tag] = {
                "table_id": table_id,
                "domain": domain,
                "match_mode": default["match_mode"],
                "description": default["description"],
            }

        relay_table_id = int(self._fixed_relay_rule["table_id"])
        relay_domain = int(self._fixed_relay_rule["domain"])
        saved_rules["pwbh"] = {
            "table_id": relay_table_id,
            "domain": relay_domain,
        }
        runtime_rules["pwbh"] = {
            "table_id": relay_table_id,
            "domain": relay_domain,
            "match_mode": "FIXED_GFILE_EFI_INDICATOR",
            "description": (
                "图元分类 RMU_PWBH_EFI -> "
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
            "rmu_name_positions_custom": positions != DEFAULT_RMU_NAME_POSITIONS,
            "rmu_name_detection_mode": detection_mode,
            "rmu_name_exclusions": exclusion_values,
            "breaker_name_source": "GRAPHICAL_TEXT",
            "force_rmu_feeder_correction": self.force_feeder_correction_check.isChecked(),
            "device_rules": saved_rules,
            "_runtime_rules": runtime_rules,
        }
