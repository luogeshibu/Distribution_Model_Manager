from dmm.domain.graphics_cleanup.rmu_feeder_topology import _resolve_nop_rmu_ownership


def test_nop_rmu_owner_uses_non_nop_side_and_stops_boundary_feeder():
    owner, stopped, status = _resolve_nop_rmu_ownership(
        {"MNA4-AH332"},
        {"MNA4-AH332", "MNA2-AH335"},
        set(),
        0,
    )
    assert owner == "MNA4-AH332"
    assert stopped == {"MNA2-AH335"}
    assert status == "RESOLVED_BY_NON_NOP_PORTS"


def test_source_entry_excluded_feeder_is_still_reported_as_stopped_at_nop():
    owner, stopped, status = _resolve_nop_rmu_ownership(
        {"MNA2-AH335"},
        {"MNA2-AH335"},
        {"OSLA-AH308"},
        0,
    )
    assert owner == "MNA2-AH335"
    assert stopped == {"OSLA-AH308"}
    assert status == "RESOLVED_BY_NON_NOP_PORTS"


def test_nop_rmu_owner_does_not_guess_when_non_nop_ports_conflict():
    owner, stopped, status = _resolve_nop_rmu_ownership(
        {"F1", "F2"},
        {"F1", "F2", "F3"},
        set(),
        1,
    )
    assert owner == ""
    assert stopped == {"F3"}
    assert status == "CONFLICT_NON_NOP_PORTS"
