from pathlib import Path
import inspect

from dmm.application.modules.master_station import MasterStationModelModule


class FilenameMasterDB:
    def __init__(self, station_name="ABH", feeder_name="AH303"):
        self.station_name = station_name
        self.feeder_name = feeder_name
        self.station_id = 40501
        self.feeder_id = 13500303
        self.bay_id = 40603
        self.calls = []

    def find_bays_by_feeder(self, hint, station_id, table_id=406):
        self.calls.append(("bay", str(hint), int(station_id), int(table_id)))
        if str(hint) == self.feeder_name and int(station_id) == self.station_id:
            return [{
                "id": self.bay_id,
                "code": self.feeder_name,
                "name": self.feeder_name,
                "st_id": self.station_id,
            }]
        return []

    def get_station_info(self, station_id):
        self.calls.append(("station", int(station_id)))
        return {"id": self.station_id, "name": self.station_name}

    # These are deliberate trip-wires: filename feeder resolution for the
    # master-station module must never need RMU/KeyID reverse lookup.
    def get_rmu_by_id(self, *_args, **_kwargs):
        raise AssertionError("RMU lookup must not be used for master-station feeder context")

    def verify_keyid(self, *_args, **_kwargs):
        raise AssertionError("KeyID reverse lookup must not be used for feeder context")


def _resolution(db: FilenameMasterDB):
    return {
        "ready": True,
        "feeder_id": db.feeder_id,
        "feeder_source": "FILENAME_405_13500",
        "feeder": {
            "id": db.feeder_id,
            "name": db.feeder_name,
            "code": "",
            "graph_name": "",
            "st_id": db.station_id,
            "station_name": db.station_name,
            "display_name": f"{db.station_name} {db.feeder_name}",
        },
        "candidates": [{
            "kind": "FILENAME",
            "identity": f"JED-NTH-{db.station_name}-03.sln.pic.g",
            "name": db.feeder_name,
        }],
        "reason": "",
    }


def test_master_station_context_uses_filename_feeder_without_rmu_or_keyid():
    db = FilenameMasterDB()
    context, error, meta = MasterStationModelModule._context_from_filename_feeder(
        db, _resolution(db)
    )

    assert error == ""
    assert context["station_id"] == db.station_id
    assert context["station_name"] == "ABH"
    assert context["feeder_id"] == db.feeder_id
    assert context["filename_feeder_name"] == "AH303"
    assert context["bay_id"] == db.bay_id
    assert meta["context_anchor_type"] == "FILENAME_FEEDER"
    assert db.calls == [
        ("bay", "AH303", db.station_id, 406),
        ("station", db.station_id),
    ]


def test_master_station_context_uses_new_ag406_filename_feeder_name():
    db = FilenameMasterDB(station_name="MDN", feeder_name="AG406")
    context, error, _meta = MasterStationModelModule._context_from_filename_feeder(
        db, _resolution(db)
    )

    assert error == ""
    assert context["station_name"] == "MDN"
    assert context["filename_feeder_name"] == "AG406"
    assert context["bay_code"] == "AG406"
    assert db.calls[0] == ("bay", "AG406", db.station_id, 406)


def test_master_station_filename_feeder_requires_unique_bay():
    db = FilenameMasterDB()

    def duplicate_bays(hint, station_id, table_id=406):
        return [
            {"id": 1, "code": hint, "st_id": station_id},
            {"id": 2, "code": hint, "st_id": station_id},
        ]

    db.find_bays_by_feeder = duplicate_bays
    context, error, _meta = MasterStationModelModule._context_from_filename_feeder(
        db, _resolution(db)
    )

    assert context is None
    assert "MASTER_STATION_BAY_NOT_UNIQUE" in error


def test_master_station_analyze_no_longer_calls_rmu_local_context():
    source = inspect.getsource(MasterStationModelModule._analyze_file)
    assert "resolve_drawing_feeder(" in source
    assert "_context_from_filename_feeder(" in source
    assert "_resolve_local_context(" not in source
    assert "MASTER_STATION_RMU_ASSOCIATION_REQUIRED" not in source


class FullFilenameMasterDB:
    station_id = 40501
    feeder_id = 303
    bay_id = 40603
    feeder = {
        "id": 303,
        "name": "AH303",
        "code": "AH303",
        "st_id": 40501,
        "station_name": "ABH",
        "display_name": "ABH AH303",
    }

    def find_substations_by_name(self, name, table_id=405):
        return [{"id": self.station_id, "name": "ABH"}] if name == "ABH" else []

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        if int(station_id) == self.station_id and feeder_name == "AH303":
            return [dict(self.feeder)]
        return []

    def get_feeder_info(self, feeder_id, table_id=13500):
        return dict(self.feeder) if int(feeder_id) == self.feeder_id else None

    def find_bays_by_feeder(self, hint, station_id, table_id=406):
        if hint == "AH303" and int(station_id) == self.station_id:
            return [{
                "id": self.bay_id,
                "code": "AH303",
                "name": "AH303",
                "st_id": self.station_id,
            }]
        return []

    def get_station_info(self, station_id):
        return {"id": self.station_id, "name": "ABH"}

    def get_devices_by_bay_id(self, table_id, bay_id):
        assert int(bay_id) == self.bay_id
        names = {407: "breaker", 408: "disconnector", 409: "grounddisconnector"}
        ids = {407: 40701, 408: 40801, 409: 40901}
        bv = {407: 111, 408: 112, 409: 113}
        code = {407: "CB", 408: "DS", 409: "GD"}
        return names[table_id], [{
            "id": ids[table_id],
            "code": code[table_id],
            "name": code[table_id],
            "bay_id": self.bay_id,
            "bv_id": bv[table_id],
        }]

    def get_bay_by_id(self, bay_id):
        return {
            "id": self.bay_id,
            "code": "AH303",
            "name": "AH303",
            "st_id": self.station_id,
        }

    def find_feeders_by_bay(self, hint, station_id, table_id=13500):
        if hint == "AH303" and int(station_id) == self.station_id:
            return [dict(self.feeder)]
        return []

    def verify_keyid(self, keyid):
        from dmm.application.modules.master_station import KEYID_STEP
        expected = {
            40701 + 40 * KEYID_STEP: (40701, 407, 40),
            40801 + 30 * KEYID_STEP: (40801, 408, 30),
            40901 + 30 * KEYID_STEP: (40901, 409, 30),
        }
        device_id, table_id, domain = expected[int(keyid)]
        return {"device_id": device_id, "tab_no": table_id, "col_no": domain}


def test_master_station_full_analysis_works_without_any_rmu_model(tmp_path: Path):
    g_file = tmp_path / "JED-NTH-ABH-03.sln.pic.g"
    g_file.write_text(
        '''<G width="2000" height="2000"><Layer>
        <Bus id="b_main" x="100" y="200" w="500" h="6"/>
        <CBreaker id="br1" x="300" y="250" w="20" h="30" link="0,0,b_main;1,0,f1" keyid="" app="" voltype="" p_ReportType="" state=""/>
        <Disconnector id="d1" x="400" y="250" w="20" h="30" link="0,0,b_main" keyid="" app="" voltype="" p_ReportType="" state=""/>
        <GroundDisconnector id="g1" x="500" y="250" w="20" h="30" link="0,0,b_main" keyid="" app="" voltype="" p_ReportType="" state=""/>
        <FeedLine id="f1" x="305" y="300" w="6" h="300" link="0,0,br1"/>
        </Layer></G>''',
        encoding="utf-8",
    )

    report = MasterStationModelModule()._analyze_file(
        FullFilenameMasterDB(), g_file, {}, lambda _message: None
    )

    assert report["association_context"]["mode"] == "filename_feeder_with_target_membership"
    assert report["association_context"]["feeder_id"] == 303
    assert report["association_context"]["bay_id"] == 40603
    rows = report["master_station_rows"]
    assert len(rows) == 3
    assert {row["object_type"] for row in rows} == {
        "CBreaker", "Disconnector", "GroundDisconnector"
    }
    assert all(row["association_ready"] == "YES" for row in rows)
    assert all(row["feeder_membership_verified"] == "YES" for row in rows)
    assert all(not row.get("context_rmu_id") for row in rows)
