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
        "match_mode": "NAME_THEN_CODE_IN_RMU_AND_FEEDER",
        "description": "配网开关/断路器（当前RMU+当前馈线，NAME优先，CODE兜底）",
    },
    "ZhaiWaiJieDiDaoZha": {
        "table_id": 13514,
        "domain": 40,
        "match_mode": "GROUND_KNAME_THEN_DCODE_IN_RMU_AND_FEEDER",
        "description": "接地刀闸（KY/KQ名称优先，Y/Q+D代码兜底）",
    },
    "BusDis": {
        "table_id": 13506,
        "domain": 1,
        "match_mode": "CODE_EQUALS_LOGICAL_CODE",
        "description": "母线",
    },
}

# 配网主站设备关联。主站模块只处理数据库定义明确的三类开关设备；Bus
# 不属于该模块的关联对象。
DEFAULT_MASTER_STATION_RULES = {
    "CBreaker": {
        "table_id": 407,
        "domain": 40,
        "table_name": "breaker",
        "description": "主站断路器",
    },
    "Disconnector": {
        "table_id": 408,
        "domain": 30,
        "table_name": "disconnector",
        "description": "主站隔离开关",
    },
    "GroundDisconnector": {
        "table_id": 409,
        "domain": 30,
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

# Jeddah hard rule for RMU cabinet names: use the RMU rectangle as the
# geometry reference and ONLY accept Text above the RMU frame. Right/left/
# bottom/global fallback is intentionally forbidden. Cached/user settings
# can never widen this production rule.
RMU_NAME_DIRECTIONS = ("top", "right", "left", "bottom")
DEFAULT_RMU_NAME_DETECTION_MODE = "FIXED"

# Protection / EFI association policy inside RMUs.
# ALL: associate every pwbh element marked RMU_PWBH_EFI for every RMU.
# SMART_ONLY: associate it only for SMART/SMR RMUs; already-linked EFI models
# in NORMAL RMUs are cleared back to an unlinked attribute state.
DEFAULT_RMU_PROTECTION_SCOPE = "ALL"


def resolve_rmu_name_positions(mode="FIXED", configured_positions=None):
    """Return the hard-coded Jeddah RMU cabinet-name direction: TOP only."""
    del mode, configured_positions
    return ["top"]

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
    # Connection details for the shared NARI configuration directory.
    # v4.1.45 never contacts this server during startup. It is used only when
    # the operator explicitly syncs, initializes, publishes or releases Admin.
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
    # Pole-switch / pole-transformer names use fixed Jeddah geometry rules
    # (model-specific direction/color + existing distance limits); no user format/background
    # preference is stored or applied.
    "last_file_path": "",
    "last_folder_path": "",
    "last_run_dir": "",
    "db": DEFAULT_DB_CONFIG,
    "rmu_name_positions": DEFAULT_NAME_POSITIONS,
    "rmu_name_detection_mode": DEFAULT_RMU_NAME_DETECTION_MODE,
    "rmu_name_exclusions": DEFAULT_RMU_NAME_EXCLUSIONS,
    "rmu_protection_scope": DEFAULT_RMU_PROTECTION_SCOPE,
    "device_rules": {},
    "master_station_rules": {},
    "breaker_name_source": "GRAPHICAL_TEXT",
    "feeder_table_id": 13500,
    "section_table_id": 13503,
    "section_domain": 1,
    "feeder_resolution_mode": "GRAPHICAL_AUTO",
    "manual_feeder_name": "",
    "feeder_station_hint": "",
    "allow_feeder_override": False,
    "feeder_drawing_mode": "SINGLE",
    "auto_create_missing_sections": True,
}
