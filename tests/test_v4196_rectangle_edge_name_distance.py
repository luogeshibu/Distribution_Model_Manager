from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import Box, GParser, box_min_edge_distance


def _catalog():
    return {
        "records": [
            {"file_name": "LBS_S.zwk.icn.g", "root_id": "LBS_S", "classification": "LBS"},
            {"file_name": "Transformer_OH.pb.icn.g", "root_id": "Transformer_OH", "classification": "TRANSFORMER_OH"},
        ]
    }


def test_rectangle_min_edge_distance_horizontal_vertical_and_diagonal():
    device = Box(100, 100, 40, 40)
    assert box_min_edge_distance(device, Box(147, 100, 500, 40)) == 7.0
    assert box_min_edge_distance(device, Box(100, 147, 60, 40)) == 7.0
    assert round(box_min_edge_distance(device, Box(143, 144, 60, 40)), 3) == 5.0


def test_pole_switch_long_name_uses_text_rectangle_edge_not_center(tmp_path):
    g = tmp_path / "pole.g"
    g.write_text(
        '''<G><Layer>
        <CBreakerDis id="sw1" x="100" y="100" w="40" h="40" devref="#LBS_S.zwk.icn.g:LBS_S"/>
        <Text id="name1" x="147" y="100" w="500" h="40" ts="LBS973248-972459" lc="255,0,0"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    row = PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]
    assert row["graphical_name"] == "LBS973248-972459"
    assert row["name_direction"] == "right"
    assert row["name_priority"] == "RIGHT"
    assert row["name_distance"] == 7.0
    assert row["name_distance_basis"] == "RECTANGLE_MIN_EDGE_DISTANCE"


def test_transformer_long_text_uses_rectangle_edge_not_center(tmp_path):
    g = tmp_path / "transformer.g"
    g.write_text(
        '''<G><Layer>
        <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
        <Text id="name1" x="147" y="100" w="500" h="40" ts="973248972459" lc="255,255,255"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    row = TransformerParser().discover_for_transformer_model(GParser().parse(g), _catalog(), {})[0][0]
    assert row["graphical_name"] == "973248972459"
    assert row["name_direction"] == "right"
    assert row["name_priority"] == "RIGHT"
    assert row["name_distance"] == 7.0
    assert row["name_distance_basis"] == "RECTANGLE_MIN_EDGE_DISTANCE"


def test_rmu_internal_breaker_name_uses_rectangle_edge_not_center(tmp_path):
    g = tmp_path / "rmu.g"
    g.write_text(
        '''<G><Layer>
        <rect id="frame" x="0" y="0" w="800" h="250"/>
        <CBreakerDis id="br1" x="100" y="100" w="40" h="40"/>
        <ZhaiWaiJieDiDaoZha id="gd1" x="200" y="100" w="20" h="20"/>
        <BusDis id="bus1" x="300" y="50" w="10" h="150"/>
        <Text id="name1" x="147" y="100" w="500" h="40" ts="Y1"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parser = GParser()
    parsed = parser.parse(g)
    frame = parser.find_rmu_frames(parsed)[0]
    breakers = parser.find_target_objects_in_frame(parsed, frame, {"CBreakerDis"})
    result = parser.resolve_breaker_graphical_names(parsed, frame, breakers, max_distance=65.0)
    assert result["br1"]["status"] == "PASS"
    assert result["br1"]["name"] == "Y1"
    assert result["br1"]["distance"] == 7.0


def test_feeder_bus_name_uses_rectangle_edge_not_center(tmp_path):
    from dmm.domain.feeder.validator import FeederValidator

    g = tmp_path / "feeder.g"
    g.write_text(
        '''<G><Layer>
        <Bus id="bus1" x="100" y="100" w="40" h="40"/>
        <Text id="name1" x="147" y="100" w="500" h="40" ts="ADEL-20"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parsed = GParser().parse(g)
    hint = FeederValidator(None, GParser()).resolve_feeder_hint(parsed)
    assert hint["hint"] == "ADEL-20"
    assert hint["distance"] == 7.0
    assert hint["source"] == "BUS_NEAREST_TEXT"
