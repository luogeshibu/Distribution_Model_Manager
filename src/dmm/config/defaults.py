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
    "top": True,
    "right": False,
    "left": False,
    "bottom": False,
}

# RMU name labels are searched in all four directions by default.  The
# checkbox map above remains as a legacy/advanced override for drawings that
# use a known fixed layout.
RMU_NAME_DIRECTIONS = ("top", "right", "left", "bottom")
DEFAULT_RMU_NAME_DETECTION_MODE = "AUTO"


def resolve_rmu_name_positions(mode="AUTO", configured_positions=None):
    """Return the effective RMU-name directions for a validation run.

    ``AUTO`` deliberately does not require a direction from the user.  The
    parser still uses direction as one spatial feature, but searches all four
    directions and lets the global ownership/scoring rules decide.

    ``FIXED`` preserves the previous checkbox behavior.  If an old caller
    supplies an empty map, fall back to the historical top direction instead
    of making the entire validation pipeline fail unexpectedly.
    """
    if str(mode or DEFAULT_RMU_NAME_DETECTION_MODE).strip().upper() == "AUTO":
        return list(RMU_NAME_DIRECTIONS)

    configured_positions = configured_positions or {}
    selected = [
        position
        for position in RMU_NAME_DIRECTIONS
        if bool(configured_positions.get(position, False))
    ]
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
    },
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
