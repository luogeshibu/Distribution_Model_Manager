from __future__ import annotations

"""Lightweight runtime i18n for G File Studio.

The project intentionally keeps XML/business identifiers untouched.  Only user-facing
text is translated.  Chinese is the canonical source language so existing modules do
not need invasive business-logic changes.
"""

from html import escape
import re
from typing import Iterable

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QWidget,
)

from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.table_layout import configure_known_dense_table, schedule_fit_known_dense_table

LANG_ZH = "zh_CN"
LANG_EN = "en_US"
SUPPORTED_LANGUAGES = (LANG_ZH, LANG_EN)

# Exact translations for the visible application vocabulary. XML tags/attributes and
# domain values such as Bus, BusDis, SMART, keyid, devref, lc/lcc/ls are intentionally
# preserved.
EN: dict[str, str] = {
    "G File Studio · NARI 国际业务部": "G File Studio · NARI International Business Division",
    "G File Studio · 吉达现场": "G File Studio · Jeddah Site",
    "NARI 国际业务部": "NARI International Business Division",
    "NARI 国际业务部 · 吉达现场": "NARI International Business Division · Jeddah Site",
    "G 文件处理工具": "G File Processing Tool",
    "G 文件处理工具 · 吉达现场": "G File Processing Tool · Jeddah Site",
    "配置权限：普通模式": "Config Access: Standard",
    "配置权限：管理员模式": "Config Access: Admin",
    "配置权限：管理员已占用": "Config Access: Admin In Use",
    "中央配置权限": "Central Configuration Access",
    "进入管理员模式": "Enter Admin Mode",
    "初始化管理员": "Initialize Admin",
    "释放管理员权限": "Release Admin Access",
    "修改管理员密码": "Change Admin Password",
    "语言 / Language": "Language",
    "中文": "Chinese",
    "English": "English",
    "中文": "Chinese",
    "语言 / Language": "Language",
    "扫描 G 文件 ID、维护规则模板，并可强制把不符合模板或重复的 ID 修复为模板格式。": "Scan G-file IDs, maintain rule templates, and force-repair IDs that violate templates or are duplicated.",
    "打开新 G 时会对照模板检查：发现新的元素类型会提醒是否加入模板；已知类型只要固定前缀或总位数不符合模板就会告警。执行修复时会强制把格式不符和重复 ID 都更新为模板格式；同类型按当前最大合法完整 ID + 1。未知或未确认类型绝不擅自生成新 ID。": "When a new G file is opened, IDs are checked against the templates. New element types require confirmation before being added. Known types are warned when the fixed prefix or total length is invalid. Repair converts malformed and duplicate IDs to the confirmed template and allocates from the current maximum valid ID + 1. Unknown or unconfirmed types never receive generated IDs.",
    "规则格式：XML 元素类型 + 固定数字起始前缀 + 固定 ID 总位数。所有模块只允许使用这里已启用、已确认的规则；新增 ID 按同类型当前最大完整 ID + 1，并始终校验前缀和位数。": "Rule format: XML element type + fixed numeric prefix + fixed total ID length. All modules may use only enabled and confirmed rules. New IDs use the current maximum complete ID of the same type + 1 and are always validated for prefix and length.",
    "默认开启：处理输出时会把已有不符合模板的 ID 也强制修复。关闭后不会强制改写已有格式不符 ID；但所有模块新生成的 ID 仍必须严格使用已确认模板。": "Enabled by default: existing IDs that do not match the template are force-repaired in output. When disabled, existing malformed IDs are left unchanged, but every newly generated ID must still use a confirmed template.",
    "✓ 已确认": "✓ Confirmed",
    "前缀 + 总位数；同类型最大 ID + 1": "Prefix + total length; maximum ID of same type + 1",
    "扫描发现需要关注的内容，请在下方滚动查看。": "The scan found items that require attention. Scroll below to review them.",
    "扫描完成，详细结果如下。": "Scan completed. Detailed results are shown below.",
    "示例：ConnectLine 使用前缀 34、总位数 8，因此 34000053、34001838 合法，而 140、340123456 不合法。新增 ID 按同类型当前最大完整 ID + 1，并且结果必须继续满足前缀和总位数。": "Example: ConnectLine uses prefix 34 and total length 8, so 34000053 and 34001838 are valid, while 140 and 340123456 are invalid. New IDs use the current maximum complete ID of the same type + 1 and must still satisfy the configured prefix and total length.",
    "XML 元素类型不能为空。": "XML element type cannot be empty.",
    "ID 固定前缀必须是数字。": "The fixed ID prefix must be numeric.",
    "ID 总位数必须是正整数。": "The total ID length must be a positive integer.",
    "ID 总位数必须大于固定前缀长度。": "The total ID length must be greater than the fixed prefix length.",
    "关闭全局 ID 强制约束": "Disable Global ID Enforcement",
    "切换界面语言；选择会自动保存，下次启动继续使用。": "Switch the interface language. Your choice is saved automatically and restored at the next startup.",
    "NARI 国际业务部 · G 文件处理工具已就绪。鼠标停留在控件上可查看提示，按 F1 打开帮助中心。": "NARI International Business Division · G File Processing Tool is ready. Hover over controls for tips; press F1 to open Help Center.",
    "数据库": "Database",
    "连接与环境": "Connections & Environment",
    "连接与环境说明": "Connections & Environment Help",
    "当前环境": "Current Environment",
    "环境": "Environment",
    "新建 / 复制环境": "New / Copy Environment",
    "删除环境": "Delete Environment",
    "保存当前环境": "Save Current Environment",
    "文件服务器（SSH/SFTP · 严格只读）": "File Server (SSH/SFTP · Strictly Read-only)",
    "业务 G 根目录": "Business G Root",
    "标准图元库": "Standard Symbol Library",
    "保存文件服务器配置": "Save File Server Configuration",
    "连接运行日志": "Connection Runtime Log",
    "连接设置": "Connection Settings",
    "Oracle 数据库作为独立公共模块；后续需要数据库的功能统一复用这里的连接配置。": "Oracle database connectivity is provided as a shared module. Future database-backed features reuse this configuration.",
    "数据库连接说明": "Database Connection Help",
    "Oracle 数据库连接": "Oracle Database Connection",
    "用户名": "Username",
    "密码": "Password",
    "服务器地址": "Server Address",
    "端口": "Port",
    "显示密码": "Show Password",
    "隐藏密码": "Hide Password",
    "测试数据库连接": "Test Database Connection",
    "保存数据库配置": "Save Database Configuration",
    "数据库运行日志": "Database Runtime Log",
    "复制日志": "Copy Log",
    "清空日志": "Clear Log",
    "尚未验证": "Not Verified",
    "正在连接…": "Connecting…",
    "公共 Oracle 数据库连接配置与只读访问入口；后续需要数据库的业务模块统一复用该配置": "Shared Oracle database configuration and read-only access entry point for future database-backed modules",
    "异常小尺寸图元检测": "Abnormal Small Element Detection",
    "ID 检查与修复": "ID Check & Repair",
    "环网柜处理": "RMU Processing",
    "基础处理": "Basic Processing",
    "通用基础处理": "General Processing",
    "通用基础处理帮助": "General Processing Help",
    "数据与分析": "Data & Analysis",
    "检查与标准": "Validation & Standards",
    "图形处理": "Graphic Processing",
    "现场批处理": "Site Batch Processing",
    "环网柜 EFI 保护图元添加": "RMU EFI Protection Icon Addition",
    "馈线图合并": "Feeder Diagram Merge",
    "图形边距调整": "Drawing Margin Adjustment",
    "图框添加": "Drawing Frame",
    "线路正交化": "Orthogonalize Lines",
    "全局对齐同类设备，并在安全条件下重画或整理电气线路。": "Globally align repeated devices and safely redraw or orthogonalize electrical lines.",
    "线路正交化帮助": "Orthogonalize Lines Help",
    "开始线路正交化": "Orthogonalize Lines",
    "线路正交化输入": "Orthogonalization Input",
    "线路正交化输出目录": "Orthogonalization Output Directory",
    "吉达图形批处理": "Jeddah Graphics Batch Processing",
    "Jeddah 专用：第一步彻底取消图形组合（删除全部 <Merge>、RMU 外框置底），再批量删除异常小元素、SMART/SMR 红框、SMART 图元校正 + SMR 智能清理/转换 + 转换后图元复检、RMU 柜名严格按外框内三类组成并只从上方识别 + 白色 + 字号50 + 上边框上方10居中、删除 RMU channel_status 红色状态点、Bus 外框清理、馈线名称上移、删除 H.T、清理同柜重复 SMART、相邻 2000.00 + UPDATED_MEASURMENT 成对删除、ID 检查与修复、图形边距调整并添加图框": "Jeddah only: first fully ungroup graphics (remove all <Merge> elements and send RMU frames to back), then batch-remove abnormal small elements, highlight SMART/SMR frames in red, validate SMART RMU device icons, apply conditional SMR cleanup/conversion, and validate SMART device icons again after conversion, recognize only RMUs whose frames contain the three required elements and accept names only from above the frame, then set recognized names to white at font size 50 centered 10 units above the top frame, remove RMU channel_status red status points, remove Bus frames, move feeder names above buses, remove exact H.T text markers, remove duplicate SMART labels within each recognized RMU, remove adjacent 2000.00 + UPDATED_MEASURMENT pairs, run ID check & repair, adjust drawing margins, and add drawing frames.",
    "面向吉达现场的单馈线图一键标准化：批量输入多个 G 文件，逐张完成固定处理并输出最终单馈线图。": "One-click standardization for Jeddah single-feeder diagrams: batch-process multiple G files with a fixed workflow and output each final feeder diagram separately.",
    "吉达图形批处理说明": "Jeddah Graphics Batch Processing Help",
    "本模块是 Jeddah 专用批处理入口，不修改现有异常元素、RMU、基础处理或 ID 模块的业务逻辑。程序按固定顺序调用已有处理能力；原始输入文件不会覆盖，最终结果写入本次 workspace 运行目录。": "This is a Jeddah-only batch entry point. It does not change the business logic of the existing Small Element, RMU, Basic Processing, or ID modules. Existing capabilities are invoked in a fixed sequence; source files are never overwritten and final results are written to this workspace run directory.",
    "Jeddah 固定处理流程": "Jeddah Fixed Processing Workflow",
    "✓ 1. 彻底取消图形组合（删除全部 <Merge>，并将 RMU 外框置底）": "✓ 1. Fully ungroup graphics (remove all <Merge> and send RMU frames to back)",
    "✓ 2. 删除异常小尺寸元素": "✓ 2. Remove abnormal small elements",
    "✓ 3. 已识别 RMU 名称统一改白、字号 50，并在环网柜上边框上方 10 距离处水平居中": "✓ 3. Set recognized RMU names to white, font size 50, centered 10 units above the RMU top frame",
    "✓ 4. SMART 环网柜外框统一刷成红色": "✓ 4. Set SMART RMU frames to red",
    "✓ 4. RMU 外框最终一致性：柜内有 SMART = 红色；柜内无 SMART = 白色": "✓ 4. Finalize RMU frames: SMART present = red; no SMART = white",
    "✓ 5. SMART/NORMAL 图元检查：有 SMART 的柜使用智能 LBS / Circuit Breaker；无 SMART 的柜必须使用非智能图元": "✓ 5. SMART/NORMAL device check: SMART cabinets use intelligent LBS / Circuit Breaker symbols; cabinets without SMART must use non-smart symbols",
    "✓ 9. 使用当前服务器标准纠正环网柜内部 LBS/Circuit Breaker 的 SMART 与非 SMART 变体；无 SMART 的柜会参考同图其他 NORMAL 柜中服务器已知的非智能图元，候选冲突时退回 GLOBAL 明确绑定；<ZhaiWaiJieDiDaoZha> 接地刀闸保持不换。替换时保持原连接端点锚点，不执行独立线路级修复": "✓ 9. Use the current server standard to correct SMART/non-smart LBS and Circuit Breaker variants. Cabinets without SMART may learn a server-known NORMAL symbol from peer NORMAL cabinets in the same drawing; ties fall back to the explicit GLOBAL binding. Ground disconnectors remain unchanged. Replacements preserve existing connection anchors and do not run standalone line-level repair.",
    "✓ 5. SMART 图元检查：凡柜内已有 SMART，Y1/Y2/Y3 的 LBS 与 Q1 Circuit Breaker 必须使用 SMART devref": "✓ 5. SMART device check: any RMU already containing SMART must use SMART devrefs for Y1/Y2/Y3 LBS and Q1 Circuit Breaker",
    "✓ 6. SMR 环网柜外框统一刷成红色": "✓ 6. Set SMR RMU frames to red",
    "✓ 7. SMR 条件转换 SMART：已有 SMART 时删除外部 SMR并保持原 SMART；没有 SMART 时生成顶部居中 SMART（字号 20）；外框强制红色": "✓ 7. Conditional SMR-to-SMART conversion: if SMART already exists, remove the external SMR and preserve the existing SMART; otherwise create a top-centered SMART label (font size 20); force the frame red",
    "✓ 8. SMR 转换后再次执行 SMART 图元检查，确保 LBS / Circuit Breaker devref 正确": "✓ 8. Re-check SMART devices after SMR conversion to ensure LBS / Circuit Breaker devrefs are correct",
    "✓ 10. 删除 RMU 红色状态点（channel_status），沿用现有状态点识别/归属规则": "✓ 10. Remove RMU red status points (channel_status) using the existing status-point association rules",
    "✓ 11. 删除带 Bus 的环网柜矩形框、上移标题，并将有效配网 BusDis 母线统一刷为蓝色（无关联时 keyid 兜底）": "✓ 11. Remove RMU rectangles containing Bus, move the corresponding title above the bus, and set eligible distribution BusDis to blue (keyid fallback when unlinked)",
    "✓ 12. 将馈线名称移动到母线上方": "✓ 12. Move feeder names above the bus",
    "✓ 13. 删除精确 H.T 文字标识": "✓ 13. Remove exact H.T text markers",
    "✓ 14. 检查所有已识别配网 RMU；同一柜内存在多个 SMART 时仅保留原有第一个，删除重复项": "✓ 14. Check every recognized distribution RMU; if multiple SMART labels exist in one cabinet, keep the original first label and remove duplicates",
    "✓ 15. 仅当 2000.00 与 UPDATED_MEASURMENT 两个 Text 同行且相邻时成对删除": "✓ 15. Remove 2000.00 and UPDATED_MEASURMENT only when the two Text elements are on the same line and adjacent",
    "✓ 16. 使用全局 ID 模板执行 ID 检查与修复": "✓ 16. Run ID Check & Repair using global ID templates",
    "✓ 17. 调整主体图形四边距（默认 500）": "✓ 17. Adjust drawing margins (default 500)",
    "✓ 18. 添加图框": "✓ 18. Add drawing frame",
    "吉达图形边距": "Jeddah Drawing Margins",
    "吉达图框": "Jeddah Drawing Frame",
    "图形边距调整完成后，直接调用现有“图框添加”处理能力。默认使用程序内置模板；内置模板标题留空时自动使用输入文件名。": "After drawing-margin adjustment, the existing Drawing Frame processor is used directly. The built-in template is selected by default; when the built-in title is left blank, the input file name is used automatically.",
    "以上步骤为吉达固定流程，本页不复制或重写现有模块算法。": "These are the fixed Jeddah steps. This page does not copy or rewrite existing module algorithms.",
    "吉达参数": "Jeddah Parameters",
    "异常小尺寸阈值": "Abnormal Small Element Threshold",
    "RMU 柜名可能位置：": "Possible RMU Name Positions:",
    "RMU 柜名排除字符串：": "RMU Name Exclusions:",
    "RMU 柜名识别：严格模式。只有框内同时存在 BusDis、CBreakerDis、ZhaiWaiJieDiDaoZha 才认定为 RMU，柜名只从外框上方按一对一规则匹配。": "RMU name resolution: Strict mode. An RMU requires BusDis, CBreakerDis and ZhaiWaiJieDiDaoZha inside its frame, and its name is assigned one-to-one only from Text above the frame.",
    "吉达固定样式：SMART/SMR 外框 = 红色 #FF0000；只要 SMART Text 的中心位于 RMU 框内，就检查并校正 Y1/Y2/Y3 的 Load_Breaker_Switch 与 Q1 Circuit_Breaker 的 CBreakerDis devref（兼容 Circuit_Breaker_NO-SMART 与 Circuit_Breaker_NON-SMART 两种源图元）；若 SMR 柜内已有 SMART，只删除外部 SMR并保留原 SMART；若柜内没有 SMART，则生成顶部居中 SMART（字号 20）；SMR 处理后再次执行 SMART 图元复检；已识别 RMU 柜名 Text = 白色 #FFFFFF、字号 50，并与环网柜上边框保持 10 距离且水平居中；RMU channel_status 红色状态点直接删除；精确 H.T Text = 删除；所有已识别配网 RMU 都检查重复 SMART，同柜多个时保留 XML 中原有第一个并删除后续重复；2000.00 与 UPDATED_MEASURMENT 只有在同行且相邻（水平间距不超过 10）时才成对删除。": "Jeddah fixed styles: SMART/SMR frames = red #FF0000; whenever the center of a SMART Text lies inside an RMU frame, its Y1/Y2/Y3 Load_Breaker_Switch and Q1 Circuit_Breaker CBreakerDis devrefs are validated/corrected to SMART (supporting both Circuit_Breaker_NO-SMART and Circuit_Breaker_NON-SMART source variants); if an SMR cabinet already contains SMART, remove only the external SMR and preserve the existing SMART label; if it has no SMART, create a top-centered SMART label at font size 20; after SMR handling, validate SMART device devrefs again; recognized RMU name Text = white #FFFFFF, font size 50, centered with a 10-unit gap above the RMU top frame; RMU channel_status red status points are removed; exact H.T Text markers are removed; every recognized distribution RMU is checked for duplicate SMART labels, preserving the first/original XML label and removing later duplicates; 2000.00 and UPDATED_MEASURMENT are removed only when they are on the same visual line and adjacent with a horizontal gap no greater than 10.",
    "吉达固定样式：最终 RMU 外框按柜内 SMART 文字决定——有 SMART = 红色 #FF0000，无 SMART = 白色 #FFFFFF；有 SMART 的柜内 Y 类 Load_Breaker_Switch 与 Q 类 Circuit_Breaker 必须使用 SMART 图元，无 SMART 的柜必须使用 NORMAL / NO-SMART / NON-SMART 非智能图元，并可参考同图其他服务器已知 NORMAL 柜图元；若 SMR 柜内已有 SMART，只删除外部 SMR并保留原 SMART；若柜内没有 SMART，则生成顶部居中 SMART（字号 20）；SMR 处理后再次复检；接地刀闸保持现有吉达规则不替换；已识别 RMU 柜名 Text = 白色 #FFFFFF、字号 50，并与环网柜上边框保持 10 距离且水平居中；RMU channel_status 红色状态点直接删除；有效配网 BusDis 母线 = 蓝色 #0000FF；精确 H.T Text = 删除；同柜多个 SMART 时保留原有第一个并删除后续重复；2000.00 与 UPDATED_MEASURMENT 只有在同行且相邻时才成对删除。": "Jeddah fixed style: final RMU frame color is determined by the cabinet-local SMART text — SMART present = red #FF0000, no SMART = white #FFFFFF. SMART cabinets must use SMART Y Load_Breaker_Switch and Q Circuit_Breaker symbols; cabinets without SMART must use NORMAL / NO-SMART / NON-SMART symbols and may learn a server-known NORMAL variant from peer cabinets in the same drawing. If an SMR cabinet already has SMART, remove only the external SMR; otherwise create a top-centered SMART label at font size 20, then re-check. Ground disconnectors keep the existing Jeddah no-replacement rule. Recognized RMU names are white #FFFFFF at font size 50, centered 10 units above the frame. Remove RMU channel_status red points, make valid distribution BusDis blue #0000FF, remove exact H.T, keep only the first SMART per cabinet, and remove adjacent 2000.00 + UPDATED_MEASURMENT pairs only when they are on the same row and adjacent.",
    "开始吉达批处理": "Start Jeddah Batch Processing",
    "按上方固定 Jeddah 流程批量处理所选单馈线 G 文件。": "Batch-process the selected single-feeder G files using the fixed Jeddah workflow above.",
    "选择包含需要执行吉达批处理的单馈线 G 文件目录。": "Select a directory containing single-feeder G files for Jeddah batch processing.",
    "也可只选择一张单馈线 G 文件进行吉达标准处理。": "You may also select a single feeder G file for Jeddah standard processing.",
    "吉达批处理输出目录": "Jeddah Batch Output Directory",
    "当目标元素的 w 和 h 同时小于该值时，吉达批处理自动删除该异常小尺寸元素。": "When both w and h of a target element are below this value, Jeddah batch processing automatically deletes that abnormal small element.",
    "使用逗号、分号或换行分隔；按完整字符串匹配并忽略大小写，不使用包含匹配。": "Separate values with commas, semicolons, or new lines. Matching is exact and case-insensitive; substring matching is not used.",
    "吉达批处理输入": "Jeddah Batch Input",
    "吉达 RMU 柜名设置": "Jeddah RMU Name Settings",
    "RMU 柜名位置至少选择上方、下方、左侧或右侧中的一个。": "Select at least one RMU name position: Top, Bottom, Left, or Right.",
    "吉达图面处理阶段没有生成可继续执行 ID 检查的 G 文件。": "The Jeddah visual-processing stage did not produce any G files for the ID check stage.",
    "异常小尺寸阈值必须大于 0。": "The abnormal small-element threshold must be greater than 0.",
    "吉达批处理的 RMU 柜名位置至少选择一个方向。": "Select at least one RMU name direction for Jeddah batch processing.",
    "没有找到可处理的 G 文件。": "No G files were found for processing.",
    "全局 ID 模板未配置": "Global ID Templates Not Configured",
    "吉达批处理的 ID 处理阶段必须使用全局 ID 模板。请先在“ID 检查与修复”模块中确认 ID 规则。": "The Jeddah batch ID-processing stage requires the global ID templates. Confirm the ID rules in ID Check & Repair first.",
    "吉达批处理的图形边距不能小于 0。": "Jeddah batch drawing margins cannot be less than 0.",
    "吉达批处理图框模板不存在：": "Jeddah batch drawing-frame template does not exist: ",
    "帮助中心": "Help Center",
    "页面帮助": "Page Help",
    "帮助": "Help",
    "输入与输出": "Input & Output",
    "输入方式": "Input Source",
    "单个 G 文件": "Single G File",
    "G 文件目录": "G File Directory",
    "SSH 远程 G 文件（只读）": "SSH Remote G Files (Read-only)",
    "选择单个 G 文件": "Select G File",
    "选择 G 文件目录": "Select G File Directory",
    "浏览…": "Browse…",
    "输出目录（workspace，只读）": "Output Directory (workspace, read-only)",
    "输出文件": "Output File",
    "输出文件名": "Output File Name",
    "文件名": "File Name",
    "状态": "Status",
    "选择": "Select",
    "取消": "Cancel",
    "确定": "OK",
    "关闭": "Close",
    "保存": "Save",
    "删除": "Delete",
    "编辑": "Edit",
    "新增": "Add",
    "打开报告": "Open Report",
    "暂无报告": "No Report Yet",
    "开始执行": "Run",
    "开始基础处理": "Start Basic Processing",
    "开始环网柜处理": "Start RMU Processing",
    "开始合并": "Start Merge",
    "开始调整图形边距": "Adjust Drawing Margins",
    "开始图框添加": "Add Drawing Frame",
    "取消任务": "Cancel Task",
    "执行与日志": "Execution & Log",
    "清空日志": "Clear Log",
    "打开本次运行目录": "Open Current Run Folder",
    "处理日志会显示在这里……": "Processing log will appear here…",
    "任务已启动……": "Task started…",
    "处理完成。": "Processing completed.",
    "处理完成": "Completed",
    "处理完成（有告警）": "Completed with Warnings",
    "处理失败": "Processing Failed",
    "处理失败：": "Processing failed:",
    "告警：": "Warnings:",
    "统计：": "Statistics:",
    "输出：": "Output:",
    "基础处理输入": "Basic Processing Input",
    "基础处理输出目录": "Basic Processing Output Directory",
    "环网柜处理输入": "RMU Processing Input",
    "环网柜处理输出目录": "RMU Processing Output Directory",
    "异常小尺寸图元输入": "Abnormal Small Element Input",
    "异常小尺寸图元输出目录": "Abnormal Small Element Output Directory",
    "ID 扫描输入": "ID Scan Input",
    "ID 处理输入": "ID Processing Input",
    "ID 修复输出目录": "ID Repair Output Directory",
    "ID 检查与修复输出目录": "ID Check & Repair Output Directory",
    "馈线图合并输入目录": "Feeder Merge Input Directory",
    "馈线图合并输出目录": "Feeder Merge Output Directory",
    "输入文件与合并顺序": "Input Files & Merge Order",
    "图形边距调整输入": "Drawing Margin Input",
    "图形边距调整输出目录": "Drawing Margin Output Directory",
    "图框添加输入": "Drawing Frame Input",
    "图框添加输出目录": "Drawing Frame Output Directory",
    "扫描文件与输出": "Scan Files & Output",
    "扫描 / 处理文件": "Scan / Process Files",
    "输入文件": "Input File",
    "目录": "Directory",
    "文件": "File",
    "元素类型": "Element Type",
    "属性名": "Attribute Name",
    "属性值": "Attribute Value",
    "旧值": "Old Value",
    "新值": "New Value",
    "备注": "Notes",
    "扫描元素与属性": "Scan Elements & Attributes",
    "替换元素属性值": "Replace Element Attribute Value",
    "删除匹配元素": "Delete Matching Element",
    "删除元素属性": "Delete Element Attribute",
    "删除属性": "Delete Attribute",
    "通用处理规则": "General Processing Rules",
    "图元版本升级适配": "Symbol Version Upgrade",
    "启用图元版本升级适配": "Enable Symbol Version Upgrade",
    "通用图元升级": "Universal Symbol Upgrade",
    "启用通用图元升级": "Enable Universal Symbol Upgrade",
    "连接点修复": "Connection Repair",
    "修复连接点（补齐 node_area / link）": "Repair Connections (complete node_area / link)",
    "线路与母线样式": "Line & Bus Styles",
    "馈线": "Feeder",
    "连接线": "Connection Line",
    "配网母线": "Distribution Bus",
    "主网母线": "Main-grid Bus",
    "修改": "Modify",
    "颜色": "Color",
    "选择颜色": "Choose Color",
    "线型": "Line Style",
    "保持原样": "Keep Original",
    "实线": "Solid",
    "虚线": "Dashed",
    "图形组合处理": "Graphic Group Processing",
    "彻底取消图形组合（删除全部 <Merge>，并将 RMU 外框置底）": "Fully Ungroup Graphics (remove all <Merge> and send RMU frames to back)",
    "环网柜图元处理": "RMU Graphic Processing",
    "组合所有环网柜": "Group All RMUs",
    "不处理环网柜组合": "Do Not Change RMU Grouping",
    "环网柜增强操作（可多选）": "RMU Enhancements (multiple selection)",
    "修改含 SMART 的环网柜外框颜色": "Change Frame Color of RMUs Containing SMART",
    "修改含 SMR 的环网柜外框颜色": "Change Frame Color of RMUs Containing SMR",
    "将已识别的环网柜名称统一改成白色": "Set recognized RMU name text to white",
    "复用现有 RMU 柜名识别规则，只把最终识别到的柜名 Text 改为白色 #FFFFFF；其他 Text、设备、连接线和柜型识别逻辑均不改变。": "Reuse the existing RMU name-recognition rules and change only the final recognized RMU name Text to white #FFFFFF. Other Text, devices, connections, and cabinet-type recognition remain unchanged.",
    "RMU 柜名设置": "RMU Name Settings",
    "移动环网柜红色状态点（channel_status）": "Move RMU Red Status Point (channel_status)",
    "删除带 Bus 的环网柜外框，并将最近标题放到母线上方": "Remove RMU Frame Containing Bus and Move Nearest Title Above Bus",
    "环网柜名称与柜型识别": "RMU Name & Type Recognition",
    "启用环网柜名称与柜型识别": "Enable RMU Name & Type Recognition",
    "柜名可能位置：": "Possible RMU name positions:",
    "柜名排除字符串：": "RMU Name Exclusions:",
    "例如：NOP, DAS/OK, SFI": "Example: NOP, DAS/OK, SFI",
    "多个字符串使用逗号或分号分隔。按完整字符串匹配，忽略大小写和首尾空白；不会使用包含关系，例如排除 SFI 不会排除 SFI-1201。": "Separate multiple strings with commas or semicolons. Matching is exact, case-insensitive, and ignores surrounding whitespace. Substring matching is not used; for example, excluding SFI will not exclude SFI-1201.",
    "上方": "Top",
    "下方": "Bottom",
    "左侧": "Left",
    "右侧": "Right",
    "识别 SMART（单独列，不参与柜型）": "Recognize SMART (separate column, excluded from cabinet type)",
    "RMU 信息汇总": "RMU Summary",
    "RMU 信息汇总设置": "RMU Summary Settings",
    "启用 RMU 信息汇总": "Enable RMU Summary",
    "启用智能环网柜分类（SMART / SMR）": "Enable Smart RMU Classification (SMART / SMR)",
    "RMU 基础识别与汇总（必需）": "RMU Base Identification & Summary (Required)",
    "启用 RMU 基础识别与汇总（固定开启）": "Enable RMU Base Identification & Summary (Always On)",
    "识别范围（固定）：": "Identification Scope (Fixed):",
    "智能环网柜（SMART / SMR）": "Smart RMUs (SMART / SMR)",
    "非智能环网柜": "Non-Smart RMUs",
    "智能 / 非智能分类（固定开启）": "Smart / Non-Smart Classification (Always On)",
    "RMU 识别是本页面所有后续功能的基础能力，固定开启且每次处理都会输出汇总报告。": "RMU identification is the required base capability for all downstream functions on this page. It is always enabled and every run outputs a summary report.",
    "固定开启 SMART / SMR 智能分类，同时保留全部非智能 RMU；后续组合、改色、Poke、台账等功能统一复用该识别结果。": "SMART / SMR classification is always enabled while all non-smart RMUs are retained. Grouping, frame coloring, Poke, ledger comparison, and other downstream functions reuse this same identification result.",
    "基础识别固定覆盖智能与非智能全部有效 RMU，并检查重复名称/ID、柜名或柜型未识别、中低置信度等异常；每次运行都必须生成 RMU 汇总 CSV / HTML 报告。": "Base identification always covers all valid smart and non-smart RMUs and checks duplicate names/IDs, unidentified names or cabinet types, medium/low confidence, and other anomalies. Every run must generate RMU Summary CSV / HTML reports.",
    "直接解析 G 文件，不使用 OCR。只有 rect 框内同时存在 BusDis、CBreakerDis 和 ZhaiWaiJieDiDaoZha 才认定为环网柜；柜名优先严格只在用户勾选方向中寻找：单候选直接使用；同一最近文字组存在多个候选时才优先绿色文字。常规几何匹配失败时，仅当柜内 BusDis.key_name 唯一候选与所选方向附近同名 Text 完全一致时回退。柜名排除字符串按完整文本匹配过滤。柜型优先按 Y1/Y2/... 与 Q1/Q2/... 名称计数，名称无法判断时才回退到设备 devref。SMART 与 SMR 统一统计为“智能环网柜”；标记会全图扫描并唯一归属最近的有效 RMU，不要求文字完全落在柜框内，并保留识别来源。": "Parse G files directly without OCR. A rect is recognized as an RMU only when BusDis, CBreakerDis, and ZhaiWaiJieDiDaoZha are all present inside it. RMU names are searched strictly in the selected directions. A single candidate is used directly; green text is preferred only when multiple candidates exist in the same nearest text group. If normal geometry matching fails, fallback is allowed only when the unique BusDis.key_name candidate inside the cabinet exactly matches nearby Text in a selected direction. Name exclusions use exact-text matching. Cabinet type is determined from Y1/Y2/... and Q1/Q2/... labels first, then falls back to device devref. SMART and SMR are treated as smart RMU markers; markers are scanned globally and assigned uniquely to the nearest valid RMU without requiring the text box to be fully inside the cabinet frame, while preserving the recognition source.",
    "RMU 台账对比": "RMU Ledger Comparison",
    "现有 RMU 台账对比（可选）": "Existing RMU Ledger Comparison (Optional)",
    "启用现有 RMU 台账对比": "Enable Existing RMU Ledger Comparison",
    "RMU 台账文件": "RMU Ledger File",
    "台账文件": "Ledger File",
    "台账输入方式：": "Ledger Input Method:",
    "Excel / CSV 导入": "Excel / CSV Import",
    "直接粘贴表格": "Paste Table",
    "只粘贴 RMU 名称": "Paste RMU Names Only",
    "选择 RMU 台账": "Select RMU Ledger",
    "打开 RMU 汇总报告": "Open RMU Summary Report",
    "打开台账对比报告": "Open Ledger Comparison Report",
    "打开图元处理报告": "Open Graphic Processing Report",
    "异常尺寸阈值": "Abnormal Size Threshold",
    "检测规则": "Detection Rule",
    "扫描异常图元": "Scan Abnormal Elements",
    "异常图元结果": "Abnormal Element Results",
    "全选处理": "Select All for Processing",
    "删除选中异常图元": "Delete Selected Abnormal Elements",
    "处理": "Process",
    "未勾选": "Not Selected",
    "本次勾选": "Selected This Run",
    "确认删除": "Confirm Deletion",
    "尚未扫描。": "Not scanned yet.",
    "无法扫描": "Unable to Scan",
    "没有文件": "No Files",
    "没有找到可扫描的 G 文件。": "No G files were found for scanning.",
    "扫描失败": "Scan Failed",
    "扫描已取消。": "Scan cancelled.",
    "未勾选": "Nothing Selected",
    "请先在结果表第一列勾选需要处理的异常图元。": "Select the abnormal elements to process in the first column of the results table.",
    "删除选中异常图元": "Delete Selected Abnormal Elements",
    "扫描异常图元": "Scan Abnormal Elements",
    "全选处理": "Select All for Processing",
    "打开报告": "Open Report",
    "可单独选择 XML ID 或任意单元格/区域，按 Ctrl+C 复制": "Select an XML ID or any cell/range and press Ctrl+C to copy.",
    "首列勾选决定哪些图元参与处理；其余单元格可像表格一样单选/框选，按 Ctrl+C 复制。": "Use the first-column checkboxes to choose elements for processing. Other cells support normal single/range selection and Ctrl+C copy.",
    "当目标元素的 w 和 h 同时小于该值时，报告为异常小尺寸图元。": "An element is reported as abnormally small when both w and h are below this threshold.",
    "扫描完成后会生成/覆盖本模块的扫描 CSV/HTML 报告，可点击“打开报告”查看。": "Scanning generates or overwrites this module's CSV/HTML scan reports. Use Open Report to view the HTML report.",
    "删除结果表中已勾选的异常小尺寸图元，生成修改后的 G 文件，并生成/覆盖处理 CSV/HTML 报告；报告会列出实际删除项。": "Delete the checked abnormal elements, generate modified G files, and generate or overwrite the processing CSV/HTML reports. The reports list the elements actually deleted.",
    "异常小尺寸图元扫描完成，扫描报告已生成并覆盖上一份扫描报告。\n可点击“打开报告”查看 HTML 报告。": "Abnormal small-element scan completed. The scan reports were generated and replaced the previous scan reports.\nUse Open Report to view the HTML report.",
    "请先执行一次扫描并生成报告。": "Run a scan first to generate a report.",
    "ID 规则模板": "ID Rule Template",
    "XML 元素类型": "XML Element Type",
    "ID 固定前缀": "ID Fixed Prefix",
    "ID 起始前缀": "ID Prefix",
    "ID 总位数": "ID Total Digits",
    "总位数": "Total Digits",
    "合法示例": "Valid Example",
    "中央配置（Oracle 数据库 + 文件服务器）": "Central Configuration (Oracle Database + File Server)",
    "中央配置中心": "Central Configuration Center",
    "一键同步全部中央配置": "Sync All Central Configuration",
    "从中央同步数据库和文件服务器": "Sync Database and File Server from Central",
    "发布数据库和文件服务器到中央": "Publish Database and File Server to Central",
    "仅同步文件服务器配置": "Sync File Server Only",
    "发布文件服务器到中央": "Publish File Server to Central",
    "仅同步数据库配置": "Sync Database Only",
    "发布数据库配置到中央": "Publish Database to Central",
    "当前规则": "Current Rule",
    "新增 ID 规则": "Add ID Rule",
    "新增规则": "Add Rule",
    "编辑 ID 规则": "Edit ID Rule",
    "编辑规则": "Edit Rule",
    "删除规则": "Delete Rule",
    "扫描当前 G": "Scan Current G",
    "扫描选中 G 文件 ID 规则": "Scan Selected G Files for ID Rules",
    "正在扫描选中 G 文件…": "Scanning Selected G Files…",
    "扫描当前G文件（只检查ID）": "Scan Current G File (ID only)",
    "检查并强制修复 ID": "Check & Force Repair IDs",
    "启用全局 ID 模板强制约束": "Enable Global ID Template Enforcement",
    "关闭全局 ID 模板强制约束": "Disable Global ID Template Enforcement",
    "正常": "Normal",
    "格式不符": "Invalid Format",
    "重复 ID": "Duplicate ID",
    "未配置模板": "Template Not Configured",
    "扫描完成": "Scan Completed",
    "扫描失败": "Scan Failed",
    "扫描已取消。": "Scan cancelled.",
    "文件名关键字": "File Name Keywords",
    "加载 / 检查": "Load / Check",
    "加载中": "Loading",
    "查询并导入": "Search & Import",
    "查询并导入 G 文件": "Search & Import G Files",
    "导入全部可用": "Import All Available",
    "删除所选": "Remove Selected",
    "置顶": "Move to Top",
    "上移": "Move Up",
    "下移": "Move Down",
    "置底": "Move to Bottom",
    "顺序": "Order",
    "图框检查": "Frame Check",
    "状态/原因": "Status / Reason",
    "垂直对齐基准": "Vertical Alignment Baseline",
    "原始基准 Y": "Original Baseline Y",
    "主母线处理": "Main Bus Processing",
    "启用主网母线处理": "Enable Main Bus Processing",
    "单母线": "Single Bus",
    "双母线": "Double Bus",
    "选择主母线类型": "Select Main Bus Type",
    "设置母线分组": "Set Bus Groups",
    "设置主母线人工分组": "Set Manual Main Bus Groups",
    "主母线人工分组": "Manual Main Bus Grouping",
    "主母线处理不可用": "Main Bus Processing Unavailable",
    "请先加载并导入需要合并的馈线文件。": "Load and import the feeder files to be merged first.",
    "设置母线分组": "Set Bus Groups",
    "请先把馈线导入合并顺序列表。": "Import feeder files into the merge-order list first.",
    "创建母线组": "Create Bus Group",
    "请至少选择 2 个连续馈线。": "Select at least two consecutive feeders.",
    "同一母线组中的馈线必须连续。": "Feeders in the same bus group must be consecutive.",
    "母线分组无效": "Invalid Bus Grouping",
    "未设置任何组；所有馈线母线保持独立。": "No groups are configured; all feeder buses remain independent.",
    "创建母线组": "Create Bus Group",
    "清除所选分组": "Clear Selected Group",
    "清空全部分组": "Clear All Groups",
    "母线组": "Bus Group",
    "未分组": "Ungrouped",
    "按当前馈线顺序选择连续的两行或多行，然后点击“创建母线组”。同组馈线将共用主母线；未分组馈线保持独立。分组完全由人工指定，不读取 keyid。": "Select two or more consecutive feeder rows in the current merge order, then click Create Bus Group. Feeders in the same group will share the main bus; ungrouped feeders remain independent. Grouping is defined manually and does not use keyid.",
    "未设置任何组；所有馈线母线保持独立。": "No bus groups are configured; all feeder buses remain independent.",
    "布局参数": "Layout Parameters",
    "默认单线图宽度": "Default Single-line Diagram Width",
    "相邻图形间隔": "Adjacent Diagram Gap",
    "左边距": "Left Margin",
    "右边距": "Right Margin",
    "上边距": "Top Margin",
    "下边距": "Bottom Margin",
    "图形左边距": "Drawing Left Margin",
    "图形右边距": "Drawing Right Margin",
    "图形上边距": "Drawing Top Margin",
    "图形下边距": "Drawing Bottom Margin",
    "主体图形边距": "Main Drawing Margins",
    "图框模板": "Drawing Frame Template",
    "图框与输出参数": "Frame & Output Parameters",
    "图框左边距": "Frame Left Margin",
    "图框右边距": "Frame Right Margin",
    "图框上边距": "Frame Top Margin",
    "图框下边距": "Frame Bottom Margin",
    "内置模板：标题与签字栏": "Built-in Template: Title & Signatures",
    "左上标题": "Top-left Title",
    "使用程序内置模板": "Use Built-in Template",
    "使用客户自定义模板": "Use Custom Template",
    "客户自定义图框模板": "Custom Drawing Frame Template",
    "导出内置模板": "Export Built-in Template",
    "导出内置图框模板": "Export Built-in Drawing Frame Template",
    "图元文件": "Symbol File",
    "旧图元": "Old Symbol",
    "新图元": "New Symbol",
    "添加旧图元 G…": "Add Old Symbol G…",
    "添加新图元 G…": "Add New Symbol G…",
    "批量添加旧图元 G…": "Batch Add Old Symbol G…",
    "批量添加新图元 G…": "Batch Add New Symbol G…",
    "从服务器选择旧图元": "Choose Old Symbol from Server",
    "本地添加旧图元": "Add Old Symbol Locally",
    "从服务器选择新图元": "Choose New Symbol from Server",
    "本地添加新图元": "Add New Symbol Locally",
    "从服务器图元中选择旧图元": "Choose Old Symbols from Server Library",
    "从服务器图元中选择新图元": "Choose New Symbols from Server Library",
    "本地缓存": "Local Cache",
    "添加选中图元": "Add Selected Symbols",
    "智能自动配对": "Smart Auto Pair",
    "解除配对": "Unpair",
    "配对方式": "Pairing Method",
    "完全同名": "Exact Name",
    "图元类型 + 主体 ID": "Symbol Type + Body ID",
    "手动确认": "Manual",
    "自动同名配对": "Auto-pair Same Names",
    "配对选中": "Pair Selected",
    "手动配对…": "Manual Pair…",
    "手动 OLD → NEW 图元配对": "Manual OLD → NEW Symbol Pairing",
    "旧图元 OLD": "Old Symbol OLD",
    "新图元 NEW": "New Symbol NEW",
    "旧图元属性": "Old Symbol Properties",
    "新图元属性": "New Symbol Properties",
    "确认配对": "Confirm Pair",
    "手动配对完成": "Manual Pairing Completed",
    "手动配对不兼容": "Manual Pairing Incompatible",
    "文件名不要求一致。请选择要升级的旧图元和它对应的新图元；手动配对优先级最高。程序仍会检查 XML 类型与端口结构，避免错误映射。": "Filenames do not need to match. Choose the OLD symbol and its corresponding NEW symbol; manual pairing has the highest priority. XML type and pin topology are still validated to prevent unsafe mappings.",
    "文件名不需要一致。选择任意旧图元行后点击这里，或不选行直接打开配对窗口，再从已上传的新图元列表中明确指定 OLD → NEW。": "Filenames do not need to match. Select any OLD row and click here, or open the pairing dialog without a selection, then explicitly choose OLD → NEW from the uploaded symbols.",
    "文件名可以完全不同：自动无法确认时，点击“手动配对…”明确指定 OLD → NEW。": "Filenames may be completely different. If automatic pairing cannot confirm a match, use Manual Pair… to explicitly choose OLD → NEW.",
    "检查全部映射": "Check All Mappings",
    "升级规则": "Upgrade Rule",
    "旧图元文件": "Old Symbol File",
    "新图元文件": "New Symbol File",
    "几何变化": "Geometry Change",
    "devref": "devref",
    "缺少新图元": "Missing New Symbol",
    "缺少旧图元": "Missing Old Symbol",
    "未配对新图元": "Unpaired New Symbol",
    "通用图元升级检查": "Universal Symbol Upgrade Check",
    "通用图元升级检查未通过": "Universal Symbol Upgrade Check Failed",
    "移除选中": "Remove Selected",
    "清空": "Clear",
    "检查配对与参数": "Check Pairing & Parameters",
    "图元配对检查": "Symbol Pairing Check",
    "待检查": "Pending Check",
    "IP / 主机": "IP / Host",
    "端口": "Port",
    "用户名": "Username",
    "密码": "Password",
    "远程目录": "Remote Directory",
    "搜索 G 文件": "Search G Files",
    "测试 SSH 连接": "Test SSH Connection",
    "刷新 G 文件列表": "Refresh G File List",
    "保存 SSH 设置": "Save SSH Settings",
    "切换界面语言；选择会自动保存，下次启动继续使用。": "Switch UI language. The selection is saved automatically and restored on next launch.",
    "全选当前结果": "Select All Results",
    "取消当前结果": "Clear Current Results",
    "清空全部选择": "Clear All Selections",
    "下载所选到本地…": "Download Selected Locally…",
    "大小": "Size",
    "服务器修改时间": "Server Modified Time",
    "尚未加载远程文件": "Remote files not loaded",
    "已下载": "Downloaded",
    "总数": "Total",
    "距边": "Inset",
    "像素": "px",
    "姓名": "Name",
    "填写": "Fill",
    "日期默认是当前日期；点击日历按钮可修改。": "The date defaults to today; click the calendar button to change it.",
    "NARI 国际业务部 · G 文件处理工具已就绪。鼠标停留在控件上可查看提示，按 F1 打开帮助中心。": "NARI International Business Division · G File Processing Tool is ready. Hover over controls for tips; press F1 for Help Center.",
    "NARI 国际业务部 · 吉达现场 · G 文件处理工具已就绪。鼠标停留在控件上可查看提示，按 F1 打开帮助中心。": "NARI International Business Division · Jeddah Site · G File Processing Tool is ready. Hover over controls for tips; press F1 for Help Center.",
    "任务已成功完成，详细结果请查看日志。": "Task completed successfully. See the log for details.",
    "任务已完成，但部分文件处理失败或存在告警，请查看日志和报告。": "Task completed with failed files or warnings. See the log and reports for details.",
    "处理过程中发生错误，详情请查看日志区域。": "An error occurred during processing. See the log for details.",
    "当前主列表就是最终参与合并的文件集合和顺序。": "The main list is the final set and order of files to be merged.",
    "未设置任何组；所有馈线母线保持独立。": "No groups are configured; all feeder buses remain independent.",
    "母线类型：单母线": "Bus type: Single Bus",
    "母线类型：双母线": "Bus type: Double Bus",
    "母线类型：未选择": "Bus type: Not Selected",
    "请选择文件": "Select Files",
    "请选择规则": "Select Rule",
    "规则已存在": "Rule Already Exists",
    "规则无效": "Invalid Rule",
    "文件不存在": "File Not Found",
    "路径无效": "Invalid Path",
    "上次路径不存在": "Previous Path Not Found",
    "上次目录不存在": "Previous Directory Not Found",
    "SSH 连接失败": "SSH Connection Failed",
    "下载失败": "Download Failed",
    "下载完成": "Download Completed",
    "保存 SSH 设置失败": "Failed to Save SSH Settings",
    "SSH 设置已保存；所有使用 SSH 文件源的模块将复用这组最后输入。": "SSH settings saved. All modules using the SSH file source will reuse these latest values.",
    "现场 SMART Profile": "Site SMART Profile",
    "独立的现场 SMART 图元模板工具。由用户明确指定标准样本属于哪个现场，扫描样本学习该现场 SMART LBS / Circuit Breaker 的 CBreakerDis devref；保存 Profile 后可单独执行 SMART 图元一致性处理。该工具不参与当前“开始环网柜处理”的原有流程，也不修改现有 RMU 识别算法。": "Independent site SMART symbol profile tool. The user explicitly assigns standard samples to a site, scans them to learn that site's SMART LBS / Circuit Breaker CBreakerDis devrefs, then saves the profile for standalone SMART device consistency processing. This tool does not participate in the existing Start RMU Processing flow and does not modify the existing RMU recognition algorithm.",
    "打开现场 SMART Profile 管理器": "Open Site SMART Profile Manager",
    "扫描用户指定现场的标准 G 样本，确认并保存 SMART LBS / Circuit Breaker devref Profile；也可使用已保存 Profile 单独检查 SMART 环网柜图元。": "Scan standard G samples for a user-designated site, confirm and save the SMART LBS / Circuit Breaker devref profile, and optionally use a saved profile to check SMART RMU devices independently.",
    "现场 SMART Profile 管理": "Site SMART Profile Manager",
    "由用户明确指定样本所属现场，再扫描标准 G 文件学习 SMART LBS / Circuit Breaker 图元。程序不依赖 JED/MD/MAK 文件名前缀猜现场；保存 Profile 后可对任意 G 执行 SMART 图元一致性检查。": "Explicitly assign sample files to a site, then scan standard G files to learn SMART LBS / Circuit Breaker symbols. The program does not guess the site from JED/MD/MAK filename prefixes. After saving a profile, SMART symbol consistency can be checked on any G file.",
    "已保存 Profile": "Saved Profile",
    "请选择已保存 Profile": "Select a saved profile",
    "新建": "New",
    "Site Name": "Site Name",
    "Profile Name": "Profile Name",
    "标准样本 G 文件": "Standard Sample G Files",
    "扫描样本": "Scan Samples",
    "尚未扫描。": "Not scanned yet.",
    "SMART LBS devref": "SMART LBS devref",
    "SMART Circuit Breaker devref": "SMART Circuit Breaker devref",
    "保存 Profile": "Save Profile",
    "SMART 图元一致性处理": "SMART Device Consistency",
    "使用当前已保存 Profile 检查所有已识别 SMART 环网柜：Y 类 CBreakerDis 强制使用 Profile 的 SMART LBS devref，Q 类 CBreakerDis 强制使用 Profile 的 SMART Circuit Breaker devref。ID、keyid、node_area、名称、旋转和拓扑关系保持不变；若目标 SMART 图元内部几何不同，程序会依据同旋转的正确 SMART 样本反算 x/y/w/h，确保原 ConnectLine 连接点绝对坐标不变；非 SMART 环网柜不处理。": "Check every recognized SMART RMU using the currently saved profile: Y-type CBreakerDis devices must use the profile SMART LBS devref and Q-type devices must use the profile SMART Circuit Breaker devref. IDs, keyids, node_area, names, rotations and topology are preserved. If target SMART icon geometry differs, x/y/w/h are recalculated from a correct same-rotation SMART sample so the original ConnectLine attachment coordinates stay exactly fixed. Non-SMART RMUs are skipped.",
    "SMART Profile 输出目录": "SMART Profile Output Directory",
    "开始 SMART 图元一致性处理": "Start SMART Device Consistency",
    "请选择 Profile": "Select Profile",
    "请先选择并保存一个 Site Profile。": "Select and save a Site Profile first.",
    "Site Profile 样本": "Site Profile Samples",
    "SMART Profile 处理输入": "SMART Profile Processing Input",
    "Profile 未完成": "Profile Incomplete",
    "Site Name、Profile Name、SMART LBS 和 SMART Circuit Breaker 都必须确认。": "Site Name, Profile Name, SMART LBS and SMART Circuit Breaker must all be confirmed.",
    "Profile 已保存": "Profile Saved",
    "删除 Profile": "Delete Profile",
    "扫描失败": "Scan Failed",

    "指定标准 G 文件属于哪个现场，扫描并保存该现场的 SMART LBS / Circuit Breaker 图元模板，再按 Profile 做通用 SMART 图元一致性检查。": "Assign standard G files to a site, scan and save that site's SMART LBS / Circuit Breaker symbol profile, then run generic SMART device consistency checks with the profile.",
    "这是独立工具，不修改原来的 RMU、吉达批处理、基础处理或 ID 模块逻辑。现场由用户明确指定；文件名 JED / MD / MAK 仅作为文件名，不用于强制判断 Site。": "This is a standalone tool. It does not change the existing RMU, Jeddah Batch, Basic Processing, or ID module logic. The site is explicitly selected by the user; JED / MD / MAK are treated only as filename text and are not used to force a site decision.",
    "现场 Profile 管理": "Site Profile Management",
    "尚未保存 Site Profile。建议先选择同一现场的标准 G 样本并扫描。": "No Site Profile has been saved. Select and scan standard G samples from the same site first.",
    "由用户指定现场并扫描标准 G 样本，保存 SMART LBS / Circuit Breaker devref Profile，再执行通用 SMART 图元一致性检查": "Assign a site and scan standard G samples, save the SMART LBS / Circuit Breaker devref profile, then run generic SMART device consistency checks",
    "请先输入 Site Name，再扫描属于该现场的标准样本。": "Enter the Site Name before scanning standard samples for that site.",
    "请先输入 Profile Name。": "Enter the Profile Name first.",
    "候选一致率低于 80%，请人工检查下拉候选后再保存。": "Candidate consistency is below 80%. Review the dropdown candidates before saving.",
    "扫描完成。请确认两个 devref 后保存 Profile。": "Scan completed. Confirm both devrefs before saving the profile.",
    "由用户指定标准 G 样本所属现场，扫描并保存 SMART LBS / Circuit Breaker 图元模板，再按 Profile 做通用 SMART 图元一致性检查。": "Assign standard G samples to a site, scan and save the SMART LBS / Circuit Breaker symbol profile, then run generic SMART device consistency checks with the profile.",
    "现场由用户明确指定，程序不依赖 JED/MD/MAK 文件名前缀强制判断。Profile 管理、样本扫描和 SMART 图元一致性处理都在本页完成；使用右侧滚动条向下继续操作。": "The site is explicitly selected by the user; the program does not force a site from JED/MD/MAK filename prefixes. Profile management, sample scanning and SMART device consistency processing are all completed on this page; use the right-side scroll bar to continue downward.",
    "Site Profile 列表": "Site Profile List",
    "像 ID 规则模板一样维护现场 SMART Profile。先新建/选择一行，再在下方指定 Site、扫描标准样本并确认 SMART LBS / Circuit Breaker devref。": "Maintain Site SMART Profiles like ID rule templates. Create or select a row, then specify the site below, scan standard samples, and confirm the SMART LBS / Circuit Breaker devrefs.",
    "新建 Profile": "New Profile",
    "删除 Profile": "Delete Profile",
    "SMART LBS": "SMART LBS",
    "SMART Circuit Breaker": "SMART Circuit Breaker",
    "Samples": "Samples",
    "Confidence": "Confidence",
    "Status": "Status",
    "Profile 设置与样本扫描": "Profile Settings and Sample Scan",
    "当前处理 Profile：未选择": "Current Processing Profile: Not selected",
    "使用列表中当前选中的已保存 Profile 检查所有已识别 SMART 环网柜：Y 类 CBreakerDis 强制使用 Profile 的 SMART LBS devref，Q 类 CBreakerDis 强制使用 Profile 的 SMART Circuit Breaker devref。ID、keyid、node_area、名称、旋转和拓扑关系保持不变；若目标 SMART 图元内部几何不同，程序会依据同旋转的正确 SMART 样本反算 x/y/w/h，确保原 ConnectLine 连接点绝对坐标不变；非 SMART 环网柜不处理。": "Use the currently selected saved profile in the list to check all recognized SMART RMUs: Y-type CBreakerDis devices must use the profile SMART LBS devref and Q-type devices must use the profile SMART Circuit Breaker devref. IDs, keyids, node_area, names, rotations and topology are preserved. If target SMART icon geometry differs, x/y/w/h are recalculated from a correct same-rotation SMART sample so the original ConnectLine attachment coordinates remain exactly fixed. Non-SMART RMUs are skipped.",
    "请先在上方列表选择并保存一个 Site Profile。": "Select and save a Site Profile from the list above first.",
    "新建 Profile：填写 Site / Profile Name 后扫描标准样本。": "New Profile: enter Site / Profile Name, then scan standard samples.",
    "第一次用标准 G 文件学习并保存现场 SMART 图元 Profile；以后复用同一套 G 文件输入直接执行 SMART 图元一致性处理。": "Learn and save a site SMART symbol profile from standard G files the first time, then reuse the same G-file input area for SMART device consistency processing.",
    "同一套 G 文件输入同时用于 Profile 学习和后续一致性处理：第一次选择标准样本后扫描并保存 Profile；以后选择待处理文件，直接使用已保存 Profile 执行。现场由用户明确指定，不依赖文件名前缀强制判断；使用右侧滚动条向下继续操作。": "The same G-file input is used for profile learning and later consistency processing: scan standard samples and save the profile the first time, then select target files and run with the saved profile. The site is explicitly assigned by the user and is not forced from filename prefixes; use the right-side scroll bar to continue downward.",
    "像 ID 规则模板一样维护现场 SMART Profile。第一次新建 Profile 并扫描标准样本；Profile Ready 后可长期复用。": "Maintain site SMART profiles like ID rule templates. Create a profile and scan standard samples once; reuse it after the profile is Ready.",
    "Profile 设置": "Profile Settings",
    "G 文件输入（学习与处理共用）": "G File Input (Shared for Learning and Processing)",
    "第一次：选择该现场的标准 G 文件 → 扫描 Profile → 确认 devref → 保存。以后：选择待处理 G 文件 → 直接执行一致性处理。无需第二套输入。": "First use: select standard G files for the site → scan the profile → confirm devrefs → save. Later: select target G files → run consistency processing directly. No second input is required.",
    "扫描并创建 Profile": "Scan and Create Profile",
    "重新扫描 Profile": "Rescan Profile",
    "执行 SMART 图元一致性处理": "Run SMART Device Consistency",
    "输出目录（workspace）": "Output Directory (workspace)",
    "尚未执行一致性处理。": "SMART consistency has not been run yet.",
    "打开报告": "Open Report",
    "报告不存在": "Report Not Found",
    "当前还没有可打开的 SMART Profile HTML 报告，请先执行处理。": "There is no SMART Profile HTML report to open yet. Run processing first.",
    "正在执行 SMART 图元一致性处理……": "Running SMART device consistency processing...",

}

# Long but frequently visible descriptions/tooltips. Exact mapping keeps the UI clean.
EN.update({
    "检测 ConnectLine、FeedLine、Bus、BusDis 中 w/h 同时过小的疑似残留短线图元；通过首列勾选单选/多选/全选后统一执行处理": "Detect suspicious residual short elements in ConnectLine, FeedLine, Bus and BusDis where both w/h are too small; select one, multiple or all rows in the first column before processing.",
    "全局 ID 规则中心：维护模板、扫描覆盖并强制修复格式异常或重复 ID": "Global ID rule center: maintain templates, scan coverage, and force-repair malformed or duplicate IDs.",
    "独立处理环网柜组合/取消组合、增强操作，以及柜名与柜型识别": "Process RMU grouping, enhancements, and RMU name/type recognition independently.",
    "执行通用属性、图元升级、馈线标题、连接点和线路/母线颜色处理；涉及 ID 时强制使用全局模板": "Run general attribute, symbol upgrade, feeder title, connection, and line/bus style processing; global templates are mandatory for ID operations.",
    "按用户选择顺序合并多个馈线 G 图": "Merge multiple feeder G drawings in the user-defined order.",
    "调整主体四边距，并同步适配内置图框": "Adjust main drawing margins and synchronize the built-in drawing frame.",
    "添加 SLD 外框、标题和签字栏": "Add SLD border, title, and signature fields.",
    "查看使用说明和目录建议": "View usage instructions and workspace recommendations.",
    "支持处理单个 G 文件或整个目录；勾选需要的规则后统一点击“开始基础处理”。": "Process a single G file or an entire directory. Select the required rules, then click Start Basic Processing.",
    "按用户选择顺序合并多个馈线 G 图，完成垂直对齐、冲突 ID 处理和画布计算。": "Merge feeder G drawings in the selected order with vertical alignment, conflicting-ID handling, and canvas calculation.",
    "把主体图形整体移动到指定四边距；内置图框自动同步调整，其他图框要求先删除。": "Move the main drawing to the specified margins. The built-in frame is adjusted automatically; other frames must be removed first.",
    "支持为单个 G 文件或整个目录批量添加并适配 SLD 图框。": "Add and adapt SLD drawing frames for a single G file or an entire directory.",
    "独立处理环网柜组合、增强操作，以及柜名与柜型识别。": "Process RMU grouping, enhancements, and RMU name/type recognition independently.",
    "查看推荐流程、页面用途、目录说明和常见问题。按 F1 可随时打开本页面。": "View the recommended workflow, page purposes, folder guidance, and FAQs. Press F1 at any time to open this page.",
    "鼠标停留在按钮或字段上可以查看简短提示；圆形问号可查看详细说明。": "Hover over buttons or fields for short tips; use the round question-mark buttons for detailed help.",
    "SSH 服务器严格只读：仅列目录、读取文件属性和下载 G 文件；G File Studio 不提供上传、覆盖、重命名、删除或修改服务器文件的接口。": "The SSH server is strictly read-only: only directory listing, file metadata reading, and G-file download are allowed. G File Studio provides no upload, overwrite, rename, delete, or server-side modification operation.",
    "本地目录或 SSH/SFTP 只读远程 G 文件。远程模式只允许读取和下载，不会修改服务器文件。": "Use a local directory or read-only SSH/SFTP G files. Remote mode only reads and downloads files and never modifies the server.",
    "输出由程序统一管理。每次运行创建独立 workspace 目录，仅保留 30 天；需要长期保存请自行复制。": "Outputs are managed by the application. Each run gets a separate workspace folder retained for 30 days; copy files elsewhere for long-term storage.",
    "这是整个 G 文件级的组合清理，不只针对环网柜。启用后删除 Layer 中全部 <Merge>，并将识别到的 RMU 外框 <rect> 移到柜内设备之前，使外框位于设备底层。除删除 Merge 和调整 rect 的 XML 顺序外，不修改任何设备属性、坐标、ID、keyid、devref 或 tfr。": "This is a whole-G-file group cleanup, not an RMU-only operation. It removes every <Merge> in Layer and moves recognized RMU frame <rect> elements before cabinet devices so frames stay behind devices. No device attribute, coordinate, ID, keyid, devref or tfr is changed; only Merge removal and rect XML order are affected.",
    "按元素标签统一调整线路与母线样式。颜色仅修改 lc/lcc；线型仅修改 ls：实线=1、虚线=2。颜色勾选与线型选择彼此独立；线型选择‘保持原样’时不会修改 ls。不会修改填充色、线宽 lw、坐标、ID 或引用。": "Adjust line and bus styles by element tag. Color changes only lc/lcc; line style changes only ls (solid=1, dashed=2). Color and line-style settings are independent; Keep Original leaves ls unchanged. Fill, lw, coordinates, IDs and references are never changed.",
})


# Register complete help/field-help translations so rich-text dialogs are fully English.
try:
    from g_file_studio.ui.help_content import APP_HELP, APP_HELP_EN, FIELD_HELP, FIELD_HELP_EN
    for _key, (_zh_title, _zh_html) in APP_HELP.items():
        _en_title, _en_html = APP_HELP_EN[_key]
        EN[_zh_title] = _en_title
        EN[_zh_html] = _en_html
    for _key, _zh_text in FIELD_HELP.items():
        if _key in FIELD_HELP_EN:
            EN[_zh_text] = FIELD_HELP_EN[_key]
except Exception:
    pass

# v2.18.7: complete the remaining static UI/help/tool-tip vocabulary so English
# mode never falls back to a generic placeholder for normal controls.
EN.update({
    "本地 G 文件目录": "Local G File Directory",
    "留空自动生成 MERGED-时间戳.sln.pic.g；也可手动输入名称": "Leave blank to generate MERGED-timestamp.sln.pic.g automatically, or enter a file name manually.",
    "启用后必须选择单母线或双母线。只检查所选主母线；异常短线 Bus 不再在这里过滤，请统一使用“异常小尺寸图元检测”模块处理。": "When enabled, select Single Bus or Double Bus. Only the selected main bus is checked. Abnormally short Bus elements are handled by Abnormal Small Element Detection instead.",
    "点击选择单母线或双母线；勾选主网母线处理时也会自动弹出选择。": "Click to select Single Bus or Double Bus. The same selection dialog opens automatically when main-grid bus processing is enabled.",
    "按当前馈线顺序人工指定哪些连续馈线共用一组主母线；未分组馈线保持独立。": "Manually specify which consecutive feeders share one main-bus group. Ungrouped feeders remain independent.",
    "请选择当前参与合并的馈线图属于单母线还是双母线。": "Select whether the feeder diagrams in this merge use a single-bus or double-bus arrangement.",
    "单母线：只检查 Y 值最小的最高有效水平 <Bus>。\n双母线：检查最高母线，以及同方向下方长度大致相同的第二条有效水平 <Bus>。": "Single Bus: check only the highest valid horizontal <Bus> with the smallest Y value.\nDouble Bus: check the highest bus and the second valid horizontal <Bus> below it in the same direction with approximately the same length.",
    "馈线合并结果只能写入 G File Studio 的 workspace 运行目录，路径不可修改。处理完成后请点击“打开本次运行目录”查看或复制文件；运行目录自动保留 30 天。": "Feeder-merge output is written only to the G File Studio workspace run directory and cannot be changed here. After processing, use Open Current Run Folder to view or copy files. Run folders are retained for 30 days.",
    "每个馈线图的最小占用宽度。实际宽度小于该值时按该值预留；实际宽度超过该值时使用实际宽度。该宽度不包含相邻馈线间隔。": "Minimum reserved width for each feeder diagram. If the actual width is smaller, this value is reserved; otherwise the actual width is used. Adjacent-feeder spacing is not included.",
    "启用后先选择单母线或双母线，再人工设置母线分组。程序不再使用 keyid 判断分组；只有同一人工分组内、且在当前馈线顺序中连续的文件才会共用母线。未分组馈线保持独立。": "When enabled, first select Single Bus or Double Bus, then configure bus groups manually. keyid is not used for grouping. Only consecutive files in the same manual group share a bus; ungrouped feeders remain independent.",
    "“组合所有环网柜”会将每个直属 <rect> 作为环网柜外框，只组合完整位于矩形框内部的直属图元；任何部分位于框外的连接线、状态图标和文字都不会进入组合。彻底取消图形组合已经移动到“基础处理 → 图形组合处理”，因为该操作会删除整个 G 文件中的全部 <Merge>，不再属于 RMU 专用功能。": "Group All RMUs treats each direct <rect> as an RMU frame and groups only direct elements fully inside that rectangle. Connection lines, status icons, and text extending outside the frame are excluded. Full graphic ungrouping is now under Basic Processing > Graphic Group Processing because it removes every <Merge> in the G file.",
    "直接解析 G 文件，不使用 OCR。只有 rect 框内同时存在 BusDis、CBreakerDis 和 ZhaiWaiJieDiDaoZha 才认定为环网柜；柜名优先严格只在用户勾选方向中寻找：单候选直接使用；同一最近文字组存在多个候选时才优先绿色文字。常规几何匹配失败时，仅当柜内 BusDis.key_name 唯一候选与所选方向附近同名 Text 完全一致时回退。柜名排除字符串按完整文本匹配过滤。柜型优先按 Y1/Y2/... 与 Q1/Q2/... 名称计数，名称无法判断时才回退到设备 devref。SMART 与 SMR 统一统计为“智能环网柜”，并保留识别来源。": "Parse G files directly without OCR. A rect is recognized as an RMU only when BusDis, CBreakerDis, and ZhaiWaiJieDiDaoZha are all present inside it. RMU names are first searched strictly in the selected directions. A single candidate is used directly; green text is preferred only when multiple candidates exist in the same nearest text group. If normal geometry matching fails, fallback is allowed only when the unique BusDis.key_name candidate inside the cabinet exactly matches nearby Text in a selected direction. User-defined RMU name exclusions filter exact text values. Cabinet type is determined from Y1/Y2/... and Q1/Q2/... names first, then falls back to device devref. SMART and SMR are both counted as Smart RMU while preserving the recognition source.",
    "BusDis.key_name + Text 确认回退": "BusDis.key_name + Text confirmed fallback",
    "RMU 信息汇总始终统计全部有效环网柜。勾选后额外将 SMART/SMR 统一归类为智能环网柜；不勾选时仅汇总 RMU 名称、柜型、重复和识别异常，不进行智能/普通分类。": "RMU Summary always includes all valid RMUs. When enabled, SMART/SMR are additionally classified as Smart RMU. When disabled, the report still summarizes names, cabinet types, duplicates, and recognition issues without smart/normal classification.",
    "无论是否启用智能分类，都会统计全部有效 RMU，并检查重复名称/ID、柜名或柜型未识别、中低置信度等异常；这些信息会在 RMU 汇总 HTML 报告中重点提示。": "All valid RMUs are counted regardless of smart classification. Duplicate names/IDs, unrecognized names or cabinet types, and medium/low-confidence results are highlighted in the RMU Summary HTML report.",
    "将用户现有 RMU 台账与 G 文件识别结果进行对比。RMU 名称为必填匹配键；柜型、是否智能为可选字段。SMART 与 SMR 在对比时统一视为“智能环网柜”。原有 G 图形识别算法不因启用台账对比而改变。": "Compare an existing RMU ledger with G-file recognition results. RMU Name is the required match key; cabinet type and smart status are optional. SMART and SMR are treated as Smart RMU during comparison. Enabling ledger comparison does not change the G-file recognition algorithm.",
    "直接粘贴表格：\nRMU名称\tRMU类型\t是否智能\n30839\t2L1T\t是\n30864\t3L1T\t否\n\n或选择“只粘贴 RMU 名称”后每行一个名称。": "Paste a table directly:\nRMU Name\tRMU Type\tSmart\n30839\t2L1T\tYes\n30864\t3L1T\tNo\n\nOr select Paste RMU Names Only and enter one name per line.",
    "Excel/CSV 支持列：RMU名称（必填）、RMU类型（可选）、是否智能（可选）。没有表头时默认第1/2/3列分别作为名称/类型/智能。": "Excel/CSV columns: RMU Name (required), RMU Type (optional), Smart (optional). Without headers, columns 1/2/3 are treated as name/type/smart by default.",
    "框内位置": "Position in Frame",
    "扫描完成后会生成/覆盖 ID 扫描 CSV/HTML 报告，可点击“打开报告”查看；发现新元素类型仍会逐条询问是否加入模板。": "Scanning creates or replaces the ID scan CSV/HTML reports. Use Open Report to view them. New element types still require individual confirmation before being added to the template.",
    "执行后会按已确认模板修复 ID，并生成/覆盖 ID 修复 CSV/HTML 报告，可点击“打开报告”查看。": "Repairs IDs using confirmed templates and creates or replaces the ID repair CSV/HTML reports. Use Open Report to view them.",
    "“组合所有环网柜”会将每个直属 <rect> 作为环网柜外框，只组合完整位于矩形框内部的直属图元；任何部分位于框外的连接线、状态图标和文字都不会进入组合。“取消所有环网柜组合”会删除成员中含 <rect> 的 <Merge> 头元素，并把 rect 外框移动到柜内设备之前，使外框位于设备下层；坐标、ID、引用和业务属性不变，其他业务 Merge 不受影响。": "Group All RMUs treats each direct <rect> as an RMU frame and groups only direct elements fully inside it. Ungroup All RMUs removes RMU <Merge> headers containing a <rect> and moves the rect before the devices so the frame stays behind them. Coordinates, IDs, references, and business attributes are unchanged; other business Merge groups are preserved.",
    "保持文件现有 Merge 结构不变。": "Keep the existing Merge structure unchanged.",
    "单文件模式处理所选文件；目录模式处理第一层全部 G 文件。每个 rect 对应一个 Merge，只组合框内图元。": "Single-file mode processes the selected file; directory mode processes all first-level G files. Each rect maps to one Merge and only elements inside the frame are grouped.",
    "删除所有成员中包含 rect 的环网柜 Merge，保留全部成员，并把 rect 调整到柜内设备下层；不删除其他业务 Merge。": "Remove RMU Merge groups whose members include a rect, preserve all members, and move the rect behind cabinet devices. Other business Merge groups are not removed.",
    "只识别框内存在 ts=SMART 的 Text 的直属 rect，并修改该 rect 的静态边框色 lc 和 lcc；SMART 字体颜色以及不含 SMART 的其他环网柜外框均保持不变。": "Recognize only direct rect frames containing Text with ts=SMART and change only that rect's static border colors lc/lcc. SMART text color and other RMU frames remain unchanged.",
    "只处理带 BusDis 的环网柜中 devref 指向 channel_status 的 <Status> 红色状态点。仅移动该状态点本身，不移动环网柜、母线、设备、标题、连接线或其他图元。": "Process only red <Status> points whose devref references channel_status inside RMUs containing BusDis. Only the status point moves; the RMU, bus, devices, title, connection lines, and other elements remain unchanged.",
    "可选择矩形框内四个角或四条边的中点；默认左下角，与示意图中的目标位置一致。": "Choose any of the four corners or four edge midpoints inside the rectangular frame. The default is Bottom Left.",
    "状态点与所选矩形框边之间的内边距，默认 5 像素。": "Inner spacing between the status point and the selected frame edge. Default: 5 pixels.",
    "识别 rect 框内的 Bus，删除该 rect 及对应环网柜 Merge；寻找距离母线最近的业务标题 Text，移动到母线上方并水平居中。": "Recognize Bus elements inside the rect, remove the rect and corresponding RMU Merge, then move the nearest business-title Text above the bus and center it horizontally.",
    "直接解析 G 文件，不使用 OCR。只有 rect 框内同时存在 BusDis、CBreakerDis 和 ZhaiWaiJieDiDaoZha 才认定为环网柜；柜名只从勾选方向上的绿色 Text 中选择。柜型优先按 Y1/Y2/... 与 Q1/Q2/... 名称计数，名称无法判断时才回退到设备 devref。柜型始终输出如 2L1T、3L1T；SMART 单独识别成一列，不参与柜型字符串。": "Parse G files directly without OCR. A rect is recognized as an RMU only when BusDis, CBreakerDis, and ZhaiWaiJieDiDaoZha are all present inside it. RMU names are selected from green Text in the enabled directions. Cabinet type is determined from Y1/Y2/... and Q1/Q2/... names first, then falls back to device devref. CabinetType remains 2L1T, 3L1T, etc.; SMART is a separate column and is not part of the cabinet-type string.",
    "启用后在识别结果/CSV 的 SMART 列输出 1 或 0；CabinetType 始终只输出 2L1T、3L1T 等 L/T 柜型。": "When enabled, output 1 or 0 in the SMART column of recognition results/CSV. CabinetType remains an L/T type such as 2L1T or 3L1T.",
    "输出文件中删除全部 Layer 直属 Merge；原文件不修改。RMU 外框只调整 XML 前后顺序，不修改任何属性。": "Remove all direct Layer Merge elements from output files. Source files are unchanged. RMU frames are only reordered in XML; no attributes are modified.",
    "识别有效的水平 <Bus>，将上下平行且范围重叠的双母线视为一组；再依据 Text 的内容、字号和局部几何位置选择唯一可确认的馈线名称，移动到最上方母线的正上方并水平居中。识别不使用 key_name 或 keyid；无法唯一判断时跳过。该操作只修改目标 Text 的 x、y，不修改文字内容、字体、颜色、母线、设备、连接线、ID 或模型关联属性。": "Recognize valid horizontal <Bus> elements and treat parallel overlapping double buses as one group. Select a uniquely identifiable feeder-name Text using content, font size, and local geometry, then move it directly above the top bus and center it horizontally. Recognition does not use key_name or keyid; ambiguous cases are skipped. Only the target Text x/y coordinates are changed.",
    "勾选后随‘开始基础处理’执行；不勾选时完全跳过。纯数字、设备标签和说明文字不会移动。": "Runs with Start Basic Processing when checked; otherwise it is skipped. Pure numbers, device labels, and explanatory text are not moved.",
    "用于将仍使用旧图元几何参数的主 G 文件适配到新图元库。请分别添加本次涉及的旧图元 G 和新图元 G，程序按完全相同的文件名强制一一配对，并直接从图元文件读取 w/h、AlignCenter 和 pin(cx,cy)。任何图元只存在旧版或只存在新版、主体类型/ID 不一致、端口数量变化时都会禁止执行。处理时保持旧电气对齐中心的绝对位置不变，并把对应连接线端点移动到新图元真实 pin；不需要正常参考主 G。": "Adapt main G files using old symbol geometry to a new symbol library. Add the required old and new symbol G files; matching is strictly one-to-one by identical file name, and w/h, AlignCenter, and pin(cx,cy) are read directly from the symbol files. Processing is blocked for missing pairs, mismatched body type/ID, or changed port counts. The old electrical alignment center remains fixed and connection-line endpoints are moved to the new real pins.",
    "只处理主 G 中 devref 命中已配对图元、且当前 w/h 与旧图元尺寸完全一致的实例；已经是新尺寸的实例会跳过，未知自定义尺寸会告警并跳过。": "Process only main-G instances whose devref matches a paired symbol and whose current w/h exactly matches the old symbol size. Instances already using the new size are skipped; unknown custom sizes are warned and skipped.",
    "用于修复图形中未对齐、缺失或不完整的绿色连接点。程序采用保守增量模式：原有连接和端口编号一律保留；仅对已验证的半像素设备沿 X 方向吸附到整数网格，不修改任何连接线坐标；随后只补齐缺失的 node_area 和 link。无法唯一判断时跳过，不会修改设备 Y、ID、文字、颜色、图标、Merge、画布或其他业务属性。": "Repair misaligned, missing, or incomplete green connection points using a conservative incremental approach. Existing connections and port numbers are preserved. Only verified half-pixel devices are snapped to the integer X grid; connection-line coordinates are not changed. Missing node_area/link references are then completed. Ambiguous cases are skipped.",
    "勾选后随“开始基础处理”执行保守连接修复；不勾选时完全跳过。原有连接不会被删除或改号。": "Run conservative connection repair with Start Basic Processing when checked; otherwise skip it completely. Existing connections are never deleted or renumbered.",
    "请先在 SSH 文件列表中选择一个或多个 G 文件": "Select one or more G files in the SSH file list first.",
    "正在只读下载所选服务器 G 文件到 workspace，并扫描元素与属性……": "Downloading the selected server G files to the workspace in read-only mode and scanning elements and attributes…",
    "留空时取输入文件名，例如 JED-CTL-ADF": "Leave blank to use the input file name, for example JED-CTL-ADF.",
    "选择随 App 一起发布的内置图框模板。": "Select a built-in drawing-frame template distributed with the app.",
    "把当前内置模板复制到外部文件，便于查看或修改。": "Copy the current built-in template to an external file for review or modification.",
    "内置模板：会按四边距调整外框，并允许修改左上标题和 Draw/Approve/Issue 信息。": "Built-in template: adjusts the frame by the configured margins and allows editing the upper-left title and Draw/Approve/Issue information.",
    "客户模板：会按四边距调整外框和锚定组件位置，但不会修改任何文字、姓名、日期、字体、颜色或表格内容。": "Customer template: adjusts the frame and anchored component positions by the configured margins without changing text, names, dates, fonts, colors, or table content.",
    "尚未添加图元。旧、新图元必须按相同文件名一一对应。": "No symbols have been added. Old and new symbols must match one-to-one by identical file name.",
    "扫描输入文件或目录内 G 文件的直属 Layer 直接子元素，生成元素标签和属性名下拉选项。": "Scan direct children of the Layer in the input G file(s) and build element-tag and attribute-name drop-down lists.",
    "请选择输入文件或目录后扫描元素与属性": "Select an input file or directory, then scan elements and attributes.",
    "请输入需要匹配的旧值": "Enter the old value to match.",
    "请输入替换后的新值": "Enter the replacement value.",
    "请输入需要精确匹配的属性值": "Enter the attribute value to match exactly.",
    "元素标签": "Element Tag",
    "从输入 G 文件的直属 Layer 直接子元素中选择，也可手动输入。": "Select from direct child elements of the Layer in the input G file, or enter a value manually.",
    "从输入 G 文件直属 Layer 的直接子元素中选择，也可手动输入。": "Select from direct child elements of the Layer in the input G file, or enter a value manually.",
    "根据所选元素标签列出实际出现的属性名，也可手动输入。": "List attribute names that actually occur for the selected element tag, or enter one manually.",
    "只有属性值与旧值完全相同时才替换。": "Replace only when the attribute value exactly matches the old value.",
    "匹配成功后写入的新属性值。": "New attribute value written after a successful match.",
    "匹配元素上存在该属性时，直接删除这个属性键。": "Delete this attribute key when it exists on a matching element.",
    "只有属性值与此内容完全一致时才删除整个元素。": "Delete the entire element only when the attribute value exactly matches this content.",
    "输入路径不存在或没有 G 文件，暂时无法生成元素和属性选项": "The input path does not exist or contains no G files, so element and attribute options cannot be generated.",
    "未扫描到直属 Layer 的直接子元素；仍可手动输入标签和属性名": "No direct child elements were found in Layer. Element tags and attribute names can still be entered manually.",
    "按照当前页面参数开始处理。处理会在后台线程中运行。": "Start processing with the current page settings. The task runs in a background thread.",
    "打开本次任务对应的 workspace 运行目录。运行记录仅保留 30 天。": "Open the workspace run directory for this task. Run records are retained for 30 days.",
    "清空当前页面的执行日志，不会删除任何文件。": "Clear the execution log on this page without deleting any files.",
    "显示当前处理任务的总体进度。": "Show overall progress for the current task.",
    "<p>点击“开始执行”后，任务会在后台运行。进度条显示总体进度，详细处理过程显示在日志区域。处理失败时请复制日志中的错误信息进行排查。</p>": "<p>After you click Run, the task runs in the background. The progress bar shows overall progress and the log area shows details. If processing fails, copy the error information from the log for troubleshooting.</p>",
    "默认使用当前日期；点击右侧日历按钮可选择其他日期。": "Use the current date by default. Click the calendar button on the right to choose another date.",
    "输入文件名关键字进行模糊查询；多个关键字用空格分隔，文件名需同时包含这些关键字。只有无图框文件和 G File Studio 内置图框文件可选择；内置图框会在合并前自动移除。": "Use file-name keywords for fuzzy search. Separate multiple keywords with spaces; a file name must contain all keywords. Only files without frames and files with a G File Studio built-in frame can be selected; built-in frames are removed before merging.",
    "例如：AJWD 48；留空显示全部文件": "Example: AJWD 48; leave blank to show all files.",
    "不区分大小写；多个空格分隔关键字采用同时包含的匹配方式。": "Case-insensitive. Space-separated keywords use an AND match.",
    "取消当前选择": "Clear Current Selection",
    "确认导入": "Import Selected",
    "先点击“加载 / 检查”扫描目录。加载时会显示进度并检查图框：内置图框可参与合并，合并前会自动移除；客户或未知图框禁止参与。随后可通过“查询并导入”按文件名模糊查询、选择或全选并导入列表，再执行删除、置顶、上移、下移和置底。": "Click Load / Check to scan the directory. Progress and frame checks are shown while loading. Built-in frames may participate and are removed before merging; customer or unknown frames are blocked. Then use Search & Import to fuzzy-search by file name, select matching files, and import them into the merge list before reordering as needed.",
    "尚未加载输入目录。": "Input directory has not been loaded yet.",
    "显示加载进度，重新扫描目录并检查 XML、对齐基准和图框类型。": "Show loading progress, rescan the directory, and check XML, alignment references, and frame types.",
    "打开模糊查询窗口，输入文件名关键字，选择或全选匹配文件后导入当前列表。": "Open the fuzzy-search dialog, enter file-name keywords, select matching files, and import them into the current list.",
    "把目录中全部可参与合并的文件按自然文件名顺序导入；非内置图框和检查失败文件不会导入。": "Import every merge-eligible file in natural file-name order. Files with non-built-in frames or failed checks are not imported.",
    "从本次合并列表移除所选文件。支持 Ctrl/Shift 多选；不会删除磁盘源文件。": "Remove selected files from the current merge list. Ctrl/Shift multi-selection is supported; source files on disk are not deleted.",
    "把当前选中的一行移动到第一位，并作为合并基准文件。": "Move the selected row to the first position and use it as the merge reference file.",
    "把当前选中的一行向前移动一位。": "Move the selected row up one position.",
    "把当前选中的一行向后移动一位。": "Move the selected row down one position.",
    "把当前选中的一行移动到最后一位。": "Move the selected row to the last position.",
    "该文件已经在合并顺序列表中。": "This file is already in the merge-order list.",
    "保持原样：不修改 ls；实线：ls=1；虚线：ls=2。线型设置与颜色复选框彼此独立。": "Keep Original: do not change ls; Solid: ls=1; Dashed: ls=2. Line-style settings are independent of the color checkbox.",
    "清空全部": "Clear All",
})

# Runtime log fragments are translated conservatively. The replacements deliberately
# avoid XML identifiers and file paths.

# v2.18.3: complete English payloads for the small-element page and SSH source.
EN.update({
    "扫描 ConnectLine、FeedLine、Bus、BusDis 中疑似误画后残留的异常短线/小尺寸图元，并按用户选择删除。": "Scan ConnectLine, FeedLine, Bus, and BusDis for suspicious short/small residual elements and delete only the items selected by the user.",
    "该模块独立检查 ConnectLine、FeedLine、Bus、BusDis，不区分母线方向。默认判定为 w<10 且 h<10。扫描结果采用表格方式显示，可直接选择单个单元格或一块区域并按 Ctrl+C 复制。需要处理的图元请在首列勾选，支持单选、多选和全选。执行选中处理时会输出修改后的 G 文件，并生成带时间戳的 CSV/HTML 报告；若勾选项存在非空 keyid，会先明确提示后再确认。": "This module independently checks ConnectLine, FeedLine, Bus, and BusDis without restricting bus orientation. The default condition is w<10 and h<10. Results are shown in a table; individual cells or ranges can be selected and copied with Ctrl+C. Use the first-column checkboxes to choose elements for processing, with single, multiple, and select-all support. Processing writes a modified G file and timestamped CSV/HTML reports. If a selected item has a non-empty keyid, an explicit confirmation is required first.",
    "扫描文件与输出": "Scan Files & Output",
    "选择异常小尺寸图元报告/处理输出目录": "Select Abnormal Small Element Report/Processing Output Directory",
    "检测规则": "Detection Rule",
    "当目标元素的 w 和 h 同时小于该值时，报告为异常小尺寸图元。": "Report an element as abnormally small when both its w and h are below this value.",
    "异常图元结果": "Abnormal Element Results",
    "尚未扫描。": "Not scanned yet.",
    "处理": "Process",
    "文件": "File",
    "元素类型": "Element Type",
    "全选处理": "Select All for Processing",
    "可单独选择 XML ID 或任意单元格/区域，按 Ctrl+C 复制": "Select an XML ID or any cell/range and press Ctrl+C to copy.",
    "扫描异常图元": "Scan Abnormal Elements",
    "扫描完成后会生成/覆盖本模块的扫描 CSV/HTML 报告，可点击“打开报告”查看。": "After scanning, this module creates or replaces its scan CSV/HTML reports. Click Open Report to view them.",
    "首列勾选决定哪些图元参与处理；其余单元格可像表格一样单选/框选，按 Ctrl+C 复制。": "The first-column checkboxes determine which elements are processed. Other cells can be selected individually or as a range and copied with Ctrl+C.",
    "删除选中异常图元": "Delete Selected Abnormal Elements",
    "删除结果表中已勾选的异常小尺寸图元，生成修改后的 G 文件，并生成/覆盖处理 CSV/HTML 报告；报告会列出实际删除项。": "Delete the checked abnormal small elements, create the modified G file, and create or replace the processing CSV/HTML reports. The report lists the items actually deleted.",
    "打开报告": "Open Report",
    "IP / 主机": "IP / Host",
    "端口": "Port",
    "用户名": "Username",
    "密码": "Password",
    "远程目录": "Remote Directory",
    "测试 SSH 连接": "Test SSH Connection",
    "刷新 G 文件列表": "Refresh G File List",
    "保存 SSH 设置": "Save SSH Settings",
    "下载所选到本地…": "Download Selected Locally…",
    "尚未测试 SSH/SFTP 连接。": "SSH/SFTP connection has not been tested yet.",
    "SSH 服务器严格只读：仅列目录、读取文件属性和下载 G 文件；G File Studio 不提供上传、覆盖、重命名、删除或修改服务器文件的接口。": "The SSH server is strictly read-only: only directory listing, file metadata reading, and G-file download are allowed. G File Studio provides no upload, overwrite, rename, delete, or server-side modification operation.",
    "搜索 G 文件": "Search G Files",
    "例如：ABH-06、JED-NTH、B412": "Example: ABH-06, JED-NTH, B412",
    "尚未加载远程文件": "Remote files not loaded",
    "全选当前结果": "Select All Results",
    "取消当前结果": "Clear Current Results",
    "清空全部选择": "Clear All Selections",
    "大小": "Size",
    "服务器修改时间": "Server Modified Time",
})

RUNTIME_REPLACEMENTS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        {
            "任务已启动……": "Task started…",
            "SSH/SFTP 连接正常；远程文件源只读。已加载 ": "SSH/SFTP connected successfully. Remote access is read-only. Loaded ",
            "SSH/SFTP 连接正常：": "SSH/SFTP connected successfully to ",
            "；远程文件源为只读。": ". Remote access is read-only.",
            " 个 .g 文件。": " .g files.",
            "SSH 设置已保存；所有使用 SSH 文件源的模块将复用这组最后输入。": "SSH settings saved. All modules using the SSH file source will reuse these latest values.",
            "保存 SSH 设置失败": "Failed to Save SSH Settings",
            "SSH 端口必须是整数。": "SSH port must be an integer.",
            "SSH 连接失败": "SSH Connection Failed",
            "远程文件列表加载失败": "Failed to Load Remote File List",
            "[SSH只读] 将 ": "[SSH read-only] Downloading ",
            " 个服务器 G 文件下载为本地处理快照：": " server G files as local processing snapshots: ",
            "[SSH只读] 后续扫描/处理仅使用 workspace 本地快照，不会修改服务器文件。": "[SSH read-only] Subsequent scanning/processing uses only local workspace snapshots and never modifies server files.",
            "SSH 处理快照目录必须位于本地 workspace 中：": "The SSH processing snapshot directory must be inside the local workspace: ",
            "请先在 SSH G 文件列表中选择一个或多个文件。": "Select one or more files in the SSH G-file list first.",
            "请选择文件": "Select Files",
            "选择本地下载目录": "Select Local Download Directory",
            "下载完成": "Download Completed",
            "已下载 ": "Downloaded ",
            " 个 G 文件到：": " G files to: ",
            "总数 ": "Total ",
            " | 当前显示 ": " | Visible ",
            " | 已选择 ": " | Selected ",
            "开始扫描异常小尺寸图元，共 ": "Starting abnormal small-element scan: ",
            "扫描结果保持 ": "Scan results remain at ",
            " 个异常图元不变；本次从原始 G 重新生成并删除 ": " abnormal elements; this run regenerated output from the original G file and deleted ",
            " 个，未处理 ": ", not processed ",
            " 个；输出 G 文件 ": "; output G files: ",
            " 个。处理报告包含全部 ": ". The processing report contains all ",
            " 个原始异常图元：": " original abnormal elements: ",
            "已从原始 G 重新生成输出，并删除本次勾选的 ": "Regenerated output from the original G file and deleted the ",
            " 个异常图元；输出 ": " selected abnormal elements; output ",
            "当前扫描结果仍保留原始文件中的 ": "The current scan results still retain ",
            "再次执行时会重新读取原始 G，并按当次勾选覆盖输出文件和处理报告。": "Each run rereads the original G file and replaces output files and processing reports according to the current selection.",
            "原文件未修改；可点击“打开报告”查看本次处理报告。": "Source files are unchanged. Click Open Report to view this processing report.",
            "删除选中异常图元（": "Delete Selected Abnormal Elements (",
            "确认删除当前勾选的 ": "Confirm deletion of the currently selected ",
            " 个异常小尺寸图元吗？": " abnormal small elements?",
            "程序会生成修改后的 G 文件以及本次 CSV/HTML 报告，原文件不会覆盖。": "The application will generate modified G files and CSV/HTML reports for this run. Source files will not be overwritten.",
            "本次勾选 ": "Selected this run: ",
            " 个异常图元，其中 ": " abnormal elements, including ",
            " 个存在非空 keyid。": " with a non-empty keyid.",
            "执行后这些图元会从输出 G 文件中删除。是否继续？": "These elements will be deleted from the output G files. Continue?",
            "其余 ": "remaining ",
            " 项省略": " items omitted",
            "设置母线分组（": "Configure Bus Groups (",
            "当前母线类型：": "Current bus type: ",
            "双母线": "Double Bus",
            "单母线": "Single Bus",
            "未设置任何组；所有馈线母线保持独立。": "No bus groups are configured; all feeder buses remain independent.",
            "母线组 ": "Bus group ",
            " 至少需要 2 个馈线文件。": " requires at least 2 feeder files.",
            " 包含已不在当前合并列表中的文件，请重新设置分组。": " contains files no longer in the current merge list. Reconfigure the group.",
            " 中存在已经属于其他母线组的文件。": " contains a file that already belongs to another bus group.",
            " 的馈线必须在当前合并顺序中连续。": " must contain consecutive feeders in the current merge order.",
            "已立即删除 ID 规则 ": "ID rule deleted immediately: ",
            "开始扫描当前 G，共 ": "Starting current-G scan: ",
            "模板覆盖检查：当前 G 共发现 ": "Template coverage check: current G contains ",
            " 类带 ID 元素；模板已覆盖 ": " ID-bearing element types; templates cover ",
            " 类，未覆盖 ": " types; uncovered: ",
            " 已存在，请使用“编辑规则”。": " already exists. Use Edit Rule.",
            "确认删除 ID 规则 ": "Confirm deletion of ID rule ",
            "删除后立即生效；再次扫描到对应元素类型时会重新提醒是否添加。": "Deletion takes effect immediately. If the element type is found again, you will be prompted to add the rule again.",
            "当前 G 中有 ": "The current G file has ",
            " 个元素类型尚未被 ID 模板覆盖，但已能从现有 ID 自动识别候选前缀和总位数。": " element types not yet covered by ID templates, but candidate prefixes and total lengths can be inferred from existing IDs.",
            "是否现在逐个确认并加入模板？": "Confirm and add them to the template now?",
            "确认扫描发现的 ID 规则：": "Confirm the ID rule discovered by scanning: ",
            " 已扫描：": " scanned: ",
            " 当前最大 ": " current maximum ",
            "，下一个 ": ", next ",
            "模板要求前缀 ": "template requires prefix ",
            "、总位数 ": ", total length ",
            "不符合模板的完整 ID": "complete IDs that do not match the template",
            "本次未加入。": " not added in this run.",
            "尚未加入模板；候选前缀 ": "Not yet in template; candidate prefix ",
            "（需人工确认）": " (manual confirmation required)",
            "（必须人工确认）": " (manual confirmation required)",
            "扫描发现，待人工确认": "discovered by scan; pending manual confirmation",
            "已选择 ": "Selected ",
            " 个服务器 G 文件；点击“扫描元素与属性”后将只读下载到 workspace 并生成下拉选项": " server G files. Click Scan Elements & Attributes to download read-only snapshots to the workspace and build the drop-down options.",
            "扫描元素与属性失败：": "Element/attribute scan failed: ",
            "检测到 ": "Detected ",
            " 个同名输出文件。": " output files with duplicate names.",
            "其余 ": "remaining ",
            " 个同名文件": " duplicate-name files",
            "图形边距调整会保持源文件名不变。请选择本次处理方式。": "Drawing-margin adjustment keeps source file names unchanged. Select how to handle this run.",
            "图形边距调整现在保持源文件名不变。": "Drawing-margin adjustment now keeps the source file name unchanged.",
            "源文件：": "Source file: ",
            "目标文件：": "Target file: ",
            "为避免覆盖原始 G 文件，请选择其他输出目录。": "Choose another output directory to avoid overwriting the source G file.",
            "图框添加会保持源文件名不变。请选择本次处理方式。": "Drawing-frame processing keeps source file names unchanged. Select how to handle this run.",
            "图框添加现在保持源文件名不变。": "Drawing-frame processing now keeps the source file name unchanged.",
            "内置模板已导出到：": "Built-in template exported to: ",
            "上次导出模板使用的目录已经不存在：": "The directory used for the previous template export no longer exists: ",
            "请重新选择模板，或恢复使用程序内置模板。": "Select a template again or restore the built-in application template.",
            "图框模板不存在：": "Drawing-frame template does not exist: ",
            "请重新选择。": "Please select again.",
            "已添加 ": "Added ",
            " 种图元；完整配对 ": " symbol types; complete pairs ",
            " 种，缺失配对 ": "; missing pairs ",
            "图元配对检查通过，共 ": "Symbol-pair validation passed. Total: ",
            "查看“": "View ",
            "”说明": " help",
            "已扫描 ": "Scanned ",
            " 个文件、": " files, ",
            " 个直属图元、": " direct elements, ",
            " 种元素标签": " element tags",
            "启用或关闭规则：": "Enable or disable rule: ",
            "上次使用的": "The previously used ",
            "已经不存在：": " no longer exists: ",
            "该路径已从配置中清除，请重新选择。": "The path was removed from settings. Select it again.",
            "所在目录已经不存在：": " directory no longer exists: ",
            " 姓名": " Name",
            "填写 ": "Enter ",
            " 日期默认是当前日期；点击日历按钮可修改。": " date defaults to today; click the calendar button to change it.",
            "当前匹配 ": "Current matches: ",
            " 个，其中 ": ", including ",
            " 个可导入。": " importable.",
            "确定从本次合并列表移除所选的 ": "Remove the selected ",
            " 个文件吗？": " files from the current merge list?",
            "此操作不会删除磁盘上的源文件。可再次通过“查询并导入”加入。": "This does not delete source files on disk. They can be added again through Search & Import.",
            "已加载 ": "Loaded ",
            " 个文件：可参与 ": " files: eligible ",
            " 个（其中内置图框 ": " (built-in frames ",
            " 个，合并时自动移除）；非内置图框禁止参与 ": ", removed automatically during merge); non-built-in frames blocked ",
            " 个；检查失败 ": "; failed checks ",
            " 个。当前已导入合并列表 ": ". Currently imported into merge list: ",
            "正在加载并检查 G 文件……": "Loading and checking G files…",
            "勾选后修改 Layer 直属 <": "When checked, change the static line colors lc/lcc of direct Layer <",
            "> 的静态线色 lc/lcc；未勾选时保持原颜色。": "> elements; when unchecked, keep the original color.",
            "输入目录不存在：": "Input directory does not exist: ",
            "输入文件不存在：": "Input file does not exist: ",
            "输入文件必须以 ": "Input file must end with ",
            "输入目录中没有以 ": "No files ending with ",
            " 结尾的文件：": " were found in the input directory: ",
            "使用用户指定输出文件名：": "Using user-specified output file name: ",
            "未填写输出文件名，自动生成：": "No output file name specified; generated automatically: ",
            "输出文件已存在且不允许覆盖：": "Output file already exists and overwrite is not allowed: ",
            "模板文件不存在：": "Template file does not exist: ",
            "图框添加保持源文件名不变，禁止覆盖原始 G 文件：": "Drawing-frame processing preserves the source file name and cannot overwrite the original G file: ",
            "请更换输出目录。": "Change the output directory.",
            "[跳过] 输出目录已存在同名文件：": "[Skipped] A file with the same name already exists in the output directory: ",
            "[基础处理汇总]": "[Basic Processing Summary]",
            "[基础处理失败]": "[Basic Processing Failed]",
            "[环网柜识别]": "[RMU Recognition]",
            "[环网柜识别告警]": "[RMU Recognition Warning]",
            "[环网柜组合]": "[RMU Grouping]",
            "[环网柜组合告警]": "[RMU Grouping Warning]",
            "[取消环网柜组合]": "[Ungroup RMUs]",
            "[取消环网柜组合告警]": "[Ungroup RMU Warning]",
            "[图元版本升级]": "[Symbol Version Upgrade]",
            "[图元版本升级告警]": "[Symbol Version Upgrade Warning]",
            "[通用图元升级]": "[Universal Symbol Upgrade]",
            "[通用图元升级告警]": "[Universal Symbol Upgrade Warning]",
            "[同类图元版本升级]": "[Same-Class Symbol Version Upgrade]",
            "[同类图元版本升级告警]": "[Same-Class Symbol Version Upgrade Warning]",
            "[图形组合清理]": "[Graphic Group Cleanup]",
            "[馈线名称定位]": "[Feeder Name Positioning]",
            "[馈线名称定位告警]": "[Feeder Name Positioning Warning]",
            "[线路与母线样式/颜色处理]": "[Line & Bus Style/Color]",
            "[连接点修复]": "[Connection Repair]",
            "[连接点修复告警]": "[Connection Repair Warning]",
            "[连接点修复失败]": "[Connection Repair Failed]",
            "[连接点修复汇总]": "[Connection Repair Summary]",
            "[SMART环网柜外框颜色]": "[SMART RMU Frame Color]",
            "[SMR环网柜外框颜色]": "[SMR RMU Frame Color]",
            "[RMU柜名白色]": "[RMU Name White]",
            "[RMU柜名白色告警]": "[RMU Name White Warning]",
            "[环网柜红色状态点]": "[RMU Red Status Point]",
            "[Bus环网柜处理]": "[Bus RMU Processing]",
            "[环网柜增强告警]": "[RMU Enhancement Warning]",
            "[ID 模板]": "[ID Template]",
            "[ID 检查]": "[ID Check]",
            "[ID 格式变化]": "[ID Format Change]",
            "[重复 ID]": "[Duplicate ID]",
            "[ID 强制修复]": "[ID Force Repair]",
            "[ID 模板修复]": "[ID Template Repair]",
            "[ID 处理失败]": "[ID Processing Failed]",
            "[ID 报告]": "[ID Report]",
            "[输出策略]": "[Output Policy]",
            "[RMU台账]": "[RMU Ledger]",
            "[RMU台账对比]": "[RMU Ledger Comparison]",
            "[环网柜图元处理报告]": "[RMU Graphic Processing Report]",
            "[RMU信息汇总报告]": "[RMU Summary Report]",
            "[SMR环网柜报告]": "[SMR RMU Report]",
            "全局强制约束已关闭，保留已有格式不符 ID；新生成 ID 仍由各业务模块按已确认模板分配。": "Global enforcement is disabled. Existing malformed IDs are preserved; new IDs are still allocated by business modules using confirmed templates.",
            "按已确认规则强制规范 ID ": "Force-normalized IDs using confirmed rules: ",
            "所有已配置类型 ID 均符合模板。": "All configured ID types comply with their templates.",
            "未发现重复 ID。": "No duplicate IDs found.",
            "无法取得稳定的服务器文件版本：": "Unable to obtain a stable server-file version: ",
            "请稍后重试。": "Try again later.",
            "XML 解析失败：": "XML parse failed: ",
            "文件 ": "File ",
            " 的 G 根节点下没有直属 Layer。": " has no direct Layer under the G root.",
            "颜色必须是 #RRGGBB 格式：": "Color must use #RRGGBB format: ",
            "不支持的线型：": "Unsupported line style: ",
            "不支持的旋转角度：": "Unsupported rotation angle: ",
            "根节点不是 G": "root node is not G",
            "没有直属 Layer": "has no direct Layer",
            "缺少有效": "missing valid ",
            "无法解析": "cannot parse",
            "已跳过": "skipped",
            "已回滚": "rolled back",
            "保留原位置": "original position preserved",
            "不一致": "mismatch",
            "未识别": "unrecognized",
            "待确认": "pending confirmation",
            "高置信度": "high confidence",
            "中等": "medium",
            "低置信度": "low confidence",
            "重复": "duplicate",
            "柜型": "cabinet type",
            "柜名": "RMU name",
            "智能": "smart",
            "普通": "normal",
            "外框": "frame",
            "状态点": "status point",
            "连接线": "connection line",
            "连接点": "connection point",
            "属性": "attribute",
            "引用": "reference",
            "成员": "member",
            "候选": "candidate",
            "成功": "succeeded",
            "失败": "failed",
            "找到": "found",
            "移动": "moved",
            "删除": "deleted",
            "修改": "modified",
            "新增": "added",
            "跳过": "skipped",
            "输入目录": "input directory",
            "输出目录": "output directory",
            "源文件": "source file",
            "目标文件": "target file",
            "生成时间": "generated at",
            "记录数": "records",
            "阈值": "threshold",
            "异常数量": "abnormal count",
            "带 keyid": "with keyid",
            "开始扫描异常小尺寸图元，共 ": "Starting abnormal small-element scan: ",
            " 个文件；阈值：": " files; threshold: ",
            "正在扫描异常短线图元……": "Scanning abnormal small elements…",
            "正在扫描：": "Scanning: ",
            "扫描已取消。": "Scan cancelled.",
            "：发现 ": ": found ",
            " 个异常图元。": " abnormal elements.",
            "扫描失败：": "Scan failed: ",
            "扫描完成：发现 ": "Scan completed: found ",
            " 个异常图元，其中 ": " abnormal elements, including ",
            " 个存在 keyid。": " with non-empty keyid.",
            "扫描完成：": "Scan completed: ",
            "报告：": "Reports: ",
            "CSV 报告：": "CSV report: ",
            "HTML 报告：": "HTML report: ",
            "[异常]": "[Abnormal]",
            "[已处理]": "[Processed]",
            "(空)": "(empty)",
            "执行处理失败：": "Processing failed: ",
            "输出 G：": "Output G: ",
            "本次独立处理：从原始 G 重新生成输出，删除 ": "Independent run: regenerated output from the original G file and deleted ",
            "扫描结果仍保留 ": "The scan results still retain ",
            " 个，不累计上一次处理状态。": " items; previous processing state is not accumulated.",
            "从原始 G 重新生成并删除 ": "regenerated from the original G file and deleted ",
            "未处理 ": "not processed ",
            "输出 G 文件 ": "output G files ",
            "处理报告包含全部 ": "The processing report contains all ",
            " 个原始异常图元": " original abnormal elements",
            "总数 ": "Total ",
            "当前显示 ": "Visible ",
            "已选择 ": "Selected ",
            "SSH 设置已保存；所有使用 SSH 文件源的模块将复用这组最后输入。": "SSH settings saved. All modules using the SSH file source will reuse these latest values.",
            "SSH/SFTP 连接失败：": "SSH/SFTP connection failed: ",
            "读取远程 G 文件列表失败：": "Failed to load remote G-file list: ",
            "请先选择一个或多个要下载到本地的 G 文件。": "Select one or more G files to download locally first.",
            "下载失败": "Download failed",
            "下载失败：": "Download failed: ",
            "发现": "found",
            "其中": "including",
            "存在": "with",
            "异常": "abnormal",
            "报告": "report",
            "已处理": "processed",
            "未处理": "not processed",
            "勾选": "selected",
            "原始": "original",
            "重新生成": "regenerated",
            "处理完成。": "Processing completed.",
            "处理失败：": "Processing failed:",
            "告警：": "Warnings:",
            "统计：": "Statistics:",
            "输出：": "Output:",
            "输入方式": "Input mode",
            "输入": "Input",
            "输出目录": "Output directory",
            "输出文件": "Output file",
            "成功": "Succeeded",
            "失败": "Failed",
            "文件": "file",
            "个文件": " files",
            "处理": "Processing",
            "扫描": "Scan",
            "完成": "completed",
            "远程": "remote",
            "只读": "read-only",
            "已确认": "Confirmed",
            "待人工确认": "Pending manual confirmation",
            "用户确认": "User confirmed",
            "扫描发现": "Detected by scan",
            "规则格式": "Rule format",
            "固定前缀": "fixed prefix",
            "总位数": "total length",
            "同类型": "same type",
            "最大": "maximum",
            "当前规则": "Current rule",
            "备注": "Notes",
            "页面帮助": "Page Help",
            "元素": "element",
            "类型": "type",
            "目录": "directory",
            "请选择": "Please select",
            "确认": "Confirm",
            "取消": "Cancel",
            "删除": "Delete",
            "修改": "Modify",
            "添加": "Add",
            "读取": "Read",
            "下载": "Download",
            "服务器": "server",
            "连接": "connection",
            "环网柜": "RMU",
            "馈线": "feeder",
            "母线": "bus",
            "图框": "drawing frame",
            "图元": "element",
            "名称": "name",
            "颜色": "color",
            "位置": "position",
            "规则": "rule",
            "模板": "template",
        }.items(),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)


def tr(text: str, language: str = LANG_ZH) -> str:
    if language != LANG_EN or not text:
        return text
    return EN.get(text, text)


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

def contains_cjk(text: str) -> bool:
    return bool(text and _CJK_RE.search(text))

def tr_runtime(text: str, language: str = LANG_ZH) -> str:
    if language != LANG_EN or not text:
        return text

    # Jeddah batch runtime messages are translated as complete structures so the
    # English path never changes the underlying site-specific processing data.
    match = re.fullmatch(r"\[吉达批处理\] 开始处理 (\d+) 个单馈线 G 文件。", text)
    if match:
        return f"[Jeddah Batch] Starting processing of {match.group(1)} single-feeder G files."
    if text == "[吉达批处理] 固定流程：彻底取消图形组合（删除全部 <Merge>，RMU 外框置底） → 删除异常小尺寸元素 → RMU 名称改白 → SMART/SMR 外框刷红 + 已有 SMART 柜图元检查（LBS / Circuit Breaker） + SMR 智能处理（已有 SMART 时删 SMR；否则生成 SMART） + SMR 转换后再次检查 SMART 图元 + 删除带 Bus 外框并上移标题 + 馈线名称上移 + 删除 H.T 文字 + 删除 RMU channel_status 红色状态点 + 清理 RMU 内重复 SMART + 删除相邻 2000.00 / UPDATED_MEASURMENT 字符对 → ID 检查与修复 → 图形边距调整 → 图框添加。":
        return "[Jeddah Batch] Fixed workflow: fully ungroup graphics (remove all <Merge> and send RMU frames to back) → remove abnormal small elements → set RMU names to white → set SMART/SMR frames to red + validate existing SMART RMU LBS/Circuit Breaker icons + conditional SMR handling + validate SMART RMU icons again after SMR conversion + remove Bus frames and move titles above buses + move feeder names above buses + remove exact H.T text markers + remove RMU channel_status red status points + remove duplicate SMART labels within each RMU + remove adjacent 2000.00 / UPDATED_MEASURMENT Text pairs → ID Check & Repair → Drawing Margin Adjustment → Drawing Frame."
    match = re.fullmatch(r"\[吉达批处理\] RMU 名称排除字符串：(.*)", text)
    if match:
        return f"[Jeddah Batch] RMU name exclusions: {match.group(1)}"
    match = re.fullmatch(r"\[吉达批处理/图形组合清理\] (.+)：原 Merge (\d+) 个，删除 (\d+) 个，剩余 (\d+) 个；识别 RMU 外框 (\d+) 个，置底 (\d+) 个。", text)
    if match:
        a = match.groups()
        return f"[Jeddah Batch/Graphic Group Cleanup] {a[0]}: original Merge {a[1]}, removed {a[2]}, remaining {a[3]}; recognized RMU frames {a[4]}, sent to back {a[5]}."
    match = re.fullmatch(r"\[吉达批处理\] 图形组合清理阶段完成：删除 Merge (\d+) 个，RMU 外框置底 (\d+) 个。", text)
    if match:
        return f"[Jeddah Batch] Graphic-group cleanup completed: Merge removed {match.group(1)}; RMU frames sent to back {match.group(2)}."
    match = re.fullmatch(r"\[吉达批处理/异常小元素\] (.+)：发现并删除 (\d+) 个，其中带 keyid (\d+) 个。", text)
    if match:
        return f"[Jeddah Batch/Abnormal Small Elements] {match.group(1)}: found and deleted {match.group(2)}; with keyid: {match.group(3)}."
    match = re.fullmatch(r"\[吉达批处理\] 异常元素阶段完成：删除 (\d+) 个，其中带 keyid (\d+) 个。", text)
    if match:
        return f"[Jeddah Batch] Abnormal-element stage completed: deleted {match.group(1)}; with keyid: {match.group(2)}."
    match = re.fullmatch(r"\[吉达批处理/RMU名称白色\] (.+)：识别柜名 (\d+) 个，匹配名称 Text (\d+) 个，改为白色 (\d+) 个。", text)
    if match:
        return f"[Jeddah Batch/RMU Name White] {match.group(1)}: recognized RMU names {match.group(2)}; matched name Text {match.group(3)}; changed to white {match.group(4)}."
    match = re.fullmatch(r"\[吉达批处理/图面处理\] (.+)：SMART 匹配 (\d+)、刷红 (\d+)；SMR Text (\d+)、匹配 (\d+)、刷红 (\d+)；已有 SMART 柜图元预检查：SMART 柜 (\d+)、校正 devref (\d+)；SMR→SMART 新生成 (\d+)；已有 SMART 清理 SMR (\d+)；删除 SMR Text (\d+)；SMR 转换阶段切 SMART 图元 (\d+)；SMR 后复检：SMART 柜 (\d+)、校正 devref (\d+)；删除带 Bus 外框 (\d+)、对应标题上移 (\d+)；馈线名称上移 (\d+)；删除 H.T 文字 (\d+)；删除 RMU 红色状态点 (\d+)/(\d+) 个；扫描 RMU (\d+) 个、重复 SMART 柜 (\d+) 个、删除重复 SMART (\d+) 个；删除相邻 2000\.00 \+ UPDATED_MEASURMENT (\d+) 对（(\d+) 个 Text）。", text)
    if match:
        a = match.groups()
        return (f"[Jeddah Batch/Visual Processing] {a[0]}: SMART matched {a[1]}, changed to red {a[2]}; "
                f"SMR Text {a[3]}, matched {a[4]}, changed to red {a[5]}; existing-SMART RMUs checked {a[6]}, device devrefs corrected {a[7]}; "
                f"new SMART labels created {a[8]}; existing-SMART SMR cleanup {a[9]}; SMR Text removed {a[10]}; "
                f"SMR conversion-stage device changes {a[11]}; post-SMR SMART RMUs checked {a[12]}, device devrefs corrected {a[13]}; "
                f"Bus frames removed {a[14]}, corresponding titles moved {a[15]}; feeder names moved {a[16]}; "
                f"H.T texts removed {a[17]}; RMU channel_status red points removed {a[18]}/{a[19]}; RMUs scanned for duplicate SMART {a[20]}, RMUs with duplicate SMART {a[21]}, duplicate SMART texts removed {a[22]}; "
                f"adjacent 2000.00 + UPDATED_MEASURMENT pairs removed {a[23]} ({a[24]} Text elements).")
    match = re.fullmatch(r"\[吉达批处理/图面处理失败\] (.+)", text)
    if match:
        return f"[Jeddah Batch/Visual Processing Failed] {match.group(1)}"
    match = re.fullmatch(r"\[吉达批处理/图形边距\] 完成 (\d+) 个 G 文件；左=(\d+)、上=(\d+)、右=(\d+)、下=(\d+)。", text)
    if match:
        a = match.groups()
        return f"[Jeddah Batch/Drawing Margin] Completed {a[0]} G files; left={a[1]}, top={a[2]}, right={a[3]}, bottom={a[4]}."
    match = re.fullmatch(r"\[吉达批处理/图框添加\] 完成 (\d+) 个 G 文件；模板=(.+)。", text)
    if match:
        return f"[Jeddah Batch/Drawing Frame] Completed {match.group(1)} G files; template={match.group(2)}."
    match = re.fullmatch(r"\[吉达批处理\] 完成：最终 G 文件 (\d+)/(\d+) 个；删除 Merge (\d+)；RMU 外框置底 (\d+)；异常元素删除 (\d+)；SMART 外框刷红 (\d+)；SMR 外框刷红 (\d+)；SMR 新生成 SMART (\d+)；已有 SMART 仅删 SMR (\d+)；删除 SMR Text (\d+)；已有 SMART 柜图元校正 (\d+)；SMR 转换阶段图元切换 (\d+)；SMR 后复检图元校正 (\d+)；RMU 名称改白 (\d+)；带 Bus 外框删除 (\d+)；对应标题上移 (\d+)；馈线名称上移 (\d+)；删除 H.T 文字 (\d+)；删除 RMU 红色状态点 (\d+)/(\d+) 个（扫描 BusDis RMU (\d+) 个）；扫描 RMU (\d+) 个、重复 SMART 柜 (\d+) 个、删除重复 SMART (\d+) 个；删除相邻测量字符对 (\d+) 对（(\d+) 个 Text）；ID 修复 (\d+)；边距调整 (\d+)；图框添加 (\d+)。", text)
    if match:
        a = match.groups()
        return (f"[Jeddah Batch] Completed: final G files {a[0]}/{a[1]}; Merge removed {a[2]}; RMU frames sent to back {a[3]}; "
                f"abnormal elements removed {a[4]}; SMART frames changed to red {a[5]}; SMR frames changed to red {a[6]}; new SMART labels created {a[7]}; "
                f"existing-SMART cabinets with SMR removed {a[8]}; SMR Text removed {a[9]}; existing-SMART device corrections {a[10]}; "
                f"SMR conversion-stage device changes {a[11]}; post-SMR SMART device corrections {a[12]}; RMU names changed to white {a[13]}; "
                f"Bus frames removed {a[14]}; corresponding titles moved {a[15]}; feeder names moved {a[16]}; "
                f"H.T texts removed {a[17]}; RMU channel_status red points removed {a[18]}/{a[19]} (BusDis RMUs scanned {a[20]}); RMUs scanned for duplicate SMART {a[21]}, RMUs with duplicate SMART {a[22]}, duplicate SMART texts removed {a[23]}; "
                f"adjacent measurement pairs removed {a[24]} ({a[25]} Text elements); IDs repaired {a[26]}; margins adjusted {a[27]}; frames added {a[28]}.")
    match = re.fullmatch(r"ID 检查发现 (\d+) 个元素类型尚未配置已确认模板；这些类型未擅自生成或改写 ID，请在 ID 检查与修复模块确认规则。", text)
    if match:
        return f"ID check found {match.group(1)} element types without confirmed templates. Their IDs were not generated or changed automatically; confirm the rules in ID Check & Repair."
    match = re.fullmatch(r"\[吉达批处理\] 最终输出目录：(.*)", text)
    if match:
        return f"[Jeddah Batch] Final output directory: {match.group(1)}"
    match = re.fullmatch(r"\[吉达批处理\] 汇总报告：(.*)", text)
    if match:
        return f"[Jeddah Batch] Summary report: {match.group(1)}"
    match = re.fullmatch(r"(.+): RMU (.+) 已识别，但未定位到可安全改色的同名 Text。", text)
    if match:
        return f"{match.group(1)}: RMU {match.group(2)} was recognized, but no exact matching Text could be safely located for color styling."

    # Dynamic merge-group strings are produced by the immutable Chinese feature code.
    # Translate their rendered form here instead of changing merge_page.py.
    group_cell = re.fullmatch(r"组(\d+)", text)
    if group_cell:
        return f"Group {group_cell.group(1)}"
    group_button = re.fullmatch(r"设置母线分组（(\d+)组）", text)
    if group_button:
        count = int(group_button.group(1))
        noun = "group" if count == 1 else "groups"
        return f"Set Bus Groups ({count} {noun})"
    group_summary = re.fullmatch(r"组(\d+): (.*?) ～ (.*?)（(\d+)个）", text)
    if group_summary:
        group_no, first_name, last_name, count_text = group_summary.groups()
        count = int(count_text)
        noun = "feeder" if count == 1 else "feeders"
        return f"Group {group_no}: {first_name} – {last_name} ({count} {noun})"

    exact = EN.get(text)
    if exact is not None:
        return exact

    translated = text

    # The confirmation dialog may contain one or more dynamic group-summary lines
    # inside a larger message, so translate those structures before generic phrase
    # replacement. This remains display-only; the underlying group lists are untouched.
    def replace_group_summary(match: re.Match[str]) -> str:
        group_no, first_name, last_name, count_text = match.groups()
        count = int(count_text)
        noun = "feeder" if count == 1 else "feeders"
        return f"Group {group_no}: {first_name} – {last_name} ({count} {noun})"

    translated = re.sub(
        r"组(\d+): ([^\n]*?) ～ ([^\n]*?)（(\d+)个）",
        replace_group_summary,
        translated,
    )
    translated = re.sub(r"设置母线分组（(\d+)组）", lambda m: f"Set Bus Groups ({m.group(1)} groups)", translated)
    translated = re.sub(r"(?<!母线)组(\d+)", lambda m: f"Group {m.group(1)}", translated)

    for source, target in RUNTIME_REPLACEMENTS:
        translated = translated.replace(source, target)
    # English mode must never leak Chinese UI text. Long-running business engines
    # still emit source-language diagnostics, so keep all already-translated technical
    # tokens/IDs/paths and remove only any residual CJK fragments as a last resort.
    # Legacy placeholder retained as a source marker for compatibility tests:
    # "Runtime message could not be fully translated."
    if contains_cjk(translated):
        translated = _CJK_RE.sub(" ", translated)
        translated = re.sub(r"[ \t]+", " ", translated)
        translated = re.sub(r" ?([，。；：]) ?", lambda m: {"，": ", ", "。": ". ", "；": "; ", "：": ": "}[m.group(1)], translated)
        translated = translated.strip()
        if not translated:
            return "Runtime message."
    return translated



def _language_manager_for_widget(widget: QWidget | None):
    """Find a LanguageManager on the widget, an ancestor, or the top-level window.

    The unified Jeddah DMM embeds GFileStudio pages instead of using the standalone
    GFileStudio MainWindow, so the language manager may live on the Graphics Workspace
    ancestor rather than the top-level application window.
    """
    current = widget
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        manager = getattr(current, "language_manager", None)
        if manager is not None:
            return manager
        current = current.parentWidget() if hasattr(current, "parentWidget") else None
    window = widget.window() if widget is not None else None
    return getattr(window, "language_manager", None)


def tr_for(widget: QWidget, text: str) -> str:
    """Translate dynamic user-facing text and remember its source form."""
    manager = _language_manager_for_widget(widget)
    if manager is None:
        return text
    translated = manager.runtime_text(text)
    manager.remember_runtime_translation(text, translated)
    return translated


_QMESSAGEBOX_ADD_BUTTON_ORIGINAL = None
_QMESSAGEBOX_CLICKED_BUTTON_ORIGINAL = None
_QMESSAGEBOX_BRIDGE_INSTALLED = False


def _manager_for_message_box(box: QMessageBox):
    """Resolve the active language manager without changing feature code/state."""
    return _language_manager_for_widget(box.parentWidget())


def _install_qmessagebox_button_i18n_bridge() -> None:
    """Translate QMessageBox captions without changing feature click semantics.

    The immutable v2.17.60 feeder-merge page stores the Python button objects returned
    by ``addButton()`` and later uses ``clickedButton()`` with ``is`` identity checks.
    On some PySide6 builds, an English custom caption can make ``clickedButton()``
    surface a different Python wrapper for the same underlying Qt button.  The Chinese
    path does not hit this wrapper mismatch.

    Keep feature code untouched: in English mode we translate only the caption passed
    to Qt, remember the *exact* Python object returned by ``addButton()``, and record
    that exact object when its ``clicked`` signal fires.  ``clickedButton()`` then
    returns the recorded object.  Button roles, dialog result codes, feature state, and
    every Chinese-mode call continues to use Qt's original implementation.
    """
    global _QMESSAGEBOX_ADD_BUTTON_ORIGINAL
    global _QMESSAGEBOX_CLICKED_BUTTON_ORIGINAL
    global _QMESSAGEBOX_BRIDGE_INSTALLED
    if _QMESSAGEBOX_BRIDGE_INSTALLED:
        return

    original_add_button = QMessageBox.addButton
    original_clicked_button = QMessageBox.clickedButton
    _QMESSAGEBOX_ADD_BUTTON_ORIGINAL = original_add_button
    _QMESSAGEBOX_CLICKED_BUTTON_ORIGINAL = original_clicked_button

    def _english_manager(box):
        manager = _manager_for_message_box(box)
        return manager if manager is not None and getattr(manager, "is_english", False) else None

    def translated_add_button(box, *args):
        manager = _english_manager(box)
        translated_args = args
        if manager is not None and args and isinstance(args[0], str):
            translated_args = (manager.runtime_text(args[0]), *args[1:])
            # The custom caption is final before Qt creates the button.  Show/Paint
            # translation must never rewrite modal button widgets afterwards.
            box.setProperty("_i18n_custom_buttons_pretranslated", True)

        button = original_add_button(box, *translated_args)

        if manager is not None and button is not None:
            # Preserve the exact Python wrapper returned to feature code.  This is
            # presentation-layer compatibility only; it does not choose a result.
            refs = getattr(box, "_i18n_exact_button_refs", None)
            if refs is None:
                refs = []
                setattr(box, "_i18n_exact_button_refs", refs)
            refs.append(button)

            def remember_clicked(_checked=False, *, _box=box, _button=button):
                setattr(_box, "_i18n_exact_clicked_button", _button)

            button.clicked.connect(remember_clicked)
        return button

    def exact_clicked_button(box):
        if _english_manager(box) is not None:
            exact = getattr(box, "_i18n_exact_clicked_button", None)
            if exact is not None:
                return exact
        return original_clicked_button(box)

    QMessageBox.addButton = translated_add_button
    QMessageBox.clickedButton = exact_clicked_button
    _QMESSAGEBOX_BRIDGE_INSTALLED = True


class LanguageManager(QObject):
    languageChanged = Signal(str)

    def __init__(self, settings: UserSettingsService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        _install_qmessagebox_button_i18n_bridge()
        self.settings = settings
        language = settings.get_value("general/language", LANG_ZH).strip()
        self._language = language if language in SUPPORTED_LANGUAGES else LANG_ZH
        self._runtime_reverse: dict[str, str] = {}
        self._event_translate_guard = False

    @property
    def language(self) -> str:
        return self._language

    @property
    def is_english(self) -> bool:
        return self._language == LANG_EN

    def text(self, source: str) -> str:
        return tr_runtime(source, self._language)

    def runtime_text(self, source: str) -> str:
        return tr_runtime(source, self._language)

    def remember_runtime_translation(self, source: str, translated: str) -> None:
        if source and translated and source != translated:
            self._runtime_reverse[str(translated)] = str(source)

    def set_language(self, language: str) -> None:
        language = language if language in SUPPORTED_LANGUAGES else LANG_ZH
        if language == self._language:
            return
        self._language = language
        self.settings.set_value("general/language", language)
        self.languageChanged.emit(language)

    def _source(self, obj: QObject, key: str, current: str) -> str:
        prop = f"_i18n_{key}"
        rendered_prop = f"_i18n_{key}_rendered"
        saved = obj.property(prop)
        if saved is None:
            obj.setProperty(prop, current)
            return current

        # If a control changed after the last translation pass, promote the new
        # dynamic value to the source text. tr_for() records English -> Chinese
        # pairs, so a dynamic English label can still switch back to Chinese.
        last_rendered = obj.property(rendered_prop)
        if current != str(saved) and (last_rendered is None or current != str(last_rendered)):
            recovered = self._runtime_reverse.get(current)
            if recovered is not None:
                obj.setProperty(prop, recovered)
                return recovered
            if contains_cjk(current):
                obj.setProperty(prop, current)
                return current
        return str(saved)

    def _translate_text_property(self, obj: QObject, key: str, getter, setter) -> None:
        current = getter()
        if not isinstance(current, str):
            return
        source = self._source(obj, key, current)
        if self.is_english:
            curated = obj.property(f"_i18n_{key}_en")
            rendered = str(curated) if curated is not None else self.text(source)
        else:
            rendered = source
        setter(rendered)
        obj.setProperty(f"_i18n_{key}_rendered", rendered)

    def _translate_table_item(self, table: QTableWidget, item: QTableWidgetItem) -> None:
        """Translate one table cell while tracking dynamic source-text updates.

        Feature code is allowed to keep setting its original Chinese display strings
        (for example ``组1`` / ``未分组``).  The i18n layer remembers both the
        canonical source and the last rendered value on the item itself, so later
        business-side ``setText()`` calls are detected as new source values rather
        than being overwritten by a stale translation cached at dialog creation.
        """
        if item is None:
            return
        source_role = 0x0100 + 481
        rendered_role = 0x0100 + 482
        current = item.text()
        saved = item.data(source_role)
        last_rendered = item.data(rendered_role)
        signals_were_blocked = table.signalsBlocked()
        table.blockSignals(True)
        try:
            if saved is None:
                source = current
                item.setData(source_role, source)
            else:
                source = str(saved)
                # A value different from both the remembered source and our own last
                # rendering came from feature code. Promote it to the new source text.
                if current != source and (last_rendered is None or current != str(last_rendered)):
                    recovered = self._runtime_reverse.get(current)
                    source = recovered if recovered is not None else current
                    item.setData(source_role, source)

            rendered = self.runtime_text(source) if self.is_english else source
            item.setData(rendered_role, rendered)
            if current != rendered:
                item.setText(rendered)
        finally:
            table.blockSignals(signals_were_blocked)

    def _ensure_table_runtime_i18n(self, table: QTableWidget) -> None:
        """Install event-driven translation for table cells changed by feature code.

        QTableWidget.itemChanged is suppressed when feature code temporarily calls
        table.blockSignals(True).  The underlying item model still emits dataChanged,
        so listen there as well.  This avoids the old fallback of rescanning every
        table on every Paint event, which was especially expensive for remote-file
        tables containing thousands of rows.
        """
        if bool(table.property("_i18n_runtime_item_hook")):
            return
        table.setProperty("_i18n_runtime_item_hook", True)

        def translate_range(top_left, bottom_right, _roles=None, *, _table=table, _manager=self):
            if bool(_table.property("_i18n_runtime_item_guard")):
                return
            _table.setProperty("_i18n_runtime_item_guard", True)
            try:
                top = max(0, top_left.row())
                bottom = min(_table.rowCount() - 1, bottom_right.row())
                left = max(0, top_left.column())
                right = min(_table.columnCount() - 1, bottom_right.column())
                for row in range(top, bottom + 1):
                    for col in range(left, right + 1):
                        item = _table.item(row, col)
                        if item is not None:
                            _manager._translate_table_item(_table, item)
            finally:
                _table.setProperty("_i18n_runtime_item_guard", False)
            schedule_fit_known_dense_table(_table)

        model = table.model()
        if model is not None:
            model.dataChanged.connect(translate_range)

    def _translate_table_widget(self, table: QTableWidget) -> None:
        self._ensure_table_runtime_i18n(table)
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                cell = table.item(row, col)
                if cell is not None:
                    self._translate_table_item(table, cell)

    def translate_widget_tree(self, root: QWidget) -> None:
        widgets: Iterable[QWidget] = [root, *root.findChildren(QWidget)]
        for widget in widgets:
            if widget.windowTitle():
                self._translate_text_property(widget, "windowTitle", widget.windowTitle, widget.setWindowTitle)
            if widget.toolTip():
                self._translate_text_property(widget, "toolTip", widget.toolTip, widget.setToolTip)
            if widget.statusTip():
                self._translate_text_property(widget, "statusTip", widget.statusTip, widget.setStatusTip)

            if isinstance(widget, QLabel):
                self._translate_text_property(widget, "text", widget.text, widget.setText)
            elif isinstance(widget, QAbstractButton):
                # Custom QMessageBox buttons may already have been translated before
                # creation by the presentation bridge. Do not rewrite them after the
                # modal button box is wired; feature code may compare clickedButton()
                # with the original returned button object.
                owner_box = widget.parentWidget()
                while owner_box is not None and not isinstance(owner_box, QMessageBox):
                    owner_box = owner_box.parentWidget()
                if not (
                    owner_box is not None
                    and bool(owner_box.property("_i18n_custom_buttons_pretranslated"))
                ):
                    self._translate_text_property(widget, "text", widget.text, widget.setText)
            elif isinstance(widget, QGroupBox):
                self._translate_text_property(widget, "title", widget.title, widget.setTitle)

            if isinstance(widget, QLineEdit) and widget.placeholderText():
                self._translate_text_property(widget, "placeholder", widget.placeholderText, widget.setPlaceholderText)
            if isinstance(widget, (QPlainTextEdit, QTextEdit)) and widget.placeholderText():
                self._translate_text_property(widget, "placeholder", widget.placeholderText, widget.setPlaceholderText)

            if isinstance(widget, QTextBrowser):
                current = widget.toHtml()
                source = self._source(widget, "html", current)
                curated = widget.property("_i18n_html_en")
                if self.is_english and curated is not None:
                    widget.setHtml(str(curated))
                else:
                    widget.setHtml(self.runtime_text(source) if self.is_english else source)
            elif isinstance(widget, QPlainTextEdit) and widget.isReadOnly():
                current = widget.toPlainText()
                source = self._source(widget, "plainText", current)
                widget.setPlainText(self.runtime_text(source) if self.is_english else source)

            if isinstance(widget, QComboBox):
                for i in range(widget.count()):
                    item = widget.itemText(i)
                    prop = f"_i18n_combo_{i}"
                    source = widget.property(prop)
                    if source is None:
                        widget.setProperty(prop, item)
                        source = item
                    widget.setItemText(i, self.text(str(source)) if self.is_english else str(source))

            if isinstance(widget, QListWidget):
                for i in range(widget.count()):
                    item = widget.item(i)
                    source = item.data(0x0100)  # Qt.UserRole without importing another enum
                    if source is None:
                        source = item.text()
                        item.setData(0x0100, source)
                    item.setText(self.text(str(source)) if self.is_english else str(source))
                    tip_source = item.data(0x0101)
                    if tip_source is None and item.toolTip():
                        tip_source = item.toolTip()
                        item.setData(0x0101, tip_source)
                    if tip_source:
                        tip = self.text(str(tip_source)) if self.is_english else str(tip_source)
                        item.setToolTip(tip)
                        item.setStatusTip(tip)

            if isinstance(widget, QTableWidget):
                self._translate_table_widget(widget)
                for col in range(widget.columnCount()):
                    item = widget.horizontalHeaderItem(col)
                    if item is None:
                        continue
                    source = item.data(0x0100)
                    if source is None:
                        source = item.text()
                        item.setData(0x0100, source)
                    item.setText(self.text(str(source)) if self.is_english else str(source))
                configure_known_dense_table(widget)

            if isinstance(widget, QTreeWidget):
                header = widget.headerItem()
                for col in range(widget.columnCount()):
                    source = header.data(col, 0x0100)
                    if source is None:
                        source = header.text(col)
                        header.setData(col, 0x0100, source)
                    header.setText(col, self.text(str(source)) if self.is_english else str(source))

            if isinstance(widget, QTabWidget):
                for i in range(widget.count()):
                    prop = f"_i18n_tab_{i}"
                    source = widget.property(prop)
                    if source is None:
                        source = widget.tabText(i)
                        widget.setProperty(prop, source)
                    widget.setTabText(i, self.text(str(source)) if self.is_english else str(source))

            if isinstance(widget, QStatusBar):
                message = widget.currentMessage()
                if message:
                    source = self._source(widget, "status_message", message)
                    widget.showMessage(self.text(source) if self.is_english else source)

        for action in root.findChildren(QAction):
            if action.text():
                self._translate_text_property(action, "text", action.text, action.setText)
            if action.toolTip():
                self._translate_text_property(action, "toolTip", action.toolTip, action.setToolTip)

    def _translate_dynamic_presentation_widget(self, widget: QWidget) -> None:
        """Translate only rendered UI text; never read or mutate business state.

        Feature modules keep their original Chinese source strings and original control
        flow.  This method runs at the presentation boundary so runtime label/button
        updates can still appear in English without inserting translation calls into
        feeder/RMU/ID/basic processing logic.
        """
        if not self.is_english:
            return
        if widget.windowTitle() and contains_cjk(widget.windowTitle()):
            self._translate_text_property(widget, "windowTitle", widget.windowTitle, widget.setWindowTitle)
        if isinstance(widget, QLabel) and contains_cjk(widget.text()):
            self._translate_text_property(widget, "text", widget.text, widget.setText)
        elif isinstance(widget, QAbstractButton) and contains_cjk(widget.text()):
            self._translate_text_property(widget, "text", widget.text, widget.setText)
        elif isinstance(widget, QGroupBox) and contains_cjk(widget.title()):
            self._translate_text_property(widget, "title", widget.title, widget.setTitle)
        # QTableWidget cells are translated by the model.dataChanged hook installed
        # in _ensure_table_runtime_i18n(). Never rescan a whole table from Paint.

    def _translate_after_show(self, widget: QWidget) -> None:
        """Translate a newly shown widget after Qt finishes its native show handling.

        This is intentionally presentation-only.  In Chinese mode the runtime i18n
        layer does absolutely nothing to newly created dialogs/widgets, so the
        original v2.17.60 behavior is preserved exactly.  In English mode translation
        is deferred to the next event-loop turn; this avoids touching QMessageBox
        buttons while Qt is still wiring its modal button box/click handling.
        """
        if not self.is_english or self._event_translate_guard:
            return
        self._event_translate_guard = True
        try:
            self.translate_widget_tree(widget)
        finally:
            self._event_translate_guard = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if self._event_translate_guard:
            return False

        # CRITICAL: Chinese is the immutable v2.17.60 golden behavior.  Do not touch
        # runtime widgets/dialogs at all in Chinese mode.
        if not self.is_english:
            return False

        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            # All application pages are pre-created and translated once by MainWindow.
            # When a stacked page becomes visible, hundreds of child widgets receive
            # Show events; translating each child subtree again causes module-switch
            # lag. Only newly shown top-level windows/dialogs need a deferred pass.
            # QMessageBox translation is still deferred until Qt finishes wiring its
            # modal button box.
            QTimer.singleShot(0, lambda w=watched: self._translate_after_show(w))
        elif event.type() == QEvent.Type.Paint and isinstance(watched, QWidget):
            # Feature code may update display text dynamically. Translate only the
            # rendered presentation value, without changing feature-module code.
            self._event_translate_guard = True
            try:
                self._translate_dynamic_presentation_widget(watched)
            finally:
                self._event_translate_guard = False
        return False

# v2.18.33 Site RMU Device Profile additions.  Kept as a late update so older
# translation keys remain backward-compatible with persisted UI text/state.
EN.update({
    "现场 RMU 图元 Profile": "Site RMU Device Profile",
    "第一次用标准 G 文件同时学习 SMART / 普通 RMU 图元 Profile；以后复用同一套 G 文件输入直接执行 RMU 图元一致性处理。": "Learn SMART and NORMAL RMU device profiles from standard G files the first time, then reuse the same G-file input for RMU device consistency processing.",
    "Site Profile 列表": "Site Profile List",
    "Version": "Version",
    "SMART CB": "SMART CB",
    "NORMAL LBS": "NORMAL LBS",
    "NORMAL CB": "NORMAL CB",
    "NORMAL LBS devref": "NORMAL LBS devref",
    "NORMAL Circuit Breaker devref": "NORMAL Circuit Breaker devref",
    "RMU 图元一致性处理": "RMU Device Consistency",
    "执行 RMU 图元一致性处理": "Run RMU Device Consistency",
    "正在执行 RMU 图元一致性处理……": "Running RMU device consistency processing...",
    "RMU Profile 处理输入": "RMU Profile Processing Input",
    "扫描并创建 Profile": "Scan and Create Profile",
    "重新扫描 Profile": "Rescan Profile",
    "打开报告": "Open Report",
    "Profile 已保存": "Profile Saved",
    "Profile 未完成": "Profile Incomplete",
    "扫描失败": "Scan Failed",
    "新建 Profile": "New Profile",
    "删除 Profile": "Delete Profile",
    "Profile 设置": "Profile Settings",
    "G 文件输入（学习与处理共用）": "G File Input (Shared for Learning and Processing)",
    "输出目录（workspace）": "Output Directory (workspace)",
    "尚未执行一致性处理。": "Consistency processing has not been run yet.",
    "报告不存在": "Report Not Found",
})

# v2.18.33 Site RMU Device Profile additions.
EN.update({
    "现场 RMU 图元 Profile": "Site RMU Device Profile",
    "第一次用标准 G 文件同时学习 SMART / 普通 RMU 图元 Profile；以后复用同一套 G 文件输入直接执行 RMU 图元一致性处理。": "Learn SMART and NORMAL RMU device profiles from standard G files the first time, then reuse the same G-file input for RMU device consistency processing.",
    "Version": "Version",
    "SMART CB": "SMART CB",
    "NORMAL LBS": "NORMAL LBS",
    "NORMAL CB": "NORMAL CB",
    "NORMAL LBS devref": "NORMAL LBS devref",
    "NORMAL Circuit Breaker devref": "NORMAL Circuit Breaker devref",
    "RMU 图元一致性处理": "RMU Device Consistency",
    "执行 RMU 图元一致性处理": "Run RMU Device Consistency",
    "正在执行 RMU 图元一致性处理……": "Running RMU device consistency processing...",
    "RMU Profile 处理输入": "RMU Profile Processing Input",
})

# v2.18.34 Site RMU Device Profile version/update workflow additions.
EN.update({
    "State": "State",
    "Profile Status": "Profile Status",
    "ACTIVE": "ACTIVE",
    "ARCHIVED": "ARCHIVED",
    "恢复此版本": "Restore This Version",
    "扫描进度 %p%": "Scan Progress %p%",
    "更新当前 Profile": "Update Current Profile",
    "Profile 已有图元标准": "Profile Already Has a Device Standard",
    "Profile Name 已存在": "Profile Name Already Exists",
    "历史版本只读": "Archived Version Is Read-only",
    "已经是当前版本": "Already the Active Version",
    "恢复历史版本": "Restore Archived Version",
    "恢复失败": "Restore Failed",
    "已恢复": "Restored",
    "请选择 ACTIVE 版本": "Select the ACTIVE Version",
    "历史版本不能单独删除": "Archived Versions Cannot Be Deleted Individually",
    "更新 Profile 标准": "Update Profile Standard",
    "正在准备标准样本……": "Preparing standard samples...",
    "扫描标准样本并学习 SMART / NORMAL 图元与图元几何的进度。": "Progress for scanning standard samples and learning SMART/NORMAL device symbols and geometry.",
})

# v2.18.35 RMU grounding-switch profile and Jeddah profile-driven consistency.
EN.update({
    "SMART 接地刀闸": "SMART Grounding Switch",
    "NORMAL 接地刀闸": "NORMAL Grounding Switch",
    "SMART 接地刀闸 devref（ZhaiWaiJieDiDaoZha）": "SMART Grounding Switch devref (ZhaiWaiJieDiDaoZha)",
    "NORMAL 接地刀闸 devref（ZhaiWaiJieDiDaoZha）": "NORMAL Grounding Switch devref (ZhaiWaiJieDiDaoZha)",
    "Needs Ground": "Needs Ground",
    "吉达 RMU 图元 Profile": "Jeddah RMU Device Profile",
    "吉达 RMU 图元 Profile 未选择": "Jeddah RMU Device Profile Not Selected",
    "Profile 学习不完整": "Profile Learning Incomplete",
})

# v2.18.36 Site RMU symbol-standard UX consolidation.
EN.update({
    "现场 RMU 图元标准与升级": "Site RMU Symbol Standard & Upgrade",
    "用标准 G 文件学习 SMART / 普通 RMU 的 LBS、断路器、接地刀闸及图元几何；以后用当前 ACTIVE 版本检查并升级旧 G 文件。": "Learn LBS, circuit breaker, grounding-switch and symbol geometry standards for SMART/NORMAL RMUs from standard G files, then use the current ACTIVE version to check and upgrade older G files.",
    "当前 RMU 图元标准": "Current RMU Symbol Standard",
    "Profile 管理": "Profile Management",
    "现场": "Site",
    "Profile 名称": "Profile Name",
    "版本": "Version",
    "样本": "Samples",
    "置信度": "Confidence",
    "Profile 状态": "Profile Status",
    "图元标准": "Symbol Standards",
    "现场名称": "Site Name",
    "RMU 类型": "RMU Type",
    "设备角色": "Device Role",
    "标准图元": "Standard Symbol",
    "保存当前标准": "Save Current Standard",
    "G 文件输入（学习 / 升级共用）": "G File Input (Shared for Learning / Upgrade)",
    "主操作": "Main Actions",
    "扫描标准样本 / 创建 Profile": "Scan Standard Samples / Create Profile",
    "扫描标准样本 / 更新 Profile": "Scan Standard Samples / Update Profile",
    "检查并升级所选 G 文件": "Check & Upgrade Selected G Files",
    "处理结果与日志": "Results & Logs",
    "日常处理直接使用当前 ACTIVE Profile 检查并升级所选 G 文件；图元标准变化时，再从“Profile 管理”中执行标准样本扫描/更新。升级过程中保持电气连接锚点绝对位置不变。": "For routine work, use the current ACTIVE Profile to check and upgrade the selected G files. When the symbol standard changes, scan/update standard samples from Profile Management. Electrical connection anchor positions are kept unchanged during upgrades.",
    "尚未执行检查与升级。": "Check and upgrade has not been run yet.",
    "正在检查并升级 RMU 图元……": "Checking and upgrading RMU symbols...",
    "就绪": "Ready",
    "需确认": "Needs Confirmation",
    "未学习": "Not Learned",
    "已保存": "Saved",
})

# v2.18.42 Generic Symbol Standard Check module.
EN.update({
    "服务器图元同步管理": "Server Symbol Sync Manager",
    "服务器图元同步管理帮助": "Server Symbol Sync Manager Help",
    "同步服务器图元信息": "Sync Server Symbol Information",
    "打开本地图元缓存": "Open Local Symbol Cache",
    "导出分类标记 JSON": "Export Classification Markers JSON",
    "载入分类标记 JSON": "Import Classification Markers JSON",
    "保存到本地": "Save Locally",
    "上传到服务器": "Upload to Server",
    "从服务器同步": "Sync from Server",
    "导出本地 JSON": "Export Local JSON",
    "导入本地 JSON": "Import Local JSON",
    "本地分类": "Local Classification",
    "服务器分类": "Server Classification",
    "服务器图元同步与分类管理": "Server Symbol Sync & Classification",
    "远程服务器图元信息同步（严格只读）": "Remote Server Symbol Sync (Read-only)",
    "服务器图元目录（左侧为序号）：尚未同步": "Server symbol catalog (serial numbers at left): Not synchronized",
    "搜索服务器图元": "Search Server Symbols",
    "服务器图元更新检查": "Server Symbol Update Check",
    "分类标记": "Classification Marker",
    "服务器图元更新检查帮助": "Server Symbol Update Check Help",
    "服务器图元更新检查输出目录": "Server Symbol Update Check Output Directory",
    "尚未执行服务器图元更新检查。": "No server symbol update check has been run yet.",
    "服务器图元更新检查输入": "Server Symbol Update Check Input",
    "服务器图元更新检查完成": "Server Symbol Update Check Complete",
    "图元标准检查": "Symbol Standard Check",
    "用标准 G 文件建立可复用图元标准；可先只检查所选 G 文件是否符合标准，也可在确认后执行检查并升级。": "Build reusable symbol standards from confirmed G files. Check selected G files in read-only mode first, then optionally check and upgrade them.",
    "当前图元标准": "Current Symbol Standard",
    "当前执行标准：尚未创建标准": "Current Standard: No standard created",
    "标准管理": "Standard Management",
    "新建标准": "New Standard",
    "扫描标准样本 / 创建标准": "Scan Standard Samples / Create Standard",
    "扫描标准样本 / 更新标准": "Scan Standard Samples / Update Standard",
    "删除标准": "Delete Standard",
    "删除选中历史版本": "Delete Selected Historical Version",
    "删除整个标准（全部版本）": "Delete Entire Standard (All Versions)",
    "适用范围": "Scope",
    "标准名称": "Standard Name",
    "标准状态": "Standard Status",
    "标准定义": "Standard Definition",
    "G 文件输入（标准学习 / 检查 / 升级共用）": "G File Input (Shared for Learning / Check / Upgrade)",
    "只检查标准": "Check Only",
    "检查并升级": "Check & Upgrade",
    "图元标准检查输出目录": "Symbol Standard Output Directory",
    "尚未执行图元标准检查。": "No symbol standard check has been run yet.",
    "请选择标准": "Select Standard",
    "标准未完成": "Standard Incomplete",
    "标准已保存": "Standard Saved",
    "标准名称已存在": "Standard Name Already Exists",
    "更新图元标准": "Update Symbol Standard",
    "图元标准检查输入": "Symbol Standard Check Input",
    "图元标准样本": "Symbol Standard Samples",
    "图元标准检查帮助": "Symbol Standard Check Help",
    "正在只读检查图元标准……源 G 文件不会修改。": "Checking symbol standards in read-only mode... Source G files will not be modified.",
    "正在按当前标准检查并升级图元……": "Checking and upgrading symbols against the current standard...",
})


# v2.18.44 User-defined generic symbol standards.
EN.update({
    "内置 RMU 标准": "Built-in RMU Standards",
    "自定义设备图元": "Custom Device Symbols",
    "前 6 行是现有 RMU 系统标准；下面可以继续添加任意设备图元。扫描标准 G 后，表格会显示图元文件、w/h、AlignCenter、pin 坐标等属性，便于确认标准图元信息。": "After scanning standard G files, the table shows the symbol file, w/h, AlignCenter and pin coordinates for operator review.",
    "添加设备图元": "Add Device Symbol",
    "添加扫描到的未映射图元": "Add Scanned Unmapped Symbols",
    "删除选中自定义项": "Delete Selected Custom Rule",
    "范围": "Scope",
    "设备角色": "Device Role",
    "XML 元素": "XML Element",
    "标准图元 devref": "Standard Symbol devref",
    "主体 ID": "Body ID",
    "w×h": "w×h",
    "AlignCenter": "AlignCenter",
    "Pins": "Pins",
    "匹配属性": "Match Attribute",
    "当前/旧图元匹配值": "Current/Old Symbol Match Value",
    "系统规则": "System Rule",
    "RMU 内接地刀闸": "Grounding Switch in RMU",
    "自定义设备": "Custom Device",
    "待确认": "Pending Confirmation",
    "缺少标准图元": "Missing Standard Symbol",
    "缺少 XML 元素": "Missing XML Element",
    "系统标准不能删除": "System Standard Cannot Be Deleted",
    "前 6 行是现有 RMU 系统标准。你可以修改标准图元，但不能删除这些系统规则。": "The first six rows are existing RMU system rules. You may change their standard symbols, but these system rules cannot be deleted.",
    "没有扫描结果": "No Scan Result",
    "请先扫描标准 G 文件。程序会把 G 中识别到的 devref 与元素属性列出来。": "Scan standard G files first. The program will list the detected devrefs and element properties.",
    "没有未映射图元": "No Unmapped Symbols",
    "扫描到的图元都已经存在于当前标准表中。": "All scanned symbols are already present in the current standard table.",
    "批量添加未映射图元": "Add Unmapped Symbols in Bulk",
    "自定义图元未完成": "Custom Symbol Incomplete",
    "自定义设备图元必须至少填写“XML 元素”和“标准图元 devref”。请补充后再保存。": "Each custom device symbol must include at least an XML Element and Standard Symbol devref before saving.",
    "图元属性目录": "Symbol Property Catalog",
    "扫描完成。请确认内置 RMU 标准；还可以点击“添加设备图元”或“添加扫描到的未映射图元”，继续维护其他设备图元标准。": "Scan complete. Confirm the built-in RMU standards, then use Add Device Symbol or Add Scanned Unmapped Symbols to maintain additional device standards.",
})

# v2.18.46 Read-only Symbol Standard Check + same-class version upgrade terminology.
EN.update({
    "用标准 G 文件建立可复用图元标准，并只读检查所选 G 文件是否符合当前 ACTIVE 标准；发现差异只告警和生成报告，不修改 G。": "Build reusable symbol standards from confirmed G files and inspect selected G files against the current ACTIVE standard in read-only mode. Differences only raise warnings and reports; G files are never modified.",
    "G 文件输入与输出（标准学习 / 检查共用）": "G File Input & Output (Shared for Standard Learning / Check)",
    "检查结果与日志": "Check Results & Logs",
    "同类图元版本升级": "Same-Class Symbol Version Upgrade",
    "启用同类图元版本升级": "Enable Same-Class Symbol Version Upgrade",
    "同类图元版本升级检查": "Same-Class Symbol Version Upgrade Check",
    "同类图元版本升级检查未通过": "Same-Class Symbol Version Upgrade Check Failed",
    "同类图元版本升级映射检查通过": "Same-Class Symbol Version Upgrade Mapping Check Passed",
    "图元标准不一致": "Symbol Standard Mismatch",
    "图元标准检查完成": "Symbol Standard Check Complete",
    "标准检查": "Standard Check",
})

# v2.18.48 Simplified symbol-standard inspection UX and one-time discovery queue.
EN.update({
    "待检查 G 文件": "G Files to Check",
    "图元标准检查": "Symbol Standard Check",
    "检查图元标准": "Check Symbol Standard",
    "查看检查报告": "View Check Report",
    "打开结果目录": "Open Results Folder",
    "编辑标准": "Edit Standard",
    "收起标准编辑": "Collapse Standard Editor",
    "显示日志": "Show Log",
    "隐藏日志": "Hide Log",
    "查看待确认图元": "Review Pending Symbols",
    "重新显示已忽略图元": "Restore Ignored Symbols",
    "发现新的图元类型": "New Symbol Types Found",
    "请选择当前标准": "Select Current Standard",
    "没有待确认图元": "No Pending Symbols",
    "当前标准没有需要确认的新图元。": "The current standard has no new symbols awaiting confirmation.",
    "加入当前标准": "Add to Current Standard",
    "不纳入此标准": "Exclude from This Standard",
    "剩余稍后处理": "Review Remaining Later",
    "加入标准失败": "Failed to Add Standard",
    "新图元已处理": "New Symbols Processed",
    "没有已忽略图元": "No Ignored Symbols",
    "当前标准没有已忽略的新图元。": "The current standard has no ignored new symbols.",
    "已恢复提示": "Notifications Restored",
    "正在检查图元标准……源 G 文件不会修改。": "Checking symbol standards... Source G files will not be modified.",
    "当前还没有检查报告，请先点击“检查图元标准”。": "No check report is available yet. Click Check Symbol Standard first.",
})


# v2.18.53 Symbol Standard safe correction (Jeddah batch unchanged).
EN.update({
    "纠正标准问题": "Correct Standard Issues",
    "确认纠正图元标准问题": "Confirm Symbol Standard Correction",
    "图元标准纠正完成": "Symbol Standard Correction Complete",
    "图元标准纠正完成（仍有待处理项）": "Symbol Standard Correction Complete (Items Remain)",
    "正在按 ACTIVE 标准生成纠正副本……源 G 文件不会覆盖。": "Creating corrected copies from the ACTIVE standard... Source G files will not be overwritten.",
    "用标准 G 文件建立可复用图元标准，检查所选 G 是否符合当前 ACTIVE 标准；需要时可生成按标准纠正后的 workspace 副本，源 G 不覆盖。": "Build reusable symbol standards, check selected G files against the current ACTIVE standard, and optionally create corrected workspace copies without overwriting source G files.",
})

# v2.18.68 Smart RMU Poke batch-safe ahref naming UI.
EN.update({
    "Poke ahref 命名": "Poke ahref Naming",
    "自动按每个主图文件名生成（推荐）": "Auto from Each Main G Filename (Recommended)",
    "自定义模板": "Custom Template",
    "自定义 ahref 模板": "Custom ahref Template",
    "自定义模板模式必须填写 ahref 模板；模板必须包含 {rmu}。": "Custom-template mode requires an ahref template containing {rmu}.",
    "自定义 ahref 模板必须包含 {rmu}，避免多个智能 RMU 指向同一个详情图。": "The custom ahref template must contain {rmu} so multiple smart RMUs do not point to the same detail drawing.",
    "Poke ahref 模板": "Poke ahref Template",
})


# v2.18.69 Smart RMU Poke standalone single/batch naming module.
EN.update({
    "智能环网柜 Poke 跳转": "Smart RMU Poke Jump",
    "启用智能环网柜 Poke 跳转": "Enable Smart RMU Poke Jump",
    "生成方式：": "Generation Mode:",
    "单文件 / 固定详情图规则": "Single File / Fixed Detail Rule",
    "批处理 / 从主图文件名提取 FEEDER": "Batch / Extract FEEDER from Main Filename",
    "单文件详情图规则": "Single-File Detail Rule",
    "批处理详情图规则": "Batch Detail Rule",
    "智能 RMU Poke": "Smart RMU Poke",
})

# v2.18.70 Smart RMU Poke unified FACNAME/RMU ahref template.
EN.update({
    "ahref 文件名模板": "ahref Filename Template",
    "请填写 ahref 文件名模板，例如 JED-NTH-ABH-{FACNAME}-{RMU}-JED.com.pic.g。": "Enter an ahref filename template, for example JED-NTH-ABH-{FACNAME}-{RMU}-JED.com.pic.g.",
    "独立为已识别的智能 RMU（SMART / SMR）生成或更新 Poke ahref。单文件和批处理统一使用同一套模板：模板中的 {FACNAME} 从当前 G 文件根节点 facName 读取，{RMU} 使用现有 RMU 识别逻辑得到的柜名；除此之外的文件名内容全部由用户自己指定，程序不再从源 G 文件名推断区域、站点或馈线号。": "Create or update Poke ahref targets for identified smart RMUs (SMART / SMR). Single-file and batch processing use the same template: {FACNAME} comes from the current G root facName, and {RMU} comes from the existing RMU identification result. All other filename text is supplied by the user; the program no longer infers region, station, or feeder data from the source G filename.",
    "示例：模板 JED-NTH-ABH-{FACNAME}-{RMU}-JED.com.pic.g；当前 G 的 facName=AH303，识别 RMU=34661 → JED-NTH-ABH-AH303-34661-JED.com.pic.g。批处理时每个文件读取自己的 facName；不再检查或解析源文件名。": "Example: template JED-NTH-ABH-{FACNAME}-{RMU}-JED.com.pic.g; with facName=AH303 and RMU=34661, the result is JED-NTH-ABH-AH303-34661-JED.com.pic.g. In batch processing, each file uses its own facName; source filenames are no longer validated or parsed.",
    "Poke 仍只包住已识别的 RMU 柜名；已有 1 个相关 Poke 则复用，多个则删除多余项只保留 1 个。如果模板使用 {FACNAME} 而某个 G 文件根节点 facName 为空，只跳过该文件的 Poke 并记录告警，不影响该文件的组合、颜色、RMU 汇总或同批其他文件。": "The Poke still wraps only the identified RMU name. One existing related Poke is reused; duplicates are removed so only one remains. If the template uses {FACNAME} and a G file has an empty root facName, only that file's Poke operation is skipped with a warning; grouping, colors, RMU summary, and other batch files continue.",
})

# v2.18.73 Simplified mandatory RMU foundation + configurable intelligent markers.
EN.update({
    "智能 RMU 标记字符：": "Smart RMU Marker Text:",
    "柜名排除字符串：": "RMU Name Exclusions:",
    "例如：SMART, SMR, NEWSMART, SMART-SE": "e.g. SMART, SMR, NEWSMART, SMART-SE",
    "修改智能环网柜外框颜色": "Change Smart RMU Frame Color",
})

# v2.18.74 Authoritative persistent symbol standard library.
EN.update({
    "上传标准图元 G / 创建标准": "Upload Standard Symbol G / Create Standard",
    "上传标准图元 G / 更新标准": "Upload Standard Symbol G / Update Standard",
    "上传标准图元 G（可多选）": "Upload Standard Symbol G (Multiple Selection)",
    "尚未上传标准图元。": "No standard symbol G files uploaded yet.",
    "标准图元库未就绪": "Standard Symbol Library Not Ready",
    "必须上传标准图元": "Standard Symbol G Upload Required",
    "标准图元文件": "Standard Symbol Files",
    "标准指纹": "Standard Fingerprint",
    "标准图元绑定无效": "Invalid Standard Symbol Binding",
    "标准图元读取完成。请确认 6 个 RMU 基础角色都绑定了本次上传的唯一图元，然后保存为 ACTIVE 标准。": "Standard symbol files loaded. Confirm that all six RMU base roles are bound to exactly one uploaded symbol, then save the ACTIVE standard.",
})

# v2.18.75 Uploaded icon G is the sole authority for Symbol Standard Check.
EN.update({
    "上传 / 更新标准图元 G": "Upload / Update Standard Symbol G",
    "上传标准图元 G": "Upload Standard Symbol G",
    "添加自定义设备角色": "Add Custom Device Role",
    "标准来源": "Standard Source",
    "未上传": "Not Uploaded",
    "标准图元无效": "Invalid Standard Symbol G",
    "缺少标准图元": "Missing Standard Symbol",
    "标准来源已切换为用户上传图元 G。业务单线图不会参与 devref、尺寸、AlignCenter 或 pin 标准的生成。": "The standard source is now the user-uploaded symbol G files. Business SLD G files never contribute devref, size, AlignCenter, or pin standards.",
})

# v2.18.79 Single-table symbol-standard UX + shared SMART/NORMAL bindings.
EN.update({
    "标准版本": "Standard Version",
    "检查范围": "Check Scope",
    "标准图元文件": "Standard Symbol File",
    "用户上传": "User Upload",
    "SMART / NORMAL 共用此标准": "Share This Standard Across SMART / NORMAL",
    "勾选后，当前标准 G 会同时绑定到同一种设备角色的 SMART 与 NORMAL 检查范围。": "When enabled, the current standard G is bound to the same device role in both SMART and NORMAL check scopes.",
    "这里不再分成“当前标准列表”和“标准定义”两个表格：一个页面只保留下面这一张图元标准表。标准版本通过上方下拉框切换。每个设备角色可以分别使用 SMART / NORMAL 标准，也允许两者共用同一个用户上传的标准图元 G。标准文件保存到用户数据目录；业务单线图永远只作为被检查对象，不会反向学习成标准。业务单线图不会参与 devref、尺寸、AlignCenter 或 pin 标准的生成。": "The separate current-standard list and standard-definition tables are merged into one symbol-standard table. Switch versions from the selector above. Each device role may use separate SMART/NORMAL standards or share one user-uploaded standard G. Standard files are stored in the user data directory; business SLD G files are check targets only and never contribute devref, size, AlignCenter, or pin standards.",
    "表中的 SMART / NORMAL 表示“检查适用范围”，不代表一定要上传两套不同图元。如果同一设备在 SMART 与 NORMAL 中使用同一个图元，勾选“SMART / NORMAL 共用此标准”后上传一次即可同时绑定两行；例如接地刀闸没有智能/非智能版本时，就应共用同一个标准 G。若两边确实不同，则分别上传即可。可以只配置当前需要检查的设备角色，不要求一次补齐全部范围。": "SMART / NORMAL in the table describes the check scope; it does not require two different symbol files. If the same device uses one symbol in both scopes, enable Share This Standard Across SMART / NORMAL and upload once to bind both rows. For example, a grounding switch with no smart/non-smart variant should share one standard G. If the variants truly differ, upload them separately. You may configure only the roles you need to check.",
})


# v2.18.79 Explicit role binding, immutable standard lock, and no business-G learning.
EN.update({
    "这里不再分成“当前标准列表”和“标准定义”两个表格：一个页面只保留下面这一张图元标准表。标准版本通过上方下拉框切换。每个设备角色可以分别使用 SMART / NORMAL 标准，也允许两者共用同一个用户上传的标准图元 G。标准文件保存到用户数据目录；业务单线图永远只作为被检查对象，不会反向学习、发现或补全标准。设备角色由用户选中的表格行明确绑定；上传 G 只提供该角色的 devref、尺寸、AlignCenter 与 pin 标准。业务单线图不会参与 devref、尺寸、AlignCenter 或 pin 标准的生成。": "The page now uses one symbol-standard table. Switch versions from the selector above. SMART/NORMAL standards may be separate or share one uploaded G. Business drawings are inspection targets only: they never learn, discover, or complete standards. The selected table role is the explicit binding authority; the uploaded G supplies devref, size, AlignCenter, and pin standards only.",
    "表中的 SMART / NORMAL 表示“检查适用范围”，不代表一定要上传两套不同图元。如果同一设备在 SMART 与 NORMAL 中使用同一个图元，勾选“SMART / NORMAL 共用此标准”后上传一次即可同时绑定两行；例如接地刀闸没有智能/非智能版本时，就应共用同一个标准 G。若两边确实不同，则分别上传即可。可以只配置当前需要检查的设备角色，不要求一次补齐全部范围。上传文件名/XML 类型仅作为参考信息，不再阻止人工绑定。": "SMART/NORMAL describes check scope and does not require two different symbol files. If the same device uses one symbol in both scopes, enable sharing and upload once to bind both rows. Ground switches without smart/non-smart variants should share one standard. Configure only the roles you need. Uploaded filenames and parsed XML types are reference information only and do not block explicit manual binding.",
    "锁定当前版本": "Lock Current Version",
    "解锁当前版本": "Unlock Current Version",
    "锁定当前标准": "Lock Current Standard",
    "解锁当前标准": "Unlock Current Standard",
    "当前标准已锁定": "Current Standard Is Locked",
    "检查对象 XML": "Target XML",
    "设备定位规则": "Device Locator Rule",
    "定位条件": "Locator Condition",
    "上传文件名/XML 类型仅作为参考信息，不再阻止人工绑定。": "Uploaded filenames and parsed XML types are reference information only and no longer block explicit manual binding.",
})


# v2.18.89 Database-driven Smart RMU Poke naming.
EN.update({
    "启用后不再要求用户填写站名、馈线名或 ahref 模板。程序读取当前 G 根节点 facID，通过公共 Oracle 数据库依次查询 DMS_FEEDER_DEVICE.NAME/ST_ID、SUBSTATION.NAME/SUBAREA_ID、SUBCONTROLAREA.NAME，自动得到完整馈线名，再与 G 文件中已识别的智能 RMU 柜名组合生成 Poke 跳转文件名。": "When enabled, users no longer enter station, feeder, or ahref templates. The program reads the G root facID, resolves DMS_FEEDER_DEVICE.NAME/ST_ID, SUBSTATION.NAME/SUBAREA_ID, and SUBCONTROLAREA.NAME through the shared Oracle database, builds the full feeder name, then combines it with the already identified smart RMU name.",
    "自动命名规则：SUBCONTROLAREA.NAME + SUBSTATION.NAME + DMS_FEEDER_DEVICE.NAME + RMU。例如数据库得到 JED-NTH + ABH + AH303，G 中识别 RMU=34661，最终 ahref 为 JED-NTH-ABH-AH303-34661.com.pic.g。GRAPH_NAME 和 G.facName 不参与名称拼接；facName 仅可用于一致性提示。": "Automatic naming: SUBCONTROLAREA.NAME + SUBSTATION.NAME + DMS_FEEDER_DEVICE.NAME + RMU. For example, JED-NTH + ABH + AH303 with RMU=34661 produces JED-NTH-ABH-AH303-34661.com.pic.g. GRAPH_NAME and G.facName are not used to construct the name; facName is only an optional consistency hint.",
    "前提：G 根节点 facID 必须有效。facID 为空时，本文件不会执行 Poke，程序会提示“请先关联馈线”，其他环网柜组合、改色、柜名和汇总操作仍继续。数据库连接统一使用左侧“数据库”页面保存的公共配置。": "Requirement: the G root facID must be valid. If facID is empty, Poke is skipped for that file and the program asks the user to associate the feeder first; grouping, coloring, RMU names, and summaries continue. The shared connection saved on the Database page is used.",
    "Poke 仍只包住既有 RMU 基础识别得到的智能柜名 Text；已有 1 个对应 Poke 则复用，多个则删除多余项仅保留 1 个。Poke 模块不会另写 RMU 识别规则。": "Poke still covers only the smart cabinet-name Text returned by the existing RMU identification. One matching Poke is reused; duplicates are removed so only one remains. The Poke module does not implement a separate RMU recognition rule.",
})

# v2.18.90 Standalone Poke processing: RMU detail jumps + station-jump jumps.
EN.update({
    "Poke 跳转处理": "Poke Jump Processing",
    "独立生成/修复 RMU 与站点跳转 Poke；复用公共 RMU 识别、Oracle 数据库及站点 Poke 参考属性": "Create/repair RMU and station-jump Pokes using the shared RMU recognition, Oracle database, and station-Poke reference properties.",
    "独立生成/修复 RMU 与站点跳转 Poke；站点跳转按强制图形条件筛选，数据库查询逻辑保持不变。": "Create/repair RMU and station-jump Pokes independently. Station-jump candidates use mandatory graphic constraints; the database lookup chain is unchanged.",
    "Poke 跳转处理帮助": "Poke Jump Processing Help",
    "跳转类型": "Jump Types",
    "RMU Poke：跳转到具体环网柜明细图": "RMU Poke: Jump to a Specific RMU Detail Drawing",
    "站点跳转 Poke：跳转到对端变电站馈线总图": "Station-Jump Poke: Jump to the Remote Substation Feeder Overview",
    "RMU Poke：环网柜明细图　目标：{区域}-{变电站}-{馈线}-{RMU}.com.pic.g": "RMU Poke: RMU detail drawing  Target: {area}-{substation}-{feeder}-{RMU}.com.pic.g",
    "站点跳转 Poke：变电站馈线总图　目标：{区域}-{变电站}.sln.pic.g": "Station-Jump Poke: Substation feeder overview  Target: {area}-{substation}.sln.pic.g",
    "Poke 目标文件命名规则": "Poke Target File Naming Rules",
    "智能环网柜名字 Poke 目标文件：{区域}-{变电站}-{馈线}-{RMU}.com.pic.g\n站点跳转 Poke 目标文件：{区域}-{变电站}.sln.pic.g": "Smart RMU Name Poke target file: {area}-{substation}-{feeder}-{RMU}.com.pic.g\nStation-jump Poke target file: {area}-{substation}.sln.pic.g",
    "识别与数据库规则": "Recognition & Database Rules",
    '站点跳转强制规则：只识别站点 Text；Text 必须是字母+数字格式（如 ANS2-44，纯数字不接受），必须有独立的可见彩色背景，并且名称 Text 本身不能是红色；已被 RMU 或 AR/LBS/SEC 设备名称占用的 Text 也不会再作为站点跳转名称。通过条件后执行原有 SUBSTATION.NAME → SUBAREA_ID → SUBCONTROLAREA.NAME 查询。若站点 Text 旁边 100 以内存在括号纯数字 （如 (35033)），只允许最终选择一个；如果 100 内存在多个括号环网柜名，只取离站点名称最近的一个作为 locateLabel；如果没有环网柜名，则使用站点间隔后缀备用规则 （如 RDS-09 → AH309）。括号数字不属于站点名。': 'Mandatory station-jump rules: only station Text is considered. It must contain letters and digits (for example ANS2-44; pure numbers are rejected), have a separate visible colored background, and the name Text itself must not be red. Text already owned by an RMU or AR/LBS/SEC device name is excluded. After those checks, the existing SUBSTATION.NAME -> SUBAREA_ID -> SUBCONTROLAREA.NAME lookup runs. A parenthesized numeric RMU name within 100 units may be used as locateLabel; the final result must contain only one, and when several candidates exist the nearest one is selected. If none qualifies, the station-interval fallback is used (for example RDS-09 -> AH309).',
    "开始 Poke 跳转处理": "Start Poke Jump Processing",
    "Poke 跳转处理输入": "Poke Processing Input",
    "Poke 跳转处理输出目录": "Poke Processing Output Directory",
    "请至少选择一种 Poke 跳转类型。": "Select at least one Poke jump type.",
    "Poke 已从“环网柜处理”独立，facID 不再作为执行前提。RMU Poke 直接复用公共 RMU 识别结果，并按每个已识别环网柜名称查询 DMS_COMBINED_DEVICE.FEEDER_ID，再沿 DMS_FEEDER_DEVICE/SUBSTATION/SUBCONTROLAREA 生成各自的完整馈线目标；一张大图可同时处理多条馈线。站点跳转 Poke 独立查找，只有同时满足字母+数字站点名和彩色背景的标签才进入数据库查询，本身不使用 facID。GRAPH_NAME 不参与目标名称生成。": "Poke processing is independent from RMU Processing and no longer requires facID. RMU Pokes reuse shared RMU recognition, resolve each recognized cabinet through DMS_COMBINED_DEVICE.FEEDER_ID, then follow DMS_FEEDER_DEVICE/SUBSTATION/SUBCONTROLAREA to build that RMU's own feeder target; one overview drawing may therefore contain multiple feeders. Station-jump Pokes use only labels that satisfy the mandatory conditions—an alphanumeric station name and a colored background—before querying the database. They do not use facID. GRAPH_NAME is not used for target naming.",
    "RMU Poke 不在本模块重新定义 RMU 规则：运行时直接读取“环网柜处理”保存的柜名方向、名称排除项和智能标记，并调用同一个 identify_rmus()。识别到柜名后，以 RMU 名称查询 DMS_COMBINED_DEVICE，由 FEEDER_ID 找到所属 DMS_FEEDER_DEVICE，再按 SUBSTATION/SUBCONTROLAREA 生成该 RMU 自己的馈线完整业务名；不依赖 facID。": "This module does not define a second RMU rule set. It reads the name directions, exclusions and smart markers saved by RMU Processing and calls the same identify_rmus(). After a cabinet name is recognized, that RMU name resolves DMS_COMBINED_DEVICE, FEEDER_ID identifies its DMS_FEEDER_DEVICE, and SUBSTATION/SUBCONTROLAREA produce that RMU's own full feeder business name without facID.",
    "站点跳转强制规则：站点 Text 必须是字母+数字格式（如 ANS2-44，纯数字不接受），必须有彩色背景；通过全部条件后才执行原有 SUBSTATION.NAME → SUBAREA_ID → SUBCONTROLAREA.NAME 查询。若旁边存在唯一的括号环网柜名（如 (35033)），优先写入该环网柜定位号；如果没有环网柜名，则把站点间隔后缀按 AH3+数字转换（如 RDS-09 → AH309），生成 JED-CTL-RDS.sln.pic.g?locateLabel=AH309&&scaleFlag=true。括号数字不属于站点名；条件不满足时不创建或更新站点跳转。": "Mandatory station-jump rules: the station Text must be alphanumeric (for example, ANS2-44; pure numbers are rejected) and have a colored background. Only after all conditions pass does the existing SUBSTATION.NAME -> SUBAREA_ID -> SUBCONTROLAREA.NAME lookup run. A unique adjacent RMU name is preferred as the locate label; when no RMU name is available, the numeric station suffix is converted with the AH3 prefix, for example RDS-09 -> AH309, producing JED-CTL-RDS.sln.pic.g?locateLabel=AH309&&scaleFlag=true. The parenthesized number is not part of the station name; no station jump is created or updated when any condition fails.",
    "上述条件全部是强制约束：已有 Poke 或几何形状不能替代彩色背景。括号环网柜名距离必须 ≤100；若有多个候选只取最近的一个；只有没有合格环网柜名时才使用站点间隔后缀备用规则。数据库唯一匹配成功后才允许修改，多个相关 Poke 仍只保留一个。": "All of the above are mandatory constraints: an existing Poke or geometry cannot replace the colored background. Adjacent parenthesized RMU names must be within 100 units; if several qualify, only the nearest one is used. The station-interval fallback is used only when no qualifying RMU name is available. Modification is allowed only after a unique database match, and duplicate related Pokes are still reduced to one.",
    "本页面负责 RMU 基础识别、环网柜组合、智能 RMU 外框改色、RMU 柜名改白、channel_status 状态点，以及柜名/柜型识别；Poke 跳转已独立到左侧“Poke 跳转处理”模块。": "This page handles RMU recognition, grouping, smart-RMU frame color, white RMU names, channel_status positioning, and name/type recognition. Poke jumps have moved to the standalone Poke Jump Processing module.",
})

# v2.18.91 Poke processing report.
EN.update({
    "打开 Poke 报告": "Open Poke Report",
    "打开最近一次 Poke 跳转处理生成的 HTML 报告；报告包含 RMU/站点跳转识别、写入 ahref、处理动作及未加跳转原因。": "Open the latest Poke HTML report. It includes RMU/station-jump recognition, written ahref targets, actions, and reasons why a jump was not added.",
    "请先执行一次 Poke 跳转处理并生成报告。": "Run Poke Jump Processing once to generate a report first.",
    "Poke处理报告": "Poke Processing Report",
    "Poke报告摘要": "Poke Report Summary",
})

# v2.18.202 Independent AR/LBS/SEC Poke and strict red top/right name recognition.
EN.update({
    "RMU Poke：环网柜设备明细图　目标：{区域}-{变电站}-{馈线}-{RMU名}.com.pic.g": "RMU Poke: RMU detail drawing  Target: {area}-{substation}-{feeder}-{RMU}.com.pic.g",
    "AR / LBS / SEC Poke（独立）：设备明细图　目标：{区域}-{变电站}-{馈线}-{设备名}.com.pic.g": "AR / LBS / SEC Poke (independent): device detail drawing  Target: {area}-{substation}-{feeder}-{device}.com.pic.g",
    "只执行独立的 AR/LBS/SEC 设备 Poke；名称必须有明确非白色颜色，红色优先、其他颜色兜底，按上方→右侧→全局优先级识别且距离不超过 200，其他数据库/ahref 逻辑不变。": "Run only the independent AR/LBS/SEC device Poke branch. Names must have an explicit non-white color; red is preferred and other colors are fallback. They are resolved TOP, then RIGHT, then GLOBAL within 200 units; database and ahref logic are unchanged.",
})

# v2.18.225 Poke Text ownership exclusivity and station/device color boundary.
EN.update({
    "独立生成/修复 RMU、AR/LBS/SEC 设备与站点跳转 Poke。": "Create/repair RMU, AR/LBS/SEC device, and station-jump Pokes.",
    "RMU Poke 继续复用公共 RMU 识别。AR/LBS/SEC 已独立为单独设备 Poke：先按服务器图元分类标记定位设备，名称 Text 必须有明确字体颜色，红色优先、其他非白色颜色兜底，白色禁止；位置仍按上方→右侧→全局优先级识别，距离不得超过 200。一个具体 Text 只能属于一种 Poke 角色：设备名称、RMU 名称、站点跳转名称互斥；已被某一角色占用后，其他角色不得再次使用。站点跳转名称 Text 禁止为红色且必须有明确彩色背景。名称识别完成后仍按原逻辑生成目标 ahref，facID 仍不是 Poke 前提。": "RMU Poke continues to reuse shared RMU recognition. AR/LBS/SEC is an independent device-Poke branch selected by server-symbol classifications: the name Text must have an explicit non-white color; red is preferred before other colored fallback labels, while location is resolved by TOP, then RIGHT, then GLOBAL, always within 200 units. One concrete Text can own only one Poke role—device name, RMU name, and station-jump name are mutually exclusive. Station-jump name Text must not be red and must have an explicit colored background. Target ahref generation remains unchanged and facID is still not a prerequisite.",
    "站点跳转强制规则：只识别站点 Text；Text 必须是字母+数字格式（如 ANS2-44，纯数字不接受），必须有彩色背景，并且名称 Text 本身不能是红色；已被 RMU 或 AR/LBS/SEC 设备名称占用的 Text 也不会再作为站点跳转名称。通过条件后执行原有 SUBSTATION.NAME → SUBAREA_ID → SUBCONTROLAREA.NAME 查询。若站点 Text 旁边 100 以内存在括号纯数字 （如 (35033)），将最近的一个环网柜名称作为 locateLabel；如果没有环网柜名，则使用站点间隔后缀备用规则 （如 RDS-09 → AH309）。括号数字不属于站点名。": "Mandatory station-jump rules: only station Text is considered; it must contain letters and digits (for example ANS2-44; pure numbers are rejected), have a colored background, and the name Text itself must not be red. A Text already owned by an RMU or AR/LBS/SEC device name cannot be reused as a station-jump name. Qualified labels then use the existing SUBSTATION.NAME -> SUBAREA_ID -> SUBCONTROLAREA.NAME lookup. A parenthesized number within 100 is used as locateLabel; when several qualify, the nearest one is used; otherwise the station-interval fallback is used (for example RDS-09 -> AH309).",
})

# v2.18.102 Symbol inventory + device comparison Excel.
EN.update({
    "G 图形内容解析": "G Graphic Content Analysis",
    "G 图形内容解析帮助": "G Graphic Content Analysis Help",
    "综合解析业务 G 文件中的设备、状态图元、量测/信号、图元引用及其他对象；已配置标准同时参与分类与校验。": "Analyze devices, status symbols, measurements/signals, symbol references, and other objects in business G files; configured standards also participate in classification and validation.",
    "开始解析": "Start Analysis",
    "打开分析结果 Excel": "Open Analysis Result Excel",
    "图形内容解析输出目录": "Graphic Content Analysis Output Directory",
    "G 图形内容解析输入": "G Graphic Content Analysis Input",
    "当前 ACTIVE 标准已锁定：图形 G 图元发现输入已隐藏。点击“解锁当前版本”后会自动恢复输入方式、SSH/本地文件选择及扫描操作。": "The current ACTIVE standard is locked, so Graphic G discovery input is hidden. Click Unlock Current Version to restore the input mode, SSH/local file selection, and scan controls.",
    "综合解析业务 G 文件中的设备、状态图元、量测/信号、图元引用及其他对象；已配置标准同时参与分类与校验": "Analyze devices, status symbols, measurements/signals, symbol references, and other objects in business G files; configured standards also participate in classification and validation",
    "本模块定位为“图形 G 内容解析”入口：设备只是其中一类。已配置标准的图元会按用途进入统一实例结果并执行标准校验；业务 G 中尚未定义的 devref 也会保留在“未定义图元”，用于后续继续识别、分类和复用。": "This module is the Graphic G content-analysis entry point. Devices are only one category. Configured standard symbols are grouped by usage and validated, while business-G devrefs not yet defined are retained under Undefined Symbols for later identification, classification, and reuse.",
    "选择一个需要分析图形内容的业务 G 文件。": "Select a business G file whose graphic content should be analyzed.",
    "选择包含多个业务 G 文件的目录；程序批量解析目录第一层中的 G 文件。": "Select a directory containing multiple business G files; G files in the first directory level are analyzed in batch.",
    "选择图形内容解析输出目录": "Select Graphic Content Analysis Output Directory",
    "请先执行一次图形内容解析。": "Run Graphic Content Analysis once first.",
    "G 图元与设备提取": "G Symbol & Device Inventory",
    "提取所有已配置标准图元实例，统计并校验标准；设备类额外导出设备对比 Excel": "Extract every configured standard-symbol instance, validate it, and export an additional device comparison Excel view for device classes.",
    "识别所有已配置标准图元，逐实例统计并校验；设备类额外输出可筛选的设备对比 Excel。": "Identify every configured standard symbol, count and validate every instance, and export a filterable device comparison Excel sheet for device classes.",
    "G 图元与设备提取帮助": "G Symbol & Device Inventory Help",
    "标准与分类": "Standards & Classification",
    "当前 ACTIVE 图元标准": "Current ACTIVE Symbol Standard",
    "图元分类来自标准库中的“图元用途 / 业务类型 / 设备子类型 / 设备层级”。标准图元全部参与校验；只有设备相关分类额外进入设备对比 Sheet。": "Classification comes from Symbol Usage / Business Type / Device Subtype / Device Level in the standard library. Every standard symbol is validated; device-related classes also appear in the Device Comparison sheet.",
    "提取并导出 Excel": "Extract & Export Excel",
    "打开设备对比 Excel": "Open Device Comparison Excel",
    "图元与设备提取输出目录": "Symbol & Device Inventory Output Directory",
    "业务类型 / 设备类型": "Business / Device Type",
    "图元定位规则": "Symbol Locator Rule",
    "图元用途": "Symbol Usage",
    "设备子类型": "Device Subtype",
    "设备层级": "Device Level",
    "设备组成图元": "Device Component Symbol",
    "状态图元": "Status Symbol",
    "标签/辅助图元": "Label / Auxiliary Symbol",
    "测量/信号": "Measurement / Signal",
    "Poke/跳转": "Poke / Jump",
    "其他": "Other",
    "独立设备": "Standalone Device",
    "组合设备": "Composite Device",
    "设备内部部件": "Device Internal Component",
    "辅助关联": "Auxiliary Association",
    "不计入设备": "Not Counted as Device",
    "添加自定义图元": "Add Custom Symbol",
    "删除选中自定义图元": "Delete Selected Custom Symbol",
})

# v2.18.104 Discovery-driven standard library: no pre-seeded fixed device roles.
EN.update({
    "为选中图元上传标准图元 G": "Upload Standard Symbol G for Selected Symbol",
    "为选中图元上传 / 更新标准 G": "Upload / Update Standard G for Selected Symbol",
    "手动添加图元（可选）": "Add Symbol Manually (Optional)",
    "删除选中图元": "Delete Selected Symbol",
    "图形 G 图元发现（只发现候选，不生成标准）": "Discover Symbols from Graphic G (Candidates Only; No Standards Generated)",
    "图形 G 图元发现输入": "Graphic G Symbol Discovery Input",
    "先选择图元候选": "Select a Symbol Candidate First",
    "请先扫描图形 G，并在表格中选中需要纳入标准管理的图元候选，然后上传对应的权威图元 G。": "Scan graphic G files first, select a candidate to manage as a standard, then upload its authoritative symbol G file.",
    "请先扫描图形 G 发现图元候选，并至少为 1 个需要管理的候选上传权威标准图元 G。": "Scan graphic G files to discover symbol candidates, then upload an authoritative standard symbol G for at least one candidate you want to manage.",
    "候选已自动分类；图元用途/设备类型可以人工修改。上传标准 G 后，w×h、AlignCenter、Pins 会自动从标准图元读取。": "Candidates are auto-classified; Symbol Usage and Device Type can be adjusted manually. After the standard G is uploaded, w×h, AlignCenter, and Pins are read from the authoritative symbol file.",
    "本表不再预置 LBS、Circuit Breaker、接地刀闸等固定系统角色。先扫描图形 G 自动发现实际使用的图元候选，用户只挑需要纳入标准管理的设备、状态或其他图元，再上传对应权威图元 G；上传后自动读取主体 ID、w×h、AlignCenter 与 Pins。图形 G 只用于发现候选和出现位置，不会反向生成这些标准参数。": "This table no longer pre-seeds fixed roles such as LBS, Circuit Breaker, or grounding switch. Scan graphic G files to discover the symbols actually used, select the device/status/other candidates you want to manage, then upload the corresponding authoritative symbol G. Body ID, w×h, AlignCenter, and Pins are derived only from that uploaded symbol G. Graphic G files provide discovery evidence and locations only; they never generate those standard parameters.",
})

# v2.18.105 Automatic learned locator + full scanned symbol-G filename.
EN.update({
    "扫描图元 G 文件全名": "Scanned Symbol G Full Filename",
    "图形 G 发现 devref": "Graphic-G Discovered devref",
    "发现次数": "Occurrences",
    "样本位置": "Sample Position",
    "定位规则与定位条件不再由用户指定。程序根据图形 G 扫描得到的 XML/devref 候选，以及随后上传的权威标准图元 G，自动计算内部定位关系。": "Locator rules and conditions are no longer user-configured. The program automatically derives the internal locator from the XML/devref candidate discovered in the graphic G and the authoritative standard symbol G uploaded afterward.",
    "扫描到的图元 G 文件名会完整显示，表格列宽按实际内容自动调整；内容较宽时使用水平滚动，不截断文件名。": "The full scanned symbol-G filename is displayed. Column widths automatically fit actual content; wide content uses horizontal scrolling instead of truncating filenames.",
})

# v2.18.106 Strict discovered-filename binding guard.
EN.update({
    "禁止上传：图元文件名不匹配": "Upload Blocked: Symbol Filename Mismatch",
    "当前候选是从业务/图形 G 自动扫描出来的，上传的标准图元 G 必须与扫描图元文件名一致。": "This candidate was discovered automatically from a business/graphic G file. The uploaded authoritative standard symbol G must use the same symbol filename as the discovered candidate.",
    "请重新选择与“扫描图元 G 文件全名”完全对应的标准图元 G。": "Select the authoritative standard symbol G whose filename exactly matches the Scanned Symbol G Full Filename.",
})

# v2.18.113 Read-only remote authoritative symbol library + incremental cache.
EN.update({
    "服务器标准图元库（只读自动同步）": "Server Standard Symbol Library (Read-only Auto Sync)",
    "自动从服务器图元库匹配标准 G（推荐）": "Automatically Match Standard G from Server Library (Recommended)",
    "图元库根目录": "Symbol Library Root",
    "检查 / 同步服务器图元库": "Check / Sync Server Symbol Library",
    "基于当前版本创建新版本": "Create New Version from Current Version",
    "无需创建新版本": "No New Version Needed",
    "没有可应用的服务器更新": "No Applicable Server Updates",
    "基于服务器更新创建新版本": "Create New Version from Server Updates",
    "创建新版本失败": "Failed to Create New Version",
    "新标准版本已创建": "New Standard Version Created",
    "打开本地缓存": "Open Local Cache",
    "服务器图元库同步 %p%": "Server Symbol Library Sync %p%",
    "服务器图元库尚未检查。扫描业务 G 后会按图元 G 文件全名自动查找、增量下载并解析；找不到或发生同名冲突时才需要人工处理。": "The server symbol library has not been checked yet. After business-G discovery, exact symbol-G filenames are located, incrementally downloaded and parsed automatically; manual handling is needed only for missing files or same-name conflicts.",
    "同步严格只读：仅递归列目录、读取 size/mtime、SFTP 下载匹配的 G 到本地缓存。未变化文件直接复用缓存；ACTIVE 已锁定时只提示服务器变化，不会改写已锁定标准。": "Synchronization is strictly read-only: recursively list directories, read size/mtime, and SFTP-download matching G files to the local cache. Unchanged files reuse the cache. When ACTIVE is locked, server changes are reported but never modify the locked standard.",
    "服务器图元库自动匹配已关闭；仍可使用人工上传标准 G。": "Automatic server-library matching is disabled; manual standard-G upload remains available.",
    "匹配 / 同步服务器标准图元 %p%": "Match / Sync Server Standard Symbols %p%",
    "服务器图元库": "Server Symbol Library",
    "待匹配/上传标准 G": "Awaiting Server Match / Upload",
    "READY · 服务器已同步": "READY · Server Synced",
    "当前还没有可匹配的图元文件名。请先扫描业务 G，或选择一个已有服务器标准版本。": "There are no symbol filenames to match yet. Scan business G files first or select an existing server-backed standard version.",
    "正在后台递归检查服务器图元库并增量同步匹配文件……界面仍可操作。": "Checking the server symbol library recursively and incrementally syncing matches in the background; the UI remains responsive.",
    "服务器图元库同步失败": "Server Symbol Library Sync Failed",
    "服务器图元库配置无效": "Invalid Server Symbol Library Configuration",
    "打开缓存失败": "Open Cache Failed",
    "优先从只读服务器图元库自动匹配并缓存权威图元 G，服务器未找到时再人工上传；随后检查业务 G 是否符合当前 ACTIVE 标准。": "Prefer automatic matching and caching of authoritative symbol G files from the read-only server library, falling back to manual upload only when missing; then validate business G files against the current ACTIVE standard.",
})

# v2.18.117 Fresh business-G rescan into isolated next-version DRAFT.
EN.update({
    "重新扫描并创建新版本": "Rescan and Create New Version",
    "取消新版本草稿": "Cancel New-Version Draft",
    "重新扫描 / 更新当前新版本草稿": "Rescan / Update Current New-Version Draft",
    "保存为新版本": "Save as New Version",
    "请选择当前 ACTIVE 标准": "Select the Current ACTIVE Standard",
    "重新扫描并创建新版本": "Rescan and Create New Version",
    "取消新版本草稿": "Cancel New-Version Draft",
    "需要重新学习现场最新 G 时使用：重新扫描 → V(N+1) DRAFT → 调整/补标准 → 保存为新版本。": "Use this when the latest site G files must be relearned: rescan → V(N+1) DRAFT → adjust/fill standards → save as a new version.",
})

# v2.18.119 Make the fresh-rescan workflow visible beside the ordinary scan and one-click.
EN.update({
    "全量重新扫描 → 新版本草稿": "Full Rescan → New-Version Draft",
    "扫描当前版本候选": "Scan Current-Version Candidates",
    "普通“扫描当前版本候选”不会创建新版本；需要让最新业务 G 重新决定候选集合时，请使用“全量重新扫描 → 新版本草稿”。": "A normal current-version candidate scan does not create a new version. To let the latest business G files redefine the candidate set, use Full Rescan → New-Version Draft.",
})

# v2.18.121 Compact Symbol Standard Check copy + last business-module restore.
EN.update({
    "维护图元标准版本并检查业务 G；详细规则请查看“页面帮助”。": "Maintain symbol-standard versions and validate business G files. See Page Help for detailed rules.",
    "业务 G 只用于发现和检查；标准 G 来自只读服务器或人工上传。正式版本会冻结到本地版本库，源 G 不覆盖。": "Business G files are used only for discovery and validation. Standard G files come from the read-only server or manual upload. Formal versions are frozen locally and source G files are never overwritten.",
    "流程：扫描候选 → 匹配/上传标准 G → 确认分类 → 保存版本。": "Flow: scan candidates → match/upload standard G → confirm classification → save version.",
    "GLOBAL 仅手动切换；保存新的 ACTIVE 不会改变全局版本。": "GLOBAL changes only when you select it manually; saving a new ACTIVE version does not change GLOBAL.",
    "历史版本和图元文件冻结在本地版本库，软件升级不会自动清理；可在“标准管理”中验证、恢复或导出。": "Historical versions and symbol files are frozen in the local repository and are not automatically cleared during upgrades; verify, restore, or export them from Standard Management.",
    "w×h、AlignCenter、Pins 只从标准 G 读取；业务 G 仅提供候选和使用位置。": "w×h, AlignCenter, and Pins are read only from standard G files; business G provides candidates and usage locations only.",
    "尚未检查服务器图元库。扫描候选后可自动匹配标准 G。": "The server symbol library has not been checked yet. Standard G files can be matched automatically after candidate scanning.",
    "服务器严格只读；匹配文件仅下载到本地缓存，不会修改服务器。": "The server is strictly read-only; matched files are downloaded only to local cache and the server is never modified.",
    "选择业务 G 后扫描候选；需要重新建立下一版本时使用“全量重新扫描 → 新版本草稿”。": "Select business G files and scan candidates. Use Full Rescan → New-Version Draft to rebuild the next version.",
    "普通扫描更新当前候选；全量重扫创建下一版本草稿。": "A normal scan updates current candidates; a full rescan creates the next-version draft.",
    "选择待检查业务 G；源文件只读，结果写入 workspace。": "Select business G files to validate. Sources are read-only and results are written to the workspace.",
    "检查只读；纠正仅生成 workspace 副本，不覆盖源 G。": "Validation is read-only; correction creates workspace copies and never overwrites source G files.",
})

# v2.18.122 Full G content/device inventory + HTML report.
EN.update({
    "全量解析业务 G：设备、图元、文本、量测/信号、Poke、连接/拓扑与 XML 结构，并输出 Excel + HTML。": "Fully analyze business G files: devices, symbols, text, measurements/signals, Poke, connectivity/topology, and XML structure, with Excel + HTML output.",
    "使用当前 GLOBAL 图元标准识别并校验全部业务 G 内容；RMU、变压器及其他设备统一汇总，同时输出完整 XML/对象结构清单。": "Use the current GLOBAL symbol standard to identify and validate all business-G content; RMUs, transformers, and other devices are summarized together, with a complete XML/object structure inventory.",
    "设备与图元分类以 GLOBAL 标准为准；全部 XML 对象仍会进入完整内容清单，不因未配置标准而丢失。": "Device and symbol classifications follow the GLOBAL standard; every XML object is still retained in the full content inventory even when it is not configured as a standard.",
    "打开详细 Excel": "Open Detailed Excel",
    "打开 HTML 报告": "Open HTML Report",
    "暂无 HTML 报告": "No HTML Report",
    "全量设备/内容报告": "Full Device / Content Report",
})

# v2.18.123 Separate semantic standards and geometry repair.
EN.update({
    "图元标准检查": "Symbol Standard Check",
    "只检查服务器标准图元与业务 G 的标准一致性；纠正仅生成 workspace 标准纠正副本，不负责全图拓扑或线路重画": "Check server standard symbols against business G; correction only creates workspace copies and does not analyze global topology or redraw lines",
    "标准一致性检查与纠正": "Standard Consistency Check & Correction",
    "生成标准纠正副本": "Create Standard-Corrected Copy",
    "进入线路正交化": "Open Line Orthogonalization",
    "线路与拓扑保持不变": "Lines and topology remain unchanged",
    "服务器标准图元（只读）": "Server Standard Symbols (Read-only)",
    "待服务器匹配": "Awaiting Server Match",
    "缺少服务器标准图元": "Server Standard Symbol Missing",
})

# v4.2.13 merged-DMM English audit.  The standalone GFileStudio pages keep their
# Chinese source text internally, but when embedded in DMM every dynamic remote-
# source/status label must render in the active English language as well.
EN.update({
    "共享连接配置": "Shared Connection Settings",
    "共享连接配置（只读）": "Shared Connection Settings (Read-only)",
    "严格只读": "Strictly Read-only",
    "已从本机缓存恢复": "Restored from Local Cache",
    "不会自动访问服务器。": "The server is not contacted automatically.",
    "缓存时间": "Cache Time",
})
RUNTIME_REPLACEMENTS = tuple(sorted((*RUNTIME_REPLACEMENTS,
    ("共享连接配置", "Shared Connection Settings"),
    ("文件服务器：", "File Server: "),
    ("用户 ", "User "),
    ("严格只读", "Strictly Read-only"),
    ("业务 G 根目录：", "Business G Root: "),
    ("已从本机缓存恢复 ", "Restored "),
    (" 个服务器 G 文件；不会自动访问服务器。", " server G files from local cache; the server was not contacted automatically."),
    (" 缓存时间：", " Cache time: "),
    ("本地缓存 ", "Local cache: "),
    (" 个文件", " files"),
    ("刷新 G 文件列表", "Refresh G File List"),
    ("下载所选到本地…", "Download Selected Locally…"),
    ("文件服务器", "File Server"),
    ("业务 G 根目录", "Business G Root"),
), key=lambda item: len(item[0]), reverse=True))

# v4.2.18 Jeddah whole-graph feeder topology page.
EN.update({
    "整图馈线拓扑分析": "Whole-Graph Feeder Topology Analysis",
    "整图馈线拓扑分析帮助": "Whole-Graph Feeder Topology Analysis Help",
    "完整复用麦加整图馈线拓扑分析逻辑；吉达仅增加‘Bus 上方馈线名’主网源识别和红色背景 NOP 识别。": "Reuse the Makkah whole-graph feeder topology logic in full; Jeddah only adds main-source recognition from the feeder name above Bus and red-background NOP recognition.",
    "纯图形分析：不连接 Oracle、不修改模型库。原始 G 永不覆盖。主网没有外框时从 Bus 上方唯一名称确定馈线；NOP 支持麦加红字和吉达红色椭圆背景两种表现。": "Graphics-only analysis: no Oracle connection and no model-database modification. Source G files are never overwritten. When the main network has no frame, the feeder is taken from the unique name above Bus; NOP supports both Makkah red text and the Jeddah red-ellipse presentation.",
    "整图拓扑分析规则（麦加逻辑完全复用）": "Whole-Graph Topology Rules (Makkah Logic Reused in Full)",
    "开始整图馈线拓扑分析 / 自动修复": "Start Whole-Graph Feeder Topology Analysis / Auto Repair",
    "打开整图拓扑报告": "Open Whole-Graph Topology Report",
    "整图馈线拓扑分析输入": "Whole-Graph Feeder Topology Input",
    "整图馈线拓扑分析输出目录": "Whole-Graph Feeder Topology Output Directory",
    "选择一张需要执行整图馈线拓扑分析的 G 文件；一次只处理 1 张。": "Select one G file for whole-graph feeder topology analysis; exactly one file is processed per run.",
    "兼容目录/SSH 快照输入，但目录中必须只有 1 个待分析 G 文件。": "Directory/SSH snapshot input is supported, but it must contain exactly one G file to analyze.",
    "✓ 1. 一次只分析 1 个 G 文件；分析 FeedLine、ConnectLine、Bus/BusDis、开关、Pole、变压器及其它有 link/node_area 的电气对象。": "✓ 1. Analyze exactly one G file per run: FeedLine, ConnectLine, Bus/BusDis, switches, Pole, transformers, and other electrical objects carrying link/node_area.",
    "✓ 2. 主网馈线源：有麦加 Bay/CBreaker 框时仍按原麦加规则；吉达主网无框时，使用 Bus 正上方唯一的馈线名称 Text（例如 AH303）作为权威源。": "✓ 2. Main-network feeder source: keep the original Makkah Bay/CBreaker rule when a frame exists; for Jeddah drawings without a frame, use the unique feeder-name Text directly above Bus (for example AH303) as the authoritative source.",
    "✓ 3. 电气连接完全复用麦加：优先 link/node_area；严格几何补链继续使用端点≤3G、端点到线段≤2G。": "✓ 3. Electrical connectivity fully reuses Makkah: prefer link/node_area; strict geometry completion keeps endpoint ≤3G and endpoint-to-segment ≤2G.",
    "✓ 4. NOP 边界完全复用麦加 Y*/Q*/柱上开关判定；仅扩展外观识别：红色 N.O.P Text 或被红色椭圆/红色背景包住的 N.O.P Text 都算 NOP。": "✓ 4. NOP boundary selection fully reuses the Makkah Y*/Q*/pole-switch rules; only visual recognition is extended: red N.O.P Text or N.O.P Text contained by a red ellipse/background is accepted.",
    "✓ 5. RMU NOP 仍映射到所属 RMU 内唯一 Y*/Q* 开关作为端口级硬边界；未归属 RMU 的 NOP 仍按最近外部开关处理。": "✓ 5. RMU NOP still maps to the unique Y*/Q* switch in its RMU as a port-level hard boundary; NOP not owned by an RMU still maps to the nearest external switch.",
    "✓ 6. 传播完全复用麦加：只从唯一馈线源沿真实拓扑传播，遇 NOP 开关停止当前路径，其它分支继续；NOP 开关本身不分配馈线。": "✓ 6. Propagation fully reuses Makkah: propagate only from unique feeder sources along real topology, stop the current path at an NOP switch while other branches continue, and do not assign a feeder to the NOP switch itself.",
    "✓ 7. NOP 两侧必须各自得到唯一馈线源：0 个=NO_SOURCE_ERROR，多个=MULTI_SOURCE_ERROR，唯一一个才确认。": "✓ 7. Each NOP side must resolve to exactly one feeder source: 0 = NO_SOURCE_ERROR, multiple = MULTI_SOURCE_ERROR, exactly one = confirmed.",
    "✓ 8. 非 NOP 设备必须且只能属于 1 条馈线：0 条=NO_FEEDER_ERROR，多条=MULTI_FEEDER_ERROR。": "✓ 8. Every non-NOP device must belong to exactly one feeder: 0 = NO_FEEDER_ERROR, multiple = MULTI_FEEDER_ERROR.",
    "✓ 9. RMU 所属馈线继续按麦加同柜 Y*/Q* 规则汇总；NOP 端口只作为边界，不参与多数投票。": "✓ 9. RMU feeder ownership continues to use the Makkah same-cabinet Y*/Q* rules; NOP ports are boundaries only and never participate in majority voting.",
    "✓ 10. 3G~4.5G 微小断点只有在双方唯一近邻、模拟后错误减少且不新增多馈线冲突时才自动修复；原始 G 永不覆盖。": "✓ 10. A 3G–4.5G micro-gap is auto-repaired only when both endpoints are reciprocal unique neighbors and simulation reduces errors without creating a multi-feeder conflict; the source G is never overwritten.",
})


# v4.2.19 Jeddah connectivity-only topology repair page.
EN.update({
    "整图拓扑连接检查/修复": "Whole-Graph Topology Connection Check / Repair",
    "整图拓扑连接检查/修复帮助": "Whole-Graph Topology Connection Check / Repair Help",
    "吉达只检查 G 图连接是否断开并自动修复；不判断馈线、不识别 NOP、不读取 Bus 馈线名、不查数据库。": "Jeddah checks only whether G-file topology connections are broken and repairs them automatically; it does not determine feeder ownership, identify NOP, read Bus feeder names, or query a database.",
    "纯 G 图连接检查：不判断馈线、不识别 NOP、不读取 Bus 名称、不连接 Oracle/数据库。发现双方互为唯一近邻的小断点后直接修复到新的安全副本，原始 G 永不覆盖。": "Pure G-file connection check: no feeder ownership, NOP recognition, Bus-name reading, Oracle, or database access. Small breaks are repaired only when both endpoints are unique nearest neighbors, and the source G is never overwritten.",
    "整图拓扑连接检查输出目录": "Whole-Graph Topology Connection Output Directory",
    "选择一张需要检查/修复拓扑连接的 G 文件；一次只处理 1 张。": "Select one G file whose topology connections should be checked/repaired; one file is processed per run.",
    "兼容目录/SSH 快照输入，但目录中必须只有 1 个待检查 G 文件。": "Directory/SSH snapshot input is supported, but it must contain exactly one G file to check.",
    "吉达整图拓扑连接检查/修复规则": "Jeddah Whole-Graph Topology Connection Check / Repair Rules",
    "开始整图拓扑检查 / 自动修复": "Start Whole-Graph Topology Check / Auto Repair",
    "打开拓扑连接报告": "Open Topology Connection Report",
    "整图拓扑连接检查输入": "Whole-Graph Topology Connection Input",
    "线路对象": "Line Objects",
    "原始无引用端点（含正常符号开口）": "Raw Unreferenced Endpoints (Including Normal Symbol Openings)",
    "断点候选": "Break Candidates",
    "自动修复": "Auto Repairs",
    "几何修复": "Geometry Repairs",
    "新增拓扑引用 token": "Topology Reference Tokens Added",
    "修复后剩余唯一断点": "Remaining Unique Breaks After Repair",
    "耗时（秒）": "Elapsed (s)",
    "修复后 G": "Repaired G",
    "✓ 1. 一次只检查 1 个 G 文件；只读取 G XML 自身，不连接 Oracle、不查模型库。": "✓ 1. Check exactly one G file per run; read only the G XML itself, with no Oracle or model-database access.",
    "✓ 2. 不判断馈线归属，不找主网馈线名，不读取 Bus 上方名称；整张图没有任何馈线传播过程。": "✓ 2. Do not determine feeder ownership, search for main-network feeder names, or read names above Bus; no feeder propagation is performed anywhere in the drawing.",
    "✓ 3. 不识别 NOP、不设置 NOP 边界；这里只关心线路物理/拓扑连接有没有断开。": "✓ 3. Do not identify NOP or create NOP boundaries; this function only checks whether physical/topological line connections are broken.",
    "✓ 4. 重点检查 ConnectLine ↔ FeedLine 的端点连接，同时处理 ≤3G 的同轴 ConnectLine ↔ ConnectLine 微小断口；检查几何坐标和 link/node_area 是否完整。": "✓ 4. Focus on ConnectLine ↔ FeedLine endpoint connections and also handle collinear ConnectLine ↔ ConnectLine micro-gaps ≤3G; validate both geometry and link/node_area completeness.",
    "✓ 5. 只有待修复端点没有现有连接、线路另一端已经接入真实拓扑时，才把它作为断点候选，避免把装饰线或自由线段误连。": "✓ 5. Treat an endpoint as a repair candidate only when that endpoint has no current connection and the opposite end already belongs to real topology, avoiding accidental links to decorative/free line fragments.",
    "✓ 6. ConnectLine ↔ FeedLine 自动修复要求互为唯一最近邻且距离 ≤25G；ConnectLine ↔ ConnectLine 仅允许 ≤3G 且同轴，约 18G 的开关正常触点断口绝不连接。": "✓ 6. ConnectLine ↔ FeedLine repair requires reciprocal unique nearest neighbors within 25G; ConnectLine ↔ ConnectLine is limited to collinear gaps ≤3G, so normal switch-contact gaps around 18G are never bridged.",
    "✓ 7. 有可见几何断口时优先正交延伸 FeedLine 到 ConnectLine；坐标已重合但 link/node_area 缺失时只补拓扑引用。": "✓ 7. For visible gaps, orthogonally extend FeedLine to ConnectLine first; if coordinates already coincide and only link/node_area is missing, add topology references only.",
    "✓ 8. 修复后再次扫描；所有已自动修复的端点都必须从断点候选中消失。原始 G 永不覆盖。": "✓ 8. Scan again after repair; every automatically repaired endpoint must disappear from the break candidates. The source G is never overwritten.",
    "✓ 9. 输出仅保留精简 HTML/CSV 和修复后的 G，不再生成馈线传播、NOP、RMU 归属等大报告，因此大图解析会明显更快。": "✓ 9. Output only compact HTML/CSV plus the repaired G; large feeder-propagation/NOP/RMU ownership reports are no longer generated, making large drawings much faster.",
})

# v4.2.21 Jeddah batch visual topology reports.
EN.update({
    "选择一张需要检查/修复拓扑连接的 G 文件。": "Select one G file whose topology connections should be checked/repaired.",
    "选择包含一个或多个 G 文件的目录；将逐个独立检查/修复，并生成单文件报告和总汇总报告。": "Select a directory containing one or more G files; each file is checked/repaired independently with per-file reports plus a total summary.",
    "✓ 1. 支持单个 G 或批量目录/SSH 快照；多个 G 按文件逐个独立处理，只读取 G XML 自身，不连接 Oracle、不查模型库。": "✓ 1. Supports a single G or a batch directory/SSH snapshot; multiple G files are processed independently using only their G XML, with no Oracle or model-database access.",
    "✓ 9. 每个 G 都输出独立 HTML/CSV、修复前完整 G 图、修复后完整 G 图和可选修复后 G；两张图必须按 G 原始坐标和图元内容重绘，修复前图再直接标出问题位置。批量时额外生成总 HTML/CSV 汇总，某个文件失败会记录后继续。": "✓ 9. Every G produces independent HTML/CSV, a complete before-G view, a complete after-G view, and an optional repaired G. Both views are redrawn from the G source coordinates and visible objects; the before view then overlays the problem locations. Batch runs also produce a total HTML/CSV summary, and a failed file is recorded while processing continues.",
    "开始整图拓扑检查 / 批量自动修复": "Start Whole-Graph Topology Check / Batch Auto Repair",
    "打开汇总/拓扑报告": "Open Summary / Topology Report",
    "请先执行一次整图拓扑连接检查/修复。批量模式完成后会打开总汇总报告。": "Run the whole-graph topology connection check/repair first. In batch mode the total summary report will be opened after completion.",
})
