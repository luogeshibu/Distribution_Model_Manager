from pathlib import Path

from dmm.application.modules.pole_switch import (
    PoleSwitchModelModule,
    PoleSwitchParser,
    normalize_pole_switch_db_lookup_name,
)
from dmm.domain.gfile.parser import Box, GObject


class ExactNameDB:
    def __init__(self):
        self.names = []

    def get_combined_device_records(self, name):
        self.names.append(name)
        return [{"id": 101, "name": name, "code": "", "_matched_field": "NAME"}]

    def get_cb_devices_by_combined_device_id(self, combined_id):
        return [{"id": 202, "name": "SW", "code": "SW", "combined_id": combined_id, "bv_id": 91}]

    def verify_keyid(self, keyid):
        return {"device_id": int(keyid) - (40 << 32), "tab_no": 13502, "col_no": 40}

    def get_device_by_id(self, table_id, device_id):
        return None


def test_lookup_name_is_identity_and_preserves_spaces_hyphens_dots():
    samples = [
        "SEC-2385",
        "AR 1234",
        "LBS96527-21240",
        "SEC.12-34",
        "AR  12-34.5",
        "  SEC-2385  ",
    ]
    for value in samples:
        assert normalize_pole_switch_db_lookup_name(value, "SEC") == value


def test_pole_switch_resolve_passes_graphical_name_to_db_unchanged():
    db = ExactNameDB()
    raw = "AR  1234-56.7"
    row = {
        "graphical_name": raw,
        "device_family": "AR",
        "xml_id": "p1",
        "current_keyid": "",
        "object_type": "CBreaker",
        "devref": "PoleSwitch.g",
    }
    out = PoleSwitchModelModule()._resolve_row(row, db)
    assert db.names == [raw]
    assert out["database_query_name"] == raw
    assert out["association_ready"] == "YES"


def test_selected_label_exposes_raw_g_text_without_whitespace_rewrite():
    parser = PoleSwitchParser()
    text = GObject(
        tag="Text",
        attrs={"id": "t1", "ts": "  AR  1234-56.7  "},
        box=Box(20, 0, 20, 10),
        xml_index=1,
    )
    device = GObject(
        tag="CBreaker",
        attrs={"id": "d1", "devref": "PoleSwitch.g"},
        box=Box(0, 0, 10, 10),
        xml_index=0,
    )
    owners = {0: [(0, 0, 10.0, 1, parser._text_value(text), text)]}
    label, _ = parser.find_nearest_name(None, device, "", (), owners)
    assert label["text"] == "AR 1234-56.7"
    assert label["raw_text"] == "  AR  1234-56.7  "


def test_oracle_13501_pole_switch_query_has_no_trim_or_normalization():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/dmm/infrastructure/database/oracle.py").read_text(encoding="utf-8")
    start = source.index("def get_combined_device_records")
    end = source.index("def get_cb_devices_by_combined_name", start)
    method = source[start:end]
    assert "WHERE name = :device_name" in method
    assert "TRIM(name)" not in method
    assert 'str(device_name or "").strip()' not in method
