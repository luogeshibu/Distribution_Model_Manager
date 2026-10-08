APP_NAME = "配网模型管理工具"
APP_NAME_EN = "Distribution Model Manager"
APP_VERSION = "4.2.23"
APP_DESCRIPTION = "吉达配网 G 文件模型关联与图形处理一体化工具"
APP_EDITION = "团队内部版"
APP_SITE_LABEL = "吉达现场版"
APP_SITE_LABEL_EN = "Jeddah Site Edition"
APP_BUILD_DATE = "2026-10-07"

WORKSPACE_RETENTION_DAYS = 30

# RMU name-label spatial recognition.
# These values are G-file coordinate units, not pixels.
# Selected directions are searched and each RMU keeps only its nearest single
# Text candidate within this distance.
RMU_LABEL_SEARCH_MAX_DISTANCE = 200.0
RMU_LABEL_EDGE_TOLERANCE = 20.0
# RMU cabinet names normally contain no spaces.  Field drawings also use a
# narrow family such as "66 B": numeric cabinet number + one space + suffix.
# Do NOT allow arbitrary internal spaces (for example "RMU 42646"), because
# that would turn many descriptive labels into RMU-name candidates.
RMU_LABEL_PATTERN = (
    r"^(?:"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
    r"|"
    r"\d{1,12}\s+[A-Za-z][A-Za-z0-9_.-]{0,31}"
    r")$"
)

# Visible breaker-label recognition inside an RMU.
BREAKER_LABEL_SEARCH_MAX_DISTANCE = 65.0
BREAKER_LABEL_AMBIGUITY_DELTA = 8.0

# RMU relay-signal association.  EFI G elements are discovered from the
# user-maintained element classification rather than any hard-coded element
# definition file name, so server-side element files may be renamed safely.
RMU_RELAY_SIGNAL_TAG = "pwbh"
RMU_RELAY_SIGNAL_CLASSIFICATION = "RMU_PWBH_EFI"
RMU_RELAY_SIGNAL_TABLE_ID = 13533
# RMU_PWBH_EFI uses slot-1 keyid for the EFI ``value`` column (domain 40)
# in dms_relay_sig. The generated KeyID is checked through verify_keyid before
# it can be written back.
RMU_RELAY_SIGNAL_DOMAIN = 40
RMU_RELAY_SIGNAL_CODE = "EFI INDICATOR"
