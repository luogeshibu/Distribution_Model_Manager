from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.ui.widgets.help_widgets import HelpButton, set_secondary
from g_file_studio.i18n import LANG_ZH, tr_runtime
from g_file_studio.services.run_history import update_run_status
from g_file_studio.workers import FunctionWorker


class TaskPanel(QFrame):
    busyChanged = Signal(bool)
    resultReceived = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("taskPanel")
        self.thread_pool = QThreadPool.globalInstance()
        self._output_dir: Path | None = None
        self._raw_log_lines: list[str] = []
        self._show_result_dialogs = True
        self._live_progress_enabled = False
        self._task_running = False
        self._progress_busy_active = False
        self._last_progress_value = 0
        self._progress_stall_timer = QTimer(self)
        self._progress_stall_timer.setSingleShot(True)
        self._progress_stall_timer.setInterval(900)
        self._progress_stall_timer.timeout.connect(self._enter_progress_busy_state)
        # Optional display-side smoothing. Worker progress remains authoritative,
        # but high-frequency worker signals update only the target value so the
        # QProgressBar is repainted at a stable cadence instead of flashing through
        # queued values. This is opt-in because most legacy modules already have
        # their own established progress behaviour.
        # All task panels use a determinate 0~100% display with smooth visual
        # progression.  The worker percentage remains authoritative; smoothing
        # only controls how quickly the bar catches up on screen.
        self._smooth_progress_enabled = True
        self._smooth_progress_target = 0
        self._smooth_progress_display = 0
        self._smooth_progress_timer = QTimer(self)
        self._smooth_progress_timer.setInterval(30)
        self._smooth_progress_timer.timeout.connect(self._advance_smooth_progress)

        self.run_button = QPushButton("开始执行")
        self.run_button.setToolTip("按照当前页面参数开始处理。处理会在后台线程中运行。")
        self.run_button.setStatusTip(self.run_button.toolTip())

        self.open_button = QPushButton("打开本次运行目录")
        set_secondary(self.open_button)
        self.open_button.setToolTip("打开本次任务对应的 workspace 运行目录。运行记录仅保留 30 天。")
        self.open_button.setStatusTip(self.open_button.toolTip())
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_output)

        self.clear_button = QPushButton("清空日志")
        set_secondary(self.clear_button)
        self.clear_button.setToolTip("清空当前页面的执行日志，不会删除任何文件。")
        self.clear_button.clicked.connect(self.log_view_clear)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setToolTip("显示当前处理任务的总体进度。")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setPlaceholderText("处理日志会显示在这里……")
        self.log_view.setMinimumHeight(170)

        title_row = QHBoxLayout()
        title = QLabel("执行与日志")
        title.setObjectName("panelTitle")
        title_row.addWidget(title)
        title_row.addWidget(
            HelpButton(
                "执行与日志",
                "<p>点击“开始执行”后，任务会在后台运行。进度条显示总体进度，详细处理过程显示在日志区域。处理失败时请复制日志中的错误信息进行排查。</p>",
            )
        )
        title_row.addStretch(1)

        buttons = QHBoxLayout()
        self.buttons_layout = buttons
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(title_row)
        layout.addLayout(buttons)
        layout.addWidget(self.progress)
        layout.addWidget(self.log_view, 1)

    def set_result_dialogs_enabled(self, enabled: bool) -> None:
        """Allow pages with domain-specific completion dialogs to suppress the generic popup."""
        self._show_result_dialogs = bool(enabled)

    def set_smooth_progress_enabled(self, enabled: bool) -> None:
        """Render determinate progress monotonically at a stable cadence.

        The worker's percentage is still the source of truth.  Enabling this does
        not invent progress and never lets the displayed value move backwards; it
        only decouples frequent worker signals from QProgressBar repaints.
        """
        self._smooth_progress_enabled = bool(enabled)
        self._smooth_progress_timer.stop()
        current = max(0, min(100, int(self.progress.value())))
        self._smooth_progress_display = current
        self._smooth_progress_target = max(current, int(self._last_progress_value))
        if self._smooth_progress_enabled and self._smooth_progress_target > current:
            self._smooth_progress_timer.start()

    def _advance_smooth_progress(self) -> None:
        if not self._smooth_progress_enabled:
            self._smooth_progress_timer.stop()
            return
        current = max(0, min(100, int(self._smooth_progress_display)))
        target = max(current, min(100, int(self._smooth_progress_target)))
        if current >= target:
            self._smooth_progress_timer.stop()
            return
        # Move by only one or two percentage points per paint.  Large worker jumps
        # therefore become a short, continuous rise instead of a burst/flicker,
        # while small real-time updates still appear promptly.
        delta = target - current
        step = 2 if delta >= 18 else 1
        current = min(target, current + step)
        self._smooth_progress_display = current
        self.progress.setValue(current)
        if current >= target:
            self._smooth_progress_timer.stop()

    def set_live_progress_enabled(self, enabled: bool) -> None:
        """Keep the compatibility API while enforcing the common 0~100% style.

        Indeterminate Qt busy bars are intentionally disabled globally. Long
        phases keep the last determinate percentage and the smooth display remains
        monotonic until the worker reports the next value.
        """
        del enabled
        self._live_progress_enabled = False
        self._progress_stall_timer.stop()
        self._restore_determinate_progress()

    def _restore_determinate_progress(self) -> None:
        if self._progress_busy_active or self.progress.minimum() == 0 and self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self._progress_busy_active = False
        self.progress.setFormat("%p%")
        value = self._smooth_progress_display if self._smooth_progress_enabled else self._last_progress_value
        self.progress.setValue(max(0, min(100, int(value))))

    def _enter_progress_busy_state(self) -> None:
        # Kept as a timer-slot compatibility shim.  All progress bars are now
        # determinate 0~100% bars; never switch to Qt's indeterminate range.
        return

    def _on_worker_progress(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        # Progress is monotonic for a single task.  Ignore late/out-of-order queued
        # signals rather than letting the bar jump backwards and visually flash.
        value = max(int(self._last_progress_value), value)
        self._last_progress_value = value
        if self._progress_busy_active:
            self.progress.setRange(0, 100)
            self._progress_busy_active = False
            self.progress.setFormat("%p%")
        if self._smooth_progress_enabled:
            self._smooth_progress_target = max(int(self._smooth_progress_target), value)
            if self._smooth_progress_display < self._smooth_progress_target and not self._smooth_progress_timer.isActive():
                self._smooth_progress_timer.start()
        else:
            self.progress.setValue(value)
        if self._live_progress_enabled and self._task_running and value < 100:
            self._progress_stall_timer.start()
        else:
            self._progress_stall_timer.stop()

    def log_view_clear(self) -> None:
        self._raw_log_lines.clear()
        self.log_view.clear()
        self.log_view.setProperty("_i18n_plainText", "")
        self.log_view.setProperty("_i18n_plainText_rendered", "")

    def append_log(self, text: str) -> None:
        if text:
            source = text.rstrip("\n")
            self._raw_log_lines.append(source)
            language = LANG_ZH
            window = self.window()
            manager = getattr(window, "language_manager", None)
            if manager is not None:
                language = manager.language
            rendered = tr_runtime(source, language)
            self.log_view.appendPlainText(rendered)
            # Store the untouched source log on the widget so switching languages
            # rerenders text only and never affects worker/business output.
            raw_text = "\n".join(self._raw_log_lines)
            self.log_view.setProperty("_i18n_plainText", raw_text)
            self.log_view.setProperty("_i18n_plainText_rendered", self.log_view.toPlainText())
            if manager is not None and rendered != source:
                manager.remember_runtime_translation(source, rendered)

    def start(self, function, output_dir: Path) -> None:
        self.log_view_clear()
        self._task_running = True
        self._last_progress_value = 0
        self._progress_stall_timer.stop()
        self._smooth_progress_timer.stop()
        self._smooth_progress_target = 0
        self._smooth_progress_display = 0
        self._restore_determinate_progress()
        self.progress.setValue(0)
        self.run_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.busyChanged.emit(True)
        self._output_dir = Path(output_dir)
        self.append_log("任务已启动……")

        worker = FunctionWorker(function)
        worker.signals.log.connect(self.append_log)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.result.connect(self.on_result)
        worker.signals.error.connect(self.on_error)
        worker.signals.finished.connect(self.on_finished)
        if self._live_progress_enabled:
            self._progress_stall_timer.start()
        self.thread_pool.start(worker)

    def set_progress(self, value: int) -> None:
        """Accept direct page progress updates through the same smooth path."""
        self._on_worker_progress(value)

    def on_finished(self) -> None:
        self._task_running = False
        self._progress_stall_timer.stop()
        self._restore_determinate_progress()
        self.run_button.setEnabled(True)
        self.busyChanged.emit(False)

    def on_result(self, result) -> None:
        self._on_worker_progress(100)
        self.resultReceived.emit(result)
        self.append_log("\n处理完成。")
        for path in result.output_files:
            self.append_log(f"输出：{path}")
        if result.warnings:
            self.append_log("告警：")
            for warning in result.warnings:
                self.append_log(f"  {warning}")
        if result.statistics:
            self.append_log("统计：")
            for key, value in result.statistics.items():
                if str(key).startswith("_"):
                    continue
                self.append_log(f"  {key}: {value}")
        self.open_button.setEnabled(True)
        if self._output_dir:
            update_run_status(self._output_dir, "SUCCESS" if result.success else "WARNING")
        if self._show_result_dialogs:
            if result.success:
                QMessageBox.information(self, "处理完成", "任务已成功完成，详细结果请查看日志。")
            else:
                QMessageBox.warning(
                    self,
                    "处理完成（有告警）",
                    "任务已完成，但部分文件处理失败或存在告警，请查看日志和报告。",
                )

    def on_error(self, traceback_text: str) -> None:
        self._progress_stall_timer.stop()
        self._smooth_progress_timer.stop()
        self._restore_determinate_progress()
        if self._output_dir:
            update_run_status(self._output_dir, "FAILED", note=traceback_text.split("\n", 1)[0])
        self.open_button.setEnabled(bool(self._output_dir))
        self.append_log("\n处理失败：")
        self.append_log(traceback_text)
        user_message = traceback_text.split("\n\n---TRACEBACK---", 1)[0].strip()
        QMessageBox.critical(
            self,
            "处理失败",
            user_message or "处理过程中发生错误，详情请查看日志区域。",
        )

    def open_output(self) -> None:
        if self._output_dir:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_dir.resolve())))
