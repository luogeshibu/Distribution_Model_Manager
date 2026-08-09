#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QSpinBox, QAbstractSpinBox,
    QComboBox, QHBoxLayout, QSizePolicy,
)

from app_config import (
    DEFAULT_DEVICE_RULES, DEFAULT_NAME_POSITIONS,
    DEFAULT_LABEL_MAX_DISTANCE, DEFAULT_LABEL_OVERLAP_TOLERANCE,
    DEFAULT_LABEL_REGEX,
)
from g_parser import GParser
from g_writeback import GWriteBackService
from validator import RmuValidator
from .base import ModelModule




def _resource_dir():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]

SPIN_UP_ICON = (_resource_dir() / "assets" / "spin_up.png").as_posix()
SPIN_DOWN_ICON = (_resource_dir() / "assets" / "spin_down.png").as_posix()


class NoWheelSpinBox(QSpinBox):
    """原生 SpinBox：支持输入和上下按钮，但鼠标滚轮不修改数值。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.setKeyboardTracking(False)
        self.setWrapping(False)
        self.setSingleStep(1)
        self.setAccelerated(False)
        self.setStyleSheet(f"""
            QSpinBox {{
                padding-right: 30px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 28px;
                background: #006B52;
                border-left: 1px solid #005640;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: #00966E;
            }}
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
                background: #004D3A;
            }}
            QSpinBox::up-arrow {{
                image: url("{SPIN_UP_ICON}");
                width: 14px;
                height: 10px;
            }}
            QSpinBox::down-arrow {{
                image: url("{SPIN_DOWN_ICON}");
                width: 14px;
                height: 10px;
            }}
        """)
        self.setFocusPolicy(self.focusPolicy())

    def wheelEvent(self, event):
        event.ignore()

class NoWheelComboBox(QComboBox):
    """禁止滚轮误切换选项，仍允许点击下拉框。"""

    def wheelEvent(self, event):
        event.ignore()


class RmuSettingsWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        info = QLabel(
            "RMU 环网柜通过 G 文件结构自动识别。开关设备名称可选择使用 "
            "p_NameString，或使用环网柜内部、紧邻 CBreakerDis 的图上文字。"
            "选择图上文字时，后续校验不再读取三类设备 XML 的 p_NameString："
            "CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        # ------------------------------------------------------------------
        # 第一行：RMU 识别 + 数据库表/域配置并排展示。
        # 避免纵向堆叠导致小分辨率下控件被压扁。
        # ------------------------------------------------------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        recog = QGroupBox("RMU 环网柜识别")
        recog.setMinimumWidth(330)
        recog.setMinimumHeight(285)
        rg = QGridLayout(recog)
        rg.setContentsMargins(14, 18, 14, 14)
        rg.setHorizontalSpacing(18)
        rg.setVerticalSpacing(10)
        rg.addWidget(QLabel("环网柜名称位置"), 0, 0, 1, 2)

        labels = {"top": "上方", "right": "右侧", "left": "左侧", "bottom": "下方"}
        self.pos_checks = {}
        saved_pos = config.get("rmu_name_positions", DEFAULT_NAME_POSITIONS)
        for idx, pos in enumerate(("top", "right", "left", "bottom")):
            cb = QCheckBox(labels[pos])
            cb.setChecked(bool(saved_pos.get(pos, False)))
            rg.addWidget(cb, 1 + idx // 2, idx % 2)
            self.pos_checks[pos] = cb

        rg.addWidget(QLabel("开关名称来源"), 3, 0)
        self.breaker_source = NoWheelComboBox()
        self.breaker_source.addItem("使用 p_NameString", "P_NAME_STRING")
        self.breaker_source.addItem("使用环网柜内图上文字", "GRAPHICAL_TEXT")
        saved_source = config.get("breaker_name_source", "P_NAME_STRING")
        index = self.breaker_source.findData(saved_source)
        self.breaker_source.setCurrentIndex(index if index >= 0 else 0)
        rg.addWidget(self.breaker_source, 3, 1)

        note = QLabel(
            "图上文字模式使用框内文字与 CBreakerDis 的最近唯一空间关系；"
            "无法唯一确定时直接报错。该模式下 CBreakerDis 的逻辑 p_NameString=图上名称，"
            "接地刀闸=开关名+D，BusDis=BUS。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#60756d;")
        rg.addWidget(note, 4, 0, 1, 2)
        rg.setRowStretch(5, 1)

        rules_box = QGroupBox("RMU 设备数据库表与域配置")
        rules_box.setMinimumWidth(590)
        rules_box.setMinimumHeight(285)
        rules = QGridLayout(rules_box)
        rules.setContentsMargins(14, 18, 14, 14)
        rules.setHorizontalSpacing(12)
        rules.setVerticalSpacing(9)
        rules.setColumnStretch(0, 2)
        rules.setColumnStretch(1, 3)
        rules.setColumnStretch(2, 3)
        rules.addWidget(QLabel("G 图元类型"), 0, 0)
        rules.addWidget(QLabel("表号（Table ID）"), 0, 1)
        rules.addWidget(QLabel("域号（Domain）"), 0, 2)

        self.table_spins = {}
        self.domain_spins = {}
        saved_rules = config.get("device_rules", {})
        for row, (tag, default) in enumerate(DEFAULT_DEVICE_RULES.items(), start=1):
            vals = dict(default)
            vals.update(saved_rules.get(tag, {}))
            rules.addWidget(QLabel(tag), row, 0)

            table = NoWheelSpinBox()
            table.setRange(0, 999999)
            table.setValue(int(vals["table_id"]))
            table.setMinimumHeight(36)

            domain = NoWheelSpinBox()
            domain.setRange(0, 999999)
            domain.setValue(int(vals["domain"]))
            domain.setMinimumHeight(36)

            rules.addWidget(table, row, 1)
            rules.addWidget(domain, row, 2)
            self.table_spins[tag] = table
            self.domain_spins[tag] = domain

        reset = QPushButton("恢复 RMU 默认配置")
        reset.setMinimumHeight(36)
        reset.clicked.connect(self.restore_defaults)
        rules.addWidget(reset, len(DEFAULT_DEVICE_RULES) + 1, 0, 1, 3)

        top_row.addWidget(recog, 4)
        top_row.addWidget(rules_box, 7)
        root.addLayout(top_row)

        policy = QGroupBox("关联前强制校验策略")
        pl = QVBoxLayout(policy)
        policy_label = QLabel(
            "• CBreakerDis：CODE 不得为空；CODE 必须等于当前用于校验的 p_NameString，NAME 不参与判断。\n"
            "• ZhaiWaiJieDiDaoZha：与 CBreakerDis 空间配对；用于校验的 p_NameString=开关名+D；CODE 必须与其一致，NAME 不参与判断。\n"
            "• BusDis：CODE 不得为空；CODE 必须等于当前用于校验的 p_NameString；图上文字模式下该值固定为 BUS，NAME 不参与判断。\n"
            "• 使用 p_NameString 模式时仍严格校验 G XML 中的 p_NameString；"
            "使用图上文字模式时不读取三类设备 XML 的 p_NameString。\n"
            "• 三类设备的 G 图元数量必须与数据库 combined_id 下记录数完全一致；"
            "多一条或少一条都会禁止该 RMU 关联。"
        )
        policy_label.setWordWrap(True)
        pl.addWidget(policy_label)
        root.addWidget(policy)

    def restore_defaults(self):
        for tag, rule in DEFAULT_DEVICE_RULES.items():
            self.table_spins[tag].setValue(int(rule["table_id"]))
            self.domain_spins[tag].setValue(int(rule["domain"]))
        for pos, value in DEFAULT_NAME_POSITIONS.items():
            self.pos_checks[pos].setChecked(bool(value))
        self.breaker_source.setCurrentIndex(0)


class RmuModelModule(ModelModule):
    module_id = "RMU"
    display_name = "RMU 环网柜模型"
    description = "RMU 环网柜模型校验、关联预览及安全回写。"
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    def create_settings_widget(self, parent, config):
        return RmuSettingsWidget(config)

    def collect_settings(self, widget):
        positions = {k:v.isChecked() for k,v in widget.pos_checks.items()}
        if not any(positions.values()):
            raise ValueError("请至少选择一个环网柜名称位置。")

        runtime_rules = {}
        saved_rules = {}
        for tag, default in DEFAULT_DEVICE_RULES.items():
            table_id = widget.table_spins[tag].value()
            domain = widget.domain_spins[tag].value()
            runtime_rules[tag] = {
                "table_id": table_id,
                "domain": domain,
                "match_mode": default["match_mode"],
                "description": default["description"],
            }
            saved_rules[tag] = {"table_id": table_id, "domain": domain}

        return {
            "rmu_name_positions": positions,
            "breaker_name_source": widget.breaker_source.currentData(),
            "device_rules": saved_rules,
            "_runtime_rules": runtime_rules,
        }

    def _new_validator(self, db, settings, log_callback):
        rules = settings["_runtime_rules"]
        parser = GParser(
            required_rmu_tags=rules.keys(),
            label_regex=DEFAULT_LABEL_REGEX,
            max_distance=DEFAULT_LABEL_MAX_DISTANCE,
            overlap_tolerance=DEFAULT_LABEL_OVERLAP_TOLERANCE,
        )
        return RmuValidator(
            db,
            parser,
            rules,
            breaker_name_source=settings.get("breaker_name_source", "P_NAME_STRING"),
            log=log_callback,
        )

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        positions = [k for k,v in settings["rmu_name_positions"].items() if v]
        validator = self._new_validator(db, settings, log_callback)
        reports = []
        aggregate = {
            "rmu_frames":0, "rmu_pass":0, "rmu_fail":0,
            "rmu_association_eligible":0,
            "elements":0, "element_pass":0, "element_warn":0, "element_fail":0,
        }
        total_files = max(len(files), 1)
        for idx, g_file in enumerate(files, start=1):
            log_callback(f"[{idx}/{len(files)}] 正在处理：{g_file.name}")

            def _file_progress(current, total, message):
                if progress_callback:
                    fraction = (idx - 1 + (current / max(total, 1))) / total_files
                    # Module work occupies 5%~95% of the overall task.
                    percent = 5 + int(fraction * 90)
                    progress_callback(min(percent, 95), f"{g_file.name}：{message}")

            report = validator.validate_file(
                g_file,
                positions,
                progress_callback=_file_progress,
            )
            reports.append(report)
            for key in aggregate:
                aggregate[key] += report["summary"].get(key, 0)
        return reports, aggregate, settings["_runtime_rules"]

    @staticmethod
    def _attributes_for_row(row):
        attrs = {
            "app": "6500000",
            "voltype": "0",
            "p_ReportType": "1",
            "keyid": str(row["expected_keyid"]),
        }
        if row["object_type"] == "BusDis":
            attrs["state"] = "15"
        else:
            attrs["state"] = "41"
        return attrs

    def preview_association(self, db, files, settings, log_callback, progress_callback=None):
        reports, summary, rules = self.validate(db, files, settings, log_callback, progress_callback)
        changes_by_file = defaultdict(list)
        rows = []
        skipped_rmus = []

        for report in reports:
            g_file = report["g_file"]
            for rmu in report.get("rmu_results", []):
                if not rmu.get("association_eligible"):
                    skipped_rmus.append({
                        "g_file": g_file,
                        "rmu_name": rmu.get("rmu_name", ""),
                        "rmu_id": rmu.get("rmu_id", ""),
                        "reasons": rmu.get("association_block_reasons", []),
                    })
                    continue

                for row in rmu.get("device_rows", []):
                    if not row.get("xml_id"):
                        continue
                    if row.get("association_ready") != "YES":
                        continue

                    # Correctly linked models are intentionally skipped.
                    if row.get("writeback_needed") != "YES":
                        if row.get("model_link_correct") == "YES":
                            log_callback(
                                f"无需关联：RMU={row.get('rmu_name')} "
                                f"{row.get('object_type')} "
                                f"{row.get('selected_device_name')} 已正确关联。"
                            )
                        continue

                    attrs = self._attributes_for_row(row)
                    change = {
                        "xml_id": row["xml_id"],
                        "tag": row["object_type"],
                        "attributes": attrs,
                        "rmu_name": row.get("rmu_name", ""),
                        "rmu_id": row.get("rmu_id", ""),
                        "device_name": row.get("selected_device_name", ""),
                        "device_id": row.get("db_device_id", ""),
                        "expected_keyid": row.get("expected_keyid", ""),
                    }
                    changes_by_file[g_file].append(change)

                    preview_row = dict(row)
                    preview_row["reason"] = (
                        f"PREVIEW_WRITE app=6500000 voltype=0 p_ReportType=1 "
                        f"state={attrs['state']} keyid={attrs['keyid']}"
                    )
                    rows.append(preview_row)

        preview_summary = dict(summary)
        preview_summary["association_change_count"] = sum(len(v) for v in changes_by_file.values())
        preview_summary["association_skipped_rmu_count"] = len(skipped_rmus)
        preview_summary["already_linked_correct_count"] = sum(
            1
            for report in reports
            for rmu in report.get("rmu_results", [])
            for row in rmu.get("device_rows", [])
            if row.get("model_link_correct") == "YES"
        )

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

        return {
            "reports": reports,
            "rows": rows,
            "summary": preview_summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
            "skipped_rmus": skipped_rmus,
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "rmu_name_positions": dict(settings.get("rmu_name_positions", {})),
                "breaker_name_source": settings.get("breaker_name_source", "P_NAME_STRING"),
                "device_rules": dict(settings.get("device_rules", {})),
            },
        }

    def apply_association(self, db, files, settings, preview_data, log_callback):
        if not preview_data:
            raise RuntimeError("没有可执行的模型关联预览。")
        changes_by_file = preview_data.get("changes_by_file", {})
        if not changes_by_file:
            raise RuntimeError("关联预览中没有可写回的设备。")

        current_snapshot = {
            "rmu_name_positions": dict(settings.get("rmu_name_positions", {})),
            "breaker_name_source": settings.get("breaker_name_source", "P_NAME_STRING"),
            "device_rules": dict(settings.get("device_rules", {})),
        }
        if current_snapshot != preview_data.get("settings_snapshot", {}):
            raise RuntimeError("RMU 配置在关联预览后发生变化，请重新生成关联预览。")

        # Refuse to apply a stale preview if a G file changed after preview.
        for g_file, fingerprint in preview_data.get("file_fingerprints", {}).items():
            path = Path(g_file)
            stat = path.stat()
            if stat.st_size != fingerprint.get("size") or stat.st_mtime_ns != fingerprint.get("mtime_ns"):
                raise RuntimeError(
                    f"G 文件在关联预览后发生变化，禁止回写，请重新生成预览：{g_file}"
                )

        service = GWriteBackService(log=log_callback)
        results = []
        for g_file, changes in changes_by_file.items():
            log_callback(f"开始回写 G 文件：{g_file}，设备数={len(changes)}")
            result = service.apply_attribute_changes(
                g_file,
                changes,
                create_backup=True,
            )
            results.append(result)
            log_callback(
                f"回写完成：{g_file}；修改={result['applied_count']}；"
                f"备份={result['backup']}"
            )
        return results
