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
        "match_mode": "CODE_EQUALS_LOGICAL_CODE",
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
        "domain": 1,
        "match_mode": "CODE_EQUALS_LOGICAL_CODE",
        "description": "母线",
    },
}

# 配网主站设备关联。Bus 的数据库表号没有在当前需求的 SQL 中明确给出，
# 因此默认保持 0（未配置），避免把母线误写入 breaker/disconnector 表。
DEFAULT_MASTER_STATION_RULES = {
    "Bus": {
        "table_id": 0,
        "domain": 40,
        "table_name": "",
        "description": "主站母线图元（请配置对应数据库表号）",
    },
    "CBreaker": {
        "table_id": 407,
        "domain": 40,
        "table_name": "breaker",
        "description": "主站断路器",
    },
    "Disconnector": {
        "table_id": 408,
        "domain": 40,
        "table_name": "disconnector",
        "description": "主站隔离开关",
    },
    "GroundDisconnector": {
        "table_id": 409,
        "domain": 40,
        "table_name": "grounddisconnector",
        "description": "主站接地开关",
    },
}

DEFAULT_NAME_POSITIONS = {
    "top": True,
    "right": False,
    "left": False,
    "bottom": False,
}

# RMU name direction remains configurable.  The Makkah default is top, while
# operators may enable multiple sides when a drawing family requires it.
RMU_NAME_DIRECTIONS = ("top", "right", "left", "bottom")
DEFAULT_RMU_NAME_DETECTION_MODE = "FIXED"


def resolve_rmu_name_positions(mode="FIXED", configured_positions=None):
    """Return the configured RMU name directions in stable UI order."""
    configured_positions = configured_positions or DEFAULT_NAME_POSITIONS
    selected = [
        position
        for position in RMU_NAME_DIRECTIONS
        if bool(configured_positions.get(position, False))
    ]
    # Older Makkah workspace files may contain the previous all-false value;
    # migrate that state to the current default instead of disabling naming.
    return selected or ["top"]

DEFAULT_RMU_NAME_EXCLUSIONS = [
    "N.O.P",
    "NOP",
    "N-O-P",
    "N_O_P",
    "SFI",
    "DAS/OK",
]

DEFAULT_SETTINGS = {
    "language": "zh_CN",
    "model_module": "RMU",
    "operation": "VALIDATE",
    "input_source": "LOCAL",
    "input_path": "",
    "ssh": {
        "host": "172.16.21.27",
        "port": 22,
        "username": "up8000",
        "password": "up8000",
        "remote_directory": "/home/up8000/data/graph/display/sln",
        "element_directory": "/home/up8000/data/graph/element",
    },
    "element_catalog": {
        "records": [],
    },
    # Name format/color/background settings are hard filters for the global
    # Text-to-device assignment.
    "pole_switch_name_numeric": False,
    "pole_switch_name_format": "ALPHANUMERIC_SPACE",
    "pole_switch_name_colors": ["WHITE"],
    "pole_switch_name_has_background": False,
    "transformer_name_numeric": True,
    "transformer_name_format": "NUMERIC",
    "transformer_name_colors": ["WHITE"],
    "transformer_name_has_background": False,
    "last_file_path": "",
    "last_folder_path": "",
    "last_run_dir": "",
    "db": DEFAULT_DB_CONFIG,
    "rmu_name_positions": DEFAULT_NAME_POSITIONS,
    "rmu_name_detection_mode": DEFAULT_RMU_NAME_DETECTION_MODE,
    "rmu_name_exclusions": DEFAULT_RMU_NAME_EXCLUSIONS,
    "device_rules": {},
    "master_station_rules": {},
    "breaker_name_source": "GRAPHICAL_TEXT",
    "feeder_table_id": 13500,
    "section_table_id": 13503,
    "section_domain": 1,
    "feeder_resolution_mode": "FACID",
    "manual_feeder_name": "",
    "feeder_station_hint": "",
    "allow_feeder_override": False,
    "feeder_drawing_mode": "AUTO",
    "auto_create_missing_sections": True,
}
