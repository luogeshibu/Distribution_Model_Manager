from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from g_file_studio.processors.rmu_efi_processor import RmuEfiSettings, process_rmu_efi
from g_file_studio.services.id_rule_service import IdRuleService
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, IntegerInput, PathRow, TaskPanel


_HELP_HTML = """
<h3>用途</h3>
<p>给环网柜补齐 EFI 保护图元 <b>NariPd_Normal.pwbh.icn.g</b>。</p>
<h3>识别与位置</h3>
<ul>
<li>按虚线环网柜外框 + BusDis + CBreakerDis 识别环网柜；</li>
<li>如果框内已经存在 NariPd_Normal，则该环网柜立即跳过：不检查 Earth、不移动任何图元、不做任何改写；</li>
<li>如果没有 Normal，则读取框内 NariPd_Earth 的位置；</li>
<li>仅处理现场确认的两种布局：Earth 在左侧中部，或 Earth 在上侧中部；</li>
<li>新增 Normal 必须位于 Earth 与柜框之间，也就是比 Earth 更靠近柜框；</li>
<li><b>柜框是第一基准</b>：先按“EFI 与环网柜框距离”放置 Normal，再从 Normal 位置重新放置 Earth；</li>
<li>Normal 与 Earth 必须视觉中心对齐，并严格保留输入的图形间距，不能挨在一起；</li>
<li>页面输入值使用 <b>G 文件自身的 x/y 坐标单位</b>，不是屏幕像素；查看器缩放不会改变保存后的距离。</li>
<li>默认 Normal-Earth 图形间距 5 G 单位，EFI-环网柜框距离 10 G 单位。</li>
<li>如果环网柜空间无法同时容纳两项距离，程序会跳过该柜并写入报告，不会偷偷缩小距离。</li>
<li><b>只输出真正发生修改的 G 文件</b>：如果一个输入 G 中所有环网柜原本都有 Normal，或本次没有任何柜成功新增 Normal，则不会复制/输出这个 G；审计 CSV 仍会记录检查结果。</li>
</ul>
<h3>安全</h3>
<p>只生成 workspace 输出文件，不修改输入文件和服务器文件。新增 pwbh ID 使用已经确认的全局 ID 规则。</p>
"""


class RmuEfiPage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        super().__init__(
            "环网柜 EFI 保护图元添加",
            "检查每个环网柜是否缺少 NariPd_Normal；缺少时以环网柜框为第一基准放置 EFI，再从 EFI 位置重新放置 Earth，并保持视觉中心对齐和严格间距。",
            "环网柜 EFI 保护图元添加帮助",
            _HELP_HTML,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "只处理环网柜框内缺少 NariPd_Normal 的情况。程序先用 Earth 判断左侧型/上侧型，"
                "但实际落位以环网柜虚线框为第一基准：先放 EFI Normal，再按输入间距重新放置 Earth，"
                "最后做视觉中心对齐。参数单位是 G 文件自身的 x/y 坐标单位，不是屏幕像素；默认 Normal-Earth=5、EFI-柜框=10。"
                " 已有 EFI 的环网柜完全不改；只有实际新增过 EFI 的 G 文件才会出现在输出目录。"
            )
        )

        io_box = QGroupBox("输入与输出")
        io_layout = QVBoxLayout(io_box)
        io_layout.setContentsMargins(12, 18, 12, 12)
        io_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择需要补齐环网柜 EFI 图元的 G 文件。",
            directory_tooltip="选择包含待处理 G 文件的目录；只扫描第一层。",
            settings_prefix="rmu_efi",
            settings_service=self.user_settings,
        )
        io_layout.addWidget(self.source)

        self.output_path = PathRow(
            directory=True,
            dialog_title="环网柜 EFI 保护图元添加输出目录",
            recent_directory_key="recent_paths/rmu_efi/output_directory",
            persistent_path_key="rmu_efi/output_directory",
            default_path=default_workspace() / "runs" / "rmu-efi",
            location_name="环网柜 EFI 保护图元添加输出目录",
            settings_service=self.user_settings,
        )
        configure_managed_output(self.output_path, "rmu-efi")
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录（workspace，只读）"))
        output_row.addWidget(self.output_path, 1)
        io_layout.addLayout(output_row)
        self.layout.addWidget(io_box)

        spacing_box = QGroupBox("EFI 位置参数")
        spacing_form = QFormLayout(spacing_box)
        spacing_form.setHorizontalSpacing(16)
        spacing_form.setVerticalSpacing(10)
        self.normal_earth_gap = IntegerInput(
            value=self.user_settings.get_int("rmu_efi/normal_earth_gap_px", 5),
            minimum=0,
            maximum=100,
        )
        self.normal_earth_gap.setSuffix(" G")
        self.normal_earth_gap.setToolTip(
            "新增 NariPd_Normal 与同柜 NariPd_Earth 的实际图形间距，单位为 G 文件 x/y 坐标单位，不是屏幕像素。默认 5。"
        )
        self.frame_margin = IntegerInput(
            value=self.user_settings.get_int("rmu_efi/frame_margin_px", 10),
            minimum=0,
            maximum=100,
        )
        self.frame_margin.setSuffix(" G")
        self.frame_margin.setToolTip(
            "以环网柜虚线框为基准，新增 EFI Normal 距靠近一侧柜框的距离；单位为 G 文件 x/y 坐标单位。默认 10。"
        )
        spacing_form.addRow("Normal 与 Earth 图形间距", self.normal_earth_gap)
        spacing_form.addRow("EFI 与环网柜框距离", self.frame_margin)
        unit_note = QLabel(
            "单位说明：这里的 G 是 G 文件 x/y 坐标单位，不是屏幕像素。"
            "处理顺序固定为：环网柜框 → EFI Normal → Earth。"
        )
        unit_note.setWordWrap(True)
        spacing_form.addRow("", unit_note)
        self.layout.addWidget(spacing_box)

        rule_box = QGroupBox("固定处理规则")
        rule_layout = QVBoxLayout(rule_box)
        rule_layout.setContentsMargins(16, 18, 16, 14)
        rule_layout.setSpacing(8)
        for text in (
            "✓ 1. 环网柜：虚线 rect 外框内必须包含 BusDis 和至少两个 CBreakerDis",
            "✓ 2. 框内存在 NariPd_Normal.pwbh.icn.g：该柜完全不处理，不检查/移动 Earth，不改任何元素",
            "✓ 3. 框内缺少 Normal：只用 NariPd_Earth.pwbh.icn.g 的原位置判断左侧型或上侧型",
            "✓ 4. 柜框第一基准：先按“EFI 与环网柜框距离”放置 Normal，绝不拿旧 Earth 位置反推柜框距离",
            "✓ 5. 再放 Earth：按“Normal 与 Earth 图形间距”从 Normal 向柜内移动 Earth，并保持视觉中心对齐",
            "✓ 6. 输入参数使用 G 文件 x/y 坐标单位，不是屏幕像素；查看器缩放不影响保存距离",
            "✓ 7. 只移动缺少 Normal 的柜中的 NariPd_Earth，并新增 NariPd_Normal；已有 Normal 的柜完全保持原样",
            "✓ 8. 只输出实际发生修改的 G 文件；没有新增任何 Normal 的输入 G 不复制到输出目录，结果只记录在审计报告中",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        self.layout.addWidget(rule_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始添加环网柜 EFI 保护图元")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)

    def run(self) -> None:
        if not validate_input_source(
            self,
            self.source,
            display_name="环网柜 EFI 保护图元添加输入",
            log=self.task.append_log,
            progress=self.task.set_progress,
        ):
            return

        rule = IdRuleService().load_rules().get("pwbh")
        if rule is None or not rule.enabled or not rule.verified:
            QMessageBox.warning(
                self,
                "pwbh ID 规则未确认",
                "本模块会新增 <pwbh> 图元，因此必须先确认全局 pwbh ID 规则。\n\n"
                "请先到‘ID 检查与修复’完成确认。",
            )
            return

        self.source.persist_all_text()
        self.user_settings.set_value("rmu_efi/normal_earth_gap_px", self.normal_earth_gap.value())
        self.user_settings.set_value("rmu_efi/frame_margin_px", self.frame_margin.value())
        run_dir = begin_managed_run(self.output_path, "rmu-efi", "add")
        settings = RmuEfiSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=run_dir,
            normal_earth_gap_px=self.normal_earth_gap.value(),
            frame_margin_px=self.frame_margin.value(),
        )
        self.task.start(lambda log, progress: process_rmu_efi(settings, log, progress), run_dir)

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()
        self.user_settings.set_value("rmu_efi/normal_earth_gap_px", self.normal_earth_gap.value())
        self.user_settings.set_value("rmu_efi/frame_margin_px", self.frame_margin.value())
