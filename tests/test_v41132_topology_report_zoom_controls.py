from pathlib import Path

from dmm.domain.graphics_cleanup.whole_graph_topology import process_whole_graph_topology_analysis


def _write_simple_fixture(path: Path):
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<G><Layer>
<FeedLine id=\"fl1\" x=\"0\" y=\"97\" w=\"200\" h=\"6\" d=\"0,100 200,100\"/>
<Text id=\"feeder\" x=\"10\" y=\"45\" w=\"120\" h=\"30\" ts=\"TEST-AH301\" lc=\"255,255,255\"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_before_and_after_topology_images_have_independent_zoom_controls(tmp_path):
    source = tmp_path / "simple.sln.pic.g"
    _write_simple_fixture(source)
    result = process_whole_graph_topology_analysis([source], tmp_path / "report")
    html = result.html_path.read_text(encoding="utf-8")

    assert html.count("data-topology-viewer") >= 2
    assert html.count("data-zoom-action='out'") == 2
    assert html.count("data-zoom-action='in'") == 2
    assert html.count("data-zoom-action='reset'") == 2
    assert html.count("data-zoom-action='fit'") == 2
    assert html.count("data-zoom-action='fullscreen'") == 2
    assert "Ctrl+鼠标滚轮" in html
    assert "const STEP=20, MIN=20, MAX=400" in html
    assert "viewer.dataset.zoom" in html
    assert "requestFullscreen" in html


def test_version_is_41132():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
