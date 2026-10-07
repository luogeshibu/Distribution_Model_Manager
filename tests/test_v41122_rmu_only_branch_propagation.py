from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_feeder_topology import _propagate_feeder_reachability


def test_feeder_propagation_stops_only_nop_branch_and_keeps_other_branch():
    adjacency = {
        "SRC": {"SPLIT"},
        "SPLIT": {"SRC", "SAFE1", "NOP"},
        "SAFE1": {"SPLIT", "SAFE2"},
        "SAFE2": {"SAFE1"},
        "NOP": {"SPLIT", "BLOCKED1"},
        "BLOCKED1": {"NOP", "BLOCKED2"},
        "BLOCKED2": {"BLOCKED1"},
    }
    labels = _propagate_feeder_reachability(
        {"SRC": "FDR-A"}, adjacency, {"NOP"}
    )
    assert labels["SRC"] == {"FDR-A"}
    assert labels["SAFE1"] == {"FDR-A"}
    assert labels["SAFE2"] == {"FDR-A"}
    assert not labels.get("NOP")
    assert not labels.get("BLOCKED1")
    assert not labels.get("BLOCKED2")


def test_other_source_breaker_is_barrier_not_cross_feeder_leak():
    adjacency = {
        "SRC_A": {"BUS"},
        "SRC_B": {"BUS", "OUT_B"},
        "BUS": {"SRC_A", "SRC_B"},
        "OUT_B": {"SRC_B"},
    }
    labels = _propagate_feeder_reachability(
        {"SRC_A": "FDR-A", "SRC_B": "FDR-B"}, adjacency, set()
    )
    assert labels["SRC_A"] == {"FDR-A"}
    assert labels["SRC_B"] == {"FDR-B"}
    assert labels["OUT_B"] == {"FDR-B"}


def test_rmu_topology_report_has_no_feedline_business_ownership_output():
    source = Path("src/dmm/domain/graphics_cleanup/rmu_feeder_topology.py").read_text(encoding="utf-8")
    assert "FeedLine拓扑归属（审计）" not in source
    assert "feedline_topology_audit.csv" not in source
    assert "本模块只判断RMU所属馈线" in source


def test_version_is_41122():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
