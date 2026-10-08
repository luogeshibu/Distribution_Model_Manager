from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from g_file_studio.models import InputMode
from g_file_studio.processors.whole_graph_topology_processor import (
    WholeGraphTopologySettings,
    process_whole_graph_topology,
)
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, TaskPanel


_HELP_HTML = """
<h3>用途</h3>
<p>吉达只做 <b>G 图拓扑连接完整性检查与修复</b>：检查线路端点是否真正接上。发现能够唯一判断的断点后，直接在安全副本中修复。</p>
<p>支持单个 G，也支持目录/SSH 快照中的多个 G。批量模式按文件逐个处理：每个 G 独立生成 HTML/CSV、修复前完整 G 图、修复后完整 G 图和修复后安全副本，并额外生成一个总 HTML/CSV 汇总报告；某一个文件失败不会中断后续文件。</p>
<h3>明确不做</h3>
<ul>
<li>不判断任何设备属于哪条馈线。</li>
<li>不识别 NOP，也不按 NOP 截断拓扑。</li>
<li>不读取 Bus 上方馈线名称。</li>
<li>不连接 Oracle，不查模型库。</li>
</ul>
<h3>连接检查与修复</h3>
<p>扫描 ConnectLine / FeedLine 的未连接端点。ConnectLine↔FeedLine 在双方互为唯一最近邻且距离不超过 25G 时可自动修复；ConnectLine↔ConnectLine 只处理 ≤3G 的同轴微小断口。</p>
<p>这个 3G 限制用于保护开关图元：开关触点内部常见约 18G 的正常断口不会被连接。修复时优先延伸 FeedLine；微小 ConnectLine 断口只闭合相邻同轴端点，并同步补齐双方 link/node_area。</p>
<h3>安全</h3>
<p>原始 G 永不覆盖；只生成新的 *.topology-fixed.sln.pic.g。无法唯一判断的连接只进入报告，不猜测、不误连。单文件 HTML 必须同时显示“修复前完整 G 图”和“修复后完整 G 图”：直接按 G 的原始画布、坐标、文字、线条、RMU 框和图元重绘，修复前图再用红色/橙色编号叠加问题位置，不能用抽象拓扑草图代替。</p>
"""


class WholeGraphTopologyPage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        self._html_report: Path | None = None
        super().__init__(
            "整图拓扑连接检查/修复",
            "吉达只检查 G 图连接是否断开并自动修复；不判断馈线、不识别 NOP、不读取 Bus 馈线名、不查数据库。",
            "整图拓扑连接检查/修复帮助",
            _HELP_HTML,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "纯 G 图连接检查：不判断馈线、不识别 NOP、不读取 Bus 名称、不连接 Oracle/数据库。"
                "发现双方互为唯一近邻的小断点后直接修复到新的安全副本，原始 G 永不覆盖。"
            )
        )

        io_box = QGroupBox("输入与输出")
        io_layout = QVBoxLayout(io_box)
        io_layout.setContentsMargins(12, 18, 12, 12)
        io_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            default_mode=InputMode.SINGLE_FILE,
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一张需要检查/修复拓扑连接的 G 文件。",
            directory_tooltip="选择包含一个或多个 G 文件的目录；将逐个独立检查/修复，并生成单文件报告和总汇总报告。",
            settings_prefix="whole_graph_topology",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)

        self.output_path = PathRow(
            directory=True,
            dialog_title="整图拓扑连接检查输出目录",
            recent_directory_key="recent_paths/whole_graph_topology/output_directory",
            persistent_path_key="whole_graph_topology/output_directory",
            default_path=default_workspace() / "runs" / "whole-graph-topology",
            location_name="整图拓扑连接检查输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "whole-graph-topology")
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录（workspace，只读）"))
        output_row.addWidget(self.output_path, 1)
        io_layout.addLayout(output_row)
        self.layout.addWidget(io_box)

        rule_box = QGroupBox("吉达整图拓扑连接检查/修复规则")
        rule_layout = QVBoxLayout(rule_box)
        rule_layout.setContentsMargins(16, 18, 16, 14)
        rule_layout.setSpacing(8)
        rules = (
            "✓ 1. 支持单个 G 或批量目录/SSH 快照；多个 G 按文件逐个独立处理，只读取 G XML 自身，不连接 Oracle、不查模型库。",
            "✓ 2. 不判断馈线归属，不找主网馈线名，不读取 Bus 上方名称；整张图没有任何馈线传播过程。",
            "✓ 3. 不识别 NOP、不设置 NOP 边界；这里只关心线路物理/拓扑连接有没有断开。",
            "✓ 4. 重点检查 ConnectLine ↔ FeedLine 的端点连接，同时处理 ≤3G 的同轴 ConnectLine ↔ ConnectLine 微小断口；检查几何坐标和 link/node_area 是否完整。",
            "✓ 5. 只有待修复端点没有现有连接、线路另一端已经接入真实拓扑时，才把它作为断点候选，避免把装饰线或自由线段误连。",
            "✓ 6. ConnectLine ↔ FeedLine 自动修复要求互为唯一最近邻且距离 ≤25G；ConnectLine ↔ ConnectLine 仅允许 ≤3G 且同轴，约 18G 的开关正常触点断口绝不连接。",
            "✓ 7. 有可见几何断口时优先正交延伸 FeedLine 到 ConnectLine；坐标已重合但 link/node_area 缺失时只补拓扑引用。",
            "✓ 8. 修复后再次扫描；所有已自动修复的端点都必须从断点候选中消失。原始 G 永不覆盖。",
            "✓ 9. 每个 G 都输出独立 HTML/CSV、修复前完整 G 图、修复后完整 G 图和可选修复后 G；两张图必须按 G 原始坐标和图元内容重绘，修复前图再直接标出问题位置。批量时额外生成总 HTML/CSV 汇总，某个文件失败会记录后继续。",
        )
        for text in rules:
            label = QLabel(text)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        self.layout.addWidget(rule_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始整图拓扑检查 / 批量自动修复")
        self.task.run_button.clicked.connect(self.run)
        self.task.resultReceived.connect(self._on_result)
        self.open_report_button = QPushButton("打开汇总/拓扑报告")
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report)
        self.task.buttons_layout.insertWidget(1, self.open_report_button)
        self.layout.addWidget(self.task, 1)

    def run(self) -> None:
        self._html_report = None
        self.open_report_button.setEnabled(False)
        if not validate_input_source(
            self,
            self.source,
            display_name="整图拓扑连接检查输入",
            log=self.task.append_log,
            progress=self.task.set_progress,
        ):
            return

        self.source.persist_all_text()
        run_dir = begin_managed_run(self.output_path, "whole-graph-topology", "repair")
        settings = WholeGraphTopologySettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=run_dir,
        )
        self.task.start(
            lambda log, progress: process_whole_graph_topology(settings, log, progress),
            run_dir,
        )

    def _on_result(self, result) -> None:
        report_value = str(result.statistics.get("_html_report", "") or "").strip()
        if report_value:
            path = Path(report_value)
            if path.is_file():
                self._html_report = path
                self.open_report_button.setEnabled(True)

    def _open_report(self) -> None:
        if self._html_report is None or not self._html_report.is_file():
            QMessageBox.warning(self, "暂无报告", "请先执行一次整图拓扑连接检查/修复。批量模式完成后会打开总汇总报告。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._html_report.resolve())))

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()
