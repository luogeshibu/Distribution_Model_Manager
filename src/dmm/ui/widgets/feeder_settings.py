from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QGridLayout, QSpinBox, QPushButton, QSizePolicy,
    QAbstractSpinBox, QComboBox, QCheckBox,
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
            "馈线模型必须在环网柜、柱上开关、柱上变压器等设备模型完成关联后使用。"
            "程序会按馈线段与附近已关联设备的距离自动确定归属，并据此查询馈线段数据库记录；"
            "不再要求用户填写馈线名、变电站名或馈线识别方式。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        root.addWidget(info)

        resolution_box = QGroupBox("馈线模型自动关联规则")
        resolution_grid = QGridLayout(resolution_box)
        resolution_grid.setContentsMargins(14, 18, 14, 14)
        resolution_grid.setHorizontalSpacing(12)
        resolution_grid.setVerticalSpacing(10)

        self._facid_locked_value = ""
        self._facid_reverting = False
        automatic_notice = QLabel(
            "处理顺序：先完成环网柜 / 柱上开关 / 柱上变压器模型关联；"
            "再处理馈线模型。每条 FeedLine 按几何距离寻找最近的已关联设备，"
            "环网柜或开关没有模型时直接告警，不会猜测或跨设备重复关联。"
        )
        automatic_notice.setWordWrap(True)
        automatic_notice.setStyleSheet(
            "background:#FFF7E6;color:#8A5A00;"
            "border:1px solid #F1D59B;border-radius:6px;padding:9px 11px;"
        )
        resolution_grid.addWidget(automatic_notice, 0, 0, 1, 3)

        resolution_grid.addWidget(QLabel("图纸类型确认"), 1, 0)
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
        resolution_grid.addWidget(self.feeder_drawing_mode, 1, 1, 1, 2)

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
        resolution_grid.addWidget(drawing_notice, 2, 0, 1, 3)

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
        resolution_grid.addWidget(self.auto_create_missing_sections, 3, 0, 1, 3)

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
        resolution_grid.addWidget(db_notice, 4, 0, 1, 3)
        resolution_grid.setColumnStretch(1, 1)
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
        """Backward-compatible no-op for older MainWindow callers."""
        return None

    def _on_resolution_mode_changed(self, _index=None):
        return None

    def set_facid_lock(self, facid=None):
        # Kept as a backward-compatible UI hook used by MainWindow.  It no
        # longer locks anything; it only shows the current root facID so the
        # operator can decide whether an explicit override is required.
        value = str(facid or "").strip()
        self._facid_locked_value = value
        # The old FACID/file/manual controls were intentionally removed. Keep
        # this hook so selecting local or remote files remains compatible with
        # MainWindow, but do not expose or rewrite any user-entered feeder name.

    def restore_defaults(self):
        self.section_table.setValue(self.DEFAULT_SECTION_TABLE_ID)
        self.section_domain.setValue(self.DEFAULT_SECTION_DOMAIN)
        self.feeder_drawing_mode.setCurrentIndex(0)
        self.auto_create_missing_sections.setChecked(True)

    def collect_settings(self):
        # 馈线主表 13500 是程序内部固定业务表，不再作为用户配置项显示。
        return {
            "feeder_table_id": self.DEFAULT_FEEDER_TABLE_ID,
            "section_table_id": int(self.section_table.value()),
            "section_domain": int(self.section_domain.value()),
            # Kept as fixed compatibility values for the application layer;
            # the feeder module no longer exposes any source selection.
            "feeder_resolution_mode": "FACID",
            "manual_feeder_name": "",
            "feeder_station_hint": "",
            "allow_feeder_override": False,
            "feeder_drawing_mode": str(
                self.feeder_drawing_mode.currentData() or "AUTO"
            ).upper(),
            "auto_create_missing_sections": bool(
                self.auto_create_missing_sections.isChecked()
            ),
        }
