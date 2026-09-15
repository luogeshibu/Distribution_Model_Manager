from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule


class RealLikeABHDB:
    """Mimic production where 405/substation.NAME is ABH, not JED-NTH-ABH."""

    def __init__(self):
        self.feeders = {
            303: {
                "id": 303,
                "name": "AH303",
                "code": "AH303",
                "graph_name": "AH303",
                "st_id": 40501,
                "station_name": "ABH",
                "display_name": "ABH AH303",
            },
            304: {
                "id": 304,
                "name": "AH304",
                "code": "AH304",
                "graph_name": "AH304",
                "st_id": 40501,
                "station_name": "ABH",
                "display_name": "ABH AH304",
            },
        }

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        h = "".join(c for c in str(hint).upper() if c.isalnum())
        out = []
        for row in self.feeders.values():
            display = "".join(c for c in row["display_name"].upper() if c.isalnum())
            if h in display:
                out.append(dict(row))
        return out

    def get_feeder_info(self, feeder_id, table_id=13500):
        return dict(self.feeders[int(feeder_id)]) if int(feeder_id) in self.feeders else None


def make_g(path: Path, facid=""):
    path.write_text(
        f'<G facID="{facid}"><Layer>'
        '<CBreaker id="cb0" x="0" y="0" w="10" h="10"/>'
        '<FeedLine id="f1" ls="2" x="10" y="10" w="20" h="2"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    return path


def test_auto_filename_full_site_falls_back_to_actual_substation_name(tmp_path):
    g = make_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g")
    logs = []
    row = FeederModelModule()._resolve_file_feeder(
        RealLikeABHDB(),
        g,
        {
            "feeder_resolution_mode": "FILENAME",
            "feeder_station_hint": "",
            "feeder_table_id": 13500,
        },
        logs.append,
    )
    assert row["id"] == 303
    assert row["name"] == "AH303"
    assert row["_filename_station"] == "ABH"
    assert "token=03" in row["_resolution_evidence"]


def test_batch_station_input_abh_resolves_each_numeric_suffix_independently(tmp_path):
    module = FeederModelModule()
    db = RealLikeABHDB()
    settings = {
        "feeder_resolution_mode": "FILENAME",
        "feeder_station_hint": "ABH",
        "feeder_table_id": 13500,
    }
    files = [
        make_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g"),
        make_g(tmp_path / "JED-NTH-ABH-04.sln.pic.g"),
    ]
    assert [
        module._resolve_file_feeder(db, f, settings, lambda _m: None)["id"]
        for f in files
    ] == [303, 304]


def test_full_feeder_code_in_filename_is_not_prefixed_again(tmp_path):
    g = make_g(tmp_path / "JED-NTH-ABH-AH303.sln.pic.g")
    row = FeederModelModule()._resolve_file_feeder(
        RealLikeABHDB(),
        g,
        {
            "feeder_resolution_mode": "FILENAME",
            "feeder_station_hint": "ABH",
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row["id"] == 303
    assert row["_filename_token"] == "AH303"


def test_manual_abh_ah303_is_absolute_target_even_if_g_has_other_facid(tmp_path):
    g = make_g(tmp_path / "anything.sln.pic.g", facid="999")
    logs = []
    row, error = FeederModelModule()._resolve_file_feeder_result(
        RealLikeABHDB(),
        g,
        {
            "feeder_resolution_mode": "MANUAL",
            "manual_feeder_name": "ABH AH303",
            "allow_feeder_override": False,
            "feeder_table_id": 13500,
        },
        logs.append,
    )
    assert error == ""
    assert row["id"] == 303
    assert row["_resolution_source"] == "MANUAL"
    assert any("未启用人工覆盖" in x for x in logs)


def test_manual_nonexistent_feeder_fails_without_fallback_to_current_facid(tmp_path):
    g = make_g(tmp_path / "anything.sln.pic.g", facid="303")
    row, error = FeederModelModule()._resolve_file_feeder_result(
        RealLikeABHDB(),
        g,
        {
            "feeder_resolution_mode": "MANUAL",
            "manual_feeder_name": "ABH AH399",
            "allow_feeder_override": True,
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row is None
    assert error.startswith("MANUAL_FEEDER_NOT_FOUND")
