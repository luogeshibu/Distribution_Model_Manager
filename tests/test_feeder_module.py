from pathlib import Path

from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import export_html_bundle, export_csv_bundle

KEY_STEP = 1 << 32


def _keyid(device_id, domain):
    return int(device_id) + int(domain) * KEY_STEP


def write_topology_g(path: Path, second_rmu=True, second_linked=True):
    # One horizontal FeedLine enters both RMU frames, so both RMUs are in the
    # same topology component.  Only CBreakerDis needs a KeyID to provide a
    # verified existing-model evidence for a trusted RMU anchor.
    second = ""
    if second_rmu:
        second_key = str(_keyid(2101, 40)) if second_linked else ""
        second = f'''
        <Text id="t2" x="840" y="150" w="100" h="20" ts="RMU-B"/>
        <rect id="r2" x="800" y="200" w="200" h="200"/>
        <CBreakerDis id="cb2" x="840" y="250" w="20" h="20" p_NameString="Y1" keyid="{second_key}"/>
        <ZhaiWaiJieDiDaoZha id="gd2" x="880" y="250" w="20" h="20" p_NameString="Y1D" keyid=""/>
        <BusDis id="bs2" x="920" y="250" w="20" h="20" p_NameString="BUS" keyid=""/>
        '''
    path.write_text(
        f'''<G width="1400" height="800"><Layer>
        <Text id="t1" x="140" y="150" w="100" h="20" ts="RMU-A"/>
        <rect id="r1" x="100" y="200" w="200" h="200"/>
        <CBreakerDis id="cb1" x="140" y="250" w="20" h="20" p_NameString="Y1" keyid="{_keyid(1101,40)}"/>
        <ZhaiWaiJieDiDaoZha id="gd1" x="180" y="250" w="20" h="20" p_NameString="Y1D" keyid=""/>
        <BusDis id="bs1" x="220" y="250" w="20" h="20" p_NameString="BUS" keyid=""/>
        {second}
        <FeedLine id="fl1" x="280" y="300" w="540" h="6" d="280,303 820,303" keyid=""/>
        <FeedLine id="fl2" x="300" y="500" w="300" h="6" d="300,503 600,503" keyid=""/>
        <ConnectLine id="cl1" x="300" y="300" w="6" h="206" d="303,303 303,503"/>
        </Layer></G>''',
        encoding="utf-8",
    )


class TopologyDB:
    def __init__(self, feeder_b=700):
        self.feeder_b = feeder_b
        self.rmus = {
            "RMU-A": {"id": 501, "name": "RMU-A", "feeder_id": 700},
            "RMU-B": {"id": 502, "name": "RMU-B", "feeder_id": feeder_b},
        }
        self.devices = {
            (13502, 1101): {"id": 1101, "combined_id": 501, "feeder_id": 700, "bv_id": 91},
            (13502, 2101): {"id": 2101, "combined_id": 502, "feeder_id": feeder_b, "bv_id": 92},
        }
        self.sections = {
            700: [
                {"id": 3001, "name": "SEC001", "code": "", "feeder_id": 700, "bv_id": 93001},
                {"id": 3003, "name": "SEC003", "code": "", "feeder_id": 700, "bv_id": 93003},
            ],
            701: [
                {"id": 4001, "name": "SEC001", "code": "", "feeder_id": 701, "bv_id": 94001},
            ],
        }

    def get_rmu_records(self, name):
        row = self.rmus.get(name)
        return [dict(row)] if row else []

    def verify_keyid(self, value):
        value = int(value)
        # RMU breaker keyids use domain 40; FeedLine expected keyids domain 1.
        if value >= 40 * KEY_STEP:
            return {"device_id": value - 40 * KEY_STEP, "tab_no": 13502, "col_no": 40}
        return {"device_id": value - KEY_STEP, "tab_no": 13503, "col_no": 1}

    def get_device_by_id(self, table_id, device_id):
        if int(table_id) == 13502:
            row = self.devices.get((13502, int(device_id)))
            return dict(row) if row else None
        for rows in self.sections.values():
            for row in rows:
                if int(row["id"]) == int(device_id):
                    return dict(row)
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections.get(int(feeder_id), [])]

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {"id": int(feeder_id), "name": f"FEEDER {feeder_id}", "display_name": f"FEEDER {feeder_id}"}


def test_same_topology_trusted_rmus_confirm_one_feeder_and_assign_sections(tmp_path):
    g = tmp_path / "same.g"
    write_topology_g(g)
    file_report = FeederValidator(TopologyDB(), GParser()).validate_file(g)
    regions = file_report["feeder_regions"]

    # fl1 and fl2 are connected through cl1 and the two RMUs are attached to
    # the same component; both trusted RMUs agree on FEEDER_ID 700.
    active = next(r for r in regions if r.get("feeder_id") == 700)
    assert active["trusted_rmu_count"] == 2
    assert active["trusted_feeder_ids"] == "700"
    assert active["association_eligible"] is True
    assert [r["assigned_section_name"] for r in active["feedline_rows"]] == ["SEC001", "SEC003"]
    assert all(r["association_ready"] == "YES" for r in active["feedline_rows"])


def test_conflicting_trusted_rmu_feeder_ids_block_whole_component(tmp_path):
    g = tmp_path / "conflict.g"
    write_topology_g(g)
    file_report = FeederValidator(TopologyDB(feeder_b=701), GParser()).validate_file(g)
    blocked = next(r for r in file_report["feeder_regions"] if r.get("trusted_rmu_count") == 2)
    assert blocked["association_eligible"] is False
    assert "FEEDER_RMU_CONFLICT" in blocked["reason"]
    assert all(row["association_ready"] == "NO" for row in blocked["feedline_rows"])


def test_unlinked_rmu_is_ignored_as_reference_but_trusted_peer_can_confirm(tmp_path):
    g = tmp_path / "partial.g"
    write_topology_g(g, second_rmu=True, second_linked=False)
    file_report = FeederValidator(TopologyDB(), GParser()).validate_file(g)
    active = next(r for r in file_report["feeder_regions"] if r.get("feeder_id") == 700)
    assert active["trusted_rmu_count"] == 1
    assert active["ignored_rmu_count"] == 1
    assert "未关联任何模型" in active["ignored_rmu_details"]
    assert active["association_eligible"] is True


def test_feeder_html_has_row_marker_checkboxes(tmp_path):
    g = tmp_path / "report.g"
    write_topology_g(g)
    file_report = FeederValidator(TopologyDB(), GParser()).validate_file(g)
    reports = file_report["feeder_regions"]
    html = tmp_path / "report.html"
    export_html_bundle(reports, html, {"FeedLine": {"table_id": 13503, "domain": 1}})
    text = html.read_text(encoding="utf-8")
    assert "馈线汇总" in text
    assert "馈线段明细" in text
    assert text.count("class='row-check'") >= 2
    assert "toggleSelectedRow" in text
    assert "row-selected" in text

    csv_paths = export_csv_bundle(reports, tmp_path / "report.csv")
    assert len(csv_paths) == 2
    assert all(Path(p).exists() for p in csv_paths)


def test_existing_correct_section_is_reserved_and_gap_uses_smallest_remaining(tmp_path):
    g = tmp_path / "gap.g"
    write_topology_g(g, second_rmu=False)
    # Make first FeedLine already use SEC003; second one is unlinked.
    text = g.read_text(encoding="utf-8")
    text = text.replace(
        'id="fl1" x="280" y="300" w="540" h="6" d="280,303 820,303" keyid=""',
        f'id="fl1" x="280" y="300" w="540" h="6" d="280,303 820,303" keyid="{_keyid(3003,1)}"',
    )
    g.write_text(text, encoding="utf-8")

    report = FeederValidator(TopologyDB(), GParser()).validate_file(g)
    active = next(r for r in report["feeder_regions"] if r.get("feeder_id") == 700)
    rows = active["feedline_rows"]

    assert rows[0]["model_link_correct"] == "YES"
    assert rows[0]["assigned_section_name"] == "SEC003"
    assert rows[0]["writeback_needed"] == "NO"
    assert rows[1]["assigned_section_name"] == "SEC001"
    assert rows[1]["writeback_needed"] == "YES"
