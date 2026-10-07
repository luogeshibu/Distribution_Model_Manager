from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.graphics_cleanup.channel_status import (
    CHANNEL_STATUS_POSITIONS,
    process_rmu_channel_status_reposition,
    reposition_channel_statuses,
)


ROOT = Path(__file__).resolve().parents[1]


def _synthetic_root(status_x=130, status_y=130):
    return ET.fromstring(
        f'''<G><Layer>
<rect id="r1" x="100" y="100" w="220" h="220" />
<BusDis id="b1" x="150" y="210" w="100" h="6" d="150,213 250,213" />
<CBreakerDis id="c1" x="190" y="180" w="40" h="40" />
<ZhaiWaiJieDiDaoZha id="g1" x="240" y="180" w="40" h="40" />
<Status id="s1" x="{status_x}" y="{status_y}" w="26" h="26" devref="#channel_status.zt.icn.g:channel_status" />
<Text id="t1" x="120" y="330" w="80" h="20" ts="KEEP" />
</Layer></G>'''
    )


def test_graphics_workspace_exposes_channel_status_operation():
    source = (ROOT / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.graphics_operation_combo.addItem("环网柜 channel_status 移动", "RMU_CHANNEL_STATUS_REPOSITION")' in source
    assert 'self._build_rmu_channel_status_panel()' in source
    assert 'G File Studio v2.18.244' in source


def test_all_gfilestudio_anchor_positions_are_available():
    assert list(CHANNEL_STATUS_POSITIONS) == [
        "top_left", "top_center", "top_right",
        "middle_left", "middle_right",
        "bottom_left", "bottom_center", "bottom_right",
    ]


def test_bottom_left_reposition_matches_gfilestudio_geometry():
    root = _synthetic_root()
    layer = root.find("Layer")
    counts = reposition_channel_statuses(layer, position="bottom_left", inner_margin=5)
    assert counts == (1, 1, 1, 0)
    status = layer.find("Status")
    assert status.get("x") == "105"
    assert status.get("y") == "289"
    # Unrelated graphics are untouched.
    text = layer.find("Text")
    assert text.get("x") == "120"
    assert text.get("y") == "330"


def test_nearby_channel_status_within_40px_is_claimed_and_moved():
    root = _synthetic_root(status_x=80, status_y=130)
    layer = root.find("Layer")
    counts = reposition_channel_statuses(layer, position="middle_right", inner_margin=5)
    assert counts == (1, 1, 1, 0)
    status = layer.find("Status")
    assert status.get("x") == "289"
    assert status.get("y") == "197"


def test_process_writes_safe_copy_and_report_without_changing_source(tmp_path):
    source = tmp_path / "sample.g"
    source.write_text(ET.tostring(_synthetic_root(), encoding="unicode"), encoding="utf-8")
    before = source.read_bytes()
    result = process_rmu_channel_status_reposition(
        [source],
        tmp_path / "out",
        tmp_path / "report",
        position="top_center",
        inner_margin=7,
    )
    assert source.read_bytes() == before
    assert result.found == 1
    assert result.moved == 1
    assert result.missing == 0
    assert result.output_files[0].exists()
    assert result.csv_path.exists()
    assert result.html_path.exists()
    out_root = ET.parse(result.output_files[0]).getroot()
    status = out_root.find("Layer/Status")
    assert status.get("x") == "197"
    assert status.get("y") == "107"
