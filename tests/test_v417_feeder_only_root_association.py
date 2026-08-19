from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser


FEEDER_ID = 3799912185593856228


class MinimalDB:
    def __init__(self):
        self.feeder = {
            "id": FEEDER_ID,
            "name": "43",
            "code": "43",
            "st_id": 113997365000000001,
            "station_name": "AJWD",
            "station_bv_id": 112871465660973067,
            "display_name": "AJWD 43",
        }

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        return [dict(self.feeder)] if str(hint) == "AJWD43" else []

    def get_feeder_info(self, feeder_id, table_id=13500):
        return dict(self.feeder) if int(feeder_id) == FEEDER_ID else None

    def get_sections_by_feeder_id(self, *args, **kwargs):
        raise AssertionError("zero-FeedLine feeder-only validation must not query 13503")


class NoDbCalls:
    pass


def _write_zero_feedline_g(path: Path):
    path.write_text(
        '<G id="root" facID=""><Layer>'
        '<Bus id="b1" key_name="busbarsection JED CTL AJWD 13.8kV AHBB1A AHBB1A id"/>'
        '</Layer></G>',
        encoding="utf-8",
    )


def test_zero_feedline_forced_feeder_is_not_failure(tmp_path):
    g = tmp_path / "TEST88.sln.pic.g"
    _write_zero_feedline_g(g)
    db = MinimalDB()
    validator = FeederValidator(db=db, parser=GParser())

    result = validator.validate_file_with_feeder_record(
        g, db.feeder, source="MANUAL"
    )
    report = result["feeder_regions"][0]

    assert report["feeder_direct_db_match_count"] == 1
    assert report["feeder_id"] == FEEDER_ID
    assert report["feeder_name"] == "AJWD 43"
    assert report["association_eligible"] is True
    assert report["feeder_root_writeback_needed"] == "YES"
    assert report["status"] == "WARN"
    assert "不会创建13503馈线段" in report["reason"]
    assert report["feedline_rows"] == []


def test_section_prefix_uses_real_substation_name_not_region():
    assert FeederModelModule._section_prefix(
        {"station_name": "AJWD", "name": "43"}, []
    ) == "AJWD_43"


def test_preview_exposes_root_facid_candidate_without_feedline(monkeypatch, tmp_path):
    g = tmp_path / "TEST88.sln.pic.g"
    _write_zero_feedline_g(g)
    report = {
        "g_file": str(g),
        "file_name": g.name,
        "region_index": 1,
        "feeder_id": FEEDER_ID,
        "feeder_name": "AJWD 43",
        "association_eligible": True,
        "feeder_root_writeback_needed": "YES",
        "feedline_rows": [],
        "status": "WARN",
        "reason": "ready",
        "summary": {},
    }
    module = FeederModelModule()
    monkeypatch.setattr(
        module,
        "validate",
        lambda *a, **k: ([report], {"feeder_files": 1}, module._rules({})),
    )

    preview = module.preview_association(
        NoDbCalls(), [g], {"feeder_resolution_mode": "MANUAL", "manual_feeder_name": "AJWD 43"}, lambda _m: None
    )
    changes = preview["changes_by_file"][str(g)]
    assert len(changes) == 1
    assert changes[0]["change_kind"] == "FEEDER_ROOT_FACID"
    assert changes[0]["tag"] == "G"
    assert changes[0]["xml_id"] == "root"
    assert changes[0]["attributes"] == {"facID": str(FEEDER_ID)}
    assert report["feeder_root_candidate_row"]["assigned_device_id"] == FEEDER_ID


def test_apply_root_only_writes_facid_and_does_not_touch_13503(tmp_path):
    g = tmp_path / "TEST88.sln.pic.g"
    _write_zero_feedline_g(g)
    stat = g.stat()
    report = {
        "g_file": str(g),
        "file_name": g.name,
        "region_index": 1,
        "feeder_id": FEEDER_ID,
        "feeder_name": "AJWD 43",
        "feeder_resolution_source": "MANUAL",
        "association_eligible": True,
        "feedline_rows": [],
        "reason": "ready",
    }
    root_row = {
        "object_type": "G",
        "xml_id": "root",
        "status": "WARN",
        "severity": "UNLINKED",
        "association_ready": "YES",
        "writeback_needed": "YES",
    }
    change = {
        "change_kind": "FEEDER_ROOT_FACID",
        "xml_id": "root",
        "tag": "G",
        "attributes": {"facID": str(FEEDER_ID)},
        "feeder_name": "AJWD 43",
        "feeder_id": FEEDER_ID,
        "region_index": 1,
        "validated_row": root_row,
    }
    settings = {
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
        "feeder_resolution_mode": "MANUAL",
        "manual_feeder_name": "AJWD 43",
        "auto_create_missing_sections": True,
    }
    preview = {
        "reports": [report],
        "changes_by_file": {str(g): [change]},
        "ls_normalization_by_file": {},
        "file_fingerprints": {str(g): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}},
        "settings_snapshot": dict(settings),
        "rules": FeederModelModule._rules(settings),
    }
    out = tmp_path / "out"
    result = FeederModelModule().apply_association(
        NoDbCalls(), [g], settings, preview, lambda _m: None, output_g_dir=out
    )
    output = Path(result["copied_files"][0])
    text = output.read_text(encoding="utf-8")
    assert f'facID="{FEEDER_ID}"' in text
    assert result["applied_count"] == 1
    assert result["database_created_count"] == 0
    assert result["results"][0]["facid_written"] is True
    assert any(c["tag"] == "G" for c in result["results"][0]["changes"])
