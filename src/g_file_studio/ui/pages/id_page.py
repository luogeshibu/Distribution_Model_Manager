from __future__ import annotations

import os
import socket
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QThreadPool, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QCheckBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from g_file_studio.engines.id_engine import inspect_tree_ids
from g_file_studio.engines.id_rule_engine import (
    ServerIdRuleCandidate,
    ServerIdRuleSyncResult,
    candidate_review_policy,
    infer_server_id_rules,
    scan_file_against_rules,
)
from g_file_studio.models import BasicOutputConflictAction, IdAction, IdSettings, InputMode
from g_file_studio.processors.common import discover_g_inputs
from g_file_studio.processors.id_processor import _write_id_reports, process_ids
from g_file_studio.services.classification_registry_service import ClassificationRegistryService
from g_file_studio.services.central_repository_settings import CentralRepositorySettings
from g_file_studio.services.id_rule_service import IdRule, IdRuleService
from g_file_studio.services.output_naming import make_task_timestamp
from g_file_studio.services.remote_g_source import download_stable_files
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output, update_run_status
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP, FIELD_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_existing_directory, validate_input_source
from g_file_studio.ui.table_layout import configure_responsive_table
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, TaskPanel
from g_file_studio.ui.widgets.help_widgets import set_primary, set_secondary
from g_file_studio.workers import FunctionWorker


class ScanResultDialog(QDialog):
    """固定尺寸的扫描结果窗口，长内容通过滚动条查看。"""

    def __init__(self, parent, title: str, text: str, *, warning: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 560)
        self.setMinimumSize(640, 420)

        header = QLabel(
            "扫描发现需要关注的内容，请在下方滚动查看。"
            if warning
            else "扫描完成，详细结果如下。"
        )
        header.setWordWrap(True)
        if warning:
            header.setObjectName("warningText")

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(text)
        viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        viewer.setMinimumHeight(320)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(viewer, 1)
        layout.addWidget(buttons)


class RuleDialog(QDialog):
    def __init__(self, parent=None, rule: IdRule | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑 ID 规则" if rule else "新增 ID 规则")
        self.tag = QLineEdit(rule.tag if rule else "")
        self.prefix = QLineEdit(rule.prefix if rule else "")
        self.total_length = QLineEdit(str(rule.total_length) if rule else "")
        self.note = QLineEdit(rule.note if rule else "")
        form = QFormLayout()
        form.addRow("XML 元素类型", self.tag)
        form.addRow("ID 固定前缀", self.prefix)
        form.addRow("ID 总位数", self.total_length)
        form.addRow("备注", self.note)
        hint = QLabel("示例：ConnectLine 使用前缀 34、总位数 8，因此 34000053、34001838 合法，而 140、340123456 不合法。新增 ID 按同类型当前最大完整 ID + 1，并且结果必须继续满足前缀和总位数。")
        hint.setWordWrap(True)
        hint.setObjectName("mutedText")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def value(self) -> IdRule:
        tag = self.tag.text().strip()
        prefix = self.prefix.text().strip()
        if not tag:
            raise ValueError("XML 元素类型不能为空。")
        if not prefix.isdigit():
            raise ValueError("ID 固定前缀必须是数字。")
        try:
            total_length = int(self.total_length.text().strip())
        except ValueError:
            raise ValueError("ID 总位数必须是正整数。")
        if total_length <= len(prefix):
            raise ValueError("ID 总位数必须大于固定前缀长度。")
        return IdRule(tag=tag, prefix=prefix, total_length=total_length, enabled=True, verified=True, note=self.note.text().strip())


class ServerRuleReviewDialog(QDialog):
    """展示用户选中 G 文件的统计，并让用户逐类确认要加入的候选规则。"""

    def __init__(
        self,
        parent,
        result: ServerIdRuleSyncResult,
        existing_rules: dict[str, IdRule],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("确认选中 G 文件的 ID 规则")
        self.resize(1050, 620)
        self.setMinimumSize(820, 460)
        self._tags: list[str] = []

        intro = QLabel(
            "以下是当前选中 G 文件的统计结果。已有且与当前规则完全一致的类型仍会显示，但默认不勾选，避免重复加入；"
            "扫描结果与当前规则不一致时会明确提示并默认勾选，等待你确认是否更新；新增类型也默认勾选。"
            "取消勾选表示保留当前规则或暂不建立。右侧会显示少数格式，供你判断样本是否混入错误。"
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedText")

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "确认",
            "元素类型",
            "扫描主流规则",
            "主流次数 / 总次数",
            "出现文件数",
            "其他格式统计",
            "当前规则",
            "对比结果",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        configure_responsive_table(self.table)
        # The responsive helper configures interactive columns; keep the final
        # "当前规则" column stretched so the table fills the dialog on first show.
        self.table.horizontalHeader().setStretchLastSection(True)

        for tag, candidate in sorted(result.candidates.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._tags.append(tag)
            current = existing_rules.get(tag)
            default_checked, comparison_text = candidate_review_policy(candidate, current)
            select = QTableWidgetItem("")
            select.setFlags(select.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            select.setCheckState(Qt.CheckState.Checked if default_checked else Qt.CheckState.Unchecked)
            select.setToolTip(comparison_text)
            self.table.setItem(row, 0, select)
            self.table.setItem(row, 1, QTableWidgetItem(f"<{tag}>"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{candidate.prefix} + {candidate.total_length} 位"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{candidate.count} / {candidate.total_ids}"))
            self.table.setItem(row, 4, QTableWidgetItem(str(candidate.file_count)))
            others = "; ".join(f"{key}: {count}" for key, count in candidate.other_formats.items()) or "无"
            self.table.setItem(row, 5, QTableWidgetItem(others))
            current_text = f"{current.prefix} + {current.total_length} 位" if current else "未建立"
            self.table.setItem(row, 6, QTableWidgetItem(current_text))
            comparison_item = QTableWidgetItem(comparison_text)
            comparison_item.setToolTip(comparison_text)
            self.table.setItem(row, 7, comparison_item)
        self.table.resizeColumnsToContents()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认并加入选中规则")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)

    def selected_candidates(self, result: ServerIdRuleSyncResult) -> list[ServerIdRuleCandidate]:
        selected: list[ServerIdRuleCandidate] = []
        for row, tag in enumerate(self._tags):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked and tag in result.candidates:
                selected.append(result.candidates[tag])
        return selected


class IdPage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        self.rule_service = IdRuleService()
        self._last_scan_candidates: dict[str, IdRule] = {}
        self._server_sync_worker: FunctionWorker | None = None
        self._central_rule_worker: FunctionWorker | None = None
        self._central_progress_dialog: QProgressDialog | None = None
        self._machine_id = self.user_settings.get_value("access_control/machine_id", "").strip()
        self._machine_name = socket.gethostname().strip() or "Unknown-PC"
        self._is_admin_mode = False
        self._admin_epoch: int | None = None
        self.last_html_report: Path | None = None
        help_title, help_html = APP_HELP["id_rules"]
        super().__init__(
            "ID 检查与修复",
            "扫描 G 文件 ID、维护规则模板，并可强制把不符合模板或重复的 ID 修复为模板格式。",
            help_title,
            help_html,
            parent,
        )
        self.layout.addWidget(InfoBanner(
            "ID 规则由你选中的 G 图形样本统计得到。程序只扫描当前选中的文件，不再全量扫描服务器目录；"
            "扫描后会汇总每种格式的出现次数，由你逐类确认，确认后才加入本机规则。"
            "样本不足的类型只告警，不擅自猜测；Admin 可再手工发布当前规则到中央仓库。"
        ))

        io_box = QGroupBox("扫描 / 处理文件")
        io_layout = QVBoxLayout(io_box)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择需要检查 ID 的 G 文件。",
            directory_tooltip="选择包含待检查 G 文件的目录；程序扫描目录第一层。",
            settings_prefix="id_rules",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)
        self.output_path = PathRow(
            directory=True,
            dialog_title="选择 ID 修复输出目录",
            recent_directory_key="recent_paths/id_rules/output_directory",
            persistent_path_key="id_rules/output_directory",
            default_path=default_workspace() / "processed",
            location_name="ID 修复输出目录",
            settings_service=self.user_settings,
        )
        self.output_path.set_tooltip(FIELD_HELP["output_dir"])
        configure_managed_output(self.output_path, "id")
        output_row = QHBoxLayout()
        output_label = QLabel("输出目录（workspace，只读）")
        output_label.setMinimumWidth(72)
        output_row.addWidget(output_label)
        output_row.addWidget(self.output_path, 1)
        io_layout.addLayout(output_row)
        self.layout.addWidget(io_box)

        template_box = QGroupBox("ID 规则模板")
        template_layout = QVBoxLayout(template_box)
        intro = QLabel("规则格式：XML 元素类型 + 固定数字起始前缀 + 固定 ID 总位数。只扫描用户当前选中的 G 文件，确认候选后才加入本机规则；Admin 可再发布到中央。新增 ID 按同类型当前最大完整 ID + 1，并始终校验前缀和位数。")
        intro.setWordWrap(True)
        intro.setObjectName("mutedText")
        template_layout.addWidget(intro)
        self.server_version_label = QLabel()
        self.server_version_label.setObjectName("mutedText")
        template_layout.addWidget(self.server_version_label)

        repo_dir = CentralRepositorySettings(self.user_settings).load().config_dir
        self.central_rule_status = QLabel(f"中央 ID 规则：{repo_dir}/id_rules.json · 仅手工同步")
        self.central_rule_status.setObjectName("mutedText")
        self.central_rule_status.setWordWrap(True)
        template_layout.addWidget(self.central_rule_status)

        self.global_strict = QCheckBox("启用全局 ID 模板强制约束")
        self.global_strict.setChecked(self.user_settings.get_bool("id_rules/global_strict", True))
        self.global_strict.setToolTip(
            "默认开启：处理输出时会把已有不符合模板的 ID 也强制修复。关闭后不会强制改写已有格式不符 ID；"
            "但所有模块新生成的 ID 仍必须严格使用当前模板。"
        )
        self.global_strict.toggled.connect(self._global_strict_toggled)
        template_layout.addWidget(self.global_strict)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("新增规则")
        self.edit_button = QPushButton("编辑规则")
        self.delete_button = QPushButton("删除规则")
        self.save_local_rule_button = QPushButton("保存到本地")
        self.save_local_rule_button.setToolTip("把当前有效 ID 规则明确写入本机 id_rules.json；不会访问中央服务器。")
        self.server_sync_button = QPushButton("扫描选中 G 文件 ID 规则")
        self.server_sync_button.setToolTip(
            "只读取当前 SSH 列表中你已勾选的 G 文件，统计 ID 格式后逐类确认；不会扫描未选中的服务器文件。"
        )
        self.central_rule_sync_button = QPushButton("从中央同步规则")
        self.central_rule_sync_button.setText("从中央同步")
        self.central_rule_sync_button.setToolTip("普通用户可用：下载中央 id_rules.json 并覆盖本机 ID 规则缓存。")
        self.central_rule_publish_button = QPushButton("发布规则到中央")
        self.central_rule_publish_button.setText("发布到中央")
        self.central_rule_publish_button.setToolTip("仅主程序当前 Admin 会话可用：把当前本机 ID 规则发布到主程序统一中央目录的 id_rules.json。")
        self.central_rule_publish_button.setEnabled(False)

        # Shared action hierarchy: maintenance helpers are secondary; explicit
        # save/sync/scan/publish actions are primary.
        for button in (self.add_button, self.edit_button, self.delete_button):
            set_secondary(button)
        for button in (
            self.save_local_rule_button,
            self.server_sync_button,
            self.central_rule_sync_button,
            self.central_rule_publish_button,
        ):
            set_primary(button)

        for button in (
            self.add_button,
            self.edit_button,
            self.delete_button,
            self.save_local_rule_button,
            self.server_sync_button,
            self.central_rule_sync_button,
            self.central_rule_publish_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        template_layout.addLayout(buttons)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["状态", "元素类型", "ID 起始前缀", "总位数", "合法示例", "当前规则", "备注"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        configure_responsive_table(self.table)
        # The responsive helper intentionally disables this by default for wide
        # tables.  ID rules are short enough that the last remarks column should
        # fill the remaining page width when the page opens or is resized.
        self.table.horizontalHeader().setStretchLastSection(True)
        template_layout.addWidget(self.table)
        self.layout.addWidget(template_box)

        self.task = TaskPanel()
        self.scan_button = QPushButton("扫描当前G文件（只检查ID）")
        set_primary(self.scan_button)
        set_primary(self.task.run_button)
        self.scan_button.setToolTip("扫描完成后会生成/覆盖 ID 扫描 CSV/HTML 报告；规则使用当前本机已确认版本。需要新增/更新规则时，请先勾选样本 G 文件并点击上方“扫描选中 G 文件 ID 规则”。")
        self.task.run_button.setText("检查并强制修复 ID")
        self.task.run_button.setToolTip("执行后会按服务器已同步或手动维护的当前模板修复 ID，并生成/覆盖 ID 修复 CSV/HTML 报告，可点击“打开报告”查看。")
        self.report_button = QPushButton("打开报告")
        self.report_button.setEnabled(False)
        set_secondary(self.report_button)
        # ID 页面只保留两个明确动作：扫描/检查，以及强制修复。
        # 报告、输出目录、清空日志均集中在“执行与日志”。
        self.task.buttons_layout.insertWidget(0, self.scan_button)
        self.task.buttons_layout.insertWidget(2, self.report_button)
        self.layout.addWidget(self.task, 1)

        self.scan_button.clicked.connect(self.scan_current)
        self.add_button.clicked.connect(self.add_rule)
        self.edit_button.clicked.connect(self.edit_rule)
        self.delete_button.clicked.connect(self.delete_rule)
        self.save_local_rule_button.clicked.connect(self._save_rules_to_local)
        self.server_sync_button.clicked.connect(self.sync_server_rules)
        self.central_rule_sync_button.clicked.connect(self._sync_central_rules)
        self.central_rule_publish_button.clicked.connect(self._publish_central_rules)
        self.task.run_button.clicked.connect(self.run)
        self.report_button.clicked.connect(self.open_last_report)
        self.task.resultReceived.connect(self._task_result)
        self._refresh_table()
        self._refresh_server_version_label()
        self._refresh_local_rule_status()

    @staticmethod
    def _local_timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _refresh_local_rule_status(self, *, extra: str = "") -> None:
        source = self.user_settings.get_value("local_cache/id_rules_source", "local").strip() or "local"
        source_labels = {
            "central": "中央同步副本",
            "custom": "本地配置",
            "local": "本地配置",
        }
        if not self.rule_service.json_path.exists():
            source_label = "内置默认规则（尚未保存本地文件）"
        else:
            source_label = source_labels.get(source, "本地配置")
        saved_at = self.user_settings.get_value("local_cache/id_rules_saved_at", "").strip()
        if not saved_at and self.rule_service.json_path.exists():
            try:
                saved_at = datetime.fromtimestamp(self.rule_service.json_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                saved_at = ""
        synced_at = self.user_settings.get_value("local_cache/id_rules_synced_at", "").strip()
        version = self.user_settings.get_value("local_cache/central_id_rules_version", "").strip()
        version_text = f" · 中央 V{version}" if version and source == "central" else ""
        extra_text = f" · {extra}" if extra else ""
        self.central_rule_status.setText(
            f"当前来源：{source_label}{version_text} · 本地更新时间：{saved_at or '尚未保存'} · "
            f"中央同步：{synced_at or '尚未同步'} · 启动不自动读取中央配置{extra_text}"
        )

    def _mark_local_rules_saved(self, source: str = "custom", *, central_version: int | None = None) -> None:
        stamp = self._local_timestamp()
        self.user_settings.set_value("local_cache/id_rules_source", source)
        self.user_settings.set_value("local_cache/id_rules_saved_at", stamp)
        if source == "central":
            self.user_settings.set_value("local_cache/id_rules_synced_at", stamp)
            if central_version is not None:
                self.user_settings.set_value("local_cache/central_id_rules_version", central_version)
        self._refresh_local_rule_status()

    def _save_rules_to_local(self) -> None:
        try:
            count = self.rule_service.persist_current()
        except Exception as exc:
            QMessageBox.warning(self, "保存到本地失败", str(exc))
            return
        self._mark_local_rules_saved("custom")
        self.task.append_log(f"当前 ID 规则已保存到本地：{count} 条；未访问中央配置。")
        QMessageBox.information(self, "已保存到本地", f"已将 {count} 条 ID 规则保存到本机。")

    def _central_registry_config(self) -> dict[str, object]:
        repository = CentralRepositorySettings(self.user_settings).load()
        cfg = repository.connection_args()
        cfg["config_dir"] = repository.config_dir
        return cfg

    def _ensure_machine_id(self) -> str:
        machine_id = self.user_settings.get_value("access_control/machine_id", "").strip()
        if not machine_id:
            machine_id = uuid4().hex
            self.user_settings.set_value("access_control/machine_id", machine_id)
        self._machine_id = machine_id
        return machine_id

    def _open_central_progress(self, title: str, label: str) -> QProgressDialog:
        dialog = QProgressDialog(label, "", 0, 100, self)
        dialog.setWindowTitle(title)
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        # Do not flash a transient progress window for fast local/central operations.
        # Qt will show it only when the operation actually lasts long enough.
        dialog.setMinimumDuration(800)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self._central_progress_dialog = dialog
        return dialog

    def _close_central_progress(self) -> None:
        dialog = self._central_progress_dialog
        self._central_progress_dialog = None
        if dialog is not None:
            dialog.setValue(100)
            dialog.close()
            dialog.deleteLater()

    def set_admin_mode(self, is_admin: bool, admin_epoch: int | None = None) -> None:
        self._is_admin_mode = bool(is_admin)
        self._admin_epoch = int(admin_epoch) if is_admin and admin_epoch is not None else None
        if hasattr(self, "central_rule_publish_button"):
            self.central_rule_publish_button.setEnabled(
                self._is_admin_mode
                and self._admin_epoch is not None
                and self._central_rule_worker is None
            )

    def _set_central_rule_busy(self, busy: bool) -> None:
        self.central_rule_sync_button.setEnabled(not busy)
        self.central_rule_publish_button.setEnabled(
            (not busy) and self._is_admin_mode and self._admin_epoch is not None
        )
        self.save_local_rule_button.setEnabled(not busy)
        self.add_button.setEnabled(not busy)
        self.edit_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)

    def _sync_central_rules(self) -> None:
        if self._central_rule_worker is not None:
            return
        try:
            cfg = self._central_registry_config()
        except Exception as exc:
            QMessageBox.warning(self, "同步中央 ID 规则", str(exc))
            return
        if QMessageBox.question(
            self,
            "从中央同步 ID 规则",
            "中央 id_rules.json 将覆盖当前本机 ID 规则缓存。继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return

        self._set_central_rule_busy(True)
        self.central_rule_status.setText("中央 ID 规则：正在同步…")
        progress_dialog = self._open_central_progress(
            "同步中央 ID 规则",
            "正在读取中央 id_rules.json…",
        )

        def task(*, log, progress):
            progress(10)
            # Compatibility marker for older source checks: ClassificationRegistryService().fetch_id_rules
            service = ClassificationRegistryService(config_dir=str(cfg["config_dir"]))
            connection = {key: cfg[key] for key in ("host", "port", "username", "password")}
            result = service.fetch_id_rules(**connection, log=log)
            progress(80)
            return result

        worker = FunctionWorker(task)
        self._central_rule_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(self._on_central_rule_sync_result)
        worker.signals.error.connect(lambda details: self._on_central_rule_error(details, "同步"))
        worker.signals.finished.connect(self._on_central_rule_finished)
        QThreadPool.globalInstance().start(worker)

    def _on_central_rule_sync_result(self, result: object) -> None:
        if self._central_progress_dialog is not None:
            self._central_progress_dialog.setLabelText("正在覆盖本机 ID 规则缓存…")
            self._central_progress_dialog.setValue(90)
        payload = dict(result) if isinstance(result, dict) else {}
        rules_payload = payload.get("id_rules")
        if not isinstance(rules_payload, dict):
            raise ValueError("中央 ID 规则返回格式无效。")
        imported = self.rule_service.replace_from_payload(rules_payload)
        instance = payload.get("instance", {})
        version = int(instance.get("config_version", 0) or 0) if isinstance(instance, dict) else 0
        self._mark_local_rules_saved("central", central_version=version)
        self._refresh_table()
        self._refresh_server_version_label()
        self._refresh_local_rule_status(extra=f"刚刚同步 {imported['rules']} 条")
        self._close_central_progress()
        QMessageBox.information(
            self,
            "中央 ID 规则已同步",
            f"已用中央 V{version} 覆盖本机 ID 规则，共 {imported['rules']} 条。",
        )

    def _publish_central_rules(self) -> None:
        if self._central_rule_worker is not None:
            return
        try:
            CentralRepositorySettings(self.user_settings).require_explicitly_saved(action="发布 ID 规则到中央")
        except Exception as exc:
            QMessageBox.warning(self, "中央仓库尚未确认", str(exc))
            return
        if not self._is_admin_mode or self._admin_epoch is None:
            QMessageBox.warning(
                self,
                "需要 Admin 权限",
                "普通客户端可以修改/保存本机 ID 规则并从中央同步，但不能发布中央仓库。请先到主程序【设置】抢占 Admin。",
            )
            return
        try:
            cfg = self._central_registry_config()
            machine_id = self._ensure_machine_id()
            payload = self.rule_service.export_payload()
        except Exception as exc:
            QMessageBox.warning(self, "发布中央 ID 规则", str(exc))
            return
        if QMessageBox.question(
            self,
            "发布中央 ID 规则",
            "将当前本机 ID 规则发布为中央正式 id_rules.json？",
        ) != QMessageBox.StandardButton.Yes:
            return

        self._set_central_rule_busy(True)
        self.central_rule_status.setText("中央 ID 规则：正在发布…")
        progress_dialog = self._open_central_progress(
            "发布中央 ID 规则",
            "正在验证管理员并上传 id_rules.json…",
        )

        def task(*, log, progress):
            progress(10)
            service = ClassificationRegistryService(config_dir=str(cfg["config_dir"]))
            connection = {key: cfg[key] for key in ("host", "port", "username", "password")}
            owner = service.fetch_admin_lease(**connection)
            if owner is None or owner.machine_id != machine_id:
                raise RuntimeError("当前主程序会话不是中央 Admin，不能发布中央 ID 规则。")
            if owner.admin_epoch != int(self._admin_epoch or -1):
                raise RuntimeError("Admin 权限已被重新抢占，请重新抢占 Admin 后再发布。")
            result = service.publish_id_rules(
                **connection,
                machine_id=machine_id,
                machine_name=self._machine_name,
                expected_admin_epoch=self._admin_epoch,
                payload=payload,
                log=log,
            )
            progress(90)
            return result

        worker = FunctionWorker(task)
        self._central_rule_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(self._on_central_rule_publish_result)
        worker.signals.error.connect(lambda details: self._on_central_rule_error(details, "发布"))
        worker.signals.finished.connect(self._on_central_rule_finished)
        QThreadPool.globalInstance().start(worker)

    def _on_central_rule_publish_result(self, result: object) -> None:
        self._close_central_progress()
        payload = dict(result) if isinstance(result, dict) else {}
        instance = payload.get("instance", {})
        rules_payload = payload.get("id_rules", {})
        version = int(instance.get("config_version", 0) or 0) if isinstance(instance, dict) else 0
        rule_count = len(rules_payload.get("rules", [])) if isinstance(rules_payload, dict) else 0
        self._refresh_local_rule_status(extra=f"已发布中央 V{version} · {rule_count} 条")
        config_dir = CentralRepositorySettings(self.user_settings).load().config_dir
        QMessageBox.information(
            self,
            "中央 ID 规则已发布",
            f"中央版本：V{version}\n规则：{rule_count} 条\n\n{config_dir}/id_rules.json",
        )

    def _on_central_rule_error(self, details: str, action: str) -> None:
        self._close_central_progress()
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self._refresh_local_rule_status(extra=f"中央{action}失败")
        QMessageBox.warning(self, f"中央 ID 规则{action}失败", message or str(details))

    def _on_central_rule_finished(self) -> None:
        self._central_rule_worker = None
        self._close_central_progress()
        self._set_central_rule_busy(False)

    def refresh_after_external_central_sync(self, summary: object = None) -> None:
        """Refresh the already-open page after the global central-sync action."""
        payload = dict(summary) if isinstance(summary, dict) else {}
        version = int(payload.get("version", 0) or 0)
        count = int(payload.get("id_rule_count", 0) or 0)
        self._refresh_table()
        self._refresh_server_version_label()
        detail = f"一键同步已更新 V{version}" if version else "一键同步已更新"
        if count:
            detail += f" · {count} 条"
        self._refresh_local_rule_status(extra=detail)

    def _refresh_table(self) -> None:
        rules = self.rule_service.load_rules()
        self.table.setRowCount(0)
        for rule in sorted(rules.values(), key=lambda item: item.tag.lower()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            example = rule.build(1)
            values = [
                "✓ 服务器已同步" if rule.note.startswith("服务器 G 图形自动读取") else "✓ 已确认",
                rule.tag,
                rule.prefix,
                str(rule.total_length),
                example,
                "前缀 + 总位数；同类型最大 ID + 1",
                rule.note,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, rule.tag)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _refresh_server_version_label(self) -> None:
        snapshot = self.rule_service.load_server_snapshot()
        version = str(snapshot.get("version", "")).strip()
        if not version:
            self.server_version_label.setText("最近一次样本确认：尚无；当前表格为本地已有规则")
            return
        self.server_version_label.setText(
            "最近一次样本确认："
            f"{version} · 样本文件 {snapshot.get('file_count', 0)} · "
            f"图元 {snapshot.get('element_count', 0)} · 已确认类型 {snapshot.get('selected_rule_count', 0)}"
        )

    def _global_strict_toggled(self, checked: bool) -> None:
        if not checked:
            answer = QMessageBox.warning(
                self,
                "关闭全局 ID 强制约束",
                "关闭后，后续处理不会再强制改写 G 文件中已有但不符合模板的 ID。\n\n"
                "注意：所有模块新生成的 ID 仍会严格按照当前 ID 规则模板生成。\n\n"
                "确认关闭全局 ID 模板强制约束吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.global_strict.blockSignals(True)
                self.global_strict.setChecked(True)
                self.global_strict.blockSignals(False)
                return
        self.user_settings.set_value("id_rules/global_strict", "true" if checked else "false")
        self.task.append_log(
            "全局 ID 模板强制约束已开启：已有格式不符 ID 会在处理输出时按模板修复。"
            if checked
            else "全局 ID 模板强制约束已关闭：已有格式不符 ID 保持不变；新生成 ID 仍严格使用模板。"
        )

    def _selected_tag(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def add_rule(self) -> None:
        dialog = RuleDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            rule = dialog.value()
        except ValueError as exc:
            QMessageBox.warning(self, "规则无效", str(exc))
            return
        rules = self.rule_service.load_rules()
        if rule.tag in rules:
            QMessageBox.warning(self, "规则已存在", f"<{rule.tag}> 已存在，请使用“编辑规则”。")
            return
        self.rule_service.upsert(rule)
        self._mark_local_rules_saved("custom")
        self._refresh_table()

    def edit_rule(self) -> None:
        tag = self._selected_tag()
        if not tag:
            QMessageBox.information(self, "请选择规则", "请先选择要编辑的规则。")
            return
        old = self.rule_service.load_rules()[tag]
        dialog = RuleDialog(self, old)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            new = dialog.value()
        except ValueError as exc:
            QMessageBox.warning(self, "规则无效", str(exc))
            return
        if new.tag != old.tag:
            self.rule_service.remove(old.tag)
        self.rule_service.upsert(new)
        self._mark_local_rules_saved("custom")
        self._refresh_table()

    def delete_rule(self) -> None:
        tag = self._selected_tag()
        if not tag:
            QMessageBox.information(self, "请选择规则", "请先在表格中选中一条要删除的规则。")
            return
        if QMessageBox.question(
            self,
            "删除规则",
            f"确认删除 ID 规则 <{tag}>？\n\n删除后立即生效；再次扫描到对应元素类型时会重新提醒是否添加。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.rule_service.remove(tag)
        self._mark_local_rules_saved("custom")
        self._last_scan_candidates.pop(tag, None)
        self._refresh_table()
        self.task.append_log(f"已立即删除 ID 规则 <{tag}>。")

    def _scan_server_rules_from_files(
        self,
        files: list[Path],
        *,
        log=None,
        progress=None,
    ) -> ServerIdRuleSyncResult:
        """扫描用户选中的 G 快照并返回统计候选；此处不修改当前规则。"""
        if not files:
            raise ValueError("没有找到可用于统计 ID 规则的已选 G 文件。")
        log = log or self.task.append_log
        progress = progress or (lambda value: self.task.set_progress(70 + round(value * 0.25)))
        result = infer_server_id_rules(
            files,
            self.rule_service.load_rules(),
            progress=progress,
        )
        log(
            f"[选中样本 ID 规则] 已读取 {result.file_count} 个 G 文件、{result.element_count} 个直接图元；"
            f"候选 {len(result.candidates)} 类，当前新增 {len(result.added)} 类，"
            f"当前变化 {len(result.updated)} 类，保持 {len(result.unchanged)} 类。"
        )
        for tag, candidate in sorted(result.candidates.items()):
            other = "; ".join(f"{key}×{count}" for key, count in candidate.other_formats.items()) or "无其他格式"
            log(
                f"  <{tag}> 主流 {candidate.prefix}+{candidate.total_length}位："
                f"{candidate.count}/{candidate.total_ids} 次，涉及 {candidate.file_count} 个文件；其他：{other}"
            )
        if result.unresolved:
            log(
                "  选中样本不足，未自动猜测：" + ", ".join(f"<{tag}>" for tag in result.unresolved)
            )
        return result

    def _review_and_apply_server_rules(self, result: ServerIdRuleSyncResult) -> bool:
        """让用户按选中样本的统计证据逐类确认，并加入本机规则。"""
        if not result.candidates:
            QMessageBox.information(self, "ID 规则样本扫描完成", "选中的 G 文件没有足够样本形成可确认的主流 ID 规则。")
            return False
        existing = self.rule_service.load_rules()
        dialog = ServerRuleReviewDialog(self, result, existing)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.task.append_log("选中 G 文件扫描完成，但本次未加入任何规则。")
            return False
        selected = dialog.selected_candidates(result)
        if not selected:
            self.task.append_log("已取消全部候选；当前本机 ID 规则保持不变。")
            return False
        rules = dict(existing)
        for candidate in selected:
            rules[candidate.tag] = IdRule(
                tag=candidate.tag,
                prefix=candidate.prefix,
                total_length=candidate.total_length,
                enabled=True,
                verified=True,
                note=(
                    "用户选中 G 文件统计后人工确认；主流 "
                    f"{candidate.count}/{candidate.total_ids} 次，涉及 {candidate.file_count} 个文件"
                ),
            )
        version = make_task_timestamp()
        candidate_statistics = {
            tag: {
                "prefix": candidate.prefix,
                "total_length": candidate.total_length,
                "count": candidate.count,
                "total_ids": candidate.total_ids,
                "file_count": candidate.file_count,
                "other_formats": candidate.other_formats,
            }
            for tag, candidate in result.candidates.items()
        }
        self.rule_service.save_server_snapshot(
            rules.values(),
            version=version,
            file_count=result.file_count,
            element_count=result.element_count,
            selected_rule_count=len(selected),
            candidate_statistics=candidate_statistics,
        )
        self._mark_local_rules_saved("custom")
        self._refresh_table()
        self._refresh_server_version_label()
        self.task.append_log(
            f"选中样本已确认并加入本机规则版本 {version}；本次确认 {len(selected)} 类。"
        )
        return True

    def _set_server_sync_busy(self, busy: bool) -> None:
        """锁定会影响选中样本扫描输入或规则版本的 UI 操作。"""
        controls = (
            self.source,
            self.add_button,
            self.edit_button,
            self.delete_button,
            self.server_sync_button,
            self.scan_button,
            self.task.run_button,
        )
        for control in controls:
            control.setEnabled(not busy)
        self.server_sync_button.setText("正在扫描选中 G 文件…" if busy else "扫描选中 G 文件 ID 规则")

    @staticmethod
    def _server_candidate_statistics(result: ServerIdRuleSyncResult) -> dict[str, dict[str, object]]:
        return {
            tag: {
                "prefix": candidate.prefix,
                "total_length": candidate.total_length,
                "count": candidate.count,
                "total_ids": candidate.total_ids,
                "file_count": candidate.file_count,
                "other_formats": candidate.other_formats,
            }
            for tag, candidate in result.candidates.items()
        }

    def _finish_server_rule_review(self, result: ServerIdRuleSyncResult) -> None:
        """在主线程中展示当前选中 G 文件的统计并让用户确认加入规则。"""
        self.task.set_progress(95)
        self.task.append_log("[阶段 4/4] 选中样本统计完成，等待你确认需要加入的规则。")
        applied = self._review_and_apply_server_rules(result)
        self.task.set_progress(100)
        self.task.append_log("[阶段 4/4] 规则确认流程完成。")
        if applied:
            if self._is_admin_mode and self._admin_epoch is not None:
                message = (
                    "已按你的勾选把规则加入本机。\n\n"
                    "当前会话拥有 Admin 权限；如确认这些规则适合作为现场公共规则，"
                    "可点击“发布到中央”上传中央 id_rules.json。"
                )
            else:
                message = (
                    "已按你的勾选把规则加入本机。\n\n"
                    "普通客户端不会自动发布中央仓库；需要 Admin 审核后再发布。"
                )
            QMessageBox.information(self, "ID 规则已加入", message)

    def _server_sync_error(self, details: str) -> None:
        self.task.append_log("选中 G 文件 ID 规则扫描失败：" + details)
        message = details.split("\n\n---TRACEBACK---", 1)[0].strip() or details
        QMessageBox.warning(self, "扫描选中 G 文件 ID 规则失败", message)

    def _server_sync_finished(self) -> None:
        self._server_sync_worker = None
        self._set_server_sync_busy(False)

    def sync_server_rules(self) -> None:
        """只读取用户当前勾选的服务器 G 文件，统计后确认加入本机规则。"""
        if self.source.mode() != InputMode.REMOTE_SSH:
            QMessageBox.information(
                self,
                "请使用服务器 G 文件",
                "请先把输入方式切换为“SSH 远程 G 文件（只读）”，在列表中勾选一个或多个样本 G 文件，再扫描 ID 规则。",
            )
            return
        if self._server_sync_worker is not None:
            return

        selected_files = list(self.source.remote.selected_files())
        if not selected_files:
            QMessageBox.information(
                self,
                "请先选择 G 文件",
                "当前没有勾选服务器 G 文件。请先在上方列表中选择有代表性的 G 文件，再点击“扫描选中 G 文件 ID 规则”。",
            )
            return

        self.task.log_view_clear()
        self.task.set_progress(0)
        self._set_server_sync_busy(True)
        self.task.append_log(
            f"已选择 {len(selected_files)} 个服务器 G 文件；只扫描这些文件，不会遍历服务器全部 G 文件。"
        )

        try:
            self.source.remote._restore_shared_settings()
            cfg = dict(self.source.remote.config())
            snapshot_dir = self.source.remote._processing_snapshot_dir()
            existing_rules = self.rule_service.load_rules()

            def run_server_scan(*, log, progress):
                log(f"[阶段 1/4] 准备读取 {len(selected_files)} 个已选服务器 G 文件。")
                progress(5)
                log(f"[阶段 2/4] 开始下载 {len(selected_files)} 个只读样本快照到 workspace。")

                last_download_progress = -1

                def download_progress(value: int) -> None:
                    nonlocal last_download_progress
                    mapped = 5 + round(value * 0.65)
                    if mapped != last_download_progress:
                        last_download_progress = mapped
                        progress(mapped)

                def download_log(message: str) -> None:
                    # 用户已主动缩小样本范围；仍对下载日志做轻量节流，避免大量勾选时 UI 高频刷新。
                    if message.startswith("[SSH "):
                        marker = message.split("]", 1)[0]
                        try:
                            current, total = marker[5:].split("/", 1)
                            index = int(current)
                            total_count = int(total)
                        except (ValueError, IndexError):
                            log(message)
                            return
                        if index not in {1, total_count} and index % 50 != 0:
                            return
                    elif message.lstrip().startswith("完成："):
                        return
                    log(message)

                downloaded = download_stable_files(
                    host=str(cfg["host"]),
                    port=int(cfg["port"]),
                    username=str(cfg["username"]),
                    password=str(cfg["password"]),
                    selected_files=selected_files,
                    target_dir=snapshot_dir,
                    log=download_log,
                    progress=download_progress,
                )
                log("[阶段 3/4] 已选 G 文件下载完成，开始逐文件解析并统计 ID。")
                result = infer_server_id_rules(
                    downloaded,
                    existing_rules,
                    progress=lambda value: progress(70 + round(value * 0.25)),
                )
                progress(95)
                log(
                    f"[选中样本 ID 规则] 已读取 {result.file_count} 个 G 文件、"
                    f"{result.element_count} 个直接图元；候选 {len(result.candidates)} 类。"
                )
                for tag, candidate in sorted(result.candidates.items()):
                    other = "; ".join(
                        f"{key}×{count}" for key, count in candidate.other_formats.items()
                    ) or "无其他格式"
                    log(
                        f"  <{tag}> 主流 {candidate.prefix}+{candidate.total_length}位："
                        f"{candidate.count}/{candidate.total_ids} 次，涉及 {candidate.file_count} 个已选文件；其他：{other}"
                    )
                if result.unresolved:
                    log("  选中样本不足，未自动猜测：" + ", ".join(f"<{tag}>" for tag in result.unresolved))
                return result

            worker = FunctionWorker(run_server_scan)
            self._server_sync_worker = worker
            worker.signals.log.connect(self.task.append_log)
            worker.signals.progress.connect(self.task.set_progress)
            worker.signals.result.connect(self._finish_server_rule_review)
            worker.signals.error.connect(self._server_sync_error)
            worker.signals.finished.connect(self._server_sync_finished)
            QTimer.singleShot(0, lambda current=worker: QThreadPool.globalInstance().start(current))
        except Exception as exc:
            self._set_server_sync_busy(False)
            QMessageBox.warning(self, "扫描选中 G 文件 ID 规则失败", str(exc))

    def scan_current(self) -> None:
        if not validate_input_source(self, self.source, display_name="ID 扫描输入"):
            return
        files = discover_g_inputs(self.source.path(), self.source.mode())
        self.task.log_view.clear()
        self.task.set_progress(0)
        # 远程规则候选只在用户点击“扫描选中 G 文件 ID 规则”时进入确认流程；
        # 普通 ID 检查始终使用当前本机已确认的规则版本。
        rules = self.rule_service.load_rules()
        self.task.append_log(
            f"开始扫描当前 G，共 {len(files)} 个文件。"
            + (" 规则来源：当前本机已确认规则。" if self.source.mode() == InputMode.REMOTE_SSH else "")
        )
        output_dir = begin_managed_run(self.output_path, "id", "scan")
        candidates: dict[str, IdRule] = {}
        new_messages: list[str] = []
        changed_messages: list[str] = []
        invalid_ids_by_tag: dict[str, list[str]] = {}
        matched: set[str] = set()
        observed_all: set[str] = set()
        uninferable: set[str] = set()
        type_max_ids: dict[str, int] = {}
        progress_dialog = QProgressDialog("正在扫描当前 G 文件并检查 ID 规则……", "取消", 0, 100, self)
        progress_dialog.setWindowTitle("扫描当前 G")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(800)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.setValue(0)
        try:
            for index, path in enumerate(files, start=1):
                if progress_dialog.wasCanceled():
                    update_run_status(output_dir, "CANCELLED") if "output_dir" in locals() else None
                    self.task.append_log("扫描已取消。")
                    return
                progress_dialog.setLabelText(f"正在扫描：{path.name}  （{index}/{len(files)}）")
                QApplication.processEvents()
                scan = scan_file_against_rules(path, rules)
                observed_all.update(scan.observed)
                matched.update(scan.matched_tags)
                for tag, value in scan.type_max_ids.items():
                    type_max_ids[tag] = max(type_max_ids.get(tag, 0), int(value))
                for item in scan.new_rule_candidates:
                    if item.prefix is not None:
                        if item.total_length is not None and item.total_length > len(item.prefix):
                            candidates[item.tag] = IdRule(
                                item.tag, item.prefix, item.total_length, enabled=True, verified=True,
                                note=f"由 {path.name} 扫描发现；当前仅作为检查候选",
                            )
                            new_messages.append(
                                f"<{item.tag}>：候选前缀 {item.prefix}、总位数 {item.total_length}（仅作检查候选）；"
                                f"样本 {', '.join(item.sample_ids[:3])}"
                            )
                for item in scan.unknown_uninferable:
                    uninferable.add(item.tag)
                for item in scan.changed_formats:
                    bucket = invalid_ids_by_tag.setdefault(item.tag, [])
                    for value in item.sample_ids:
                        if value not in bucket:
                            bucket.append(value)
                pct = round(index * 100 / max(len(files), 1))
                progress_dialog.setValue(pct)
                self.task.set_progress(pct)
                self.task.append_log(f"[{index}/{len(files)}] 已扫描：{path.name}")
                QApplication.processEvents()
        except Exception as exc:
            update_run_status(output_dir, "FAILED", note=str(exc))
            QMessageBox.warning(self, "扫描失败", str(exc))
            return
        finally:
            progress_dialog.close()
        self._last_scan_candidates = candidates
        covered_tags = observed_all & set(rules)
        missing_tags = observed_all - set(rules)
        parts = [f"模板覆盖检查：当前 G 共发现 {len(observed_all)} 类带 ID 元素；模板已覆盖 {len(covered_tags)} 类，未覆盖 {len(missing_tags)} 类。"]
        if missing_tags:
            parts.append("未覆盖类型：" + ", ".join(f"<{tag}>" for tag in sorted(missing_tags)))
        if type_max_ids:
            preview = []
            for tag in sorted(type_max_ids):
                current = type_max_ids[tag]
                preview.append(f"<{tag}> 当前最大 {current}，下一个 {current + 1}")
            parts.append("同类型 ID 递增预览：\n" + "\n".join(preview[:16]))
        if new_messages:
            parts.append("发现新元素类型：\n" + "\n".join(new_messages))
        if uninferable:
            parts.append("样本不足、不能自动推断：" + ", ".join(sorted(uninferable)) + "。请人工新增规则。")
        if invalid_ids_by_tag:
            for tag in sorted(invalid_ids_by_tag):
                rule = rules.get(tag)
                values = invalid_ids_by_tag[tag]
                changed_messages.append(
                    f"<{tag}>：模板要求前缀 {rule.prefix}、总位数 {rule.total_length}；"
                    f"不符合模板的完整 ID（{len(values)} 个）：{', '.join(values)}"
                )
            parts.append(
                "发现已有类型 ID 不符合模板：\n"
                + "\n".join(changed_messages)
                + "\n以上数字均为 XML 中实际存在的完整 ID，不是前缀。模板不会自动修改。"
            )
        scan_text = "\n".join(parts)
        self.task.append_log("\nID 模板扫描结果：")
        self.task.append_log(scan_text)

        # “扫描当前 G（只检查 ID）”同样生成独立 CSV/HTML 报告。
        # 报告只记录实际发现的问题；无问题文件记录为“正常”。
        report_rows: list[dict[str, str]] = []
        for path in files:
            try:
                scan = scan_file_against_rules(path, rules)
                file_rows = 0
                for item in scan.new_rule_candidates:
                    detail = (
                        f"尚未加入模板；候选前缀 {item.prefix}、总位数 {item.total_length}（如需加入，请用上方选中样本扫描并确认）"
                        if item.prefix is not None and item.total_length is not None
                        else "尚未加入模板"
                    )
                    for value in item.sample_ids or [""]:
                        report_rows.append({"File": path.name, "Category": "未配置模板", "ElementType": item.tag, "OriginalID": value, "NewID": "", "Detail": detail})
                        file_rows += 1
                for item in scan.unknown_uninferable:
                    for value in item.sample_ids or [""]:
                        report_rows.append({"File": path.name, "Category": "未配置模板", "ElementType": item.tag, "OriginalID": value, "NewID": "", "Detail": "样本不足，不能可靠推断 ID 模板"})
                        file_rows += 1
                for item in scan.changed_formats:
                    rule = rules.get(item.tag)
                    detail = f"模板要求前缀 {rule.prefix}、总位数 {rule.total_length}" if rule else "不符合当前模板"
                    for value in item.sample_ids:
                        report_rows.append({"File": path.name, "Category": "格式不符", "ElementType": item.tag, "OriginalID": value, "NewID": "", "Detail": detail})
                        file_rows += 1
                inspection = inspect_tree_ids(ET.parse(path), path)
                for group in inspection.duplicate_groups:
                    report_rows.append({"File": path.name, "Category": "重复 ID", "ElementType": ", ".join(group.tags), "OriginalID": group.value, "NewID": "", "Detail": f"出现 {group.count} 次"})
                    file_rows += 1
                if file_rows == 0:
                    report_rows.append({"File": path.name, "Category": "正常", "ElementType": "", "OriginalID": "", "NewID": "", "Detail": "未发现模板格式异常或重复 ID"})
            except Exception as exc:
                report_rows.append({"File": path.name, "Category": "处理失败", "ElementType": "", "OriginalID": "", "NewID": "", "Detail": str(exc)})
        timestamp = make_task_timestamp()
        csv_path, html_path = _write_id_reports(output_dir, report_rows, timestamp, report_kind="scan")
        self.last_html_report = html_path
        self.report_button.setEnabled(True)
        self.task._output_dir = output_dir
        self.task.open_button.setEnabled(True)
        self.task.append_log(f"CSV 报告：{csv_path}")
        self.task.append_log(f"HTML 报告：{html_path}")
        self.task.set_progress(100)
        update_run_status(output_dir, "SUCCESS")
        QMessageBox.information(
            self,
            "扫描完成",
            "ID 扫描完成，扫描报告已生成并覆盖上一份扫描报告。\n可点击“打开报告”查看 HTML 报告。",
        )

        if candidates:
            self.task.append_log(
                "当前检查文件发现未配置类型；本按钮只检查，不自动加入规则。"
                "如需加入，请在 SSH 列表中勾选代表性 G 文件，点击上方“扫描选中 G 文件 ID 规则”并确认。"
            )

    def _confirm_detected_rules(self) -> None:
        if not self._last_scan_candidates:
            return
        added: list[str] = []
        skipped: list[str] = []
        for tag in sorted(list(self._last_scan_candidates)):
            candidate = self._last_scan_candidates[tag]
            dialog = RuleDialog(self, candidate)
            dialog.setWindowTitle(f"确认扫描发现的 ID 规则：{tag}")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                skipped.append(tag)
                continue
            try:
                confirmed = dialog.value()
            except ValueError as exc:
                QMessageBox.warning(self, "规则无效", str(exc))
                skipped.append(tag)
                continue
            existing = self.rule_service.load_rules()
            if confirmed.tag in existing and confirmed.tag != tag:
                QMessageBox.warning(self, "规则已存在", f"<{confirmed.tag}> 已存在，本次未加入。")
                skipped.append(tag)
                continue
            confirmed = IdRule(
                tag=confirmed.tag, prefix=confirmed.prefix, total_length=confirmed.total_length,
                enabled=True, verified=True,
                note=confirmed.note or "由当前 G 扫描自动识别参数，经用户确认",
            )
            self.rule_service.upsert(confirmed)
            added.append(confirmed.tag)
            self._last_scan_candidates.pop(tag, None)
        self._refresh_table()
        pieces = []
        if added:
            pieces.append("已确认加入：" + ", ".join(f"<{tag}>" for tag in added))
        if skipped:
            pieces.append("暂未加入：" + ", ".join(f"<{tag}>" for tag in skipped))
        if pieces:
            self.task.append_log("；".join(pieces) + "。")

    def add_detected_rules(self) -> None:
        self._confirm_detected_rules()

    def _task_result(self, result) -> None:
        path_text = str(result.statistics.get("html_report_path", "")) if getattr(result, "statistics", None) else ""
        if path_text:
            self.last_html_report = Path(path_text)
            self.report_button.setEnabled(self.last_html_report.exists())
            QMessageBox.information(
                self,
                "ID 修复完成",
                "ID 检查与强制修复已完成，修复报告已生成并覆盖上一份修复报告。\n可点击“打开报告”查看 HTML 报告。",
            )

    def open_last_report(self) -> None:
        if not self.last_html_report or not self.last_html_report.exists():
            QMessageBox.information(self, "暂无报告", "请先执行一次 ID 检查或修复。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_html_report.resolve())))

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()

    def _same_path(self, left: Path, right: Path) -> bool:
        return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(str(right.resolve(strict=False)))

    def run(self) -> None:
        if not validate_input_source(self, self.source, display_name="ID 处理输入"):
            return
        action = IdAction.REPAIR
        # Managed workspace output is disposable and recreated on demand.
        self.source.persist_current()
        output_dir = begin_managed_run(self.output_path, "id", "repair")
        timestamp = make_task_timestamp()
        # 每次修复都进入独立运行目录，处理后的 G 文件严格保持源文件名。
        conflict_action = BasicOutputConflictAction.OVERWRITE
        settings = IdSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=output_dir,
            action=action,
            output_conflict_action=conflict_action,
            task_timestamp=timestamp,
        )
        self.task.start(lambda log, progress: process_ids(settings, log, progress), output_dir)
