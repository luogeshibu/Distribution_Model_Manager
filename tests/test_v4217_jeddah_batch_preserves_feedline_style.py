from pathlib import Path


def test_jeddah_batch_no_longer_forces_feedline_solid():
    root = Path(__file__).resolve().parents[1]
    batch = (root / "src/g_file_studio/jeddah/batch_processor.py").read_text(encoding="utf-8")
    page = (root / "src/g_file_studio/ui/pages/jeddah_batch_page.py").read_text(encoding="utf-8")
    help_text = (root / "src/g_file_studio/ui/help_content.py").read_text(encoding="utf-8")

    assert "apply_jeddah_feedline_solid" not in batch
    assert "feedline_solid_applied" not in batch
    assert "将所有 FeedLine 馈线统一改成实线" not in page
    assert "将所有 &lt;FeedLine&gt; 馈线线型统一设为实线" not in help_text
    assert "Set every &lt;FeedLine&gt; to solid line style" not in help_text


def test_standalone_feedline_style_engine_is_still_available():
    root = Path(__file__).resolve().parents[1]
    style_engine = (root / "src/g_file_studio/jeddah/style_engine.py").read_text(encoding="utf-8")
    assert "def apply_jeddah_feedline_solid(" in style_engine
