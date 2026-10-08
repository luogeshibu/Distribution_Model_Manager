from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RMU = ROOT / "src" / "dmm" / "ui" / "widgets" / "rmu_settings.py"


def test_rmu_logic_panel_is_top_aligned_and_does_not_spread_cards():
    source = RMU.read_text(encoding="utf-8")
    assert "logic_box.setMinimumHeight(0)" in source
    assert "logic_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)" in source
    assert "logic.setAlignment(Qt.AlignTop)" in source
    assert "logic.addStretch(1)" in source
    assert "top_row.addWidget(logic_box, 7, alignment=Qt.AlignTop)" in source
    assert "logic.setSpacing(3)" in source


def test_v4198_keeps_rmu_business_description_markers():
    source = RMU.read_text(encoding="utf-8")
    for marker in [
        "只有矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha",
        "固定 CODE=EFI INDICATOR",
        "13533 / dms_relay_sig",
        "当前 KeyID 只用于判断 PASS / UNLINKED / RELINK / RMU_RELINK",
        "所有修改只写 Workspace 安全副本，原始 G 文件不修改",
    ]:
        assert marker in source
