from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class BulkAssociationSettingsWidget(QWidget):
    """UI-only coordinator for Jeddah multi-model association.

    This widget intentionally owns no model validation or write-back business
    rules.  It only lets the operator choose which existing independent model
    modules should participate in the shared two-step workflow:
    model validation -> confirmed association.
    """

    MODULES = (
        ("RMU", "RMU 环网柜模型"),
        ("POLE_SWITCH", "柱上开关模型"),
        ("TRANSFORMER", "柱上变压器模型"),
        ("FUSE", "熔断器模型"),
        ("MASTER_STATION", "配网主站设备关联"),
        ("FEEDER", "馈线模型"),
    )

    def __init__(self, config):
        super().__init__()
        self.config = config or {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        box = QGroupBox("一键多模型关联配置")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        notice = QLabel(
            "本页只负责调用现有独立模型，不复制、不重写任何业务规则。"
            "勾选哪些模块，一键执行时就按固定安全顺序调用这些模块；"
            "每个独立模型仍可在上方‘模型类型’中单独校验和关联。"
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background:#E8F7F1;color:#315E53;border:1px solid #B9DACD;"
            "border-radius:7px;padding:8px 10px;font-weight:600;"
        )
        layout.addWidget(notice)

        order = QLabel(
            "固定执行顺序：RMU → 柱上开关 → 柱上变压器 → 熔断器 → "
            "配网主站设备 → 馈线。前一模块的安全回写结果会继续作为后一模块的输入。"
        )
        order.setWordWrap(True)
        order.setStyleSheet(
            "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;"
            "border-radius:6px;padding:7px 9px;"
        )
        layout.addWidget(order)

        saved = set(
            str(value).upper()
            for value in (self.config.get("batch_modules", []) or [])
        )
        if not saved:
            saved = {module_id for module_id, _label in self.MODULES}

        self.checks = {}
        for module_id, label in self.MODULES:
            check = QCheckBox(label)
            check.setChecked(module_id in saved)
            check.setProperty("module_id", module_id)
            self.checks[module_id] = check
            layout.addWidget(check)

        actions = QHBoxLayout()
        select_all = QPushButton("全选")
        clear_all = QPushButton("全不选")
        select_all.clicked.connect(self.select_all)
        clear_all.clicked.connect(self.clear_all)
        actions.addWidget(select_all)
        actions.addWidget(clear_all)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.single_line_notice = QLabel()
        self.single_line_notice.setWordWrap(True)
        self.single_line_notice.setStyleSheet(
            "background:#FFF8DE;color:#7A5A00;border:1px solid #E7D59A;"
            "border-radius:7px;padding:8px 10px;font-weight:600;"
        )
        layout.addWidget(self.single_line_notice)

        self.status_label = QLabel("请选择需要关联的模型，然后先执行模型校验。")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color:#60756d;")
        layout.addWidget(self.status_label)

        safe = QLabel(
            "安全规则：一键模式只编排现有模块；原始 G 文件和 SSH 服务器文件不修改，"
            "所有写回累计在同一份 Workspace 安全副本中。"
        )
        safe.setWordWrap(True)
        safe.setStyleSheet("color:#607680;")
        layout.addWidget(safe)

        root.addWidget(box)

    def select_all(self):
        for check in self.checks.values():
            check.setChecked(True)

    def clear_all(self):
        for check in self.checks.values():
            check.setChecked(False)

    def selected_module_ids(self):
        return [
            module_id
            for module_id, _label in self.MODULES
            if self.checks[module_id].isChecked()
        ]

    def collect_settings(self):
        return {"batch_modules": self.selected_module_ids()}
