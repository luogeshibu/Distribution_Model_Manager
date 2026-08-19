from pathlib import Path

from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import export_html_bundle

KEY_STEP = 1 << 32


def keyid(device_id, domain):
    return int(device_id) + int(domain) * KEY_STEP


class DomainRepairDB:
    def __init__(self):
        self.sections = [
            {"id": 3001, "name": "AJWD_43_SEC001", "code": "", "feeder_id": 700, "bv_id": 93001},
            {"id": 3002, "name": "AJWD_43_SEC002", "code": "", "feeder_id": 700, "bv_id": 93002},
        ]
        self.rmu = {"id": 501, "name": "RMU-A", "feeder_id": 700}
        self.breaker = {"id": 1101, "combined_id": 501, "feeder_id": 700, "bv_id": 91}

    def verify_keyid(self, value):
        value = int(value)
        domain = value // KEY_STEP
        device_id = value - domain * KEY_STEP
        if domain == 40:
            return {"device_id": device_id, "tab_no": 13502, "col_no": 40}
        return {"device_id": device_id, "tab_no": 13503, "col_no": domain}

    def get_device_by_id(self, table_id, device_id):
        if int(table_id) == 13502 and int(device_id) == 1101:
            return dict(self.breaker)
        if int(table_id) == 13503:
            for row in self.sections:
                if int(row["id"]) == int(device_id):
                    return dict(row)
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections if int(x["feeder_id"]) == int(feeder_id)]

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {"id": int(feeder_id), "name": "AJWD 43", "display_name": "AJWD 43"}

    def get_rmu_records(self, name):
        return [dict(self.rmu)] if name == "RMU-A" else []


def write_composite_region(path: Path):
    path.write_text(
        f'''<G width="1400" height="800"><Layer>
        <Text id="t1" x="140" y="150" w="100" h="20" ts="RMU-A"/>
        <rect id="r1" x="100" y="200" w="200" h="200"/>
        <CBreakerDis id="cb1" x="140" y="250" w="20" h="20" p_NameString="Y1" keyid="{keyid(1101,40)}"/>
        <ZhaiWaiJieDiDaoZha id="gd1" x="180" y="250" w="20" h="20" p_NameString="Y1D" keyid=""/>
        <BusDis id="bs1" x="220" y="250" w="20" h="20" p_NameString="BUS" keyid=""/>
        <FeedLine id="fl1" x="280" y="300" w="540" h="6" d="280,303 820,303" keyid="{keyid(3001,5)}"/>
        <FeedLine id="fl2" x="300" y="500" w="300" h="6" d="300,503 600,503" keyid=""/>
        <ConnectLine id="cl1" x="300" y="300" w="6" h="206" d="303,303 303,503"/>
        </Layer></G>''',
        encoding="utf-8",
    )


def test_composite_domain_only_error_preserves_same_section_and_is_relinkable(tmp_path):
    g = tmp_path / "domain5.g"
    write_composite_region(g)
    report = FeederValidator(DomainRepairDB(), GParser()).validate_file(g)
    active = next(r for r in report["feeder_regions"] if r.get("feeder_id") == 700)
    rows = {row["xml_id"]: row for row in active["feedline_rows"]}
    row = rows["fl1"]

    assert row["current_device_id"] == 3001
    assert row["current_domain"] == 5
    assert row["assigned_device_id"] == 3001
    assert row["expected_keyid"] == keyid(3001, 1)
    assert row["relink_same_section"] == "YES"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert row["severity"] == "RELINK"
    assert "DOMAIN_RELINK_READY" in row["reason"]

    # The domain-wrong section stays reserved, so the unlinked peer receives
    # SEC002 rather than stealing SEC001.
    assert rows["fl2"]["assigned_device_id"] == 3002


def test_feeder_html_has_independent_fuzzy_filters(tmp_path):
    reports = [{
        "report_type": "FEEDER",
        "g_file": str(tmp_path / "x.g"),
        "file_name": "x.g",
        "drawing_type": "SINGLE_FEEDER",
        "feeder_name": "AJWD 43",
        "status": "PASS",
        "severity": "PASS",
        "feedline_rows": [{
            "file_name": "x.g",
            "feeder_name": "AJWD 43",
            "xml_id": "fl1",
            "assigned_section_name": "AJWD_43_SEC001",
            "status": "PASS",
            "severity": "PASS",
        }],
    }]
    out = tmp_path / "feeder.html"
    export_html_bundle(reports, out, {"FeedLine": {"table_id": 13503, "domain": 1}})
    text = out.read_text(encoding="utf-8")
    assert "id='feeder-summary-table'" in text
    assert "id='feedline-detail-table'" in text
    assert "filterReportTable('feeder-summary-table'" in text
    assert "filterReportTable('feedline-detail-table'" in text
    assert "输入馈线名称或任意字符，模糊匹配" in text
    assert "输入馈线段名称或任意字符，模糊匹配" in text
    assert "function filterReportTable" in text

def test_single_feeder_domain_only_error_is_relinkable_without_changing_device(tmp_path):
    g = tmp_path / "single-domain5.g"
    g.write_text(
        f'<G><Layer><FeedLine id="fl1" x="10" y="10" w="100" h="6" '
        f'd="10,13 110,13" keyid="{keyid(3001,5)}"/></Layer></G>',
        encoding="utf-8",
    )
    result = FeederValidator(DomainRepairDB(), GParser()).validate_file_with_feeder_record(
        g,
        {"id": 700, "name": "AJWD 43", "display_name": "AJWD 43"},
        source="MANUAL",
    )
    row = result["feeder_regions"][0]["feedline_rows"][0]
    assert row["current_device_id"] == 3001
    assert row["assigned_device_id"] == 3001
    assert row["current_domain"] == 5
    assert row["expected_keyid"] == keyid(3001, 1)
    assert row["relink_same_section"] == "YES"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert row["severity"] == "RELINK"
