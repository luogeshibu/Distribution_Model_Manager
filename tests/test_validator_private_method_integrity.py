import inspect
import re

from dmm.domain.rmu.validator import RmuValidator


def test_all_self_private_method_calls_exist():
    """
    Prevent regressions like v3.0.15 where
    self._make_expected_keyid(...) was called but not implemented.
    """
    source = inspect.getsource(RmuValidator)

    referenced = set(
        re.findall(r"self\.(_[A-Za-z0-9_]+)\s*\(", source)
    )

    implemented = {
        name
        for name in dir(RmuValidator)
        if name.startswith("_") and callable(getattr(RmuValidator, name))
    }

    missing = sorted(referenced - implemented)

    assert not missing, (
        "RmuValidator references undefined private methods: "
        + ", ".join(missing)
    )
