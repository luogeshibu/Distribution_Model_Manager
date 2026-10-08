from __future__ import annotations

import csv
import html
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from g_file_studio.engines.smart_profile_engine import (
    apply_smart_profile_to_file,
    apply_smart_profile_to_tree,
)
from g_file_studio.engines.standard_connection_cleanup import (
    inspect_standard_device_connections,
)
from g_file_studio.models import InputMode, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs
from g_file_studio.services.site_profile_service import (
    SiteProfileService,
    SiteSmartProfile,
    authoritative_geometry_templates,
)
from g_file_studio.services.report_i18n import report_is_english


@dataclass(frozen=True)
class SmartProfileProcessingSettings:
    source_path: Path
    input_mode: InputMode
    output_dir: Path
    profile: SiteSmartProfile
    # UI execution sets this True. Default False keeps internal/API compatibility
    # for legacy callers and unit fixtures created before authoritative standard files existed.
    require_authoritative_standard: bool = False


def _drift_candidates(counter: Counter[str], totals: dict[str, int]) -> list[str]:
    """Return diagnostic mismatch-frequency hints; never use business G as standard input."""
    hints: list[str] = []
    for key, count in counter.most_common():
        try:
            cabinet_class, role, devref = key.split(":", 2)
        except ValueError:
            continue
        denominator = totals.get(f"{cabinet_class}:{role}", 0)
        ratio = (count / denominator) if denominator else 0.0
        if count >= 5 and ratio >= 0.30:
            hints.append(f"{cabinet_class} {role}: {devref} ({count}/{denominator}, {ratio:.0%})")
    return hints


def _check_only(
    source: Path,
    *,
    profile: SiteSmartProfile,
    progress: ProgressCallback | None = None,
):
    """Run a read-only comparison against the locally frozen standard icon files.

    The business drawing is never used to learn/fill the expected geometry. The
    target devrefs come from role bindings and width/height/pin anchors come only
    from the managed server-derived icon-definition G files.
    """
    managed = bool(profile.managed_standard_files)
    connection_geometry_templates = (
        authoritative_geometry_templates(profile) if managed else profile.geometry_templates
    )
    kwargs = dict(
        smart_lbs_devref=profile.smart_lbs_devref,
        smart_breaker_devref=profile.smart_breaker_devref,
        normal_lbs_devref=profile.normal_lbs_devref,
        normal_breaker_devref=profile.normal_breaker_devref,
        smart_ground_devref=profile.smart_ground_devref,
        normal_ground_devref=profile.normal_ground_devref,
        profile_geometry_templates=connection_geometry_templates,
        custom_symbols=profile.custom_symbols,
        allow_source_geometry_fallback=not managed,
    )
    if progress:
        progress(2)
    tree = ET.parse(source)
    if progress:
        progress(8)
    eligible_devrefs, single_pin_devrefs = _standard_connection_scope(profile)
    connection_findings = inspect_standard_device_connections(
        tree,
        eligible_devrefs=eligible_devrefs,
        single_pin_devrefs=single_pin_devrefs,
        geometry_templates=connection_geometry_templates,
    )
    result = apply_smart_profile_to_tree(
        tree,
        source,
        **kwargs,
        progress=(lambda value: progress(8 + round(value * 0.92))) if progress else None,
    )
    if connection_findings.issues:
        result.mismatch_details.extend(
            _connection_issue_detail(source, issue) for issue in connection_findings.issues
        )
        result.mismatch_counts["TOPOLOGY:CONNECTION"] = len(connection_findings.issues)
    if progress:
        progress(100)
    return result




def _standard_connection_scope(profile: SiteSmartProfile) -> tuple[set[str], set[str]]:
    """Return standard devrefs for the separate topology-repair workflow.

    This compatibility helper remains available to read-only connection inspection
    and the Jeddah pipeline. The symbol-standard correction itself does not invoke
    connection normalization or alter line/topology objects.
    """
    devrefs = {
        value.strip() for value in (
            profile.smart_lbs_devref,
            profile.smart_breaker_devref,
            profile.normal_lbs_devref,
            profile.normal_breaker_devref,
            profile.smart_ground_devref,
            profile.normal_ground_devref,
        ) if value and value.strip()
    }
    for row in profile.custom_symbols or []:
        if bool(row.get("enabled", True)):
            value = str(row.get("standard_devref", "")).strip()
            if value:
                devrefs.add(value)

    geometry_payload = authoritative_geometry_templates(profile) if profile.managed_standard_files else profile.geometry_templates
    single_pin: set[str] = set()
    for devref, rows in (geometry_payload or {}).items():
        if devref not in devrefs or not isinstance(rows, list):
            continue
        valid_counts = {
            len(row.get("anchor_offsets", []))
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("anchor_offsets", []), list) and row.get("anchor_offsets")
        }
        if valid_counts == {1}:
            single_pin.add(devref)
    return devrefs, single_pin


def standard_connection_scope(profile: SiteSmartProfile) -> tuple[set[str], set[str]]:
    """Return the shared safe connection-cleanup scope for an authoritative Profile.

    Symbol Standard Correction and Jeddah Batch both use this helper so eligible
    devrefs and one-pin device classification can never drift between modules.
    """
    return _standard_connection_scope(profile)


def _connection_issue_detail(file_path: Path, issue) -> dict[str, object]:
    return {
        "File": file_path.name,
        "RMU": "-",
        "RMURectID": "-",
        "Scope": "TOPOLOGY",
        "Role": "ConnectLine",
        "ElementTag": "ConnectLine",
        "ElementID": issue.line_id or "-",
        "DeviceName": "-",
        "KeyName": "-",
        "Rotation": 0,
        "IssueType": issue.issue_type,
        "Reason": issue.reason,
        "CurrentDevref": "-",
        "StandardDevref": "-",
        "CurrentSize": "-",
        "StandardSize": "-",
        "CurrentPosition": issue.current or "-",
        "ExpectedPosition": issue.expected or "-",
        "ConnectedLines": issue.line_id or "-",
        "_AppliedDevrefChanged": False,
        "_AppliedGeometryChanged": False,
    }


def _expected_devref(profile: SiteSmartProfile, scope: str, role: str) -> str:
    scope = (scope or "").strip().upper()
    role_key = (role or "").strip().upper()
    if scope == "SMART":
        if role_key == "LBS":
            return profile.smart_lbs_devref
        if role_key == "BREAKER":
            return profile.smart_breaker_devref
        if role_key == "GROUND":
            return profile.smart_ground_devref
    if scope == "NORMAL":
        if role_key == "LBS":
            return profile.normal_lbs_devref
        if role_key == "BREAKER":
            return profile.normal_breaker_devref
        if role_key == "GROUND":
            return profile.normal_ground_devref
    if scope == "CUSTOM":
        matches = [
            str(row.get("standard_devref", "")).strip()
            for row in profile.custom_symbols
            if bool(row.get("enabled", True))
            and str(row.get("role", "")).strip().upper() == role_key
            and str(row.get("standard_devref", "")).strip()
        ]
        if len(set(matches)) == 1:
            return matches[0]
    return ""



def process_smart_profile_consistency(
    settings: SmartProfileProcessingSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    if not files:
        raise ValueError("没有找到可处理的 G 文件。")
    profile = settings.profile.normalized()
    if settings.require_authoritative_standard:
        standard_ready, standard_issues = SiteProfileService().validate_authoritative_standard(profile)
        if not standard_ready:
            raise ValueError(
                "当前 ACTIVE 图元标准不是完整的服务器标准库，不能执行检查：\n"
                + "\n".join(standard_issues[:10])
            )

    output_root = Path(settings.output_dir)
    report_dir = output_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0)

    rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    warnings: list[str] = []
    outputs: list[Path] = []
    mismatch_counter: Counter[str] = Counter()
    totals = {
        "files": len(files),
        "smart_rmus": 0,
        "normal_rmus": 0,
        "ignored_rmus": 0,
        "lbs_checked": 0,
        "breaker_checked": 0,
        "normal_lbs_checked": 0,
        "normal_breaker_checked": 0,
        "ground_checked": 0,
        "normal_ground_checked": 0,
        "lbs_changed": 0,
        "breaker_changed": 0,
        "normal_lbs_changed": 0,
        "normal_breaker_changed": 0,
        "ground_changed": 0,
        "normal_ground_changed": 0,
        "custom_checked": 0,
        "custom_changed": 0,
        "geometry_adjusted": 0,
    }
    log(
        f"[服务器图元更新检查] 模式：只检查（只读，不修改 G）；标准：{profile.profile_name} / "
        f"适用范围：{profile.site_name} / 服务器版本 {profile.server_standard_label} UTC / "
        f"标准指纹：{profile.standard_fingerprint or '-'}"
    )
    log(f"[服务器图元更新检查] SMART LBS devref：{profile.smart_lbs_devref}")
    log(f"[服务器图元更新检查] SMART Circuit Breaker devref：{profile.smart_breaker_devref}")
    if profile.normal_ready:
        log(f"[服务器图元更新检查] NORMAL LBS devref：{profile.normal_lbs_devref}")
        log(f"[服务器图元更新检查] NORMAL Circuit Breaker devref：{profile.normal_breaker_devref}")
    else:
        log("[服务器图元更新检查] NORMAL 标准尚未配置完整；普通 RMU 只统计，不参与该角色的一致性判定。")
    if profile.smart_ground_devref:
        log(f"[服务器图元更新检查] SMART 接地刀闸 devref：{profile.smart_ground_devref}")
    if profile.normal_ground_devref:
        log(f"[服务器图元更新检查] NORMAL 接地刀闸 devref：{profile.normal_ground_devref}")
    if profile.managed_standard_files:
        log(f"[服务器图元更新检查] 权威标准图元文件：{len(profile.managed_standard_files)} 个（仅使用服务器来源的本地冻结副本）")
        for row in profile.managed_standard_files[:12]:
            log(
                f"  - {row.get('original_name') or '-'} | {row.get('devref') or '-'} | "
                f"SHA256 {str(row.get('sha256') or '-')[:16]}"
            )
    enabled_custom = [row for row in profile.custom_symbols if bool(row.get("enabled", True)) and str(row.get("standard_devref", "")).strip()]
    if enabled_custom:
        log(f"[服务器图元更新检查] 自定义设备图元标准：{len(enabled_custom)} 项。")
        for row in enabled_custom[:12]:
            log(
                f"  - {row.get('scope', 'ANY')} / {row.get('role', '自定义')} / "
                f"{row.get('element_tag', '-')}: {row.get('standard_devref', '-')}"
            )

    content_span = 82
    file_total = max(1, len(files))
    for index, source in enumerate(files, 1):
        file_start = round((index - 1) * content_span / file_total)
        file_end = round(index * content_span / file_total)
        file_span = max(1, file_end - file_start)
        if progress:
            progress(file_start)
        result = _check_only(
            source,
            profile=profile,
            progress=(
                lambda value, start=file_start, span=file_span: progress(start + round(value * span / 100))
            ) if progress else None,
        )
        warnings.extend(result.warnings)
        mismatch_counter.update(result.mismatch_counts)
        totals["smart_rmus"] += result.smart_rmu_count
        totals["normal_rmus"] += result.normal_rmu_count
        totals["ignored_rmus"] += result.ignored_rmu_count
        totals["lbs_checked"] += result.lbs_checked_count
        totals["breaker_checked"] += result.breaker_checked_count
        totals["normal_lbs_checked"] += result.normal_lbs_checked_count
        totals["normal_breaker_checked"] += result.normal_breaker_checked_count
        totals["ground_checked"] += result.ground_checked_count
        totals["normal_ground_checked"] += result.normal_ground_checked_count
        totals["lbs_changed"] += result.lbs_changed_count
        totals["breaker_changed"] += result.breaker_changed_count
        totals["normal_lbs_changed"] += result.normal_lbs_changed_count
        totals["normal_breaker_changed"] += result.normal_breaker_changed_count
        totals["ground_changed"] += result.ground_changed_count
        totals["normal_ground_changed"] += result.normal_ground_changed_count
        totals["custom_checked"] += result.custom_checked_count
        totals["custom_changed"] += result.custom_changed_count
        totals["geometry_adjusted"] += result.geometry_adjusted_count

        detail_rows.extend(result.mismatch_details)
        nonstandard = len(result.mismatch_details)
        issue_counter = Counter(str(item.get("IssueType", "不符合标准")) for item in result.mismatch_details)
        issue_summary = "；".join(f"{name} ×{count}" for name, count in issue_counter.most_common()) or "-"
        row_result = "NON-STANDARD" if nonstandard else "STANDARD"
        if result.warnings:
            row_result += " WITH WARNINGS"

        rows.append({
            "File": source.name,
            "SmartRMUs": result.smart_rmu_count,
            "NormalRMUs": result.normal_rmu_count,
            "IgnoredRMUs": result.ignored_rmu_count,
            "SmartLBSChecked": result.lbs_checked_count,
            "SmartLBSChanged": result.lbs_changed_count,
            "SmartBreakerChecked": result.breaker_checked_count,
            "SmartBreakerChanged": result.breaker_changed_count,
            "NormalLBSChecked": result.normal_lbs_checked_count,
            "NormalLBSChanged": result.normal_lbs_changed_count,
            "NormalBreakerChecked": result.normal_breaker_checked_count,
            "NormalBreakerChanged": result.normal_breaker_changed_count,
            "SmartGroundChecked": result.ground_checked_count,
            "SmartGroundChanged": result.ground_changed_count,
            "NormalGroundChecked": result.normal_ground_checked_count,
            "NormalGroundChanged": result.normal_ground_changed_count,
            "CustomChecked": result.custom_checked_count,
            "CustomChanged": result.custom_changed_count,
            "GeometryAdjusted": result.geometry_adjusted_count,
            "NonstandardCount": nonstandard,
            "IssueSummary": issue_summary,
            "Result": row_result,
        })
        if nonstandard:
            warnings.append(
                f"{source.name}: 检测到 {nonstandard} 个图元/几何与当前 ACTIVE 标准不一致；本模块只告警和生成报告，不会替换或升级 G。"
            )
            for mismatch_key, count in sorted(result.mismatch_counts.items()):
                try:
                    scope, role, current_devref = mismatch_key.split(":", 2)
                except ValueError:
                    continue
                expected = _expected_devref(profile, scope, role)
                if expected:
                    warnings.append(
                        f"{source.name}: {scope} {role} 图元变体不符合标准 ×{count}；当前 {current_devref or '<空 devref>'}；应为 {expected}。"
                    )
                else:
                    warnings.append(
                        f"{source.name}: {scope} {role} 图元变体不符合标准 ×{count}；当前 {current_devref or '<空 devref>'}。"
                    )
            if result.geometry_adjusted_count:
                warnings.append(
                    f"{source.name}: 发现 {result.geometry_adjusted_count} 个图元几何参数（w/h、AlignCenter 或 pin 锚点）与标准不一致。"
                )
        log(
            f"[服务器图元更新检查] {source.name}：SMART RMU {result.smart_rmu_count}，NORMAL RMU {result.normal_rmu_count}；"
            f"SMART Y/Q/接地 不符合 {result.lbs_changed_count}/{result.breaker_changed_count}/{result.ground_changed_count}；"
            f"NORMAL Y/Q/接地 不符合 {result.normal_lbs_changed_count}/{result.normal_breaker_changed_count}/{result.normal_ground_changed_count}；"
            f"自定义设备检查/不符合 {result.custom_checked_count}/{result.custom_changed_count}；"
            f"几何不符合 {result.geometry_adjusted_count}。"
        )
        if progress:
            progress(file_end)

    if progress:
        progress(83)
    role_totals = {
        "SMART:LBS": totals["lbs_checked"],
        "SMART:BREAKER": totals["breaker_checked"],
        "NORMAL:LBS": totals["normal_lbs_checked"],
        "NORMAL:BREAKER": totals["normal_breaker_checked"],
        "SMART:GROUND": totals["ground_checked"],
        "NORMAL:GROUND": totals["normal_ground_checked"],
    }
    drift = _drift_candidates(mismatch_counter, role_totals)
    if drift:
        warnings.append("检测到可能的图元标准漂移：如这些图元属于新的确认标准，请用标准 G 文件重新扫描；待检查文件不会被自动学习。")
        for item in drift[:8]:
            log(f"[图元标准漂移] {item}")

    if progress:
        progress(85)
    csv_path = report_dir / "symbol-standard-check.csv"
    english = report_is_english()
    changed_word = "不符合"
    geometry_word = "图元几何不符合"
    header_map_zh = {
        "File": "文件",
        "SmartRMUs": "SMART环网柜",
        "NormalRMUs": "普通环网柜",
        "IgnoredRMUs": "忽略/特殊环网柜",
        "SmartLBSChecked": "SMART LBS检查",
        "SmartLBSChanged": f"SMART LBS{changed_word}",
        "SmartBreakerChecked": "SMART断路器检查",
        "SmartBreakerChanged": f"SMART断路器{changed_word}",
        "NormalLBSChecked": "普通LBS检查",
        "NormalLBSChanged": f"普通LBS{changed_word}",
        "NormalBreakerChecked": "普通断路器检查",
        "NormalBreakerChanged": f"普通断路器{changed_word}",
        "SmartGroundChecked": "SMART接地刀闸检查",
        "SmartGroundChanged": f"SMART接地刀闸{changed_word}",
        "NormalGroundChecked": "普通接地刀闸检查",
        "NormalGroundChanged": f"普通接地刀闸{changed_word}",
        "CustomChecked": "自定义设备检查",
        "CustomChanged": f"自定义设备{changed_word}",
        "GeometryAdjusted": geometry_word,
        "NonstandardCount": "不符合标准总数",
        "IssueSummary": "主要不符合原因",
        "Result": "结果",
    }
    internal_headers = list(rows[0].keys())
    display_headers = internal_headers if english else [header_map_zh.get(key, key) for key in internal_headers]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(display_headers)
        for row in rows:
            writer.writerow([row[key] for key in internal_headers])

    if progress:
        progress(89)
    detail_csv_path = report_dir / "symbol-standard-check-details.csv"
    detail_headers = [
        "File", "RMU", "RMURectID", "Scope", "Role", "ElementTag", "ElementID",
        "DeviceName", "KeyName", "Rotation", "IssueType", "Reason", "CurrentDevref",
        "StandardDevref", "CurrentSize", "StandardSize", "CurrentPosition",
        "ExpectedPosition", "ConnectedLines",
    ]
    detail_header_zh = {
        "File": "文件", "RMU": "RMU", "RMURectID": "RMU框ID", "Scope": "范围",
        "Role": "设备角色", "ElementTag": "XML元素", "ElementID": "元素ID",
        "DeviceName": "设备名", "KeyName": "key_name", "Rotation": "旋转角度",
        "IssueType": "问题类型", "Reason": "不符合原因", "CurrentDevref": "当前devref",
        "StandardDevref": "标准devref", "CurrentSize": "当前尺寸", "StandardSize": "标准尺寸",
        "CurrentPosition": "当前位置", "ExpectedPosition": "标准建议位置", "ConnectedLines": "关联连接线",
    }
    detail_display_headers = detail_headers if english else [detail_header_zh[key] for key in detail_headers]
    with detail_csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(detail_display_headers)
        for row in detail_rows:
            writer.writerow([row.get(key, "") for key in detail_headers])

    if progress:
        progress(92)
    html_path = report_dir / "symbol-standard-check.html"
    standard_file_rows = []
    for row in profile.managed_standard_files:
        standard_file_rows.append(
            f"{html.escape(str(row.get('original_name') or '-'))} | "
            f"{html.escape(str(row.get('devref') or '-'))} | SHA256 {html.escape(str(row.get('sha256') or '-')[:16])}"
        )
    standard_files_html = "<br>".join(standard_file_rows) or "-"

    if english:
        report_title = "Symbol Standard Check Report"
        meta = (
            f"Standard: {html.escape(profile.profile_name)} | Scope: {html.escape(profile.site_name)} | "
            f"Version: V{profile.profile_version} | Status: ACTIVE | Standard Fingerprint: {html.escape(profile.standard_fingerprint or '-')} | Mode: CHECK ONLY (READ-ONLY)"
        )
        symbols = (
            f"SMART LBS: {html.escape(profile.smart_lbs_devref)}<br>SMART Breaker: {html.escape(profile.smart_breaker_devref)}"
            f"<br>SMART Ground: {html.escape(profile.smart_ground_devref or '-')}"
            f"<br>NORMAL LBS: {html.escape(profile.normal_lbs_devref or '-')}<br>NORMAL Breaker: {html.escape(profile.normal_breaker_devref or '-')}"
            f"<br>NORMAL Ground: {html.escape(profile.normal_ground_devref or '-')}"
            f"<br>Custom Standards: {sum(1 for row in profile.custom_symbols if bool(row.get('enabled', True)))}"
            f"<br><br><b>Uploaded Standard Files</b><br>{standard_files_html}"
        )
        labels = {
            "overview": "Overview", "files": "Files", "nonstd_files": "Non-standard Files",
            "issues": "Non-standard Elements", "details": "Non-standard Details",
            "summary": "File Summary", "no_issue": "No non-standard elements were found.",
            "reason": "Why it is non-standard", "current": "Current", "expected": "Standard Requirement",
            "location": "Location / Element", "action": "Handling",
            "readonly": "This module only reports problems and never modifies the source G. Same-class OLD→NEW version upgrades are handled in Basic Processing.",
        }
    else:
        report_title = "服务器图元更新检查报告"
        meta = (
            f"标准：{html.escape(profile.profile_name)} | 适用范围：{html.escape(profile.site_name)} | "
            f"版本：V{profile.profile_version} | 状态：当前生效 | 标准指纹：{html.escape(profile.standard_fingerprint or '-')} | 模式：只检查（只读，不修改源 G）"
        )
        symbols = (
            f"SMART LBS：{html.escape(profile.smart_lbs_devref)}<br>SMART 断路器：{html.escape(profile.smart_breaker_devref)}"
            f"<br>SMART 接地刀闸：{html.escape(profile.smart_ground_devref or '-')}"
            f"<br>普通 LBS：{html.escape(profile.normal_lbs_devref or '-')}<br>普通断路器：{html.escape(profile.normal_breaker_devref or '-')}"
            f"<br>普通接地刀闸：{html.escape(profile.normal_ground_devref or '-')}"
            f"<br>自定义设备标准：{sum(1 for row in profile.custom_symbols if bool(row.get('enabled', True)))} 项"
            f"<br><br><b>服务器来源的权威标准图元文件</b><br>{standard_files_html}"
        )
        labels = {
            "overview": "检查概览", "files": "检查文件", "nonstd_files": "存在问题文件",
            "issues": "不符合标准图元", "details": "不符合标准明细",
            "summary": "文件检查汇总", "no_issue": "未发现不符合当前 ACTIVE 标准的图元。",
            "reason": "为什么不符合", "current": "当前值", "expected": "标准要求",
            "location": "位置 / 元素", "action": "处理建议",
            "readonly": "本模块只负责检查、告警和报告，不修改源 G。同类 OLD→NEW 图元版本升级请到“基础处理”执行。",
        }

    nonstandard_files = sum(1 for row in rows if int(row.get("NonstandardCount", 0) or 0) > 0)
    total_issues = len(detail_rows)
    summary_rows = []
    for row in rows:
        result_text = str(row.get("Result", ""))
        status_class = "bad" if result_text.startswith("NON-STANDARD") else "good"
        total_checked = (
            int(row.get("SmartLBSChecked", 0)) + int(row.get("SmartBreakerChecked", 0))
            + int(row.get("NormalLBSChecked", 0)) + int(row.get("NormalBreakerChecked", 0))
            + int(row.get("SmartGroundChecked", 0)) + int(row.get("NormalGroundChecked", 0))
            + int(row.get("CustomChecked", 0))
        )
        summary_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('File', '')))}</td>"
            f"<td>{row.get('SmartRMUs', 0)}</td><td>{row.get('NormalRMUs', 0)}</td>"
            f"<td>{total_checked}</td><td>{row.get('NonstandardCount', 0)}</td>"
            f"<td class='wrap'>{html.escape(str(row.get('IssueSummary', '-')))}</td>"
            f"<td><span class='badge {status_class}'>{html.escape(result_text)}</span></td>"
            "</tr>"
        )

    details_html = []
    for index, row in enumerate(detail_rows, 1):
        issue_type = html.escape(str(row.get("IssueType", "")))
        location = (
            f"RMU: {html.escape(str(row.get('RMU', '-')))}<br>"
            f"{html.escape(str(row.get('ElementTag', '-')))} / ID={html.escape(str(row.get('ElementID', '-')))}"
            f"<br>Name={html.escape(str(row.get('DeviceName', '-')))} / Rotate={html.escape(str(row.get('Rotation', 0)))}°"
        )
        current_value = (
            f"<b>devref</b>: {html.escape(str(row.get('CurrentDevref', '-')))}<br>"
            f"<b>size</b>: {html.escape(str(row.get('CurrentSize', '-')))}<br>"
            f"<b>position</b>: {html.escape(str(row.get('CurrentPosition', '-')))}"
        )
        expected_value = (
            f"<b>devref</b>: {html.escape(str(row.get('StandardDevref', '-')))}<br>"
            f"<b>size</b>: {html.escape(str(row.get('StandardSize', '-')))}<br>"
            f"<b>position</b>: {html.escape(str(row.get('ExpectedPosition', '-')))}"
        )
        action = labels["readonly"]
        details_html.append(
            "<tr class='issue-row'>"
            f"<td>{index}</td><td>{html.escape(str(row.get('File', '')))}</td>"
            f"<td>{location}</td>"
            f"<td><span class='badge bad'>{issue_type}</span><br><small>{html.escape(str(row.get('Scope', '')))} / {html.escape(str(row.get('Role', '')))}</small></td>"
            f"<td class='reason'>{html.escape(str(row.get('Reason', '')))}</td>"
            f"<td class='value'>{current_value}</td><td class='value expected'>{expected_value}</td>"
            f"<td>{html.escape(str(row.get('ConnectedLines', '-')))}</td>"
            f"<td class='action'>{html.escape(action)}</td>"
            "</tr>"
        )

    drift_html = ""
    if drift:
        title = "Standard Drift Candidates" if english else "图元标准漂移候选"
        note = (
            "If the server standard has changed, save a new local standard version. Business drawings are never learned or promoted into the standard."
            if english else "如服务器标准已变化，请保存新的本地标准版本；业务单线图永远不会被学习或提升为标准。"
        )
        drift_html = f"<section><h3>{title}</h3><ul>" + "".join(
            f"<li>{html.escape(item)}</li>" for item in drift
        ) + f"</ul><p>{html.escape(note)}</p></section>"

    details_section = (
        f"<div class='table-scroll'><table class='details'><thead><tr>"
        f"<th>#</th><th>{'文件' if not english else 'File'}</th><th>{labels['location']}</th>"
        f"<th>{'问题类型' if not english else 'Issue Type'}</th><th>{labels['reason']}</th>"
        f"<th>{labels['current']}</th><th>{labels['expected']}</th>"
        f"<th>{'关联连接线' if not english else 'Connected Lines'}</th><th>{labels['action']}</th>"
        f"</tr></thead><tbody>{''.join(details_html)}</tbody></table></div>"
        if details_html else f"<div class='empty'>{labels['no_issue']}</div>"
    )

    if progress:
        progress(96)
    html_path.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(report_title)}</title>"
        "<style>"
        "*{box-sizing:border-box}body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:0;background:#f5f8f7;color:#173042}"
        ".page{max-width:1800px;margin:0 auto;padding:24px}.hero{background:#fff;border:1px solid #dbe7e3;border-radius:14px;padding:22px 24px;margin-bottom:16px}"
        "h1{margin:0 0 12px;font-size:25px;color:#0b5d4b}h2{font-size:19px;margin:0 0 12px}h3{color:#0b5d4b}"
        ".meta{color:#52656e;line-height:1.7}.notice{margin-top:14px;padding:12px 14px;border-left:4px solid #0f8a6a;background:#eef9f5;border-radius:6px}"
        ".cards{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px;margin:16px 0}.card{background:#fff;border:1px solid #dbe7e3;border-radius:12px;padding:16px}"
        ".card .n{font-size:28px;font-weight:700;color:#0f6f59}.card.bad-card .n{color:#b42318}.card .t{color:#667984;font-size:13px;margin-top:4px}"
        "section{background:#fff;border:1px solid #dbe7e3;border-radius:14px;padding:18px;margin:16px 0}.table-scroll{overflow:auto;border-radius:10px;border:1px solid #d7e2df}"
        "table{border-collapse:collapse;width:100%;background:#fff}th,td{border-bottom:1px solid #e1e9e6;padding:10px 11px;text-align:left;vertical-align:top}th{background:#e8f3ef;color:#16483c;white-space:nowrap;position:sticky;top:0}"
        "tr:last-child td{border-bottom:0}.wrap{min-width:260px;white-space:normal}.details{min-width:1500px}.details td{font-size:13px}.reason{min-width:360px;line-height:1.55;background:#fff8f6}"
        ".value{min-width:250px;line-height:1.55;word-break:break-all}.expected{background:#f0faf6}.action{min-width:260px;line-height:1.5;color:#52656e}"
        ".badge{display:inline-block;padding:4px 8px;border-radius:999px;font-weight:600;font-size:12px}.badge.good{background:#e7f7ef;color:#12633f}.badge.bad{background:#fdebea;color:#a83228}"
        ".empty{padding:28px;text-align:center;color:#60727b;background:#fafcfb;border:1px dashed #cfdcd8;border-radius:10px}.symbols{columns:2;column-gap:28px;line-height:1.65;font-size:13px;word-break:break-all}"
        "@media(max-width:900px){.cards{grid-template-columns:1fr 1fr}.symbols{columns:1}.page{padding:12px}}"
        "</style></head><body><div class='page'>"
        f"<div class='hero'><h1>{html.escape(report_title)}</h1><div class='meta'>{meta}</div>"
        f"<div class='notice'>{html.escape(labels['readonly'])}</div></div>"
        f"<div class='cards'><div class='card'><div class='n'>{len(rows)}</div><div class='t'>{labels['files']}</div></div>"
        f"<div class='card bad-card'><div class='n'>{nonstandard_files}</div><div class='t'>{labels['nonstd_files']}</div></div>"
        f"<div class='card bad-card'><div class='n'>{total_issues}</div><div class='t'>{labels['issues']}</div></div>"
        f"<div class='card'><div class='n'>{profile.profile_version}</div><div class='t'>{'ACTIVE 标准版本' if not english else 'ACTIVE Standard Version'}</div></div></div>"
        f"<section><h2>{'当前 ACTIVE 图元标准' if not english else 'Current ACTIVE Symbol Standard'}</h2><div class='symbols'>{symbols}</div></section>"
        f"<section><h2>{labels['summary']}</h2><div class='table-scroll'><table><thead><tr>"
        f"<th>{'文件' if not english else 'File'}</th><th>SMART RMU</th><th>NORMAL RMU</th><th>{'检查图元' if not english else 'Checked'}</th>"
        f"<th>{labels['issues']}</th><th>{'主要不符合原因' if not english else 'Main Issues'}</th><th>{'结果' if not english else 'Result'}</th>"
        f"</tr></thead><tbody>{''.join(summary_rows)}</tbody></table></div></section>"
        f"<section><h2>{labels['details']}</h2>{details_section}</section>"
        f"{drift_html}</div></body></html>",
        encoding="utf-8",
    )
    outputs.extend([csv_path, detail_csv_path, html_path])
    if progress:
        progress(100)
    nonstandard_total = len(detail_rows)
    # Business drawings are inspection targets only. v2.18.79 deliberately does
    # not build/persist an unmapped-symbol catalog from them; standards come only
    # from the server-derived frozen icon repository.
    unmanaged_symbol_count = 0
    return ProcessingResult(
        success=True,
        output_files=outputs,
        warnings=warnings,
        statistics={
            "Mode": "CHECK",
            "Profile": profile.profile_name,
            "Profile Version": profile.profile_version,
            "Standard Fingerprint": profile.standard_fingerprint,
            "Site": profile.site_name,
            "SMART RMUs": totals["smart_rmus"],
            "NORMAL RMUs": totals["normal_rmus"],
            "Ignored RMUs": totals["ignored_rmus"],
            "SMART LBS Changed": totals["lbs_changed"],
            "SMART Breaker Changed": totals["breaker_changed"],
            "NORMAL LBS Changed": totals["normal_lbs_changed"],
            "NORMAL Breaker Changed": totals["normal_breaker_changed"],
            "SMART Ground Changed": totals["ground_changed"],
            "NORMAL Ground Changed": totals["normal_ground_changed"],
            "Custom Symbols Checked": totals["custom_checked"],
            "Custom Symbols Changed": totals["custom_changed"],
            "Geometry Adjusted": totals["geometry_adjusted"],
            "Nonstandard Symbols": nonstandard_total,
            "Profile Drift Candidates": len(drift),
            "Unmanaged Symbols": unmanaged_symbol_count,
            "_UnmappedSymbolCandidates": [],
            "New Unmapped Symbols": 0,
            "Pending Unmapped Symbols": 0,
        },
    )



def process_smart_profile_correction(
    settings: SmartProfileProcessingSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    """Create corrected G copies from the current ACTIVE symbol standard.

    This is the write-capable companion of :func:`process_smart_profile_consistency`.
    It never overwrites the selected source G files.  Only symbols explicitly
    covered by the ACTIVE standard (the six built-in RMU roles plus enabled custom
    symbol rows) are normalized.  The shared anchor-preserving engine keeps
    ConnectLine electrical endpoints fixed whenever a reliable geometry template
    can be fitted; ambiguous mappings remain unchanged and are surfaced as warnings
    by the engine/post-check instead of being guessed.

    Jeddah batch processing does not call this function.  Its pipeline remains
    independent and unchanged.
    """
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    if not files:
        raise ValueError("没有找到可处理的 G 文件。")
    profile = settings.profile.normalized()
    if settings.require_authoritative_standard:
        standard_ready, standard_issues = SiteProfileService().validate_authoritative_standard(profile)
        if not standard_ready:
            raise ValueError(
                "当前 ACTIVE 图元标准不是完整的服务器标准库，不能执行检查：\n"
                + "\n".join(standard_issues[:10])
            )

    output_root = Path(settings.output_dir)
    corrected_dir = output_root / "corrected"
    corrected_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0)

    managed = bool(profile.managed_standard_files)
    connection_geometry_templates = (
        authoritative_geometry_templates(profile) if managed else profile.geometry_templates
    )
    kwargs = dict(
        smart_lbs_devref=profile.smart_lbs_devref,
        smart_breaker_devref=profile.smart_breaker_devref,
        normal_lbs_devref=profile.normal_lbs_devref,
        normal_breaker_devref=profile.normal_breaker_devref,
        smart_ground_devref=profile.smart_ground_devref,
        normal_ground_devref=profile.normal_ground_devref,
        profile_geometry_templates=connection_geometry_templates,
        custom_symbols=profile.custom_symbols,
        require_template_for_connected_devref_change=True,
        allow_source_geometry_fallback=not managed,
    )

    log(
        f"[图元标准纠正] 标准：{profile.profile_name} / 适用范围：{profile.site_name} / "
        f"服务器版本 {profile.server_standard_label} UTC / 标准指纹：{profile.standard_fingerprint or '-'}；"
        f"源 G 只读，纠正副本输出到：{corrected_dir}"
    )
    log(
        "[图元标准纠正] 仅处理 ACTIVE 标准已定义的设备图元。目标图元几何可可靠拟合时，"
        "保持现有电气锚点绝对位置并反算设备 x/y/w/h；不删除、重画或正交化 ConnectLine/FeedLine/Bus。"
        "未纳入标准或无法可靠映射的图元不猜测。"
    )

    outputs: list[Path] = []
    warnings: list[str] = []
    changed_files = 0
    corrected_elements = 0
    devref_changes = 0
    geometry_changes = 0
    redundant_lines_removed = 0
    connection_lines_straightened = 0
    connection_devices_realigned = 0
    connection_endpoints_connected = 0
    connection_topology_links_repaired = 0
    correction_span = 62
    file_total = max(1, len(files))
    for index, source in enumerate(files, 1):
        file_start = round((index - 1) * correction_span / file_total)
        file_end = round(index * correction_span / file_total)
        file_span = max(1, file_end - file_start)
        if progress:
            progress(file_start)
        target = corrected_dir / source.name
        applied = apply_smart_profile_to_file(
            source,
            target,
            **kwargs,
            progress=(
                lambda value, start=file_start, span=file_span: progress(start + round(value * span / 100))
            ) if progress else None,
        )
        outputs.append(target)
        warnings.extend(applied.warnings)
        file_corrected = sum(
            1 for row in applied.mismatch_details
            if bool(row.get("_AppliedDevrefChanged")) or bool(row.get("_AppliedGeometryChanged"))
        )
        corrected_elements += file_corrected
        devref_changes += applied.changed_count
        geometry_changes += applied.geometry_adjusted_count
        if applied.changed_count or applied.geometry_adjusted_count:
            changed_files += 1
        log(
            f"[图元标准纠正] {source.name}：发现/处理 {file_corrected} 个标准差异；"
            f"devref/变体纠正 {applied.changed_count}，设备图元几何纠正 {applied.geometry_adjusted_count}；"
            "线路与拓扑关系保持不变。"
        )
        if progress:
            progress(file_end)

    if progress:
        progress(62)
    # Always run a read-only post-check on the corrected copies.  The familiar
    # detailed HTML/CSV report therefore describes what, if anything, remains after
    # correction rather than forcing users to run the checker a second time.
    post_dir = output_root / "post-check"
    post_settings = SmartProfileProcessingSettings(
        source_path=corrected_dir,
        input_mode=InputMode.DIRECTORY,
        output_dir=post_dir,
        profile=profile,
    )
    post_result = process_smart_profile_consistency(
        post_settings,
        log=log,
        progress=(lambda value: progress(62 + round(value * 0.37))) if progress else None,
    )
    outputs.extend(post_result.output_files)
    warnings.extend(post_result.warnings)

    stats = dict(post_result.statistics or {})
    stats.update({
        "Mode": "CORRECT",
        "Corrected Output Directory": str(corrected_dir),
        "Corrected Files": changed_files,
        "Output G Files": len(files),
        "Corrected Elements": corrected_elements,
        "Devref Corrections": devref_changes,
        "Geometry Corrections": geometry_changes,
        "Redundant Connection Lines Removed": redundant_lines_removed,
        "Connection Lines Straightened": connection_lines_straightened,
        "Connection Devices Realigned": connection_devices_realigned,
        "Connection Endpoints Connected": connection_endpoints_connected,
        "Connection Topology Links Repaired": connection_topology_links_repaired,
        "Remaining Nonstandard Symbols": int(stats.get("Nonstandard Symbols", 0) or 0),
    })
    if progress:
        progress(100)
    return ProcessingResult(
        success=True,
        output_files=outputs,
        warnings=warnings,
        statistics=stats,
    )
