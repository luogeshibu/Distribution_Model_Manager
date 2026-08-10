from abc import ABC, abstractmethod


class ModelModule(ABC):
    module_id = ""
    display_name = ""
    description = ""
    SUPPORTED_OPERATIONS = ("VALIDATE",)

    def supports(self, operation):
        return operation in self.SUPPORTED_OPERATIONS

    @abstractmethod
    def validate(self, db, files, settings, log_callback, progress_callback=None):
        raise NotImplementedError

    def preview_association(self, db, files, settings, log_callback, progress_callback=None):
        raise NotImplementedError(
            f"{self.display_name}: association preview is not implemented yet."
        )

    def apply_association(
        self,
        db,
        files,
        settings,
        preview_data,
        log_callback,
        output_g_dir=None,
    ):
        raise NotImplementedError(
            f"{self.display_name}: model write-back is not implemented yet."
        )
