from pathlib import Path

from dmm.application.modules.transformer import TransformerModelModule


def test_transformer_apply_writes_and_verifies_keyid1_keyid2(tmp_path, monkeypatch):
    source = tmp_path / "source.g"
    source.write_text(
        '<G><Layer><TransformerDis id="tr1" x="10" y="10" w="40" h="40" '
        'devref="#Transformer_OH.pb.icn.g:Transformer_OH" state1="18" state2="18"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    expected = "3801319564772377299"
    module = TransformerModelModule()

    monkeypatch.setattr(
        module,
        "_analyze_file",
        lambda *args, **kwargs: {
            "transformer_rows": [{
                "object_type": "TransformerDis",
                "xml_id": "tr1",
                "association_ready": "YES",
                "writeback_needed": "YES",
                "expected_keyid": expected,
                "status": "UNLINKED",
            }]
        },
    )

    stat = source.stat()
    preview = {
        "changes_by_file": {
            str(source): [{
                "xml_id": "tr1",
                "tag": "TransformerDis",
                "_source_file": str(source),
                "attributes": {},
                "validated_row": {"xml_id": "tr1"},
            }]
        },
        "file_fingerprints": {
            str(source): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        },
    }

    logs = []
    result = module.apply_association(
        object(), [source], {}, preview, logs.append, output_g_dir=output_dir
    )

    assert result["applied_count"] == 1
    assert len(result["results"]) == 1
    written = Path(result["copied_files"][0]).read_text(encoding="utf-8")
    assert f'keyid1="{expected}"' in written
    assert f'keyid2="{expected}"' in written
    assert any("回写确认" in line for line in logs)


def test_transformer_apply_does_not_report_success_when_nothing_is_written(tmp_path, monkeypatch):
    source = tmp_path / "source.g"
    source.write_text(
        '<G><Layer><TransformerDis id="tr1" x="10" y="10" w="40" h="40"/></Layer></G>',
        encoding="utf-8",
    )
    module = TransformerModelModule()
    monkeypatch.setattr(
        module,
        "_analyze_file",
        lambda *args, **kwargs: {
            "transformer_rows": [{
                "object_type": "TransformerDis",
                "xml_id": "tr1",
                "association_ready": "NO",
                "writeback_needed": "NO",
                "reason": "TEST_NOT_READY",
            }]
        },
    )
    stat = source.stat()
    preview = {
        "changes_by_file": {str(source): [{"xml_id": "tr1", "tag": "TransformerDis", "_source_file": str(source)}]},
        "file_fingerprints": {str(source): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}},
    }
    try:
        module.apply_association(object(), [source], {}, preview, lambda _m: None, output_g_dir=tmp_path / "out")
    except RuntimeError as exc:
        assert "没有任何对象实际写入" in str(exc)
        assert "TEST_NOT_READY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
