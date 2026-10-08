from pathlib import Path


def test_graphics_workspace_uses_new_jeddah_batch_display_name():
    text = Path('src/dmm/ui/graphics_workspace.py').read_text(encoding='utf-8')
    assert '("吉达图形批处理", "jeddah_batch"' in text
    assert '吉达馈线批处理' not in text


def test_i18n_uses_new_english_display_name():
    dmm = Path('src/dmm/i18n/translator.py').read_text(encoding='utf-8')
    gfs = Path('src/g_file_studio/i18n.py').read_text(encoding='utf-8')
    assert '"吉达图形批处理": "Jeddah Graphics Batch Processing"' in dmm
    assert '"吉达图形批处理": "Jeddah Graphics Batch Processing"' in gfs
    assert 'Jeddah Feeder Batch Processing' not in dmm
    assert 'Jeddah Feeder Batch Processing' not in gfs


def test_batch_internal_key_is_unchanged():
    text = Path('src/dmm/ui/graphics_workspace.py').read_text(encoding='utf-8')
    assert '"jeddah_batch"' in text
