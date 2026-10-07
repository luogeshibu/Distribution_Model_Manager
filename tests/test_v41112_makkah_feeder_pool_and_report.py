from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.ring_discovery import (
    attach_makkah_ring_feeder_inventory,
    compare_makkah_ring_feeders_for_files,
)
from dmm.infrastructure.reporting.writer import export_html_bundle

KEY_STEP = 1 << 32


def _keyid(device_id, domain=1):
    return int(device_id) + int(domain) * KEY_STEP


class PoolDB:
    def __init__(self):
        self.stations = {
            "STA1": {"id": 101, "name": "STA1", "code": "STA1"},
            "STA2": {"id": 102, "name": "STA2", "code": "STA2"},
        }
        self.feeders = {
            101: [{"id": 1001, "name": "AH101", "code": "AH101", "st_id": 101, "station_name": "STA1"}],
            102: [{"id": 2001, "name": "AH202", "code": "AH202", "st_id": 102, "station_name": "STA2"}],
        }
        self.sections = {
            1001: [
                {"id": 5001, "name": "STA1_AH101_SEC001", "code": "", "feeder_id": 1001, "bv_id": 91},
            ],
            2001: [
                {"id": 6001, "name": "STA2_AH202_SEC001", "code": "", "feeder_id": 2001, "bv_id": 92},
                {"id": 6002, "name": "STA2_AH202_SEC002", "code": "", "feeder_id": 2001, "bv_id": 92},
            ],
        }

    def find_stations_by_name_hint(self, hint, table_id=405):
        row = self.stations.get(str(hint).strip().upper())
        return [dict(row)] if row else []

    def get_feeders_by_station(self, station_id, table_id=13500):
        return [dict(x) for x in self.feeders.get(int(station_id), [])]

    def get_feeder_info(self, feeder_id, table_id=13500):
        fid = int(feeder_id)
        for rows in self.feeders.values():
            for row in rows:
                if int(row["id"]) == fid:
                    out = dict(row)
                    out["display_name"] = f"{out['station_name']}-{out['name']}"
                    return out
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections.get(int(feeder_id), [])]

    def get_device_by_id(self, table_id, device_id):
        if int(table_id) != 13503:
            return None
        for rows in self.sections.values():
            for row in rows:
                if int(row["id"]) == int(device_id):
                    return dict(row)
        return None

    def verify_keyid(self, value):
        value = int(value)
        domain = value // KEY_STEP
        device_id = value - domain * KEY_STEP
        return {"device_id": device_id, "tab_no": 13503, "col_no": domain}

    def get_preferred_feeder_section_voltage(self, station_id):
        return {"bv_id": 91 if int(station_id) == 101 else 92, "nomvol": 13.8}

    def create_missing_sections(self, feeder_id, create_defs, table_id=13503, area_id=0):
        feeder_id = int(feeder_id)
        rows = self.sections.setdefault(feeder_id, [])
        next_id = max([int(x["id"]) for values in self.sections.values() for x in values] + [7000]) + 1
        created = []
        for item in create_defs:
            row = {
                "id": next_id,
                "name": item["name"],
                "code": "",
                "feeder_id": feeder_id,
                "bv_id": int(item["bv_id"]),
                "section_type": int(item["section_type"]),
            }
            next_id += 1
            rows.append(row)
            created.append(dict(row))
        return created


def _write_g(path: Path):
    path.write_text(
        f'''<G facID=""><Layer>
        <Rect id="r1" x="0" y="0" w="300" h="140"/>
        <CBreaker id="b1" x="20" y="20" w="20" h="20" link="0,1,fl1"/>
        <Text id="t1" x="305" y="20" w="240" h="30" ts="STA1-AH101" lc="255,255,255"/>
        <Rect id="r2" x="800" y="0" w="300" h="140"/>
        <CBreaker id="b2" x="820" y="20" w="20" h="20" link="0,1,fl3"/>
        <Text id="t2" x="1105" y="20" w="240" h="30" ts="STA2-AH202" lc="255,255,255"/>
        <FeedLine id="fl1" x="20" y="40" w="0" h="100" d="30,40 30,140" link="0,1,b1;1,0,fl2" ls="2" keyid="{_keyid(6001, 1)}"/>
        <FeedLine id="fl2" x="30" y="140" w="120" h="0" d="30,140 150,140" link="0,1,fl1" ls="2" keyid=""/>
        <FeedLine id="fl3" x="820" y="40" w="0" h="100" d="830,40 830,140" link="0,1,b2;1,0,fl4" ls="1" keyid=""/>
        <FeedLine id="fl4" x="830" y="140" w="120" h="0" d="830,140 950,140" link="0,1,fl3" ls="" keyid=""/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_makkah_validation_uses_each_feedlines_topology_feeder(tmp_path):
    g = _write_g(tmp_path / "ring.g")
    module = FeederModelModule()
    logs = []
    reports, summary, _rules = module.validate(PoolDB(), [g], {}, logs.append)
    assert len(reports) == 1
    report = reports[0]
    assert report["ring_candidate_feeder_ids"] == "1001, 2001"
    rows = {row["xml_id"]: row for row in report["feedline_rows"]}

    # fl1 is topologically on STA1-AH101. Its old link points to feeder 2001,
    # so v4.1.124 must relink it instead of accepting any feeder in the drawing.
    assert rows["fl1"]["ownership_status"] == "CONFIRMED"
    assert rows["fl1"]["topology_primary_feeder"] == "STA1-AH101"
    assert rows["fl1"]["assigned_feeder_id"] == 1001
    assert rows["fl1"]["assigned_device_id"] == 5001
    assert rows["fl1"]["writeback_needed"] == "YES"

    # The second STA1 FeedLine can no longer borrow an STA2 section; shortage
    # is created under its own topology feeder.
    assert rows["fl2"]["assigned_feeder_id"] == 1001
    assert rows["fl2"]["db_create_needed"] == "YES"
    assert rows["fl2"]["planned_section_name"] == "STA1_AH101_SEC002"

    # STA2 FeedLines consume only STA2 sections.
    assert rows["fl3"]["assigned_feeder_id"] == 2001
    assert rows["fl3"]["assigned_device_id"] == 6001
    assert rows["fl4"]["assigned_feeder_id"] == 2001
    assert rows["fl4"]["assigned_device_id"] == 6002
    assert len(report["section_create_plan"]) == 1
    assert report["section_create_plan"][0]["feeder_id"] == 1001
    assert summary["feedlines"] == 4


def test_feeder_html_lists_every_found_graph_feeder(tmp_path):
    g = _write_g(tmp_path / "ring.g")
    db = PoolDB()
    module = FeederModelModule()
    reports, _summary, rules = module.validate(db, [g], {}, lambda _msg: None)
    inventory = compare_makkah_ring_feeders_for_files(db, [g], {}, None)
    attach_makkah_ring_feeder_inventory(reports, inventory)

    html_path = tmp_path / "report.html"
    export_html_bundle(reports, html_path, rules)
    text = html_path.read_text(encoding="utf-8")

    assert "本图识别馈线（全部）" in text
    assert "STA1-AH101" in text
    assert "STA2-AH202" in text
    assert ">1001<" in text
    assert ">2001<" in text
    assert "目标馈线ID" in text
    assert "目标馈线名称" in text


def test_preview_and_apply_use_topology_target_feeders_without_cross_group_protection(tmp_path):
    g = _write_g(tmp_path / "ring.g")
    db = PoolDB()
    module = FeederModelModule()
    preview = module.preview_association(db, [g], {}, lambda _msg: None)
    changes = preview["changes_by_file"][str(g)]
    by_xml = {item["xml_id"]: item for item in changes}
    assert by_xml["fl1"]["feeder_id"] == 1001
    assert by_xml["fl2"]["feeder_id"] == 1001
    assert by_xml["fl3"]["feeder_id"] == 2001
    assert by_xml["fl4"]["feeder_id"] == 2001

    out = tmp_path / "g_output"
    result = module.apply_association(db, [g], {}, preview, lambda _msg: None, output_g_dir=out)
    assert result["database_created_count"] == 1
    assert result["skipped_count"] == 0
    assert result["applied_count"] == 4
    output = Path(result["copied_files"][0]).read_text(encoding="utf-8")
    assert f'keyid="{_keyid(5001, 1)}"' in output
    assert f'keyid="{_keyid(6001, 1)}"' in output
    assert f'keyid="{_keyid(6002, 1)}"' in output

