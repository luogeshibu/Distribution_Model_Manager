from dmm.domain.gfile.parser import GParser


def _parser():
    return GParser(required_rmu_tags={
        "CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"
    })


def test_rmu_type_prefers_y_q_text_and_cross_checks_devref(tmp_path):
    g = tmp_path / "rmu.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180" p_NameString="BUS"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30" p_NameString="Y1" devref="#Load_Breaker_Switch_NON-SMART.zwk.icn.g:Load_Breaker_Switch_NON-SMART"/>
        <CBreakerDis id="c2" x="150" y="300" w="30" h="30" p_NameString="Y2" devref="#Load_Breaker_Switch_SMART.zwk.icn.g:Load_Breaker_Switch_SMART"/>
        <CBreakerDis id="c3" x="300" y="220" w="30" h="30" p_NameString="Q1" devref="#Circuit_Breaker_NO-SMART.zwk.icn.g:Circuit_Breaker_NO-SMART"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20"/>
        <Text id="t1" x="175" y="180" w="30" h="20" ts="Y1"/>
        <Text id="t2" x="175" y="300" w="30" h="20" ts="Y2"/>
        <Text id="t3" x="330" y="220" w="30" h="20" ts="Q1"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parser = _parser()
    parsed = parser.parse(g)
    frame = parser.find_rmu_frames(parsed)[0]
    info = parser.classify_rmu_type(parsed, frame)
    assert info["rmu_type"] == "2L1T"
    assert info["source"] == "TEXT_YQ"
    assert info["text_type"] == "2L1T"
    assert info["devref_type"] == "2L1T"
    assert info["consistent"] is True


def test_rmu_type_uses_any_recognized_yq_text_before_devref(tmp_path):
    g = tmp_path / "rmu.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30" devref="#Load_Breaker_Switch.zwk.icn.g:Load_Breaker_Switch"/>
        <CBreakerDis id="c2" x="150" y="300" w="30" h="30" devref="#Load_Breaker_Switch.zwk.icn.g:Load_Breaker_Switch"/>
        <CBreakerDis id="c3" x="300" y="220" w="30" h="30" devref="#Circuit_Breaker.zwk.icn.g:Circuit_Breaker"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20"/>
        <Text id="t1" x="175" y="180" w="30" h="20" ts="Y1"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parser = _parser()
    parsed = parser.parse(g)
    frame = parser.find_rmu_frames(parsed)[0]
    info = parser.classify_rmu_type(parsed, frame)
    assert info["rmu_type"] == "1L"
    assert info["source"] == "TEXT_YQ"
    assert info["devref_type"] == "2L1T"
    assert info["consistent"] is False
