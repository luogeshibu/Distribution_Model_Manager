from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from g_file_studio.engines.smart_profile_engine import SmartProfileScanResult, scan_smart_profile_samples
from g_file_studio.models import InputMode
from g_file_studio.processors.common import discover_g_inputs
from g_file_studio.processors.smart_profile_processor import (
    SmartProfileProcessingSettings,
    process_smart_profile_consistency,
)
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.site_profile_service import SiteProfileService, SiteSmartProfile
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.path_validation import validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, TaskPanel
from g_file_studio.ui.widgets.help_widgets import set_secondary


class SiteProfileDialog(QDialog):
    """User-confirmed site SMART-symbol profile scanner and consistency tool.

    This dialog is intentionally separate from the existing RMU processing run.  It
    does not modify shared RMU algorithms or defaults.  Users explicitly designate
    sample G files as belonging to one site, scan them to learn the site's SMART LBS
    and Circuit Breaker devrefs, confirm/save the profile, and may then run a generic
    SMART-device consistency pass using that saved profile.
    """

    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        super().__init__(parent)
        self.user_settings = user_settings
        self.service = SiteProfileService()
        self._last_scan: SmartProfileScanResult | None = None
        self.setWindowTitle("现场 SMART Profile 管理")
        self.resize(1040, 820)
        self.setMinimumSize(900, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        root.addWidget(
            InfoBanner(
                "由用户明确指定样本所属现场，再扫描标准 G 文件学习 SMART LBS / Circuit Breaker 图元。"
                "程序不依赖 JED/MD/MAK 文件名前缀猜现场；保存 Profile 后可对任意 G 执行 SMART 图元一致性检查。"
            )
        )

        profile_box = QGroupBox("Site Profile")
        profile_layout = QVBoxLayout(profile_box)
        profile_layout.setContentsMargins(14, 18, 14, 12)
        profile_layout.setSpacing(10)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("已保存 Profile"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(280)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        select_row.addWidget(self.profile_combo, 1)
        self.new_button = QPushButton("新建")
        self.delete_button = QPushButton("删除")
        set_secondary(self.new_button)
        set_secondary(self.delete_button)
        self.new_button.clicked.connect(self._new_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        select_row.addWidget(self.new_button)
        select_row.addWidget(self.delete_button)
        profile_layout.addLayout(select_row)

        form = QFormLayout()
        self.site_name = QLineEdit()
        self.site_name.setPlaceholderText("例如：Madinah / Makkah / Jeddah")
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("例如：Madinah Standard")
        form.addRow("Site Name", self.site_name)
        form.addRow("Profile Name", self.profile_name)
        profile_layout.addLayout(form)

        sample_label = QLabel("标准样本 G 文件")
        sample_label.setObjectName("sectionCaption")
        profile_layout.addWidget(sample_label)
        self.sample_source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一张已知现场、可作为 SMART 图元标准样本的 G 文件。",
            directory_tooltip="选择包含多张同一现场标准样本 G 文件的目录。建议使用多张样本提高可信度。",
            settings_prefix="site_profile_samples",
            settings_service=self.user_settings,
        )
        profile_layout.addWidget(self.sample_source)

        scan_row = QHBoxLayout()
        self.scan_button = QPushButton("扫描样本")
        self.scan_button.clicked.connect(self._scan_samples)
        scan_row.addWidget(self.scan_button)
        self.scan_summary = QLabel("尚未扫描。")
        self.scan_summary.setObjectName("mutedText")
        self.scan_summary.setWordWrap(True)
        scan_row.addWidget(self.scan_summary, 1)
        profile_layout.addLayout(scan_row)

        result_form = QFormLayout()
        self.lbs_combo = QComboBox()
        self.breaker_combo = QComboBox()
        self.lbs_combo.setMinimumContentsLength(60)
        self.breaker_combo.setMinimumContentsLength(60)
        result_form.addRow("SMART LBS devref", self.lbs_combo)
        result_form.addRow("SMART Circuit Breaker devref", self.breaker_combo)
        profile_layout.addLayout(result_form)

        save_row = QHBoxLayout()
        self.save_button = QPushButton("保存 Profile")
        self.save_button.clicked.connect(self._save_profile)
        save_row.addWidget(self.save_button)
        self.profile_status = QLabel("")
        self.profile_status.setObjectName("mutedText")
        save_row.addWidget(self.profile_status, 1)
        profile_layout.addLayout(save_row)
        root.addWidget(profile_box)

        apply_box = QGroupBox("SMART 图元一致性处理")
        apply_layout = QVBoxLayout(apply_box)
        apply_layout.setContentsMargins(14, 18, 14, 12)
        apply_layout.setSpacing(10)
        note = QLabel(
            "使用当前已保存 Profile 检查所有已识别 SMART 环网柜：Y 类 CBreakerDis 强制使用 Profile 的 SMART LBS devref，"
            "Q 类 CBreakerDis 强制使用 Profile 的 SMART Circuit Breaker devref。ID、keyid、node_area、名称、旋转和拓扑关系保持不变；"
            "若目标 SMART 图元内部几何不同，程序会依据同旋转的正确 SMART 样本反算 x/y/w/h，确保原 ConnectLine 连接点绝对坐标不变；非 SMART 环网柜不处理。"
        )
        note.setWordWrap(True)
        note.setObjectName("mutedText")
        apply_layout.addWidget(note)

        self.apply_source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一张需要按当前 Site Profile 检查 SMART 图元的 G 文件。",
            directory_tooltip="选择包含待检查 G 文件的目录。",
            settings_prefix="site_profile_apply",
            settings_service=self.user_settings,
        )
        apply_layout.addWidget(self.apply_source)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录（workspace，只读）"))
        self.output_path = PathRow(
            directory=True,
            dialog_title="SMART Profile 输出目录",
            recent_directory_key="recent_paths/site_profile/output_directory",
            persistent_path_key="site_profile/output_directory",
            default_path=default_workspace() / "runs" / "smart-profile",
            location_name="SMART Profile 输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "smart-profile")
        output_row.addWidget(self.output_path, 1)
        apply_layout.addLayout(output_row)

        self.task = TaskPanel()
        self.task.run_button.setText("开始 SMART 图元一致性处理")
        self.task.run_button.clicked.connect(self._run_profile)
        apply_layout.addWidget(self.task)
        root.addWidget(apply_box, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("关闭")
        set_secondary(close_button)
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

        self._reload_profiles()

    def _reload_profiles(self, select_name: str = "") -> None:
        profiles = self.service.load_profiles()
        current = select_name or self.profile_combo.currentData() or ""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("请选择已保存 Profile", "")
        for name, profile in sorted(profiles.items(), key=lambda row: row[0].casefold()):
            self.profile_combo.addItem(f"{name}  ·  {profile.site_name}", name)
        index = self.profile_combo.findData(current)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.profile_combo.blockSignals(False)
        if index >= 0:
            self._profile_changed(index)
        else:
            self._new_profile(clear_selection=False)

    def _new_profile(self, *_args, clear_selection: bool = True) -> None:
        if clear_selection:
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(0)
            self.profile_combo.blockSignals(False)
        self.site_name.clear()
        self.profile_name.clear()
        self.lbs_combo.clear()
        self.breaker_combo.clear()
        self.scan_summary.setText("尚未扫描。")
        self.profile_status.clear()
        self._last_scan = None

    def _profile_changed(self, *_args) -> None:
        name = str(self.profile_combo.currentData() or "")
        if not name:
            return
        profile = self.service.load_profiles().get(name)
        if profile is None:
            return
        self.site_name.setText(profile.site_name)
        self.profile_name.setText(profile.profile_name)
        self._fill_candidate_combo(self.lbs_combo, profile.lbs_candidates, profile.smart_lbs_devref)
        self._fill_candidate_combo(self.breaker_combo, profile.breaker_candidates, profile.smart_breaker_devref)
        self.scan_summary.setText(
            f"已保存：样本 {len(profile.sample_files)} 个，SMART RMU {profile.smart_rmu_count} 个；"
            f"LBS 可信度 {profile.lbs_confidence:.0%}，Q 可信度 {profile.breaker_confidence:.0%}。"
        )
        self.profile_status.setText(f"最后保存：{profile.updated_at or '-'}")
        self._last_scan = None

    @staticmethod
    def _fill_candidate_combo(combo: QComboBox, counts: dict[str, int], selected: str) -> None:
        combo.clear()
        total = sum(max(0, int(value)) for value in counts.values())
        rows = sorted(counts.items(), key=lambda row: (-int(row[1]), row[0].casefold()))
        for devref, count in rows:
            confidence = (count / total) if total else 0.0
            combo.addItem(f"{devref}   [{count}, {confidence:.0%}]", devref)
        if selected and combo.findData(selected) < 0:
            combo.addItem(selected, selected)
        index = combo.findData(selected)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _scan_samples(self) -> None:
        if not self.site_name.text().strip():
            QMessageBox.warning(self, "Site Name", "请先输入 Site Name，再扫描属于该现场的标准样本。")
            return
        if not self.profile_name.text().strip():
            QMessageBox.warning(self, "Profile Name", "请先输入 Profile Name。")
            return
        if not validate_input_source(self, self.sample_source, display_name="Site Profile 样本"):
            return
        self.sample_source.persist_current()
        try:
            files = discover_g_inputs(self.sample_source.path(), self.sample_source.mode())
            scan = scan_smart_profile_samples(files)
        except Exception as exc:
            QMessageBox.critical(self, "扫描失败", str(exc))
            return
        self._last_scan = scan
        self._fill_candidate_combo(self.lbs_combo, scan.lbs_counts, scan.suggested_lbs_devref)
        self._fill_candidate_combo(self.breaker_combo, scan.breaker_counts, scan.suggested_breaker_devref)
        lbs_conf = scan.lbs_candidates[0].confidence if scan.lbs_candidates else 0.0
        brk_conf = scan.breaker_candidates[0].confidence if scan.breaker_candidates else 0.0
        self.scan_summary.setText(
            f"扫描 {scan.parsed_file_count}/{len(files)} 个文件，识别 SMART RMU {scan.smart_rmu_count} 个；"
            f"LBS 主候选 {lbs_conf:.0%}，Q 主候选 {brk_conf:.0%}。"
        )
        if scan.warnings:
            self.profile_status.setText("；".join(scan.warnings[:3]))
        elif min(lbs_conf, brk_conf) < 0.8:
            self.profile_status.setText("候选一致率低于 80%，请人工检查下拉候选后再保存。")
        else:
            self.profile_status.setText("扫描完成。请确认两个 devref 后保存 Profile。")

    def _save_profile(self) -> None:
        site_name = self.site_name.text().strip()
        profile_name = self.profile_name.text().strip()
        lbs = str(self.lbs_combo.currentData() or "").strip()
        breaker = str(self.breaker_combo.currentData() or "").strip()
        if not site_name or not profile_name or not lbs or not breaker:
            QMessageBox.warning(self, "Profile 未完成", "Site Name、Profile Name、SMART LBS 和 SMART Circuit Breaker 都必须确认。")
            return

        scan = self._last_scan
        if scan is not None:
            lbs_rows = {row.devref: row for row in scan.lbs_candidates}
            breaker_rows = {row.devref: row for row in scan.breaker_candidates}
            sample_files = [path.name for path in scan.files]
            smart_rmu_count = scan.smart_rmu_count
            lbs_observations = sum(scan.lbs_counts.values())
            breaker_observations = sum(scan.breaker_counts.values())
            lbs_confidence = lbs_rows.get(lbs).confidence if lbs in lbs_rows else 0.0
            breaker_confidence = breaker_rows.get(breaker).confidence if breaker in breaker_rows else 0.0
            lbs_candidates = dict(scan.lbs_counts)
            breaker_candidates = dict(scan.breaker_counts)
        else:
            old = self.service.load_profiles().get(profile_name)
            sample_files = list(old.sample_files) if old else []
            smart_rmu_count = old.smart_rmu_count if old else 0
            lbs_observations = old.lbs_observations if old else 0
            breaker_observations = old.breaker_observations if old else 0
            lbs_confidence = old.lbs_confidence if old else 0.0
            breaker_confidence = old.breaker_confidence if old else 0.0
            lbs_candidates = dict(old.lbs_candidates) if old else {lbs: 1}
            breaker_candidates = dict(old.breaker_candidates) if old else {breaker: 1}

        try:
            profile = self.service.upsert(
                SiteSmartProfile(
                    profile_name=profile_name,
                    site_name=site_name,
                    smart_lbs_devref=lbs,
                    smart_breaker_devref=breaker,
                    sample_files=sample_files,
                    smart_rmu_count=smart_rmu_count,
                    lbs_observations=lbs_observations,
                    breaker_observations=breaker_observations,
                    lbs_confidence=lbs_confidence,
                    breaker_confidence=breaker_confidence,
                    lbs_candidates=lbs_candidates,
                    breaker_candidates=breaker_candidates,
                )
            )
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._reload_profiles(profile.profile_name)
        QMessageBox.information(self, "Profile 已保存", f"已保存 {profile.profile_name}（{profile.site_name}）。")

    def _delete_profile(self) -> None:
        name = str(self.profile_combo.currentData() or "")
        if not name:
            QMessageBox.information(self, "请选择 Profile", "请先选择需要删除的已保存 Profile。")
            return
        if QMessageBox.question(self, "删除 Profile", f"确认删除 Site Profile “{name}”？") != QMessageBox.StandardButton.Yes:
            return
        self.service.remove(name)
        self._reload_profiles()

    def _run_profile(self) -> None:
        name = str(self.profile_combo.currentData() or "")
        profile = self.service.load_profiles().get(name)
        if profile is None:
            QMessageBox.warning(self, "请选择 Profile", "请先选择并保存一个 Site Profile。")
            return
        if not validate_input_source(self, self.apply_source, display_name="SMART Profile 处理输入", log=self.task.append_log):
            return
        self.apply_source.persist_current()
        run_dir = begin_managed_run(self.output_path, "smart-profile", "process")
        settings = SmartProfileProcessingSettings(
            source_path=self.apply_source.path(),
            input_mode=self.apply_source.mode(),
            output_dir=run_dir,
            profile=profile,
        )
        self.task.start(lambda log, progress: process_smart_profile_consistency(settings, log, progress), run_dir)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.sample_source.persist_all_text()
        self.apply_source.persist_all_text()
        self.output_path.persist_current_text()
        super().closeEvent(event)
