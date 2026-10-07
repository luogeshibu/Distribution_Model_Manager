from dmm.domain.graphics_cleanup.rmu_feeder_topology import _apply_source_entry_nop_rule


def test_source_entry_nop_stops_only_entry_branch_not_whole_feeder():
    source_rows = [
        {"status": "SOURCE_CONFIRMED", "breaker_xml_id": "B1", "feeder_label": "OSLA-AH308"},
        {"status": "SOURCE_CONFIRMED", "breaker_xml_id": "B2", "feeder_label": "MNA4-AH332"},
    ]
    source_by_breaker = {"B1": "OSLA-AH308", "B2": "MNA4-AH332"}
    adjacency = {
        "B1": {"L1"}, "L1": {"B1", "P1"}, "P1": {"L1"},
        "B2": {"L2"}, "L2": {"B2", "P2"}, "P2": {"L2", "P3"}, "P3": {"P2"},
    }
    port_index = {
        "P1": {"rmu_name": "33137", "frame_xml_id": "R1", "port_name": "Y2", "port_xml_id": "P1"},
        "P2": {"rmu_name": "17296", "frame_xml_id": "R2", "port_name": "Y1", "port_xml_id": "P2"},
        # Same RMU has an NOP on Y3, but it is not the main-network entry switch.
        "P3": {"rmu_name": "17296", "frame_xml_id": "R2", "port_name": "Y3", "port_xml_id": "P3"},
    }
    boundary_nodes = {"P1", "P3"}

    active, excluded, direct = _apply_source_entry_nop_rule(
        source_rows, source_by_breaker, adjacency, port_index, boundary_nodes
    )

    assert excluded == {"OSLA-AH308"}
    assert active == source_by_breaker
    assert source_rows[0]["first_rmu_name"] == "33137"
    assert source_rows[0]["entry_port_name"] == "Y2"
    assert source_rows[0]["entry_port_is_nop"] == "YES"
    assert source_rows[0]["candidate_status"] == "ENTRY_BRANCH_STOPPED_AT_NOP"
    assert source_rows[1]["first_rmu_name"] == "17296"
    assert source_rows[1]["entry_port_name"] == "Y1"
    assert source_rows[1]["entry_port_is_nop"] == "NO"
    assert source_rows[1]["candidate_status"] == "PROPAGATE"
    assert direct["P1"] == {"OSLA-AH308"}
    assert direct["P2"] == {"MNA4-AH332"}
