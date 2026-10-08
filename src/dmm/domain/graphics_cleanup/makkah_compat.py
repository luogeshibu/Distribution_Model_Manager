"""Frozen Makkah constants used by the copied whole-graph topology logic.

These values are intentionally local to the graphics analyzer so the Jeddah
model-association parser and site rules remain untouched.
"""

RMU_LABEL_SEARCH_MAX_DISTANCE = 300.0
RMU_LABEL_EDGE_TOLERANCE = 20.0
RMU_LABEL_PATTERN = (
    r"^(?:"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
    r"|"
    r"\d{1,12}\s+[A-Za-z][A-Za-z0-9_.-]{0,31}"
    r")$"
)
BREAKER_LABEL_SEARCH_MAX_DISTANCE = 200.0
BREAKER_LABEL_AMBIGUITY_DELTA = 8.0

DEFAULT_RMU_NAME_EXCLUSIONS = [
    "N.O.P",
    "NOP",
    "N-O-P",
    "N_O_P",
    "SFI",
    "DAS/OK",
]
