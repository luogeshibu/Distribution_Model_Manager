
from dmm.application.modules.feeder import FeederModelModule


class DB:
    def __init__(self):
        self.rows = {
            1006: {
                "id": 1006,
                "name": "6",
                "st_id": 1,
                "station_name": "JED CTL AJWD",
                "display_name": "JED CTL AJWD 6",
            },
            10006: {
                "id": 10006,
                "name": "06",
                "st_id": 1,
                "station_name": "JED CTL AJWD",
                "display_name": "JED CTL AJWD 06",
            },
        }

    def get_feeder_info(self, feeder_id, table_id=13500):
        return self.rows.get(int(feeder_id))

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        h = str(hint).upper()
        out = []
        for row in self.rows.values():
            compact = "".join(
                c for c in row["display_name"].upper()
                if c.isalnum()
            )
            if h in compact:
                out.append(dict(row))
        return out


def make_g(tmp_path, filename, facid):
    p = tmp_path / filename
    p.write_text(
        f'<G facID="{facid}"><Layer>'
        '<FeedLine id="f1" ls="2"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    return p


def test_manual_mode_is_independent_even_when_facid_is_nonempty(tmp_path):
    g = make_g(tmp_path, "JED-CTL-AJWD-06.sln.pic.g", "1006")
    row = FeederModelModule()._resolve_file_feeder(
        DB(), g,
        {
            "feeder_resolution_mode": "MANUAL",
            "manual_feeder_name": "AJWD 06",
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row["id"] == 10006
    assert row["_resolution_source"] == "MANUAL"


def test_empty_facid_manual_keeps_leading_zero_significant(tmp_path):
    g = make_g(tmp_path, "x.sln.pic.g", "")
    row = FeederModelModule()._resolve_file_feeder(
        DB(), g,
        {
            "feeder_resolution_mode": "MANUAL",
            "manual_feeder_name": "AJWD 06",
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row["id"] == 10006
    assert row["name"] == "06"


def test_empty_facid_filename_keeps_leading_zero_significant(tmp_path):
    g = make_g(tmp_path, "JED-CTL-AJWD-06.sln.pic.g", "")
    row = FeederModelModule()._resolve_file_feeder(
        DB(), g,
        {
            "feeder_resolution_mode": "FILENAME",
            "manual_feeder_name": "",
            "feeder_table_id": 13500,
        },
        lambda _m: None,
    )
    assert row["id"] == 10006


def test_normalization_does_not_strip_numeric_zero():
    n = FeederModelModule._normalize_lookup_text
    assert n("AJWD 6") == "AJWD6"
    assert n("AJWD 06") == "AJWD06"
    assert n("AJWD 6") != n("AJWD 06")
