from dmm.application.modules.base import ModelModule

class FeederModelModule(ModelModule):
    module_id = "FEEDER"
    display_name = "馈线模型"
    description = "馈线模型校验及后续关联/回写。"
    SUPPORTED_OPERATIONS = ()

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        raise NotImplementedError("馈线模型业务规则尚未配置，当前不能执行。")
