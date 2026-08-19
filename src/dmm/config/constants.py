APP_NAME = "配网模型管理工具"
APP_NAME_EN = "Distribution Model Manager"
APP_VERSION = "4.1.17"
APP_DESCRIPTION = "配网 G 文件模型校验、候选选择及安全关联回写工具"
APP_EDITION = "团队内部版"
APP_BUILD_DATE = "2026-08-19"

WORKSPACE_RETENTION_DAYS = 30

# RMU name-label spatial recognition.
# These values are G-file coordinate units, not pixels.
# `RMU_LABEL_SEARCH_MAX_DISTANCE` is retained for configuration/backward
# compatibility, but RMU cabinet-name lookup now performs global search in
# user-selected directions and does not apply this legacy distance cut-off.
RMU_LABEL_SEARCH_MAX_DISTANCE = 120.0
RMU_LABEL_EDGE_TOLERANCE = 20.0
RMU_LABEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"

# Visible breaker-label recognition inside an RMU.
BREAKER_LABEL_SEARCH_MAX_DISTANCE = 65.0
BREAKER_LABEL_AMBIGUITY_DELTA = 8.0
