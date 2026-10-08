from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from g_file_studio.engines.transformer_fuse_engine import TARGET_MARKER
from g_file_studio.processors.transformer_fuse_processor import (
    TransformerFuseSettings,
    process_transformer_fuse,
)
from g_file_studio.services.id_rule_service import IdRuleService
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.remote_symbol_library import RemoteSymbolLibraryService
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, TaskPanel


_HELP_HTML = """
<h3>用途</h3>
<p>把服务器图元分类中标记为 <b>TRANSFORMER_OH</b> 的柱上变压器替换为模板中的“矩形框 + 熔断器 + 柱上变压器”完整组合。</p>
<h3>替换条件</h3>
<ul>
<li>只处理直属 &lt;TransformerDis&gt;；</li>
<li>只认本机已同步/确认的 TRANSFORMER_OH 分类，不根据文件名猜测；</li>
<li>柱上变压器两个端点中必须只有一个端点连接 ConnectLine/FeedLine；</li>
<li>旧图 reciprocal link 缺失时，会用同类图元已确认的 Pin 精确坐标识别真正接到端点的线路；</li>
<li>没有线路连接，或 Transformer 两个端点都已连接时，保持原图不变。</li>
</ul>
<h3>拓扑</h3>
<p>原外部线路的坐标完全不移动，只把原来接到 Transformer 的那个端点改接到 Fuse 空闲 Pin；
程序按模板对应方向整体复制 Merge、白色虚线矩形框、Fuse、Transformer_OH 和内部短 ConnectLine。</p>
<h3>安全</h3>
<p>服务器 G 文件始终只读。结果只写到本地 workspace 的独立运行目录。</p>
"""


class TransformerFusePage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        super().__init__(
            "柱上变压器熔断器替换",
            "将 TRANSFORMER_OH 替换为模板原样的完整矩形框组合；只处理仅有一个 Transformer 端点已连接的柱上变压器。",
            "柱上变压器熔断器替换帮助",
            _HELP_HTML,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "只使用主程序“图元管理”中已经确认的 TRANSFORMER_OH 分类。"
                "原外部 ConnectLine/FeedLine 几何坐标不移动；若 Transformer 只有一个端点已连接，"
                "程序按模板原样复制对应方向的完整矩形框组合，并把原线路端点改接到 Fuse 空闲端。"
                "旧图缺少 reciprocal link 时使用精确 Pin 坐标回退；两个端点均已连接的 Transformer 不处理。"
            )
        )

        io_box = QGroupBox("输入与输出")
        io_layout = QVBoxLayout(io_box)
        io_layout.setContentsMargins(12, 18, 12, 12)
        io_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一张需要执行 TRANSFORMER_OH 熔断器组合替换的 G 文件。",
            directory_tooltip="选择包含待处理 G 文件的目录；只扫描第一层。",
            settings_prefix="transformer_fuse",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)

        self.output_path = PathRow(
            directory=True,
            dialog_title="柱上变压器熔断器替换输出目录",
            recent_directory_key="recent_paths/transformer_fuse/output_directory",
            persistent_path_key="transformer_fuse/output_directory",
            default_path=default_workspace() / "runs" / "transformer-fuse",
            location_name="柱上变压器熔断器替换输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "transformer-fuse")
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录（workspace，只读）"))
        output_row.addWidget(self.output_path, 1)
        io_layout.addLayout(output_row)
        self.layout.addWidget(io_box)

        rule_box = QGroupBox("固定替换规则")
        rule_layout = QVBoxLayout(rule_box)
        rule_layout.setContentsMargins(16, 18, 16, 14)
        rule_layout.setSpacing(8)
        for text in (
            "✓ 1. 仅识别分类标记 TRANSFORMER_OH 对应的 <TransformerDis>",
            "✓ 2. 统计 Transformer 两个端点的实际拓扑；缺失 reciprocal link 时用同类图元 Pin 精确坐标回退",
            "✓ 3. 只有一个端点已连接：必须替换；两个端点均已连接：直接跳过",
            "✓ 4. 根据原线路末端方向选择模板的上 / 下 / 左 / 右完整矩形框组合",
            "✓ 5. Merge、白色虚线 rect、Fuse、Transformer、内部短 ConnectLine 按模板原样整体平移",
            "✓ 6. 原外部线路 d 坐标保持不变；原端点改接 Fuse 的空闲 Pin",
            "✓ 7. 保留原 Transformer 的 ID 与业务属性；新增 Merge/rect/Fuse/ConnectLine 使用全局已确认 ID 模板",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        self.marker_status = QLabel()
        self.marker_status.setObjectName("mutedText")
        self.marker_status.setWordWrap(True)
        rule_layout.addWidget(self.marker_status)
        self.layout.addWidget(rule_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始柱上变压器熔断器替换")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)
        self._refresh_marker_status()

    def _classification_marker_entries(self) -> tuple[tuple[str, str, str, str], ...]:
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
                    str(entry.get("element_id", "") or ""),
                )
                for entry in entries
                if str(entry.get("classification_marker", "") or "").strip()
            )
        except Exception:
            return ()

    def _refresh_marker_status(self) -> None:
        entries = self._classification_marker_entries()
        targets = [entry for entry in entries if entry[2].strip().casefold() == TARGET_MARKER.casefold()]
        if targets:
            names = ", ".join(sorted({entry[0] or entry[1] for entry in targets if entry[0] or entry[1]}))
            self.marker_status.setText(
                f"当前本地分类：TRANSFORMER_OH 共 {len(targets)} 条"
                + (f"（{names}）" if names else "")
            )
        else:
            self.marker_status.setText(
                "当前本地分类未找到 TRANSFORMER_OH；请先在主程序“图元管理”中刷新图元列表、确认分类并保存到本地缓存。"
            )

    def on_page_activated(self) -> None:
        self._refresh_marker_status()

    def run(self) -> None:
        if not validate_input_source(
            self,
            self.source,
            display_name="柱上变压器熔断器替换输入",
            log=self.task.append_log,
            progress=self.task.set_progress,
        ):
            return

        marker_entries = self._classification_marker_entries()
        target_entries = [
            entry for entry in marker_entries
            if entry[2].strip().casefold() == TARGET_MARKER.casefold()
        ]
        if not target_entries:
            QMessageBox.warning(
                self,
                "未配置 TRANSFORMER_OH",
                "当前本机已同步的图元分类中没有 TRANSFORMER_OH。\n\n"
                "请先在主程序“图元管理”中刷新或同步图元分类，并确认 TRANSFORMER_OH 标记已保存到本地缓存。",
            )
            return

        id_rules = IdRuleService().load_rules()
        missing_rules = [
            tag for tag in ("ZhaiWaiDaoZha", "ConnectLine")
            if tag not in id_rules or not id_rules[tag].enabled or not id_rules[tag].verified
        ]
        if missing_rules:
            QMessageBox.warning(
                self,
                "新增图元 ID 规则未确认",
                "本模块会新增 Fuse 与内部 ConnectLine，因此必须先确认以下全局 ID 规则：\n"
                + "\n".join(f"- <{tag}>" for tag in missing_rules)
                + "\n\n请先到“ID 检查与修复”完成确认。",
            )
            return

        self.source.persist_all_text()
        run_dir = begin_managed_run(self.output_path, "transformer-fuse", "replace")
        settings = TransformerFuseSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=run_dir,
            classification_marker_entries=tuple(marker_entries),
        )
        self.task.start(
            lambda log, progress: process_transformer_fuse(settings, log, progress),
            run_dir,
        )

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()
