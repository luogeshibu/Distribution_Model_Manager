from pathlib import Path

import dmm.application.modules.transformer as transformer_module
from dmm.application.modules.transformer import TransformerModelModule


def _catalog():
    return {
        "records": [
            {"file_name": "tr.g", "root_id": "TRROOT", "classification": "Transformer_OH"},
        ]
    }


def test_transformer_model_uses_parser_global_geometry_without_db_name_reselection(tmp_path, monkeypatch):
    """Standalone transformer model must not let 13505 re-pick graphical names.

    The parser owns Text globally by pure geometry.  _analyze_file must trust
    that assignment and only perform database validation afterwards.
    """
    g = tmp_path / "tr.g"
    g.write_text(
        """<G><Layer>
        <TransformerDis id="tr1" x="100" y="100" w="20" h="20" devref="#tr.g:TRROOT"/>
        <TransformerDis id="tr2" x="100" y="180" w="20" h="20" devref="#tr.g:TRROOT"/>
        <Text id="name1" x="125" y="100" w="40" h="20" ts="10001" lc="255,255,255"/>
        <Text id="name2" x="125" y="180" w="40" h="20" ts="10002" lc="255,255,255"/>
        </Layer></G>""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        transformer_module,
        "resolve_drawing_feeder",
        lambda *args, **kwargs: {
            "ready": True,
            "feeder_id": "100",
            "feeder_source": "TEST",
            "feeder_evidence": "",
            "feeder_anchor": "",
            "feeder": {"id": "100", "name": "F1"},
            "candidates": [],
        },
    )
    monkeypatch.setattr(
        transformer_module,
        "enforce_device_feeder_membership",
        lambda *args, **kwargs: None,
    )

    # If the standalone model accidentally goes back through the shared
    # DB-assisted helper, this test must fail immediately.
    monkeypatch.setattr(
        transformer_module,
        "resolve_transformer_graphical_name",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("standalone transformer model must not DB-reselect graphical names")
        ),
    )

    module = TransformerModelModule()

    def fake_resolve_row(row, db):
        row = dict(row)
        row.update({
            "status": "UNLINKED",
            "association_ready": "YES",
            "writeback_needed": "YES",
            "db_device_id": row.get("graphical_name"),
            "db_feeder_id": "100",
        })
        return row

    monkeypatch.setattr(module, "_resolve_row", fake_resolve_row)

    report = module._analyze_file(
        object(),
        g,
        settings={"element_catalog": _catalog()},
    )
    rows = report["transformer_rows"]
    assert [row["graphical_name"] for row in rows] == ["10001", "10002"]
    assert all(row["name_source"] == "JEDDAH_TOP_RIGHT_GLOBAL_NUMERIC_WHITE_NO_BACKGROUND" for row in rows)
    assert len({row["name_xml_id"] for row in rows}) == 2
