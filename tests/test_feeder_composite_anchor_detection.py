
from pathlib import Path

from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser


class NoMatchDB:
    def find_feeders_by_name_hint(self, hint, table_id=13500):
        return []


def test_composite_layout_uses_g_titles_even_when_db_anchor_lookup_returns_zero(
    tmp_path,
):
    g = tmp_path / "combined.g"
    g.write_text(
        """<G width="8000" height="1200"><Layer>
        <Bus id="b1" x="100" y="100" w="7600" h="6"/>
        <Text id="t1" x="400" y="50" w="100" h="20" ts="ABH-03"/>
        <Text id="t2" x="2400" y="50" w="100" h="20" ts="ABH-04"/>
        <Text id="t3" x="4400" y="50" w="100" h="20" ts="ABH-05"/>
        <FeedLine id="f1" x="450" y="200" w="6" h="100" keyid=""/>
        <FeedLine id="f2" x="2450" y="200" w="6" h="100" keyid=""/>
        <FeedLine id="f3" x="4450" y="200" w="6" h="100" keyid=""/>
        </Layer></G>""",
        encoding="utf-8",
    )

    validator = FeederValidator(NoMatchDB(), GParser())
    parsed = GParser().parse(g)
    layout = validator.detect_drawing_layout(parsed, "AUTO")

    assert layout["drawing_type"] == "MULTI_FEEDER_COMPOSITE"
    assert [x["hint"] for x in layout["anchors"]] == [
        "ABH-03",
        "ABH-04",
        "ABH-05",
    ]
    assert layout["db_resolved_anchor_count"] == 0


def test_bay_no_annotation_does_not_create_extra_feeder_region(tmp_path):
    g = tmp_path / "combined.g"
    g.write_text(
        """<G width="5000" height="1200"><Layer>
        <Bus id="b1" x="100" y="100" w="4600" h="6"/>
        <Text id="t1" x="500" y="50" w="100" h="20" ts="ABH-17"/>
        <Text id="t2" x="1800" y="45" w="150" h="40" ts="BAY NO&#10;ABH-17"/>
        <Text id="t3" x="2800" y="50" w="100" h="20" ts="ABH-18"/>
        <FeedLine id="f1" x="550" y="250" w="6" h="100" keyid=""/>
        <FeedLine id="f2" x="2850" y="250" w="6" h="100" keyid=""/>
        </Layer></G>""",
        encoding="utf-8",
    )

    validator = FeederValidator(NoMatchDB(), GParser())
    parsed = GParser().parse(g)
    layout = validator.detect_drawing_layout(parsed, "AUTO")

    assert layout["drawing_type"] == "MULTI_FEEDER_COMPOSITE"
    assert [x["hint"] for x in layout["anchors"]] == [
        "ABH-17",
        "ABH-18",
    ]


def test_clean_duplicate_title_is_preserved_and_marked_duplicate(tmp_path):
    g = tmp_path / "combined.g"
    g.write_text(
        """<G width="6000" height="1200"><Layer>
        <Bus id="b1" x="100" y="100" w="5600" h="6"/>
        <Text id="t1" x="500" y="50" w="100" h="20" ts="ABH-26"/>
        <Text id="t2" x="2500" y="50" w="100" h="20" ts="ABH-26"/>
        <Text id="t3" x="4500" y="50" w="100" h="20" ts="ABH-28"/>
        <FeedLine id="f1" x="550" y="250" w="6" h="100" keyid=""/>
        <FeedLine id="f2" x="2550" y="250" w="6" h="100" keyid=""/>
        <FeedLine id="f3" x="4550" y="250" w="6" h="100" keyid=""/>
        </Layer></G>""",
        encoding="utf-8",
    )

    validator = FeederValidator(NoMatchDB(), GParser())
    parsed = GParser().parse(g)
    layout = validator.detect_drawing_layout(parsed, "AUTO")

    duplicated = [
        x for x in layout["anchors"]
        if x["hint"] == "ABH-26"
    ]
    assert len(duplicated) == 2
    assert all(x["duplicate_feeder_anchor"] for x in duplicated)
