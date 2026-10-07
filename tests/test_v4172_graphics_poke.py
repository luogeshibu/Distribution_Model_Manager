from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.config.defaults import DEFAULT_RMU_NAME_EXCLUSIONS, DEFAULT_RMU_NAME_POSITIONS
from dmm.domain.gfile.parser import GParser
from dmm.domain.poke.engine import (
    apply_main_feeder_pokes,
    apply_smart_rmu_pokes,
    process_poke_files,
)


class FakePokeDb:
    def find_stations_by_name_hint(self, hint, table_id=405):
        assert table_id == 405
        if str(hint).upper() == "GVCM":
            return [
                {
                    "id": 113997365567815706,
                    "code": "GVCM",
                    "name": "GVCM",
                    "graph_name": "MAK-XXX-GVCM-1.fac.pic.g",
                }
            ]
        return []

    def resolve_rmu_poke_contexts(self, names):
        contexts = {}
        for name in names:
            key = " ".join(str(name).split()).casefold()
            if key == "35020":
                contexts[key] = {
                    "combined_device_id": 1,
                    "feeder_id": 3799912185593856961,
                    "feeder_name": "AH304",
                    "station_name": "GVCM",
                    "subcontrolarea_name": "MAK-MKN",
                    "feeder_full_name": "MAK-MKN-GVCM-AH304",
                }
        return contexts, {}


def _write_main_feeder_g(path: Path):
    path.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<G>
  <Layer>
    <rect id='20000001' x='100' y='100' w='160' h='130'/>
    <CBreaker id='11000001' x='160' y='145' w='20' h='30'/>
    <Text id='50000001' x='100' y='55' w='145' h='30' ts='GVCM-AH304' lc='255,255,255' lcc='#ffffff'/>
  </Layer>
</G>
""",
        encoding="utf-8",
    )


def _write_smart_rmu_g(path: Path, *, smart: bool = True):
    smart_text = "<Text id='50000102' x='140' y='120' w='50' h='18' ts='SMART' lc='255,0,0'/>" if smart else ""
    path.write_text(
        f"""<?xml version='1.0' encoding='utf-8'?>
<G>
  <Layer>
    <rect id='20000100' x='100' y='100' w='200' h='200'/>
    <CBreakerDis id='11700100' x='135' y='150' w='25' h='25' p_NameString='Y1'/>
    <ZhaiWaiJieDiDaoZha id='18800100' x='180' y='150' w='25' h='25' p_NameString='Y1D'/>
    <BusDis id='13500100' x='220' y='150' w='25' h='25'/>
    {smart_text}
    <Text id='50000101' x='320' y='160' w='80' h='28' ts='35020' lc='255,255,255' lcc='#ffffff'/>
  </Layer>
</G>
""",
        encoding="utf-8",
    )


def _pokes(path: Path):
    root = ET.parse(path).getroot()
    return [element for element in root.iter() if element.tag.lower().endswith('poke')]


def test_main_feeder_poke_uses_405_graph_name_and_label_geometry(tmp_path):
    source = tmp_path / "ring.g"
    _write_main_feeder_g(source)
    parsed = GParser().parse(source)

    rows = apply_main_feeder_pokes(parsed, FakePokeDb(), file_name=source.name)
    assert len(rows) == 1
    assert rows[0].action == "added"
    assert rows[0].target_ahref == "MAK-XXX-GVCM-1.fac.pic.g?locateLabel=AH304&&scaleFlag=true"

    root = parsed.root
    poke = next(element for element in root.iter() if element.tag.lower() == "poke")
    assert poke.get("ahref") == rows[0].target_ahref
    assert (poke.get("x"), poke.get("y"), poke.get("w"), poke.get("h")) == (
        "100", "55", "145", "30"
    )
    assert poke.get("dmm_main_feeder_poke") == "1"
    assert poke.get("dmm_feeder_text_id") == "50000001"
    # Same invisible click-box behavior as the proven GFileStudio RMU Poke.
    assert poke.get("fm") == "0"
    assert poke.get("ls") == "0"
    assert poke.get("RectStyle") == "0"
    assert poke.get("p_RectStyle") == "0"
    assert poke.get("switchapp") == "1"
    assert poke.get("switchappflag") == "1"


def test_main_feeder_poke_rerun_reuses_existing_poke(tmp_path):
    source = tmp_path / "ring.g"
    _write_main_feeder_g(source)
    parsed = GParser().parse(source)
    db = FakePokeDb()

    first = apply_main_feeder_pokes(parsed, db, file_name=source.name)
    assert first[0].action == "added"
    # Persist once and reparse to simulate a real second run.
    ET.ElementTree(parsed.root).write(source, encoding="utf-8", xml_declaration=True)
    reparsed = GParser().parse(source)
    second = apply_main_feeder_pokes(reparsed, db, file_name=source.name)
    assert second[0].action == "unchanged"
    assert sum(1 for e in reparsed.root.iter() if e.tag.lower() == "poke") == 1


def test_smart_rmu_gets_gfilestudio_style_detail_poke(tmp_path):
    source = tmp_path / "ring.g"
    _write_smart_rmu_g(source, smart=True)
    settings = {
        "rmu_name_positions": dict(DEFAULT_RMU_NAME_POSITIONS),
        "rmu_name_exclusions": list(DEFAULT_RMU_NAME_EXCLUSIONS),
    }

    rows = apply_smart_rmu_pokes(source, FakePokeDb(), settings)
    assert len(rows) == 1
    assert rows[0].rmu_name == "35020"
    assert rows[0].action == "added"
    assert rows[0].target_ahref == "MAK-MKN-GVCM-AH304-35020.com.pic.g"

    poke = _pokes(source)[0]
    assert poke.get("gfs_rmu_poke") == "1"
    assert poke.get("gfs_rmu_name") == "35020"
    assert poke.get("gfs_rmu_text_id") == "50000101"
    assert poke.get("ahref") == "MAK-MKN-GVCM-AH304-35020.com.pic.g"
    assert (poke.get("x"), poke.get("y"), poke.get("w"), poke.get("h")) == (
        "320", "160", "80", "28"
    )
    assert poke.get("fm") == "0" and poke.get("ls") == "0"


def test_non_smart_rmu_does_not_get_poke(tmp_path):
    source = tmp_path / "ring.g"
    _write_smart_rmu_g(source, smart=False)
    settings = {
        "rmu_name_positions": dict(DEFAULT_RMU_NAME_POSITIONS),
        "rmu_name_exclusions": list(DEFAULT_RMU_NAME_EXCLUSIONS),
    }
    rows = apply_smart_rmu_pokes(source, FakePokeDb(), settings)
    assert rows == []
    assert _pokes(source) == []


def test_process_poke_files_keeps_original_untouched_and_writes_reports(tmp_path):
    source = tmp_path / "source.g"
    _write_main_feeder_g(source)
    original = source.read_bytes()

    result = process_poke_files(
        FakePokeDb(),
        [source],
        {
            "rmu_name_positions": dict(DEFAULT_RMU_NAME_POSITIONS),
            "rmu_name_exclusions": list(DEFAULT_RMU_NAME_EXCLUSIONS),
        },
        tmp_path / "g_output",
        tmp_path / "report",
        enable_main_feeder=True,
        enable_smart_rmu=False,
    )

    assert source.read_bytes() == original
    assert len(result.output_files) == 1
    assert _pokes(result.output_files[0])
    assert result.csv_path.exists()
    assert result.html_path.exists()
    assert "GVCM-AH304" in result.csv_path.read_text(encoding="utf-8-sig")
    assert "locateLabel=AH304" in result.html_path.read_text(encoding="utf-8")


def test_graphics_processing_ui_is_first_level_with_full_width_poke_page():
    source = Path(__file__).parents[1] / "src" / "dmm" / "ui" / "main_window.py"
    text = source.read_text(encoding="utf-8")
    assert '("图形处理", None, "group")' in text
    assert '("Poke 跳转", 3, "child")' in text
    assert 'secondary_title = QLabel("Poke 跳转")' in text
    assert 'setObjectName("graphicsFunctionBar")' in text
    assert 'setObjectName("graphicsSubNav")' not in text
    assert 'QGroupBox("文件来源（Poke 跳转）")' in text
    assert 'self.poke_remote_file_table = QTableWidget()' in text
    assert "PokeProcessingWorker" in text
