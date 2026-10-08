from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QVBoxLayout

from g_file_studio.models import InputMode, OrthogonalizeSettings
from g_file_studio.processors.orthogonalize_processor import process_orthogonalize
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.remote_symbol_library import DEFAULT_REMOTE_SYMBOL_ROOT
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_existing_directory, validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, TaskPanel


class OrthogonalizePage(BasePage):
    """Standalone safe geometry cleanup for electrical line routes and devices."""

    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        help_title, help_html = APP_HELP["orthogonalize"]
        super().__init__(
            "线路正交化",
            "按单个 G 文件对设备连接进行局部整理，并在安全条件下重画电气线路。",
            help_title,
            help_html,
            parent,
        )
        self.layout.addWidget(
            InfoBanner(
                "本模块逐个处理 G 文件，不跨文件建立全局拓扑，专门处理 ConnectLine、FeedLine、BusDis、Bus、ACLine 和 line 的 d 路径。"
                "优先读取已经同步到本机 AppData 的服务器图元标准 Pin（不会自动访问 SSH），并结合当前 G 文件的 devref、w/h、rotate、link/node_area 判断真实连接点。"
                "若发现线路端点与唯一标准 Pin 之间存在小间隙，会沿原端点方向安全延长/吸附到 Pin，并补齐线路与设备的 reciprocal link/node_area；"
                "已有明确设备引用的端点按引用 Pin 校正，无引用端点只有在候选 Pin 唯一、方向一致、Pin 未被其他线路占用且延长后不穿越其他设备时才自动连接。"
                "对已识别 RMU/环网柜，还会检查所有从柜框四边穿出的出线，不区分 Y1/Y2/Q1/Y3/Y4：先沿 link/node_area 穿过中间 ConnectLine 追溯到实际 LOAD_BREAKER_SWITCH/CIRCUIT_BREAKER 出线 Pin；旧图若缺少中间 line-line 引用，但同一 RMU 内只有唯一的同轴重叠/微小间隙，也会保守继续追踪。蓝色出线、中间连接线和外部 FeedLine 最终必须与该 Pin 严格同轴；普通正交化完成后再做一次最终 RMU 出线校验，优先拉长 ConnectLine/FeedLine 到真实交点，不移动 RMU 设备本体。"
                "随后继续执行同类设备对齐、明确连接线路重画和其余斜线正交化。Text、DText、Poke 和未知图元不修改。"
                "若候选存在歧义、距离过大或会穿越其他设备，则保守跳过并写入日志。"
                "原始 G 文件不会覆盖，结果写入本次 workspace 目录。"
            )
        )

        io_box = QGroupBox("输入与输出")
        io_layout = QVBoxLayout(io_box)
        io_layout.setContentsMargins(12, 18, 12, 12)
        io_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一个需要整理线路的 G 文件。",
            directory_tooltip="选择包含多个需要整理线路的 G 文件目录；程序只扫描目录第一层。",
            settings_prefix="orthogonalize",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)
        self.output_path = PathRow(
            directory=True,
            dialog_title="选择线路正交化输出目录",
            recent_directory_key="recent_paths/orthogonalize/output_directory",
            persistent_path_key="orthogonalize/output_directory",
            default_path=default_workspace() / "orthogonalized",
            location_name="线路正交化输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "orthogonalize")
        io_layout.addWidget(self.output_path)
        self.layout.addWidget(io_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始线路正交化")
        self.task.run_button.setToolTip(
            "按当前 G 文件分析同类设备、明确端点和线路障碍，在安全条件下对齐设备并重画/正交化线路；输出不会覆盖源 G 文件。"
        )
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()

    def run(self) -> None:
        if not validate_input_source(
            self,
            self.source,
            display_name="线路正交化输入",
            log=self.task.append_log,
        ):
            return
        self.source.persist_current()
        # Managed workspace output is recreated automatically if the whole workspace
        # was deleted between runs.
        output_dir = begin_managed_run(self.output_path, "orthogonalize", "normalize")
        prepared_source = self.source.prepare_for_processing(log=self.task.append_log)
        input_mode = self.source.mode()
        if input_mode == InputMode.REMOTE_SSH:
            input_mode = InputMode.DIRECTORY
        try:
            remote_cfg = self.source.remote.config()
        except Exception:
            remote_cfg = {}
        symbol_root = self.user_settings.get_value(
            "site_profile/remote_symbol_library_root",
            DEFAULT_REMOTE_SYMBOL_ROOT,
        ).strip() or DEFAULT_REMOTE_SYMBOL_ROOT
        settings = OrthogonalizeSettings(
            source_path=prepared_source,
            input_mode=input_mode,
            output_dir=output_dir,
            symbol_library_host=str(remote_cfg.get("host", "") or "").strip(),
            symbol_library_root=symbol_root,
        )
        self.task.start(lambda log, progress: process_orthogonalize(settings, log, progress), output_dir)
