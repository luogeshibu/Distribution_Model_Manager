from pathlib import Path

from dmm.domain.gfile.parser import GParser
from dmm.domain.feeder.validator import FeederValidator


def test_rmu_requires_all_three_core_device_types(tmp_path):
    g = tmp_path / "rmu.g"
    g.write_text(
        '''<G><Layer>
        <Rect id="r1" x="0" y="0" w="300" h="300"/>
        <CBreakerDis id="c1" x="30" y="30" w="20" h="20"/>
        <ZhaiWaiJieDiDaoZha id="z1" x="70" y="30" w="20" h="20"/>
        <BusDis id="b1" x="110" y="30" w="20" h="20"/>
        <Rect id="r2" x="400" y="0" w="300" h="300"/>
        <CBreakerDis id="c2" x="430" y="30" w="20" h="20"/>
        <BusDis id="b2" x="510" y="30" w="20" h="20"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"}
    )
    parsed = parser.parse(g)
    frames = parser.find_rmu_frames(parsed)
    assert [frame.frame.xml_id for frame in frames] == ["r1"]


class DuplicateDB:
    def get_feeder_info(self, feeder_id):
        return {"id": feeder_id, "name": "ABH 12", "display_name": "JED NTH ABH 12"}

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        rows = [
            {"id": 1001, "name": "ABH_12_SEC001", "feeder_id": feeder_id, "bv_id": 111},
            {"id": 1002, "name": "ABH_12_SEC002", "feeder_id": feeder_id, "bv_id": 222},
        ]
        return "dms_section_device", rows

    def verify_keyid(self, keyid):
        # current duplicate keyid 1001 + (1 << 32), and generated expected keyids
        device_id = int(keyid) - (1 << 32)
        return {"device_id": device_id, "tab_no": 13503, "col_no": 1}

    def get_device_by_id(self, table_id, device_id):
        if int(device_id) == 1001:
            return {"id": 1001, "name": "ABH_12_SEC001", "feeder_id": 77, "bv_id": 111}
        if int(device_id) == 1002:
            return {"id": 1002, "name": "ABH_12_SEC002", "feeder_id": 77, "bv_id": 222}
        return None


def test_duplicate_feedline_links_are_all_selectable_repair_candidates(tmp_path):
    keyid = 1001 + (1 << 32)
    g = tmp_path / "f.g"
    g.write_text(
        f'''<G><Layer>
        <FeedLine id="f1" x="0" y="0" w="100" h="6" keyid="{keyid}"/>
        <FeedLine id="f2" x="0" y="100" w="100" h="6" keyid="{keyid}"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    parser = GParser()
    parsed = parser.parse(g)
    feedlines = [o for o in parsed.objects if o.tag == "FeedLine"]
    validator = FeederValidator(DuplicateDB(), parser=parser)
    region = {
        "region_index": 1,
        "feedlines": feedlines,
        "rmu_anchors": [
            {"trusted": True, "rmu_name": "30830", "feeder_id": 77, "reason": "TRUSTED"}
        ],
    }
    report = validator._validate_rmu_topology_region(parsed, region)
    rows = report["feedline_rows"]
    assert len(rows) == 2
    assert all(row["association_ready"] == "YES" for row in rows)
    assert all(row["writeback_needed"] == "YES" for row in rows)
    assert all("DUPLICATE_LINK" in row["reason"] for row in rows)
    assert {row["assigned_device_id"] for row in rows} == {1001, 1002}

from dmm.application.modules.feeder import FeederModelModule


def test_selecting_one_duplicate_reassigns_only_selected_feedline(tmp_path):
    current_keyid = 1001 + (1 << 32)
    source = tmp_path / "dup.g"
    source.write_text(
        f'''<G><Layer>
        <FeedLine id="f1" x="0" y="0" w="100" h="6" keyid="{current_keyid}" voltype="111" app="6500000" p_ReportType="1" state="20"/>
        <FeedLine id="f2" x="0" y="100" w="100" h="6" keyid="{current_keyid}" voltype="111" app="6500000" p_ReportType="1" state="20"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    stat = source.stat()
    duplicate_rows = [
        {
            "order_index": 1,
            "object_type": "FeedLine",
            "xml_id": "f1",
            "model_linked": "YES",
            "current_keyid": current_keyid,
            "current_device_id": 1001,
            "current_table_id": 13503,
            "current_domain": 1,
            "current_feeder_id": 77,
            "current_db_name": "ABH_12_SEC001",
            "severity": "DUPLICATE_LINK",
        },
        {
            "order_index": 2,
            "object_type": "FeedLine",
            "xml_id": "f2",
            "model_linked": "YES",
            "current_keyid": current_keyid,
            "current_device_id": 1001,
            "current_table_id": 13503,
            "current_domain": 1,
            "current_feeder_id": 77,
            "current_db_name": "ABH_12_SEC001",
            "severity": "DUPLICATE_LINK",
        },
    ]
    preview = {
        "settings_snapshot": {
            "feeder_table_id": 13500,
            "section_table_id": 13503,
            "section_domain": 1,
            "drawing_mode": "AUTO",
        },
        "file_fingerprints": {
            str(source): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        },
        "reports": [{
            "g_file": str(source),
            "region_index": 1,
            "feeder_id": 77,
            "association_eligible": True,
            "reason": "FEEDER_RMU_TOPOLOGY_CONFIRMED",
            "feedline_rows": duplicate_rows,
        }],
        # Simulate user selecting only f2.
        "changes_by_file": {
            str(source): [{
                "xml_id": "f2",
                "tag": "FeedLine",
                "feeder_id": 77,
                "region_index": 1,
                "validated_row": dict(duplicate_rows[1]),
                "attributes": {},
            }]
        },
    }
    settings = {
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
        "drawing_mode": "AUTO",
    }
    out = tmp_path / "out"
    result = FeederModelModule().apply_association(
        DuplicateDB(),
        [source],
        settings,
        preview,
        lambda _msg: None,
        output_g_dir=out,
    )
    assert result["applied_count"] == 1
    copied = Path(result["copied_files"][0]).read_text(encoding="utf-8")
    f1 = next(line for line in copied.splitlines() if 'id="f1"' in line)
    f2 = next(line for line in copied.splitlines() if 'id="f2"' in line)
    assert f'keyid="{current_keyid}"' in f1
    expected_f2 = 1002 + (1 << 32)
    assert f'keyid="{expected_f2}"' in f2
    assert 'voltype="222"' in f2
