from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.models import BasicSettings, InputMode
from g_file_studio.services.g_schema_service import (
    LayerSchemaScanResult,
    scan_direct_layer_schema,
)
from g_file_studio.ui.widgets.help_widgets import HelpLabel, set_secondary
from g_file_studio.ui.widgets.wheel_safe_combo_box import WheelSafeComboBox
from g_file_studio.ui.widgets.rule_card import RuleCard


class BasicRulesEditor(QWidget):
    scanRequested = Signal()
    """基础处理规则编辑器。

    元素标签与属性名来自输入目录中 G 文件的实际结构。扫描范围与处理范围完全一致：
    只扫描 G 根节点直属 Layer 的直接子元素，不读取 Theme、Layer 外内容或图元内部子元素。
    下拉框保持可编辑，用户仍可手动输入尚未扫描到的标签或属性名。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._input_dir: Path | None = None
        self._schema = LayerSchemaScanResult()

        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.setInterval(350)
        self._scan_timer.timeout.connect(self.refresh_schema)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(9)
        self.scan_button = QPushButton("扫描元素与属性")
        set_secondary(self.scan_button)
        self.scan_button.setToolTip(
            "扫描输入文件或目录内 G 文件的直属 Layer 直接子元素，生成元素标签和属性名下拉选项。"
        )
        self.scan_button.clicked.connect(self.scanRequested.emit)
        self.scan_status = QLabel("请选择输入文件或目录后扫描元素与属性")
        self.scan_status.setObjectName("mutedText")
        self.scan_status.setWordWrap(True)
        scan_row.addWidget(self.scan_button)
        scan_row.addWidget(self.scan_status, 1)
        root.addLayout(scan_row)

        self.replace_attribute_rule = RuleCard(
            "替换元素属性值",
            "从实际 G 文件中选择元素标签和属性名，旧值与新值由用户手动输入。",
            """
<p>程序会扫描输入目录，在下拉框中列出直属 Layer 的直接子元素标签，并根据所选标签列出实际存在的属性名。</p>
<p>匹配条件为：元素标签、属性名和旧值全部一致。</p>
<p>只处理 G 根节点直属 Layer 的直接子元素；不会修改 G、Theme、Layer 外内容，也不会递归修改图元内部子元素。</p>
<p>下拉框允许手动输入，旧值和新值始终由用户手动填写。</p>
""",
        )
        self.replace_attribute_rule.enabled.setChecked(False)
        replace_form = QFormLayout()
        replace_form.setHorizontalSpacing(16)
        replace_form.setVerticalSpacing(8)
        self.replace_tag = self._create_combo("请选择或输入元素标签")
        self.replace_attribute_name = self._create_combo("请先选择元素标签，再选择属性名")
        self.replace_old_value = QLineEdit()
        self.replace_old_value.setPlaceholderText("请输入需要匹配的旧值")
        self.replace_new_value = QLineEdit()
        self.replace_new_value.setPlaceholderText("请输入替换后的新值")
        replace_form.addRow(
            HelpLabel("元素标签", "从输入 G 文件的直属 Layer 直接子元素中选择，也可手动输入。"),
            self.replace_tag,
        )
        replace_form.addRow(
            HelpLabel("属性名", "根据所选元素标签列出实际出现的属性名，也可手动输入。"),
            self.replace_attribute_name,
        )
        replace_form.addRow(
            HelpLabel("旧值", "只有属性值与旧值完全相同时才替换。"),
            self.replace_old_value,
        )
        replace_form.addRow(
            HelpLabel("新值", "匹配成功后写入的新属性值。"),
            self.replace_new_value,
        )
        self.replace_attribute_rule.options_layout.addLayout(replace_form)


        self.delete_attribute_rule = RuleCard(
            "删除元素属性",
            "删除指定元素标签上的某个属性本身；不会删除元素，也不会把属性值改为空字符串。",
            """
<p>从输入 G 文件实际结构中选择元素标签和属性名。</p>
<p>执行后会对直属 Layer 中所有匹配标签的元素删除该属性，例如删除 &lt;Text&gt; 的某个属性。</p>
<p>这是“删除属性”，不是“修改属性值”，也不是“删除整个元素”。</p>
<p>只处理 G 根节点直属 Layer 的直接子元素，不递归处理图元内部子元素。</p>
""",
        )
        self.delete_attribute_rule.enabled.setChecked(False)
        delete_attr_form = QFormLayout()
        delete_attr_form.setHorizontalSpacing(16)
        delete_attr_form.setVerticalSpacing(8)
        self.delete_attr_tag = self._create_combo("请选择或输入元素标签")
        self.delete_attr_name = self._create_combo("请先选择元素标签，再选择要删除的属性")
        delete_attr_form.addRow(
            HelpLabel("元素标签", "从输入 G 文件直属 Layer 的直接子元素中选择，也可手动输入。"),
            self.delete_attr_tag,
        )
        delete_attr_form.addRow(
            HelpLabel("删除属性", "匹配元素上存在该属性时，直接删除这个属性键。"),
            self.delete_attr_name,
        )
        self.delete_attribute_rule.options_layout.addLayout(delete_attr_form)

        self.delete_element_rule = RuleCard(
            "删除匹配元素",
            "从实际 G 文件中选择元素标签和属性名，属性值由用户手动输入。",
            """
<p>程序会扫描输入目录，在下拉框中列出直属 Layer 的直接子元素标签，并根据所选标签列出实际存在的属性名。</p>
<p>匹配条件为：元素标签、属性名和属性值全部一致。</p>
<p>该规则不是只删除一个属性，而是删除整个匹配元素及其内部子树。</p>
<p>只检查 G 根节点直属 Layer 的直接子元素；不会删除 Theme、Layer 外元素或其他位置的同名元素。</p>
<p>程序会在当前 Layer 范围内清理 link、node_area、p_FatherObjId 中指向已删除真实图元的引用。</p>
""",
        )
        self.delete_element_rule.enabled.setChecked(False)
        delete_form = QFormLayout()
        delete_form.setHorizontalSpacing(16)
        delete_form.setVerticalSpacing(8)
        self.delete_tag = self._create_combo("请选择或输入元素标签")
        self.delete_attribute = self._create_combo("请先选择元素标签，再选择属性名")
        self.delete_value = QLineEdit()
        self.delete_value.setPlaceholderText("请输入需要精确匹配的属性值")
        delete_form.addRow(
            HelpLabel("元素标签", "从输入 G 文件的直属 Layer 直接子元素中选择，也可手动输入。"),
            self.delete_tag,
        )
        delete_form.addRow(
            HelpLabel("属性名", "根据所选元素标签列出实际出现的属性名，也可手动输入。"),
            self.delete_attribute,
        )
        delete_form.addRow(
            HelpLabel("属性值", "只有属性值与此内容完全一致时才删除整个元素。"),
            self.delete_value,
        )
        self.delete_element_rule.options_layout.addLayout(delete_form)

        self.replace_tag.currentTextChanged.connect(
            lambda text: self._update_attribute_combo(self.replace_attribute_name, text)
        )
        self.delete_attr_tag.currentTextChanged.connect(
            lambda text: self._update_attribute_combo(self.delete_attr_name, text)
        )
        self.delete_tag.currentTextChanged.connect(
            lambda text: self._update_attribute_combo(self.delete_attribute, text)
        )

        root.addWidget(self.replace_attribute_rule)
        root.addWidget(self.delete_attribute_rule)
        root.addWidget(self.delete_element_rule)

    @staticmethod
    def _create_combo(placeholder: str) -> WheelSafeComboBox:
        combo = WheelSafeComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(WheelSafeComboBox.InsertPolicy.NoInsert)
        combo.setMaxVisibleItems(24)
        combo.setCurrentIndex(-1)
        if combo.lineEdit() is not None:
            combo.lineEdit().setPlaceholderText(placeholder)
            combo.lineEdit().setClearButtonEnabled(True)
        return combo

    def set_input_dir(self, path: str | Path) -> None:
        """设置用于生成下拉选项的输入文件或目录，并延迟自动扫描。"""
        text = str(path).strip()
        self._input_dir = Path(text).expanduser() if text else None
        self._scan_timer.start()

    def refresh_schema(self) -> None:
        self._scan_timer.stop()
        if self._input_dir is None:
            self._schema = LayerSchemaScanResult()
            self.scan_status.setText("请选择输入文件或目录后扫描元素与属性")
            return

        result = scan_direct_layer_schema(self._input_dir)
        self._schema = result
        self._populate_tag_combo(self.replace_tag)
        self._populate_tag_combo(self.delete_attr_tag)
        self._populate_tag_combo(self.delete_tag)
        self._update_attribute_combo(
            self.replace_attribute_name,
            self.replace_tag.currentText(),
        )
        self._update_attribute_combo(
            self.delete_attr_name,
            self.delete_attr_tag.currentText(),
        )
        self._update_attribute_combo(
            self.delete_attribute,
            self.delete_tag.currentText(),
        )

        if not self._input_dir.exists():
            self.scan_status.setText("输入路径不存在或没有 G 文件，暂时无法生成元素和属性选项")
            self.scan_status.setToolTip("\n".join(result.warnings))
            return

        if not result.tags:
            self.scan_status.setText("未扫描到直属 Layer 的直接子元素；仍可手动输入标签和属性名")
        else:
            self.scan_status.setText(
                f"已扫描 {result.file_count} 个文件、{result.direct_element_count} 个直属图元、"
                f"{len(result.tags)} 种元素标签"
            )
        self.scan_status.setToolTip("\n".join(result.warnings))

    def _populate_tag_combo(self, combo: WheelSafeComboBox) -> None:
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(list(self._schema.tags))
        if current:
            combo.setEditText(current)
        else:
            combo.setCurrentIndex(-1)
        combo.blockSignals(False)

    def _update_attribute_combo(self, combo: WheelSafeComboBox, tag: str) -> None:
        current = combo.currentText().strip()
        attributes = self._schema.tag_attributes.get(tag.strip(), ())
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(list(attributes))
        if current:
            combo.setEditText(current)
        else:
            combo.setCurrentIndex(-1)
        combo.blockSignals(False)

    def build_settings(
        self,
        source_path: Path,
        input_mode: InputMode,
        output_dir: Path,
    ) -> BasicSettings:
        return BasicSettings(
            source_path=source_path,
            input_mode=input_mode,
            output_dir=output_dir,
            replace_attribute=self.replace_attribute_rule.enabled.isChecked(),
            replace_target_tag=self.replace_tag.currentText().strip(),
            replace_target_attribute=self.replace_attribute_name.currentText().strip(),
            replace_old_value=self.replace_old_value.text(),
            replace_new_value=self.replace_new_value.text(),
            delete_attribute=self.delete_attribute_rule.enabled.isChecked(),
            delete_attribute_target_tag=self.delete_attr_tag.currentText().strip(),
            delete_attribute_name=self.delete_attr_name.currentText().strip(),
            delete_matching_element=self.delete_element_rule.enabled.isChecked(),
            delete_target_tag=self.delete_tag.currentText().strip(),
            delete_target_attribute=self.delete_attribute.currentText().strip(),
            delete_target_value=self.delete_value.text(),
        )
