from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from g_file_studio.engines.rmu_efi_engine import EARTH_DEVREF, NORMAL_DEVREF, add_rmu_efi_normal_icons
from g_file_studio.models import InputMode
from g_file_studio.processors.rmu_efi_processor import RmuEfiSettings, process_rmu_efi
from g_file_studio.services.id_rule_service import IdRule, IdRuleService


def _rule() -> IdRule:
    return IdRule("pwbh", "182", 9)


def _write_rmu(path: Path, *, with_normal: bool, with_earth: bool = True) -> None:
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "rect", id="2000001", x="100", y="200", w="220", h="220", ls="2")
    ET.SubElement(layer, "BusDis", id="38000001", x="130", y="310", w="160", h="6")
    ET.SubElement(layer, "CBreakerDis", id="117000001", x="150", y="260", w="28", h="30")
    ET.SubElement(layer, "CBreakerDis", id="117000002", x="240", y="260", w="28", h="30")
    if with_earth:
        ET.SubElement(layer, "pwbh", id="182000001", x="195", y="226", w="30", h="30", devref=EARTH_DEVREF)
    if with_normal:
        ET.SubElement(
            layer,
            "pwbh",
            id="182000002",
            x="200",
            y="210",
            w="36",
            h="36",
            devref=NORMAL_DEVREF,
            tfr="rotate(0) scale(2,2)",
        )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_existing_normal_is_absolute_noop_even_without_earth(tmp_path: Path) -> None:
    source = tmp_path / "already-correct.g"
    _write_rmu(source, with_normal=True, with_earth=False)
    before = source.read_bytes()
    tree = ET.parse(source)

    result = add_rmu_efi_normal_icons(tree, file_name=source.name, pwbh_id_rule=_rule())

    assert result.added == 0
    assert result.already_present == 1
    assert result.skipped_no_earth == 0
    assert result.rows[0]["result"] == "ALREADY_PRESENT_NO_CHANGE"
    # The engine must not mutate an already-correct cabinet.
    after_tree = ET.tostring(tree.getroot(), encoding="utf-8")
    original_tree = ET.tostring(ET.parse(source).getroot(), encoding="utf-8")
    assert after_tree == original_tree
    assert source.read_bytes() == before


def test_processor_outputs_only_files_that_were_modified(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    unchanged = source_dir / "all-good.g"
    changed = source_dir / "needs-efi.g"
    _write_rmu(unchanged, with_normal=True)
    _write_rmu(changed, with_normal=False)
    unchanged_before = unchanged.read_bytes()

    monkeypatch.setattr(IdRuleService, "load_rules", lambda self: {"pwbh": _rule()})
    logs: list[str] = []
    result = process_rmu_efi(
        RmuEfiSettings(
            source_path=source_dir,
            input_mode=InputMode.DIRECTORY,
            output_dir=output_dir,
        ),
        log=logs.append,
    )

    assert result.success
    assert not (output_dir / unchanged.name).exists()
    assert (output_dir / changed.name).exists()
    assert unchanged.read_bytes() == unchanged_before
    assert result.statistics["实际修改并输出 G 文件"] == 1
    assert result.statistics["未修改且未输出 G 文件"] == 1
    assert any("all-good.g] 未修改，不输出 G 文件" in line for line in logs)
    assert any("needs-efi.g] 已修改并输出 G" in line for line in logs)

    report = output_dir / "rmu-efi-report.csv"
    assert report.exists()
    with report.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    summaries = {row["file"]: row["result"] for row in rows if row["result"].startswith("FILE_")}
    assert summaries["all-good.g"] == "FILE_UNCHANGED_NO_G_OUTPUT"
    assert summaries["needs-efi.g"] == "FILE_MODIFIED_OUTPUT"
