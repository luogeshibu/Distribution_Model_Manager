from dmm.domain.gfile.parser import GParser


def _parser():
    return GParser(required_rmu_tags={
        "CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"
    })


def test_rmu_type_cross_checks_text_and_site_neutral_devref_templates(tmp_path):
    g = tmp_path / "rmu.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180" p_NameString="BUS"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30" p_NameString="Y1" devref="#ANY_SITE_L_TEMPLATE.zwk.icn.g:ANY_SITE_L_TEMPLATE"/>
        <CBreakerDis id="c2" x="150" y="300" w="30" h="30" p_NameString="Y2" devref="#ANY_SITE_L_TEMPLATE.zwk.icn.g:ANY_SITE_L_TEMPLATE"/>
        <CBreakerDis id="c3" x="300" y="220" w="30" h="30" p_NameString="Q1" devref="#COMPLETELY_DIFFERENT_NAME.zwk.icn.g:COMPLETELY_DIFFERENT_NAME"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20" devref="#RMU_ES.zwjddz.icn.g:RMU_ES"/>
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
    assert info["devref_status"] == "PASS"
    assert info["devref_templates_y"] == ["ANY_SITE_L_TEMPLATE"]
    assert info["devref_templates_q"] == ["COMPLETELY_DIFFERENT_NAME"]
    # Ground-disconnector devref must never participate in RMU type detection.
    all_templates = info["devref_templates_y"] + info["devref_templates_q"]
    assert "RMU_ES" not in all_templates


def test_rmu_type_uses_valid_devref_when_visible_text_is_incomplete(tmp_path):
    g = tmp_path / "rmu.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30" p_NameString="Y1" devref="#SITE_A.zwk.icn.g:SITE_A"/>
        <CBreakerDis id="c2" x="150" y="300" w="30" h="30" p_NameString="Y2" devref="#SITE_A.zwk.icn.g:SITE_A"/>
        <CBreakerDis id="c3" x="300" y="220" w="30" h="30" p_NameString="Q1" devref="#SITE_B.zwk.icn.g:SITE_B"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20" devref="#GROUND_ANY_NAME.zwk.icn.g:GROUND_ANY_NAME"/>
        <Text id="t1" x="175" y="180" w="30" h="20" ts="Y1"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parser = _parser()
    parsed = parser.parse(g)
    frame = parser.find_rmu_frames(parsed)[0]
    info = parser.classify_rmu_type(parsed, frame)
    assert info["rmu_type"] == "2L1T"
    assert info["source"] == "DEVREF"
    assert info["text_type"] == "1L"
    assert info["devref_type"] == "2L1T"
    assert info["consistent"] is False
    assert info["devref_status"] == "PASS"


def test_same_y_role_must_not_mix_devref_templates(tmp_path):
    g = tmp_path / "mixed_y.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30" p_NameString="Y1" devref="#RMU_LBS_NON.zwk.icn.g:RMU_LBS_NON"/>
        <CBreakerDis id="c2" x="150" y="300" w="30" h="30" p_NameString="Y2" devref="#RMU_LBS_S.zwk.icn.g:RMU_LBS_S"/>
        <CBreakerDis id="c3" x="300" y="220" w="30" h="30" p_NameString="Q1" devref="#RMU_BRK_NON.zwk.icn.g:RMU_BRK_NON"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="130" y="180" w="20" h="20" devref="#RMU_ES.zwjddz.icn.g:RMU_ES"/>
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
    # Invalid devref structure is not guessed from template words.
    assert info["devref_type"] == "UNKNOWN"
    assert info["devref_status"] == "WARN"
    assert info["consistent"] is False
    # Valid visible Y/Q text can still provide the display type.
    assert info["rmu_type"] == "2L1T"
    assert info["source"] == "TEXT_YQ"
    assert "Y类CBreakerDis的devref模板不一致" in info["devref_reason"]


def test_y_and_q_using_same_devref_is_ambiguous(tmp_path):
    g = tmp_path / "same_template.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="100" y="100" w="300" h="300"/>
        <BusDis id="b1" x="240" y="180" w="8" h="180"/>
        <CBreakerDis id="c1" x="150" y="180" w="30" h="30" p_NameString="Y1" devref="#ONE_TEMPLATE.zwk.icn.g:ONE_TEMPLATE"/>
        <CBreakerDis id="c2" x="150" y="300" w="30" h="30" p_NameString="Y2" devref="#ONE_TEMPLATE.zwk.icn.g:ONE_TEMPLATE"/>
        <CBreakerDis id="c3" x="300" y="220" w="30" h="30" p_NameString="Q1" devref="#ONE_TEMPLATE.zwk.icn.g:ONE_TEMPLATE"/>
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
    assert info["devref_type"] == "UNKNOWN"
    assert info["devref_status"] == "WARN"
    assert "Y类与Q类CBreakerDis使用相同devref模板" in info["devref_reason"]
