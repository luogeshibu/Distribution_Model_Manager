from dmm.domain.gfile.parser import Box, GObject
from dmm.domain.rmu.validator import RmuValidator


class _Db:
    def verify_keyid(self, keyid):
        return {"device_id": 1001, "tab_no": 13502, "col_no": 40}

    def get_device_by_id(self, table_id, device_id):
        assert table_id == 13502
        assert device_id == 1001
        return {
            "id": 1001,
            "code": "Y1",
            "name": "Y1",
            "combined_id": 30864,
            "bv_id": 112871465660973067,
            "_table_name": "dms_cb_device",
        }

    def get_rmu_by_id(self, rmu_id):
        assert rmu_id == 30864
        return {"id": 30864, "name": "30864"}

    def get_devices_by_combined_id(self, table_id, rmu_id):
        assert table_id == 13502
        assert rmu_id == 30864
        return "dms_cb_device", [
            {
                "id": 1001,
                "code": "Y1",
                "name": "Y1",
                "combined_id": 30864,
            }
        ]


class _DummyParser:
    pass


def _elem():
    return GObject(
        tag="CBreakerDis",
        attrs={"id": "117000001", "keyid": "123456"},
        box=Box(0, 0, 10, 10),
        xml_index=1,
    )


def _validator():
    return RmuValidator(_Db(), _DummyParser(), {})


def test_unparsed_rmu_name_does_not_turn_valid_existing_link_into_rmu_mismatch():
    validator = _validator()
    elem = _elem()
    row = validator._default_device_row(
        "",
        "",
        elem,
        {"table_id": 13502, "domain": 40},
        {"table_name": ""},
    )
    row["logical_code"] = "Y1"
    row["selected_device_name"] = "Y1"

    validator._inspect_current_link_without_unique_rmu(
        row,
        elem,
        "RMU_NAME_NOT_PARSED: 图上名称未解析",
    )

    assert row["status"] == "PASS"
    assert row["model_link_correct"] == "YES"
    assert row["current_combined_id"] == 30864
    assert row["current_rmu_name"] == "30864"
    assert row["current_rmu_name_match"] == "N/A"
    assert row["writeback_needed"] == "NO"


def test_unparsed_rmu_name_infers_same_rmu_from_all_existing_device_links_and_explains_it():
    validator = _validator()
    rows = []
    for xml_id in ("1", "2", "3"):
        rows.append({
            "xml_id": xml_id,
            "model_linked": "YES",
            "model_link_correct": "YES",
            "association_ready": "YES",
            "writeback_needed": "NO",
            "current_combined_id": 30864,
            "current_rmu_name": "30864",
            "status": "PASS",
            "severity": "PASS",
            "reason": "EXISTING_MANUAL_LINK_VALID",
        })

    rmu = {
        "frame_xml_id": "2000332",
        "rmu_name": "",
        "rmu_reason": "RMU_NAME_NOT_PARSED: 在当前配置方向未解析到名称",
        "device_rows": rows,
        "db_integrity_issues": [],
        "association_block_reasons": [
            "RMU_NAME_NOT_PARSED: 矩形框XML ID=2000332 未解析出环网柜名称；禁止自动关联。"
        ],
    }

    validator._validate_nonunique_rmu_existing_links(rmu)

    assert rmu["inferred_rmu_id"] == 30864
    assert rmu["inferred_rmu_name"] == "30864"
    assert "ID=30864" in rmu["rmu_reason"]
    assert "NAME=30864" in rmu["rmu_reason"]
    assert "现有RMU归属关联一致且正确" in rmu["rmu_reason"]
    assert "请检查图上的环网柜名称是否应为“30864”" in rmu["rmu_reason"]
    assert any("现有一致关联无需修改" in x for x in rmu["association_block_reasons"])
    assert all(row["status"] == "PASS" for row in rows)
    assert all("当前KeyID设备所属环网柜ID=30864" in row["reason"] for row in rows)


def test_unparsed_rmu_name_with_existing_links_spanning_multiple_rmus_is_still_hard_error():
    validator = _validator()
    rows = [
        {
            "xml_id": "1",
            "model_linked": "YES",
            "model_link_correct": "YES",
            "association_ready": "YES",
            "writeback_needed": "NO",
            "current_combined_id": 30864,
            "current_rmu_name": "30864",
            "status": "PASS",
            "severity": "PASS",
            "reason": "",
        },
        {
            "xml_id": "2",
            "model_linked": "YES",
            "model_link_correct": "YES",
            "association_ready": "YES",
            "writeback_needed": "NO",
            "current_combined_id": 30833,
            "current_rmu_name": "30833",
            "status": "PASS",
            "severity": "PASS",
            "reason": "",
        },
    ]
    rmu = {
        "rmu_name": "",
        "rmu_reason": "RMU_NAME_NOT_PARSED: 图上名称未解析",
        "device_rows": rows,
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    validator._validate_nonunique_rmu_existing_links(rmu)

    assert rmu["db_integrity_issues"]
    assert "多个数据库环网柜ID" in rmu["db_integrity_issues"][0]
    assert all(row["status"] == "RMU_LINK" for row in rows)
    assert all(row["model_link_correct"] == "NO" for row in rows)
