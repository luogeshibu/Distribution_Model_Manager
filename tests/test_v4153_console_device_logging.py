
from dmm.application.modules.rmu import RmuModelModule
from dmm.application.modules.pole_switch import PoleSwitchModelModule
from dmm.application.modules.transformer import TransformerModelModule


def test_pole_switch_found_device_is_logged():
    logs = []
    PoleSwitchModelModule._log_found_device(logs.append, 1, {
        "selected_device_name": "SEC123",
        "device_model": "SEC",
        "xml_id": "101",
        "name_xml_id": "201",
        "name_distance": 42.5,
        "db_device_id": 301,
        "status": "UNLINKED",
        "association_ready": "YES",
        "reason": "POLE_SWITCH_ASSOCIATION_READY",
    })
    assert len(logs) == 1
    assert "[柱上开关][找到设备]" in logs[0]
    assert "名称=SEC123" in logs[0]
    assert "DB_ID=301" in logs[0]


def test_transformer_found_device_is_logged():
    logs = []
    TransformerModelModule._log_found_device(logs.append, 1, {
        "selected_device_name": "93106",
        "xml_id": "102",
        "name_xml_id": "202",
        "name_distance": 18,
        "db_device_id": 302,
        "status": "PASS",
        "association_ready": "YES",
        "reason": "TRANSFORMER_MODEL_LINK_CORRECT",
    })
    assert len(logs) == 1
    assert "[柱上变压器][找到设备]" in logs[0]
    assert "名称=93106" in logs[0]
    assert "Text_ID=202" in logs[0]


def test_rmu_and_inframe_devices_are_logged():
    logs = []
    RmuModelModule._log_found_rmus(logs.append, {
        "rmu_results": [{
            "rmu_name": "902",
            "frame_xml_id": "500",
            "rmu_id": 600,
            "rmu_status": "PASS",
            "association_eligible": True,
            "rmu_reason": "RMU_MODEL_DATA_VALID",
            "device_rows": [{
                "object_type": "CBreakerDis",
                "selected_device_name": "Y1",
                "xml_id": "700",
                "db_device_id": 800,
                "status": "PASS",
                "association_ready": "YES",
                "reason": "MODEL_LINK_CORRECT",
            }],
        }]
    })
    assert any("[RMU][找到设备]" in line and "名称=902" in line for line in logs)
    assert any("[RMU][柜内设备]" in line and "类型=CBreakerDis" in line for line in logs)
