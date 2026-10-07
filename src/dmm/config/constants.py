APP_NAME = "配网模型管理工具"
APP_NAME_EN = "Distribution Model Manager"
APP_VERSION = "4.1.135"
APP_DESCRIPTION = "配网 G 文件模型校验、候选选择及安全关联回写工具"
APP_EDITION = "团队内部版"
APP_SITE_LABEL = "麦加现场版"
APP_SITE_LABEL_EN = "Makkah Site Edition"
APP_BUILD_DATE = "2026-10-07"

WORKSPACE_RETENTION_DAYS = 30

# RMU name-label spatial recognition.
# These values are G-file coordinate units, not pixels.
# `RMU_LABEL_SEARCH_MAX_DISTANCE` is retained for configuration/backward
# compatibility. Makkah assigns names by RIGHT -> BOTTOM -> GLOBAL fallback
# using rectangle minimum-edge distance; each RMU and each Text can be consumed only once.
RMU_LABEL_SEARCH_MAX_DISTANCE = 300.0
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
BREAKER_LABEL_SEARCH_MAX_DISTANCE = 200.0
BREAKER_LABEL_AMBIGUITY_DELTA = 8.0

# RMU relay-signal association.  G-symbol discovery is driven by the
# Element Management classification RMU_PWBH_EFI.  Database CODE remains a
# fixed business rule; table ID and domain remain configurable.
RMU_RELAY_SIGNAL_TAG = "pwbh"
RMU_RELAY_SIGNAL_DEVREF = "naripd_normal.pwbh.icn.g"  # legacy compatibility only; no longer used for discovery
RMU_RELAY_SIGNAL_CLASSIFICATION = "RMU_PWBH_EFI"
RMU_RELAY_SIGNAL_TABLE_ID = 13533
# NariPd_Normal.keyid1 is the EFI ``value`` column, which is column/domain 40
# in dms_relay_sig. The generated KeyID is checked through verify_keyid before
# it can be written back.
RMU_RELAY_SIGNAL_DOMAIN = 40
RMU_RELAY_SIGNAL_CODE = "EFI INDICATOR"

# RMU channel-status symbol association, ported from the Jazan field logic.
# Makkah keeps its own RMU-frame/name/database resolution unchanged; once an
# RMU is uniquely resolved, a Status whose devref contains the token below is
# associated through dms_terminal_info -> dms_channel_info by RMU COMBINED_ID.
# DR channels are excluded, and dms_channel_info.ID is converted to the G-file
# KeyID using table 13566 / domain 40.
RMU_CHANNEL_STATUS_TAG = "Status"
RMU_CHANNEL_STATUS_DEVREF_TOKEN = "channel_status.zt.icn.g"
RMU_CHANNEL_STATUS_TABLE_ID = 13566
RMU_CHANNEL_STATUS_DOMAIN = 40
RMU_CHANNEL_STATUS_KEYID_OFFSET = RMU_CHANNEL_STATUS_DOMAIN << 32
