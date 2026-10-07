from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.master_station_frames import distance_object_to_frame
from dmm.domain.gfile.parser import Box, GObject, GParser


def test_box_edge_distance_matches_minimum_rectangle_gap():
    device = Box(0, 0, 400, 100)
    long_text = Box(407, 10, 600, 40)
    assert device.edge_distance(long_text) == 7.0


def test_transformer_name_distance_uses_rectangle_edges_not_center_or_anchor():
    device = GObject("GIcon", {}, Box(0, 0, 400, 100), 1)
    text = GObject("Text", {"ts": "973248"}, Box(407, 10, 600, 40), 2)
    # Historical center->Text.x would be 207 (>200 in similar field layouts),
    # while the visual rectangle gap is only 7.
    assert TransformerParser._transformer_model_text_anchor_distance(device, text) == 7.0


def test_master_bay_title_distance_uses_rectangle_edges():
    frame = GObject("Rect", {}, Box(0, 0, 400, 100), 1)
    text = GObject("Text", {"ts": "ARF2-07"}, Box(407, 10, 600, 40), 2)
    assert distance_object_to_frame(text, frame) == 7.0


class RingDB:
    def __init__(self):
        self.feeders = {
            "ARF2-07": {
                "id": 7007,
                "name": "07",
                "display_name": "ARF2-07",
                "station_name": "ARF2",
                "st_id": 9001,
            },
            "MNA4-12": {
                "id": 4012,
                "name": "12",
                "display_name": "MNA4-12",
                "station_name": "MNA4",
                "st_id": 9002,
            },
            "GVCM-04": {
                "id": 5004,
                "name": "04",
                "display_name": "GVCM-04",
                "station_name": "GVCM",
                "st_id": 9003,
            },
        }

    def find_stations_by_name_hint(self, hint, table_id=405):
        key = str(hint).strip().upper()
        mapping = {
            "ARF2": {"id": 9001, "name": "ARF2", "code": "ARF2"},
            "MNA4": {"id": 9002, "name": "MNA4", "code": "MNA4"},
            "GVCM": {"id": 9003, "name": "GVCM", "code": "GVCM"},
        }
        return [dict(mapping[key])] if key in mapping else []

    def get_feeders_by_station(self, station_id, table_id=13500):
        return [dict(row) for row in self.feeders.values() if int(row["st_id"]) == int(station_id)]

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        row = self.feeders.get(str(hint).strip().upper())
        return [dict(row)] if row else []

    def get_feeder_info(self, feeder_id, table_id=13500):
        for row in self.feeders.values():
            if int(row["id"]) == int(feeder_id):
                return dict(row)
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", []

    def get_preferred_feeder_section_voltage(self, station_id):
        return {"bv_id": 91, "nomvol": 13.8}


def _ring_g(path: Path):
    path.write_text(
        '''<G facID=""><Layer>
        <Rect id="r1" x="0" y="0" w="400" h="120"/>
        <CBreaker id="b1" x="20" y="20" w="20" h="20"/>
        <Text id="t1" x="407" y="20" w="500" h="30" ts="ARF2-07" lc="255,255,255"/>
        <Rect id="r2" x="1000" y="0" w="400" h="120"/>
        <CBreaker id="b2" x="1020" y="20" w="20" h="20"/>
        <Text id="t2" x="1407" y="20" w="500" h="30" ts="MNA4-12" lc="255,255,255"/>
        <FeedLine id="f1" x="0" y="300" w="100" h="5" ls="2"/>
        <FeedLine id="f2" x="0" y="400" w="100" h="5" ls="2"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_makkah_feeder_selects_first_confirmed_feeder_from_current_ring(tmp_path):
    g = _ring_g(tmp_path / "ring.g")
    logs = []
    selected, candidates = FeederModelModule()._resolve_any_ring_feeder(
        RingDB(), g, {"feeder_table_id": 13500}, logs.append
    )
    assert selected["id"] == 7007
    assert {row["id"] for row in candidates} == {7007, 4012}
    assert any("全部 FeedLine" in line for line in logs)


def test_makkah_feeder_plans_all_feedlines_under_one_selected_feeder(tmp_path):
    g = _ring_g(tmp_path / "ring.g")
    reports, _summary, _rules = FeederModelModule().validate(
        RingDB(),
        [g],
        {
            "feeder_table_id": 13500,
            "section_table_id": 13503,
            "section_domain": 1,
            "auto_create_missing_sections": True,
        },
        lambda _m: None,
    )
    assert len(reports) == 1
    report = reports[0]
    assert report["feeder_id"] == 7007
    assert len(report["feedline_rows"]) == 2
    assert len(report["section_create_plan"]) == 2
    assert all(row.get("planned_section_name") for row in report["feedline_rows"])


