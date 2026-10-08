from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QGroupBox, QLabel, QMessageBox, QPushButton, QVBoxLayout

from g_file_studio.processors.poke_processor import PokeProcessingSettings, process_pokes
from g_file_studio.services.database_service import OracleDatabaseService
from g_file_studio.services.remote_symbol_library import (
    DEFAULT_REMOTE_SYMBOL_ROOT,
    RemoteSymbolLibraryService,
)
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_existing_directory, validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, TaskPanel
from g_file_studio.ui.widgets.help_widgets import set_secondary



class PokePage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        self.database_service = OracleDatabaseService(user_settings)
        self.last_html_report: Path | None = None
        help_title, help_html = APP_HELP["poke"]
        super().__init__(
            "Poke 跳转处理",
            "独立生成/修复 RMU、AR/LBS/SEC 设备与站点跳转 Poke。",
            help_title,
            help_html,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "RMU Poke 继续复用公共 RMU 识别，并且柜名只认柜体上方 Text。AR/LBS/SEC 已独立为单独设备 Poke：先按服务器图元分类标记定位设备，"
                "名称 Text 必须有明确字体颜色：红色优先；没有可分配红色名称时才允许其他非白色 Text 兜底；位置仍按上方→右侧→全局优先级识别，距离不超过 200。"
                "一个具体 Text 只能属于一种 Poke 角色：设备名称、RMU 名称、站点跳转名称互斥；已被某一角色占用后，其他角色不得再次使用。"
                "站点跳转名称 Text 禁止为红色且必须有独立的可见彩色背景；Text 自身 fc/fcc 不算背景。"
            "名称识别完成后仍按原逻辑生成目标 ahref，facID 仍不是 Poke 前提。"
            )
        )

        io_box = QGroupBox("输入与输出")
        io_layout = QVBoxLayout(io_box)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一个需要生成/修复 Poke 的 G 文件。",
            directory_tooltip="选择包含多个待处理 G 文件的目录；程序只扫描目录第一层。",
            settings_prefix="poke",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)
        self.output_path = PathRow(
            directory=True,
            dialog_title="选择 Poke 跳转处理输出目录",
            recent_directory_key="recent_paths/poke/output_directory",
            persistent_path_key="poke/output_directory",
            default_path=default_workspace() / "poke-processed",
            location_name="Poke 跳转处理输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "poke")
        io_layout.addWidget(self.output_path)
        self.layout.addWidget(io_box)

        mode_box = QGroupBox("跳转类型")
        mode_layout = QVBoxLayout(mode_box)
        self.enable_rmu_poke = QCheckBox(
            "RMU Poke：环网柜设备明细图　目标：{区域}-{变电站}-{馈线}-{RMU名}.com.pic.g"
        )
        self.enable_classified_device_poke = QCheckBox(
            "AR / LBS / SEC Poke（独立）：设备明细图　目标：{区域}-{变电站}-{馈线}-{设备名}.com.pic.g"
        )
        self.enable_station_poke = QCheckBox(
            "站点跳转 Poke：变电站馈线总图　目标：{区域}-{变电站}.sln.pic.g"
        )
        self.enable_rmu_poke.setChecked(self.user_settings.get_bool("poke/enable_rmu", True))
        self.enable_classified_device_poke.setChecked(
            self.user_settings.get_bool("poke/enable_classified_device", True)
        )
        self.enable_station_poke.setChecked(self.user_settings.get_bool("poke/enable_station", True))
        mode_layout.addWidget(self.enable_rmu_poke)
        mode_layout.addWidget(self.enable_classified_device_poke)
        mode_layout.addWidget(self.enable_station_poke)
        self.layout.addWidget(mode_box)


        recognition_box = QGroupBox("识别与数据库规则")
        recognition_layout = QVBoxLayout(recognition_box)
        shared_rmu = QLabel(
            "RMU 继续调用同一个 identify_rmus()。AR/LBS/SEC 已从 RMU Poke 独立抽离，只认主程序“图元管理”中的 "
            "AR、LBS、SEC 分类标记；设备名称 Text 必须有明确字体颜色，红色优先、其他非白色颜色兜底，白色禁止；位置仍按上方→右侧→全局优先级识别，距离不得超过 200。"
            "每个目标设备只分配一个名称 Text；同一个具体 Text 在设备名称、RMU 名称、站点跳转名称之间全局互斥，不能重复使用。"
            "两个 Text 内容即使相同，只要 Text ID 不同，仍作为两个独立名称实例参与分配。后续数据库查询和目标 ahref 生成逻辑保持不变。"
        )
        shared_rmu.setWordWrap(True)
        shared_rmu.setObjectName("mutedText")
        recognition_layout.addWidget(shared_rmu)
        station_rule = QLabel(
            "站点跳转强制规则：只识别站点 Text；Text 必须是字母+数字格式（如 ANS2-44，纯数字不接受），必须有独立的可见彩色背景，"
            "并且名称 Text 本身不能是红色；已被 RMU 或 AR/LBS/SEC 设备名称占用的 Text 也不会再作为站点跳转名称。通过条件后执行原有 "
            "SUBSTATION.NAME → SUBAREA_ID → SUBCONTROLAREA.NAME 查询。若站点 Text 旁边 100 以内存在括号纯数字 "
            "（如 (35033)），只允许最终选择一个；如果 100 内存在多个括号环网柜名，只取离站点名称最近的一个作为 locateLabel；如果没有环网柜名，则使用站点间隔后缀备用规则 "
            "（如 RDS-09 → AH309）。括号数字不属于站点名。"
        )
        station_rule.setWordWrap(True)
        station_rule.setObjectName("mutedText")
        recognition_layout.addWidget(station_rule)
        fallback = QLabel(
            "上述条件全部是强制约束：Text 自身的 fc/fcc 属性、无填充对象或纯几何形状都不能替代独立彩色背景。"
            "站点旁括号环网柜名只允许输出一个：候选距离必须 ≤100，多个候选时取最近的一个；只有没有合格环网柜名时才使用站点间隔后缀备用规则。"
            "数据库唯一匹配成功后才允许修改，多个相关 Poke 仍只保留一个。"
        )
        fallback.setWordWrap(True)
        fallback.setObjectName("mutedText")
        recognition_layout.addWidget(fallback)
        self.layout.addWidget(recognition_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始 Poke 跳转处理")
        self.task.run_button.clicked.connect(self.run)
        self.report_button = QPushButton("打开 Poke 报告")
        self.report_button.setToolTip("打开最近一次 Poke 跳转处理生成的 HTML 报告；报告包含 RMU、AR/LBS/SEC、站点跳转识别和未加跳转原因。")
        set_secondary(self.report_button)
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self.open_last_report)
        self.task.buttons_layout.insertWidget(1, self.report_button)
        self.task.resultReceived.connect(self._on_result)
        self.layout.addWidget(self.task, 1)

    def _shared_rmu_settings(self) -> tuple[tuple[str, ...], str, str]:
        positions = tuple(
            key for key, default in (("top", True), ("bottom", False), ("left", False), ("right", False))
            if self.user_settings.get_bool(f"basic/rmu/name_{key}", default)
        )
        if not positions:
            positions = ("top",)
        exclusions = self.user_settings.get_value("basic/rmu/name_exclusions", "").strip()
        markers = self.user_settings.get_value("basic/rmu/intelligent_markers", "SMART, SMR").strip() or "SMART, SMR"
        return positions, exclusions, markers

    def _classification_marker_entries(self) -> tuple[tuple[str, str, str], ...]:
        """Read operator-owned markers from the local symbol-sync cache only."""
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
            # Missing local sync cache must not block ordinary Poke processing.
            return ()

    def run(self) -> None:
        self._start_processing(
            enable_rmu=self.enable_rmu_poke.isChecked(),
            enable_classified_device=self.enable_classified_device_poke.isChecked(),
            enable_station=self.enable_station_poke.isChecked(),
            persist_mode_choices=True,
        )

    def _start_processing(
        self,
        *,
        enable_rmu: bool,
        enable_classified_device: bool,
        enable_station: bool,
        persist_mode_choices: bool,
    ) -> None:
        if not validate_input_source(self, self.source, display_name="Poke 跳转处理输入"):
            return
        if not (enable_rmu or enable_classified_device or enable_station):
            QMessageBox.warning(self, "Poke 跳转处理", "请至少选择一种 Poke 跳转类型。")
            return

        self.source.persist_current()
        if persist_mode_choices:
            self.user_settings.set_value("poke/enable_rmu", enable_rmu)
            self.user_settings.set_value("poke/enable_classified_device", enable_classified_device)
            self.user_settings.set_value("poke/enable_station", enable_station)
        positions, exclusions, markers = self._shared_rmu_settings()
        classification_marker_entries = self._classification_marker_entries() if enable_classified_device else ()
        output_dir = begin_managed_run(self.output_path, "poke", "process")
        settings = PokeProcessingSettings(
            source_path=Path(self.source.path()),
            input_mode=self.source.mode(),
            output_dir=output_dir,
            enable_rmu_poke=enable_rmu,
            enable_classified_device_poke=enable_classified_device,
            enable_station_poke=enable_station,
            rmu_name_positions=positions,
            rmu_name_exclusions=exclusions,
            rmu_intelligent_markers=markers,
            classification_marker_entries=classification_marker_entries,
        )
        self.last_html_report = None
        self.report_button.setEnabled(False)
        self.task.start(
            lambda log, progress: process_pokes(settings, self.database_service, log, progress),
            output_dir,
        )

    def _on_result(self, result) -> None:
        self.last_html_report = None
        path_text = str(result.statistics.get("html_report_path", "")) if getattr(result, "statistics", None) else ""
        if path_text:
            path = Path(path_text)
            if path.exists():
                self.last_html_report = path
        self.report_button.setEnabled(self.last_html_report is not None)
        if self.last_html_report is not None:
            stats = result.statistics
            self.task.append_log(
                "[Poke报告摘要] "
                f"识别 RMU {stats.get('rmu_identified_total', 0)} 个，智能 RMU {stats.get('smart_rmu_identified_total', 0)} 个；"
                f"新增 RMU Poke {stats.get('rmu_added', 0)} 个；"
                f"AR/LBS/SEC 设备 {stats.get('classified_device_total', 0)} 个，已分配名称 {stats.get('classified_device_named', 0)} 个，新增设备 Poke {stats.get('classified_device_added', 0)} 个；"
                f"站点跳转候选 {stats.get('station_candidates', 0)} 个，成功解析 {stats.get('station_resolved_count', 0)} 个，"
                f"新增站点跳转 Poke {stats.get('station_added', 0)} 个，未加跳转 {stats.get('station_skipped', 0)} 个。"
            )

    def open_last_report(self) -> None:
        if not self.last_html_report or not self.last_html_report.exists():
            QMessageBox.information(self, "暂无报告", "请先执行一次 Poke 跳转处理并生成报告。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_html_report.resolve())))

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()
        self.user_settings.set_value("poke/enable_rmu", self.enable_rmu_poke.isChecked())
        self.user_settings.set_value(
            "poke/enable_classified_device", self.enable_classified_device_poke.isChecked()
        )
        self.user_settings.set_value("poke/enable_station", self.enable_station_poke.isChecked())
