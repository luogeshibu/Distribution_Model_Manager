from pathlib import Path

from dmm.application.modules.pole_switch import PoleSwitchModelModule, PoleSwitchParser
from dmm.domain.gfile.parser import GParser


def _catalog(classification="LBS"):
    return {
        "records": [
            {
                "file_name": "custom_switch.g",
                "root_id": "CUSTOM_ROOT",
                "classification": classification,
            }
        ]
    }


def _write(path: Path, tag: str = "AnyFutureSwitchElement") -> Path:
    path.write_text(
        f'''<G><Layer>
          <{tag} id="sw1" x="100" y="100" w="20" h="20" devref="#custom_switch.g:CUSTOM_ROOT" keyid=""/>
          <Text id="name1" x="135" y="100" w="80" h="20" ts="LBS-2385" lc="170,0,0"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_pole_switch_recognition_depends_on_classification_not_xml_tag(tmp_path):
    g_file = _write(tmp_path / "custom.g", tag="AnyFutureSwitchElement")
    rows = PoleSwitchParser().discover(
        GParser().parse(g_file),
        _catalog("LBS"),
        {},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["object_type"] == "AnyFutureSwitchElement"
    assert row["xml_id"] == "sw1"
    assert row["device_family"] == "LBS"
    assert row["graphical_name"] == "LBS-2385"
    assert row["name_direction"] == "right"


def test_same_arbitrary_xml_tag_is_ignored_without_lbs_sec_ar_classification(tmp_path):
    g_file = _write(tmp_path / "not_switch.g", tag="AnyFutureSwitchElement")
    rows = PoleSwitchParser().discover(
        GParser().parse(g_file),
        _catalog("OTHER_DEVICE"),
        {},
    )
    assert rows == []


def test_preview_writeback_uses_real_xml_tag_not_cbreakerdis(tmp_path, monkeypatch):
    g_file = _write(tmp_path / "preview.g", tag="FuturePoleDevice")
    module = PoleSwitchModelModule()
    validated_row = {
        "object_type": "FuturePoleDevice",
        "xml_id": "sw1",
        "association_ready": "YES",
        "writeback_needed": "YES",
        "selected_device_name": "LBS-2385",
        "db_device_id": 123,
        "expected_keyid": 456,
        "db_bv_id": "789",
    }
    report = {
        "g_file": str(g_file),
        "pole_switch_rows": [validated_row],
    }

    monkeypatch.setattr(
        module,
        "validate",
        lambda db, files, settings, log_callback, progress_callback=None: (
            [report],
            {},
            module._rules(),
        ),
    )

    preview = module.preview_association(None, [g_file], {}, lambda _msg: None)
    change = preview["changes_by_file"][str(g_file)][0]
    assert change["tag"] == "FuturePoleDevice"
    assert change["xml_id"] == "sw1"


def test_pole_switch_logic_description_says_xml_tag_is_not_a_filter():
    source = Path("src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
    assert "不限制它在 G 文件里使用 CBreakerDis、CBreaker 或其它 XML 元素" in source
    assert "XML 元素类型不作为过滤条件" in source
