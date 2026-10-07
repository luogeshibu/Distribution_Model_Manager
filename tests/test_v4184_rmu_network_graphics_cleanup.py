from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.graphics_cleanup.engine import (
    FIXED_RMU_NETWORK_STATUS_DEVREFS,
    process_rmu_network_status_cleanup,
)


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_workspace_has_cleanup_operation():
    source = _source()
    assert 'self.graphics_operation_combo.addItem("Poke 跳转处理", "POKE")' in source
    assert 'self.graphics_operation_combo.addItem("环网柜网络图元清理", "RMU_NETWORK_CLEANUP")' in source
    assert 'self._build_rmu_network_cleanup_panel()' in source
    assert 'box = QGroupBox("文件来源（图形工作区）")' in source


def test_fixed_cleanup_devrefs_include_field_names_and_compat_alias():
    assert "#NariPd_Generator.zt.icn.g:NariPd_Generator" in FIXED_RMU_NETWORK_STATUS_DEVREFS
    assert "#NariPd_Temporary_Cable.zt.icn.g:NariPd_Temporary_Cable" in FIXED_RMU_NETWORK_STATUS_DEVREFS
    assert "#NariPd_General_Note.zt.icn.g:NariPd_General_Note" in FIXED_RMU_NETWORK_STATUS_DEVREFS
    assert "#NariPd_General_Note.zt.icg.g:NariPd_General_Note" in FIXED_RMU_NETWORK_STATUS_DEVREFS


def test_cleanup_removes_only_fixed_status_elements(tmp_path):
    source = tmp_path / "sample.g"
    source.write_text(
        '''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <Status id="1" p_NameString="G" devref="#NariPd_Generator.zt.icn.g:NariPd_Generator" />
  <Status id="2" p_NameString="L" devref="#NariPd_Temporary_Cable.zt.icn.g:NariPd_Temporary_Cable" />
  <Status id="3" p_NameString="N" devref="#NariPd_General_Note.zt.icn.g:NariPd_General_Note" />
  <Status id="4" p_NameString="OTHER" devref="#channel_status.zt.icn.g:channel_status" />
  <Text id="5" devref="#NariPd_Generator.zt.icn.g:NariPd_Generator" ts="do not remove non-Status" />
</Layer></G>''',
        encoding="utf-8",
    )
    result = process_rmu_network_status_cleanup(
        [source], tmp_path / "out", tmp_path / "report"
    )
    assert result.removed == 3
    target = result.output_files[0]
    root = ET.parse(target).getroot()
    ids = {element.get("id") for element in root.iter()}
    assert {"1", "2", "3"}.isdisjoint(ids)
    assert "4" in ids
    assert "5" in ids
    assert source.read_text(encoding="utf-8").count("NariPd_Generator.zt.icn.g") == 2
    assert result.csv_path.exists()
    assert result.html_path.exists()


def test_cleanup_accepts_general_note_icg_compat_alias(tmp_path):
    source = tmp_path / "legacy.g"
    source.write_text(
        '''<?xml version="1.0" encoding="utf-8"?>
<G><Layer><Status id="9" devref="#NariPd_General_Note.zt.icg.g:NariPd_General_Note" /></Layer></G>''',
        encoding="utf-8",
    )
    result = process_rmu_network_status_cleanup(
        [source], tmp_path / "out", tmp_path / "report"
    )
    assert result.removed == 1
    assert list(ET.parse(result.output_files[0]).getroot().iter("Status")) == []
