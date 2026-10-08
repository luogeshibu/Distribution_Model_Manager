from pathlib import Path
from dmm.application.modules import feeder_context
from dmm.domain.gfile.parser import GParser

class DB:
    def find_substations_by_name(self,name,table_id=405):
        return [{"id":40501,"name":"ABH"}] if name=="ABH" else []
    def find_feeders_by_station_and_name(self,station_id,feeder_name,table_id=13500):
        return [{"id":303,"name":"AH303","st_id":40501}] if feeder_name=="AH303" else []
    def get_feeder_info(self,feeder_id,table_id=13500):
        return {"id":303,"name":"AH303","station_name":"ABH"} if int(feeder_id)==303 else None
    def get_rmu_records(self,*a,**k): raise AssertionError("device feeder source disabled")
    def get_combined_device_records(self,*a,**k): raise AssertionError("device feeder source disabled")
    def get_transformer_devices_by_name(self,*a,**k): raise AssertionError("device feeder source disabled")

def _parsed(tmp_path):
    p=Path(tmp_path)/"JED-NTH-ABH-03.sln.pic.g"
    p.write_text("<G><Layer/></G>",encoding="utf-8")
    return GParser().parse(p)

def test_filename_only_resolution_does_not_call_rmu(monkeypatch,tmp_path):
    monkeypatch.setattr(feeder_context,"_graphical_rmu_candidates",lambda *a,**k: (_ for _ in ()).throw(AssertionError("disabled")))
    result=feeder_context.resolve_drawing_feeder(DB(),_parsed(tmp_path),{})
    assert result["ready"] is True and result["feeder_id"]==303

def test_filename_only_resolution_does_not_call_pole_switch(monkeypatch,tmp_path):
    monkeypatch.setattr(feeder_context,"_graphical_pole_switch_candidates",lambda *a,**k: (_ for _ in ()).throw(AssertionError("disabled")))
    result=feeder_context.resolve_drawing_feeder(DB(),_parsed(tmp_path),{})
    assert result["feeder_source"]=="FILENAME_405_13500"

def test_filename_only_resolution_does_not_call_transformer(monkeypatch,tmp_path):
    monkeypatch.setattr(feeder_context,"_graphical_transformer_candidates",lambda *a,**k: (_ for _ in ()).throw(AssertionError("disabled")))
    result=feeder_context.resolve_drawing_feeder(DB(),_parsed(tmp_path),{})
    assert "13500.NAME=AH303" in result["feeder_evidence"]
