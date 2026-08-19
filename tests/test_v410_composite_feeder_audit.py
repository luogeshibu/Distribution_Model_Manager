
from pathlib import Path
from dmm.application.modules.feeder import FeederModelModule


def test_real_uploaded_drawings_classify_single_and_composite():
    composite = Path("/mnt/data/JED-NTH-ABH.sln.pic(6).g")
    single = Path("/mnt/data/JED-NTH-ABH-06.sln.pic(7).g")
    if not composite.exists() or not single.exists():
        return
    m = FeederModelModule()
    cp = m._drawing_profile(composite)
    sp = m._drawing_profile(single)
    assert cp["drawing_type"] == "MULTI_FEEDER_COMPOSITE"
    assert cp["bus_count"] >= 2
    assert sp["drawing_type"] == "SINGLE_FEEDER"
    assert sp["bus_count"] == 1


def test_single_file_feedline_ids_are_contained_in_composite():
    composite = Path("/mnt/data/JED-NTH-ABH.sln.pic(6).g")
    single = Path("/mnt/data/JED-NTH-ABH-06.sln.pic(7).g")
    if not composite.exists() or not single.exists():
        return
    m = FeederModelModule()
    cp = m._drawing_profile(composite)["parsed"]
    sp = m._drawing_profile(single)["parsed"]
    cids = {str(o.xml_id) for o in cp.objects if o.tag == "FeedLine"}
    sids = {str(o.xml_id) for o in sp.objects if o.tag == "FeedLine"}
    assert sids
    assert sids <= cids


def test_composite_code_is_audit_only_and_ignores_root_facid():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/feeder.py"
    ).read_text(encoding="utf-8")
    assert "MULTI_FEEDER_COMPOSITE" in source
    assert "SINGLE_FILE_FINGERPRINT" in source
    assert "TOPOLOGY_COMPONENT" in source
    assert '"association_eligible":False' in source
    assert "组合大图忽略根 facID" in source


def test_directory_mode_requires_facid_for_single_drawings():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/feeder.py"
    ).read_text(encoding="utf-8")
    assert "DIRECTORY_MODE_FACID_REQUIRED" in source
    assert "单馈线图只允许 facID" in source
