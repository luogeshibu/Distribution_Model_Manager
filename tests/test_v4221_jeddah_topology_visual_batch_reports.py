from pathlib import Path

from dmm.domain.graphics_cleanup.jeddah_topology_connectivity import (
    repair_jeddah_topology_connectivity,
)
from g_file_studio.models import InputMode
from g_file_studio.processors.whole_graph_topology_processor import (
    WholeGraphTopologySettings,
    process_whole_graph_topology,
)


def _write_gap_g(path: Path, offset: int = 0) -> None:
    path.write_text(
        "<D5000><Layer>"
        f'<ConnectLine id="{34000001+offset}" d="0,0 10,0" x="-3" y="-3" w="16" h="6" lc="85,170,255" lw="1" '
        f'link="0,0,{99000001+offset}" node_area="0,0,{99000001+offset}" />'
        f'<FeedLine id="{117000001+offset}" d="20,0 30,0" x="17" y="-3" w="16" h="6" lc="230,90,0" lw="2" '
        f'link="1,0,{99000002+offset}" node_area="1,0,{99000002+offset}" />'
        "</Layer></D5000>",
        encoding="utf-8",
    )


def test_single_file_report_embeds_before_after_topology_and_problem_location(tmp_path: Path):
    source = tmp_path / "one.sln.pic.g"
    _write_gap_g(source)
    out = tmp_path / "out"

    result = repair_jeddah_topology_connectivity(source, out)

    assert result.repair_count == 1
    assert result.before_svg_path.is_file()
    assert result.after_svg_path.is_file()
    assert result.html_path.is_file()

    before = result.before_svg_path.read_text(encoding="utf-8")
    after = result.after_svg_path.read_text(encoding="utf-8")
    report = result.html_path.read_text(encoding="utf-8")

    assert "#1 断点" in before
    assert "#ef4444" in before
    assert "#1 已修复" in after
    assert "#059669" in after
    assert "修复前拓扑图（问题定位）" in report
    assert "修复后拓扑图" in report
    assert result.before_svg_path.name in report
    assert result.after_svg_path.name in report
    assert "问题位置坐标" in report


def test_directory_batch_generates_per_file_reports_and_total_html_with_diagram_links(tmp_path: Path):
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    _write_gap_g(source_dir / "a.sln.pic.g", 0)
    _write_gap_g(source_dir / "b.sln.pic.g", 100)

    out = tmp_path / "run"
    result = process_whole_graph_topology(
        WholeGraphTopologySettings(
            source_path=source_dir,
            input_mode=InputMode.DIRECTORY,
            output_dir=out,
        )
    )

    report_root = out / "whole_graph_topology_report"
    summary = report_root / "jeddah_topology_batch_summary.html"
    summary_csv = report_root / "jeddah_topology_batch_summary.csv"
    assert summary.is_file()
    assert summary_csv.is_file()
    assert result.statistics["输入 G 文件数"] == 2
    assert result.statistics["成功处理"] == 2

    text = summary.read_text(encoding="utf-8")
    assert "修复前拓扑 / 问题位置" in text
    assert "修复后拓扑" in text
    assert text.count("单文件报告") >= 2

    per_file_reports = sorted(report_root.glob("files/*/jeddah_topology_connection_report.html"))
    before_svgs = sorted(report_root.glob("files/*/jeddah_topology_before.svg"))
    after_svgs = sorted(report_root.glob("files/*/jeddah_topology_after.svg"))
    assert len(per_file_reports) == 2
    assert len(before_svgs) == 2
    assert len(after_svgs) == 2
