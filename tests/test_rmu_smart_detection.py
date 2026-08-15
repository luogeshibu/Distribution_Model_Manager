
from dmm.domain.gfile.parser import GParser


def _parser():
    return GParser(
        required_rmu_tags={
            "CBreakerDis",
            "ZhaiWaiJieDiDaoZha",
            "BusDis",
        },
        label_regex=r"^[A-Za-z0-9_-]+$",
    )


def test_smart_and_smr_are_globally_assigned_to_nearest_rmu(tmp_path):
    g = tmp_path / "smart.g"
    g.write_text(
        """<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20"/>
        <Text id="smart1" x="220" y="120" w="80" h="20" ts="SMART"/>
        <Text id="smr1" x="40" y="230" w="50" h="20" ts="SMR"/>

        <Rect id="r2" x="900" y="100" w="300" h="300"/>
        <BusDis id="b2" x="1040" y="180" w="8" h="180"/>
        <CBreakerDis id="c2" x="950" y="180" w="30" h="30"/>
        <ZhaiWaiJieDiDaoZha id="z2" x="930" y="180" w="20" h="20"/>
        </Layer></G>""",
        encoding="utf-8",
    )

    parser = _parser()
    parsed = parser.parse(g)
    frames = parser.find_rmu_frames(parsed)
    result = parser.assign_rmu_smart_markers_globally(parsed, frames)

    assert result["r1"]["is_smart"] is True
    assert result["r1"]["marker_types"] == ["SMART", "SMR"]
    assert len(result["r1"]["markers"]) == 2

    assert result["r2"]["is_smart"] is False
    assert result["r2"]["marker_types"] == []


def test_smr_outside_is_assigned_by_nearest_distance_without_cutoff(tmp_path):
    g = tmp_path / "smr.g"
    g.write_text(
        """<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20"/>

        <Rect id="r2" x="3000" y="100" w="300" h="300"/>
        <BusDis id="b2" x="3140" y="180" w="8" h="180"/>
        <CBreakerDis id="c2" x="3050" y="180" w="30" h="30"/>
        <ZhaiWaiJieDiDaoZha id="z2" x="3030" y="180" w="20" h="20"/>

        <Text id="smr2" x="3550" y="200" w="50" h="20" ts="SMR"/>
        </Layer></G>""",
        encoding="utf-8",
    )

    parser = _parser()
    parsed = parser.parse(g)
    frames = parser.find_rmu_frames(parsed)
    result = parser.assign_rmu_smart_markers_globally(parsed, frames)

    assert result["r2"]["is_smart"] is True
    assert result["r2"]["marker_types"] == ["SMR"]
    assert result["r1"]["is_smart"] is False
