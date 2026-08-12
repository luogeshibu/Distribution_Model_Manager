from dmm.infrastructure.reporting.writer import (
    flatten_device_rows,
    flatten_rmu_rows,
)


def _device(object_type, name, xml_id):
    return {
        "object_type": object_type,
        "selected_device_name": name,
        "xml_id": xml_id,
        "status": "PASS",
    }


def _rmu(frame_index, name, devices, records=None):
    return {
        "frame_index": frame_index,
        "frame_xml_id": f"frame-{frame_index}",
        "rmu_name": name,
        "rmu_status": "PASS",
        "rmu_reason": "",
        "rmu_db_count": len(records or []),
        "device_rows": devices,
        "rmu_records": records or [],
        "association_eligible": True,
    }


def test_rmu_summary_orders_only_by_frame_sequence():
    report = {
        "file_name": "A.g",
        "rmu_results": [
            _rmu(6, "8723", []),
            _rmu(3, "15953", []),
            _rmu(9, "16934", []),
            _rmu(1, "17483", [], records=[
                {"id": 101},
                {"id": 102},
                {"id": 103},
            ]),
            _rmu(5, "19019", []),
        ],
    }

    rows = flatten_rmu_rows([report])

    assert [row["frame_index"] for row in rows] == [
        1, 3, 5, 6, 9
    ]

    # Duplicate database RMUs are represented by one G-frame summary row.
    first = rows[0]
    assert first["rmu_db_count"] == 3
    assert first["rmu_id"] == ""
    assert first["rmu_status"] == "FAIL"


def test_device_details_only_group_types_inside_each_rmu():
    report = {
        "file_name": "A.g",
        "rmu_results": [
            _rmu(2, "RMU-A", [
                _device("ZhaiWaiJieDiDaoZha", "Y2D", 1),
                _device("BusDis", "BUS", 2),
                _device("CBreakerDis", "Y2", 3),
                _device("ZhaiWaiJieDiDaoZha", "Q1D", 4),
                _device("CBreakerDis", "Q1", 5),
                _device("CBreakerDis", "Y1", 6),
                _device("ZhaiWaiJieDiDaoZha", "Y1D", 7),
            ]),
            _rmu(1, "RMU-B", [
                _device("BusDis", "BUS-B", 8),
                _device("CBreakerDis", "B2", 9),
                _device("CBreakerDis", "B1", 10),
            ]),
        ],
    }

    rows = flatten_device_rows([report])

    # RMU processing order must remain RMU-A then RMU-B.
    assert [row["rmu_name"] for row in rows] == [
        "RMU-A", "RMU-A", "RMU-A", "RMU-A", "RMU-A", "RMU-A", "RMU-A",
        "RMU-B", "RMU-B", "RMU-B",
    ]

    # Inside RMU-A only type grouping applies; same-type source order remains.
    assert [
        (row["object_type"], row["selected_device_name"])
        for row in rows[:7]
    ] == [
        ("CBreakerDis", "Y2"),
        ("CBreakerDis", "Q1"),
        ("CBreakerDis", "Y1"),
        ("ZhaiWaiJieDiDaoZha", "Y2D"),
        ("ZhaiWaiJieDiDaoZha", "Q1D"),
        ("ZhaiWaiJieDiDaoZha", "Y1D"),
        ("BusDis", "BUS"),
    ]

    # RMU-B retains B2 before B1; there is no device-name sorting.
    assert [
        (row["object_type"], row["selected_device_name"])
        for row in rows[7:]
    ] == [
        ("CBreakerDis", "B2"),
        ("CBreakerDis", "B1"),
        ("BusDis", "BUS-B"),
    ]
