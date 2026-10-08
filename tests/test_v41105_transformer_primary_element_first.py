from pathlib import Path

from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import GParser


def _write(path: Path, devref: str, tag: str = "AnyTransformerTag") -> Path:
    xml = (
        '<G><Layer>'
        f'<{tag} id="tr1" x="100" y="100" w="40" h="40" devref="{devref}" keyid1="" keyid2=""/>'
        '<Text id="name1" x="110" y="60" w="70" h="20" ts="971765" lc="255,255,255"/>'
        '</Layer></G>'
    )
    path.write_text(xml, encoding="utf-8")
    return path


def _catalog(file_name: str, classification: str):
    return {
        "records": [
            {
                "file_name": file_name,
                "root_id": "ROOT",
                "classification": classification,
            }
        ]
    }


def test_primary_transformer_file_is_recognized_without_classification(tmp_path):
    g_file = _write(tmp_path / "primary.g", "#Transformer_OH.pb.icn.g:Transformer_OH")
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file),
        _catalog("Transformer_OH.pb.icn.g", "OTHER_DEVICE"),
        {},
    )
    assert len(rows) == 1
    assert rows[0]["recognition_source"] == "PRIMARY_ELEMENT_FILE"
    assert rows[0]["graphical_name"] == "971765"


def test_primary_transformer_file_accepts_path_and_case_normalization(tmp_path):
    g_file = _write(
        tmp_path / "primary_path.g",
        "#Elements/TRANSFORMER_OH.PB.ICN.G:Transformer_OH",
    )
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file), {}, {}
    )
    assert len(rows) == 1
    assert rows[0]["recognition_source"] == "PRIMARY_ELEMENT_FILE"


def test_classification_is_fallback_for_non_primary_element(tmp_path):
    g_file = _write(tmp_path / "fallback.g", "#custom_transformer.g:ROOT")
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file),
        _catalog("custom_transformer.g", "TRANSFORMER_OH"),
        {},
    )
    assert len(rows) == 1
    assert rows[0]["recognition_source"] == "TRANSFORMER_OH_CLASSIFICATION_FALLBACK"


def test_non_primary_without_classification_is_ignored(tmp_path):
    g_file = _write(tmp_path / "ignored.g", "#custom_transformer.g:ROOT")
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file),
        _catalog("custom_transformer.g", "OTHER_DEVICE"),
        {},
    )
    assert rows == []


def test_similar_but_not_exact_primary_filename_does_not_bypass_classification(tmp_path):
    g_file = _write(
        tmp_path / "similar.g",
        "#Transformer_OH.pb.icn.g.bak:Transformer_OH",
    )
    rows, _ = TransformerParser().discover_for_transformer_model(
        GParser().parse(g_file),
        _catalog("Transformer_OH.pb.icn.g.bak", "OTHER_DEVICE"),
        {},
    )
    assert rows == []
