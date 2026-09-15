from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser

KEY_STEP = 1 << 32


class ABHDB:
    def __init__(self):
        self.feeders = {
            303: {
                "id": 303,
                "name": "AH303",
                "code": "AH303",
                "graph_name": "AH303",
                "st_id": 40501,
                "station_name": "JED NTH ABH",
                "station_bv_id": 112871465660973067,
                "display_name": "JED NTH ABH AH303",
            },
            304: {
                "id": 304,
                "name": "AH304",
                "code": "AH304",
                "graph_name": "AH304",
                "st_id": 40501,
                "station_name": "JED NTH ABH",
                "station_bv_id": 112871465660973067,
                "display_name": "JED NTH ABH AH304",
            },
            305: {
                "id": 305,
                "name": "AH305",
                "code": "AH305",
                "graph_name": "AH305",
                "st_id": 40501,
                "station_name": "JED NTH ABH",
                "station_bv_id": 112871465660973067,
                "display_name": "JED NTH ABH AH305",
            },
        }
        self.sections = {
            303: [{"id": 3001, "name": "ABH_AH303_SEC001", "feeder_id": 303, "bv_id": 91}],
            304: [{"id": 4001, "name": "ABH_AH304_SEC001", "feeder_id": 304, "bv_id": 91}],
            305: [{"id": 5001, "name": "ABH_AH305_SEC001", "feeder_id": 305, "bv_id": 91}],
            999: [{"id": 9001, "name": "OLD_SEC001", "feeder_id": 999, "bv_id": 91}],
        }

    def get_feeder_info(self, feeder_id, table_id=13500):
        row = self.feeders.get(int(feeder_id))
        if row:
            return dict(row)
        if int(feeder_id) == 999:
            return {
                "id": 999,
                "name": "OLD",
                "station_name": "JED NTH OLD",
                "display_name": "JED NTH OLD OLD",
            }
        return None

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        h = "".join(c for c in str(hint).upper() if c.isalnum())
        out = []
        for row in self.feeders.values():
            display = "".join(c for c in row["display_name"].upper() if c.isalnum())
            if h in display:
                out.append(dict(row))
        return out

    def verify_keyid(self, keyid):
        value = int(keyid)
        return {"device_id": value - KEY_STEP, "tab_no": 13503, "col_no": 1}

    def get_device_by_id(self, table_id, device_id):
        for rows in self.sections.values():
            for row in rows:
                if int(row["id"]) == int(device_id):
                    return dict(row)
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections.get(int(feeder_id), [])]

    def get_preferred_feeder_section_voltage(self, station_id):
        return {"bv_id": 91, "nomvol": 13.8}


def make_g(path: Path, facid=""):
    path.write_text(
        f'<G facID="{facid}"><Layer>'
        '<CBreaker id="cb0" x="0" y="0" w="10" h="10"/>'
        '<FeedLine id="f1" ls="2" x="10" y="10" w="20" h="2"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    return path


def test_filename_parser_supports_numeric_and_full_code_and_timestamp_suffix():
    m = FeederModelModule()
    station, token, _ = m._filename_feeder_parts(
        Path("JED-NTH-ABH-03.sln.pic(20260831-143200).g")
    )
    assert station == "JED-NTH-ABH"
    assert token == "03"

    station, token, _ = m._filename_feeder_parts(
        Path("JED-NTH-ABH-AH303.sln.pic.g")
    )
    assert station == "JED-NTH-ABH"
    assert token == "AH303"


def test_filename_numeric_token_resolves_with_short_station_hint(tmp_path):
    g = make_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g", facid="999")
    row = FeederModelModule()._resolve_file_feeder(
        ABHDB(),
        g,
        {
            "feeder_resolution_mode": "FILENAME",
            "feeder_station_hint": "ABH",
            "allow_feeder_override": True,
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row["id"] == 303
    assert row["name"] == "AH303"
    assert row["_resolution_source"] == "FILENAME"
    assert "token=03" in row["_resolution_evidence"]


def test_filename_full_code_is_used_directly(tmp_path):
    g = make_g(tmp_path / "JED-NTH-ABH-AH305.sln.pic.g")
    row = FeederModelModule()._resolve_file_feeder(
        ABHDB(),
        g,
        {
            "feeder_resolution_mode": "FILENAME",
            "feeder_station_hint": "JED-NTH-ABH",
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row["id"] == 305
    assert row["name"] == "AH305"


def test_same_filename_resolver_handles_batch_files_independently(tmp_path):
    files = [
        make_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g"),
        make_g(tmp_path / "JED-NTH-ABH-AH304.sln.pic.g"),
    ]
    module = FeederModelModule()
    settings = {
        "feeder_resolution_mode": "FILENAME",
        "feeder_station_hint": "ABH",
        "feeder_table_id": 13500,
    }
    ids = [
        module._resolve_file_feeder(ABHDB(), f, settings, lambda _m: None)["id"]
        for f in files
    ]
    assert ids == [303, 304]


def test_directory_validation_no_longer_requires_facid(tmp_path):
    files = [
        make_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g"),
        make_g(tmp_path / "JED-NTH-ABH-04.sln.pic.g"),
    ]
    reports, summary, _rules = FeederModelModule().validate(
        ABHDB(),
        files,
        {
            "input_is_directory": True,
            "feeder_resolution_mode": "FILENAME",
            "feeder_station_hint": "ABH",
            "allow_feeder_override": False,
            "feeder_table_id": 13500,
            "section_table_id": 13503,
            "section_domain": 1,
            "feeder_drawing_mode": "AUTO",
            "auto_create_missing_sections": True,
        },
        lambda _m: None,
    )
    assert {int(r["feeder_id"]) for r in reports} == {303, 304}
    assert summary["feeder_files"] == 2


def test_existing_facid_conflict_requires_explicit_override(tmp_path):
    g = make_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g", facid="999")
    feeder = ABHDB().feeders[303]

    blocked = FeederValidator(
        ABHDB(), GParser(), allow_feeder_override=False
    ).validate_file_with_feeder_record(g, feeder, source="FILENAME")["feeder_regions"][0]
    assert blocked["association_eligible"] is False
    assert "FEEDER_ROOT_FACID_CONFLICT" in blocked["reason"]

    allowed = FeederValidator(
        ABHDB(), GParser(), allow_feeder_override=True
    ).validate_file_with_feeder_record(g, feeder, source="FILENAME")["feeder_regions"][0]
    assert allowed["feeder_root_writeback_needed"] == "YES"
    assert allowed["feeder_root_current_facid"] == "999"
    assert allowed["feeder_root_expected_facid"] == "303"
