from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.gfile.parser import Box, GObject, GParser, ParsedG, RmuFrame
from dmm.domain.rmu.validator import RmuValidator


def _validator(records):
    return RmuValidator(
        object(),
        GParser(),
        {"pwbh": {"table_id": 13533, "domain": 40}},
        element_catalog={"records": records},
    )


def _pwbh(devref, x=10, y=10, xml_id="p1"):
    return GObject(
        tag="pwbh",
        attrs={"id": xml_id, "devref": devref},
        box=Box(x, y, 5, 5),
        xml_index=1,
    )


def test_efi_discovery_uses_rmu_pwbh_efi_classification_file_name():
    validator = _validator([
        {
            "file_key": "protect_dis/Custom_EFI.pwbh.icn.g",
            "file_name": "Custom_EFI.pwbh.icn.g",
            "classification": "RMU_PWBH_EFI",
        }
    ])
    elem = _pwbh("#protect_dis/Custom_EFI.pwbh.icn.g:9001")
    assert validator._is_normal_relay_signal(elem) is True


def test_old_hardcoded_naripd_filename_is_not_a_fallback_anymore():
    validator = _validator([])
    elem = _pwbh("#protect_dis/NariPd_Normal.pwbh.icn.g:9001")
    assert validator._is_normal_relay_signal(elem) is False


def test_non_efi_classification_does_not_enter_relay_logic():
    validator = _validator([
        {
            "file_key": "protect_dis/NariPd_Normal.pwbh.icn.g",
            "classification": "OTHER_SIGNAL",
        }
    ])
    elem = _pwbh("#protect_dis/NariPd_Normal.pwbh.icn.g:9001")
    assert validator._is_normal_relay_signal(elem) is False


def test_marked_file_is_only_considered_when_instance_is_inside_current_rmu_frame():
    parser = GParser()
    validator = _validator([
        {
            "file_key": "protect_dis/NariPd_Normal.pwbh.icn.g",
            "classification": "RMU_PWBH_EFI",
        }
    ])
    frame_obj = GObject(
        tag="Rect",
        attrs={"id": "rmu-frame"},
        box=Box(0, 0, 100, 100),
        xml_index=0,
    )
    frame = RmuFrame(frame_obj)
    inside = _pwbh("#protect_dis/NariPd_Normal.pwbh.icn.g:1", 20, 20, "inside")
    outside = _pwbh("#protect_dis/NariPd_Normal.pwbh.icn.g:2", 200, 200, "outside")
    parsed = ParsedG(
        path=Path("sample.g"),
        root=ET.Element("G"),
        layer=ET.Element("Layer"),
        objects=[frame_obj, inside, outside],
    )

    in_frame = parser.find_target_objects_in_frame(parsed, frame, ["pwbh"])
    relay = [elem for elem in in_frame if validator._is_normal_relay_signal(elem)]
    assert [elem.xml_id for elem in relay] == ["inside"]
