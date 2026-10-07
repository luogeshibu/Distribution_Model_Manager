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

# 配网主站设备关联。主网 Bus 使用 410 / busbarsection，Domain=40。
# Bus 只使用主网标题确认出的 ST_ID，不检查 BAY_ID；在该站 410 记录池中
# 任意一对一分配。其它主网设备继续使用已确认的 BAY_ID。
DEFAULT_MASTER_STATION_RULES = {
    "Bus": {
        "table_id": 410,
        "domain": 40,
        "table_name": "busbarsection",
        "description": "主站母线段",
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

# Feeder topology keeps the existing top-side reference behavior. RMU uses a
# separate site-specific default so this setting does not affect feeders.
DEFAULT_RMU_NAME_POSITIONS = {
    "top": False,
    "right": True,
    "left": False,
    "bottom": False,
}

# RMU name direction remains configurable. Makkah drawings default to the
# right-side label, while operators may enable multiple sides when needed.
RMU_NAME_DIRECTIONS = ("top", "right", "left", "bottom")
DEFAULT_RMU_NAME_DETECTION_MODE = "FIXED"


def resolve_rmu_name_positions(mode="FIXED", configured_positions=None):
    """Return the configured RMU name directions in stable UI order."""
    configured_positions = configured_positions or DEFAULT_RMU_NAME_POSITIONS
    selected = [
        position
        for position in RMU_NAME_DIRECTIONS
        if bool(configured_positions.get(position, False))
    ]
    # Older workspace files may contain an all-false value; migrate that state
    # to the Makkah default instead of disabling RMU naming.
    return selected or ["right"]


# Makkah standalone pole-device recognition no longer depends on Element
# Management classifications. Operators maintain exact devref file names here.
# Every file in this list is a pole switch; users do not classify it as
# AR/LBS/SEC. Database association therefore requires exactly one 13502 child
# under the uniquely matched 13501 parent.
DEFAULT_POLE_SWITCH_ELEMENT_FILES = [
    "SEC_S.zwk.icn.g",
    "SEC_NON.zwk.icn.g",
    "SEC_NON_H.zwk.icn.g",
    "AR_NON_H.zwk.icn.g",
]

# Backward-compatibility only for older v4.1.93 settings/tests. New UI and model
# logic use DEFAULT_POLE_SWITCH_ELEMENT_FILES and ignore the family field.
DEFAULT_POLE_SWITCH_ELEMENT_RULES = [
    {"file_name": "SEC_S.zwk.icn.g", "family": "SEC"},
    {"file_name": "SEC_NON.zwk.icn.g", "family": "SEC"},
    {"file_name": "SEC_NON_H.zwk.icn.g", "family": "SEC"},
    {"file_name": "AR_NON_H.zwk.icn.g", "family": "AR"},
]

DEFAULT_TRANSFORMER_ELEMENT_FILES = [
    "Transformer_OH.pb.icn.g",
]

# Makkah fuse identity follows the same operator-maintained devref-file model
# as pole switches and pole transformers. Every configured file is a fuse;
# Element Management FUSE classification is not consulted. The defaults below
# are taken from the supplied Makkah drawings and can be changed from the model
# page without editing code.
DEFAULT_FUSE_ELEMENT_FILES = [
    "Fuse_arrow.zwk.icn.g",
    "Fuse_NON_SMART.zwk.icn.g",
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
    # Shared central configuration repository.  Startup never contacts it;
    # network I/O occurs only after an explicit sync/Admin action.
    "central_config": {
        "enabled": True,
        "host": "172.16.21.27",
        "port": 22,
        "username": "up8000",
        "password": "up8000",
        "remote_directory": "/home/up8000/nari-international/distribution-model-manager/config",
    },
    "machine_id": "",
    "element_catalog": {
        "records": [],
    },
    # Makkah pole-device identity is driven by exact devref file names maintained
    # by the operator. Every configured file is a pole switch; no AR/LBS/SEC
    # classification is required. Element Management is not consulted.
    "pole_switch_element_files": DEFAULT_POLE_SWITCH_ELEMENT_FILES,
    "transformer_element_files": DEFAULT_TRANSFORMER_ELEMENT_FILES,
    "fuse_element_files": DEFAULT_FUSE_ELEMENT_FILES,
    # Name format/color/background settings are hard filters for the global
    # Text-to-device assignment.
    "pole_switch_name_numeric": False,
    "pole_switch_name_format": "ALPHANUMERIC_SPACE",
    "pole_switch_name_colors": ["WHITE"],
    "pole_switch_name_has_background": False,
    "transformer_name_numeric": False,
    "transformer_name_format": "AUTO",
    "transformer_name_colors": ["WHITE"],
    "transformer_name_has_background": False,
    "last_file_path": "",
    "last_folder_path": "",
    "last_run_dir": "",
    "db": DEFAULT_DB_CONFIG,
    "rmu_name_positions": DEFAULT_RMU_NAME_POSITIONS,
    "rmu_name_positions_custom": False,
    "feeder_rmu_name_positions": DEFAULT_NAME_POSITIONS,
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
