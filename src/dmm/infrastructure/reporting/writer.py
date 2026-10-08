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
    "rmu_name", "rmu_id", "rmu_is_smart", "rmu_protection_scope",
    "feeder_resolution_source", "feeder_id", "subcontrolarea_path",
    "station_name", "feeder_db_name", "feeder_name", "feeder_path",
    "object_type", "xml_id", "logical_code", "graphical_name",
    "selected_name_source", "selected_device_name", "paired_breaker_name",
    "table_id", "table_name", "configured_domain", "match_mode",
    "db_match_count", "db_match_field", "db_device_id", "db_code", "db_name",
    "db_combined_id", "db_feeder_id", "required_feeder_id", "db_bv_id",
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
    "devref", "graphical_name", "database_query_name", "name_source", "name_distance",
    "name_direction", "name_priority", "name_xml_id", "inside_rmu",
    "feeder_resolution_source", "feeder_id", "station_name",
    "feeder_code", "feeder_graph_name", "feeder_name", "feeder_path",
    "key_name", "current_keyid", "current_device_id", "current_table_id",
    "current_domain", "current_db_name", "current_db_code",
    "current_combined_id", "combined_db_code", "combined_db_name",
    "combined_db_feeder_id", "combined_match_field", "combined_db_match_count", "db_combined_id",
    "cb_parent_match_count", "cb_db_match_count", "db_device_id", "db_code",
    "db_name", "db_cb_combined_id", "db_bv_id", "db_feeder_id", "table_id", "table_name",
    "configured_domain", "expected_keyid", "expected_keyid_verified",
    "model_linked", "model_link_correct", "model_link_status",
    "association_action", "association_ready", "writeback_needed",
    "status", "severity", "reason",
]

POLE_LABELS = {
    "file_name": "G文件", "object_type": "G图元类型", "xml_id": "图元XML ID（来源：G文件）",
    "device_model": "柱上开关型号", "device_family": "设备族",
    "devref": "devref", "graphical_name": "图上名称（原样）",
    "database_query_name": "数据库查询名称（复合名保留横杠；普通名查询前去点/横杠/空格）", "name_source": "名称来源",
    "name_distance": "名称距离", "name_direction": "名称方向", "name_priority": "名称方向优先级", "name_xml_id": "名称XML ID",
    "inside_rmu": "是否在环网柜内", "key_name": "XML key_name",
    "current_keyid": "当前KeyID（来源：G文件）", "current_device_id": "当前设备ID（来源：数据库）",
    "current_table_id": "当前表号（KeyID反解/数据库定义）", "current_domain": "当前域号（KeyID反解/数据库定义）",
    "current_db_name": "当前模型设备NAME（来源：数据库）", "current_db_code": "当前模型设备CODE（来源：数据库）",
    "current_combined_id": "当前模型combined_id", "combined_name": "数据库查询名称（复合名可保留横杠）",
    "combined_db_code": "13501 CODE（来源：数据库）", "combined_db_name": "13501 NAME（来源：数据库）",
    "combined_db_feeder_id": "13501馈线ID（来源：数据库）",
    "combined_match_field": "13501匹配字段",
    "combined_db_match_count": "13501匹配数", "db_combined_id": "13501 ID（来源：数据库）",
    "cb_parent_match_count": "13502父设备记录数",
    "cb_db_match_count": "13502目标匹配数", "db_device_id": "目标设备ID（来源：数据库）",
    "db_code": "目标设备CODE（来源：数据库）", "db_name": "目标设备NAME（来源：数据库）",
    "db_cb_combined_id": "目标combined_id（来源：数据库）", "db_bv_id": "目标BV_ID（来源：数据库）",
    "db_feeder_id": "目标13502馈线ID（来源：数据库）",
    "table_id": "目标表号（来源：数据库定义）", "table_name": "目标数据库表（来源：数据库）",
    "configured_domain": "目标域号（来源：数据库定义）", "expected_keyid": "期望KeyID（程序计算）",
    "expected_keyid_verified": "期望KeyID校验（数据库）", "model_linked": "是否已关联",
    "model_link_correct": "当前模型是否正确", "model_link_status": "当前模型状态",
    "association_action": "处理建议", "association_ready": "可进入关联流程",
    "writeback_needed": "是否需要回写", "status": "状态", "severity": "状态类型",
    "station_name": "厂站名称（来源：数据库）", "feeder_code": "馈线CODE（来源：数据库）",
    "feeder_graph_name": "馈线图名（来源：数据库）", "feeder_path": "厂站 / 馈线定位（数据库）",
    "feeder_resolution_source": "图级馈线识别方式",
    "feeder_id": "图级馈线ID（来源：数据库）",
    "subcontrolarea_path": "调控区域路径（来源：数据库）",
    "station_name": "厂站名称（来源：数据库）",
    "feeder_db_name": "13500馈线NAME（来源：数据库）",
    "feeder_name": "数据库验证馈线全名",
    "feeder_path": "完整馈线路径（数据库）",
    "reason": "说明",
}

POLE_LABELS_EN = {
    key: value for key, value in {
        "file_name": "G File", "object_type": "G Object Type", "xml_id": "XML ID (G File)",
        "device_model": "Pole Switch Model", "device_family": "Device Family",
        "devref": "devref", "graphical_name": "Graphical Name (Original)",
        "database_query_name": "Database Lookup Name (compound name may keep hyphen)", "name_source": "Name Source",
        "name_distance": "Name Distance", "name_direction": "Name Direction", "name_priority": "Name Direction Priority", "name_xml_id": "Name XML ID",
        "inside_rmu": "Inside RMU", "key_name": "XML key_name",
        "current_keyid": "Current KeyID (G File)", "current_device_id": "Current Device ID (Database)",
        "current_table_id": "Current Table ID (Decoded/DB Definition)", "current_domain": "Current Domain (Decoded/DB Definition)",
        "current_db_name": "Current Model NAME (Database)", "current_db_code": "Current Model CODE (Database)",
        "current_combined_id": "Current Model combined_id", "combined_name": "Database Lookup Name (compound name may keep hyphen)",
        "combined_db_code": "13501 CODE (Database)", "combined_db_name": "13501 NAME (Database)",
        "combined_db_feeder_id": "13501 Feeder ID (Database)",
        "combined_match_field": "13501 Match Field",
        "combined_db_match_count": "13501 Match Count", "db_combined_id": "13501 ID (Database)",
        "cb_parent_match_count": "13502 Parent Record Count",
        "cb_db_match_count": "13502 Target Match Count", "db_device_id": "Target Device ID (Database)",
        "db_code": "Target Device CODE (Database)", "db_name": "Target Device NAME (Database)",
        "db_cb_combined_id": "Target combined_id (Database)", "db_bv_id": "Target BV_ID (Database)",
        "db_feeder_id": "Target 13502 Feeder ID (Database)",
        "table_id": "Target Table ID (Database Definition)", "table_name": "Target Database Table (Database)",
        "configured_domain": "Target Domain (Database Definition)", "expected_keyid": "Expected KeyID (Calculated)",
        "expected_keyid_verified": "Expected KeyID Check (Database)", "model_linked": "Model Linked",
        "model_link_correct": "Current Model Correct", "model_link_status": "Current Model Status",
        "association_action": "Recommended Action", "association_ready": "Ready for Association",
        "writeback_needed": "Write-back Needed", "status": "Status", "severity": "Status Type",
        "station_name": "Station Name (Database)", "feeder_code": "Feeder CODE (Database)",
        "feeder_graph_name": "Feeder Graph Name (Database)", "feeder_path": "Station / Feeder Path (Database)",
        "feeder_resolution_source": "Graph Feeder Resolution Source",
        "feeder_id": "Graph Feeder ID (Database)",
        "feeder_name": "Graph Feeder Name (Database)",
        "reason": "Details",
    }.items()
}

TRANSFORMER_FIELDS = [
    "file_name", "object_type", "xml_id", "devref", "graphical_name",
    "name_source", "name_distance", "name_direction", "name_priority", "name_xml_id",
    "feeder_resolution_source", "feeder_id",
    "station_name", "feeder_code", "feeder_graph_name", "feeder_db_name", "feeder_name", "feeder_path",
    "bay_id", "bay_code", "bay_name", "location_label",
    "current_keyid", "current_keyid1", "current_keyid2",
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
    "devref": "devref", "graphical_name": "图上名称（原样）",
    "database_query_name": "数据库查询名称（复合名保留横杠；普通名查询前去点/横杠/空格）", "name_source": "名称来源",
    "name_distance": "名称距离", "name_direction": "名称方向", "name_priority": "名称方向优先级", "name_xml_id": "名称XML ID",
    "feeder_resolution_source": "馈线识别方式", "feeder_id": "目标馈线ID",
    "station_name": "厂站名称（来源：数据库）", "feeder_code": "馈线CODE（来源：数据库）",
    "feeder_graph_name": "馈线图名（来源：数据库）", "feeder_path": "厂站 / 馈线定位（数据库）",
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
    "name_distance": "Name Distance", "name_direction": "Name Direction", "name_priority": "Name Direction Priority", "name_xml_id": "Name XML ID",
    "feeder_resolution_source": "Feeder Resolution Source", "feeder_id": "Target Feeder ID",
    "station_name": "Station Name (Database)", "feeder_code": "Feeder CODE (Database)",
    "feeder_graph_name": "Feeder Graph Name (Database)", "feeder_path": "Station / Feeder Path (Database)",
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


FUSE_FIELDS = [
    "file_name", "object_type", "xml_id", "devref", "derived_fuse_name",
    "transformer_assignment_status", "transformer_assignment_reason", "transformer_owner_fuse_xml_id", "transformer_claim_count",
    "nearest_transformer_name", "nearest_transformer_xml_id", "nearest_transformer_distance",
    "transformer_name_direction", "transformer_name_priority", "transformer_name_distance", "transformer_name_distance_basis", "transformer_name_xml_id",
    "transformer_name_resolution_status", "transformer_13505_match_count", "feeder_resolution_source", "feeder_anchor", "feeder_id",
    "station_name", "feeder_code", "feeder_graph_name", "feeder_name", "feeder_path",
    "current_keyid", "current_device_id", "current_table_id", "current_domain",
    "current_db_name", "current_db_code", "current_feeder_id",
    "db_match_count", "db_device_id", "db_code", "db_name", "db_bv_id", "db_feeder_id",
    "table_id", "table_name", "configured_domain", "expected_keyid", "expected_keyid_verified",
    "model_linked", "model_link_correct", "model_link_status", "association_action",
    "association_ready", "writeback_needed", "status", "severity", "reason",
]

FUSE_LABELS = {
    "file_name": "G文件", "object_type": "G图元类型", "xml_id": "熔断器XML ID（来源：G文件）",
    "devref": "devref", "transformer_assignment_status": "柱上变压器分配状态",
    "transformer_assignment_reason": "柱上变压器分配说明", "transformer_owner_fuse_xml_id": "柱上变压器占用FUSE XML ID",
    "transformer_claim_count": "同一变压器FUSE候选数", "nearest_transformer_name": "匹配柱上变压器名称",
    "nearest_transformer_xml_id": "最近柱上变压器XML ID", "nearest_transformer_distance": "熔断器到变压器距离",
    "transformer_name_direction": "变压器名称方向", "transformer_name_priority": "变压器名称方向优先级", "transformer_name_distance": "变压器名称距离",
    "transformer_name_distance_basis": "变压器名称距离基准", "transformer_name_xml_id": "变压器名称Text XML ID",
    "transformer_name_resolution_status": "柱上变压器名称数据库校验", "transformer_13505_match_count": "柱上变压器13505匹配数", "derived_fuse_name": "计算熔断器名称",
    "feeder_resolution_source": "馈线识别方式", "feeder_anchor": "馈线判定设备",
    "feeder_id": "图级馈线ID", "station_name": "厂站名称（来源：数据库）",
    "feeder_code": "馈线CODE（来源：数据库）", "feeder_graph_name": "馈线图名（来源：数据库）",
    "feeder_name": "图级馈线名称（来源：数据库）", "feeder_path": "厂站 / 馈线定位（数据库）",
    "current_keyid": "当前KeyID（来源：G文件）", "current_device_id": "当前设备ID（来源：数据库）",
    "current_table_id": "当前表号（KeyID反解）", "current_domain": "当前域号（KeyID反解）",
    "current_db_name": "当前模型NAME（来源：数据库）", "current_db_code": "当前模型CODE（来源：数据库）",
    "current_feeder_id": "当前模型馈线ID（来源：数据库）", "db_match_count": "13513匹配数",
    "db_device_id": "目标设备ID", "db_code": "目标设备CODE（来源：数据库）",
    "db_name": "目标设备NAME（来源：数据库）", "db_bv_id": "目标BV_ID（来源：数据库）",
    "db_feeder_id": "目标设备馈线ID（来源：数据库）", "table_id": "目标表号（数据库定义）",
    "table_name": "目标数据库表", "configured_domain": "目标域号（数据库定义）",
    "expected_keyid": "期望KeyID（程序计算）", "expected_keyid_verified": "期望KeyID校验（数据库）",
    "model_linked": "是否已关联", "model_link_correct": "当前模型是否正确",
    "model_link_status": "当前模型状态", "association_action": "处理建议",
    "association_ready": "可进入关联流程", "writeback_needed": "是否需要回写",
    "status": "状态", "severity": "状态类型", "reason": "说明",
}

FUSE_LABELS_EN = {
    "file_name": "G File", "object_type": "G Object Type", "xml_id": "Fuse XML ID (G File)",
    "devref": "devref", "transformer_assignment_status": "Transformer Assignment",
    "transformer_assignment_reason": "Transformer Assignment Details", "transformer_owner_fuse_xml_id": "Owning Fuse XML ID",
    "transformer_claim_count": "Fuse Claims on Transformer", "nearest_transformer_name": "Matched Pole Transformer Name",
    "nearest_transformer_xml_id": "Nearest Transformer XML ID", "nearest_transformer_distance": "Fuse-to-Transformer Distance",
    "transformer_name_direction": "Transformer Name Direction", "transformer_name_priority": "Transformer Name Priority", "transformer_name_distance": "Transformer Name Distance",
    "transformer_name_distance_basis": "Transformer Name Distance Basis", "transformer_name_xml_id": "Transformer Name Text XML ID",
    "transformer_name_resolution_status": "Transformer Name DB Validation", "transformer_13505_match_count": "Transformer 13505 Match Count", "derived_fuse_name": "Derived Fuse NAME",
    "feeder_resolution_source": "Feeder Resolution Source", "feeder_anchor": "Feeder Anchor Device",
    "feeder_id": "Drawing Feeder ID", "station_name": "Station Name (Database)",
    "feeder_code": "Feeder CODE (Database)", "feeder_graph_name": "Feeder Graph Name (Database)",
    "feeder_name": "Drawing Feeder Name (Database)", "feeder_path": "Station / Feeder Path (Database)",
    "current_keyid": "Current KeyID (G File)", "current_device_id": "Current Device ID (Database)",
    "current_table_id": "Current Table ID (Decoded)", "current_domain": "Current Domain (Decoded)",
    "current_db_name": "Current Model NAME (Database)", "current_db_code": "Current Model CODE (Database)",
    "current_feeder_id": "Current Model Feeder ID (Database)", "db_match_count": "13513 Match Count",
    "db_device_id": "Target Device ID", "db_code": "Target Device CODE (Database)",
    "db_name": "Target Device NAME (Database)", "db_bv_id": "Target BV_ID (Database)",
    "db_feeder_id": "Target Device Feeder ID (Database)", "table_id": "Target Table ID",
    "table_name": "Target Database Table", "configured_domain": "Target Domain",
    "expected_keyid": "Expected KeyID", "expected_keyid_verified": "Expected KeyID Check",
    "model_linked": "Model Linked", "model_link_correct": "Current Model Correct",
    "model_link_status": "Current Model Status", "association_action": "Recommended Action",
    "association_ready": "Ready for Association", "writeback_needed": "Write-back Needed",
    "status": "Status", "severity": "Status Type", "reason": "Details",
}

MASTER_STATION_FIELDS = [
    "file_name", "object_type", "xml_id", "key_name", "logical_code",
    "feeder_resolution_source", "feeder_anchor", "feeder_id", "station_id",
    "station_name", "feeder_code", "feeder_graph_name", "feeder_db_name", "feeder_name", "feeder_path",
    "bay_id", "bay_code", "bay_name", "location_label",
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
    "key_name": "XML key_name（来源：G文件，仅展示）", "logical_code": "CODE解析（不使用）",
    "feeder_resolution_source": "图级馈线识别方式",
    "feeder_anchor": "本次判定依据设备/环网柜",
    "feeder_id": "图级馈线ID（来源：数据库）", "station_id": "厂站ID（来源：数据库）",
    "station_name": "厂站名称（来源：数据库）", "feeder_code": "馈线CODE（来源：数据库）",
    "feeder_graph_name": "馈线图名（来源：数据库）", "feeder_name": "图级馈线名称（来源：数据库）",
    "feeder_db_name": "馈线NAME（来源：数据库）", "feeder_path": "厂站 / 馈线定位（数据库）",
    "bay_id": "间隔BAY ID（来源：数据库）", "bay_code": "间隔BAY CODE（来源：数据库）",
    "bay_name": "间隔BAY NAME（来源：数据库）", "location_label": "完整厂站 / 馈线 / 间隔定位",
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
    "configured_domain": "目标域号（配置/数据库定义）", "db_match_count": "BAY_ID候选数（数据库）",
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
        "key_name": "XML key_name (G File, display only)", "logical_code": "CODE Parsing (Unused)",
        "feeder_resolution_source": "Graph Feeder Resolution Source",
        "feeder_anchor": "Feeder Anchor Device/RMU",
        "feeder_id": "Graph Feeder ID (Database)", "station_id": "Station ID (Database)",
        "station_name": "Station Name (Database)", "feeder_code": "Feeder CODE (Database)",
        "feeder_graph_name": "Feeder Graph Name (Database)", "feeder_name": "Graph Feeder Name (Database)",
        "feeder_db_name": "Feeder NAME (Database)", "feeder_path": "Station / Feeder Path (Database)",
        "bay_id": "Bay ID (Database)", "bay_code": "Bay CODE (Database)",
        "bay_name": "Bay NAME (Database)", "location_label": "Full Station / Feeder / Bay Location",
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
        "configured_domain": "Target Domain (Config/DB Definition)", "db_match_count": "BAY_ID Candidate Count (Database)",
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
    "feeder_resolution_source", "feeder_id", "subcontrolarea_path",
    "station_name", "feeder_db_name", "feeder_name", "feeder_path",
    "rmu_db_total_count", "rmu_db_count",
    "rmu_type", "rmu_type_source", "rmu_type_text", "rmu_type_devref",
    "rmu_type_consistent", "rmu_type_check_status", "rmu_type_check_reason",
    "rmu_is_smart", "rmu_smart_marker_types", "rmu_protection_scope",
    "rmu_status", "rmu_reason",
    "database_unique", "rmu_id",
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
    "rmu_protection_scope": "保护/EFI关联范围",
    "feeder_resolution_source": "图级馈线识别方式",
    "feeder_id": "图级馈线ID（来源：数据库）",
    "subcontrolarea_path": "调控区域路径（来源：数据库）",
    "station_name": "厂站名称（来源：数据库）",
    "feeder_db_name": "13500馈线NAME（来源：数据库）",
    "feeder_code": "馈线CODE（来源：数据库）",
    "feeder_graph_name": "馈线图名（来源：数据库）",
    "feeder_name": "数据库验证馈线全名",
    "feeder_path": "完整馈线路径（数据库）",
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
    "db_match_field": "最终匹配字段",
    "db_device_id": "关联数据库设备ID（来源：数据库）",
    "db_code": "关联设备CODE（来源：数据库）",
    "db_name": "关联设备NAME（来源：数据库）",
    "db_combined_id": "所属环网柜ID（来源：数据库）",
    "db_feeder_id": "设备所属馈线ID（来源：数据库）",
    "required_feeder_id": "文件名确定的馈线ID",
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
    "feeder_resolution_source": "图级馈线识别方式",
    "feeder_id": "图级馈线ID（来源：数据库）",
    "subcontrolarea_path": "调控区域路径（来源：数据库）",
    "station_name": "厂站名称（来源：数据库）",
    "feeder_db_name": "13500馈线NAME（来源：数据库）",
    "feeder_name": "数据库验证馈线全名",
    "feeder_path": "完整馈线路径（数据库）",
    "rmu_db_total_count": "同名环网柜总数（13501）",
    "rmu_db_count": "当前馈线内匹配数",
    "rmu_type": "环网柜类型",
    "rmu_type_source": "类型识别来源",
    "rmu_type_text": "图内文字类型",
    "rmu_type_devref": "devref类型",
    "rmu_type_consistent": "类型交叉校验",
    "rmu_type_check_status": "柜型校验状态",
    "rmu_type_check_reason": "柜型交叉校验说明",
    "rmu_is_smart": "是否智能",
    "rmu_smart_marker_types": "智能标识",
    "rmu_protection_scope": "保护/EFI关联范围",
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
    "rmu_protection_scope": "Protection / EFI Scope",
    "feeder_resolution_source": "Graph Feeder Resolution Source",
    "feeder_id": "Graph Feeder ID (Database)",
    "subcontrolarea_path": "Control Area Path (Database)",
    "station_name": "Substation (Database)",
    "feeder_db_name": "13500 Feeder NAME (Database)",
    "feeder_name": "Database-verified Full Feeder Name",
    "feeder_path": "Full Feeder Path (Database)",
    "object_type": "G Object Type", "xml_id": "XML ID (G File)", "logical_code": "Logical CODE (Graph Rule)",
    "graphical_name": "Graphical Name", "selected_name_source": "Device Name Source", "selected_device_name": "Final Device Name",
    "paired_breaker_name": "Paired Breaker Name", "table_id": "Table ID (Database Definition)", "table_name": "Database Table",
    "configured_domain": "Domain (Database Definition)", "match_mode": "Match Rule", "db_match_count": "DB Match Count",
    "db_match_field": "Final Match Field",
    "db_device_id": "Matched DB Device ID (Database)", "db_code": "Matched Device CODE (Database)", "db_name": "Matched Device NAME (Database)",
    "db_combined_id": "RMU ID (Database)", "db_feeder_id": "Device Feeder ID (Database)", "required_feeder_id": "Filename Feeder ID",
    "db_bv_id": "BV_ID", "expected_keyid": "Expected KeyID (Calculated/Verified)",
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
    "feeder_resolution_source": "Graph Feeder Resolution Source",
    "feeder_id": "Graph Feeder ID (Database)",
    "subcontrolarea_path": "Control Area Path (Database)",
    "station_name": "Substation (Database)",
    "feeder_db_name": "13500 Feeder NAME (Database)",
    "feeder_name": "Database-verified Full Feeder Name",
    "feeder_path": "Full Feeder Path (Database)",
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
                feeder_id = str(
                    rmu.get("feeder_id", report.get("feeder_id", "")) or ""
                ).strip()
                if feeder_id:
                    reason = (
                        f"RMU_DUPLICATE_IN_FEEDER: 当前图级 FEEDER_ID={feeder_id} 下"
                        f"仍找到 {db_count} 个同名环网柜，无法唯一确定目标。"
                    )
                    duplicate_block = (
                        f"当前图级馈线 {feeder_id} 下仍有 {db_count} 个同名环网柜；"
                        "禁止自动关联，请检查数据库模型。"
                    )
                else:
                    reason = (
                        f"RMU_DUPLICATE_IN_DATABASE: 数据库中找到 {db_count} 个同名环网柜，"
                        "请检查数据库模型和当前 G 图中的该环网柜。"
                    )
                    duplicate_block = (
                        f"数据库中找到 {db_count} 个同名环网柜；环网柜必须唯一，"
                        "禁止自动关联，请检查数据库模型和当前 G 图中的该环网柜。"
                    )
                if duplicate_block not in block_reasons:
                    block_reasons.append(duplicate_block)

            elif db_count == 0:
                status = "FAIL"
                severity = "ERROR"
                if not reason or reason == "RMU_NOT_FOUND_IN_DATABASE":
                    reason = (
                        "RMU_NOT_FOUND_IN_DATABASE: 数据库中未找到该环网柜，"
                        "请检查数据库模型和当前 G 图中的环网柜名称。"
                    )

            device_rows = [
                d for d in rmu.get("device_rows", [])
                if d.get("xml_id")
            ]
            # SMART_ONLY policy intentionally exempts protection/EFI rows in
            # NORMAL RMUs from database association completeness. They remain
            # visible in details/statistics, but do not make the RMU look
            # incomplete merely because the policy says they must be unlinked.
            completeness_rows = [
                d for d in device_rows
                if d.get("policy_exempt") != "YES"
            ]
            matched_device_count = sum(
                1
                for d in completeness_rows
                if int(d.get("db_match_count") or 0) == 1
                and (
                    db_count != 1
                    or str(d.get("db_combined_id", ""))
                    == str(unique_record.get("id", ""))
                )
            )
            device_complete = (
                db_count == 1
                and bool(completeness_rows)
                and matched_device_count == len(completeness_rows)
            )

            row = {
                "file_name": file_name,
                "frame_index": rmu.get("frame_index", ""),
                "frame_xml_id": rmu.get("frame_xml_id", ""),
                "rmu_name": rmu.get("rmu_name", ""),
                "feeder_resolution_source": rmu.get(
                    "feeder_resolution_source", report.get("feeder_resolution_source", "")
                ),
                "feeder_resolution_evidence": rmu.get(
                    "feeder_resolution_evidence", report.get("feeder_resolution_evidence", "")
                ),
                "feeder_id": rmu.get("feeder_id", report.get("feeder_id", "")),
                "subcontrolarea_path": rmu.get("subcontrolarea_path", report.get("subcontrolarea_path", "")),
                "station_name": rmu.get("station_name", report.get("station_name", "")),
                "feeder_db_name": rmu.get("feeder_db_name", report.get("feeder_db_name", "")),
                "feeder_name": rmu.get("feeder_name", report.get("feeder_name", "")),
                "feeder_path": rmu.get("feeder_path", report.get("feeder_path", "")),
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
                "rmu_protection_scope": rmu.get("rmu_protection_scope", ""),
                "rmu_status": status,
                "rmu_severity": severity,
                "rmu_reason": reason,
                "rmu_db_total_count": rmu.get(
                    "rmu_db_total_count", db_count
                ),
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
                row.setdefault("rmu_is_smart", (
                    "SMART"
                    if str(rmu.get("rmu_is_smart", "NO")).strip().upper()
                    in {"YES", "TRUE", "1", "SMART", "SMR"}
                    else "NORMAL"
                ))
                row.setdefault("rmu_protection_scope", rmu.get("rmu_protection_scope", row.get("rmu_protection_scope", "")))
                row.pop("x", None)
                row.pop("y", None)
                row["file_name"] = file_name
                row.setdefault("rmu_name", rmu.get("rmu_name", ""))
                row.setdefault("rmu_id", rmu.get("rmu_id", ""))
                row.setdefault("feeder_resolution_source", rmu.get("feeder_resolution_source", report.get("feeder_resolution_source", "")))
                row.setdefault("feeder_id", rmu.get("feeder_id", report.get("feeder_id", "")))
                row.setdefault("subcontrolarea_path", rmu.get("subcontrolarea_path", report.get("subcontrolarea_path", "")))
                row.setdefault("station_name", rmu.get("station_name", report.get("station_name", "")))
                row.setdefault("feeder_db_name", rmu.get("feeder_db_name", report.get("feeder_db_name", "")))
                row.setdefault("feeder_name", rmu.get("feeder_name", report.get("feeder_name", "")))
                row.setdefault("feeder_path", rmu.get("feeder_path", report.get("feeder_path", "")))
                rows.append(row)

    return rows


def _rmu_feeder_overview(reports, english=False):
    """Render the database-verified feeder hierarchy per G file.

    The G filename supplies only the station token + feeder token.  The final
    hierarchy shown to operators is verified through:
        405/substation.NAME -> 405.SUBAREA_ID -> 404/subcontrolarea.ID
        -> 13500/dms_feeder_device(ST_ID + NAME)
    so a file such as JED-CTL-ADF-34.sln.pic.g can display
    ``JED CTL | ADF | AH334 | JED CTL ADF AH334``.
    """
    rows = []
    for report in reports:
        file_name = str(report.get("file_name", "") or "").strip()
        source = str(report.get("feeder_resolution_source", "") or "").strip()
        selected_id = str(report.get("feeder_id", "") or "").strip()
        control_area = str(report.get("subcontrolarea_path", "") or "").strip()
        station_name = str(report.get("station_name", "") or "").strip()
        feeder_db_name = str(report.get("feeder_db_name", "") or "").strip()
        full_name = str(
            report.get("feeder_name", "")
            or report.get("feeder_path", "")
            or report.get("feeder_graph_name", "")
            or ""
        ).strip()

        if not station_name:
            # Filename is still the drawing identity, so expose its station
            # token on failed DB resolution to help the operator locate the
            # failing database link.
            stem = file_name
            lower = stem.lower()
            for suffix in (".sln.pic.g", ".pic.g", ".g"):
                if lower.endswith(suffix):
                    stem = stem[:-len(suffix)]
                    break
            parts = stem.split("-")
            if len(parts) == 4 and parts[0].upper() == "JED":
                station_name = parts[2].strip().upper()

        ready = str(report.get("feeder_context_ready", "") or "").upper() == "YES"
        resolved = ready and bool(selected_id) and source.upper() == "FILENAME_405_13500"

        if not resolved:
            message = str(
                report.get("feeder_context_message", "")
                or report.get("reason", "")
                or ""
            ).strip()
            message_upper = message.upper()
            if "FILENAME" in message_upper and (
                "FORMAT" in message_upper
                or "INVALID" in message_upper
                or "文件名" in message
            ):
                full_name = (
                    "Invalid filename; please rename the G file."
                    if english
                    else "文件名不符合规则，请修改文件名。"
                )
            else:
                full_name = (
                    "Not found in database; check 405/substation, 404/subcontrolarea and 13500/dms_feeder_device."
                    if english
                    else "数据库未找到，请检查该图的馈线是否已创建。请同时核对 405/substation、404/subcontrolarea 和 13500/dms_feeder_device。"
                )
            feeder_db_name = feeder_db_name or "-"

        rows.append(
            "<tr>"
            f"<td>{esc(file_name)}</td>"
            f"<td>{esc(control_area or '-')}</td>"
            f"<td>{esc(station_name or '-')}</td>"
            f"<td>{esc(feeder_db_name or '-')}</td>"
            f"<td style='white-space:normal'>{esc(full_name or '-')}</td>"
            "</tr>"
        )

    headers = (
        ["G File", "Control Area", "Substation", "13500 Feeder NAME", "Database-verified Full Feeder Name"]
        if english
        else ["G文件", "调控区域", "所属站/厂站", "13500馈线NAME", "数据库验证馈线全名"]
    )
    empty = "No filename feeder result was found." if english else "未找到文件名馈线判定结果。"
    body = "".join(rows) or f"<tr><td colspan='5'>{esc(empty)}</td></tr>"
    title = "Filename Feeder Overview" if english else "文件名馈线概览"
    intro = (
        "The filename selects the station/feeder token; the displayed hierarchy is verified by 405/substation, 404/subcontrolarea and 13500/dms_feeder_device."
        if english
        else "文件名只负责解析厂站/馈线标识；显示的完整层级由 405/substation → 404/subcontrolarea → 13500/dms_feeder_device 数据库链路验证。"
    )
    return (
        f"<div class='card'><h2>{esc(title)}</h2><p>{esc(intro)}</p>"
        "<table class='feeder-overview-table'><thead><tr>"
        + "".join(f"<th>{esc(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def _feeder_resolution_kind(source):
    """Return the feeder-anchor family encoded in the shared resolver source."""
    source = str(source or "").upper()
    if source.startswith("FILENAME_"):
        return "FILENAME"
    if "POLE_SWITCH" in source:
        return "POLE_SWITCH"
    if "TRANSFORMER" in source:
        return "TRANSFORMER"
    if "RMU" in source:
        return "RMU"
    return ""


def _friendly_feeder_anchor(anchor, kind, english=False):
    """Render the selected feeder anchor as one short operator-facing label."""
    anchor = str(anchor or "").strip()
    labels = {
        "RMU": ("RMU" if english else "环网柜"),
        "POLE_SWITCH": ("Pole Switch" if english else "柱上开关"),
        "TRANSFORMER": ("Pole Transformer" if english else "柱上变压器"),
        "FILENAME": ("G Filename" if english else "G文件名"),
    }
    label = labels.get(kind, "Device" if english else "设备")
    if not anchor:
        return "-"
    prefixes = {
        "RMU:": labels["RMU"] + " ",
        "POLE_SWITCH:": labels["POLE_SWITCH"] + " ",
        "TRANSFORMER:": labels["TRANSFORMER"] + " ",
        "FILE:": labels["FILENAME"] + " ",
    }
    for prefix, replacement in prefixes.items():
        if anchor.upper().startswith(prefix):
            return replacement + anchor[len(prefix):].strip()
    return anchor


def _feeder_resolution_method(source, english=False):
    """Explain the authoritative filename-only feeder resolution."""
    kind = _feeder_resolution_kind(source)
    if kind == "FILENAME":
        return (
            "G filename -> exact 405/substation.NAME -> NN builds AH3NN / AGNN builds AG4NN -> exact 13500 ST_ID + NAME -> FEEDER_ID"
            if english
            else "G文件名 → 405/substation.NAME 精确找站 → 普通 NN 拼接 AH3+两位编号；AGNN 转为 AG4NN → 13500 按 ST_ID + NAME 精确查询 → FEEDER_ID"
        )
    return (
        "Filename resolution failed; graphical devices are not permitted to choose a feeder."
        if english
        else "文件名馈线判定失败；禁止再使用环网柜、柱上开关、柱上变压器等图中设备反推馈线。"
    )

def _feeder_resolution_card(reports, english=False, *, context_key=None, title=None):
    """Render a compact human-readable explanation of how the feeder was chosen.

    The detailed resolver evidence remains internal.  Reports intentionally show
    only the selected anchor device, the short database path used to determine
    FEEDER_ID, and the final feeder result.
    """
    rows = []
    for report in reports:
        context = (report.get(context_key, {}) or {}) if context_key else report
        source = str(context.get("feeder_resolution_source") or "").strip()
        anchor = str(context.get("feeder_anchor") or "").strip()
        feeder_id = str(context.get("feeder_id") or report.get("feeder_id") or "").strip()
        feeder_label = str(
            context.get("feeder_path")
            or context.get("location_label")
            or context.get("feeder_name")
            or report.get("feeder_path")
            or report.get("feeder_name")
            or report.get("feeder_graph_name")
            or ""
        ).strip()
        kind = _feeder_resolution_kind(source)
        device = _friendly_feeder_anchor(anchor, kind, english=english)
        method = _feeder_resolution_method(source, english=english)
        resolved = bool(feeder_id) and source.upper() == "FILENAME_405_13500"
        result = ("Resolved" if english else "已确定") if resolved else ("Unresolved" if english else "无法确定")
        final_feeder = feeder_label or "-"
        if feeder_id:
            final_feeder = f"{final_feeder} (FEEDER_ID={feeder_id})" if final_feeder != "-" else f"FEEDER_ID={feeder_id}"
        note = ""
        if not resolved:
            note = str(
                context.get("feeder_context_message")
                or context.get("message")
                or report.get("feeder_context_message")
                or report.get("reason")
                or ""
            ).strip()
        rows.append(
            "<tr>"
            f"<td>{esc(report.get('file_name', ''))}</td>"
            f"<td><strong>{esc(device)}</strong></td>"
            f"<td style='white-space:normal;min-width:360px'>{esc(method)}</td>"
            f"<td>{esc(final_feeder)}</td>"
            f"<td>{esc(result)}</td>"
            f"<td style='white-space:normal;min-width:220px'>{esc(note or '-')}</td>"
            "</tr>"
        )
    headers = (
        ["G File", "Anchor Device", "How Feeder Was Determined", "Final Feeder", "Result", "Note"]
        if english else
        ["G文件", "判定设备", "馈线判定方式", "最终馈线", "结果", "说明"]
    )
    body = "".join(rows) or (
        "<tr><td colspan='6'>" + esc("No feeder resolution result." if english else "未找到馈线判定结果。") + "</td></tr>"
    )
    card_title = title or ("Feeder Resolution" if english else "馈线判定")
    intro = (
        "The report shows only the actual anchor device and the short database path used to obtain FEEDER_ID; verbose internal evidence is omitted."
        if english else
        "这里只显示本次实际采用的判定设备和 FEEDER_ID 的简要判断过程，不展开内部的长判定链。"
    )
    return (
        f"<div class='card compact-result'><h2>{esc(card_title)}</h2><p>{esc(intro)}</p>"
        "<table class='feeder-overview-table'><thead><tr>"
        + "".join(f"<th>{esc(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def _pole_switch_feeder_result(reports, english=False):
    return _feeder_resolution_card(
        reports,
        english=english,
        title=("Pole-switch Feeder Resolution" if english else "柱上开关馈线判定"),
    )

def _jeddah_scope_overview(reports, english=False):
    """Compact common Jeddah association-scope card for every module."""
    rows = []
    for report in reports:
        scope = report.get("drawing_scope", {}) or {}
        counts = scope.get("main_device_counts", {}) or {}
        main_text = ", ".join(
            f"{tag}={counts.get(tag, 0)}"
            for tag in ("CBreaker", "Disconnector", "GroundDisconnector")
        )
        allowed = bool(scope.get("association_allowed"))
        result = "允许关联" if allowed else "禁止关联"
        if english:
            result = "Association allowed" if allowed else "Association blocked"
        rows.append(
            "<tr>"
            f"<td>{esc(report.get('file_name', ''))}</td>"
            f"<td>{esc(scope.get('drawing_type', '') or '-')}</td>"
            f"<td>{esc(report.get('graph_facid', '') or '-')}</td>"
            f"<td>{esc(report.get('facid_check', '') or '-')}</td>"
            f"<td>{esc(scope.get('associated_bus_count', 0))}</td>"
            f"<td>{esc(scope.get('main_bus_layout', '') or '-')}</td>"
            f"<td>{esc(scope.get('associated_bus_xml_id', '') or '-')}</td>"
            f"<td>{esc(main_text)}</td>"
            f"<td>{esc(result)}</td>"
            f"<td>{esc(scope.get('block_reason', '') or '-')}</td>"
            "</tr>"
        )
    headers = (
        ["G File", "Drawing Type", "G facID", "facID Check", "Connected Main Bus Count", "Bus Layout", "Main Bus XML ID", "Main Device Counts", "Result", "Restriction"]
        if english
        else ["G文件", "图纸类型", "G根节点 facID", "facID 校验", "关联主网 Bus 数量", "母线形式", "主网 Bus XML ID", "主网设备数量", "结果", "关联限制"]
    )
    body = "".join(rows) or f"<tr><td colspan='10'>{esc('No scope data.' if english else '未找到图纸范围判断信息。')}</td></tr>"
    title = "Jeddah Association Scope" if english else "吉达关联范围判断"
    intro = (
        "Association is allowed only when one single-line feeder and one connected main-device group are detected. A single-bus or double-bus arrangement is valid; isolated Bus objects are ignored."
        if english
        else
        "只有在单线图中，并且检测到一个与主网设备相连的主网设备组时才允许关联；单母线或双母线均可，孤立 Bus 不计入。"
    )
    return (
        f"<div class='card'><h2>{esc(title)}</h2><p>{esc(intro)}</p>"
        "<table><thead><tr>"
        + "".join(f"<th>{esc(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def _compact_transformer_feeder_result(reports, english=False):
    return _feeder_resolution_card(
        reports,
        english=english,
        title=("Pole-transformer Feeder Resolution" if english else "柱上变压器馈线判定"),
    )



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



def flatten_fuse_rows(reports):
    rows = []
    for report in reports:
        file_name = report.get("file_name", "")
        for item in report.get("fuse_rows", []) or []:
            row = dict(item)
            for coordinate in ("x", "y", "w", "h"):
                row.pop(coordinate, None)
            row.pop("feeder_resolution_evidence", None)
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
        # Keep feeder-resolution evidence available to validation/logging, but do not
        # expose the verbose evidence chain as a user-facing report column/JSON field.
        "feeder_resolution_evidence",
        "topology_component",
        "topology_member_count",
        "topology_member_ids",
        "topology_member_tags",
        "topology_neighbor_count",
        "topology_neighbor_ids",
    }
)


def _pole_report_for_output(report):
    """Remove internal evidence from the persisted public pole report.

    The pole-switch validator still keeps these fields in memory for validation,
    feeder ownership checks and logging. They are intentionally not exposed in
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



def _is_fuse_reports(reports):
    return bool(
        reports
        and str(reports[0].get("report_type", "")).upper() == "FUSE"
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




def _failure_csv_spec(reports, language="zh_CN"):
    """Return the rows/columns used by the extra red-FAIL CSV.

    The filter intentionally mirrors the HTML report color rule: only rows
    that render with the red ``fail`` CSS class are exported.  This includes
    legacy hard-error statuses such as RMU_LINK, because those rows are red in
    the report even though their literal status text is not FAIL.
    """
    language = normalize_language(language)
    english = language == "en_US"

    def is_red(row, status_field):
        # Keep this in sync with _table_html().  CREATE_PENDING is the only
        # severity value that overrides the normal status color there.
        semantic_status = str(row.get("severity", "") or "")
        effective_status = (
            semantic_status
            if semantic_status == "CREATE_PENDING"
            else str(row.get(status_field, "") or "")
        )
        return status_cls(effective_status) == "fail"

    def unique_fields(*groups):
        result = []
        seen = set()
        for group in groups:
            for field in group:
                if field not in seen:
                    seen.add(field)
                    result.append(field)
        return result

    def tagged(rows, section, status_field="status"):
        exported = []
        for row in rows:
            if not is_red(row, status_field):
                continue
            item = dict(row)
            item["report_section"] = section
            exported.append(item)
        return exported

    section_label = "Report Section" if english else "报告分类"

    if _is_pole_reports(reports):
        rows = tagged(
            flatten_pole_rows(reports),
            "Pole Switch Details" if english else "柱上开关明细",
        )
        return rows, ["report_section"] + POLE_FIELDS, {
            "report_section": section_label,
            **(POLE_LABELS_EN if english else POLE_LABELS),
        }

    if _is_transformer_reports(reports):
        rows = tagged(
            flatten_transformer_rows(reports),
            "Pole Transformer Details" if english else "柱上变压器明细",
        )
        return rows, ["report_section"] + TRANSFORMER_FIELDS, {
            "report_section": section_label,
            **(TRANSFORMER_LABELS_EN if english else TRANSFORMER_LABELS),
        }

    if _is_fuse_reports(reports):
        rows = tagged(
            flatten_fuse_rows(reports),
            "Fuse Details" if english else "熔断器明细",
        )
        return rows, ["report_section"] + FUSE_FIELDS, {
            "report_section": section_label,
            **(FUSE_LABELS_EN if english else FUSE_LABELS),
        }

    if _is_master_station_reports(reports):
        rows = tagged(
            flatten_master_station_rows(reports),
            "Master Station Device Details" if english else "配网主站设备明细",
        )
        return rows, ["report_section"] + MASTER_STATION_FIELDS, {
            "report_section": section_label,
            **(MASTER_STATION_LABELS_EN if english else MASTER_STATION_LABELS),
        }

    if _is_feeder_reports(reports):
        feeder_rows = tagged(
            flatten_feeder_rows(reports),
            "Feeder Summary" if english else "馈线汇总",
        )
        section_rows = tagged(
            flatten_feedline_rows(reports),
            "Feeder Section Details" if english else "馈线段明细",
        )
        fields = ["report_section"] + unique_fields(FEEDER_FIELDS, FEEDLINE_FIELDS)
        labels = {
            "report_section": section_label,
            **(FEEDER_LABELS_EN if english else FEEDER_LABELS),
            **(FEEDLINE_LABELS_EN if english else FEEDLINE_LABELS),
        }
        return feeder_rows + section_rows, fields, labels

    # RMU is the default report family.  Red rows may come from either the
    # RMU summary or the child-device detail table, so the extra CSV carries a
    # report-section column and the union of both original report columns.
    rmu_rows = tagged(
        flatten_rmu_rows(reports),
        "RMU Summary" if english else "环网柜汇总",
        status_field="rmu_status",
    )
    device_rows = tagged(
        flatten_device_rows(reports),
        "Device Details" if english else "设备明细",
    )
    device_fields = ["file_name"] + DEVICE_FIELDS
    fields = ["report_section"] + unique_fields(RMU_FIELDS, device_fields)
    labels = {
        "report_section": section_label,
        **(RMU_LABELS_EN if english else RMU_LABELS),
        **(DEVICE_LABELS_EN if english else DEVICE_LABELS),
    }
    return rmu_rows + device_rows, fields, labels


def _csv_language_tag(language):
    return "EN" if normalize_language(language) == "en_US" else "CN"


def _tagged_csv_name(name, language):
    """Append the explicit CN/EN marker before the .csv suffix."""
    path = Path(name)
    tag = _csv_language_tag(language)
    if path.suffix.lower() == ".csv":
        return path.with_name(f"{path.stem}_{tag}{path.suffix}")
    return path.with_name(f"{path.name}_{tag}.csv")


def _write_failure_csv(reports, base, language="zh_CN", *, tagged=False):
    """Create the extra red-FAIL CSV for one requested language.

    ``tagged=True`` is used by the model workspace bilingual export contract so
    Chinese and English files can coexist in the same report directory.
    """
    base = Path(base)
    language = normalize_language(language)
    english = language == "en_US"
    failure_path = base.with_name(
        base.name + ("_association_failures.csv" if english else "_关联失败.csv")
    )
    if tagged:
        failure_path = _tagged_csv_name(failure_path, language)
    rows, fields, labels = _failure_csv_spec(reports, language=language)
    _write_csv(
        failure_path,
        rows,
        fields,
        labels,
        language=language,
    )
    return failure_path


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
        _write_failure_csv(reports, output_dir / "report", language="zh_CN")
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
        _write_failure_csv(reports, output_dir / "report", language="zh_CN")
        html_path = output_dir / "index.html"
        export_html_bundle(reports, html_path, domain_rules)
        return html_path

    if _is_fuse_reports(reports):
        _write_csv(
            output_dir / "fuse_details.csv",
            flatten_fuse_rows(reports),
            FUSE_FIELDS,
            FUSE_LABELS,
        )
        (output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        _write_failure_csv(reports, output_dir / "report", language="zh_CN")
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
        _write_failure_csv(reports, output_dir / "report", language="zh_CN")
        html_path = output_dir / "index.html"
        export_html_bundle(reports, html_path, domain_rules)
        return html_path

    if _is_feeder_reports(reports):
        _write_csv(
            output_dir / "feeder_summary.csv",
            flatten_feeder_rows(reports),
            FEEDER_FIELDS,
            FEEDER_LABELS,
        )
        _write_csv(
            output_dir / "feeder_section_details.csv",
            flatten_feedline_rows(reports),
            FEEDLINE_FIELDS,
            FEEDLINE_LABELS,
        )
        (output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        _write_failure_csv(reports, output_dir / "report", language="zh_CN")
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

    _write_failure_csv(reports, output_dir / "report", language="zh_CN")
    html_path = output_dir/"index.html"
    export_html_bundle(reports, html_path, domain_rules)
    return html_path



def _export_csv_bundle_one_language(reports, export_path, language="zh_CN", *, tagged=True):
    """Write one language variant and return the paths for that variant only."""
    export_path = Path(export_path)
    base = (
        export_path.with_suffix("")
        if export_path.suffix.lower() == ".csv"
        else export_path
    )

    language = normalize_language(language)
    english = language == "en_US"

    def out_path(suffix):
        path = base.with_name(base.name + suffix)
        return _tagged_csv_name(path, language) if tagged else path

    if _is_pole_reports(reports):
        pole_path = out_path(
            "_pole_switch_details.csv" if english else "_柱上开关明细.csv"
        )
        _write_csv(
            pole_path,
            flatten_pole_rows(reports),
            POLE_FIELDS,
            POLE_LABELS_EN if english else POLE_LABELS,
            language=language,
        )
        failure_path = _write_failure_csv(
            reports, base, language=language, tagged=tagged
        )
        return [pole_path, failure_path]

    if _is_transformer_reports(reports):
        transformer_path = out_path(
            "_transformer_details.csv" if english else "_柱上变压器明细.csv"
        )
        _write_csv(
            transformer_path,
            flatten_transformer_rows(reports),
            TRANSFORMER_FIELDS,
            TRANSFORMER_LABELS_EN if english else TRANSFORMER_LABELS,
            language=language,
        )
        failure_path = _write_failure_csv(
            reports, base, language=language, tagged=tagged
        )
        return [transformer_path, failure_path]

    if _is_fuse_reports(reports):
        fuse_path = out_path(
            "_fuse_details.csv" if english else "_熔断器明细.csv"
        )
        _write_csv(
            fuse_path,
            flatten_fuse_rows(reports),
            FUSE_FIELDS,
            FUSE_LABELS_EN if english else FUSE_LABELS,
            language=language,
        )
        failure_path = _write_failure_csv(
            reports, base, language=language, tagged=tagged
        )
        return [fuse_path, failure_path]

    if _is_master_station_reports(reports):
        master_path = out_path(
            "_master_station_details.csv" if english else "_配网主站设备明细.csv"
        )
        _write_csv(
            master_path,
            flatten_master_station_rows(reports),
            MASTER_STATION_FIELDS,
            MASTER_STATION_LABELS_EN if english else MASTER_STATION_LABELS,
            language=language,
        )
        failure_path = _write_failure_csv(
            reports, base, language=language, tagged=tagged
        )
        return [master_path, failure_path]

    if _is_feeder_reports(reports):
        feeder_path = out_path(
            "_feeder_summary.csv" if english else "_馈线汇总.csv"
        )
        section_path = out_path(
            "_feeder_section_details.csv" if english else "_馈线段明细.csv"
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
        failure_path = _write_failure_csv(
            reports, base, language=language, tagged=tagged
        )
        return [feeder_path, section_path, failure_path]

    rmu_path = out_path(
        "_rmu_summary.csv" if english else "_环网柜汇总.csv"
    )
    dev_path = out_path(
        "_device_details.csv" if english else "_设备明细.csv"
    )

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

    failure_path = _write_failure_csv(
        reports, base, language=language, tagged=tagged
    )
    return [rmu_path, dev_path, failure_path]


def export_csv_bundle(reports, export_path, language="zh_CN"):
    """Export model-workspace CSV reports.

    Chinese UI is a bilingual-delivery mode: every CSV is emitted twice from
    the exact same report rows, once with Chinese headers/text (``*_CN.csv``)
    and once with English headers/text (``*_EN.csv``).  The returned list is
    the current-UI-language set so existing buttons/history continue to open a
    single primary copy.  English UI continues to emit the English set only.
    """
    language = normalize_language(language)
    if language == "zh_CN":
        cn_paths = _export_csv_bundle_one_language(
            reports, export_path, language="zh_CN", tagged=True
        )
        _export_csv_bundle_one_language(
            reports, export_path, language="en_US", tagged=True
        )
        return cn_paths
    return _export_csv_bundle_one_language(
        reports, export_path, language="en_US", tagged=True
    )

def _selected_row_css():
    """Shared visual treatment for manually checked report rows."""
    return """
tr.row-selected > td {
  background:#DCEEFF !important;
  border-top:2px solid #1976D2 !important;
  border-bottom:2px solid #1976D2 !important;
  font-weight:600;
}
tr.row-selected > td:first-child { border-left:2px solid #1976D2 !important; }
tr.row-selected > td:last-child { border-right:2px solid #1976D2 !important; }
"""


def _table_interaction_script(language="zh_CN"):
    """Shared client-side behavior for report table text/color filters and row selection."""
    english = normalize_language(language) == "en_US"
    script = """<script>
function toggleSelectedRow(cb) {
  const row = cb.closest('tr');
  if (!row) return;
  row.classList.toggle('row-selected', cb.checked);
}

function getReportRowColor(row) {
  if (row.classList.contains('pass')) return 'green';
  if (row.classList.contains('warn')) return 'yellow';
  if (row.classList.contains('relink') || row.classList.contains('create')) return 'orange';
  if (row.classList.contains('rmu-relink')) return 'purple';
  if (row.classList.contains('blocked') || row.classList.contains('info')) return 'blue';
  if (row.classList.contains('fail')) return 'red';
  return '';
}

function filterReportTable(tableId) {
  const table = document.getElementById(tableId);
  if (!table || !table.tBodies || !table.tBodies.length) return;
  const textInput = document.getElementById(tableId + '-text-filter');
  const colorSelect = document.getElementById(tableId + '-color-filter');
  const query = String(textInput ? textInput.value : '').trim().toLocaleUpperCase();
  const color = String(colorSelect ? colorSelect.value : 'all');
  const rows = Array.from(table.tBodies[0].rows);
  let visible = 0;
  for (const row of rows) {
    const haystack = String(row.textContent || '').toLocaleUpperCase();
    const textMatched = !query || haystack.includes(query);
    const rowColor = getReportRowColor(row);
    const colorMatched = color === 'all' || rowColor === color;
    const matched = textMatched && colorMatched;
    row.style.display = matched ? '' : 'none';
    if (matched) visible += 1;
  }
  const counter = document.getElementById(tableId + '-count');
  if (counter) {
    const filtered = Boolean(query) || color !== 'all';
    counter.textContent = filtered
      ? (__IS_ENGLISH__ ? ('Matched ' + visible + ' / ' + rows.length + ' rows') : ('匹配 ' + visible + ' / ' + rows.length + ' 行'))
      : (__IS_ENGLISH__ ? (rows.length + ' rows') : ('共 ' + rows.length + ' 行'));
  }
}
</script>"""
    return script.replace("__IS_ENGLISH__", "true" if english else "false")


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
            "环网柜名称只使用完整位于 RMU 图框外、且在图框正上方的 Text；Text 框与任意 RMU 框重叠即排除；不允许右侧、左侧、下方或全局兜底，上方找不到名称即识别失败；RMU 矩形框与 Text 矩形框最小边缘距离必须不超过 200；"
            "所有图都先按 G 文件名 → 405/substation → 13500/dms_feeder_device 唯一确定图级馈线，再只在该 FEEDER_ID 下选择同名环网柜；数据库其它馈线上的同名记录不会参与关联。"
            "如果当前馈线下没有同名环网柜，或当前馈线下仍有多条同名记录，则禁止关联；同一 G 图内环网柜名称重复时仍按原规则阻断。"
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
            "The RMU summary follows the RMU sequence in each G file. Each RMU is shown once with type, smart markers, database uniqueness, device completeness, and association status. RMU-name distance uses rectangle minimum-edge distance; only Text within 200 is eligible. Every drawing resolves its feeder only from the strict G filename through 405/substation and 13500/dms_feeder_device. Same-name RMUs are then filtered by that FEEDER_ID. No matching RMU on the current feeder, or more than one matching RMU on that feeder, blocks association. Duplicate graphical RMU names in one G file remain blocked."
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
        "所有图中，文件名确定的图级 FEEDER_ID 都是环网柜和柜内设备的硬关联条件：RMU 必须属于该馈线，柜内设备必须同时属于当前 RMU 且属于该馈线；facID 不参与馈线判定。"
    )
    if english:
        source_note = (
            "Field sources: Frame XML ID, G-object XML ID, and current G-file KeyID come from the G file; "
            "RMU ID, device ID, CODE, NAME, BV_ID, and owning RMU ID come from the database; "
            "table/domain values come from database definitions; Expected KeyID is calculated from device ID + domain and then verified by the database function. "
            "On every drawing, the filename-resolved graph FEEDER_ID is a hard association condition: the RMU must belong to that feeder, and child devices must belong to both that RMU and the same feeder; facID never selects the feeder."
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
    feeder_overview = _rmu_feeder_overview(reports, english=english)

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
{_selected_row_css()}
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

  {feeder_overview}

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
    scope_overview = _jeddah_scope_overview(reports, english=english)
    feeder_resolution_overview = _feeder_resolution_card(
        reports,
        english=english,
        title=("Feeder Identification" if english else "馈线判定"),
    )

    feeder_rule_intro = (
        "Feeder resolution uses the G filename as the only authoritative source: JED-<3-letter AREA>-<STATION>-<NN> or JED-<3-letter AREA>-<STATION>-AG<NN> -> exact 405/substation.NAME -> NN builds AH3<NN>, AG<NN> builds AG4<NN> -> exact 13500/dms_feeder_device ST_ID + NAME. RMU, Pole Switch, Pole Transformer, G-root facID, source-CBreaker text and manual input never select or override the feeder. All devices must belong to the resolved FEEDER_ID. If the feeder does not exist in 13500, association is blocked and the operator is asked to verify that the drawing feeder has been created. The only database write allowed is INSERT into 13503 / dms_section_device, using model Domain 1."
        if english else
        "馈线识别规则：G 文件名是唯一馈线来源。文件名支持 JED-<三位区域代码>-<站名>-<两位馈线号> 和 JED-<三位区域代码>-<站名>-AG<两位馈线号>；先用站名精确查询 405/substation.NAME，普通 NN 拼接 AH3+NN，AGNN 则插入 4 转成 AG4NN，并按 13500/dms_feeder_device.ST_ID=站ID 且 NAME=目标名精确唯一确认。环网柜、柱上开关、柱上变压器、G 根 facID、源侧 CBreaker 和人工输入均不再参与馈线判定。所有设备只能关联到该 FEEDER_ID 下；13500 中不存在该馈线时直接阻断，并提示检查该图的馈线是否已创建。唯一允许写入的数据库表是 13503 / dms_section_device，模型域号为 1。"
    )
    feeder_status_desc = {
        "pass": "The FeedLine is already linked to a database section under this feeder with the correct table ID and Domain." if english else "当前 FeedLine 已经关联到本馈线下的数据库馈线段，表号/域号均正确。",
        "warn": "The FeedLine is unlinked but has been assigned to an existing available section under this feeder and can be associated directly." if english else "当前 FeedLine 尚未关联，但已经分配到本馈线下已有的可用数据库馈线段，可以在工作区勾选后直接执行模型关联。",
        "create": "There are not enough available 13503 sections under this feeder. A new dms_section_device record must be created before generating the KeyID and associating this FeedLine." if english else "当前馈线数据库中没有足够的可用 13503 馈线段；该 FeedLine 需要先单独创建新的 dms_section_device 记录，再生成正确 KeyID 并完成关联。",
        "fail": "The G filename cannot uniquely resolve a valid feeder through 405/substation and 13500/dms_feeder_device, or another hard error prevents safe association." if english else "G 文件名无法通过 405/substation 与 13500/dms_feeder_device 唯一确定有效馈线，或存在其它硬错误。",
    }
    feeder_summary_intro = (
        "The drawing feeder is resolved only from the G filename through exact 405/substation.NAME and exact 13500 ST_ID + NAME, using AH3NN for an NN token and AG4NN for an AGNN token. Graphical devices never choose the feeder. If the filename/database path cannot determine one feeder, the result is FAIL and no section is created or associated."
        if english else
        "图级馈线只按 G 文件名识别：普通 NN 格式 → 405.NAME 精确找站 → AH3+NN；新增 AGNN 格式 → 405.NAME 精确找站 → AG4NN；最后均用 13500.ST_ID+NAME 精确确认。图中设备不参与馈线判定；文件名或数据库无法确认唯一馈线时直接 FAIL，不创建馈线段，也不执行 FeedLine 关联。"
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
{_selected_row_css()}
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

  {feeder_resolution_overview}

  <div class="card">
    <h2>{("Feeder Summary" if english else "馈线汇总")}</h2>
    <p>{esc(feeder_summary_intro)}</p>
    {feeder_table}
  </div>

  {scope_overview}

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


def _pole_reason_for_report(value, english=False):
    """Convert internal pole-switch diagnostics into short operator text."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    code, sep, detail = raw.partition(":")
    code = code.strip()
    detail = detail.strip() if sep else raw
    if english:
        return detail or raw

    graph_match = re.search(r"图级\s*FEEDER_ID[=：]([^；,.。\s]+)|图级馈线\s*([^；,.。\s]+)", detail, flags=re.IGNORECASE)
    graph_feeder = next((item for item in (graph_match.groups() if graph_match else ()) if item), "")
    target_match = re.search(r"目标设备\s*FEEDER_ID=([^；,.。\s]+)", detail, flags=re.IGNORECASE)
    target_feeder = target_match.group(1) if target_match else ""

    if code == "POLE_SWITCH_NAME_NOT_FOUND":
        return "图上没有找到符合规则的柱上开关名称：名称文字必须有明确颜色且不能是白色；设备矩形框与 Text 矩形框的最小边缘距离必须不超过 200，并按上方 → 右方 → 其他方向查找。"
    if code == "POLE_SWITCH_COMBINED_NAME_NOT_UNIQUE":
        # The internal detail already contains both the original graphical
        # name and the normalized database lookup value. Keep those facts but
        # remove the diagnostic-code style wording.
        m = re.search(r"图上名称=([^；]+)；数据库查询名称=([^；]+)；.*?匹配到\s*(\d+)\s*条", detail)
        if m:
            return f"图上名称是 {m.group(1)}；查询数据库时使用 {m.group(2)}。13501 查到 {m.group(3)} 条记录，不能唯一确定设备，因此不自动关联。"
        return "数据库 13501 中没有唯一找到这台柱上开关，因此不自动关联。"
    if code == "POLE_SWITCH_COMBINED_ID_INVALID":
        return "已经找到 13501 记录，但记录 ID 无效，因此不自动关联。"
    if code == "POLE_SWITCH_CB_NOT_UNIQUE":
        m = re.search(r"父设备记录数=(\d+).*?筛选后=(\d+)", detail)
        if m:
            return f"13501 已找到，但对应的 13502 记录无法唯一确定（共 {m.group(1)} 条，按设备族筛选后 {m.group(2)} 条），因此不自动关联。"
        return "13501 已找到，但对应的 13502 柱上开关记录无法唯一确定，因此不自动关联。"
    if code == "POLE_SWITCH_DEVICE_ID_INVALID":
        return "已经找到 13502 记录，但设备 ID 无效，因此不自动关联。"
    if code == "POLE_SWITCH_CB_COMBINED_ID_MISMATCH":
        return "13502 记录与前面找到的 13501 不是同一台设备，因此禁止自动关联。"
    if code == "POLE_SWITCH_FEEDER_ID_EMPTY":
        suffix = f"（当前图纸馈线：{graph_feeder}）" if graph_feeder else ""
        return f"数据库里没有完整的馈线归属信息，无法确认这台柱上开关是否属于当前图纸馈线{suffix}，因此不自动关联。"
    if code == "POLE_SWITCH_FEEDER_MISMATCH":
        if target_feeder and graph_feeder:
            return f"馈线归属不一致：数据库设备属于 {target_feeder}，当前图纸属于 {graph_feeder}，因此禁止自动关联。"
        return "数据库设备的馈线归属与当前图纸不一致，因此禁止自动关联。"
    if code == "POLE_SWITCH_13501_13502_FEEDER_MISMATCH":
        return "数据库中的 13501 与 13502 记录属于不同馈线，设备关系不一致，因此禁止自动关联。"
    if code == "POLE_SWITCH_BV_ID_EMPTY":
        return "数据库目标缺少 BV_ID，无法生成安全的回写数据，因此不自动关联。"
    if code == "POLE_SWITCH_EXPECTED_KEYID_VERIFY_FAILED":
        return "程序计算出的目标 KeyID 无法通过数据库校验，因此不自动关联。"
    if code == "POLE_SWITCH_MODEL_LINK_CORRECT":
        return "当前柱上开关已经关联正确，无需处理。"
    if code == "POLE_SWITCH_ASSOCIATION_READY":
        return "图上名称、数据库设备和馈线归属都已唯一确认，可以执行关联。"
    return detail or raw


def _export_pole_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    language = normalize_language(language)
    english = language == "en_US"
    rows = flatten_pole_rows(reports)
    display_rows = []
    for source_row in rows:
        display_row = dict(source_row)
        display_row["reason"] = _pole_reason_for_report(
            source_row.get("reason", ""),
            english=english,
        )
        display_rows.append(display_row)
    labels = POLE_LABELS_EN if english else POLE_LABELS
    title = "Pole Switch Model Report" if english else "柱上开关模型报告"
    intro = (
        "Pole-switch identity is determined only by the LBS, SEC, or AR classification in Element Management; the concrete G XML tag is unrestricted. "
        "Graphical name detection scans Text across the whole drawing. A candidate must have an explicit color and must not be white; the exact shade is not restricted. Distance is the minimum edge-to-edge distance between the device rectangle and Text rectangle and is limited to 200; TOP -> RIGHT -> GLOBAL priority and one-to-one Text ownership remain unchanged. Center-point distance is not used. The graphical name is preserved exactly. Before the 13501 lookup, ordinary names still remove dots, hyphens, and spaces (for example SEC-2385 -> SEC2385). However, for an AR/LBS/SEC-classified device, an exact compound business name in the form family+digits-digits (for example LBS96527-21240) keeps the embedded hyphen and is queried as drawn. 13501/13502, feeder ownership, KeyID, and write-back rules are unchanged."
        if english
        else
        "本报告只按图元管理中的 LBS/SEC/AR 分类标记识别柱上开关，不限制 G XML 元素类型；只要图元 devref 对应这些分类之一，就进入本模块。"
        "第一步只负责找图上名称：从整张 G 图查找 Text，候选文字必须明确设置颜色且不能是白色，不再限制具体颜色深浅；设备矩形框与 Text 矩形框按最小边缘距离计算且不超过 200，不再使用中心点距离；优先上方，其次右方，最后其他方向，同一 Text 只给一个设备；"
        "第二步才查询数据库：图上名称始终原样保留。普通名称在查询 13501 前临时删除点号、横杠和空格，例如 SEC-2385、SEC 2385、SEC.2385 都用 SEC2385 查询；但若设备分类为 AR/LBS/SEC，且名称严格符合“设备族+数字-数字”的复合业务格式，例如 LBS96527-21240、LBS33513-97376，则保留中间横杠，直接按原名查询。"
        "后面的 13501/13502、馈线归属、KeyID 和回写规则不变。"
    )
    domain_rows = (
        "<tr><td>LBS/SEC/AR classified element</td><td>13502</td><td>40</td></tr>"
        if english
        else "<tr><td>LBS/SEC/AR 分类图元（XML 类型不限）</td><td>13502</td><td>40</td></tr>"
    )
    table = _table_html(
        display_rows,
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
    feeder_overview = _pole_switch_feeder_result(reports, english=english)
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
{_selected_row_css()}
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
{feeder_overview}
<div class="card"><h2>{'Pole Switch Details' if english else '柱上开关明细'}</h2>{table}</div>
</main>
{_table_interaction_script(language)}
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
        "Pole-transformer recognition uses two levels: an object whose devref points exactly to Transformer_OH.pb.icn.g is accepted first without requiring an Element Management classification; for other element files, TRANSFORMER_OH classification is the fallback. The concrete G XML tag itself is not used as a device-type filter. "
        "Name candidates are collected globally but must be pure numeric, white, and have no background. Direction priority is TOP -> RIGHT -> GLOBAL fallback; within the same tier, the nearest candidate wins and Text ownership remains one-to-one. The maximum distance is 300. Distance is the minimum edge-to-edge distance between the classified transformer rectangle and the Text rectangle; direction is based on rectangle placement. Center-point and Text-anchor distance are not used. Before association, the drawing feeder is resolved only from the strict G filename through 405/substation and 13500/dms_feeder_device; each transformer must have a unique 13505 record whose FEEDER_ID equals that filename-resolved feeder."
        if english
        else
        "本报告按两级规则识别柱上变压器：devref 精确指向 Transformer_OH.pb.icn.g 的标准图元优先直接识别，不依赖图元管理分类；其它图元再以 TRANSFORMER_OH 分类标记作为兜底。XML 元素标签本身不作为设备类型过滤条件。"
        "先全局收集纯数字、白色、无背景 Text；名称方向按 上方 → 右方 → 全局兜底 的优先级分配，同一优先级内按距离最近，Text 仍保持一对一且最大距离 300；距离按被标记柱上变压器矩形框与 Text 矩形框的最小边缘距离计算，方向按两个矩形的相对位置判断；不再使用中心点距离或 Text 锚点距离；关联前只按 G 文件名 → 405/substation → 13500/dms_feeder_device 精确确定图级馈线，"
        "然后强制校验柱上变压器唯一 13505 记录的 FEEDER_ID 等于图级 FEEDER_ID。"
    )
    domain_rows = "<tr><td>Transformer_OH.pb.icn.g（优先） / TRANSFORMER_OH（分类兜底）</td><td>13505</td><td>1</td></tr>"
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
    feeder_result = _compact_transformer_feeder_result(reports, english=english)
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
{_selected_row_css()}
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
{feeder_result}
<div class="card"><h2>{'Pole Transformer Details' if english else '柱上变压器明细'}</h2>{table}</div>
</main>
{_table_interaction_script(language)}
</body></html>"""
    export_path.write_text(text, encoding="utf-8")
    return export_path



def _export_fuse_html_bundle(reports, export_path, domain_rules, language="zh_CN"):
    export_path = Path(export_path)
    language = normalize_language(language)
    english = language == "en_US"
    rows = flatten_fuse_rows(reports)
    labels = FUSE_LABELS_EN if english else FUSE_LABELS
    title = "Fuse Model Report" if english else "熔断器模型报告"
    intro = (
        "Only graphic objects classified FUSE in Element Management are counted. Each FUSE nominates only its single nearest Transformer_OH. A transformer can be owned by only one FUSE; if several FUSE objects nominate the same transformer, the closest FUSE wins and the others remain statistics-only without falling back to another transformer. After the nearest transformer is fixed, its name follows the Jeddah pole-transformer rule: scan the whole drawing for pure-numeric, white, no-background Text within 300 units, prioritize TOP, then RIGHT, then GLOBAL fallback, and use rectangle placement for direction plus minimum rectangle edge-to-edge distance for same-tier ranking. The selected graphical name must be unique in 13505. NAME is then derived as FUSE + transformer name and queried in 13513 / dms_disconnector_device by NAME + drawing FEEDER_ID with Domain 40."
        if english else
        "本报告统计图元管理中分类为 FUSE 的全部图元。每个 FUSE 只提名几何位置最近的 Transformer_OH；同一柱上变压器只能被一个 FUSE 使用，多个 FUSE 指向同一变压器时由距离更近者获得，其他 FUSE 仅统计、不关联，也不会改找第二近变压器。锁定最近柱上变压器后，名称完全沿用吉达柱上变压器规则：全图只使用纯数字、白色、无背景 Text，距离不超过 300，方向优先级严格为上方 → 右方 → 全局兜底；方向按柱上变压器矩形框与 Text 矩形框的相对位置判断，同级距离按两矩形最小边缘距离计算，不再使用中心点距离；图形选中的名称必须在 13505 唯一。随后生成 NAME=FUSE+变压器名称，并按 NAME + 图级 FEEDER_ID 查询 13513 / dms_disconnector_device，Domain 固定为 40。"
    )
    table = _table_html(
        rows,
        FUSE_FIELDS,
        labels,
        "status",
        selectable=True,
        table_id="fuse-table",
        filter_placeholder=(
            "Enter fuse name, transformer name, feeder ID, or XML ID"
            if english else
            "输入熔断器名称、柱上变压器名称、馈线ID或XML ID"
        ),
        language=language,
    )
    feeder_result = _feeder_resolution_card(
        reports,
        english=english,
        title=("Fuse Feeder Resolution" if english else "熔断器馈线判定"),
    )
    total_fuse = sum(int((report.get("summary") or {}).get("fuse_count") or 0) for report in reports)
    matched_fuse = sum(int((report.get("summary") or {}).get("fuse_transformer_matched") or 0) for report in reports)
    unmatched_fuse = sum(int((report.get("summary") or {}).get("fuse_transformer_unmatched") or 0) for report in reports)
    ready_fuse = sum(int((report.get("summary") or {}).get("association_ready_count") or 0) for report in reports)
    summary_card = (
        f"<div class='card'><h2>{'Fuse / Transformer Assignment Summary' if english else '熔断器与柱上变压器分配统计'}</h2>"
        f"<table><thead><tr><th>{'Total FUSE' if english else 'FUSE总数'}</th>"
        f"<th>{'Assigned one-to-one' if english else '已独占匹配柱上变压器'}</th>"
        f"<th>{'Statistics only' if english else '仅统计不处理'}</th>"
        f"<th>{'Database-ready' if english else '数据库可关联'}</th></tr></thead>"
        f"<tbody><tr><td>{total_fuse}</td><td>{matched_fuse}</td><td>{unmatched_fuse}</td><td>{ready_fuse}</td></tr></tbody></table>"
        f"<p>{'Unassigned FUSE rows remain in the detail table for statistics, but they cannot be selected or written back.' if english else '未分配到独占柱上变压器的 FUSE 仍保留在明细和统计中，但不会进入关联选择，也不会执行任何回写。'}</p></div>"
    )
    domain_rows = "<tr><td>FUSE classification</td><td>13513</td><td>40</td><td>dms_disconnector_device</td></tr>"
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
.relink{{background:#FFE8CC}} .blocked{{background:#EAF3FF}} .fail{{background:#FFF0F0}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px;flex-wrap:wrap}}
.table-filter-input{{width:min(560px,70vw);padding:8px 11px;border:1px solid #D3E3DC;border-radius:6px}}
{_selected_row_css()}
</style></head><body>
<header><h1>{esc(title)}</h1><div>{esc(APP_NAME if not english else APP_NAME_EN)}　v{esc(APP_VERSION)}</div></header>
<main>
<div class="card"><h2>{'Association Rules' if english else '关联规则'}</h2><p>{esc(intro)}</p>
<table><thead><tr><th>{'Recognition' if english else '识别对象'}</th><th>{'Table ID' if english else '表号'}</th><th>{'Domain' if english else '域号'}</th><th>{'Database Table' if english else '数据库表'}</th></tr></thead><tbody>{domain_rows}</tbody></table></div>
{summary_card}
{feeder_result}
<div class="card"><h2>{'Fuse Details' if english else '熔断器明细'}</h2>{table}</div>
</main>{_table_interaction_script(language)}</body></html>"""
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
        "Only the configured CBreaker, Disconnector, and GroundDisconnector G objects are processed. "
        "Bus is intentionally excluded as an association target. The target device is resolved by BAY_ID from the database context; G-file CODE/NAME is not parsed. "
        "When multiple disconnectors share one BAY_ID, the two Bus-side objects are ordered left-to-right, followed by the remaining object."
        if english else
        "本报告只处理配置中的 CBreaker、Disconnector、GroundDisconnector 图元，Bus 不作为关联对象，仅用于多个隔离开关的 Bus 侧定位。"
        "主站设备不再解析 G 文件 CODE/NAME，直接使用关联上下文中的 BAY_ID 查询数据库；多个隔离开关时，按 Bus 侧从左到右匹配前两个，剩余对象匹配剩余记录。"
    )
    source_note = (
        "字段来源说明：G 文件名、图元类型、XML ID、key_name 和当前 KeyID 来自 G 文件；"
        "BAY_ID、目标设备 ID、CODE、NAME、BV_ID 来自数据库；目标表号和域号来自本模块配置/数据库定义；"
        "期望 KeyID 由程序按设备 ID + 域号计算并通过数据库函数校验。回写只修改 G 图元中已有属性。"
        if not english else
        "Field sources: file name, object type, XML ID, key_name, and current KeyID come from the G file; "
        "BAY_ID, target ID, CODE, NAME, and BV_ID come from the database; table/domain come from module configuration/database definition; "
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
        filter_placeholder=("Enter BAY_ID, object type, or XML ID" if english else "输入 BAY_ID、图元类型或 XML ID"),
        language=language,
    )
    context = (reports[0].get("association_context", {}) if reports else {}) or {}
    feeder_context_title = "图级厂站 / 馈线判定" if not english else "Graph Station / Feeder Resolution"
    feeder_context_rows = "".join(
        f"<tr><th>{esc(label)}</th><td>{esc(value or '-')}</td></tr>"
        for label, value in (
            (("判定依据" if not english else "Anchor"), _friendly_feeder_anchor(context.get("feeder_anchor", ""), _feeder_resolution_kind(context.get("feeder_resolution_source", "")), english=english) or ("No unique anchor" if english else "未找到唯一判定设备")),
            (("判定过程" if not english else "Resolution Method"), _feeder_resolution_method(context.get("feeder_resolution_source", ""), english=english)),
            (("馈线定位" if not english else "Feeder Location"), context.get("location_label", "") or context.get("feeder_path", "")),
            (("G根节点 facID" if not english else "G root facID"), context.get("graph_facid", "")),
            (("facID校验" if not english else "facID Check"), context.get("facid_check", "")),
            (("FEEDER_ID" if not english else "FEEDER_ID"), context.get("feeder_id", "")),
            (("BAY_ID" if not english else "BAY_ID"), context.get("bay_id", "")),
            (("处理结果" if not english else "Result"), context.get("message", "")),
        )
    )
    feeder_context_card = (
        f"<div class=\"card\"><h2>{esc(feeder_context_title)}</h2>"
        f"<table class=\"context-table\"><tbody>{feeder_context_rows}</tbody></table></div>"
    )
    scope_overview = _jeddah_scope_overview(reports, english=english)
    text = f"""<!doctype html>
<html lang="{'en' if english else 'zh-CN'}"><head><meta charset="utf-8">
<title>{esc(title)}</title>
<style>
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:#17372E}}
header{{background:#006B52;color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}} .card{{background:white;border:1px solid #D3E3DC;border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th{{background:#006B52;color:white;position:sticky;top:0}}
th,td{{border:1px solid #D3E3DC;padding:6px 8px;text-align:left;white-space:nowrap}}
.context-table{{width:min(1100px,100%);font-size:13px}} .context-table th{{width:190px;position:static;background:#EAF8F2;color:#17372E}}
.scroll{{overflow:auto;max-height:700px}} .pass{{background:#EAF8F2}} .warn{{background:#FFF8DE}}
.relink{{background:#FFE8CC}} .fail{{background:#FFF0F0}} .blocked{{background:#EAF3FF}}
.table-filter{{display:flex;align-items:center;gap:10px;margin:10px 0 12px;flex-wrap:wrap}}
.table-filter-input{{width:min(560px,70vw);padding:8px 11px;border:1px solid #D3E3DC;border-radius:6px}}
{_selected_row_css()}
</style></head><body><header><h1>{esc(title)}</h1><div>{esc(APP_NAME if not english else APP_NAME_EN)}　v{esc(APP_VERSION)}</div></header>
<main><div class="card"><h2>{'Association Rules' if english else '关联规则'}</h2><p>{esc(intro)}</p><p><strong>{'Field sources:' if english else '字段来源：'}</strong>{esc(source_note)}</p>
<table><thead><tr><th>{'G Object Type' if english else 'G图元类型'}</th><th>{'Table ID' if english else '表号'}</th><th>{'Domain' if english else '域号'}</th><th>{'Database Table' if english else '数据库表'}</th></tr></thead><tbody>{domain_rows}</tbody></table></div>
{feeder_context_card}
{scope_overview}
<div class="card"><h2>{'Master Station Device Details' if english else '配网主站设备明细'}</h2>{table}</div></main>{_table_interaction_script(language)}</body></html>"""
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
    if _is_fuse_reports(reports):
        return _export_fuse_html_bundle(
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
