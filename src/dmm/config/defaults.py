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

DEFAULT_NAME_POSITIONS = {
    "top": False,
    "right": False,
    "left": False,
    "bottom": False,
}

# RMU name labels must use the direction explicitly selected by the user.
# Keeping the direction in settings is intentional: different G-file sites
# place cabinet names in different visual bands.
RMU_NAME_DIRECTIONS = ("top", "right", "left", "bottom")
DEFAULT_RMU_NAME_DETECTION_MODE = "FIXED"


def resolve_rmu_name_positions(mode="FIXED", configured_positions=None):
    """Return only the directions explicitly selected by the user."""
    configured_positions = configured_positions or {}
    return [
        position
        for position in RMU_NAME_DIRECTIONS
        if bool(configured_positions.get(position, False))
    ]

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
