from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule

KEY_STEP = 1 << 32


def _keyid(device_id, domain=1):
    return int(device_id) + int(domain) * KEY_STEP


class MultiCreateDB:
    def __init__(self):
        self.stations = {
            "STA1": {"id": 101, "name": "STA1", "code": "STA1"},
            "STA2": {"id": 102, "name": "STA2", "code": "STA2"},
        }
        self.feeders = {
            101: [{"id": 1001, "name": "AH101", "code": "AH101", "st_id": 101, "station_name": "STA1"}],
            102: [{"id": 2001, "name": "AH202", "code": "AH202", "st_id": 102, "station_name": "STA2"}],
        }
        # Each feeder has only one existing section while the G drawing has
        # two FeedLines on each topology branch. One shortage must therefore
        # be created under EACH feeder independently.
        self.sections = {
            1001: [{"id": 5001, "name": "STA1_AH101_SEC001", "code": "", "feeder_id": 1001, "bv_id": 91, "section_type": 0}],
            2001: [{"id": 6001, "name": "STA2_AH202_SEC001", "code": "", "feeder_id": 2001, "bv_id": 92, "section_type": 0}],
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


def _write_two_branch_g(path: Path):
    path.write_text(
        '''<G facID=""><Layer>
<Rect id="r1" x="0" y="0" w="300" h="140"/>
<CBreaker id="b1" x="20" y="20" w="20" h="20" link="0,1,fl1"/>
<Text id="t1" x="305" y="20" w="240" h="30" ts="STA1-AH101" lc="255,255,255"/>
<Rect id="r2" x="800" y="0" w="300" h="140"/>
<CBreaker id="b2" x="820" y="20" w="20" h="20" link="0,1,fl3"/>
<Text id="t2" x="1105" y="20" w="240" h="30" ts="STA2-AH202" lc="255,255,255"/>
<FeedLine id="fl1" x="20" y="40" w="0" h="100" d="30,40 30,140" link="0,1,b1;1,0,fl2" ls="2" keyid=""/>
<FeedLine id="fl2" x="30" y="140" w="120" h="0" d="30,140 150,140" link="0,1,fl1" ls="2" keyid=""/>
<FeedLine id="fl3" x="820" y="40" w="0" h="100" d="830,40 830,140" link="0,1,b2;1,0,fl4" ls="1" keyid=""/>
<FeedLine id="fl4" x="830" y="140" w="120" h="0" d="830,140 950,140" link="0,1,fl3" ls="" keyid=""/>
</Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_each_topology_feeder_gets_its_own_shortage_plan(tmp_path):
    g = _write_two_branch_g(tmp_path / "ring.g")
    db = MultiCreateDB()
    module = FeederModelModule()

    reports, summary, _ = module.validate(db, [g], {}, lambda _msg: None)
    report = reports[0]
    rows = {row["xml_id"]: row for row in report["feedline_rows"]}

    assert report["feedline_topology_confirmed_count"] == 4
    assert report["feedline_topology_conflict_count"] == 0
    assert report["feedline_topology_unresolved_count"] == 0

    assert rows["fl1"]["assigned_feeder_id"] == 1001
    assert rows["fl2"]["assigned_feeder_id"] == 1001
    assert rows["fl3"]["assigned_feeder_id"] == 2001
    assert rows["fl4"]["assigned_feeder_id"] == 2001

    plans = report["section_create_plan"]
    assert len(plans) == 2
    assert {(item["feeder_id"], item["name"]) for item in plans} == {
        (1001, "STA1_AH101_SEC002"),
        (2001, "STA2_AH202_SEC002"),
    }
    assert summary["association_ready"] == 4


def test_apply_creates_missing_sections_under_both_topology_feeders(tmp_path):
    g = _write_two_branch_g(tmp_path / "ring.g")
    db = MultiCreateDB()
    module = FeederModelModule()

    preview = module.preview_association(db, [g], {}, lambda _msg: None)
    changes = preview["changes_by_file"][str(g)]
    by_xml = {item["xml_id"]: item for item in changes}
    assert by_xml["fl2"]["feeder_id"] == 1001
    assert by_xml["fl4"]["feeder_id"] == 2001

    out = tmp_path / "g_output"
    result = module.apply_association(
        db, [g], {}, preview, lambda _msg: None, output_g_dir=out
    )
    assert result["database_created_count"] == 2
    assert result["skipped_count"] == 0
    assert result["applied_count"] == 4

    assert any(row["name"] == "STA1_AH101_SEC002" for row in db.sections[1001])
    assert any(row["name"] == "STA2_AH202_SEC002" for row in db.sections[2001])


def test_unresolved_feedline_is_blocked_instead_of_cross_feeder_guess(tmp_path):
    g = _write_two_branch_g(tmp_path / "ring.g")
    text = g.read_text(encoding="utf-8")
    # Break fl4 away from both source branches without adding any alternative
    # feeder evidence. It must not borrow a section from either candidate.
    text = text.replace(
        '<FeedLine id="fl4" x="830" y="140" w="120" h="0" d="830,140 950,140" link="0,1,fl3" ls="" keyid=""/>',
        '<FeedLine id="fl4" x="3000" y="3000" w="120" h="0" d="3000,3000 3120,3000" link="" ls="" keyid=""/>',
    )
    text = text.replace('link="0,1,b2;1,0,fl4" ls="1"', 'link="0,1,b2" ls="1"')
    g.write_text(text, encoding="utf-8")

    report = FeederModelModule().validate(
        MultiCreateDB(), [g], {}, lambda _msg: None
    )[0][0]
    rows = {row["xml_id"]: row for row in report["feedline_rows"]}
    assert rows["fl4"]["ownership_status"] == "UNRESOLVED"
    assert rows["fl4"]["association_ready"] == "NO"
    assert rows["fl4"]["db_create_needed"] == "NO"
    assert rows["fl4"].get("assigned_feeder_id") in (None, "")
