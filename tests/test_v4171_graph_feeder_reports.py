from pathlib import Path
import csv

from dmm.domain.feeder.ring_discovery import (
    attach_makkah_ring_feeder_inventory,
    compare_makkah_ring_feeders,
)
from dmm.infrastructure.reporting import writer


class GraphFeederDB:
    def __init__(self):
        self.stations = {
            "GVCM": {"id": 101, "name": "GVCM", "code": "GVCM"},
            "ARF4": {"id": 102, "name": "ARF4", "code": "ARF4"},
        }
        self.feeders = {
            101: [{"id": 1001, "name": "AH304", "code": "AH304", "st_id": 101}],
            102: [
                {"id": 2001, "name": "AH348", "code": "AH348", "st_id": 102},
                {"id": 2002, "name": "AH3101", "code": "AH3101", "st_id": 102},
            ],
        }

    def find_stations_by_name_hint(self, hint, table_id=405):
        row = self.stations.get(str(hint).strip().upper())
        return [dict(row)] if row else []

    def get_feeders_by_station(self, station_id, table_id=13500):
        return [dict(row) for row in self.feeders.get(int(station_id), [])]


def _write_graph(path: Path):
    path.write_text(
        '''<G facID=""><Layer>
        <Rect id="r1" x="0" y="0" w="300" h="140"/><CBreaker id="b1" x="20" y="20" w="20" h="20"/><Text id="t1" x="305" y="20" w="240" h="30" ts="GVCM-AH304" lc="255,255,255"/>
        <Rect id="r2" x="800" y="0" w="300" h="140"/><CBreaker id="b2" x="820" y="20" w="20" h="20"/><Text id="t2" x="1105" y="20" w="240" h="30" ts="ARF4-AH348" lc="255,255,255"/>
        <Rect id="r3" x="1600" y="0" w="300" h="140"/><CBreaker id="b3" x="1620" y="20" w="20" h="20"/><Text id="t3" x="1905" y="20" w="240" h="30" ts="ARF4-AH3101" lc="255,255,255"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_graph_feeder_comparison_lists_every_graph_feeder(tmp_path):
    rows = compare_makkah_ring_feeders(GraphFeederDB(), _write_graph(tmp_path / "ring.g"))
    assert [row["graph_feeder"] for row in rows] == [
        "GVCM-AH304", "ARF4-AH348", "ARF4-AH3101"
    ]
    assert [row["db_feeder_id"] for row in rows] == [1001, 2001, 2002]
    assert {row["match_result"] for row in rows} == {"MATCH"}


def test_graph_feeder_comparison_keeps_not_found_row(tmp_path):
    g = _write_graph(tmp_path / "ring.g")
    db = GraphFeederDB()
    db.feeders[102] = [db.feeders[102][0]]
    rows = compare_makkah_ring_feeders(db, g)
    missing = next(row for row in rows if row["graph_feeder"] == "ARF4-AH3101")
    assert missing["db_feeder_id"] == ""
    assert missing["match_result"] == "FEEDER_NOT_FOUND"


def test_common_graph_feeder_html_and_csv_are_result_only(tmp_path):
    reports = [{
        "report_type": "FEEDER",
        "file_name": "ring.g",
        "feedline_rows": [],
        "section_create_plan": [],
        "association_eligible": False,
        "status": "WARN",
        "severity": "TEST",
        "reason": "",
    }]
    inventory = {
        str(tmp_path / "ring.g"): [
            {
                "file_name": "ring.g",
                "graph_feeder": "GVCM-AH304",
                "db_feeder_id": 1001,
                "db_code": "AH304",
                "db_name": "AH304",
                "db_st_id": 101,
                "match_result": "MATCH",
            }
        ]
    }
    attach_makkah_ring_feeder_inventory(reports, inventory)

    html_path = tmp_path / "report.html"
    writer.export_html_bundle(
        reports,
        html_path,
        {"FeedLine": {"table_id": 13503, "domain": 1}},
    )
    html = html_path.read_text(encoding="utf-8")
    assert "图形馈线" in html
    assert "GVCM-AH304" in html
    assert "数据库匹配结果" in html
    assert "馈线识别依据" not in html
    assert "馈线归属方法" not in html

    paths = writer.export_csv_bundle(reports, tmp_path / "report.csv")
    assert len(paths) == 2  # existing return contract is unchanged
    graph_csv = tmp_path / "report_图形馈线.csv"
    assert graph_csv.exists()
    with graph_csv.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["图形馈线"] == "GVCM-AH304"
    assert rows[0]["数据库匹配结果"] == "MATCH"
