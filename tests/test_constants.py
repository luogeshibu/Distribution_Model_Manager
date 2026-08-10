from dmm.config.constants import (
    RMU_LABEL_SEARCH_MAX_DISTANCE,
    RMU_LABEL_EDGE_TOLERANCE,
    WORKSPACE_RETENTION_DAYS,
)


def test_rmu_label_defaults():
    assert RMU_LABEL_SEARCH_MAX_DISTANCE == 120.0
    assert RMU_LABEL_EDGE_TOLERANCE == 20.0


def test_workspace_retention():
    assert WORKSPACE_RETENTION_DAYS == 30
