from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from g_file_studio.services.output_naming import normalize_merge_output_name


MERGED_FILE_SUFFIX = ".sln.pic.g"


class TemplateMode(str, Enum):
    """图框模板来源。"""

    BUILTIN = "builtin"
    CUSTOM = "custom"


class InputMode(str, Enum):
    """G 文件输入类型。"""

    SINGLE_FILE = "single_file"
    DIRECTORY = "directory"
    REMOTE_SSH = "remote_ssh"


class IdAction(str, Enum):
    """独立 ID 模块操作。"""

    CHECK = "check"
    REPAIR = "repair"

class RmuAction(str, Enum):
    """基础处理中的环网柜组合操作。"""

    NONE = "none"
    GROUP = "group"
    UNGROUP = "ungroup"




class RmuLedgerInputMode(str, Enum):
    """RMU 现有台账输入方式。"""

    FILE = "file"
    PASTE_TABLE = "paste_table"
    NAME_LIST = "name_list"


class RmuStatusPosition(str, Enum):
    """环网柜 channel_status 红色状态点在矩形框内的锚点位置。"""

    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    MIDDLE_LEFT = "middle_left"
    MIDDLE_RIGHT = "middle_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"

    @property
    def label(self) -> str:
        return {
            self.TOP_LEFT: "左上角",
            self.TOP_CENTER: "上边中点",
            self.TOP_RIGHT: "右上角",
            self.MIDDLE_LEFT: "左边中点",
            self.MIDDLE_RIGHT: "右边中点",
            self.BOTTOM_LEFT: "左下角",
            self.BOTTOM_CENTER: "下边中点",
            self.BOTTOM_RIGHT: "右下角",
        }[self]


class BasicOutputConflictAction(str, Enum):
    """基础处理输出文件发生冲突时的处理方式。"""

    OVERWRITE = "overwrite"
    TIMESTAMP = "timestamp"


# 向后兼容旧代码和已有配置。
PipelineInputMode = InputMode


class BasicSettings(BaseModel):
    """基础处理参数。

    输入既可以是单个 G 文件，也可以是包含多个 G 文件的目录。

    所有规则都只作用于 G 根节点直属 Layer 的直接子元素：
    - 属性替换：元素标签、属性名、旧值全部精确匹配后写入新值；
    - 元素删除：元素标签、属性名、属性值全部精确匹配后删除整个元素子树。

    G、Theme、Layer 本身、Layer 外内容，以及 Layer 图元内部的嵌套子元素均保持不变。
    """

    source_path: Path
    input_mode: InputMode = InputMode.DIRECTORY
    output_dir: Path

    replace_attribute: bool = False
    replace_target_tag: str = ""
    replace_target_attribute: str = ""
    replace_old_value: str = ""
    replace_new_value: str = ""

    # 删除元素上的某个属性本身，不删除元素。
    delete_attribute: bool = False
    delete_attribute_target_tag: str = ""
    delete_attribute_name: str = ""

    delete_matching_element: bool = False
    delete_target_tag: str = ""
    delete_target_attribute: str = ""
    delete_target_value: str = ""

    # 通用图元升级：支持显式 OLD -> NEW 图元映射；旧字段保留兼容旧配置。
    upgrade_icon_geometry: bool = False
    old_icon_files: list[Path] = Field(default_factory=list)
    new_icon_files: list[Path] = Field(default_factory=list)
    icon_upgrade_pairs: list[tuple[Path, Path]] = Field(default_factory=list)

    # 勾选后仅做保守的设备半像素吸附，并补齐缺失的 node_area/link。
    repair_connection_points: bool = False
    rmu_action: RmuAction = RmuAction.NONE
    # 兼容 v2.7/v2.8 代码；为 True 且 rmu_action=NONE 时按 GROUP 处理。
    group_rmu_elements: bool = False
    # 独立“环网柜处理”页面专用：组合前若当前文件已有 Merge，先彻底取消全部 Merge 再重建。
    # 默认 False，基础处理等其他调用保持原有组合逻辑不变。
    reset_existing_merges_before_rmu_group: bool = False

    # 图形组合清理：删除 Layer 直属全部 <Merge>，并可将识别到的 RMU 外框置于设备底层。
    remove_all_graphic_merges: bool = False
    lower_rmu_rects_after_merge_cleanup: bool = True

    # 线路与母线样式。颜色使用 #RRGGBB；线型 keep/solid/dashed 分别表示保持/实线/虚线。
    change_feedline_color: bool = False
    feedline_color: str = "#0000FF"
    feedline_line_style: str = "keep"
    change_connectline_color: bool = False
    connectline_color: str = "#0000FF"
    connectline_line_style: str = "keep"
    change_busdis_color: bool = False
    busdis_color: str = "#0000FF"
    busdis_line_style: str = "keep"
    change_bus_color: bool = False
    bus_color: str = "#0000FF"
    bus_line_style: str = "keep"

    # 环网柜增强处理。可与组合/取消组合同时启用。
    # 仅修改“框内存在 SMART Text”的环网柜外框颜色，不修改 SMART 字体。
    change_smart_rmu_frame_color: bool = False
    smart_rmu_frame_color: str = "#00A651"
    # 根据直属 Text[ts=SMR] 与最近有效环网柜 rect 的几何关系修改外框颜色；不修改 SMR Text。
    change_smr_rmu_frame_color: bool = False
    smr_rmu_frame_color: str = "#FF0000"
    # 将现有 RMU 名称识别算法最终选中的柜名 Text 统一改为白色；不影响其他 Text。
    set_rmu_name_text_white: bool = False
    # 独立 RMU 页面专用：基于 identify_rmus() 的智能柜结果添加/更新 Poke 详情图跳转。
    # 默认 False，其他基础处理/吉达流程不受影响。
    add_smart_rmu_poke: bool = False
    # v2.18.71 智能 RMU Poke ahref 模板。程序始终替换 {RMU}（识别到的智能 RMU，必填）；
    # 单文件若模板未使用 {FACNAME}，则完全不依赖 facName。仅当模板包含 {FACNAME}
    # 时，才读取当前 G 根节点 facName 进行替换。
    smart_rmu_poke_ahref_template: str = ""
    # 以下为 v2.18.69 及更早兼容字段；新版 RMU 页面不再写入，也不参与新版执行路径。
    smart_rmu_poke_naming_mode: str = "batch"
    smart_rmu_poke_single_rule: str = ""
    smart_rmu_poke_batch_rule: str = ""
    smart_rmu_poke_target_override: str = ""
    # 将 BusDis 环网柜内 devref 指向 channel_status 的红色状态点移动到框内指定锚点。
    reposition_channel_status: bool = False
    channel_status_position: RmuStatusPosition = RmuStatusPosition.BOTTOM_LEFT
    channel_status_inner_margin: int = Field(default=5, ge=0, le=1000)
    remove_bus_rmu_frame_and_reposition_title: bool = False

    # RMU 信息汇总。只读取/统计，不修改 G 图元；SMART 与 SMR 统一归类为智能环网柜。
    identify_rmu_name_and_type: bool = False
    # RMU cabinet-name resolver mode retained for compatibility.  The shared
    # recognizer now always uses the strict top-of-frame rule.
    rmu_name_resolution_mode: str = "selected_direction"
    rmu_name_top: bool = True
    rmu_name_bottom: bool = False
    rmu_name_left: bool = False
    rmu_name_right: bool = False
    # 用户指定的 RMU 柜名排除字符串。仅用于名称候选过滤，不影响柜体/柜型识别。
    rmu_name_exclusions: str = ""
    # 可配置智能 RMU 文本标记；完整文本匹配、全图扫描、唯一归属最近有效 RMU。
    # 默认 SMART / SMR；这些标记也会自动从柜名候选中排除。
    rmu_intelligent_markers: str = "SMART, SMR"
    rmu_smart_in_type: bool = False
    export_rmu_identification_csv: bool = True

    # 可选：将用户现有 RMU 台账与 G 图形识别结果进行对比。
    compare_rmu_ledger: bool = False
    rmu_ledger_input_mode: RmuLedgerInputMode = RmuLedgerInputMode.FILE
    rmu_ledger_file: Path | None = None
    rmu_ledger_text: str = ""

    output_conflict_action: BasicOutputConflictAction = BasicOutputConflictAction.OVERWRITE
    task_timestamp: str = ""




class IdSettings(BaseModel):
    """独立 ID 规则模板模块参数。"""

    source_path: Path
    input_mode: InputMode = InputMode.DIRECTORY
    output_dir: Path
    action: IdAction = IdAction.CHECK
    output_conflict_action: BasicOutputConflictAction = BasicOutputConflictAction.OVERWRITE
    task_timestamp: str = ""

class ConnectionRepairSettings(BaseModel):
    """连接点修复参数。

    该独立操作只允许修改 ``node_area`` 和 ``link``，其他图元属性保持不变。
    """

    source_path: Path
    input_mode: InputMode = InputMode.DIRECTORY
    output_dir: Path
    output_conflict_action: BasicOutputConflictAction = BasicOutputConflictAction.OVERWRITE
    task_timestamp: str = ""


class OrthogonalizeSettings(BaseModel):
    """线路正交化参数。

    处理只生成输出副本；线路重画保留原 ID 和拓扑引用，同类设备仅在安全条件下对齐。
    ``symbol_library_*`` 仅用于读取已经同步到本机 AppData 的服务器图元 Pin 几何，
    线路正交化本身不会因此访问 SSH。
    """

    source_path: Path
    input_mode: InputMode = InputMode.DIRECTORY
    output_dir: Path
    task_timestamp: str = ""
    symbol_library_host: str = ""
    symbol_library_root: str = ""


class MergeSettings(BaseModel):
    input_dir: Path
    output_dir: Path
    output_name: str = ""
    # App 中由用户定义的合并顺序；为空时由引擎按文件名自然排序。
    ordered_file_names: list[str] = Field(default_factory=list)
    feeder_gap: int = Field(default=300, ge=0)
    feeder_min_width: int = Field(default=1000, ge=0)
    merge_main_bus: bool = False
    main_bus_mode: str = "single"
    main_bus_groups: list[list[str]] = Field(default_factory=list)
    left_margin: int = Field(default=300, ge=0)
    top_margin: int = Field(default=300, ge=0)
    right_margin: int = Field(default=300, ge=0)
    bottom_margin: int = Field(default=300, ge=0)
    # Optional post-processing.  The merge UI enables Poke by default, but the
    # model keeps False as the compatibility default for direct/programmatic
    # callers that only want the legacy merge operation.
    add_poke_after_merge: bool = False
    poke_rmu_name_positions: tuple[str, ...] = ("top",)
    poke_rmu_name_exclusions: str = ""
    poke_rmu_intelligent_markers: str = "SMART, SMR"
    poke_classification_marker_entries: list[tuple[str, str, str]] = Field(default_factory=list)
    add_frame_after_merge: bool = False
    frame_template_file: Path | None = None
    frame_template_mode: TemplateMode = TemplateMode.BUILTIN
    frame_builtin_template_id: str = "default_sld_frame"
    frame_left: int = Field(default=50, ge=0)
    frame_top: int = Field(default=50, ge=0)
    frame_right: int = Field(default=50, ge=0)
    frame_bottom: int = Field(default=50, ge=0)

    @field_validator("output_name")
    @classmethod
    def normalize_output_name(cls, value: str) -> str:
        """合并结果统一使用 .sln.pic.g 后缀。"""
        return normalize_merge_output_name(value)


class MarginSettings(BaseModel):
    """主体图形四边距调整参数。

    仅可确认的 G File Studio 内置图框会被排除在主体边界计算之外，并在新画布上
    保留原四边距、同步拉伸外框和移动附属组件；其他图框要求用户先删除。
    """

    source_path: Path
    input_mode: InputMode = InputMode.DIRECTORY
    output_dir: Path
    left_margin: int = Field(default=500, ge=0)
    top_margin: int = Field(default=500, ge=0)
    right_margin: int = Field(default=500, ge=0)
    bottom_margin: int = Field(default=500, ge=0)
    preserve_existing_frame: bool = True
    # Jeddah fixed workflow only: the user has already chosen the authoritative
    # frame template, so any detected pre-existing frame is removed before margin
    # calculation and the selected template is added again in the final stage.
    force_remove_existing_frame: bool = False
    output_suffix: str = ""
    append_timestamp: bool = False
    task_timestamp: str = ""
    overwrite: bool = True


class PersonSettings(BaseModel):
    name: str = ""
    date: str = ""


class FrameSettings(BaseModel):
    """图框添加参数。

    输入既可以是单个 G 文件，也可以是包含多个 G 文件的目录。
    输出始终写入 output_dir，原始文件不会被覆盖。
    """

    source_path: Path
    input_mode: InputMode = InputMode.DIRECTORY
    output_dir: Path
    template_file: Path
    template_mode: TemplateMode = TemplateMode.BUILTIN
    builtin_template_id: str = "default_sld_frame"
    title: str = ""
    draw: PersonSettings = Field(default_factory=PersonSettings)
    approve: PersonSettings = Field(default_factory=PersonSettings)
    issue: PersonSettings = Field(default_factory=PersonSettings)
    frame_left: int = Field(default=50, ge=0)
    frame_top: int = Field(default=50, ge=0)
    frame_right: int = Field(default=50, ge=0)
    frame_bottom: int = Field(default=50, ge=0)
    output_suffix: str = ""
    append_timestamp: bool = False
    task_timestamp: str = ""
    overwrite: bool = True

    @property
    def edit_builtin_content(self) -> bool:
        """仅内置模板允许替换标题、姓名与日期。"""
        return self.template_mode == TemplateMode.BUILTIN

    def config_dict(self) -> dict[str, Any]:
        """生成内置模板的标题与签字栏配置。

        自定义模板模式不会使用这些配置，但保留同一数据结构，便于 UI 和配置文件复用。
        """
        return {
            "default": {
                "title": self.title,
                "draw": self.draw.model_dump(),
                "approve": self.approve.model_dump(),
                "issue": self.issue.model_dump(),
            },
            "files": {},
        }



class ProcessingResult(BaseModel):
    success: bool
    output_files: list[Path] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    statistics: dict[str, Any] = Field(default_factory=dict)
