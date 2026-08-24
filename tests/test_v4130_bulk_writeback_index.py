from pathlib import Path

from dmm.infrastructure.gfile.writeback import GWriteBackService
from dmm.i18n import translate_runtime_text


def _sample_g(count=12):
    tags = ["CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"]
    rows = ['<?xml version="1.0" encoding="utf-8"?>', '<G id="1">']
    for index in range(count):
        tag = tags[index % len(tags)]
        rows.append(
            f'<{tag} id="{1000 + index}" keyid="0" app="0" '
            f'state="0" voltype="0"/>'
        )
    rows.append('</G>')
    return "\n".join(rows) + "\n"


def _changes(count=12):
    tags = ["CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"]
    return [
        {
            "tag": tags[index % len(tags)],
            "xml_id": str(1000 + index),
            "attributes": {
                "keyid": str(9000 + index),
                "app": "1",
                "state": str(index % 50),
            },
        }
        for index in range(count)
    ]


def test_bulk_writeback_does_not_use_per_object_full_file_locator(tmp_path, monkeypatch):
    path = tmp_path / "bulk.g"
    path.write_text(_sample_g(120), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy per-object full-file locator must not be used")

    monkeypatch.setattr(GWriteBackService, "_find_exact_open_tag", forbidden)
    result = GWriteBackService().apply_attribute_changes(
        path,
        _changes(120),
        create_backup=False,
    )
    assert result["applied_count"] == 120
    text = path.read_text(encoding="utf-8")
    assert 'id="1000" keyid="9000" app="1" state="0"' in text
    assert 'id="1119" keyid="9119" app="1" state="19"' in text


def test_bulk_writeback_preserves_sequential_duplicate_target_semantics(tmp_path):
    path = tmp_path / "duplicate.g"
    path.write_text(
        '<G><CBreakerDis id="10" keyid="0" state="0"/></G>\n',
        encoding="utf-8",
    )
    result = GWriteBackService().apply_attribute_changes(
        path,
        [
            {
                "tag": "CBreakerDis",
                "xml_id": "10",
                "attributes": {"keyid": "100"},
            },
            {
                "tag": "CBreakerDis",
                "xml_id": "10",
                "attributes": {"state": "41"},
            },
        ],
        create_backup=False,
    )
    assert result["applied_count"] == 2
    assert result["changes"][0]["before"]["keyid"] == "0"
    assert result["changes"][1]["before"]["state"] == "0"
    text = path.read_text(encoding="utf-8")
    assert 'keyid="100"' in text
    assert 'state="41"' in text


def test_bulk_writeback_emits_live_progress_and_english_translation(tmp_path):
    path = tmp_path / "progress.g"
    path.write_text(_sample_g(205), encoding="utf-8")
    logs = []
    GWriteBackService(log=logs.append).apply_attribute_changes(
        path,
        _changes(205),
        create_backup=False,
    )
    assert any("正在建立 G 文件回写索引" in line for line in logs)
    assert any("G 文件回写进度：205/205" in line for line in logs)

    for line in logs:
        translated = translate_runtime_text(line, "en_US")
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in translated), translated
