from dmm.application.modules.feeder import FeederModelModule
from dmm.application.modules.rmu import RmuModelModule


def get_model_modules():
    modules = [RmuModelModule(), FeederModelModule()]
    return {module.module_id: module for module in modules}
