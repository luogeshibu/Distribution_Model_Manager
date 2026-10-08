from pathlib import Path

from dmm.application.modules.fuse import FuseParser
from dmm.application.modules.transformer import TransformerModelModule, TransformerParser
from dmm.domain.gfile.parser import GParser


def _catalog(classification="TRANSFORMER_OH"):
    return {
        "records": [
            {
                "file_name": "custom_transformer.g",
                "root_id": "CUSTOM_TRANSFORMER",
                "classification": classification,
            },
            {
                "file_name": "custom_fuse.g",
                "root_id": "CUSTOM_FUSE",
                "classification": "FUSE",
            },
        ]
    }


def _write(path: Path, tag: str = "AnyFutureTransformerElement") -> Path:
    path.write_text(
        f'''<G><Layer>
          <{tag} id="tr1" x="100" y="100" w="40" h="40" devref="#custom_transformer.g:CUSTOM_TRANSFORMER" keyid1="" keyid2=""/>
          <Text id="name1" x="120" y="60" w="100" h="30" ts="971765" lc="255,255,255"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_transformer_recognition_depends_on_classification_not_xml_tag(tmp_path):
    g_file = _write(tmp_path / "custom.g", tag="AnyFutureTransformerElement")
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file),
        _catalog("TRANSFORMER_OH"),
        {},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["object_type"] == "AnyFutureTransformerElement"
    assert row["xml_id"] == "tr1"
    assert row["graphical_name"] == "971765"
    assert row["name_direction"] == "top"


def test_same_arbitrary_xml_tag_is_ignored_without_transformer_classification(tmp_path):
    g_file = _write(tmp_path / "not_transformer.g", tag="AnyFutureTransformerElement")
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file),
        _catalog("OTHER_DEVICE"),
        {},
    )
    assert rows == []


def test_transformer_preview_writeback_uses_real_xml_tag(tmp_path, monkeypatch):
    g_file = _write(tmp_path / "preview.g", tag="FutureTransformerDevice")
    module = TransformerModelModule()
    validated_row = {
        "object_type": "FutureTransformerDevice",
        "xml_id": "tr1",
        "association_ready": "YES",
        "writeback_needed": "YES",
        "selected_device_name": "971765",
        "db_device_id": 123,
        "expected_keyid": 456,
    }
    report = {
        "g_file": str(g_file),
        "transformer_rows": [validated_row],
    }

    monkeypatch.setattr(
        module,
        "validate",
        lambda db, files, settings, log_callback, progress_callback=None: (
            [report],
            {},
            module._rules(),
        ),
    )

    preview = module.preview_association(None, [g_file], {}, lambda _msg: None)
    change = preview["changes_by_file"][str(g_file)][0]
    assert change["tag"] == "FutureTransformerDevice"
    assert change["xml_id"] == "tr1"


def test_fuse_nearest_transformer_chain_accepts_non_transformerdis_tag(tmp_path):
    g_file = tmp_path / "fuse_custom_transformer.g"
    g_file.write_text(
        '''<G><Layer>
          <AnyFutureTransformerElement id="tr1" x="100" y="100" w="40" h="40" devref="#custom_transformer.g:CUSTOM_TRANSFORMER"/>
          <Text id="name1" x="120" y="60" w="100" h="30" ts="971765" lc="255,255,255"/>
          <AnyFutureFuseElement id="fu1" x="105" y="145" w="20" h="20" devref="#custom_fuse.g:CUSTOM_FUSE"/>
        </Layer></G>''',
        encoding="utf-8",
    )

    rows, context = FuseParser().discover(GParser().parse(g_file), _catalog(), {})
    assert len(rows) == 1
    assert rows[0]["nearest_transformer_xml_id"] == "tr1"
    assert rows[0]["nearest_transformer_name"] == "971765"
    assert rows[0]["derived_fuse_name"] == "FUSE971765"
    assert context["transformer_rows"][0]["object_type"] == "AnyFutureTransformerElement"


def test_transformer_logic_description_says_primary_element_then_classification_fallback():
    source = Path("src/dmm/ui/widgets/transformer_settings.py").read_text(encoding="utf-8")
    assert "Transformer_OH.pb.icn.g" in source
    assert "TRANSFORMER_OH 分类标记作为兜底" in source
