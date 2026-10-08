from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from g_file_studio.jeddah import JeddahBatchSettings, process_jeddah_batch
from g_file_studio.i18n import LANG_ZH, tr_runtime
from g_file_studio.services.id_rule_service import IdRuleService
from g_file_studio.services.remote_symbol_library import (
    DEFAULT_REMOTE_SYMBOL_ROOT,
    RemoteSymbolLibraryService,
)
from g_file_studio.services.site_profile_service import (
    SiteProfileService,
    resolve_jeddah_classification_marker_roles,
    standard_catalog_from_server_records,
)
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_input_source
from g_file_studio.ui.widgets import (
    InfoBanner,
    InputSourceSelector,
    IntegerInput,
    PathRow,
    TaskPanel,
    TemplateSelector,
)


class _JeddahBatchTaskPanel(TaskPanel):
    """High-volume log panel used only by Jeddah Graphics Batch Processing.

    The shared TaskPanel intentionally keeps immediate per-line rendering for legacy
    modules.  A Jeddah run over hundreds of G files can produce thousands of worker
    messages, and the legacy path rebuilt the complete translated log after every
    line.  This opt-in panel batches UI rendering while preserving every raw line and
    does not alter any processor/business rule.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pending_batch_logs: list[str] = []
        self._batch_log_timer = QTimer(self)
        self._batch_log_timer.setSingleShot(True)
        self._batch_log_timer.setInterval(80)
        self._batch_log_timer.timeout.connect(self._flush_batch_logs)

    def append_log(self, text: str) -> None:
        if not text:
            return
        source = text.rstrip("\n")
        self._pending_batch_logs.extend(source.splitlines() or [source])
        # Bound the number of queued Qt paint/update operations even when a stage
        # emits hundreds of file-level messages almost instantly.
        if len(self._pending_batch_logs) >= 40:
            self._flush_batch_logs()
        elif not self._batch_log_timer.isActive():
            self._batch_log_timer.start()

    def _flush_batch_logs(self) -> None:
        if not self._pending_batch_logs:
            return
        self._batch_log_timer.stop()
        lines = self._pending_batch_logs
        self._pending_batch_logs = []
        self._raw_log_lines.extend(lines)

        language = LANG_ZH
        window = self.window()
        manager = getattr(window, "language_manager", None)
        if manager is not None:
            language = manager.language
        rendered_lines = [tr_runtime(line, language) for line in lines]
        self.log_view.appendPlainText("\n".join(rendered_lines))

        # Update the language-switch backing properties once per batch rather than
        # rebuilding/toPlainText() for every individual worker message.
        raw_addition = "\n".join(lines)
        rendered_addition = "\n".join(rendered_lines)
        old_raw = str(self.log_view.property("_i18n_plainText") or "")
        old_rendered = str(self.log_view.property("_i18n_plainText_rendered") or "")
        self.log_view.setProperty(
            "_i18n_plainText",
            old_raw + (("\n" if old_raw else "") + raw_addition if raw_addition else ""),
        )
        self.log_view.setProperty(
            "_i18n_plainText_rendered",
            old_rendered + (("\n" if old_rendered else "") + rendered_addition if rendered_addition else ""),
        )
        if manager is not None:
            for source, rendered in zip(lines, rendered_lines):
                if rendered != source:
                    manager.remember_runtime_translation(source, rendered)

    def log_view_clear(self) -> None:
        self._batch_log_timer.stop()
        self._pending_batch_logs.clear()
        super().log_view_clear()

    def on_result(self, result) -> None:
        self._flush_batch_logs()
        super().on_result(result)
        self._flush_batch_logs()

    def on_error(self, traceback_text: str) -> None:
        self._flush_batch_logs()
        super().on_error(traceback_text)
        self._flush_batch_logs()

    def on_finished(self) -> None:
        self._flush_batch_logs()
        super().on_finished()



class JeddahBatchPage(BasePage):
    """Jeddah-only one-click feeder cleanup page.

    The page does not replace or alter any existing module.  It only invokes the
    existing processors/engines in a fixed Jeddah workflow and owns its site-specific
    parameters under the ``jeddah_batch`` settings namespace.
    """

    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        help_title, help_html = APP_HELP["jeddah_batch"]
        super().__init__(
            "吉达图形批处理",
            "面向吉达现场的单馈线图一键标准化：批量输入多个 G 文件，逐张完成固定处理并输出最终单馈线图。",
            help_title,
            help_html,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "本模块是 Jeddah 专用批处理入口，不修改现有异常元素、RMU、基础处理或 ID 模块的业务逻辑。"
                "程序按固定顺序调用已有处理能力；原始输入文件不会覆盖，最终结果写入本次 workspace 运行目录。"
            )
        )

        io_box = QGroupBox("输入与输出")
        io_layout = QVBoxLayout(io_box)
        io_layout.setContentsMargins(12, 18, 12, 12)
        io_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            directory_tooltip="选择包含需要执行吉达批处理的单馈线 G 文件目录。",
            file_tooltip="也可只选择一张单馈线 G 文件进行吉达标准处理。",
            settings_prefix="jeddah_batch",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)

        self.output_path = PathRow(
            directory=True,
            dialog_title="吉达批处理输出目录",
            recent_directory_key="recent_paths/jeddah_batch/output_directory",
            persistent_path_key="jeddah_batch/output_directory",
            default_path=default_workspace() / "runs" / "jeddah-batch",
            location_name="吉达批处理输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "jeddah-batch")
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录（workspace，只读）"))
        output_row.addWidget(self.output_path, 1)
        io_layout.addLayout(output_row)
        self.layout.addWidget(io_box)

        pipeline_box = QGroupBox("Jeddah 固定处理流程")
        pipeline_layout = QVBoxLayout(pipeline_box)
        pipeline_layout.setContentsMargins(16, 18, 16, 14)
        pipeline_layout.setSpacing(8)
        for text in (
            "✓ 1. 彻底取消图形组合（删除全部 <Merge>，并将 RMU 外框置底）",
            "✓ 2. 删除异常小尺寸元素",
            "✓ 3. 已识别 RMU 名称统一改白、字号 50，并在环网柜上边框上方 10 距离处水平居中",
            "✓ 4. RMU 外框最终一致性：柜内有 SMART = 红色；柜内无 SMART = 白色",
            "✓ 5. RMU 图元类型先看原图元 devref/文件名：Circuit_Breaker → Circuit Breaker，Load_Breaker_Switch → LBS；柜内 SMART 文字只决定换 SMART 还是 NO-SMART",
            "✓ 6. SMR 环网柜外框统一刷成红色",
            "✓ 7. SMR 条件转换 SMART：已有 SMART 时删除外部 SMR并保持原 SMART；没有 SMART 时生成顶部居中 SMART（字号 20）；外框强制红色",
            "✓ 8. SMR 转换后再次执行 SMART 图元检查，确保 LBS / Circuit Breaker devref 正确",
            "✓ 9. 使用已保存的四个分类标记严格纠正 RMU 图元：原图元名称含 Circuit_Breaker 就按 Circuit Breaker 处理，含 Load_Breaker_Switch 就按 LBS 处理；柜内有 SMART 时分别换成 CIRCUIT_BREAKER_SMART / LOAD_BREAKER_SWITCH_SMART，无 SMART 时分别换成 CIRCUIT_BREAKER_NO_SMART / LOAD_BREAKER_SWITCH_NO_SMART；Y/Q 名称不覆盖原图元类型，且不再参考同图其他柜猜版本；<ZhaiWaiJieDiDaoZha> 接地刀闸保持不换。",
            "✓ 10. 删除 RMU 红色状态点（channel_status），沿用现有状态点识别/归属规则",
            "✓ 11. 删除带 Bus 的环网柜矩形框、上移标题，并将有效配网 BusDis 母线统一刷为蓝色（无关联时 keyid 兜底）",
            "✓ 12. 将馈线名称移动到母线上方",
            "✓ 13. 删除精确 H.T 文字标识",
            "✓ 14. 检查所有已识别配网 RMU；同一柜内存在多个 SMART 时仅保留原有第一个，删除重复项",
            "✓ 15. 仅当 2000.00 与 UPDATED_MEASURMENT 两个 Text 同行且相邻时成对删除",
            "✓ 16. 使用全局 ID 模板执行 ID 检查与修复",
            "✓ 17. 调整主体图形四边距（默认 500）",
            "✓ 18. 添加图框",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            pipeline_layout.addWidget(label)
        note = QLabel("以上步骤为吉达固定流程，本页不复制或重写现有模块算法。")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        pipeline_layout.addWidget(note)
        self.layout.addWidget(pipeline_box)

        settings_box = QGroupBox("吉达参数")
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.setContentsMargins(16, 18, 16, 14)
        settings_layout.setSpacing(10)

        self.profile_service = SiteProfileService()

        threshold_form = QFormLayout()
        self.threshold = IntegerInput(
            value=self.user_settings.get_int("jeddah_batch/small_element_threshold", 10),
            minimum=1,
            maximum=100000,
        )
        self.threshold.setToolTip("当目标元素的 w 和 h 同时小于该值时，吉达批处理自动删除该异常小尺寸元素。")
        threshold_form.addRow("异常小尺寸阈值", self.threshold)
        settings_layout.addLayout(threshold_form)

        auto_name_note = QLabel(
            "RMU 柜名识别：严格检查有效环网柜，并且只从环网柜外框正上方的 Text 按一对一规则分配；"
            "没有匹配到上方名称时保持为空。"
        )
        auto_name_note.setObjectName("mutedText")
        auto_name_note.setWordWrap(True)
        settings_layout.addWidget(auto_name_note)

        exclusion_row = QHBoxLayout()
        exclusion_row.addWidget(QLabel("RMU 柜名排除字符串："))
        self.name_exclusions = QLineEdit(
            self.user_settings.get_value("jeddah_batch/rmu_name_exclusions", "NOP, DAS/OK, SFI")
        )
        self.name_exclusions.setPlaceholderText("例如：NOP, DAS/OK, SFI")
        self.name_exclusions.setToolTip(
            "使用逗号、分号或换行分隔；按完整字符串匹配并忽略大小写，不使用包含匹配。"
        )
        exclusion_row.addWidget(self.name_exclusions, 1)
        settings_layout.addLayout(exclusion_row)

        color_note = QLabel(
            "吉达固定样式：最终 RMU 外框按柜内 SMART 文字决定——有 SMART = 红色 #FF0000，无 SMART = 白色 #FFFFFF；原图元名称含 Load_Breaker_Switch 的设备按 LBS 处理、含 Circuit_Breaker 的设备按 Circuit Breaker 处理（Y/Q 名称不覆盖原图元类型）；有 SMART 的柜必须使用分类标记 LOAD_BREAKER_SWITCH_SMART / CIRCUIT_BREAKER_SMART 指向的智能图元，无 SMART 的柜必须使用分类标记 CIRCUIT_BREAKER_NO_SMART / LOAD_BREAKER_SWITCH_NO_SMART 指向的非智能图元；若 SMR 柜内已有 SMART，只删除外部 SMR并保留原 SMART；若柜内没有 SMART，则生成顶部居中 SMART（字号 20）；SMR 处理后再次复检；接地刀闸保持现有吉达规则不替换；已识别 RMU 柜名 Text = 白色 #FFFFFF、字号 50，并与环网柜上边框保持 10 距离且水平居中；RMU channel_status 红色状态点直接删除；有效配网 BusDis 母线 = 蓝色 #0000FF；精确 H.T Text = 删除；同柜多个 SMART 时保留原有第一个并删除后续重复；2000.00 与 UPDATED_MEASURMENT 只有在同行且相邻时才成对删除。"
        )
        color_note.setObjectName("mutedText")
        color_note.setWordWrap(True)
        settings_layout.addWidget(color_note)
        self.layout.addWidget(settings_box)

        margin_box = QGroupBox("吉达图形边距")
        margin_form = QFormLayout(margin_box)
        margin_form.setHorizontalSpacing(16)
        margin_form.setVerticalSpacing(10)
        self.margin_left = IntegerInput(
            value=self.user_settings.get_int("jeddah_batch/margin_left", 500),
            minimum=0,
            maximum=100000,
        )
        self.margin_top = IntegerInput(
            value=self.user_settings.get_int("jeddah_batch/margin_top", 500),
            minimum=0,
            maximum=100000,
        )
        self.margin_right = IntegerInput(
            value=self.user_settings.get_int("jeddah_batch/margin_right", 500),
            minimum=0,
            maximum=100000,
        )
        self.margin_bottom = IntegerInput(
            value=self.user_settings.get_int("jeddah_batch/margin_bottom", 500),
            minimum=0,
            maximum=100000,
        )
        margin_form.addRow("图形左边距", self.margin_left)
        margin_form.addRow("图形上边距", self.margin_top)
        margin_form.addRow("图形右边距", self.margin_right)
        margin_form.addRow("图形下边距", self.margin_bottom)
        self.layout.addWidget(margin_box)

        frame_box = QGroupBox("吉达图框")
        frame_layout = QVBoxLayout(frame_box)
        frame_layout.setContentsMargins(12, 18, 12, 12)
        frame_layout.setSpacing(9)
        frame_note = QLabel(
            "图形边距调整完成后，直接调用现有“图框添加”处理能力。当前选择的模板就是最终权威模板；"
            "如果输入 G 已有旧图框（包括非内置或与当前模板不同的图框），程序会直接删除旧图框并强制覆盖，"
            "不再要求人工先删除或再次确认。默认使用程序内置模板；内置模板标题留空时自动使用输入文件名。"
        )
        frame_note.setObjectName("mutedText")
        frame_note.setWordWrap(True)
        frame_layout.addWidget(frame_note)
        self.template_selector = TemplateSelector(
            settings_prefix="jeddah_batch/frame",
            settings_service=self.user_settings,
        )
        frame_layout.addWidget(self.template_selector)
        self.layout.addWidget(frame_box)

        # Jeddah batch can emit thousands of file-level log lines for 100~300+
        # drawings. Use an isolated buffered UI panel so the shared TaskPanel and
        # every standalone graphics module retain their established behaviour.
        self.task = _JeddahBatchTaskPanel()
        self.task.run_button.setText("开始吉达批处理")
        self.task.run_button.setToolTip("按上方固定 Jeddah 流程批量处理所选单馈线 G 文件。")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)

    @staticmethod
    def _is_jeddah_profile(profile) -> bool:
        site_key = str(getattr(profile, "site_name", "") or "").strip().upper()
        return site_key.startswith("JED") or "JEDDAH" in site_key

    def refresh_profiles(self, preferred_name: str = "") -> None:
        """Compatibility hook; the page now reads the current server standard at run time."""
        del preferred_name

    def on_page_activated(self) -> None:
        """Page-navigation hook: always show the shared current server standard."""
        self.refresh_profiles()

    def _cached_server_standard_records(self) -> tuple[dict[str, object], ...]:
        """Return the already-synchronized server symbol definitions from AppData.

        Jeddah batch execution is intentionally offline: it must never open SSH on
        Run.  A normal client only needs to sync the server-symbol page once; the
        batch then uses that same local cache directly.
        """
        try:
            cfg = self.source.remote.config()
            host = str(cfg.get("host", "")).strip()
            root = self.user_settings.get_value(
                "site_profile/remote_symbol_library_root", ""
            ).strip()
            if not host or not root:
                return ()
            snapshot = RemoteSymbolLibraryService().load_cached_sync_snapshot(
                host=host,
                root=root,
            )
            if not isinstance(snapshot, dict):
                return ()

            # v2.18.249: use the same physical READY inventory that the
            # Main DMM Element Management catalog is the authoritative inventory. Older AppData snapshots may
            # have a legacy ``matched_records`` entry without nested sha256 even
            # though its physical server-file row is READY and has the hash.
            # Feeding that old matched record into the standard catalog makes the
            # catalog drop it and produces the misleading “target not in current
            # server standard” warning seen by operators.
            records: list[dict[str, object]] = []
            rows = snapshot.get("server_file_records", [])
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    status = str(row.get("sync_status", "READY") or "READY").strip().upper()
                    if status not in {"", "READY"}:
                        continue
                    standard = row.get("standard_record", {})
                    if not isinstance(standard, dict):
                        continue
                    merged = dict(standard)
                    if not str(merged.get("devref", "") or "").strip():
                        continue
                    backfill = {
                        "sha256": row.get("sha256", ""),
                        "original_name": row.get("name", ""),
                        "cache_path": row.get("cache_path", ""),
                        "remote_host": row.get("remote_host", host),
                        "remote_root": row.get("remote_root", root),
                        "remote_path": row.get("remote_path", ""),
                        "relative_path": row.get("relative_path", ""),
                        "remote_size": row.get("size", 0),
                        "remote_mtime": row.get("mtime_epoch", 0),
                    }
                    for field, value in backfill.items():
                        if not str(merged.get(field, "") or "").strip() and value not in (None, ""):
                            merged[field] = value
                    records.append(merged)
            if records:
                return tuple(records)

            # Compatibility fallback for very old caches that do not contain the
            # physical inventory array at all.
            matched = snapshot.get("matched_records", {})
            if not isinstance(matched, dict):
                return ()
            return tuple(
                dict(record)
                for record in matched.values()
                if isinstance(record, dict) and str(record.get("devref", "") or "").strip()
            )
        except Exception:
            return ()

    def _classification_marker_entries(self) -> tuple[tuple[str, str, str], ...]:
        """Read the locally saved server-symbol classification markers.

        Jeddah target selection is intentionally offline/read-only at run time: the
        operator first saves the four target markers in main DMM Element Management;
        this page then consumes that local cache without reconnecting to the server.
        """
        try:
            cfg = self.source.remote.config()
            host = str(cfg.get("host", "")).strip()
            root = self.user_settings.get_value(
                "site_profile/remote_symbol_library_root", ""
            ).strip()
            if not host or not root:
                return ()
            entries = RemoteSymbolLibraryService().load_classification_marker_entries(
                host=host,
                root=root,
            )
            return tuple(
                (
                    str(entry.get("file_name", "") or ""),
                    str(entry.get("devref", "") or ""),
                    str(entry.get("classification_marker", "") or ""),
                )
                for entry in entries
                if str(entry.get("classification_marker", "") or "").strip()
            )
        except Exception:
            return ()


    def _persist(self) -> None:
        self.source.persist_all_text()
        # Jeddah uses the already-synchronized local server-symbol cache directly.
        self.user_settings.set_value("jeddah_batch/small_element_threshold", self.threshold.value())
        self.user_settings.set_value("jeddah_batch/rmu_name_exclusions", self.name_exclusions.text().strip())
        self.user_settings.set_value("jeddah_batch/margin_left", self.margin_left.value())
        self.user_settings.set_value("jeddah_batch/margin_top", self.margin_top.value())
        self.user_settings.set_value("jeddah_batch/margin_right", self.margin_right.value())
        self.user_settings.set_value("jeddah_batch/margin_bottom", self.margin_bottom.value())
        self.template_selector.persist_current()

    def run(self) -> None:
        # Standard definitions may have changed while this page was open. Reload
        # before validation so execution can never use a stale combo entry.
        self.refresh_profiles()
        if not validate_input_source(
            self,
            self.source,
            display_name="吉达批处理输入",
            log=self.task.append_log,
        ):
            return
        if not self.template_selector.validate_selection():
            return
        if not IdRuleService().load_rules():
            QMessageBox.warning(
                self,
                "全局 ID 模板未配置",
                "吉达批处理的 ID 处理阶段必须使用全局 ID 模板。请先在“ID 检查与修复”模块中确认 ID 规则。",
            )
            return
        # v2.18.248: the public server-symbol page is the source of truth.  Do not
        # require the retired hidden Profile/global-selection workflow here.  This
        # also makes a freshly configured normal client runnable after it has
        # synchronized the server symbol catalog and central classification.
        server_standard_records = self._cached_server_standard_records()
        if not server_standard_records:
            QMessageBox.warning(
                self,
                "主程序图元缓存不可用",
                "当前本机没有可用的服务器图元缓存。\n\n"
                "请先到主程序“图元管理”点击“刷新图元列表”，确认分类后点击“保存到本地缓存”，再执行吉达批处理。",
            )
            return

        classification_marker_entries = self._classification_marker_entries()
        marker_roles, marker_issues = resolve_jeddah_classification_marker_roles(
            classification_marker_entries
        )
        if marker_issues:
            QMessageBox.warning(
                self,
                "吉达图元分类标记不完整",
                "吉达图形批处理只认主程序“图元管理”中保存的以下四个分类标记：\n"
                "- CIRCUIT_BREAKER_SMART\n"
                "- LOAD_BREAKER_SWITCH_SMART\n"
                "- CIRCUIT_BREAKER_NO_SMART\n"
                "- LOAD_BREAKER_SWITCH_NO_SMART\n\n"
                + "当前问题：\n"
                + "\n".join(f"- {item}" for item in marker_issues)
                + "\n\n请先将分类标记保存到本地，再执行吉达批处理。",
            )
            return

        standard_catalog = standard_catalog_from_server_records(list(server_standard_records))
        standard_keys = {str(key).strip().casefold() for key in standard_catalog if str(key).strip()}
        missing_targets = [
            target
            for key, target in marker_roles.items()
            if key in {"smart_lbs", "smart_breaker", "normal_lbs", "normal_breaker"}
            and target
            and target.casefold() not in standard_keys
        ]
        if missing_targets:
            QMessageBox.warning(
                self,
                "分类标记目标不在当前服务器标准",
                "以下已标记图元不在当前已应用的服务器标准版本中：\n"
                + "\n".join(f"- {item}" for item in missing_targets)
                + "\n\n请先在主程序“图元管理”刷新图元列表、确认分类标记并保存到本地缓存后再执行。",
            )
            return

        self._persist()
        run_dir = begin_managed_run(self.output_path, "jeddah-batch", "process")
        settings = JeddahBatchSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=run_dir,
            small_element_threshold=self.threshold.value(),
            rmu_name_exclusions=self.name_exclusions.text().strip(),
            margin_left=self.margin_left.value(),
            margin_top=self.margin_top.value(),
            margin_right=self.margin_right.value(),
            margin_bottom=self.margin_bottom.value(),
            frame_template_file=self.template_selector.resolved_template_path(),
            frame_template_mode=self.template_selector.mode(),
            frame_builtin_template_id=self.template_selector.builtin_template_id(),
            rmu_profile_name="",
            rmu_profile_version=None,
            classification_marker_entries=classification_marker_entries,
            server_standard_records=tuple(server_standard_records),
        )
        self.task.start(
            lambda log, progress: process_jeddah_batch(settings, log, progress),
            run_dir,
        )

    def save_state(self) -> None:
        self._persist()
        self.output_path.persist_current_text()
