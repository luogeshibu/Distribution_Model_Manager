from dmm.application.modules.feeder import FeederModelModule
from dmm.application.modules.master_station import MasterStationModelModule
from dmm.application.modules.pole_switch import PoleSwitchModelModule
from dmm.application.modules.rmu import RmuModelModule
from dmm.application.modules.transformer import TransformerModelModule


def get_model_modules():
    modules = [
        RmuModelModule(),
        FeederModelModule(),
        PoleSwitchModelModule(),
        TransformerModelModule(),
        MasterStationModelModule(),
    ]
    return {module.module_id: module for module in modules}
