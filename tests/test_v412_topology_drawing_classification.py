from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier
from dmm.domain.gfile.parser import GParser


def test_two_bus_xml_objects_do_not_force_composite(tmp_path):
    g = tmp_path / "single_with_point_bus.g"
    g.write_text(
        '''<G width="2000" height="2000"><Layer>
        <Bus id="b_main" x="100" y="200" w="500" h="6" key_name="busbarsection AJWD"/>
        <Bus id="b_point" x="700" y="800" w="6" h="6"/>
        <Text id="t1" x="250" y="150" w="100" h="20" ts="AJWD-14"/>
        <CBreaker id="br1" x="300" y="250" w="20" h="30" link="0,0,b_main;1,0,f1"/>
        <FeedLine id="f1" x="305" y="300" w="6" h="300" link="0,0,br1"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    profile = FeederModelModule._drawing_profile(g)
    assert profile["bus_count"] == 2
    assert profile["effective_busbar_count"] == 1
    assert profile["feeder_source_branch_count"] == 1
    assert profile["drawing_type"] == "SINGLE_FEEDER"


def test_multiple_independent_source_branches_are_composite(tmp_path):
    g = tmp_path / "composite.g"
    g.write_text(
        '''<G width="4000" height="2000"><Layer>
        <Bus id="b_main" x="100" y="200" w="3500" h="6" key_name="busbarsection ABH"/>
        <Text id="t1" x="500" y="150" w="100" h="20" ts="ABH-03"/>
        <Text id="t2" x="2500" y="150" w="100" h="20" ts="ABH-04"/>
        <CBreaker id="br1" x="500" y="250" w="20" h="30" link="0,0,b_main;1,0,f1"/>
        <FeedLine id="f1" x="505" y="300" w="6" h="300" link="0,0,br1"/>
        <CBreaker id="br2" x="2500" y="250" w="20" h="30" link="0,0,b_main;1,0,f2"/>
        <FeedLine id="f2" x="2505" y="300" w="6" h="300" link="0,0,br2"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    profile = FeederDrawingTopologyClassifier(GParser()).classify(g)
    assert profile["effective_busbar_count"] == 1
    assert profile["feeder_source_branch_count"] == 2
    assert profile["drawing_type"] == "MULTI_FEEDER_COMPOSITE"


def test_uploaded_ajwd_single_and_abh_composite_regression():
    single = Path("/mnt/data/$JED-CTL-AJWD-14-BAK.sln.pic(1).g")
    composite = Path("/mnt/data/JED-NTH-ABH.sln.pic(7).g")
    if not single.exists() or not composite.exists():
        return

    sp = FeederModelModule._drawing_profile(single)
    cp = FeederModelModule._drawing_profile(composite)

    assert sp["bus_count"] == 2
    assert sp["effective_busbar_count"] == 1
    assert sp["feeder_source_branch_count"] == 1
    assert sp["drawing_type"] == "SINGLE_FEEDER"

    assert cp["effective_busbar_count"] == 3
    assert cp["feeder_source_branch_count"] >= 2
    assert cp["drawing_type"] == "MULTI_FEEDER_COMPOSITE"
