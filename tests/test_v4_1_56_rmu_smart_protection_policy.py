from pathlib import Path

from dmm.application.modules.rmu import RmuModelModule
from dmm.config.defaults import resolve_rmu_name_positions
from dmm.domain.gfile.parser import Box, GObject
from dmm.domain.rmu.validator import RmuValidator
from dmm.infrastructure.gfile.writeback import GWriteBackService


class Dummy:
    pass


def make_relay(attrs):
    base = {
        "id": "182000005",
        "devref": "#NariPd_Normal.pwbh.icn.g:NariPd_Normal",
        "key_name1": "",
    }
    base.update(attrs)
    return GObject("pwbh", base, Box(10, 10, 36, 36), 1)


def make_validator(scope="SMART_ONLY"):
    return RmuValidator(
        db=Dummy(),
        parser=Dummy(),
        device_rules={},
        protection_scope=scope,
    )


def test_rmu_cabinet_name_direction_is_top_right_global():
    assert resolve_rmu_name_positions("FIXED", {"top": True, "right": True}) == ["top"]


def test_smart_only_linked_normal_rmu_efi_becomes_mandatory_clear():
    elem = make_relay({
        "app": "6500000",
        "app1": "6500000",
        "voltype1": "0",
        "p_ReportType1": "1",
        "state1": "41",
        "keyid1": "3809201031624227257",
    })
    validator = make_validator()
    row = {
        "object_type": "pwbh",
        "xml_id": elem.xml_id,
    }

    validator._apply_non_smart_relay_policy(row, elem)

    assert row["policy_clear_link"] == "YES"
    assert row["mandatory_policy_change"] == "YES"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert row["status"] == "RELINK"
    assert row["policy_clear_attributes"] == {
        "app": "",
        "app1": "",
        "voltype1": "",
        "p_ReportType1": "0",
        "state1": "",
        "keyid1": "",
    }


def test_smart_only_unlinked_normal_rmu_efi_stays_unlinked_without_writeback():
    # Mirrors the field-observed unlinked EFI shape: no voltype1 key, empty
    # app/app1/state1/keyid1 and p_ReportType1=0.
    elem = make_relay({
        "app": "",
        "app1": "",
        "p_ReportType1": "0",
        "state1": "",
        "keyid1": "",
    })
    validator = make_validator()
    row = {
        "object_type": "pwbh",
        "xml_id": elem.xml_id,
    }

    validator._apply_non_smart_relay_policy(row, elem)

    assert row["policy_clear_link"] == "NO"
    assert row["mandatory_policy_change"] == "NO"
    assert row["writeback_needed"] == "NO"
    assert row["model_link_correct"] == "YES"
    assert "voltype1" not in row["policy_clear_attributes"]


def test_clear_writeback_preserves_attribute_keys_and_clears_values(tmp_path):
    g = tmp_path / "clear.g"
    g.write_text(
        '<G><Layer><pwbh id="182000005" devref="#NariPd_Normal.pwbh.icn.g:NariPd_Normal" '
        'app="6500000" app1="6500000" voltype1="0" p_ReportType1="1" '
        'state1="41" keyid1="3809201031624227257" key_name1=""/></Layer></G>',
        encoding="utf-8",
    )

    row = {
        "object_type": "pwbh",
        "xml_id": "182000005",
        "policy_clear_link": "YES",
        "policy_clear_attributes": {
            "app": "",
            "app1": "",
            "voltype1": "",
            "p_ReportType1": "0",
            "state1": "",
            "keyid1": "",
        },
    }
    attrs = RmuModelModule._attributes_for_row(row)
    GWriteBackService().apply_attribute_changes(
        g,
        [{"tag": "pwbh", "xml_id": "182000005", "attributes": attrs}],
        create_backup=False,
        allow_new_attributes=False,
    )
    raw = g.read_text(encoding="utf-8")

    for key in ("app", "app1", "voltype1", "p_ReportType1", "state1", "keyid1"):
        assert f'{key}="' in raw
    assert 'app=""' in raw
    assert 'app1=""' in raw
    assert 'voltype1=""' in raw
    assert 'p_ReportType1="0"' in raw
    assert 'state1=""' in raw
    assert 'keyid1=""' in raw
