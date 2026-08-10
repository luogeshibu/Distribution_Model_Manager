from dmm.ui.widgets.feeder_settings import FeederSettingsWidget
from dmm.ui.widgets.rmu_settings import RmuSettingsWidget


SETTINGS_WIDGETS = {
    "RMU": RmuSettingsWidget,
    "FEEDER": FeederSettingsWidget,
}


def create_settings_widget(module_id, parent, settings):
    try:
        widget_cls = SETTINGS_WIDGETS[module_id]
    except KeyError as exc:
        raise KeyError(f"No settings widget registered for module: {module_id}") from exc

    widget = widget_cls(settings)
    widget.setParent(parent)
    return widget
