from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.jeddah_topology_connectivity import (
    repair_jeddah_topology_connectivity,
)


def _by_id(root: ET.Element, xml_id: str) -> ET.Element:
    return next(element for element in root.iter() if element.get("id") == xml_id)


def test_jeddah_repairs_connection_gaps_without_feeder_nop_or_database(tmp_path: Path):
    source = tmp_path / "jeddah.sln.pic.g"
    source.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <ConnectLine id="c1" d="0,50 0,0" link="1,0,dummy_c1" node_area="1,0,dummy_c1" />
  <FeedLine id="f1" d="0,61 0,100" link="1,0,dummy_f1" node_area="1,0,dummy_f1" />

  <ConnectLine id="c2" d="100,50 100,0" link="1,0,dummy_c2" node_area="1,0,dummy_c2" />
  <ConnectLine id="c3" d="100,51 100,100" link="1,0,dummy_c3" node_area="1,0,dummy_c3" />

  <!-- Deliberate switch-like open contact: 18G must never be bridged. -->
  <ConnectLine id="switch_a" d="200,50 200,0" link="1,0,dummy_a" node_area="1,0,dummy_a" />
  <ConnectLine id="switch_b" d="200,68 200,100" link="1,0,dummy_b" node_area="1,0,dummy_b" />

  <Text id="feeder_name" ts="AH999" x="0" y="0" />
  <Text id="nop" ts="N.O.P" x="300" y="300" />
</Layer></G>
""",
        encoding="utf-8",
    )

    result = repair_jeddah_topology_connectivity(source, tmp_path / "report")

    assert result.repair_count == 2
    assert result.geometry_repair_count == 2
    assert result.remaining_candidate_count == 0
    assert result.unresolved_count == 0
    assert result.fixed_g_path is not None and result.fixed_g_path.is_file()

    tree = ET.parse(result.fixed_g_path)
    root = tree.getroot()
    c1 = _by_id(root, "c1")
    f1 = _by_id(root, "f1")
    c2 = _by_id(root, "c2")
    c3 = _by_id(root, "c3")
    switch_a = _by_id(root, "switch_a")
    switch_b = _by_id(root, "switch_b")

    # ConnectLine↔FeedLine 11G break is physically closed and topology refs are reciprocal.
    assert f1.get("d", "").startswith("0,50")
    assert "c1" in f1.get("link", "") and "f1" in c1.get("link", "")
    assert "c1" in f1.get("node_area", "") and "f1" in c1.get("node_area", "")

    # Tiny 1G collinear ConnectLine split is also closed.
    assert c3.get("d", "").startswith("100,50")
    assert "c2" in c3.get("link", "") and "c3" in c2.get("link", "")

    # 18G switch/contact gap remains untouched so the repair cannot bypass a switch symbol.
    assert switch_a.get("d") == "200,50 200,0"
    assert switch_b.get("d") == "200,68 200,100"
    assert "switch_b" not in switch_a.get("link", "")
    assert "switch_a" not in switch_b.get("link", "")

    # Feeder-name/NOP text is irrelevant to this connectivity-only engine and stays unchanged.
    assert _by_id(root, "feeder_name").get("ts") == "AH999"
    assert _by_id(root, "nop").get("ts") == "N.O.P"

    with result.csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert {frozenset((row["left_tag"], row["right_tag"])) for row in rows} == {
        frozenset(("ConnectLine", "FeedLine")),
        frozenset(("ConnectLine", "ConnectLine")),
    }


def test_connectivity_module_has_no_feeder_nop_or_database_dependency():
    source = Path(
        "src/dmm/domain/graphics_cleanup/jeddah_topology_connectivity.py"
    ).read_text(encoding="utf-8")
    assert "analyze_whole_graph_topology" not in source
    assert "FeederOwnershipResolver" not in source
    assert "from dmm.infrastructure" not in source
    assert "import cx_Oracle" not in source and "import oracledb" not in source
