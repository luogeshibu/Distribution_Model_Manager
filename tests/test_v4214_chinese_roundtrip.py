from dmm.i18n.translator import translate_runtime_text


def test_runtime_phrase_round_trip_back_to_chinese():
    source = 'SSH只读模式：模型校验会重新下载服务器当前最新 G 文件。'
    en = translate_runtime_text(source, 'en_US')
    assert en != source
    assert translate_runtime_text(en, 'zh_CN') == source


def test_exact_static_round_trip_back_to_chinese():
    source = '环网柜名称来源'
    en = translate_runtime_text(source, 'en_US')
    assert en == 'RMU Name Source'
    assert translate_runtime_text(en, 'zh_CN') == source


def test_engineering_english_is_not_reverse_translated_in_chinese_mode():
    raw = 'current type status region FEEDER_ID=12345'
    assert translate_runtime_text(raw, 'zh_CN') == raw


def test_qt_tree_round_trip_if_qt_available():
    import pytest
    PySide6 = pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication, QLabel, QComboBox, QWidget, QVBoxLayout
    from dmm.i18n.translator import retranslate_qt_tree

    app = QApplication.instance() or QApplication([])
    root = QWidget()
    layout = QVBoxLayout(root)
    label = QLabel('环网柜名称来源')
    combo = QComboBox()
    combo.addItem('按指定方向')
    layout.addWidget(label)
    layout.addWidget(combo)

    retranslate_qt_tree(root, 'en_US')
    assert label.text() == 'RMU Name Source'
    assert combo.itemText(0) == 'Use Fixed Direction'
    retranslate_qt_tree(root, 'zh_CN')
    assert label.text() == '环网柜名称来源'
    assert combo.itemText(0) == '按指定方向'
