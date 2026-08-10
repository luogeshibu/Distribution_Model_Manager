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

DEFAULT_SETTINGS = {
    "model_module": "RMU",
    "operation": "VALIDATE",
    "input_path": "",
    "last_file_path": "",
    "last_folder_path": "",
    "last_run_dir": "",
    "db": DEFAULT_DB_CONFIG,
    "rmu_name_positions": DEFAULT_NAME_POSITIONS,
    "device_rules": {},
    "breaker_name_source": "P_NAME_STRING",
}
