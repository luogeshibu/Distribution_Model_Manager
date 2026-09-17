#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path

from dmm.config.constants import APP_NAME, APP_NAME_EN, APP_VERSION
from dmm.i18n import normalize_language, translate_runtime_text



FEEDER_FIELDS = [
    "file_name",
    "drawing_type",
    "drawing_mode",
    "automatic_drawing_type",
    "classification_reason",
    "region_index",
    "region_identity_confidence",
    "feeder_resolution_source",
    "feeder_resolution_evidence",
    "fingerprint_match_ratio",
    "current_feeder_ids",
    "current_feeder_count",
    "majority_feeder_id",
    "majority_feeder_count",
    "anomaly_count",
    "feeder_db_count",
    "feeder_id",
    "feeder_name",
    "station_name",
    "station_bv_id",
    "section_nominal_voltage_kv",
    "section_prefix",
    "feedline_count",
    "database_section_count",
    "planned_create_count",
    "linked_correct_count",
    "unlinked_count",
    "error_count",
    "association_ready_count",
    "association_eligible",
    "status",
    "severity",
    "reason",
]

FEEDLINE_FIELDS = [
    "file_name",
    "feeder_name",
    "feeder_resolution_source",
    "topology_region",
    "current_feeder_name",
    "order_index",
    "object_type",
    "xml_id",
    "ls",
    "planned_section_type",
    "db_create_needed",
    "model_linked",
    "model_link_correct",
    "current_keyid",
    "current_device_id",
    "current_table_id",
    "current_domain",
    "current_db_name",
    "current_db_code",
    "current_bv_id",
    "current_feeder_id",
    "assigned_device_id",
    "assigned_section_name",
    "assigned_bv_id",
    "expected_keyid",
    "expected_keyid_verified",
    "association_ready",
    "writeback_needed",
    "status",
    "severity",
    "reason",
]

FEEDER_LABELS = {
    "file_name": "G文件",
    "drawing_type": "最终图纸类型",
    "drawing_mode": "图纸类型设置",
    "automatic_drawing_type": "自动拓扑识别",
    "classification_reason": "最终分型判据",
    "region_index": "区域序号",
    "region_identity_confidence": "区域身份置信度",
    "feeder_resolution_source": "馈线识别方式",
    "feeder_resolution_evidence": "馈线识别依据",
    "fingerprint_match_ratio": "单馈线指纹匹配率",
    "current_feeder_ids": "当前区域FEEDER_ID集合",
    "current_feeder_count": "当前区域FEEDER_ID数量",
    "majority_feeder_id": "多数FEEDER_ID",
    "majority_feeder_count": "多数FEEDER_ID条数",
    "anomaly_count": "异常FeedLine数",
    "feeder_db_count": "13500数据库匹配数",
    "feeder_id": "馈线ID",
    "feeder_name": "数据库馈线名称",
    "station_name": "所属变电站",
    "station_bv_id": "馈线段创建BV_ID",
    "section_nominal_voltage_kv": "馈线段创建电压等级(kV)",
    "section_prefix": "馈线段名称前缀",
    "feedline_count": "FeedLine图元数",
    "database_section_count": "数据库已有馈线段数",
    "planned_create_count": "计划新增馈线段数",
    "linked_correct_count": "已正确关联数",
    "unlinked_count": "未关联数",
    "error_count": "错误数",
    "association_ready_count": "可执行关联数",
    "association_eligible": "馈线可执行关联",
    "status": "状态",
    "severity": "状态类型",
    "reason": "说明",
}

FEEDLINE_LABELS = {
    "file_name": "G文件",
    "feeder_name": "馈线名称",
    "feeder_resolution_source": "馈线识别方式",
    "topology_region": "拓扑区域",
    "current_feeder_name": "当前所属馈线名称",
    "order_index": "FeedLine序号",
    "object_type": "G图元类型",
    "xml_id": "图元XML ID",
    "ls": "ls",
    "planned_section_type": "SECTION_TYPE",
    "db_create_needed": "是否需要创建数据库馈线段",
    "model_linked": "是否已关联",
    "model_link_correct": "当前模型是否正确",
    "current_keyid": "当前KeyID",
    "current_device_id": "当前数据库馈线段ID",
    "current_table_id": "当前表号",
    "current_domain": "当前域号",
    "current_db_name": "当前数据库馈线段NAME",
    "current_db_code": "当前数据库馈线段CODE",
    "current_bv_id": "当前模型BV_ID",
    "current_feeder_id": "当前模型所属馈线ID",
    "assigned_device_id": "目标馈线段ID",
    "assigned_section_name": "目标馈线段NAME",
    "assigned_bv_id": "目标BV_ID / voltype",
    "expected_keyid": "期望KeyID",
    "expected_keyid_verified": "期望KeyID校验",
    "association_ready": "可进入关联流程",
    "writeback_needed": "是否需要回写",
    "status": "状态",
    "severity": "状态类型",
    "reason": "说明",
}


DEVICE_FIELDS = [
    "rmu_name", "rmu_id",
    "object_type", "xml_id", "logical_code", "graphical_name",
    "selected_name_source", "selected_device_name", "paired_breaker_name",
    "table_id", "table_name", "configured_domain", "match_mode",
    "db_match_count", "db_device_id", "db_code", "db_name",
    "db_combined_id", "db_bv_id",
    "expected_keyid", "expected_keyid_verified",
    "current_keyid", "current_device_id", "current_table_id", "current_domain",
    "current_table_name", "current_db_code", "current_db_name",
    "current_combined_id", "current_rmu_name",
    "current_rmu_match", "current_rmu_name_match",
    "model_linked", "model_link_correct", "model_link_status",
    "association_action", "writeback_needed",
    "association_ready", "status", "severity", "reason",
]

POLE_FIELDS = [
    "file_name", "object_type", "xml_id", "device_model", "device_family",
    "devref", "graphical_name", "name_source", "name_distance",
    "name_direction", "name_xml_id", "inside_rmu",
    "key_name", "current_keyid", "current_device_id", "current_table_id",
    "current_domain", "current_db_name", "current_db_code",
    "current_combined_id", "combined_name", "combined_db_code", "combined_db_name",
    "combined_match_field", "combined_db_match_count", "db_combined_id",
    "cb_parent_match_count", "cb_db_match_count", "db_device_id", "db_code",
    "db_name", "db_cb_combined_id", "db_bv_id", "table_id", "table_name",
    "configured_domain", "expected_keyid", "expected_keyid_verified",
    "model_linked", "model_link_correct", "model_link_status",
    "association_action", "association_ready", "writeback_needed",
    "status", "severity", "reason",
]

POLE_LABELS = {
    "file_name": "G文件", "object_type": "G图元类型", "xml_id": "图元XML ID（来源：G文件）",
    "device_model": "柱上开关型号", "device_family": "设备族",
    "devref": "devref", "graphical_name": "图上名称", "name_source": "名称来源",
    "name_distance": "名称距离", "name_direction": "名称方向", "name_xml_id": "名称XML ID",
    "inside_rmu": "是否在环网柜内", "key_name": "XML key_name",
    "current_keyid": "当前KeyID（来源：G文件）", "current_device_id": "当前设备ID（来源：数据库）",
    "current_table_id": "当前表号（KeyID反解/数据库定义）", "current_domain": "当前域号（KeyID反解/数据库定义）",
    "current_db_name": "当前模型设备NAME（来源：数据库）", "current_db_code": "当前模型设备CODE（来源：数据库）",
    "current_combined_id": "当前模型combined_id", "combined_name": "图上名称/查询值",
    "combined_db_code": "13501 CODE（来源：数据库）", "combined_db_name": "13501 NAME（来源：数据库）",
    "combined_match_field": "13501匹配字段",
    "combined_db_match_count": "13501匹配数", "db_combined_id": "13501 ID（来源：数据库）",
    "cb_parent_match_count": "13502父设备记录数",
    "cb_db_match_count": "13502目标匹配数", "db_device_id": "目标设备ID（来源：数据库）",
    "db_code": "目标设备CODE（来源：数据库）", "db_name": "目标设备NAME（来源：数据库）",
    "db_cb_combined_id": "目标combined_id（来源：数据库）", "db_bv_id": "目标BV_ID（来源：数据库）",
    "table_id": "目标表号（来源：数据库定义）", "table_name": "目标数据库表（来源：数据库）",
    "configured_domain": "目标域号（来源：数据库定义）", "expected_keyid": "期望KeyID（程序计算）",
    "expected_keyid_verified": "期望KeyID校验（数据库）", "model_linked": "是否已关联",
    "model_link_correct": "当前模型是否正确", "model_link_status": "当前模型状态",
    "association_action": "处理建议", "association_ready": "可进入关联流程",
    "writeback_needed": "是否需要回写", "status": "状态", "severity": "状态类型",
    "reason": "说明",
}

POLE_LABELS_EN = {
    key: value for key, value in {
        "file_name": "G File", "object_type": "G Object Type", "xml_id": "XML ID (G File)",
        "device_model": "Pole Switch Model", "device_family": "Device Family",
        "devref": "devref", "graphical_name": "Graphical Name", "name_source": "Name Source",
        "name_distance": "Name Distance", "name_direction": "Name Direction", "name_xml_id": "Name XML ID",
        "inside_rmu": "Inside RMU", "key_name": "XML key_name",
        "current_keyid": "Current KeyID (G File)", "current_device_id": "Current Device ID (Database)",
        "current_table_id": "Current Table ID (Decoded/DB Definition)", "current_domain": "Current Domain (Decoded/DB Definition)",
        "current_db_name": "Current Model NAME (Database)", "current_db_code": "Current Model CODE (Database)",
        "current_combined_id": "Current Model combined_id", "combined_name": "Graphical Name / Lookup",
        "combined_db_code": "13501 CODE (Database)", "combined_db_name": "13501 NAME (Database)",
        "combined_match_field": "13501 Match Field",
        "combined_db_match_count": "13501 Match Count", "db_combined_id": "13501 ID (Database)",
        "cb_parent_match_count": "13502 Parent Record Count",
        "cb_db_match_count": "13502 Target Match Count", "db_device_id": "Target Device ID (Database)",
        "db_code": "Target Device CODE (Database)", "db_name": "Target Device NAME (Database)",
        "db_cb_combined_id": "Target combined_id (Database)", "db_bv_id": "Target BV_ID (Database)",
        "table_id": "Target Table ID (Database Definition)", "table_name": "Target Database Table (Database)",
        "configured_domain": "Target Domain (Database Definition)", "expected_keyid": "Expected KeyID (Calculated)",
        "expected_keyid_verified": "Expected KeyID Check (Database)", "model_linked": "Model Linked",
        "model_link_correct": "Current Model Correct", "model_link_status": "Current Model Status",
        "association_action": "Recommended Action", "association_ready": "Ready for Association",
        "writeback_needed": "Write-back Needed", "status": "Status", "severity": "Status Type",
        "reason": "Details",
    }.items()
}

TRANSFORMER_FIELDS = [
    "file_name", "object_type", "xml_id", "devref", "graphical_name",
    "name_source", "name_distance", "name_direction", "name_xml_id",
    "feeder_resolution_source", "feeder_id",
    "feeder_name", "current_keyid", "current_keyid1", "current_keyid2",
    "current_device_id", "current_table_id", "current_domain",
    "current_db_name", "current_db_code", "current_feeder_id",
    "db_match_count", "db_device_id", "db_code", "db_name", "db_feeder_id",
    "table_id", "table_name", "configured_domain", "expected_keyid",
    "expected_keyid_verified", "model_linked", "model_link_correct",
    "model_link_status", "association_action", "association_ready",
    "writeback_needed", "status", "severity", "reason",
]

TRANSFORMER_LABELS = {
    "file_name": "G文件", "object_type": "G图元类型", "xml_id": "图元XML ID（来源：G文件）",
    "devref": "devref", "graphical_name": "图上名称", "name_source": "名称来源",
    "name_distance": "名称距离", "name_direction": "名称方向", "name_xml_id": "名称XML ID",
    "feeder_resolution_source": "馈线识别方式", "feeder_id": "目标馈线ID",
    "feeder_name": "目标馈线名称（来源：数据库）", "current_keyid": "当前KeyID（来源：G文件）",
    "current_keyid1": "当前keyid1", "current_keyid2": "当前keyid2",
    "current_device_id": "当前设备ID（来源：数据库）", "current_table_id": "当前表号（KeyID反解/数据库定义）",
    "current_domain": "当前域号（KeyID反解/数据库定义）", "current_db_name": "当前模型设备NAME（来源：数据库）",
    "current_db_code": "当前模型设备CODE（来源：数据库）", "current_feeder_id": "当前模型馈线ID（来源：数据库）",
    "db_match_count": "13505匹配数", "db_device_id": "目标设备ID",
    "db_code": "目标设备CODE（来源：数据库）", "db_name": "目标设备NAME（来源：数据库）",
    "db_feeder_id": "目标设备馈线ID（来源：数据库）", "table_id": "目标表号（来源：数据库定义）",
    "table_name": "目标数据库表（来源：数据库）", "configured_domain": "目标域号（来源：数据库定义）",
    "expected_keyid": "期望KeyID（程序计算）", "expected_keyid_verified": "期望KeyID校验（数据库）",
    "model_linked": "是否已关联", "model_link_correct": "当前模型是否正确",
    "model_link_status": "当前模型状态", "association_action": "处理建议",
    "association_ready": "可进入关联流程", "writeback_needed": "是否需要回写",
    "status": "状态", "severity": "状态类型", "reason": "说明",
}

TRANSFORMER_LABELS_EN = {
    "file_name": "G File", "object_type": "G Object Type", "xml_id": "XML ID (G File)",
    "devref": "devref", "graphical_name": "Graphical Name", "name_source": "Name Source",
    "name_distance": "Name Distance", "name_direction": "Name Direction", "name_xml_id": "Name XML ID",
    "feeder_resolution_source": "Feeder Resolution Source", "feeder_id": "Target Feeder ID",
    "feeder_name": "Target Feeder Name (Database)", "current_keyid": "Current KeyID (G File)",
    "current_keyid1": "Current keyid1", "current_keyid2": "Current keyid2",
    "current_device_id": "Current Device ID (Database)", "current_table_id": "Current Table ID (Decoded/DB Definition)",
    "current_domain": "Current Domain (Decoded/DB Definition)", "current_db_name": "Current Model NAME (Database)",
    "current_db_code": "Current Model CODE (Database)", "current_feeder_id": "Current Model Feeder ID (Database)",
    "db_match_count": "13505 Match Count", "db_device_id": "Target Device ID",
    "db_code": "Target Device CODE (Database)", "db_name": "Target Device NAME (Database)",
    "db_feeder_id": "Target Feeder ID (Database)", "table_id": "Target Table ID (Database Definition)",
    "table_name": "Target Database Table (Database)", "configured_domain": "Target Domain (Database Definition)",
    "expected_keyid": "Expected KeyID (Calculated)", "expected_keyid_verified": "Expected KeyID Check (Database)",
    "model_linked": "Model Linked", "model_link_correct": "Current Model Correct",
    "model_link_status": "Current Model Status", "association_action": "Recommended Action",
    "association_ready": "Ready for Association", "writeback_needed": "Write-back Needed",
    "status": "Status", "severity": "Status Type", "reason": "Details",
}

MASTER_STATION_FIELDS = [
    "file_name", "object_type", "xml_id", "key_name", "logical_code",
    "context_source", "context_station_id", "context_station_name",
    "context_feeder_id", "context_feeder_code", "context_feeder_name", "context_bay_id",
    "context_rmu_frame_xml_id", "context_rmu_id", "context_rmu_name",
    "context_anchor_type", "context_anchor_xml_id", "context_anchor_keyid",
    "current_keyid", "current_device_id", "current_table_id", "current_domain",
    "table_id", "table_name", "configured_domain", "db_match_count",
    "db_device_id", "db_code", "db_name", "db_bv_id", "expected_keyid",
    "expected_keyid_verified", "model_linked", "model_link_correct",
    "model_link_status", "association_action", "association_ready",
    "writeback_needed", "status", "severity", "reason",
]

MASTER_STATION_LABELS = {
    "file_name": "G文件", "object_type": "G图元类型", "xml_id": "图元XML ID（来源：G文件）",
    "key_name": "XML key_name（来源：G文件）", "logical_code": "解析出的CODE（来源：G文件）",
    "context_source": "馈线上下文来源（KeyID/数据库）", "context_station_id": "厂站ID（数据库）",
    "context_station_name": "厂站名称（数据库）", "context_feeder_id": "馈线ID（数据库）",
    "context_feeder_code": "馈线CODE（数据库）", "context_feeder_name": "馈线名称（数据库）",
    "context_bay_id": "锚点Bay ID（数据库）",
    "context_rmu_frame_xml_id": "最近环网柜矩形框XML ID（G文件）",
    "context_rmu_id": "环网柜ID（数据库）", "context_rmu_name": "环网柜名称（数据库）",
    "context_anchor_type": "框内关联锚点类型（G文件）",
    "context_anchor_xml_id": "框内关联锚点XML ID（G文件）",
    "context_anchor_keyid": "框内关联锚点KeyID（G文件）",
    "current_keyid": "当前KeyID（来源：G文件）", "current_device_id": "当前设备ID（KeyID反解）",
    "current_table_id": "当前表号（KeyID反解）", "current_domain": "当前域号（KeyID反解）",
    "table_id": "目标表号（配置/数据库定义）", "table_name": "目标数据库表（数据库）",
    "configured_domain": "目标域号（配置/数据库定义）", "db_match_count": "CODE匹配数（数据库）",
    "db_device_id": "目标设备ID（数据库）", "db_code": "目标CODE（数据库）",
    "db_name": "目标NAME（数据库）", "db_bv_id": "目标BV_ID（数据库）",
    "expected_keyid": "期望KeyID（程序计算）", "expected_keyid_verified": "期望KeyID校验（数据库）",
    "model_linked": "是否已关联", "model_link_correct": "当前模型是否正确",
    "model_link_status": "当前模型状态", "association_action": "处理建议",
    "association_ready": "可进入关联流程", "writeback_needed": "是否需要回写",
    "status": "状态", "severity": "状态类型", "reason": "说明",
}
MASTER_STATION_LABELS_EN = {
    key: value for key, value in {
        "file_name": "G File", "object_type": "G Object Type", "xml_id": "XML ID (G File)",
        "key_name": "XML key_name (G File)", "logical_code": "Parsed CODE (G File)",
        "context_source": "Feeder Context Source (KeyID/Database)", "context_station_id": "Station ID (Database)",
        "context_station_name": "Station Name (Database)", "context_feeder_id": "Feeder ID (Database)",
        "context_feeder_code": "Feeder CODE (Database)", "context_feeder_name": "Feeder Name (Database)",
        "context_bay_id": "Anchor Bay ID (Database)",
        "context_rmu_frame_xml_id": "Nearest RMU Frame XML ID (G File)",
        "context_rmu_id": "RMU ID (Database)", "context_rmu_name": "RMU Name (Database)",
        "context_anchor_type": "In-frame Anchor Type (G File)",
        "context_anchor_xml_id": "In-frame Anchor XML ID (G File)",
        "context_anchor_keyid": "In-frame Anchor KeyID (G File)",
        "current_keyid": "Current KeyID (G File)", "current_device_id": "Current Device ID (Decoded)",
        "current_table_id": "Current Table ID (Decoded)", "current_domain": "Current Domain (Decoded)",
        "table_id": "Target Table ID (Config/DB Definition)", "table_name": "Target DB Table (Database)",
        "configured_domain": "Target Domain (Config/DB Definition)", "db_match_count": "CODE Match Count (Database)",
        "db_device_id": "Target Device ID (Database)", "db_code": "Target CODE (Database)",
        "db_name": "Target NAME (Database)", "db_bv_id": "Target BV_ID (Database)",
        "expected_keyid": "Expected KeyID (Calculated)", "expected_keyid_verified": "Expected KeyID Check (Database)",
        "model_linked": "Model Linked", "model_link_correct": "Current Model Correct",
        "model_link_status": "Current Model Status", "association_action": "Recommended Action",
        "association_ready": "Ready for Association", "writeback_needed": "Write-back Needed",
        "status": "Status", "severity": "Severity", "reason": "Details",
    }.items()
}

RMU_FIELDS = [
    "file_name", "frame_index", "frame_xml_id", "rmu_name",
    "rmu_type", "rmu_type_source", "rmu_type_text", "rmu_type_devref",
    "rmu_type_consistent", "rmu_type_check_status", "rmu_type_check_reason",
    "rmu_is_smart", "rmu_smart_marker_types",
    "rmu_status", "rmu_reason",
    "rmu_db_count", "database_unique", "rmu_id",
    "device_count", "matched_device_count", "device_complete",
    "linked_correct_count", "unlinked_count",
    "linked_wrong_count", "association_eligible",
    "association_block_reasons", "device_block_reasons",
    "inventory_issues", "db_integrity_issues",
]


DEVICE_LABELS = {
    "file_name": "G文件",
    "rmu_name": "环网柜名称（来源：G文件图上文字）",
    "rmu_type": "环网柜类型",
    "rmu_type_source": "类型识别来源",
    "rmu_type_text": "图内文字类型",
    "rmu_type_devref": "devref类型",
    "rmu_type_consistent": "类型交叉校验",
    "rmu_type_check_status": "柜型校验状态",
    "rmu_type_check_reason": "柜型交叉校验说明",
    "rmu_is_smart": "是否智能",
    "rmu_smart_marker_types": "智能标识",
    "rmu_id": "环网柜ID（来源：数据库）",
    "object_type": "G图元类型",
    "xml_id": "图元XML ID（来源：G文件）",
    "logical_code": "逻辑CODE（图上规则）",
    "graphical_name": "图上名称",
    "selected_name_source": "设备名称来源",
    "selected_device_name": "最终设备名称",
    "paired_breaker_name": "配对开关名称",
    "table_id": "表号（来源：数据库定义）",
    "table_name": "数据库表（来源：数据库）",
    "configured_domain": "域号（来源：数据库定义）",
    "match_mode": "匹配规则",
    "db_match_count": "数据库匹配数",
    "db_device_id": "关联数据库设备ID（来源：数据库）",
    "db_code": "关联设备CODE（来源：数据库）",
    "db_name": "关联设备NAME（来源：数据库）",
    "db_combined_id": "所属环网柜ID（来源：数据库）",
    "db_bv_id": "BV_ID（来源：数据库）",
    "expected_keyid": "期望KeyID（程序计算/数据库校验）",
    "expected_keyid_verified": "期望KeyID校验（数据库）",
    "current_keyid": "当前KeyID（来源：G文件）",
    "current_device_id": "当前设备ID（KeyID反解/数据库）",
    "current_table_id": "当前表号（KeyID反解/数据库定义）",
    "current_domain": "当前域号（KeyID反解/数据库定义）",
    "current_table_name": "当前模型数据库表（来源：数据库）",
    "current_db_code": "当前模型设备CODE（来源：数据库）",
    "current_db_name": "当前模型设备NAME（来源：数据库）",
    "current_combined_id": "当前模型所属环网柜ID（来源：数据库）",
    "current_rmu_name": "当前模型所属环网柜名称",
    "current_rmu_match": "当前模型环网柜ID是否正确",
    "current_rmu_name_match": "当前模型环网柜名称是否正确",
    "model_linked": "设备是否已关联模型",
    "model_link_correct": "当前模型是否正确",
    "model_link_status": "当前模型状态",
    "association_action": "处理建议",
    "writeback_needed": "是否需要回写",
    "association_ready": "可进入关联流程",
    "status": "状态",
    "severity": "状态类型",
    "reason": "说明",
}

RMU_LABELS = {
    "file_name": "G文件",
    "frame_index": "环网柜序号",
    "frame_xml_id": "矩形框XML ID（来源：G文件）",
    "rmu_name": "环网柜名称（来源：G文件图上文字）",
    "rmu_type": "环网柜类型",
    "rmu_type_source": "类型识别来源",
    "rmu_type_text": "图内文字类型",
    "rmu_type_devref": "devref类型",
    "rmu_type_consistent": "类型交叉校验",
    "rmu_type_check_status": "柜型校验状态",
    "rmu_type_check_reason": "柜型交叉校验说明",
    "rmu_is_smart": "是否智能",
    "rmu_smart_marker_types": "智能标识",
    "rmu_status": "状态",
    "rmu_reason": "说明",
    "rmu_db_count": "数据库记录数",
    "database_unique": "数据库是否唯一",
    "rmu_id": "环网柜ID（来源：数据库）",
    "device_count": "G图设备数",
    "matched_device_count": "数据库唯一匹配设备数",
    "device_complete": "环网柜设备是否完整",
    "linked_correct_count": "已正确关联设备数",
    "unlinked_count": "未关联设备数",
    "linked_wrong_count": "关联错误设备数",
    "association_eligible": "RMU可关联",
    "association_block_reasons": "RMU级关联阻断原因",
    "device_block_reasons": "设备级阻断原因",
    "inventory_issues": "G图元匹配问题",
    "db_integrity_issues": "数据库匹配问题",
}


FEEDER_LABELS_EN = {
    "file_name": "G File", "drawing_type": "Final Drawing Type",
    "drawing_mode": "Drawing Type Setting", "automatic_drawing_type": "Automatic Topology Result",
    "classification_reason": "Classification Rule", "region_index": "Region Index",
    "region_identity_confidence": "Region Identity Confidence", "feeder_resolution_source": "Feeder Resolution Source",
    "feeder_resolution_evidence": "Feeder Resolution Evidence", "fingerprint_match_ratio": "Single-feeder Fingerprint Match",
    "current_feeder_ids": "Current FEEDER_ID Set", "current_feeder_count": "Current FEEDER_ID Count",
    "majority_feeder_id": "Majority FEEDER_ID", "majority_feeder_count": "Majority FEEDER_ID Rows",
    "anomaly_count": "Abnormal FeedLine Count", "feeder_db_count": "13500 DB Match Count",
    "feeder_id": "Feeder ID", "feeder_name": "Database Feeder Name",
    "station_name": "Substation", "station_bv_id": "Section Creation BV_ID",
    "section_nominal_voltage_kv": "Section Creation Voltage (kV)", "section_prefix": "Section Name Prefix",
    "feedline_count": "FeedLine Count", "database_section_count": "Existing DB Section Count",
    "planned_create_count": "Planned New Sections", "linked_correct_count": "Correctly Linked",
    "unlinked_count": "Unlinked", "error_count": "Errors", "association_ready_count": "Ready for Association",
    "association_eligible": "Feeder Association Eligible", "status": "Status", "severity": "Status Type", "reason": "Details",
}

FEEDLINE_LABELS_EN = {
    "file_name": "G File", "feeder_name": "Feeder Name", "feeder_resolution_source": "Feeder Resolution Source",
    "topology_region": "Topology Region", "current_feeder_name": "Current Feeder Name", "order_index": "FeedLine Index",
    "object_type": "G Object Type", "xml_id": "XML ID", "ls": "ls", "planned_section_type": "SECTION_TYPE",
    "db_create_needed": "Create DB Section", "model_linked": "Model Linked", "model_link_correct": "Current Model Correct",
    "current_keyid": "Current KeyID", "current_device_id": "Current DB Section ID", "current_table_id": "Current Table ID",
    "current_domain": "Current Domain", "current_db_name": "Current DB Section NAME", "current_db_code": "Current DB Section CODE",
    "current_bv_id": "Current Model BV_ID", "current_feeder_id": "Current Model Feeder ID",
    "assigned_device_id": "Target Section ID", "assigned_section_name": "Target Section NAME",
    "assigned_bv_id": "Target BV_ID / voltype", "expected_keyid": "Expected KeyID",
    "expected_keyid_verified": "Expected KeyID Check", "association_ready": "Ready for Association",
    "writeback_needed": "Write-back Needed", "status": "Status", "severity": "Status Type", "reason": "Details",
}

DEVICE_LABELS_EN = {
    "file_name": "G File", "rmu_name": "RMU Name (G Text)", "rmu_type": "RMU Type", "rmu_type_source": "Type Source",
    "rmu_type_text": "Graphical Text Type", "rmu_type_devref": "devref Type", "rmu_type_consistent": "Type Cross-check",
    "rmu_type_check_status": "Type Check Status", "rmu_type_check_reason": "Type Cross-check Details",
    "rmu_is_smart": "Smart Type", "rmu_smart_marker_types": "Smart Markers", "rmu_id": "RMU ID (Database)",
    "object_type": "G Object Type", "xml_id": "XML ID (G File)", "logical_code": "Logical CODE (Graph Rule)",
    "graphical_name": "Graphical Name", "selected_name_source": "Device Name Source", "selected_device_name": "Final Device Name",
    "paired_breaker_name": "Paired Breaker Name", "table_id": "Table ID (Database Definition)", "table_name": "Database Table",
    "configured_domain": "Domain (Database Definition)", "match_mode": "Match Rule", "db_match_count": "DB Match Count",
    "db_device_id": "Matched DB Device ID (Database)", "db_code": "Matched Device CODE (Database)", "db_name": "Matched Device NAME (Database)",
    "db_combined_id": "RMU ID (Database)", "db_bv_id": "BV_ID", "expected_keyid": "Expected KeyID (Calculated/Verified)",
    "expected_keyid_verified": "Expected KeyID Check (Database)", "current_keyid": "Current KeyID (G File)", "current_device_id": "Current Device ID (Decoded/Database)",
    "current_table_id": "Current Table ID (Decoded/DB Definition)", "current_domain": "Current Domain (Decoded/DB Definition)", "current_table_name": "Current Model DB Table (Database)",
    "current_db_code": "Current Model Device CODE (Database)", "current_db_name": "Current Model Device NAME (Database)",
    "current_combined_id": "Current Model RMU ID (Database)", "current_rmu_name": "Current Model RMU Name",
    "current_rmu_match": "Current RMU ID Correct", "current_rmu_name_match": "Current RMU Name Correct",
    "model_linked": "Device Linked", "model_link_correct": "Current Model Correct", "model_link_status": "Current Model Status",
    "association_action": "Recommended Action", "writeback_needed": "Write-back Needed", "association_ready": "Ready for Association",
    "status": "Status", "severity": "Status Type", "reason": "Details",
}

RMU_LABELS_EN = {
    "file_name": "G File", "frame_index": "RMU Index (G File)", "frame_xml_id": "Frame XML ID (G File)", "rmu_name": "RMU Name (G Text)",
    "rmu_type": "RMU Type", "rmu_type_source": "Type Source", "rmu_type_text": "Graphical Text Type",
    "rmu_type_devref": "devref Type", "rmu_type_consistent": "Type Cross-check", "rmu_type_check_status": "Type Check Status",
    "rmu_type_check_reason": "Type Cross-check Details", "rmu_is_smart": "Smart Type", "rmu_smart_marker_types": "Smart Markers",
    "rmu_status": "Status", "rmu_reason": "Details", "rmu_db_count": "DB Record Count", "database_unique": "DB Unique",
    "rmu_id": "RMU ID (Database)", "device_count": "G Device Count", "matched_device_count": "Unique DB Matched Devices",
    "device_complete": "RMU Devices Complete", "linked_correct_count": "Correctly Linked Devices", "unlinked_count": "Unlinked Devices",
    "linked_wrong_count": "Incorrectly Linked Devices", "association_eligible": "RMU Association Eligible",
    "association_block_reasons": "RMU-level Block Reasons", "device_block_reasons": "Device-level Block Reasons",
    "inventory_issues": "G Object Match Issues", "db_integrity_issues": "Database Match Issues",
}


def esc(value):
    return html.escape("" if value is None else str(value))


def status_cls(status):
    return {
        "PASS": "pass",
        "WARN": "warn",
        "UNLINKED": "warn",
        "RELINK": "relink",
        "CREATE_PENDING": "create",
        "RMU_RELINK": "rmu-relink",
        # RMU_LINK remains a hard error used by ambiguous/non-unique RMU cases.
        "RMU_LINK": "fail",
        "BLOCKED": "blocked",
        "FAIL": "fail",
        "INFO": "info",
    }.get(status, "")



# ---------------------------------------------------------------------------
# Report ordering
# ---------------------------------------------------------------------------
# RMU summary:
#   only order by RMU sequence/frame_index within each G file.
#
# Device details:
#   preserve G-file order and RMU processing order;
#   inside each RMU, only group rows by G object type.
#   Rows of the same type keep their original validation order.
DEVICE_TYPE_ORDER = {
    "CBreakerDis": 10,
    "ZhaiWaiJieDiDaoZha": 20,
    "BusDis": 30,
}


def _numeric_sequence(value):
    if value in (None, ""):
        return 10**18
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**18


def sort_rmu_results_by_sequence(rmu_results):
    """
    Stable sort by RMU sequence only.

    Duplicate database records remain adjacent because they are expanded
    after the RMU itself has been ordered.
    """
    return sorted(
        list(rmu_results),
        key=lambda rmu: _numeric_sequence(rmu.get("frame_index", "")),
    )


def sort_devices_within_rmu(device_rows):
    """
    The ONLY device-detail ordering rule:

        CBreakerDis
        ZhaiWaiJieDiDaoZha
        BusDis
        other types

    Python's sort is stable, so rows inside the same G object type retain
    their original validator order.
    """
    return sorted(
        list(device_rows),
        key=lambda row: DEVICE_TYPE_ORDER.get(
            str(row.get("object_type", "") or "").strip(),
            999,
        ),
    )


def flatten_rmu_rows(reports):
    """
    RMU summary rules (v3.0.19)
    --------------------------
    1. One G-file RMU frame -> exactly one summary row.
    2. Rows are always sorted by G-file RMU sequence/frame_index.
    3. Oracle dms_combined_device result count is reported in that one row:
       - 0 rows  -> RMU_NOT_FOUND_IN_DATABASE
       - 1 row   -> normal validation; show the unique RMU ID
       - >1 rows -> RMU_DUPLICATE_IN_DATABASE, but DO NOT expand every DB ID.
                    Leave RMU ID blank and tell the user how many RMUs were found.
    4. Device detail remains G-element based and is handled separately.
    """
    rows = []

    for report in reports:
        file_name = report.get("file_name", "")
        rmu_results = sort_rmu_results_by_sequence(
            report.get("rmu_results", [])
        )

        for rmu in rmu_results:
            records = list(rmu.get("rmu_records") or [])
            db_count = len(records)

            # Only one database record is considered safe/usable.
            unique_record = records[0] if db_count == 1 else {}

            status = rmu.get("rmu_status", "")
            severity = rmu.get("rmu_severity", "")
            reason = rmu.get("rmu_reason", "")
            block_reasons = list(rmu.get("association_block_reasons", []))

            # RMU name resolution failures are hard RMU-level identity errors.
            # Keep them visibly red and make sure the blocker column explains
            # the actual name-parsing problem instead of falling back to a
            # misleading database-not-found message.
            reason_code = str(reason or "").split(":", 1)[0]
            if reason_code in {
                "RMU_NAME_NOT_PARSED",
                "RMU_NAME_NOT_FOUND",
                "RMU_NAME_RESOLUTION_ERROR",
                "RMU_LOOKUP_ERROR",
            }:
                status = "FAIL"
                severity = "ERROR"
                if not block_reasons:
                    frame_ref = rmu.get("frame_xml_id", "") or "-"
                    if reason_code in {"RMU_NAME_NOT_PARSED", "RMU_NAME_NOT_FOUND"}:
                        block_reasons.append(
                            "RMU_NAME_NOT_PARSED: "
                            f"矩形框XML ID={frame_ref} 未解析出环网柜名称；"
                            "环网柜身份未确定，禁止该RMU及柜内设备自动关联。"
                        )
                    else:
                        block_reasons.append(
                            "RMU_NAME_RESOLUTION_ERROR: "
                            f"矩形框XML ID={frame_ref} 环网柜名称解析/核验异常；"
                            f"详情={reason or '-'}；禁止该RMU及柜内设备自动关联。"
                        )

            if db_count > 1:
                status = "FAIL"
                severity = "ERROR"
                reason = (
                    f"RMU_DUPLICATE_IN_DATABASE: 数据库中找到 {db_count} 个同名环网柜，"
                    "请检查数据库模型和单线图中的该环网柜。"
                )
                duplicate_block = (
                    f"数据库中找到 {db_count} 个同名环网柜；环网柜必须唯一，"
                    "禁止自动关联，请检查数据库模型和单线图中的该环网柜。"
                )
                if duplicate_block not in block_reasons:
                    block_reasons.append(duplicate_block)

            elif db_count == 0:
                status = "FAIL"
                severity = "ERROR"
                if not reason or reason == "RMU_NOT_FOUND_IN_DATABASE":
                    reason = (
                        "RMU_NOT_FOUND_IN_DATABASE: 数据库中未找到该环网柜，"
                        "请检查数据库模型和单线图中的环网柜名称。"
                    )

            device_rows = [
                d for d in rmu.get("device_rows", [])
                if d.get("xml_id")
            ]
            matched_device_count = sum(
                1
                for d in device_rows
                if int(d.get("db_match_count") or 0) == 1
                and (
                    db_count != 1
                    or str(d.get("db_combined_id", ""))
                    == str(unique_record.get("id", ""))
                )
            )
            device_complete = (
                db_count == 1
                and bool(device_rows)
                and matched_device_count == len(device_rows)
            )

            row = {
                "file_name": file_name,
                "frame_index": rmu.get("frame_index", ""),
                "frame_xml_id": rmu.get("frame_xml_id", ""),
                "rmu_name": rmu.get("rmu_name", ""),
                "rmu_type": rmu.get("rmu_type", "UNKNOWN"),
                "rmu_type_source": rmu.get("rmu_type_source", ""),
                "rmu_type_text": rmu.get("rmu_type_text", ""),
                "rmu_type_devref": rmu.get("rmu_type_devref", ""),
                "rmu_type_consistent": rmu.get("rmu_type_consistent", ""),
                "rmu_type_check_status": rmu.get(
                    "rmu_type_check_status",
                    "",
                ),
                "rmu_type_check_reason": rmu.get(
                    "rmu_type_check_reason",
                    "",
                ),
                # Report-facing wording requested in v4.1.4.  Keep the
                # validator's internal YES/NO contract unchanged, but render
                # the user-facing column as SMART/NORMAL.
                "rmu_is_smart": (
                    "SMART"
                    if str(rmu.get("rmu_is_smart", "NO")).strip().upper()
                    in {"YES", "TRUE", "1", "SMART", "SMR"}
                    else "NORMAL"
                ),
                "rmu_smart_marker_types": rmu.get(
                    "rmu_smart_marker_types",
                    "",
                ),
                "rmu_status": status,
                "rmu_severity": severity,
                "rmu_reason": reason,
                "rmu_db_count": db_count,
                "database_unique": (
                    "YES" if db_count == 1 else "NO"
                ),
                # Duplicate RMU: intentionally DO NOT list multiple IDs.
                "rmu_id": unique_record.get("id", "") if db_count == 1 else "",
                "device_count": len(device_rows),
                "matched_device_count": matched_device_count,
                "device_complete": "YES" if device_complete else "NO",
                "linked_correct_count": rmu.get(
                    "linked_correct_count", 0
                ),
                "unlinked_count": rmu.get("unlinked_count", 0),
                "linked_wrong_count": rmu.get(
                    "linked_wrong_count", 0
                ),
                "association_eligible": (
                    "YES"
                    if rmu.get("association_eligible") and db_count == 1
                    else "NO"
                ),
                "association_block_reasons": "; ".join(block_reasons),
                "device_block_reasons": "; ".join(
                    rmu.get("device_block_reasons", [])
                ),
                "inventory_issues": "; ".join(
                    rmu.get("inventory_issues", [])
                ),
                "db_integrity_issues": "; ".join(
                    rmu.get("db_integrity_issues", [])
                ),
            }
            rows.append(row)

    # Final sort across all files: file name then numeric RMU sequence.
    return sorted(
        rows,
        key=lambda r: (
            str(r.get("file_name", "")),
            _numeric_sequence(r.get("frame_index", "")),
        ),
    )



def flatten_device_rows(reports):
    rows = []

    # Preserve report / G-file order.
    for report in reports:
        file_name = report.get("file_name", "")

        # Preserve RMU processing order exactly as validator produced it.
        for rmu in report.get("rmu_results", []):
            # The only device-detail sort is object-type grouping
            # inside this single RMU.
            devices = sort_devices_within_rmu(
                rmu.get("device_rows", [])
            )

            for device in devices:
                row = dict(device)
                row.pop("x", None)
                row.pop("y", None)
                row["file_name"] = file_name
                row.setdefault("rmu_name", rmu.get("rmu_name", ""))
                row.setdefault("rmu_id", rmu.get("rmu_id", ""))
                rows.append(row)

    return rows



def flatten_pole_rows(reports):
    rows = []
    for report in reports:
        file_name = report.get("file_name", "")
        for item in report.get("pole_switch_rows", []) or []:
            row = dict(item)
            for coordinate in ("x", "y", "w", "h"):
                row.pop(coordinate, None)
            for key in _POLE_INTERNAL_ONLY_FIELDS:
                row.pop(key, None)
            row["file_name"] = file_name
            rows.append(row)
    return rows


def flatten_transformer_rows(reports):
    rows = []
    for report in reports:
        file_name = report.get("file_name", "")
        for item in report.get("transformer_rows", []) or []:
            row = dict(item)
            for coordinate in ("x", "y", "w", "h"):
                row.pop(coordinate, None)
            # Topology internals are used by validation only and are not part
            # of the user-facing transformer report.
            for key in (
                "topology_component", "topology_member_count", "topology_member_ids",
                "topology_member_tags", "topology_neighbor_count", "topology_neighbor_ids",
            ):
                row.pop(key, None)
            row["file_name"] = file_name
            rows.append(row)
    return rows


def flatten_master_station_rows(reports):
    rows = []
    for report in reports:
        file_name = report.get("file_name", "")
        for item in report.get("master_station_rows", []) or []:
            row = dict(item)
            for coordinate in ("x", "y", "w", "h"):
                row.pop(coordinate, None)
            row["file_name"] = file_name
            rows.append(row)
    return rows


_TRANSFORMER_INTERNAL_ONLY_FIELDS = frozenset(
    {
        "source_cbreaker_count",
        "source_cbreaker_keyid",
        "source_cbreaker_keyids",
        "source_cbreaker_keyids_by_transformer",
        "source_feeder_id",
        "source_feeder_name",
        "topology_component",
        "topology_member_count",
        "topology_member_ids",
        "topology_member_tags",
        "topology_neighbor_count",
        "topology_neighbor_ids",
    }
)


def _transformer_report_for_output(report):
    payload = dict(report)
    payload["transformer_rows"] = [
        {
            key: value
            for key, value in row.items()
            if key not in _TRANSFORMER_INTERNAL_ONLY_FIELDS
        }
        for row in report.get("transformer_rows", []) or []
    ]
    return payload


_POLE_INTERNAL_ONLY_FIELDS = frozenset(
    {
        "topology_component",
        "topology_member_count",
        "topology_member_ids",
        "topology_member_tags",
        "topology_neighbor_count",
        "topology_neighbor_ids",
    }
)


def _pole_report_for_output(report):
    """Remove topology evidence from the persisted public pole report.

    The pole-switch validator still keeps these fields in memory for topology
    analysis and association decisions. They are intentionally not exposed in
    HTML, CSV, or report.json output.
    """
    payload = dict(report)
    payload["pole_switch_rows"] = [
        {
            key: value
            for key, value in row.items()
            if key not in _POLE_INTERNAL_ONLY_FIELDS
        }
        for row in report.get("pole_switch_rows", []) or []
    ]
    return payload


def _is_pole_reports(reports):
    return bool(
        reports
        and str(reports[0].get("report_type", "")).upper() == "POLE_SWITCH"
    )


def _is_transformer_reports(reports):
    return bool(
        reports
        and str(reports[0].get("report_type", "")).upper() == "TRANSFORMER"
    )


def _is_feeder_reports(reports):
    return bool(
        reports
        and str(reports[0].get("report_type", "")).upper() == "FEEDER"
    )


def _is_master_station_reports(reports):
    return bool(
        reports
        and str(reports[0].get("report_type", "")).upper() == "MASTER_STATION"
    )


def flatten_feeder_rows(reports):
    rows = []
    for report in reports:
        feedline_rows = list(report.get("feedline_rows", []))
        section_plan = list(report.get("section_create_plan", []) or [])
        database_section_count = 0
        # Current validator exposes available_count after DB query; when absent,
        # derive a conservative count from rows that resolve to a current DB ID.
        if report.get("available_count") not in (None, ""):
            try:
                database_section_count = int(report.get("available_count") or 0)
            except (TypeError, ValueError):
                database_section_count = 0
        else:
            database_section_count = len({
                str(row.get("current_device_id"))
                for row in feedline_rows
                if row.get("current_device_id") not in (None, "")
            })

        rows.append({
            "file_name": report.get("file_name", ""),
            "drawing_type": report.get("drawing_type", ""),
            "drawing_mode": report.get("drawing_mode", "AUTO"),
            "automatic_drawing_type": report.get("automatic_drawing_type", ""),
            "classification_reason": report.get("classification_reason", ""),
            "region_index": report.get("region_index", ""),
            "region_identity_confidence": report.get("region_identity_confidence", ""),
            "feeder_resolution_source": report.get(
                "feeder_resolution_source",
                report.get("feeder_hint_source", ""),
            ),
            "feeder_resolution_evidence": report.get(
                "feeder_resolution_evidence", ""
            ),
            "fingerprint_match_ratio": report.get("fingerprint_match_ratio", ""),
            "current_feeder_ids": report.get("current_feeder_ids", ""),
            "current_feeder_count": report.get("current_feeder_count", ""),
            "majority_feeder_id": report.get("majority_feeder_id", ""),
            "majority_feeder_count": report.get("majority_feeder_count", ""),
            "anomaly_count": report.get("anomaly_count", ""),
            "feeder_db_count": len(report.get("feeder_records", []) or []),
            "feeder_id": report.get("feeder_id", ""),
            "feeder_name": report.get("feeder_name", ""),
            "station_name": report.get(
                "section_station_name",
                report.get("station_name", ""),
            ),
            "station_bv_id": report.get(
                "section_station_bv_id",
                report.get("station_bv_id", ""),
            ),
            "section_nominal_voltage_kv": report.get(
                "section_nominal_voltage_kv", ""
            ),
            "section_prefix": report.get("section_prefix", ""),
            "feedline_count": len(feedline_rows),
            "database_section_count": database_section_count,
            "planned_create_count": len(section_plan),
            "linked_correct_count": sum(
                1 for row in feedline_rows
                if row.get("model_link_correct") == "YES"
            ),
            "unlinked_count": sum(
                1 for row in feedline_rows
                if row.get("model_linked") == "NO"
            ),
            "error_count": sum(
                1 for row in feedline_rows
                if row.get("status") == "FAIL"
            ),
            "association_ready_count": sum(
                1 for row in feedline_rows
                if (
                    row.get("association_ready") == "YES"
                    and row.get("writeback_needed") == "YES"
                )
            ),
            "association_eligible": (
                "YES" if report.get("association_eligible") else "NO"
            ),
            "status": report.get("status", ""),
            "severity": report.get("severity", ""),
            "reason": report.get("reason", ""),
        })

    return rows


def flatten_feedline_rows(reports):
    rows = []
    for report in reports:
        file_name = report.get("file_name", "")
        feeder_name = report.get("feeder_name", "")
        resolution_source = report.get(
            "feeder_resolution_source",
            report.get("feeder_hint_source", ""),
        )
        for row in report.get("feedline_rows", []):
            item = dict(row)
            item.pop("x", None)
            item.pop("y", None)
            # Obsolete topology/RMU feeder-identification data is intentionally
            # not exported by the feeder report.
            item.pop("topology_component", None)
            item.pop("topology_cross_region", None)
            item["file_name"] = file_name
            item["feeder_name"] = feeder_name
            item["feeder_resolution_source"] = resolution_source
            rows.append(item)

    return sorted(
        rows,
        key=lambda row: (
            str(row.get("file_name", "")),
            int(row.get("order_index") or 10**9),
        ),
    )


_LOCALIZABLE_REPORT_VALUE_FIELDS = {
    "reason", "rmu_reason", "association_block_reasons",
    "device_block_reasons", "inventory_issues", "db_integrity_issues",
    "model_link_status", "association_action", "rmu_type_check_reason",
}


def _write_csv(path, rows, fields, labels, language="zh_CN"):
    path = Path(path)
    language = normalize_language(language)
    english = language == "en_US"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([labels.get(field, field) for field in fields])
        for row in rows:
            values = []
            for field in fields:
                value = row.get(field, "")
                if english and field in _LOCALIZABLE_REPORT_VALUE_FIELDS:
                    value = translate_runtime_text(value, language)
                values.append(value)
            writer.writerow(values)


def write_report(report, output_dir, domain_rules):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = [report]

    if _is_pole_reports(reports):
        _write_csv(
            output_dir / "pole_switch_details.csv",
            flatten_pole_rows(reports),
            POLE_FIELDS,
            POLE_LABELS,
        )
        (output_dir / "report.json").write_text(
            json.dumps(
                _pole_report_for_output(report),
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        html_path = output_dir / "index.html"
        export_html_bundle(reports, html_path, domain_rules)
        return html_path

    if _is_transformer_reports(reports):
        _write_csv(
            output_dir / "transformer_details.csv",
            flatten_transformer_rows(reports),
            TRANSFORMER_FIELDS,
            TRANSFORMER_LABELS,
        )
        (output_dir / "report.json").write_text(
            json.dumps(_transformer_report_for_output(report), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        html_path = output_dir / "index.html"
        export_html_bundle(reports, html_path, domain_rules)
        return html_path

    if _is_master_station_reports(reports):
        _write_csv(
            output_dir / "master_station_details.csv",
            flatten_master_station_rows(reports),
            MASTER_STATION_FIELDS,
            MASTER_STATION_LABELS,
        )
        (output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        html_path = output_dir / "index.html"
        export_html_bundle(reports, html_path, domain_rules)
        return html_path

    _write_csv(
        output_dir/"rmu_summary.csv",
        flatten_rmu_rows(reports),
        RMU_FIELDS,
        RMU_LABELS,
    )
    device_fields = ["file_name"] + DEVICE_FIELDS
    _write_csv(
        output_dir/"device_validation.csv",
        flatten_device_rows(reports),
        device_fields,
        DEVICE_LABELS,
    )

    (output_dir/"report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    html_path = output_dir/"index.html"
    export_html_bundle(reports, html_path, domain_rules)
    return html_path



def export_csv_bundle(reports, export_path, language="zh_CN"):
    export_path = Path(export_path)
    base = (
        export_path.with_suffix("")
        if export_path.suffix.lower() == ".csv"
        else export_path
    )

    language = normalize_language(language)
    english = language == "en_US"

    if _is_pole_reports(reports):
        pole_path = base.with_name(
            base.name
            + ("_pole_switch_details.csv" if english else "_柱上开关明细.csv")
        )
        _write_csv(
            pole_path,
            flatten_pole_rows(reports),
            POLE_FIELDS,
            POLE_LABELS_EN if english else POLE_LABELS,
            language=language,
        )
        return [pole_path]

    if _is_transformer_reports(reports):
        transformer_path = base.with_name(
            base.name + ("_transformer_details.csv" if english else "_柱上变压器明细.csv")
        )
        _write_csv(
            transformer_path,
            flatten_transformer_rows(reports),
            TRANSFORMER_FIELDS,
            TRANSFORMER_LABELS_EN if english else TRANSFORMER_LABELS,
            language=language,
        )
        return [transformer_path]

    if _is_master_station_reports(reports):
        master_path = base.with_name(
            base.name + ("_master_station_details.csv" if english else "_配网主站设备明细.csv")
        )
        _write_csv(
            master_path,
            flatten_master_station_rows(reports),
            MASTER_STATION_FIELDS,
            MASTER_STATION_LABELS_EN if english else MASTER_STATION_LABELS,
            language=language,
        )
        return [master_path]

    if _is_feeder_reports(reports):
        feeder_path = base.with_name(
            base.name + ("_feeder_summary.csv" if english else "_馈线汇总.csv")
        )
        section_path = base.with_name(
            base.name + ("_feeder_section_details.csv" if english else "_馈线段明细.csv")
        )
        _write_csv(
            feeder_path,
            flatten_feeder_rows(reports),
            FEEDER_FIELDS,
            FEEDER_LABELS_EN if english else FEEDER_LABELS,
            language=language,
        )
        _write_csv(
            section_path,
            flatten_feedline_rows(reports),
            FEEDLINE_FIELDS,
            FEEDLINE_LABELS_EN if english else FEEDLINE_LABELS,
            language=language,
        )
        return [feeder_path, section_path]

    rmu_path = base.with_name(base.name + ("_rmu_summary.csv" if english else "_环网柜汇总.csv"))
    dev_path = base.with_name(base.name + ("_device_details.csv" if english else "_设备明细.csv"))

    _write_csv(
        rmu_path,
        flatten_rmu_rows(reports),
        RMU_FIELDS,
        RMU_LABELS_EN if english else RMU_LABELS,
        language=language,
    )
    _write_csv(
        dev_path,
        flatten_device_rows(reports),
        ["file_name"] + DEVICE_FIELDS,
        DEVICE_LABELS_EN if english else DEVICE_LABELS,
        language=language,
    )

    return [rmu_path, dev_path]

def _table_html(
    rows,
    fields,
    labels,
    status_field=None,
    selectable=False,
    table_id=None,
    filter_placeholder=None,
    language="zh_CN",
):
    english = normalize_language(language) == "en_US"
    body = []
    present_colors = set()
    class_to_color = {
        "pass": "green",
        "warn": "yellow",
        "relink": "orange",
        "create": "orange",
        "rmu-relink": "purple",
        "blocked": "blue",
        "info": "blue",
        "fail": "red",
    }
    for row in rows:
        if status_field:
            # Some feeder rows keep status=WARN for operational readiness while
            # severity carries the exact action type. CREATE_PENDING needs its
            # own report color so users can immediately distinguish "link an
            # existing section" from "create a new 13503 section, then link".
            semantic_status = str(row.get("severity", "") or "")
            cls = (
                status_cls(semantic_status)
                if semantic_status == "CREATE_PENDING"
                else status_cls(str(row.get(status_field, "")))
            )
        else:
            cls = ""
        row_color = class_to_color.get(cls, "")
        if row_color:
            present_colors.add(row_color)
        select_cell = (
            "<td class='select-col'>"
            "<input type='checkbox' class='row-check' "
            + ("title='Keep the full row highlighted for horizontal review' " if english else "title='选中后整行保持高亮，便于横向查看' ")
            + "onchange='toggleSelectedRow(this)'>"
            "</td>"
            if selectable else ""
        )
        body.append(
            f"<tr class='{cls}'>"
            + select_cell
            + "".join(
                f"<td>{esc(translate_runtime_text(row.get(field, ''), language) if english and field in {"reason", "rmu_reason", "association_block_reasons", "device_block_reasons", "inventory_issues", "db_integrity_issues", "model_link_status", "association_action"} else row.get(field, ''))}</td>"
                for field in fields
            )
            + "</tr>"
        )

    select_header = (
        ("<th class='select-col'>Select</th>" if english else "<th class='select-col'>选择</th>")
        if selectable else ""
    )

    table_id_attr = f" id='{esc(table_id)}'" if table_id else ""
    filter_html = ""
    if table_id:
        placeholder = filter_placeholder or ("Enter any text to filter" if english else "输入任意内容进行模糊筛选")
        color_labels = {
            "green": "Green" if english else "绿色",
            "yellow": "Yellow" if english else "黄色",
            "orange": "Orange" if english else "橙色",
            "purple": "Purple" if english else "紫色",
            "blue": "Blue" if english else "蓝色",
            "red": "Red" if english else "红色",
        }
        color_order = ["green", "yellow", "orange", "purple", "blue", "red"]
        color_options = [
            f"<option value='{color}'>{esc(color_labels[color])}</option>"
            for color in color_order
            if color in present_colors
        ]
        color_select = (
            f"<select class='table-color-filter' id='{esc(table_id)}-color-filter' "
            f"onchange=\"filterReportTable('{esc(table_id)}')\">"
            + ("<option value='all'>All Colors</option>" if english else "<option value='all'>全部颜色</option>")
            + "".join(color_options)
            + "</select>"
        )
        filter_html = (
            "<div class='table-filter'>"
            + ("<label>Filter:</label>" if english else "<label>筛选：</label>")
            + f"<input type='search' class='table-filter-input' id='{esc(table_id)}-text-filter' "
            + f"placeholder='{esc(placeholder)}' "
            + f"oninput=\"filterReportTable('{esc(table_id)}')\">"
            + ("<label>Color:</label>" if english else "<label>颜色：</label>")
            + color_select
            + f"<span class='filter-count' id='{esc(table_id)}-count'>"
            + ((f"{len(rows)} rows") if english else (f"共 {len(rows)} 行"))
            + "</span>"
            + "</div>"
        )

    return (
        filter_html
        + f"<div class='scroll'><table{table_id_attr}><thead><tr>"
        + select_header
        + "".join(
            f"<th>{esc(labels.get(field,field))}</th>"
            for field in fields
        )
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


# Compatibility marker for historical report-contract tests: <h2>环网柜汇总</h2>
def _export_rmu_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    rmu_rows = flatten_rmu_rows(reports)
    device_rows = flatten_device_rows(reports)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    language = normalize_language(language)
    english = language == "en_US"

    is_operation_report = any(
        str(rmu.get("rmu_reason", "")).startswith(
            "ASSOCIATION_EXECUT"
        )
        for report in reports
        for rmu in report.get("rmu_results", [])
    )
    report_title = (
        "RMU 模型关联执行报告"
        if is_operation_report
        else "配网模型管理报告"
    )
    rmu_intro = (
        "本报告只展示本次用户勾选并执行的环网柜。"
        "未选中的环网柜不会进入本次执行报告。"
        if is_operation_report
        else (
            "环网柜汇总严格按照 G 文件环网柜序号排列，"
            "每个环网柜只展示一行；柜型、智能标识、数据库唯一性、"
            "设备完整性及关联状态统一汇总在本表中。"
        )
    )
    device_intro = (
        "本表只展示本次用户勾选执行的设备。"
        "PASS 表示本次成功写回；FAIL 表示执行时数据库事实发生变化，"
        "该设备已跳过且未写回。"
        if is_operation_report
        else (
            "设备明细仅展示 G 文件实际存在的设备图元。"
        )
    )

    if english:
        report_title = "RMU Model Association Execution Report" if is_operation_report else "Distribution Model Management Report"
        rmu_intro = (
            "This report contains only RMUs selected and executed in this operation. Unselected RMUs are excluded."
            if is_operation_report else
            "The RMU summary follows the RMU sequence in each G file. Each RMU is shown once with type, smart markers, database uniqueness, device completeness, and association status."
        )
        device_intro = (
            "This table contains only devices selected for this execution. PASS means write-back succeeded; FAIL means database facts changed during execution and the device was skipped."
            if is_operation_report else
            "Device details include only device objects that actually exist in the G file."
        )

    source_note = (
        "字段来源说明：矩形框 XML ID、图元 XML ID、当前 G 文件 KeyID 来自 G 文件；"
        "环网柜 ID、设备 ID、CODE、NAME、BV_ID、所属环网柜 ID 来自数据库；"
        "表号和域号来自数据库定义；期望 KeyID 是程序按设备 ID + 域号计算后，再通过数据库函数校验的结果。"
    )
    if english:
        source_note = (
            "Field sources: Frame XML ID, G-object XML ID, and current G-file KeyID come from the G file; "
            "RMU ID, device ID, CODE, NAME, BV_ID, and owning RMU ID come from the database; "
            "table/domain values come from database definitions; Expected KeyID is calculated from device ID + domain and then verified by the database function."
        )

    domain_rows = "".join(
        f"<tr><td>{esc(tag)}</td><td>{esc(rule['table_id'])}</td><td>{esc(rule['domain'])}</td></tr>"
        for tag, rule in domain_rules.items()
    )

    rmu_table = _table_html(
        rmu_rows,
        RMU_FIELDS,
        RMU_LABELS_EN if english else RMU_LABELS,
        "rmu_status",
        selectable=True,
        table_id="rmu-summary-table",
        filter_placeholder=("Enter an RMU name or any text" if english else "输入环网柜名称或任意字符，模糊匹配"),
        language=language,
    )
    device_fields = ["file_name"] + DEVICE_FIELDS
    device_table = _table_html(
        device_rows,
        device_fields,
        DEVICE_LABELS_EN if english else DEVICE_LABELS,
        "status",
        selectable=True,
        table_id="rmu-device-table",
        filter_placeholder=("Enter an RMU name or any text" if english else "输入环网柜名称或任意字符，模糊匹配"),
        language=language,
    )

    text = f"""<!doctype html>
<html lang="{'en' if english else 'zh-CN'}">
<head>
<meta charset="utf-8">
<title>{esc(report_title)}</title>
<style>
:root {{
  --green:#008C6A;
  --green-dark:#006B52;
  --green-light:#E9F7F1;
  --border:#D3E3DC;
  --text:#17372E;
}}
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:var(--text)}}
header{{background:var(--green-dark);color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}}
.card{{background:white;border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th{{background:var(--green-dark);color:white;position:sticky;top:0}}
th,td{{border:1px solid var(--border);padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:650px}}
.pass{{background:#EAF8F2}}
.warn{{background:#FFF8DE}}
.relink{{background:#FFE8CC}}
.rmu-relink{{background:#F0E7FF}}
.blocked{{background:#EAF3FF}}
.fail{{background:#FFF0F0}}
tr.row-selected{{outline:3px solid #1976D2;outline-offset:-3px;font-weight:600}}
.select-col{{position:sticky;left:0;z-index:4;text-align:center!important;min-width:52px;max-width:52px;background:#F8FBFA!important}}
thead .select-col{{z-index:7;background:var(--green-dark)!important;color:white}}
.row-check{{width:17px;height:17px;cursor:pointer;accent-color:#1976D2}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px 0;flex-wrap:wrap}}
.table-filter label{{font-weight:600;color:var(--green-dark)}}
.table-filter-input{{width:min(520px,70vw);padding:8px 11px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none;background:#fff;color:var(--text)}}
.table-filter-input:focus{{border-color:var(--green);box-shadow:0 0 0 2px rgba(0,140,106,.12)}}
.table-color-filter{{padding:8px 30px 8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:#fff;color:var(--text);outline:none;cursor:pointer}}
.table-color-filter:focus{{border-color:var(--green);box-shadow:0 0 0 2px rgba(0,140,106,.12)}}
.filter-count{{font-size:12px;color:#607D74}}
.status-list{{display:flex;flex-direction:column;gap:8px;max-width:1100px}}
.status-item{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;padding:9px 12px;border-radius:6px;border:1px solid var(--border)}}
.status-item strong{{white-space:nowrap}}
.status-item span{{line-height:1.55}}
.meta{{color:#D7EEE5}}
.source-note{{background:#F0F8F5;border:1px solid var(--border);border-radius:6px;padding:10px 12px;line-height:1.6;margin-top:10px}}
</style>
</head>
<body>
<header>
  <h1>{esc(report_title)}</h1>
  <div class="meta">{("Software: " + esc(APP_NAME_EN) + "  Version: " + esc(APP_VERSION) + "  Exported: " + esc(now)) if english else ("软件：" + esc(APP_NAME) + "　版本：" + esc(APP_VERSION) + "　导出时间：" + esc(now))}</div>
</header>
<main>
  <div class="card">
    <h2>{("Device Model Association Rules" if english else "设备模型关联规则")}</h2>
    <div class="source-note">{esc(source_note)}</div>
    <table>
      <thead><tr><th>{("G Object Type" if english else "G 图元类型")}</th><th>{("Table ID (Database Definition)" if english else "表号（数据库定义）")}</th><th>{("Domain (Database Definition)" if english else "域号（数据库定义）")}</th></tr></thead>
      <tbody>{domain_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>{("Status Legend" if english else "状态颜色说明")}</h2>
    <div class="status-list">
      <div class="status-item pass">
        <strong>{("Green PASS" if english else "绿色 PASS")}</strong>
        <span>{("The current model is linked to the correct current database device; no action is required." if english else "当前模型已关联到数据库当前正确设备，无需处理。")}</span>
      </div>
      <div class="status-item warn">
        <strong>{("Yellow UNLINKED" if english else "黄色 UNLINKED")}</strong>
        <span>{("The G object is not linked yet; the database RMU and target device are unique and satisfy CODE, graphical-name, and RMU ownership rules." if english else "当前 G 图元尚未关联；数据库 RMU 和目标设备均唯一且符合 CODE/图上逻辑名称与环网柜归属规则，可以关联。")}</span>
      </div>
      <div class="status-item relink" style="background:#FFE8CC">
        <strong>{("Orange RELINK" if english else "橙色 RELINK")}</strong>
        <span>{("The old KeyID, device ID, table ID, or Domain is stale/incorrect, or the old device was recreated. The current target is still unique and can be relinked safely." if english else "旧 KeyID、设备 ID、表号或 Domain 已过期/错误，或者旧设备被删除后重新创建；数据库当前目标设备仍唯一且符合规则，可以重新关联并覆盖旧模型。")}</span>
      </div>
      <div class="status-item rmu-relink" style="background:#F0E7FF">
        <strong>{("Purple RMU_RELINK" if english else "紫色 RMU_RELINK")}</strong>
        <span>{("The current KeyID points to another RMU, but the current RMU and device are uniquely determined by CODE / graphical naming; relinking to this RMU is allowed." if english else "当前 KeyID 指向了其他环网柜，但当前 RMU 唯一，并且本 RMU 内 CODE/图上逻辑名称已唯一确定正确设备；允许重新关联到当前环网柜。")}</span>
      </div>
      <div class="status-item blocked">
        <strong>{("Blue BLOCKED" if english else "蓝色 BLOCKED")}</strong>
        <span>{("A blocked scenario requiring manual confirmation." if english else "需要人工确认的整体阻断场景。")}</span>
      </div>
      <div class="status-item fail">
        <strong>{("Red FAIL" if english else "红色 FAIL")}</strong>
        <span>{("The current database facts cannot safely determine a target, such as zero/multiple RMUs, zero/multiple CODE matches, CODE/name mismatch, wrong RMU ownership, or invalid Expected KeyID / BV_ID." if english else "数据库当前事实无法安全确定目标，例如 RMU 0/多条、当前 RMU 内 CODE 0/多条、CODE 与图上逻辑名称不一致、目标设备不属于当前 RMU、Expected KeyID 或 BV_ID 无效。")}</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>{("RMU Summary" if english else "环网柜汇总")}</h2>
    <p>{esc(rmu_intro)}</p>
    {rmu_table}
  </div>

  <div class="card">
    <h2>{("Device Details" if english else "设备明细")}</h2><p>{esc(device_intro)}</p>
    {device_table}
  </div>
</main>
<script>
function toggleSelectedRow(cb) {{
  const row = cb.closest('tr');
  if (!row) return;
  if (cb.checked) {{
    row.classList.add('row-selected');
  }} else {{
    row.classList.remove('row-selected');
  }}
}}

function getReportRowColor(row) {{
  if (row.classList.contains('pass')) return 'green';
  if (row.classList.contains('warn')) return 'yellow';
  if (row.classList.contains('relink') || row.classList.contains('create')) return 'orange';
  if (row.classList.contains('rmu-relink')) return 'purple';
  if (row.classList.contains('blocked') || row.classList.contains('info')) return 'blue';
  if (row.classList.contains('fail')) return 'red';
  return '';
}}
function filterReportTable(tableId) {{
  const table = document.getElementById(tableId);
  if (!table || !table.tBodies || !table.tBodies.length) return;
  const textInput = document.getElementById(tableId + '-text-filter');
  const colorSelect = document.getElementById(tableId + '-color-filter');
  const query = String(textInput ? textInput.value : '').trim().toLocaleUpperCase();
  const color = String(colorSelect ? colorSelect.value : 'all');
  const rows = Array.from(table.tBodies[0].rows);
  let visible = 0;
  for (const row of rows) {{
    const haystack = String(row.textContent || '').toLocaleUpperCase();
    const textMatched = !query || haystack.includes(query);
    const rowColor = getReportRowColor(row);
    const colorMatched = color === 'all' || rowColor === color;
    const matched = textMatched && colorMatched;
    row.style.display = matched ? '' : 'none';
    if (matched) visible += 1;
  }}
  const counter = document.getElementById(tableId + '-count');
  if (counter) {{
    const filtered = Boolean(query) || color !== 'all';
    counter.textContent = filtered
      ? ("{language}" === "en_US" ? `Matched ${{visible}} / ${{rows.length}} rows` : `匹配 ${{visible}} / ${{rows.length}} 行`)
      : ("{language}" === "en_US" ? `${{rows.length}} rows` : `共 ${{rows.length}} 行`);
  }}
}}
</script>
</body>
</html>"""

    export_path.write_text(text, encoding="utf-8")
    return export_path

def _export_feeder_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    feeder_rows = flatten_feeder_rows(reports)
    feedline_rows = flatten_feedline_rows(reports)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    language = normalize_language(language)
    english = language == "en_US"

    domain_rows = "".join(
        f"<tr><td>{esc(tag)}</td>"
        f"<td>{esc(rule['table_id'])}</td>"
        f"<td>{esc(rule['domain'])}</td></tr>"
        for tag, rule in domain_rules.items()
    )

    feeder_table = _table_html(
        feeder_rows,
        FEEDER_FIELDS,
        FEEDER_LABELS_EN if english else FEEDER_LABELS,
        "status",
        selectable=True,
        table_id="feeder-summary-table",
        filter_placeholder=("Enter a feeder name or any text" if english else "输入馈线名称或任意字符，模糊匹配"),
        language=language,
    )
    feedline_table = _table_html(
        feedline_rows,
        FEEDLINE_FIELDS,
        FEEDLINE_LABELS_EN if english else FEEDLINE_LABELS,
        "status",
        selectable=True,
        table_id="feedline-detail-table",
        filter_placeholder=("Enter a feeder section name or any text" if english else "输入馈线段名称或任意字符，模糊匹配"),
        language=language,
    )

    feeder_rule_intro = (
        "Feeder resolution uses exactly the operator-selected independent source: G-root facID, file name, or manual input. An existing facID is current-state evidence only and does not override the selected source. File-name mode supports both single files and batch folders; each file independently resolves its substation and feeder token (for example ABH + 03 -> AH303, while AH303 is used directly) and must produce one unique 13500 / dms_feeder_device match. Replacing a different existing facID/cross-feeder section association requires the explicit override option. Substation 405 determines feeder ownership; section BV_ID is selected from the station voltage levels. The only database write allowed is INSERT into 13503 / dms_section_device, using model Domain 1."
        if english else
        "馈线识别规则：FACID、文件名、人工输入三种来源相互独立，本次只使用用户明确选择的来源。已有 G.facID 仅作为当前关联状态，不再强制覆盖用户选择。文件名模式同时支持单文件和批量目录，每个文件独立解析变电站与馈线号，例如 ABH + 03 可在站内唯一解析为 AH303，文件名已带 AH303 时则直接使用完整馈线号；最终必须唯一匹配 13500 / dms_feeder_device。若目标与当前 facID/馈线段归属不同，只有显式启用覆盖选项后才允许重关联。405 / substation 用于确定馈线所属变电站；创建馈线段的 BV_ID 从该站 402 / voltagelevel 中选择。唯一允许写入的数据库表是 13503 / dms_section_device，模型域号为 1。"
    )
    feeder_status_desc = {
        "pass": "The FeedLine is already linked to a database section under this feeder with the correct table ID and Domain." if english else "当前 FeedLine 已经关联到本馈线下的数据库馈线段，表号/域号均正确。",
        "warn": "The FeedLine is unlinked but has been assigned to an existing available section under this feeder and can be associated directly." if english else "当前 FeedLine 尚未关联，但已经分配到本馈线下已有的可用数据库馈线段，可以在工作区勾选后直接执行模型关联。",
        "create": "There are not enough available 13503 sections under this feeder. A new dms_section_device record must be created before generating the KeyID and associating this FeedLine." if english else "当前馈线数据库中没有足够的可用 13503 馈线段；该 FeedLine 需要先单独创建新的 dms_section_device 记录，再生成正确 KeyID 并完成关联。",
        "fail": "The feeder cannot be uniquely resolved, an existing feeder conflict has not been explicitly authorized for override, or another hard error prevents safe association." if english else "馈线无法唯一解析、现有馈线冲突未明确启用人工覆盖、无法安全确定目标或其它硬错误。",
    }
    feeder_summary_intro = (
        "A feeder is resolved from exactly one source: root facID, file name, or manual input. The selected source must uniquely match 13500 / dms_feeder_device. If uniqueness cannot be established, the result is FAIL and no section is created or associated."
        if english else
        "馈线通过三种互相独立的来源之一确定：G 根节点 facID、文件名、人工输入。默认使用 facID；所选来源必须单独唯一匹配到 13500 / dms_feeder_device，不与另外两种来源交叉分析。无法唯一确认时直接 FAIL，不创建馈线段，也不执行 FeedLine 关联。馈线报告不再包含任何 RMU / 环网柜拓扑判定字段。"
    )
    feedline_detail_intro = (
        "After the feeder is uniquely confirmed, the program queries 13503 / dms_section_device for that FEEDER_ID. Existing correct links are preserved without geometric SEC reordering. Unlinked or stale FeedLines use available unoccupied sections first; only the real shortage is created. Association then completes LINK / RELINK using refreshed database records."
        if english else
        "唯一馈线确认后，程序查询该 FEEDER_ID 下的 13503 / dms_section_device。已正确关联到本馈线且表号/域号正确的 FeedLine 保持原关联，不按图形几何顺序强制重排 SEC；未关联或旧关联失效的 FeedLine 才使用当前馈线未占用的现有馈线段，真实数量不足时仅按短缺数量生成 SECnnn 创建计划。执行模型关联时先补齐缺失记录、重新查询数据库，再完成 LINK / RELINK。表格左侧复选框仅用于人工标记。"
    )

    text = f"""<!doctype html>
<html lang="{'en' if english else 'zh-CN'}">
<head>
<meta charset="utf-8">
<title>{"Feeder Model Management Report" if english else "馈线模型管理报告"}</title>
<style>
:root {{
  --green:#008C6A;
  --green-dark:#006B52;
  --border:#D3E3DC;
  --text:#17372E;
}}
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:var(--text)}}
header{{background:var(--green-dark);color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}}
.card{{background:white;border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th{{background:var(--green-dark);color:white;position:sticky;top:0}}
th,td{{border:1px solid var(--border);padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:650px}}
.pass{{background:#EAF8F2}}
.warn{{background:#FFF8DE}}
.create{{background:#FFE8CC}}
.fail{{background:#FFF0F0}}
.info{{background:#EAF3FF}}
.row-selected td{{background:#DCEEFF !important;box-shadow:inset 0 1px #8AB8F5,inset 0 -1px #8AB8F5}}
.select-col{{width:42px;min-width:42px;text-align:center;position:sticky;left:0;z-index:3}}
th.select-col{{z-index:5;background:var(--green-dark)}}
td.select-col{{background:inherit}}
.row-check{{width:16px;height:16px;cursor:pointer}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px 0;flex-wrap:wrap}}
.table-filter label{{font-weight:600;color:var(--green-dark)}}
.table-filter-input{{width:min(520px,70vw);padding:8px 11px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none;background:#fff;color:var(--text)}}
.table-filter-input:focus{{border-color:var(--green);box-shadow:0 0 0 2px rgba(0,140,106,.12)}}
.table-color-filter{{padding:8px 30px 8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:#fff;color:var(--text);outline:none;cursor:pointer}}
.table-color-filter:focus{{border-color:var(--green);box-shadow:0 0 0 2px rgba(0,140,106,.12)}}
.filter-count{{font-size:12px;color:#607D74}}
.status-list{{display:flex;flex-direction:column;gap:8px;max-width:1100px}}
.status-item{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;padding:9px 12px;border-radius:6px;border:1px solid var(--border)}}
.meta{{color:#D7EEE5}}
</style>
</head>
<body>
<header>
  <h1>{"Feeder Model Management Report" if english else "馈线模型管理报告"}</h1>
  <div class="meta">{("Software: " + esc(APP_NAME_EN) + "  Version: " + esc(APP_VERSION) + "  Exported: " + esc(now)) if english else ("软件：" + esc(APP_NAME) + "　版本：" + esc(APP_VERSION) + "　导出时间：" + esc(now))}</div>
</header>
<main>
  <div class="card">
    <h2>{("Feeder Section Model Rules" if english else "馈线段模型规则")}</h2>
    <table>
      <thead><tr><th>{"G Object Type" if english else "G 图元类型"}</th><th>{"Table ID (Database Definition)" if english else "表号（数据库定义）"}</th><th>{"Domain (Database Definition)" if english else "域号（数据库定义）"}</th></tr></thead>
      <tbody>{domain_rows}</tbody>
    </table>
    <p>{esc(feeder_rule_intro)}</p>
  </div>

  <div class="card">
    <h2>{("Status Legend" if english else "状态颜色说明")}</h2>
    <div class="status-list">
      <div class="status-item pass" style="background:#EAF8F2">
        <strong>{("Green PASS" if english else "绿色 PASS")}</strong>
        <span>{esc(feeder_status_desc["pass"])}</span>
      </div>
      <div class="status-item warn" style="background:#FFF8DE">
        <strong>{("Yellow WARN" if english else "黄色 WARN")}</strong>
        <span>{esc(feeder_status_desc["warn"])}</span>
      </div>
      <div class="status-item create" style="background:#FFE8CC">
        <strong>{("Orange CREATE" if english else "橙色 CREATE")}</strong>
        <span>{esc(feeder_status_desc["create"])}</span>
      </div>
      <div class="status-item fail" style="background:#FFF0F0">
        <strong>{("Red FAIL" if english else "红色 FAIL")}</strong>
        <span>{esc(feeder_status_desc["fail"])}</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>{("Feeder Summary" if english else "馈线汇总")}</h2>
    <p>{esc(feeder_summary_intro)}</p>
    {feeder_table}
  </div>

  <div class="card">
    <h2>{("Feeder Section Details" if english else "馈线段明细")}</h2>
    <p>{esc(feedline_detail_intro)}</p>
    {feedline_table}
  </div>
</main>
<script>
function toggleSelectedRow(cb) {{
  const row = cb.closest('tr');
  if (!row) return;
  row.classList.toggle('row-selected', cb.checked);
}}
function getReportRowColor(row) {{
  if (row.classList.contains('pass')) return 'green';
  if (row.classList.contains('warn')) return 'yellow';
  if (row.classList.contains('relink') || row.classList.contains('create')) return 'orange';
  if (row.classList.contains('rmu-relink')) return 'purple';
  if (row.classList.contains('blocked') || row.classList.contains('info')) return 'blue';
  if (row.classList.contains('fail')) return 'red';
  return '';
}}
function filterReportTable(tableId) {{
  const table = document.getElementById(tableId);
  if (!table || !table.tBodies || !table.tBodies.length) return;
  const textInput = document.getElementById(tableId + '-text-filter');
  const colorSelect = document.getElementById(tableId + '-color-filter');
  const query = String(textInput ? textInput.value : '').trim().toLocaleUpperCase();
  const color = String(colorSelect ? colorSelect.value : 'all');
  const rows = Array.from(table.tBodies[0].rows);
  let visible = 0;
  for (const row of rows) {{
    const haystack = String(row.textContent || '').toLocaleUpperCase();
    const textMatched = !query || haystack.includes(query);
    const rowColor = getReportRowColor(row);
    const colorMatched = color === 'all' || rowColor === color;
    const matched = textMatched && colorMatched;
    row.style.display = matched ? '' : 'none';
    if (matched) visible += 1;
  }}
  const counter = document.getElementById(tableId + '-count');
  if (counter) {{
    const filtered = Boolean(query) || color !== 'all';
    counter.textContent = filtered
      ? ("{language}" === "en_US" ? `Matched ${{visible}} / ${{rows.length}} rows` : `匹配 ${{visible}} / ${{rows.length}} 行`)
      : ("{language}" === "en_US" ? `${{rows.length}} rows` : `共 ${{rows.length}} 行`);
  }}
}}
</script>
</body>
</html>"""

    export_path.write_text(text, encoding="utf-8")
    return export_path


def _export_pole_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    language = normalize_language(language)
    english = language == "en_US"
    rows = flatten_pole_rows(reports)
    labels = POLE_LABELS_EN if english else POLE_LABELS
    title = "Pole Switch Model Report" if english else "柱上开关模型报告"
    intro = (
        "Only CBreakerDis objects whose element file is marked LBS, SEC, or AR in Element Management are included. "
        "Each device independently resolves its name from the nearest eligible Text; RMU and connection topology are not analyzed."
        if english
        else
        "本报告只展示 CBreakerDis 且对应图元文件在图元管理中标记为 LBS/SEC/AR 的柱上开关，"
        "每个设备独立取最近合规 Text；Text.ts 中的换行名称会合并为空格后保留，"
        "kV、A、V 等单位文字不作为名称，"
        "并输出数据库链路和 KeyID 校验结果。"
    )
    domain_rows = "<tr><td>CBreakerDis</td><td>13502</td><td>40</td></tr>"
    table = _table_html(
        rows,
        POLE_FIELDS,
        labels,
        "status",
        selectable=True,
        table_id="pole-switch-table",
        filter_placeholder=(
            "Enter a pole-switch name, model, devref, or XML ID"
            if english
            else "输入柱上开关名称、型号、devref 或 XML ID"
        ),
        language=language,
    )
    text = f"""<!doctype html>
<html lang="{'en' if english else 'zh-CN'}">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<style>
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:#17372E}}
header{{background:#006B52;color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}} .card{{background:white;border:1px solid #D3E3DC;border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th{{background:#006B52;color:white;position:sticky;top:0}}
th,td{{border:1px solid #D3E3DC;padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:700px}} .pass{{background:#EAF8F2}} .warn{{background:#FFF8DE}}
.relink{{background:#FFE8CC}} .rmu-relink{{background:#F0E7FF}} .blocked{{background:#EAF3FF}}
.fail{{background:#FFF0F0}} .info{{background:#EAF3FF}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px;flex-wrap:wrap}}
.table-filter-input{{width:min(560px,70vw);padding:8px 11px;border:1px solid #D3E3DC;border-radius:6px}}
.status-list{{display:flex;flex-direction:column;gap:8px;max-width:1100px}}
.status-item{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;padding:9px 12px;border-radius:6px;border:1px solid #D3E3DC}}
.status-item strong{{white-space:nowrap}} .status-item span{{line-height:1.55}}
</style>
</head>
<body>
<header><h1>{esc(title)}</h1><div>{esc(APP_NAME if not english else APP_NAME_EN)}　v{esc(APP_VERSION)}</div></header>
<main>
<div class="card"><h2>{'Association Rules' if english else '关联规则'}</h2>
<p>{esc(intro)}</p><p><strong>{'Field sources:' if english else '字段来源：'}</strong>{'G file name, object type, XML ID, text name, and current KeyID come from the G file; target device ID, CODE, NAME, table ID, and Domain come from the database or its table definition.' if english else 'G文件名、图元类型、XML ID、图上名称和当前KeyID来自G文件；目标设备ID、CODE、NAME、表号和域号来自数据库或数据库定义。'}</p><table><thead><tr><th>{'G Object Type' if english else 'G图元类型'}</th><th>{'Table ID (Database Definition)' if english else '表号（数据库定义）'}</th><th>{'Domain (Database Definition)' if english else '域号（数据库定义）'}</th></tr></thead><tbody>{domain_rows}</tbody></table></div>
<div class="card"><h2>{'Status Legend' if english else '状态颜色说明'}</h2>
<div class="status-list">
  <div class="status-item pass"><strong>{'Green PASS' if english else '绿色 PASS'}</strong><span>{'The current model is linked to the correct current database device; no action is required.' if english else '当前模型已关联到数据库当前正确设备，无需处理。'}</span></div>
  <div class="status-item warn"><strong>{'Yellow UNLINKED' if english else '黄色 UNLINKED'}</strong><span>{'The G object is not linked yet; the current 13501 and 13502 database targets are unique and valid for association.' if english else '当前 G 图元尚未关联；13501 和 13502 数据库目标均唯一且有效，可以关联。'}</span></div>
  <div class="status-item relink"><strong>{'Orange RELINK' if english else '橙色 RELINK'}</strong><span>{'The old KeyID, device ID, table ID, or Domain is stale or incorrect; the current target is unique and can be relinked safely.' if english else '旧 KeyID、设备 ID、表号或域号已过期或错误；当前数据库目标唯一，可以安全重新关联。'}</span></div>
  <div class="status-item rmu-relink"><strong>{'Purple RMU_RELINK' if english else '紫色 RMU_RELINK'}</strong><span>{'Reserved for the common device-link status palette when an existing KeyID points to another container and a safe relink is determined.' if english else '沿用统一设备关联颜色体系，表示已有 KeyID 指向其他归属对象，但当前目标已安全确定并允许重新关联。'}</span></div>
  <div class="status-item blocked"><strong>{'Blue BLOCKED' if english else '蓝色 BLOCKED'}</strong><span>{'A blocked scenario requiring manual confirmation.' if english else '需要人工确认的整体阻断场景。'}</span></div>
  <div class="status-item fail"><strong>{'Red FAIL' if english else '红色 FAIL'}</strong><span>{'The current database facts cannot safely determine a unique target or the KeyID/BV_ID is invalid.' if english else '数据库当前事实无法安全确定唯一目标，或者 Expected KeyID / BV_ID 无效。'}</span></div>
</div></div>
<div class="card"><h2>{'Pole Switch Details' if english else '柱上开关明细'}</h2>{table}</div>
</main>
</body></html>"""
    export_path.write_text(text, encoding="utf-8")
    return export_path


def _export_transformer_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    language = normalize_language(language)
    english = language == "en_US"
    rows = flatten_transformer_rows(reports)
    labels = TRANSFORMER_LABELS_EN if english else TRANSFORMER_LABELS
    title = "Pole Transformer Model Report" if english else "柱上变压器模型报告"
    intro = (
        "Only TransformerDis objects marked Transformer_OH in Element Management are included. "
        "Each device independently resolves its name from the nearest eligible Text. "
        "The feeder uses G-root facID, with a unique facName fallback; connection topology is not analyzed."
        if english
        else
        "本报告只展示图元管理中标记为 Transformer_OH 的 TransformerDis 图元。"
        "每个设备独立取整张 G 图中最近的合规 Text 直接解析，"
        "馈线使用 G 根 facID，查不到时仅使用唯一 facName 兜底，不分析连接拓扑。"
    )
    domain_rows = "<tr><td>TransformerDis</td><td>13505</td><td>1</td></tr>"
    table = _table_html(
        rows,
        TRANSFORMER_FIELDS,
        labels,
        "status",
        selectable=True,
        table_id="transformer-table",
        filter_placeholder=(
            "Enter a transformer name, feeder ID, devref, or XML ID"
            if english
            else "输入变压器名称、馈线ID、devref 或 XML ID"
        ),
        language=language,
    )
    text = f"""<!doctype html>
<html lang="{'en' if english else 'zh-CN'}">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<style>
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:#17372E}}
header{{background:#006B52;color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}} .card{{background:white;border:1px solid #D3E3DC;border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th{{background:#006B52;color:white;position:sticky;top:0}}
th,td{{border:1px solid #D3E3DC;padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:700px}} .pass{{background:#EAF8F2}} .warn{{background:#FFF8DE}}
.relink{{background:#FFE8CC}} .rmu-relink{{background:#F0E7FF}} .blocked{{background:#EAF3FF}}
.fail{{background:#FFF0F0}} .info{{background:#EAF3FF}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px;flex-wrap:wrap}}
.table-filter-input{{width:min(560px,70vw);padding:8px 11px;border:1px solid #D3E3DC;border-radius:6px}}
.status-list{{display:flex;flex-direction:column;gap:8px;max-width:1100px}}
.status-item{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;padding:9px 12px;border-radius:6px;border:1px solid #D3E3DC}}
.status-item strong{{white-space:nowrap}} .status-item span{{line-height:1.55}}
</style>
</head>
<body>
<header><h1>{esc(title)}</h1><div>{esc(APP_NAME if not english else APP_NAME_EN)}　v{esc(APP_VERSION)}</div></header>
<main>
<div class="card"><h2>{'Association Rules' if english else '关联规则'}</h2>
<p>{esc(intro)}</p><p><strong>{'Field sources:' if english else '字段来源：'}</strong>{'G file name, object type, XML ID, text name, and current KeyID come from the G file; target device ID, CODE, NAME, table ID, and Domain come from the database or its table definition.' if english else 'G文件名、图元类型、XML ID、图上名称和当前KeyID来自G文件；目标设备ID、CODE、NAME、表号和域号来自数据库或数据库定义。'}</p><table><thead><tr><th>{'G Object Type' if english else 'G图元类型'}</th><th>{'Table ID (Database Definition)' if english else '表号（数据库定义）'}</th><th>{'Domain (Database Definition)' if english else '域号（数据库定义）'}</th></tr></thead><tbody>{domain_rows}</tbody></table></div>
<div class="card"><h2>{'Status Legend' if english else '状态颜色说明'}</h2>
<div class="status-list">
  <div class="status-item pass"><strong>{'Green PASS' if english else '绿色 PASS'}</strong><span>{'The current keyid1/keyid2 pair points to the correct transformer; no action is required.' if english else '当前 keyid1/keyid2 均已关联到正确的数据库变压器，无需处理。'}</span></div>
  <div class="status-item warn"><strong>{'Yellow UNLINKED' if english else '黄色 UNLINKED'}</strong><span>{'The Text name, feeder, and 13505 target are unique; the transformer can be linked.' if english else '图上 Text 名称、馈线和 13505 目标均唯一，可以关联。'}</span></div>
  <div class="status-item relink"><strong>{'Orange RELINK' if english else '橙色 RELINK'}</strong><span>{'The existing transformer KeyID pair is stale or incomplete; the unique 13505 target can be written again.' if english else '已有变压器 KeyID 不完整或已失效，当前唯一 13505 目标可以重新关联。'}</span></div>
  <div class="status-item rmu-relink"><strong>{'Purple RMU_RELINK' if english else '紫色 RMU_RELINK'}</strong><span>{'Reserved for the shared association status palette.' if english else '沿用统一设备关联颜色体系的保留状态。'}</span></div>
  <div class="status-item blocked"><strong>{'Blue BLOCKED' if english else '蓝色 BLOCKED'}</strong><span>{'Manual confirmation is required.' if english else '需要人工确认。'}</span></div>
  <div class="status-item fail"><strong>{'Red FAIL' if english else '红色 FAIL'}</strong><span>{'The feeder, name, target device, or Expected KeyID cannot be determined safely.' if english else '馈线、名称、目标设备或 Expected KeyID 无法安全确定。'}</span></div>
</div></div>
<div class="card"><h2>{'Pole Transformer Details' if english else '柱上变压器明细'}</h2>{table}</div>
</main>
</body></html>"""
    export_path.write_text(text, encoding="utf-8")
    return export_path


def _export_master_station_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    language = normalize_language(language)
    english = language == "en_US"
    rows = flatten_master_station_rows(reports)
    labels = MASTER_STATION_LABELS_EN if english else MASTER_STATION_LABELS
    title = "Master Station Device Association Report" if english else "配网主站设备关联报告"
    intro = (
        "Only the configured Bus, CBreaker, Disconnector, and GroundDisconnector G objects are processed. "
        "The CODE is extracted from key_name and matched exactly against the configured database table; topology is not analyzed."
        if english else
        "本报告只处理配置中的 Bus、CBreaker、Disconnector、GroundDisconnector 图元。"
        "程序从 G 文件 key_name 提取 CODE，按配置表号精确查询数据库，不分析拓扑。"
    )
    source_note = (
        "字段来源说明：G 文件名、图元类型、XML ID、key_name、CODE 和当前 KeyID 来自 G 文件；"
        "目标设备 ID、CODE、NAME、BV_ID 来自数据库；目标表号和域号来自本模块配置/数据库定义；"
        "期望 KeyID 由程序按设备 ID + 域号计算并通过数据库函数校验。回写只修改 G 图元中已有属性。"
        if not english else
        "Field sources: file name, object type, XML ID, key_name, CODE, and current KeyID come from the G file; "
        "target ID, CODE, NAME, and BV_ID come from the database; table/domain come from module configuration/database definition; "
        "Expected KeyID is calculated and verified by the database. Write-back changes existing G attributes only."
    )
    domain_rows = "".join(
        f"<tr><td>{esc(tag)}</td><td>{esc(rule.get('table_id', ''))}</td><td>{esc(rule.get('domain', ''))}</td><td>{esc(rule.get('table_name', '') or '未配置' if not english else rule.get('table_name', '') or 'Not configured')}</td></tr>"
        for tag, rule in (domain_rules or {}).items()
    )
    table = _table_html(
        rows,
        MASTER_STATION_FIELDS,
        labels,
        "status",
        selectable=True,
        table_id="master-station-table",
        filter_placeholder=("Enter CODE, G object type, or XML ID" if english else "输入 CODE、图元类型或 XML ID"),
        language=language,
    )
    text = f"""<!doctype html>
<html lang="{'en' if english else 'zh-CN'}"><head><meta charset="utf-8">
<title>{esc(title)}</title>
<style>
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:#17372E}}
header{{background:#006B52;color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}} .card{{background:white;border:1px solid #D3E3DC;border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th{{background:#006B52;color:white;position:sticky;top:0}}
th,td{{border:1px solid #D3E3DC;padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:700px}} .pass{{background:#EAF8F2}} .warn{{background:#FFF8DE}}
.relink{{background:#FFE8CC}} .fail{{background:#FFF0F0}} .blocked{{background:#EAF3FF}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px;flex-wrap:wrap}}
.table-filter-input{{width:min(560px,70vw);padding:8px 11px;border:1px solid #D3E3DC;border-radius:6px}}
</style></head><body><header><h1>{esc(title)}</h1><div>{esc(APP_NAME if not english else APP_NAME_EN)}　v{esc(APP_VERSION)}</div></header>
<main><div class="card"><h2>{'Association Rules' if english else '关联规则'}</h2><p>{esc(intro)}</p><p><strong>{'Field sources:' if english else '字段来源：'}</strong>{esc(source_note)}</p>
<table><thead><tr><th>{'G Object Type' if english else 'G图元类型'}</th><th>{'Table ID' if english else '表号'}</th><th>{'Domain' if english else '域号'}</th><th>{'Database Table' if english else '数据库表'}</th></tr></thead><tbody>{domain_rows}</tbody></table></div>
<div class="card"><h2>{'Master Station Device Details' if english else '配网主站设备明细'}</h2>{table}</div></main></body></html>"""
    export_path.write_text(text, encoding="utf-8")
    return export_path


def export_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    if _is_pole_reports(reports):
        return _export_pole_html_bundle(
            reports,
            export_path,
            domain_rules,
            language=language,
        )
    if _is_transformer_reports(reports):
        return _export_transformer_html_bundle(
            reports,
            export_path,
            domain_rules,
            language=language,
        )
    if _is_feeder_reports(reports):
        return _export_feeder_html_bundle(
            reports,
            export_path,
            domain_rules,
            language=language,
        )
    if _is_master_station_reports(reports):
        return _export_master_station_html_bundle(
            reports,
            export_path,
            domain_rules,
            language=language,
        )
    return _export_rmu_html_bundle(
        reports,
        export_path,
        domain_rules,
        language=language,
    )
