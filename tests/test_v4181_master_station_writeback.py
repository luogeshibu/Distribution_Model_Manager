from pathlib import Path

from dmm.application.modules.master_station import MasterStationModelModule


def _attrs(kind, state):
    attrs = MasterStationModelModule._attributes_for_row({
        "object_type": kind,
        "xml_id": "x1",
        "db_bv_id": "12345",
        "expected_keyid": 987654321,
    })
    assert attrs == {
        "app": "100000",
        "voltype": "12345",
        "p_ReportType": "1",
        "state": state,
        "keyid": "987654321",
    }


def test_master_station_writeback_contract_uses_app_100000():
    _attrs("CBreaker", "41")
    _attrs("Disconnector", "31")
    _attrs("GroundDisconnector", "31")
    _attrs("Bus", "10")


def test_execution_recheck_blocks_changed_target(tmp_path, monkeypatch):
    g = tmp_path / "a.g"
    g.write_text("<G/>", encoding="utf-8")
    stat = g.stat()
    module = MasterStationModelModule()

    preview_row = {
        "object_type": "CBreaker",
        "xml_id": "cb1",
        "association_ready": "YES",
        "writeback_needed": "YES",
        "table_id": 407,
        "configured_domain": 40,
        "db_device_id": 1001,
        "db_bv_id": "88",
        "expected_keyid": 123,
    }
    preview = {
        "changes_by_file": {
            str(g): [{
                "xml_id": "cb1",
                "tag": "CBreaker",
                "_source_file": str(g),
                "validated_row": preview_row,
                "attributes": {},
            }]
        },
        "file_fingerprints": {str(g): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}},
    }

    def fake_analyze(*args, **kwargs):
        fresh = dict(preview_row)
        fresh["db_device_id"] = 2002
        fresh["expected_keyid"] = 456
        fresh["reason"] = "MASTER_STATION_ASSOCIATION_READY_BY_BAY"
        return {"master_station_rows": [fresh]}

    monkeypatch.setattr(module, "_analyze_file", fake_analyze)
    result = module.apply_association(
        db=object(), files=[str(g)], settings={}, preview_data=preview,
        log_callback=lambda *_: None, output_g_dir=tmp_path / "out",
    )
    assert result["applied_count"] == 0
    assert result["skipped_count"] == 1
    assert result["copied_files"] == []
    assert "TARGET_CHANGED" in result["operation_reports"][0]["master_station_rows"][0]["reason"]


def test_sidebar_contract_uses_graphics_workspace_as_primary_navigation():
    source = (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert '("模型工作区", 0)' in source
    assert '("数据库", 1)' in source
    assert '("图元管理", 2)' in source
    assert '("图形工作区", 3)' in source
    assert '("运行历史", 4)' in source
