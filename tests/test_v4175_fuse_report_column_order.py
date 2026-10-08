from dmm.infrastructure.reporting.writer import FUSE_FIELDS


def test_derived_fuse_name_is_near_front_of_fuse_report():
    assert FUSE_FIELDS.count("derived_fuse_name") == 1
    assert FUSE_FIELDS.index("derived_fuse_name") == FUSE_FIELDS.index("devref") + 1
    assert FUSE_FIELDS.index("derived_fuse_name") < FUSE_FIELDS.index("transformer_assignment_status")
