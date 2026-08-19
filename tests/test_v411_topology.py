
from pathlib import Path
import pytest
from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.topology import FeederTopologyResolver
S=Path("/mnt/data/JED-NTH-ABH-03.sln.pic(1).g")
def test_ls():
    m=FeederModelModule
    assert m._normalize_feedline_ls("1")==("1",1,False,True)
    assert m._normalize_feedline_ls("2")==("2",0,False,True)
    assert m._normalize_feedline_ls("")==("",3,False,True)
    assert m._normalize_feedline_ls("3")==("2",0,True,True)
    assert m._normalize_feedline_ls("4")==("2",0,True,True)
def test_real_names():
    if not S.exists():
        pytest.skip("legacy real G fixture not available")
    r=FeederTopologyResolver().resolve(S)
    assert r["35000655"]["section_name"]=="B303_22545-Y1"
    assert r["35000587"]["section_name"]=="22545-Y3_22521-Y2"
    assert r["35000620"]["section_name"]=="22545-Y2_8664-Y2"
    assert r["35000621"]["section_name"]=="8664-Y1_22520"
