from modules.rmu import RmuModelModule
from modules.feeder import FeederModelModule

def get_model_modules():
    items = [RmuModelModule(), FeederModelModule()]
    return {m.module_id: m for m in items}
