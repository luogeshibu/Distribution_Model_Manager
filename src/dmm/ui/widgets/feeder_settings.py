from __future__ import annotations

import sys
from pathlib import Path

from dmm.i18n import tr, translate_runtime_text

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QGridLayout, QSpinBox, QPushButton, QSizePolicy,
    QAbstractSpinBox, QComboBox, QCheckBox, QLineEdit, QMessageBox,
)


def _resource_dir():
    if getattr(sys, "frozen", False):
        return (
            Path(
                getattr(
                    sys,
                    "_MEIPASS",
                    Path(sys.executable).resolve().parent,
                )
            )
            / "dmm"
            / "resources"
        )
    return Path(__file__).resolve().parents[2] / "resources"


SPIN_UP_ICON = (_resource_dir() / "spin_up.png").as_posix()
SPIN_DOWN_ICON = (_resource_dir() / "spin_down.png").as_posix()


class NoWheelSpinBox(QSpinBox):
    """
    与 RMU 模块完全一致的数字输入框：
    - 深绿色上下调节按钮；
    - 支持直接输入；
    - 鼠标滚轮不误修改数值。
    """

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

    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    """禁止鼠标滚轮误切换选项，仍允许点击下拉和键盘操作。"""

    def wheelEvent(self, event):
        event.ignore()


class FeederSettingsWidget(QWidget):
    DEFAULT_FEEDER_TABLE_ID = 13500
    DEFAULT_SECTION_TABLE_ID = 13503
    DEFAULT_SECTION_DOMAIN = 1

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.language = str(config.get("language", "zh_CN") or "zh_CN")

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Maximum,
        )
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "馈线识别来源相互独立：可按 G 根节点 facID、文件名或人工输入确定本次目标馈线。"
            "人工输入为绝对目标，例如 ABH AH303；若输入不存在或不唯一则直接失败，不回退到 facID/文件名。"
            "文件名模式同时支持单文件和批量目录：批量时可只输入变电站名 ABH，也可留空自动从文件名识别；"
            "JED-NTH-ABH-03 会在 ABH 站内把末尾 03 唯一解析到 AH303，"
            "JED-NTH-ABH-AH303 则直接使用完整馈线号。目标必须在 13500 / dms_feeder_device 中唯一。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        root.addWidget(info)

        resolution_box = QGroupBox("馈线识别与数据库补齐")
        resolution_grid = QGridLayout(resolution_box)
        resolution_grid.setContentsMargins(14, 18, 14, 14)
        resolution_grid.setHorizontalSpacing(12)
        resolution_grid.setVerticalSpacing(10)

        resolution_grid.addWidget(QLabel("馈线识别方式"), 0, 0)
        self._facid_locked_value = ""
        self._facid_reverting = False
        self.feeder_resolution_mode = NoWheelComboBox()
        self.feeder_resolution_mode.addItem(
            "仅使用 G 根节点 facID（默认）",
            "FACID",
        )
        self.feeder_resolution_mode.addItem(
            "仅使用文件名",
            "FILENAME",
        )
        self.feeder_resolution_mode.addItem(
            "仅使用人工输入",
            "MANUAL",
        )
        saved_mode = str(
            config.get("feeder_resolution_mode", "FACID") or "FACID"
        ).upper()
        mode_index = self.feeder_resolution_mode.findData(saved_mode)
        self.feeder_resolution_mode.setCurrentIndex(
            mode_index if mode_index >= 0 else 0
        )
        self.feeder_resolution_mode.setMinimumHeight(36)
        self.feeder_resolution_mode.currentIndexChanged.connect(
            self._on_resolution_mode_changed
        )
        resolution_grid.addWidget(
            self.feeder_resolution_mode,
            0,
            1,
            1,
            2,
        )

        self.feeder_station_hint_label = QLabel("批量变电站名称（文件名模式，可选）")
        resolution_grid.addWidget(self.feeder_station_hint_label, 1, 0)
        self.feeder_station_hint = QLineEdit(
            str(config.get("feeder_station_hint", "") or "")
        )
        self.feeder_station_hint.setPlaceholderText(
            "例如：ABH；也支持 JED-NTH-ABH；留空则从每个文件名自动识别"
        )
        self.feeder_station_hint.setMinimumHeight(36)
        resolution_grid.addWidget(
            self.feeder_station_hint,
            1,
            1,
            1,
            2,
        )

        self.manual_feeder_name_label = QLabel("人工目标馈线（变电站 + 馈线）")
        resolution_grid.addWidget(self.manual_feeder_name_label, 2, 0)
        self.manual_feeder_name = QLineEdit(
            str(config.get("manual_feeder_name", "") or "")
        )
        self.manual_feeder_name.setPlaceholderText(
            "例如：ABH AH303 或 AJWD 43"
        )
        self.manual_feeder_name.setMinimumHeight(36)
        resolution_grid.addWidget(
            self.manual_feeder_name,
            2,
            1,
            1,
            2,
        )

        self.allow_feeder_override = QCheckBox(
            "允许覆盖现有 facID 和馈线段关联"
        )
        self.allow_feeder_override.setChecked(
            bool(config.get("allow_feeder_override", False))
        )
        self.allow_feeder_override.setToolTip(
            "仅在用户明确勾选后允许：当文件名/人工输入解析出的目标馈线与当前 G.facID 或 FeedLine 所属馈线不一致时，"
            "把安全输出副本的根 facID 和所选 FeedLine 重新关联到目标馈线。组合图仍禁止整图覆盖到单一馈线。"
        )
        resolution_grid.addWidget(
            self.allow_feeder_override,
            3,
            0,
            1,
            3,
        )

        self.facid_policy_notice = QLabel(
            "G.facID 仅表示当前关联。FACID / 文件名 / 人工输入三种来源互不强制；"
            "如所选目标与当前 facID 不同，只有启用“允许覆盖”后才会生成覆盖候选。"
        )
        self.facid_policy_notice.setWordWrap(True)
        self.facid_policy_notice.setStyleSheet(
            "background:#EEF5F8;color:#35515E;"
            "border:1px solid #C8D7DE;border-radius:6px;padding:7px 9px;"
        )
        resolution_grid.addWidget(
            self.facid_policy_notice,
            4,
            0,
            1,
            3,
        )

        resolution_grid.addWidget(QLabel("图纸类型确认"), 5, 0)
        self.feeder_drawing_mode = NoWheelComboBox()
        self.feeder_drawing_mode.addItem(
            "自动识别（默认，按 G 图拓扑）",
            "AUTO",
        )
        self.feeder_drawing_mode.addItem(
            "强制单馈线图（本次文件/目录）",
            "SINGLE",
        )
        self.feeder_drawing_mode.addItem(
            "强制组合图（本次文件/目录）",
            "MULTI",
        )
        saved_drawing_mode = str(
            config.get("feeder_drawing_mode", "AUTO") or "AUTO"
        ).upper()
        drawing_mode_index = self.feeder_drawing_mode.findData(
            saved_drawing_mode
        )
        self.feeder_drawing_mode.setCurrentIndex(
            drawing_mode_index if drawing_mode_index >= 0 else 0
        )
        self.feeder_drawing_mode.setMinimumHeight(36)
        self.feeder_drawing_mode.setToolTip(
            "AUTO 使用 G 文件电气拓扑自动判断。强制单馈线后，若馈线名称在"
            "13500 中唯一，可将该 FEEDER_ID 回写到整张 G 根 facID；"
            "强制组合图则禁止整图根 facID 绑定到单一馈线。目录模式下该选择"
            "应用于本次目录中的全部 G 文件。"
        )
        resolution_grid.addWidget(
            self.feeder_drawing_mode,
            5,
            1,
            1,
            2,
        )

        drawing_notice = QLabel(
            "安全边界：图纸类型只决定是否允许把整张 G 归属到一个馈线。"
            "单馈线图的馈线根 facID 关联不依赖 Breaker、Busbar、FeedLine "
            "等设备关联状态；组合图禁止整图写入单一 FEEDER_ID。"
        )
        drawing_notice.setWordWrap(True)
        drawing_notice.setStyleSheet(
            "background:#EEF5F8;color:#35515E;"
            "border:1px solid #C8D7DE;border-radius:6px;padding:7px 9px;"
        )
        resolution_grid.addWidget(drawing_notice, 6, 0, 1, 3)

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
        resolution_grid.addWidget(
            self.auto_create_missing_sections,
            7,
            0,
            1,
            3,
        )

        db_notice = QLabel(
            "数据库写入边界：仅在此选项启用且执行【模型关联】时，"
            "允许 INSERT 缺失的 DMS_SECTION_DEVICE。"
            "模型校验阶段不写数据库；已有馈线段绝不重复创建。"
        )
        db_notice.setWordWrap(True)
        db_notice.setStyleSheet(
            "background:#FFF7E6;color:#8A5A00;"
            "border:1px solid #F1D59B;border-radius:6px;padding:7px 9px;"
        )
        resolution_grid.addWidget(db_notice, 8, 0, 1, 3)
        resolution_grid.setColumnStretch(1, 1)
        self._sync_manual_enabled()
        root.addWidget(resolution_box)

        mapping = QGroupBox("馈线段数据库表与域配置")
        mapping.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        grid = QGridLayout(mapping)
        grid.setContentsMargins(14, 18, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 3)

        grid.addWidget(QLabel("用途"), 0, 0)
        grid.addWidget(QLabel("表号（Table ID）"), 0, 1)
        grid.addWidget(QLabel("域号（Domain）"), 0, 2)

        grid.addWidget(QLabel("馈线段 dms_section_device"), 1, 0)

        self.section_table = NoWheelSpinBox()
        self.section_table.setRange(1, 999999)
        self.section_table.setMinimumHeight(36)
        self.section_table.setValue(
            int(
                config.get(
                    "section_table_id",
                    self.DEFAULT_SECTION_TABLE_ID,
                )
            )
        )
        grid.addWidget(self.section_table, 1, 1)

        self.section_domain = NoWheelSpinBox()
        self.section_domain.setRange(0, 999999)
        self.section_domain.setMinimumHeight(36)
        self.section_domain.setValue(
            int(
                config.get(
                    "section_domain",
                    self.DEFAULT_SECTION_DOMAIN,
                )
            )
        )
        grid.addWidget(self.section_domain, 1, 2)

        restore = QPushButton("恢复馈线默认配置")
        restore.setMinimumHeight(36)
        restore.clicked.connect(self.restore_defaults)
        grid.addWidget(restore, 2, 0, 1, 3)

        root.addWidget(mapping)

    def _sync_manual_enabled(self):
        """Show only the controls that belong to the selected feeder source.

        v4.1.39 keeps the three feeder sources not only logically independent
        but visually independent as well. Hidden fields retain their last
        value for convenience when an operator switches back, but the feeder
        application layer reads only the selected source.
        """
        mode = str(self.feeder_resolution_mode.currentData() or "").upper()

        filename_mode = mode == "FILENAME"
        manual_mode = mode == "MANUAL"
        override_mode = filename_mode or manual_mode

        self.feeder_station_hint_label.setVisible(filename_mode)
        self.feeder_station_hint.setVisible(filename_mode)
        self.feeder_station_hint.setEnabled(filename_mode)

        self.manual_feeder_name_label.setVisible(manual_mode)
        self.manual_feeder_name.setVisible(manual_mode)
        self.manual_feeder_name.setEnabled(manual_mode)
        self.manual_feeder_name.setReadOnly(False)

        # FACID mode already uses the current G-root association as the target,
        # so an override toggle has no meaning there.  It is shown only when
        # file-name/manual resolution can intentionally choose a different
        # target feeder.
        self.allow_feeder_override.setVisible(override_mode)
        self.allow_feeder_override.setEnabled(override_mode)

    def _on_resolution_mode_changed(self, _index=None):
        # v4.1.39: feeder sources remain deliberately independent.  A populated
        # root facID is shown as the current association but never forces the
        # combo box back to FACID.
        self._sync_manual_enabled()

    def set_facid_lock(self, facid=None):
        # Kept as a backward-compatible UI hook used by MainWindow.  It no
        # longer locks anything; it only shows the current root facID so the
        # operator can decide whether an explicit override is required.
        value = str(facid or "").strip()
        self._facid_locked_value = value
        self.feeder_resolution_mode.setEnabled(True)
        self._sync_manual_enabled()
        lang = self.config.get("language", self.language)
        self.manual_feeder_name.setPlaceholderText(tr("例如：ABH AH303 或 AJWD 43", lang))
        self.feeder_station_hint.setPlaceholderText(
            tr("例如：ABH；也支持 JED-NTH-ABH；留空则从每个文件名自动识别", lang)
        )
        if value:
            self.facid_policy_notice.setText(
                translate_runtime_text(
                    f"当前 G.facID={value}。该值仅表示当前关联，不会强制改变本次馈线识别来源。"
                    "若文件名/人工输入解析出的目标馈线不同，只有明确勾选“允许覆盖现有 facID 和馈线段关联”后才允许覆盖。",
                    lang,
                )
            )
            self.facid_policy_notice.setStyleSheet(
                "background:#EEF5F8;color:#35515E;"
                "border:1px solid #C8D7DE;border-radius:6px;padding:7px 9px;"
            )
        else:
            self.facid_policy_notice.setText(
                tr(
                    "当前 G.facID 为空。FACID / 文件名 / 人工输入三种来源独立；"
                    "文件名模式支持单文件和批量目录，并对每个文件独立解析、独立数据库唯一校验。",
                    lang,
                )
            )
            self.facid_policy_notice.setStyleSheet(
                "background:#FFF7E6;color:#8A5A00;"
                "border:1px solid #F1D59B;border-radius:6px;padding:7px 9px;"
            )

    def restore_defaults(self):
        self.section_table.setValue(self.DEFAULT_SECTION_TABLE_ID)
        self.section_domain.setValue(self.DEFAULT_SECTION_DOMAIN)
        self.feeder_resolution_mode.setCurrentIndex(0)
        self.manual_feeder_name.clear()
        self.feeder_station_hint.clear()
        self.allow_feeder_override.setChecked(False)
        self.feeder_drawing_mode.setCurrentIndex(0)
        self.auto_create_missing_sections.setChecked(True)

    def collect_settings(self):
        # 馈线主表 13500 是程序内部固定业务表，不再作为用户配置项显示。
        return {
            "feeder_table_id": self.DEFAULT_FEEDER_TABLE_ID,
            "section_table_id": int(self.section_table.value()),
            "section_domain": int(self.section_domain.value()),
            "feeder_resolution_mode": str(
                self.feeder_resolution_mode.currentData() or "FACID"
            ),
            "manual_feeder_name": self.manual_feeder_name.text().strip(),
            "feeder_station_hint": self.feeder_station_hint.text().strip(),
            "allow_feeder_override": bool(self.allow_feeder_override.isChecked()),
            "feeder_drawing_mode": str(
                self.feeder_drawing_mode.currentData() or "AUTO"
            ).upper(),
            "auto_create_missing_sections": bool(
                self.auto_create_missing_sections.isChecked()
            ),
        }
