from pathlib import Path


def test_feeder_source_ui_is_mode_specific_and_manual_is_editable():
    source = Path("src/dmm/ui/widgets/feeder_settings.py").read_text(encoding="utf-8")

    assert 'self.feeder_station_hint_label = QLabel("批量变电站名称（文件名模式，可选）")' in source
    assert 'self.manual_feeder_name_label = QLabel("人工目标馈线（变电站 + 馈线）")' in source

    # Mode-specific visibility: inactive source inputs do not remain as disabled
    # clutter on screen.
    assert 'self.feeder_station_hint_label.setVisible(filename_mode)' in source
    assert 'self.feeder_station_hint.setVisible(filename_mode)' in source
    assert 'self.manual_feeder_name_label.setVisible(manual_mode)' in source
    assert 'self.manual_feeder_name.setVisible(manual_mode)' in source
    assert 'self.allow_feeder_override.setVisible(override_mode)' in source

    # When MANUAL is selected the field must be fully editable so a persisted
    # value such as "ABH AH306" can be deleted/cleared by the operator.
    assert 'self.manual_feeder_name.setEnabled(manual_mode)' in source
    assert 'self.manual_feeder_name.setReadOnly(False)' in source


def test_business_resolver_still_branches_only_on_selected_source():
    source = Path("src/dmm/application/modules/feeder.py").read_text(encoding="utf-8")
    assert 'if requested_mode == "FACID":' in source
    assert 'if requested_mode == "FILENAME":' in source
    assert 'elif requested_mode == "MANUAL":' in source
    assert 'exact_by_text(manual, "MANUAL")' in source
