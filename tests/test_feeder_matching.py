from dmm.domain.rmu.validator import (
    compose_database_feeder_name,
    feeder_hint_from_g_filename,
    normalize_feeder_text,
)


def test_extract_feeder_hint_from_filename():
    assert (
        feeder_hint_from_g_filename("JED-NTH-ABH-06.sln.pic.g")
        == "ABH-06"
    )

    assert (
        feeder_hint_from_g_filename("JED-NTH-ABH_06.sln.pic.g")
        == "ABH-06"
    )


def test_separator_variants_compare_equally():
    assert normalize_feeder_text("ABH-06") == "ABH 06"
    assert normalize_feeder_text("ABH_06") == "ABH 06"
    assert normalize_feeder_text("ABH 06") == "ABH 06"


def test_db_readable_feeder_contains_file_hint():
    feeder = {
        "id": 3799912185593856225,
        "name": "06",
        "_table_id": 13500,
        "_table_name": "dms_feeder_device",
    }
    station = {
        "name": "JED NTH ABH",
    }

    display = compose_database_feeder_name(feeder, station)

    assert display == "JED NTH ABH 06"
    assert (
        normalize_feeder_text("ABH-06")
        in normalize_feeder_text(display)
    )


def test_non_matching_feeder_is_detectable():
    display = "JED NTH XYZ 05"

    assert (
        normalize_feeder_text("ABH-06")
        not in normalize_feeder_text(display)
    )
