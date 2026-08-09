#!/usr/bin/env python3
# -*- coding: utf-8 -*-

APP_NAME = "配网模型管理工具"
APP_NAME_EN = "Distribution Model Manager"
APP_VERSION = "2.8.0"
APP_DESCRIPTION = "配网 G 文件模型校验、模型关联预览及安全回写工具"
APP_EDITION = "团队内部版"

DEFAULT_DB_CONFIG = {
    "user": "d5000",
    "password": "OracleDV1Dec.25",
    "host": "172.16.21.45",
    "port": 1521,
    "service_name": "jedup8000",
}

DEFAULT_DEVICE_RULES = {
    "CBreakerDis": {
        "table_id": 13502,
        "domain": 40,
        "match_mode": "CODE_EQUALS_PNAME",
        "description": "配网开关/断路器",
    },
    "ZhaiWaiJieDiDaoZha": {
        "table_id": 13514,
        "domain": 40,
        "match_mode": "GROUND_FROM_BREAKER",
        "description": "接地刀闸",
    },
    "BusDis": {
        "table_id": 13506,
        "domain": 0,
        "match_mode": "CODE_EQUALS_PNAME",
        "description": "母线",
    },
}

DEFAULT_NAME_POSITIONS = {
    "top": True,
    "right": False,
    "left": False,
    "bottom": False,
}

DEFAULT_LABEL_MAX_DISTANCE = 120.0
DEFAULT_LABEL_OVERLAP_TOLERANCE = 20.0
DEFAULT_LABEL_REGEX = r"^\d+$"
HISTORY_RETENTION_DAYS = 30
