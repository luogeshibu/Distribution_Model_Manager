from pathlib import Path

from dmm.domain.feeder.ownership import FeederOwnershipResolver
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser


class OwnershipDB:
    def __init__(self):
        self.feeders = {
            "AA01": {"id": 101, "name": "AA-01", "display_name": "AA-01"},
            "BB02": {"id": 202, "name": "BB-02", "display_name": "BB-02"},
        }

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        key = "".join(c for c in str(hint).upper() if c.isalnum())
        row = self.feeders.get(key)
        return [dict(row)] if row else []


def make_ring(path: Path, *, with_nop: bool):
    nop = '<Text id="tnop" x="198" y="-55" w="50" h="20" ts="NOP"/>' if with_nop else ""
    path.write_text(
        f'''<G><Layer>
        <rect id="fa" x="-20" y="-20" w="80" h="100"/>
        <Text id="ta" x="-5" y="-55" w="60" h="20" ts="AA-01" lc="255,255,255" lcc="#ffffff"/>
        <CBreaker id="srcA" x="0" y="0" w="40" h="40" node_area="0,0,l1"/>
        <ConnectLine id="l1" x="20" y="40" w="80" h="2" d="20,40 100,40" link="0,0,srcA;1,0,f1"/>
        <FeedLine id="f1" x="100" y="37" w="100" h="6" d="100,40 200,40" link="0,0,l1;1,0,sw"/>
        <CBreakerDis id="sw" x="200" y="20" w="40" h="40" node_area="0,0,f1;1,0,f2" p_NameString="Y1"/>
        {nop}
        <FeedLine id="f2" x="240" y="37" w="100" h="6" d="240,40 340,40" link="0,0,sw;1,0,l2"/>
        <ConnectLine id="l2" x="340" y="40" w="80" h="2" d="340,40 420,40" link="0,0,f2;1,0,srcB"/>
        <rect id="fb" x="400" y="0" w="80" h="100"/>
        <CBreaker id="srcB" x="420" y="20" w="40" h="40" node_area="0,0,l2"/>
        <Text id="tb" x="415" y="-35" w="60" h="20" ts="BB-02" lc="255,255,255" lcc="#ffffff"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_nop_splits_two_main_feeder_sources(tmp_path):
    parsed = GParser().parse(make_ring(tmp_path / "ring.g", with_nop=True))
    result = FeederOwnershipResolver(OwnershipDB()).resolve(
        parsed,
        [],
        lambda _obj: None,
    )
    assert result["summary"]["source_cbreaker_count"] == 2
    assert result["summary"]["resolved_source_feeder_count"] == 2
    assert result["summary"]["nop_boundary_switch_count"] >= 1
    assert result["ownership"]["f1"]["feeder_id"] == 101
    assert result["ownership"]["f1"]["status"] == "CONFIRMED"
    assert result["ownership"]["f2"]["feeder_id"] == 202
    assert result["ownership"]["f2"]["status"] == "CONFIRMED"


def test_two_source_feeders_without_nop_are_blocked_as_conflict(tmp_path):
    parsed = GParser().parse(make_ring(tmp_path / "ring.g", with_nop=False))
    result = FeederOwnershipResolver(OwnershipDB()).resolve(
        parsed,
        [],
        lambda _obj: None,
    )
    assert result["ownership"]["f1"]["status"] == "CONFLICT"
    assert result["ownership"]["f2"]["status"] == "CONFLICT"
    assert result["ownership"]["f1"]["candidate_feeder_ids"] == "101,202"


def test_strict_endpoint_repair_connects_missing_xml_link(tmp_path):
    path = tmp_path / "gap.g"
    path.write_text(
        '''<G><Layer>
        <rect id="fa" x="-20" y="-20" w="80" h="100"/>
        <Text id="ta" x="-5" y="-55" w="60" h="20" ts="AA-01" lc="255,255,255" lcc="#ffffff"/>
        <CBreaker id="srcA" x="0" y="0" w="40" h="40" node_area="0,0,l1"/>
        <ConnectLine id="l1" x="20" y="40" w="80" h="2" d="20,40 100,40" link="0,0,srcA"/>
        <FeedLine id="f1" x="100" y="37" w="100" h="6" d="100,40 200,40"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parsed = GParser().parse(path)
    result = FeederOwnershipResolver(OwnershipDB()).resolve(
        parsed,
        [],
        lambda _obj: None,
    )
    assert result["summary"]["strict_geometry_repair_count"] >= 1
    assert result["ownership"]["f1"]["feeder_id"] == 101


class RegionDB:
    def get_feeder_info(self, feeder_id, table_id=13500):
        return {"id": int(feeder_id), "name": "AA-01", "display_name": "AA-01"}

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [
            {"id": 5001, "name": "A_01_SEC001", "feeder_id": int(feeder_id), "bv_id": 91}
        ]

    def verify_keyid(self, keyid):
        value = int(keyid)
        return {"device_id": value - (1 << 32), "tab_no": 13503, "col_no": 1}


def test_confirmed_ownership_does_not_require_global_nearest_device(tmp_path):
    path = tmp_path / "owned.g"
    path.write_text(
        '<G><Layer><FeedLine id="f1" x="0" y="0" w="100" h="6" ls="2"/></Layer></G>',
        encoding="utf-8",
    )
    parser = GParser()
    parsed = parser.parse(path)
    feedline = next(obj for obj in parsed.objects if obj.tag == "FeedLine")
    validator = FeederValidator(RegionDB(), parser=parser)
    report = validator._validate_rmu_topology_region(
        parsed,
        {
            "region_index": 1,
            "feedlines": [feedline],
            "rmu_anchors": [],
            "confirmed_feeder_id": 101,
            "ownership_by_feedline": {
                "f1": {
                    "feeder_id": 101,
                    "status": "CONFIRMED",
                    "method": "STRICT_TOPOLOGY",
                    "component": 1,
                    "candidate_feeder_ids": "101",
                    "evidence_sources": "MAIN_CBREAKER",
                    "evidence": "MAIN_CBREAKER:A-01",
                    "evidence_count": 1,
                }
            },
        },
    )
    row = report["feedline_rows"][0]
    assert row["ownership_status"] == "CONFIRMED"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert "NEARBY_DEVICE" not in row["reason"]

class IntegrationDB(OwnershipDB):
    def get_feeder_info(self, feeder_id, table_id=13500):
        for row in self.feeders.values():
            if int(row["id"]) == int(feeder_id):
                return dict(row)
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        base = 5000 if int(feeder_id) == 101 else 6000
        return "dms_section_device", [
            {"id": base + 1, "name": f"F{feeder_id}_SEC001", "feeder_id": int(feeder_id), "bv_id": 91}
        ]

    def verify_keyid(self, keyid):
        value = int(keyid)
        return {"device_id": value - (1 << 32), "tab_no": 13503, "col_no": 1}


def test_validate_file_multi_groups_feedlines_by_resolved_feeder(tmp_path):
    g = make_ring(tmp_path / "ring.g", with_nop=True)
    validator = FeederValidator(IntegrationDB(), parser=GParser())
    result = validator.validate_file(g, drawing_mode="MULTI")
    regions = result["feeder_regions"]
    assert result["drawing_type"] == "FEEDER_OWNERSHIP"
    assert {int(r["feeder_id"]) for r in regions if r.get("feeder_id")} == {101, 202}
    rows = [row for r in regions for row in r.get("feedline_rows", [])]
    assert {row.get("ownership_status") for row in rows} == {"CONFIRMED"}
    assert all(row.get("association_ready") == "YES" for row in rows)
