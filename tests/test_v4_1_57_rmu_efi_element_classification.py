from dmm.domain.gfile.element_catalog import devref_has_classification
from dmm.domain.gfile.parser import Box, GObject
from dmm.domain.rmu.validator import RmuValidator


class Dummy:
    pass


def _record(file_name, classification):
    return {
        "file_name": file_name,
        "file_key": f"protect_dis/{file_name}",
        "root_id": file_name.split(".", 1)[0],
        "classification": classification,
    }


def _pwbh(devref):
    return GObject(
        "pwbh",
        {"id": "1", "devref": devref},
        Box(0, 0, 18, 18),
        1,
    )


def _validator(catalog):
    return RmuValidator(
        db=Dummy(),
        parser=Dummy(),
        device_rules={},
        element_catalog=catalog,
    )


def test_classification_match_does_not_depend_on_historical_filename():
    catalog = {"records": [
        _record("Renamed_EFI.pwbh.icn.g", "RMU_PWBH_EFI"),
    ]}
    assert devref_has_classification(
        "#Renamed_EFI.pwbh.icn.g:Renamed_EFI",
        catalog,
        "RMU_PWBH_EFI",
    )
    assert _validator(catalog)._is_efi_relay_signal(
        _pwbh("#Renamed_EFI.pwbh.icn.g:Renamed_EFI")
    )


def test_multiple_files_can_share_rmu_pwbh_efi_classification():
    catalog = {"records": [
        _record("EFI_A.pwbh.icn.g", "RMU_PWBH_EFI"),
        _record("EFI_B.pwbh.icn.g", "RMU_PWBH_EFI"),
        _record("Other.pwbh.icn.g", "OTHER"),
    ]}
    validator = _validator(catalog)
    assert validator._is_efi_relay_signal(_pwbh("#EFI_A.pwbh.icn.g:EFI_A"))
    assert validator._is_efi_relay_signal(_pwbh("#EFI_B.pwbh.icn.g:EFI_B"))
    assert not validator._is_efi_relay_signal(_pwbh("#Other.pwbh.icn.g:Other"))


def test_historical_filename_is_not_special_without_classification():
    catalog = {"records": [
        _record("NariPd_Normal.pwbh.icn.g", ""),
        _record("New_EFI.pwbh.icn.g", "RMU_PWBH_EFI"),
    ]}
    validator = _validator(catalog)
    assert not validator._is_efi_relay_signal(
        _pwbh("#NariPd_Normal.pwbh.icn.g:NariPd_Normal")
    )
    assert validator._is_efi_relay_signal(
        _pwbh("#New_EFI.pwbh.icn.g:New_EFI")
    )


def test_non_pwbh_object_never_becomes_rmu_efi_even_if_catalog_marked():
    catalog = {"records": [_record("EFI_A.pwbh.icn.g", "RMU_PWBH_EFI")]}
    obj = GObject(
        "Text",
        {"id": "2", "devref": "#EFI_A.pwbh.icn.g:EFI_A"},
        Box(0, 0, 10, 10),
        2,
    )
    assert not _validator(catalog)._is_efi_relay_signal(obj)


def test_same_basename_in_multiple_catalog_folders_accepts_marked_record():
    catalog = {"records": [
        {
            "file_name": "NariPd_Normal.pwbh.icn.g",
            "file_key": "indicator_dis/NariPd_Normal.pwbh.icn.g",
            "classification": "",
        },
        {
            "file_name": "NariPd_Normal.pwbh.icn.g",
            "file_key": "protect_dis/NariPd_Normal.pwbh.icn.g",
            "classification": "RMU_PWBH_EFI",
        },
    ]}
    validator = _validator(catalog)
    assert validator._is_efi_relay_signal(
        _pwbh("#NariPd_Normal.pwbh.icn.g:NariPd_Normal")
    )
