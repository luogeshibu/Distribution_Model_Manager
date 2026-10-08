from __future__ import annotations

import re

LANG_ZH = "zh_CN"
LANG_EN = "en_US"

# Exact UI translations. The Chinese source text remains the canonical key so
# business code does not need language branches sprinkled throughout the app.
ZH_TO_EN = {
    "NARI国际业务部内部工具": "NARI International Business Internal Tool",
    "模型校验": "Model Validation",
    "校验候选": "Validated Candidates",
    "安全回写": "Safe Write-back",
    "数据库": "Database",
    "模型工作区": "Model Workspace",
    "运行历史": "Run History",
    "设置": "Settings",
    "帮助": "Help",
    "Oracle 数据库连接": "Oracle Database Connection",
    "用户名": "Username",
    "密码": "Password",
    "服务器地址": "Server Address",
    "端口": "Port",
    "测试数据库连接": "Test Database Connection",
    "保存数据库配置": "Save Database Settings",
    "尚未验证": "Not validated",
    "数据库运行日志": "Database Runtime Log",
    "复制日志": "Copy Log",
    "清空日志": "Clear Log",
    "模型任务": "Model Task",
    "批量模型关联（可选）": "Batch Model Association (Optional)",
    "批量关联": "Batch Association",
    "批量输入来源": "Batch Input Source",
    "设置文件来源": "Set File Source",
    "批量模型关联": "Batch Model Association",
    "批量任务进度": "Batch Task Progress",
    "等待执行批量任务": "Waiting for batch task",
    "批量任务 Console 日志": "Batch Task Console Log",
    "打开批量汇总 HTML": "Open Batch Summary HTML",
    "打开批量汇总 CSV": "Open Batch Summary CSV",
    "批量校验": "Batch Validation",
    "执行批量关联": "Apply Batch Association",
    "先检查所选模块，生成本次批量关联计划": "Validate selected modules and build the batch association plan",
    "执行已经通过批量校验的安全关联计划": "Apply the safe association plan that passed batch validation",
    "尚未执行批量校验": "Batch validation not run",
    "RMU 环网柜": "RMU",
    "柱上开关": "Pole Switch",
    "柱上变压器": "Pole Transformer",
    "熔断器": "Fuse",
    "馈线": "Feeder",
    "配网主站设备": "Master-station Devices",
    "打开批量校验汇总 HTML": "Open Batch Validation Summary HTML",
    "打开批量校验汇总 CSV": "Open Batch Validation Summary CSV",
    "打开批量关联汇总 HTML": "Open Batch Association Summary HTML",
    "打开批量关联汇总 CSV": "Open Batch Association Summary CSV",
    "模型类型": "Model Type",
    "当前模型帮助": "Current Model Help",
    "文件来源（RMU / 馈线通用）": "File Source (shared by RMU / Feeder)",
    "本地文件 / 目录": "Local File / Folder",
    "SSH 文件服务器（只读）": "SSH File Server (Read-only)",
    "G 文件 / 目录": "G File / Folder",
    "选择文件": "Select File",
    "选择目录": "Select Folder",
    "测试 SSH 连接": "Test SSH Connection",
    "保存 SSH 配置": "Save SSH Settings",
    "刷新 G 文件列表": "Refresh G File List",
    "下载所选 G 文件": "Download Selected G Files",
    "搜索 G 文件": "Search G Files",
    "尚未加载远程文件": "Remote files not loaded",
    "全选当前结果": "Select Visible Results",
    "清空选择和搜索": "Clear Selection & Search",
    "执行前需要进行 Oracle 预检查。": "Oracle pre-check is required before execution.",
    "Workspace": "Workspace",
    "打开 Workspace": "Open Workspace",
    "任务进度": "Task Progress",
    "等待执行任务": "Waiting for task",
    "本次运行 Console 日志": "Current Run Console Log",
    "打开 HTML": "Open HTML",
    "打开环网柜 CSV": "Open RMU CSV",
    "打开设备 CSV": "Open Device CSV",
    "打开修改记录 CSV": "Open Change Log CSV",
    "打开本次运行目录": "Open Current Run Directory",
    "执行模型关联": "Apply Model Association",
    "数据库设置": "Database Settings",
    "刷新": "Refresh",
    "打开运行目录": "Open Run Directory",
    "安全策略": "Safety Policy",
    "快速使用": "Quick Start",
    "环网柜名称识别规则": "RMU Name Resolution Rules",
    "设备名称判断规则": "Device Naming Rules",
    "数据库强制校验": "Mandatory Database Validation",
    "状态颜色说明": "Status Legend",
    "模型关联与 G 文件回写": "Model Association and G-file Write-back",
    "报告说明": "Report Guide",
    "馈线模型规则": "Feeder Model Rules",
    "注意事项": "Notes",
    "关于 / 版本信息": "About / Version",
    "RMU 环网柜模型": "RMU Model",
    "馈线模型": "Feeder Model",
    "RMU 环网柜识别": "RMU Recognition",
    "环网柜名称排除字符串": "RMU Name Exclusion Strings",
    "例如：N.O.P, NOP, SFI, DAS/OK": "Example: N.O.P, NOP, SFI, DAS/OK",
    "上方": "Top",
    "右侧": "Right",
    "左侧": "Left",
    "下方": "Bottom",
    "开关名称来源": "Breaker Name Source",
    "环网柜内图上文字（固定）": "Graphical Text Inside RMU (Fixed)",
    "RMU 设备数据库表与域配置": "RMU Device Table / Domain Settings",
    "RMU 设备数据库定义（固定）": "RMU Device Database Definitions (Fixed)",
    "以下表号和域号由吉达项目模型规则固定，程序关联时强制使用，用户不可修改。": "The table IDs and domains below are fixed by the Jeddah project model rules. Association always uses these definitions and users cannot edit them.",
    "G 图元类型": "G Object Type",
    "表号（Table ID）": "Table ID",
    "域号（Domain）": "Domain",
    "固定表号（Table ID）": "Fixed Table ID",
    "固定域号（Domain）": "Fixed Domain",
    "EFI 固定规则：图元管理分类标记=RMU_PWBH_EFI；数据库表=13533 / dms_relay_sig；CODE=EFI INDICATOR；Domain=40；回写使用 value 域 keyid1。以上规则不可编辑。": "Fixed EFI rule: element classification=RMU_PWBH_EFI; database table=13533 / dms_relay_sig; CODE=EFI INDICATOR; Domain=40; write-back uses value.keyid1. These rules are read-only.",
    "恢复 RMU 默认配置": "Restore RMU Defaults",
    "馈线识别与数据库补齐": "Feeder Resolution and Database Completion",
    "馈线自动识别与数据库补齐": "Automatic Feeder Resolution and Database Completion",
    "馈线识别方式与柱上开关、柱上变压器保持一致：都采用“目标图元 + 最近有效 Text + 数据库唯一匹配”。馈线模块识别本图的源侧 CBreaker，在 400 范围内按设备矩形框与 Text 矩形框的最小边缘距离选择最近 Text，并沿用现有名称格式、颜色和背景规则，再用该图上名称唯一查询 13500 / dms_feeder_device。文件名、G 根 facID 和人工选择均不参与馈线识别；无法唯一匹配时直接阻断关联。": "Feeder recognition follows the same pattern as Pole Switch and Pole Transformer: target graphic object + nearest eligible Text + unique database match. The feeder module uses the source CBreaker, selects the nearest Text within 400 drawing units by minimum rectangle edge-to-edge distance using the current name-format, color, and background rules; center-point distance is not used, then uniquely queries 13500 / dms_feeder_device with that graphical name. File name, G-root facID, and manual selection are not feeder-resolution inputs; non-unique resolution blocks association.",
    "自动识别流程：源侧 CBreaker → 按矩形最小边缘距离选择最近有效 Text → 13500 唯一匹配 → FEEDER_ID。这里沿用柱上开关/柱上变压器的图元邻近名称识别方式，但不会读取它们的 feeder_id 来反推馈线。文件名、根 facID 和人工输入不参与馈线识别。": "Automatic resolution: source CBreaker -> nearest eligible Text by rectangle minimum-edge distance -> unique 13500 match -> FEEDER_ID. This reuses the graphical nearest-name recognition pattern of Pole Switch / Pole Transformer, but does not infer the feeder from their feeder_id values. File name, root facID, and manual input do not participate in feeder resolution.",
    "安全边界：图纸类型仍按原有规则决定是否允许执行馈线段关联；馈线识别来源只改为图内设备数据库归属，13503 分配、缺失段创建、KeyID 校验和安全副本回写规则保持不变。": "Safety boundary: drawing type still uses the existing rules to decide whether feeder-section association is allowed. Only the feeder-resolution source changes to device database ownership; 13503 allocation, missing-section creation, KeyID verification, and safe-copy write-back remain unchanged.",
    "馈线识别方式": "Feeder Resolution Mode",
    "仅使用 G 根节点 facID（默认）": "Use G Root facID Only (Default)",
    "仅使用文件名": "Use File Name Only",
    "仅使用人工输入": "Use Manual Input Only",
    "人工馈线名称": "Manual Feeder Name",
    "人工目标馈线（变电站 + 馈线）": "Manual Target Feeder (Substation + Feeder)",
    "变电站标识（文件名模式，可选）": "Substation Identifier (File-name Mode, Optional)",
    "批量变电站名称（文件名模式，可选）": "Batch Substation Name (File-name Mode, Optional)",
    "例如：ABH；也支持 JED-NTH-ABH；留空则从每个文件名自动识别": "Example: ABH; JED-NTH-ABH is also supported; leave blank to auto-detect from each file name",
    "例如：ABH AH303 或 AJWD 43": "Example: ABH AH303 or AJWD 43",
    "例如：ABH 或 JED-NTH-ABH；留空则从每个文件名自动识别": "Example: ABH or JED-NTH-ABH; leave blank to auto-detect from each file name",
    "允许覆盖现有 facID 和馈线段关联": "Allow overriding existing facID and feeder-section associations",
    "馈线段数据库表与域配置": "Feeder Section Table / Domain Settings",
    "用途": "Purpose",
    "语言": "Language",
    "团队内部版": "Internal Team Edition",
    "简体中文": "Simplified Chinese",
    "英文": "English",
    "语言设置": "Language Settings",
    "应用语言": "Application Language",
    "语言切换立即生效，并自动保存最后一次选择。": "Language changes take effect immediately and the last selection is saved automatically.",
    "环网柜名称筛选": "RMU Name Filter",
    "清除筛选": "Clear Filter",
    "已选择 0 个设备": "0 devices selected",
    "全选可关联": "Select All Eligible",
    "清空选择": "Clear Selection",
    "可关联对象（模型校验后生成；仅勾选项会执行回写）": "Eligible Objects (generated after validation; only selected rows are written back)",
}

# Longer static descriptions that matter in daily operation.
ZH_TO_EN.update({
    "Oracle 数据库作为独立公共模块。数据库测试日志只显示在本模块中。": "Oracle is a shared standalone module. Database test logs are shown only on this page.",
    "模型配置、处理进度和 Console 运行日志集中在当前工作区；任务完成后自动生成 HTML / CSV 报告。": "Model settings, progress, and Console logs are centralized in this workspace. HTML / CSV reports are generated automatically when a task completes.",
    "团队内部版的公共安全策略和报告保留策略。": "Common safety policies and report retention settings for the internal team edition.",
    "团队内部使用说明：RMU 与馈线模型校验、校验候选、报告和安全回写。": "Internal user guide for RMU and feeder validation, validated candidates, reports, and safe write-back.",
    "RMU 环网柜只有在矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 时才识别。开关设备名称固定使用环网柜内图上文字；环网柜名称默认读取矩形框上方，也可以多选右侧、左侧或下方，多选时只保留最近的一个 Text。设备命名规则不读取三类设备 XML 的 p_NameString：CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。": "An RMU is recognized only when its rectangle contains CBreakerDis, BusDis, and ZhaiWaiJieDiDaoZha. Device naming uses graphical text inside the RMU. The default RMU-name direction is above the rectangle; other directions may be selected too, and multiple selected directions still keep only the nearest Text. XML p_NameString is not used for these three device types.",
    "馈线识别来源相互独立：可按 G 根节点 facID、文件名或人工输入确定本次目标馈线。已有 facID 只作为当前关联状态，不再强制覆盖用户选择。文件名模式同时支持单文件和批量目录；例如 JED-NTH-ABH-03 可在 ABH 站内唯一解析到 AH303，JED-NTH-ABH-AH303 则直接使用完整馈线号。目标必须在 13500 / dms_feeder_device 中唯一。": "Feeder identification sources are independent: use the G-root facID, file name, or manual input to determine the target feeder for this run. An existing facID is current-association state only and no longer overrides the selected source. File-name mode supports both a single file and batch folders; for example, JED-NTH-ABH-03 can uniquely resolve to AH303 within substation ABH, while JED-NTH-ABH-AH303 uses the complete feeder code directly. The target must be unique in 13500 / dms_feeder_device.",
})

# v4.1.43 unified feeder ownership wording.
ZH_TO_EN.update({
    "馈线统一按图内设备顺序自动识别：先逐个检查环网柜，只要某个环网柜名称在 13501 唯一匹配并取得有效 FEEDER_ID 就立即采用；所有环网柜都无法唯一判定时，再逐个检查柱上开关（13501）；仍无法判定时最后逐个检查柱上变压器（13505）。文件名、G 根 facID、源侧 CBreaker 名称和人工选择均不参与馈线识别。": "Feeder resolution follows RMU -> Pole Switch -> Pole Transformer priority. Devices are checked one by one; the first unique database match with a valid FEEDER_ID wins. If every device in one family is non-unique or unusable, resolution falls through to the next family. File name, G-root facID, source-CBreaker text, and manual selection are not feeder-identification inputs.",
    "自动识别流程：逐个环网柜（13501）→ 首个唯一匹配即采用；若全部不唯一/无法使用，再逐个柱上开关（13501）→ 首个唯一匹配即采用；仍失败再逐个柱上变压器（13505）→ 首个唯一匹配即采用 → 读取 FEEDER_ID → 13500。": "Automatic resolution: try RMUs one by one against 13501 and use the first unique valid match; if all RMUs fail, try Pole Switches the same way against 13501; if those also fail, try Pole Transformers against 13505; then confirm FEEDER_ID in 13500.",
    "AUTO 使用 G 文件电气拓扑自动判断。强制单馈线/组合图只改变本次图纸类型判定；目标 FEEDER_ID 按 环网柜 → 柱上开关 → 柱上变压器 顺序逐个尝试，首个数据库唯一匹配设备直接确定。": "AUTO determines the drawing type from G-file topology. Force Single/Composite only changes drawing classification; target FEEDER_ID is resolved by trying RMU -> Pole Switch -> Pole Transformer one by one and using the first unique database match.",
    "馈线模型校验、数据库缺失馈线段补齐及安全回写。目标馈线按 环网柜 → 柱上开关 → 柱上变压器 顺序逐个尝试；每类设备中首个数据库唯一匹配且带有效 FEEDER_ID 的设备立即作为判定依据，整类失败才继续下一类。文件名、G 根 facID、源侧 CBreaker 名称和人工输入均不作为馈线识别来源；其余馈线段逻辑保持不变。": "Feeder model validation, completion of missing feeder sections, and safe write-back. The target feeder is resolved by trying RMU, Pole Switch, then Pole Transformer devices one by one; the first unique database match with a valid FEEDER_ID wins, and only a whole-family failure falls through to the next family. File name, G-root facID, source-CBreaker text, and manual input are not feeder-resolution inputs; all other feeder-section logic remains unchanged.",
})

# v4.1.100 strict Jeddah filename feeder fallback wording.
ZH_TO_EN.update({
    "馈线模型校验、数据库缺失馈线段补齐及安全回写。目标馈线唯一按吉达 G 文件名识别：普通 NN 文件名生成 AH3NN；新增 AGNN 文件名生成 AG4NN；均先按 405/substation.NAME 精确找站，再按 13500/dms_feeder_device.ST_ID + NAME 精确唯一确认。环网柜、柱上开关、柱上变压器、G 根 facID、源侧 CBreaker 名称和人工输入均不参与馈线判定；其它设备只能关联到该 FEEDER_ID 下。": "Feeder model validation, completion of missing feeder sections, and safe write-back. The G filename is the only feeder source: an NN token becomes AH3NN, while an AGNN token becomes AG4NN; both resolve the station by exact 405/substation.NAME and then exact-match 13500 by ST_ID + NAME. RMU, Pole Switch, Pole Transformer, G-root facID, source-CBreaker text and manual input never select the feeder; all target devices must belong to that FEEDER_ID.",
})

# Additional field-work UI strings.
ZH_TO_EN.update({
    "IP / 主机": "IP / Host",
    "远程目录": "Remote Directory",
    "SSH 用户名": "SSH Username",
    "图纸类型确认": "Drawing Type Confirmation",
    "自动识别（默认，按 G 图拓扑）": "Auto Detect (Default, G-file Topology)",
    "强制单馈线图（本次文件/目录）": "Force Single-feeder Drawing (Current File/Folder)",
    "强制组合图（本次文件/目录）": "Force Composite Drawing (Current File/Folder)",
    "AUTO 使用 G 文件电气拓扑自动判断。强制单馈线/组合图只改变本次图纸类型判定；目标 FEEDER_ID 仍必须由源侧 CBreaker 按矩形最小边缘距离找到的最近有效 Text 在 13500 中自动唯一确定。": "AUTO determines drawing type from the G-file electrical topology. Force Single/Composite changes only the drawing-type decision; the target FEEDER_ID must still be uniquely resolved in 13500 from the source CBreaker's nearest eligible Text selected by rectangle minimum-edge distance.",
    "执行模型关联时自动创建数据库中缺失的馈线段": "Automatically create missing feeder sections during model association",
    "恢复馈线默认配置": "Restore Feeder Defaults",
    "仅在用户明确勾选后允许：当文件名/人工输入解析出的目标馈线与当前 G.facID 或 FeedLine 所属馈线不一致时，把安全输出副本的根 facID 和所选 FeedLine 重新关联到目标馈线。组合图仍禁止整图覆盖到单一馈线。": "Only when explicitly enabled by the operator: if the target feeder resolved from file name/manual input differs from the current G.facID or FeedLine feeder ownership, relink the root facID and selected FeedLines in the safe output copy to the target feeder. Composite drawings still cannot be overwritten to one feeder.",
    "G.facID 仅表示当前关联。FACID / 文件名 / 人工输入三种来源互不强制；如所选目标与当前 facID 不同，只有启用“允许覆盖”后才会生成覆盖候选。": "G.facID represents only the current association. FACID, file-name, and manual sources are independent; if the selected target differs from the current facID, overwrite candidates are generated only when override is enabled.",
    "当前 G.facID 为空。FACID / 文件名 / 人工输入三种来源独立；文件名模式支持单文件和批量目录，并对每个文件独立解析、独立数据库唯一校验。": "The current G.facID is empty. FACID, file-name, and manual sources are independent. File-name mode supports both single-file and batch-folder processing, resolving and uniquely validating each file independently.",
    "馈线段 dms_section_device": "Feeder Section dms_section_device",
    "可关联设备选择（模型校验结果）": "Eligible Device Selection (Validation Result)",
    "可关联馈线 / 馈线段选择（模型校验结果）": "Eligible Feeder / Section Selection (Validation Result)",
    "馈线段快速筛选": "Quick Feeder Section Filter",
    "源G文件": "Source G File",
    "设备图元": "Device Object",
    "逻辑设备名称（图上规则）": "Logical Device Name (Graph Rule)",
    "当前关联": "Current Association",
    "目标设备ID": "Target Device ID",
    "目标馈线段": "Target Feeder Section",
    "处理说明": "Action Details",
    "打开结果": "Open Result",
    "大小": "Size",
    "服务器修改时间": "Server Modified Time",
    "状态": "Status",
    "选择": "Select",
    "G文件": "G File",
    "环网柜名称": "RMU Name",
    "环网柜序号": "RMU Index",
    "图元XML ID": "XML ID",
    "FeedLine序号": "FeedLine Index",
    "数据库CODE": "Database CODE",
    "打开校验 HTML": "Open Validation HTML",
    "打开预览 HTML": "Open Preview HTML",
    "打开关联结果 HTML": "Open Association Result HTML",
    "打开校验环网柜 CSV": "Open Validation RMU CSV",
    "打开校验设备 CSV": "Open Validation Device CSV",
    "打开预览环网柜 CSV": "Open Preview RMU CSV",
    "打开预览设备 CSV": "Open Preview Device CSV",
    "打开关联结果环网柜 CSV": "Open Association RMU CSV",
    "打开关联结果设备 CSV": "Open Association Device CSV",
    "打开馈线汇总 CSV": "Open Feeder Summary CSV",
    "打开馈线段明细 CSV": "Open Feeder Section Details CSV",
    "打开汇总 CSV": "Open Summary CSV",
    "打开明细 CSV": "Open Details CSV",
    "确认执行模型关联": "Confirm Model Association",
    "任务准备中……": "Preparing task...",
    "文件准备失败": "File Preparation Failed",
    "任务执行失败": "Task Failed",
    "任务执行完成": "Task Completed",
    "模型关联失败": "Model Association Failed",
    "模型关联完成": "Model Association Completed",
    "模型关联完成，最终 HTML / CSV 报告已生成": "Model association completed. Final HTML / CSV reports generated.",
    "模型关联完成，最终报告已生成": "Model association completed. Final reports generated.",
    "模型关联写回完成，正在整理执行结果……": "Model association write-back completed; preparing execution results...",
    "模型关联后台任务异常结束，未返回执行结果。": "The model association background task ended unexpectedly without returning a result.",
    "数据库连接正常": "Database Connection OK",
    "数据库连接失败": "Database Connection Failed",
    "SSH 连接失败": "SSH Connection Failed",
    "根facID未关联": "Root facID Unlinked",
    "当前记录无需回写或已被校验阻断。": "This record does not require write-back or is blocked by validation.",
    "本地模式：请选择 G 文件或目录。": "Local mode: select a G file or folder.",
    "SSH模式：请选择远程 G 文件后执行模型校验。": "SSH mode: select remote G files, then run model validation.",
    "执行前需要进行 Oracle 预检查。": "Oracle pre-check is required before execution.",
    "SSH 文件服务器严格只读；每次模型校验重新下载当前最新版本，关联锁定该次快照": "SSH file server is strictly read-only; each validation downloads the latest version and association uses the locked validation snapshot",
    "输入环网柜名称快速筛选，例如：17613 / RMU-42646": "Filter by RMU name, e.g. 17613 / RMU-42646",
    "输入 FEEDER_ID / 馈线名称 / FeedLine XML ID / 目标馈线段名称": "Enter FEEDER_ID / feeder name / FeedLine XML ID / target section name",
    "例如：AJWD 43": "Example: AJWD 43",
    "例如：ABH-06、SAMR、JED-NTH": "Example: ABH-06, SAMR, JED-NTH",
    "请选择下方具体任务按钮执行。": "Select an action below to continue.",
    "数据库连接正常": "Database Connection OK",
    "数据库连接失败": "Database Connection Failed",
    "任务准备中……": "Preparing task...",
    "文件准备失败": "File Preparation Failed",
    "任务执行完成": "Task Completed",
    "任务执行失败": "Task Failed",
    "已选择 0 个对象": "0 objects selected",
    "正在准备模型关联……": "Preparing model association...",
    "正在写入安全 G 文件副本……": "Writing safe G-file copies...",
    "模型关联失败": "Model Association Failed",
    "SSH只读模式：RMU/馈线模型校验都会重新下载服务器当前最新 G 文件。": "SSH read-only mode: RMU and feeder validation always downloads the latest G files from the server.",
    "模型校验完成，报告和可关联清单已生成": "Model validation completed; reports and eligible-object list were generated.",
    "数据库配置已保存。": "Database settings saved.",
    "Oracle 数据库连接验证通过。": "Oracle database connection validated.",
    "模型校验完成，校验报告和可关联清单已生成。": "Model validation completed; validation reports and eligible-object list were generated.",
    "数据库配置": "Database Settings",
    "Oracle 数据库连接失败": "Oracle Database Connection Failed",
    "SSH 配置": "SSH Settings",
    "下载所选 G 文件": "Download Selected G Files",
    "G 文件下载完成": "G-file Download Completed",
    "下载远程 G 文件失败": "Remote G-file Download Failed",
    "打开 Workspace 失败": "Open Workspace Failed",
    "本次运行目录": "Current Run Directory",
    "打开本次运行目录失败": "Open Current Run Directory Failed",
    "模型任务配置错误": "Model Task Configuration Error",
    "创建 Workspace 运行目录失败": "Create Workspace Run Directory Failed",
    "模型任务执行失败": "Model Task Failed",
    "确认执行模型关联": "Confirm Model Association",
    "打开结果": "Open Result",
    "打开结果失败": "Open Result Failed",
    "当前没有可打开的结果文件。": "There is no result file to open.",
    "当前没有可打开的运行目录。": "There is no run directory to open.",
    "请先勾选至少一个远程 G 文件。": "Select at least one remote G file first.",
    "已关联": "Linked",
    "未关联": "Unlinked",
    "连接区域": "Connection Region",
    "G图元类型": "G Object Type",
    "数据库当前事实唯一正确，可选择执行关联/重新关联。": "The current database facts uniquely identify the correct target; association / relink can be selected.",
    "模型校验完成后，这里展示 G 文件设备明细。只有数据库当前事实已经唯一确定、并且需要关联或重新关联的设备才允许勾选。执行模型关联时只处理你勾选的设备。": "After validation, this table shows G-file device details. Only devices with a uniquely determined database target that require association or relink can be selected. Model association processes only selected devices.",
    "模型校验完成后，这里展示可执行的馈线根关联和 FeedLine 明细。当 G 文件没有 FeedLine、但人工输入/文件名已唯一确定 13500 馈线时，可单独勾选 G 根节点 facID 关联；不会创建 13503 馈线段。其余 FeedLine 仍按原规则逐条选择。": "After validation, this table shows executable feeder-root associations and FeedLine details. If a G file has no FeedLine but a 13500 feeder is uniquely resolved by manual input or file name, the G root facID can be selected independently; no 13503 section will be created. Other FeedLines remain individually selectable.",
})


# Full-page descriptions/help. Keeping these in the locale layer prevents
# engineering logic from accumulating language-specific branches.
ZH_TO_EN.update({
    "数据库访问模式：只读查询为默认。仅馈线模型在启用“自动创建缺失馈线段”并执行【模型关联】时，允许 INSERT DMS_SECTION_DEVICE；不会 UPDATE / DELETE 已有数据库设备。除该明确启用的馈线段 INSERT 外，其他流程不会向 Oracle 数据库执行 INSERT / UPDATE / DELETE。G 文件仍只修改 Workspace 安全副本。":
        "Database access is read-only by default. Only the feeder model, when 'Automatically create missing feeder sections' is enabled and Model Association is executed, may INSERT into DMS_SECTION_DEVICE. Existing database devices are never UPDATEd or DELETEd. All other workflows are read-only, and G-file changes are limited to safe Workspace copies.",
    "SSH 服务器只读：本工具仅允许列目录、读取属性和下载 G 文件；禁止上传、覆盖、重命名、删除或修改服务器上的任何文件。":
        "SSH server access is read-only: the tool can list directories, read attributes, and download G files only. Uploading, overwriting, renaming, deleting, or modifying server files is prohibited.",
    "安全说明：RMU 环网柜模型和馈线模型共用本地/SSH文件来源；本地原始 G 文件和 SSH 服务器文件均不修改。SSH 模式每次【模型校验】都会重新下载服务器当前最新稳定版本到 remote_input；同一次校验后的【执行模型关联】只使用该次快照，并仅修改 g_output 安全副本。":
        "Safety: RMU and feeder models share the same local/SSH source. Original local G files and SSH server files are never modified. In SSH mode, every Model Validation downloads the current stable version into remote_input. Model Association after that validation uses the same locked snapshot and modifies only the g_output safe copy.",
    "模型校验完成后，这里展示 G 文件设备明细。只有数据库当前事实已经唯一确定、并且需要关联或重新关联的设备才允许勾选。PASS / FAIL / BLOCKED 行不会被误关联。执行模型关联时只处理你勾选的设备。":
        "After validation, this table shows G-file device details. Only devices whose current database target is uniquely determined and that require association/relink can be selected. PASS / FAIL / BLOCKED rows cannot be associated accidentally. Model Association processes only selected devices.",
    "每次模型校验/模型关联都会在对应 run 目录写入 run_manifest.json。模型关联还会生成 model_change_log.csv，记录 XML 图元各属性修改前后的值。":
        "Every validation/association writes run_manifest.json into its run directory. Model Association also creates model_change_log.csv with the before/after values of each changed XML object attribute.",
    "RMU 环网柜只有在矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 时才识别。环网柜名称默认读取矩形框上方，也可以多选右侧、左侧或下方，多选时只保留最近的一个 Text；设备命名规则固定使用环网柜内图上文字，不再读取三类设备 XML 的 p_NameString：CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。":
        "An RMU is recognized only when its rectangle contains CBreakerDis, BusDis, and ZhaiWaiJieDiDaoZha. The default RMU-name direction is above the rectangle; other directions may be selected too, and multiple selected directions keep only the nearest Text. Device naming uses graphical text inside the RMU; XML p_NameString is not used for these three device types.",
    "开关名称不再读取 XML p_NameString。CBreakerDis 仅使用环网柜内图上文字；接地刀闸逻辑名称=配对开关名+D；BusDis 固定为 BUS。图上名称无法唯一识别，或与数据库 CODE 校验失败时，会明确告警对应环网柜。":
        "Breaker names no longer use XML p_NameString. CBreakerDis uses only graphical text inside the RMU; grounding-switch logical name = paired breaker name + D; BusDis is always BUS. If a graphical name cannot be uniquely resolved or fails the database CODE check, the corresponding RMU is reported explicitly.",
    "运行时检测 G.facID：非空即强制 facID；facID 为空时才使用文件名或人工输入。":
        "At runtime, a non-empty G.facID is mandatory and authoritative; file-name or manual resolution is used only when facID is empty.",
    "安全边界：图纸类型只决定是否允许把整张 G 归属到一个馈线。单馈线图的馈线根 facID 关联不依赖 Breaker、Busbar、FeedLine 等设备关联状态；组合图禁止整图写入单一 FEEDER_ID。":
        "Safety boundary: drawing type only determines whether the whole G file may belong to one feeder. For a single-feeder drawing, root facID association does not depend on Breaker, Busbar, or FeedLine association state. A composite drawing can never be assigned one FEEDER_ID at the G root.",
    "数据库写入边界：仅在此选项启用且执行【模型关联】时，允许 INSERT 缺失的 DMS_SECTION_DEVICE。模型校验阶段不写数据库；已有馈线段绝不重复创建。":
        "Database write boundary: only when this option is enabled and Model Association is executed may missing DMS_SECTION_DEVICE rows be INSERTed. Validation never writes the database, and existing feeder sections are never duplicated.",
    "1. 在【数据库】页面确认 Oracle 配置，可先点击‘测试数据库连接’。\n2. 进入【模型工作区】，选择 RMU 环网柜模型或馈线模型，并选择 G 文件/目录。\n3. RMU 模块配置名称来源与设备表/域；馈线模块配置 13503 馈线段表及域号。\n4. 点击底部【模型校验】执行校验，并生成 HTML / CSV 以及可关联清单。\n5. 在可关联清单中勾选需要处理的设备或 FeedLine，然后点击【执行模型关联】。\n6. 执行前会显示最终确认摘要；模型关联只修改 Workspace 中的安全副本，原始 G 文件不变。\n7. 关联完成后生成本次执行 HTML / CSV、model_change_log.csv，并写入【运行历史】。":
        "1. Confirm Oracle settings on the Database page; optionally click Test Database Connection.\n2. Open Model Workspace, select RMU Model or Feeder Model, and choose a G file/folder.\n3. Configure RMU name/device table-domain settings, or the feeder 13503 section table/domain.\n4. Click Model Validation to run validation and generate HTML / CSV reports plus the eligible-object list.\n5. Select devices or FeedLines to process, then click Apply Model Association.\n6. Review the final confirmation summary. Association modifies only safe Workspace copies; original G files remain unchanged.\n7. After association, execution HTML / CSV and model_change_log.csv are generated and recorded in Run History.",
    "• 环网柜只有在矩形框内同时存在 CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 三类图元时才识别为 RMU。\n• RMU 柜型：柜内 Y*/Q* 文字与 CBreakerDis.devref 模板结构独立计算并交叉验证；devref 不解析任何现场图元关键字，只检查 Y 类同模板、Q 类同模板且 Y/Q 模板可区分。有效 devref 与文字冲突时仍以 devref 为准，同时 WARN。\n• 环网柜名称默认读取矩形框上方，也可以多选右侧、左侧或下方；多选时每个 RMU 只保留所选方向中最近的一个 Text。\n• 每个 Text 全局只分配给距离最近的一个环网柜。\n• 绿色依据 G 文件属性判断：lc=0,255,0 或 lcc=#00ff00；实际名称读取 Text.ts，但颜色不改变最近名称选择。\n• 环网柜名称始终按字符串处理，支持 42646、RMU-42646、ABC_123、JED-RMU-01、ABC.01 等常见工程名称，不会强制转换成数字。":
        "• An RMU is recognized only when its rectangle contains CBreakerDis, ZhaiWaiJieDiDaoZha, and BusDis.\n• RMU type: Y*/Q* text and CBreakerDis.devref template structure are calculated independently and cross-checked. devref names are not interpreted; Y devices must share one template, Q devices one template, and Y/Q templates must be distinguishable. If valid devref conflicts with text, devref wins and WARN is reported.\n• The default RMU-name direction is above the rectangle; other directions may be selected too. With multiple directions selected, each RMU keeps only the nearest Text among those directions.\n• Each Text is globally assigned only to its nearest RMU to prevent one name from being reused by two cabinets.\n• Green text is identified by lc=0,255,0 or lcc=#00ff00; the actual name comes from Text.ts, but color does not override nearest-name selection.\n• RMU names are always treated as strings, supporting compact values such as 42646, RMU-42646, ABC_123, JED-RMU-01, and ABC.01, plus the field form number + space + suffix such as 66 B.",
    "• 13502 / CBreakerDis：先在当前 RMU + 当前文件名馈线范围内按 NAME 精确匹配；NAME 为 0 条时才按同值 CODE 精确兜底；NAME 或 CODE 多条都禁止自动选择。\n• 13514 / ZhaiWaiJieDiDaoZha：Y* 优先 NAME=KY*，Q* 优先 NAME=KQ*；NAME 为 0 条时才使用原 CODE=Y*D/Q*D 兜底。\n• 13506 / BusDis：逻辑 CODE 固定 BUS，并同样强制校验当前 RMU 与当前文件名馈线归属。\n• 目标 RMU 必须属于文件名确定的 FEEDER_ID；柜内设备必须同时属于该 RMU 且 FEEDER_ID 相同。\n• 匹配只针对 G 文件实际存在的图元；其它无关数据库记录不参与数量比较。":
        "• 13502 / CBreakerDis: first match exact NAME within the current RMU and filename-resolved feeder; only when NAME has zero matches may the same-value CODE be used as fallback. Multiple NAME or CODE matches are blocked.\n• 13514 / ZhaiWaiJieDiDaoZha: Y* first matches NAME=KY*, Q* first matches NAME=KQ*; only when NAME has zero matches may the original CODE=Y*D/Q*D fallback be used.\n• 13506 / BusDis: logical CODE remains BUS, with the same hard current-RMU and filename-feeder ownership checks.\n• The RMU must belong to the filename-resolved FEEDER_ID; each child device must belong to both that RMU and the same FEEDER_ID.\n• Matching is limited to objects that actually exist in the G file; unrelated database rows are ignored.",
    "绿色 PASS：设备模型校验正常；已有人工关联且名称匹配、环网柜归属、馈线归属均正确时也可显示绿色。\n黄色 WARN：设备尚未关联，但满足自动关联条件。\n黄色 WARN：设备当前未关联，但数据库当前目标唯一有效，可以关联。\n橙色 RELINK：旧设备 ID、KeyID、表号或域号已过期/错误，或旧设备被删除重建；数据库当前目标唯一有效，可以重新关联。\n紫色 RMU_RELINK：旧 KeyID 指向其他环网柜，但当前 RMU 内已唯一确定正确设备，可以强制重新关联。\n红色 FAIL：数据库当前事实无法唯一确定安全目标，例如 RMU 0/多条、NAME/CODE 0/多条、目标设备不属于当前 RMU、设备不属于文件名馈线、Expected KeyID/BV_ID 无效。\nRMU 报告会携带文件名确定的图级馈线，并把它作为 RMU 与柜内设备的硬约束。":
        "Green PASS: device validation is correct; existing manual links are also green when name matching, RMU ownership, and feeder ownership are all correct.\nYellow WARN: device is unlinked but satisfies automatic association conditions.\nYellow WARN: the current database target is uniquely valid and can be associated.\nOrange RELINK: old device ID, KeyID, table ID, or Domain is stale/incorrect, or the old device was recreated; the current database target is uniquely valid and can be relinked.\nPurple RMU_RELINK: old KeyID points to another RMU, but the correct device is uniquely determined inside the current RMU and can be force-relinked.\nRed FAIL: current database facts cannot uniquely determine a safe target, such as zero/multiple RMUs, zero/multiple NAME/CODE matches, wrong RMU ownership, wrong filename-feeder ownership, or invalid Expected KeyID/BV_ID.\nThe RMU report carries the filename-resolved graph feeder and treats it as a hard constraint for the RMU and child devices.",
    "• SSH 模式只允许读取目录、读取文件属性和下载 G 文件；程序没有上传、覆盖、删除、重命名服务器文件的功能。\n• IP/主机、端口、用户名、密码和远程目录都可以自定义；点击【保存 SSH 配置】后写入本地 Workspace 配置，下次启动自动恢复最后一次保存值。\n• 点击【刷新 G 文件列表】只刷新浏览列表；搜索只在当前已加载列表中本地过滤。\n• RMU 环网柜模型与馈线模型使用完全相同的 SSH 文件源。无论当前模型类型是哪一个，每次点击【模型校验】都会重新从服务器下载当前勾选文件的最新版本，历史 remote_input 或本地缓存绝不会作为新一次校验输入。\n• 下载采用 stat-before → download → stat-after 稳定性检查；如果 size/mtime 在下载期间变化，会自动重新下载，最多 3 次。\n• 下载成功后写入本次 run/remote_input，并计算 SHA256；该快照即为本次模型校验的固定输入。\n• 同一次校验后的【执行模型关联】禁止再次从服务器下载。关联必须使用本次 remote_input 快照复制到 g_output 后修改，从而保证“校验哪个版本，就修改哪个版本”。\n• 若服务器文件后来发生变化，需要重新点击【模型校验】取得新的最新快照。":
        "• SSH mode may only list directories, read file attributes, and download G files; the application has no upload, overwrite, delete, or rename capability.\n• IP/host, port, username, password, and remote directory are configurable. Save SSH Settings stores them in the local Workspace and restores the last saved values at next startup.\n• Refresh G File List refreshes only the browser list; search filters the currently loaded list locally.\n• RMU and feeder models use the same SSH source. Every Model Validation re-downloads the latest version of the selected server files; historical remote_input or cache is never reused as a new validation input.\n• Download stability uses stat-before → download → stat-after; if size/mtime changes during download, it retries automatically up to three times.\n• Successful downloads are stored under run/remote_input with SHA256; that snapshot becomes the fixed validation input.\n• Apply Model Association after the same validation never re-downloads from the server. It copies the locked remote_input snapshot into g_output and modifies only that copy.\n• If the server file changes later, run Model Validation again to obtain a new snapshot.",
    "• 执行模型关联前建议保留 G 文件源目录的额外工程备份。\n• 如果图上设备文字本身错误，图上文字模式也会得到错误名称，因此必须查看报告后再执行关联。\n• 表号和域号可以修改，但修改后会直接影响 Expected KeyID，请仅在确认数据库定义后调整。\n• 本工具为团队内部工程工具，不建议在未验证的数据库或未知版本 G 文件上直接批量回写。":
        "• Keep an additional engineering backup of the source G-file directory before Model Association.\n• If graphical device text is wrong, graphical-name mode will also produce a wrong name; review the report before association.\n• Table ID and Domain are configurable, but changes directly affect Expected KeyID; adjust them only after confirming database definitions.\n• This is an internal engineering tool; do not perform bulk write-back against unverified databases or unknown G-file versions."
})



ZH_TO_EN.update({
    "文件名": "File Name",
    "源G文件": "Source G File",
    "输出G文件": "Output G File",
    "属性": "Attribute",
    "修改前": "Before",
    "修改后": "After",
    "无": "None",
    "馈线文件": "Feeder File",
    "馈线对象": "Feeder Object",
    "设备图元": "Device Object",
    "选择 G 文件下载目录": "Select G-file Download Directory",
    "选择 G 文件": "Select G File",
    "选择包含 G 文件的目录": "Select Directory Containing G Files",
    "G 文件 (*.g);;所有文件 (*.*)": "G Files (*.g);;All Files (*.*)",
    "历史路径不存在": "Saved Path Not Found",
    "上次记录的文件或目录不存在，请重新选择。": "The previously saved file or directory no longer exists. Select a new path.",
    "SSH 配置已保存。": "SSH settings saved.",
    "SSH 配置已保存；下次启动将自动恢复最后一次保存的输入。": "SSH settings saved. The last saved values will be restored at next startup.",
    "SSH只读模式：请先测试连接或刷新 G 文件列表。": "SSH read-only mode: test the connection or refresh the G-file list first.",
    "正在测试 SSH/SFTP 只读连接……": "Testing read-only SSH/SFTP connection...",
    "SSH/SFTP 连接正常；远程文件源为只读。": "SSH/SFTP connection OK; the remote source is read-only.",
    "SSH/SFTP 已连接；正在读取远程 G 文件列表……": "SSH/SFTP connected; reading remote G-file list...",
    "远程文件列表已刷新": "Remote file list refreshed",
    "读取远程 G 文件失败": "Failed to read remote G files",
    "读取远程 G 文件列表失败": "Failed to read remote G-file list",
    "SSH 端口必须是整数。": "SSH port must be an integer.",
    "SSH 端口必须在 1~65535 之间。": "SSH port must be between 1 and 65535.",
    "SSH IP / 主机不能为空。": "SSH IP / host cannot be empty.",
    "SSH 用户名不能为空。": "SSH username cannot be empty.",
    "SSH 远程目录不能为空。": "SSH remote directory cannot be empty.",
    "运行日志已复制。": "Run log copied.",
    "打开结果目录": "Open Result Directory",
    "打开修改记录": "Open Change Log",
    "关闭": "Close",
})

# v4.1.25 English-release completeness: every static UI string below is
# user-facing presentation text. Engineering codes/DB/XML values remain
# untranslated.
ZH_TO_EN.update({
    "模型帮助": "Model Help",
    "查看模型校验和模型关联的历史记录、报告、修改记录与运行目录。": "Review validation/association history, reports, change records, and run directories.",
    "时间": "Time",
    "模型": "Model",
    "操作": "Operation",
    "G 文件/输入": "G File / Input",
    "选中": "Selected",
    "成功": "Succeeded",
    "跳过/失败": "Skipped / Failed",
    "结果": "Result",
    "运行目录": "Run Directory",
    "模型关联": "Model Association",
    "当前记录没有对应的文件或目录。": "The selected record has no corresponding file or directory.",
    "团队内部版的公共安全策略和报告保留策略。": "Common safety policies and report-retention settings for the internal team edition.",
    "• 当前工作目录下自动生成的报告保留 30 天\n• 每次执行任务前必须进行 Oracle 预检查\n• 模型回写必须先生成校验候选\n• 原始 G 文件不修改；关联前先复制到 Workspace 安全副本\n• 回写目标必须通过 G 图元类型 + XML ID 唯一定位\n• G 文件采用临时文件写入后原子替换\n• 文件与目录选择会自动记住上一次位置\n• SSH 文件服务器严格只读；每次模型校验重新下载当前最新版本，关联锁定该次快照": "• Automatically generated reports in the current Workspace are retained for 30 days\n• Every task requires an Oracle pre-check before execution\n• Model write-back requires validated candidates first\n• Original G files are never modified; safe Workspace copies are created before association\n• Write-back targets are uniquely located by G object type + XML ID\n• G files are written through a temporary file followed by atomic replacement\n• File/folder dialogs remember the last location\n• The SSH file server is strictly read-only; every validation downloads the current latest version and association uses that locked snapshot",
    "当前工作目录下自动生成的报告保留 30 天\n• 每次执行任务前必须进行 Oracle 预检查\n• 模型回写必须先生成校验候选\n• 原始 G 文件不修改；关联前先复制到 Workspace 安全副本\n• 回写目标必须通过 G 图元类型 + XML ID 唯一定位\n• G 文件采用临时文件写入后原子替换\n• 文件与目录选择会自动记住上一次位置\n• SSH 文件服务器严格只读；每次模型校验重新下载当前最新版本，关联锁定该次快照": "Automatically generated reports in the current Workspace are retained for 30 days\n• Every task requires an Oracle pre-check before execution\n• Model write-back requires validated candidates first\n• Original G files are never modified; safe Workspace copies are created before association\n• Write-back targets are uniquely located by G object type + XML ID\n• G files are written through a temporary file followed by atomic replacement\n• File/folder dialogs remember the last location\n• The SSH file server is strictly read-only; every validation downloads the current latest version and association uses that locked snapshot",
    "请选择一个 G 文件，或包含 G 文件的目录": "Select a G file or a directory containing G files",
    "尚未测试 SSH/SFTP 连接。": "SSH/SFTP connection has not been tested.",
    "当前 G 文件 facID 非空，禁止人工输入": "Manual input is disabled because the current G file has a non-empty facID",
    "AUTO 使用 G 文件电气拓扑自动判断。强制单馈线后，若馈线名称在13500 中唯一，可将该 FEEDER_ID 回写到整张 G 根 facID；强制组合图则禁止整图根 facID 绑定到单一馈线。目录模式下该选择应用于本次目录中的全部 G 文件。": "AUTO determines drawing type from the G-file electrical structure. When Single-feeder is forced and the feeder name is unique in 13500, that FEEDER_ID may be written to the G root facID. Forced Composite mode prohibits binding the whole drawing root facID to one feeder. In directory mode this setting applies to every G file in the current directory.",
    "仅 INSERT DMS_SECTION_DEVICE 中确实不存在的记录；不会 UPDATE / DELETE 已有记录。创建成功后会重新查询数据库，再计算 Expected KeyID 并修改本地 G 输出副本。": "Only records truly missing from DMS_SECTION_DEVICE are INSERTed; existing records are never UPDATEd or DELETEd. After creation the database is queried again, Expected KeyID is recalculated, and only the local G output copy is modified.",
    "请至少选择一个环网柜名称位置。": "Select at least one RMU name position.",
    "馈线 facID 已锁定": "Feeder facID Locked",
    "当前 G.facID 为空：可选择文件名或人工输入。名称必须精准匹配；AJWD 6 与 AJWD 06 不等价。执行关联成功后，会把最终 FEEDER_ID 回写到 G 根节点 facID。": "Current G.facID is empty: file-name or manual feeder resolution may be used. Matching is exact; AJWD 6 and AJWD 06 are different feeders. After successful association, the final FEEDER_ID is written to the G root facID.",
    "【设备名称规则（固定）】\n• CBreakerDis：只使用环网柜内图上文字；XML p_NameString 完全不参与设备命名。\n• ZhaiWaiJieDiDaoZha：与柜内开关一对一配对；Y1/Y2/Y3 优先匹配数据库 NAME=KY1/KY2/KY3，Q1/Q2/Q3 优先匹配 NAME=KQ1/KQ2/KQ3；NAME 找不到时再用原 CODE=Y1D/Y2D/Y3D/Q1D/Q2D/Q3D 兜底。\n• BusDis：逻辑名称固定为 BUS。\n• CBreakerDis：图上识别到 Y1/Y2/Y3/Q1/Q2/Q3... 后，先在当前 RMU 且当前文件名馈线内匹配数据库 NAME；NAME 找不到时才用同值 CODE 兜底。\n• 所有柜内目标设备必须同时满足：COMBINED_ID 属于当前唯一 RMU，FEEDER_ID 等于文件名确定的图级馈线；任一不满足都禁止关联。\n\n【RMU 柜型识别】\n• 第一套：柜内 Y1/Y2/Y3... 每个计 L；Q1/Q2/Q3... 每个计 T，形成文字柜型。\n• 第二套：只分析 CBreakerDis.devref 模板结构；Y 类同模板、Q 类同模板，且 Y/Q 模板必须不同。ZhaiWaiJieDiDaoZha/RMU_ES 等不参与，且不解析任何现场 devref 名称含义。\n• 两套结果都存在时必须交叉验证；冲突时最终采用 devref 柜型，同时产生 WARN 并指出具体环网柜。\n\n• 环网柜数据库记录为 0 条或多条时，环网柜汇总直接 FAIL。若 G 设备未关联，禁止自动关联。\n• 环网柜数据库记录为 0 条或多条，但 G 设备已经有人为 KeyID 时，不丢弃该模型：继续反解当前设备并校验现有关联和实际所属环网柜。\n• 唯一 RMU 下，若旧 KeyID 实际属于其它环网柜，使用紫色 RMU_RELINK 标记，可以覆盖旧模型并重新关联到当前 RMU；只有 RMU 本身不唯一时才继续作为硬阻断。\n• RMU 模块不再通过任何设备反推馈线；所有图统一只认 G 文件名 → 405/substation → 13500/dms_feeder_device 得到的唯一 FEEDER_ID。RMU 本身不属于该馈线时禁止关联。\n• 唯一 RMU 下以当前数据库为准：NAME 优先/CODE 兜底匹配、目标设备 RMU 归属和 FEEDER_ID 均通过后，即使旧设备 ID、表号、域号、KeyID 已失效，也允许重新关联。": "[Fixed Device Naming Rules]\n• CBreakerDis uses only graphical text inside the RMU; XML p_NameString is never used. Match exact database NAME first inside the current RMU and filename feeder, then use same-value CODE only when NAME is absent.\n• ZhaiWaiJieDiDaoZha is paired one-to-one with the breaker: Y* prefers NAME=KY*, Q* prefers NAME=KQ*, then falls back to the original Y*D/Q*D CODE only when NAME is absent.\n• BusDis remains fixed to BUS.\n• Every child target must belong to both the unique current RMU and the filename-resolved FEEDER_ID.\n\n[RMU Type Recognition]\n• Source 1: Y1/Y2/Y3... each count as L; Q1/Q2/Q3... each count as T.\n• Source 2: only CBreakerDis.devref template structure is analyzed. Y devices share one template, Q devices share one template, and Y/Q templates must differ. ZhaiWaiJieDiDaoZha/RMU_ES does not participate and no site-specific devref words are interpreted.\n• When both sources exist they are cross-checked; on conflict the final type uses devref and WARN identifies the RMU.\n\n• Zero or multiple RMU database rows makes the RMU summary FAIL. If a G device is unlinked, automatic association is blocked.\n• If the RMU database result is zero/multiple but a G device already has a manual KeyID, the existing model is retained for reverse-resolution and CODE/graphical-name/actual-RMU checks.\n• Under a unique RMU, an old KeyID belonging to another RMU is marked purple RMU_RELINK and may be corrected; only non-unique RMU identity is a hard block.\n• RMU feeder selection never comes from devices: every drawing uses only the strict G filename -> 405/substation -> 13500/dms_feeder_device path. An RMU outside that feeder is blocked.\n• Under a unique RMU, current database truth is authoritative: once NAME-first/CODE-fallback matching plus RMU and FEEDER_ID ownership pass, stale device ID/table/domain/KeyID may be relinked.",
    "建议先执行【模型校验】，在可关联清单中确认 Expected KeyID 和待处理对象后再执行关联。\n真正执行模型关联时，程序会重新检查数据库及预览有效性，然后复制所有选中 G 文件到 Workspace/g_output，只修改副本。原始 G 文件绝不修改。\n\nCBreakerDis / ZhaiWaiJieDiDaoZha 回写：\napp=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\nBusDis 回写：\napp=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\n模型关联不会修改图上设备名称，也不会读取 XML p_NameString 作为设备名称。图级馈线只由文件名确定；RMU 必须属于该馈线，柜内设备必须同时属于当前 RMU 和该馈线。CBreakerDis 按 NAME 优先/CODE 兜底，接地刀闸按 KY*/KQ* NAME 优先、Y*D/Q*D CODE 兜底。旧 KeyID 仅用于识别 PASS / RELINK / RMU_RELINK，不会阻止修复已经过期的模型关联。": "Run Model Validation first and review Expected KeyID and the selected targets before association.\nDuring Model Association the database and validated result are rechecked, selected G files are copied to Workspace/g_output, and only those copies are modified. Original G files are never changed.\n\nCBreakerDis / ZhaiWaiJieDiDaoZha write-back:\napp=6500000, voltype=database device BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\nBusDis write-back:\napp=6500000, voltype=database device BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\nAssociation never changes graphical device names and never uses XML p_NameString as the device name. The graph feeder comes only from the filename; the RMU must belong to that feeder, and each child device must belong to both the RMU and that feeder. CBreakerDis uses NAME first with CODE fallback; grounding switches use KY*/KQ* NAME first with Y*D/Q*D CODE fallback. Old KeyID is used only to classify PASS / RELINK / RMU_RELINK and does not block repair of stale associations.",
    "•【环网柜汇总】严格按 G 文件环网柜序号排列，每个 G 环网柜只显示一行；数据库 0 条或多条直接 FAIL，不展开多个 ID。\n•【设备明细】只显示 G 文件实际存在的 RMU 设备图元，并展示逻辑设备名称、数据库 CODE、当前 KeyID 和实际所属环网柜。\n• RMU 数据库记录异常时，已有人为 KeyID 的设备仍继续校验；未关联设备则直接阻断自动关联。\n• 当选择图上文字模式时，报告中的逻辑设备名称 表示用于校验的逻辑 图上逻辑名称，不是 XML 原属性。\n• 每次模型校验和模型关联都会自动生成 HTML / CSV，并写入【运行历史】。\n• 模型关联额外生成 model_change_log.csv，逐项记录 XML ID、属性、修改前值和修改后值；Workspace 历史按软件保留策略自动清理。": "• RMU Summary follows G-file RMU order and shows one row per G RMU; zero/multiple database rows FAIL without expanding duplicate IDs.\n• Device Details shows only RMU device objects actually present in the G file, including logical name, database CODE, current KeyID, and actual RMU ownership.\n• When RMU database records are abnormal, devices with an existing manual KeyID continue validation; unlinked devices are blocked from automatic association.\n• In graphical-text mode, Logical Device Name is the logical graphical name used for validation, not the original XML attribute.\n• Every validation and association automatically generates HTML / CSV and is recorded in Run History.\n• Association additionally generates model_change_log.csv with XML ID, attribute, before value, and after value; Workspace history is cleaned according to retention policy.",
    "• 当前版本仅处理单馈线 G 图，不处理一个文件内多馈线总图。\n• 馈线名称优先从 <Bus> 周围最近的有效 Text 获取，例如 AJWD-07；若找不到，再从文件名提取。\n• 数据库可读馈线名称由站名 + dms_feeder_device.NAME 组合；名称匹配忽略横线、下划线和空格：AJWD-07 → AJWD07；JED CTL AJWD + 07 → JEDCTLAJWD07。\n• 馈线主表：13500 / dms_feeder_device；馈线段表：13503 / dms_section_device；默认域号：1。\n• G 馈线段图元为 <FeedLine>。已有关联时，当前 KeyID 必须反解到 13503 / Domain 1 且数据库记录属于当前馈线。\n• 已关联 FeedLine：13503、Domain、FEEDER_ID 均正确即保持原关联，不按几何顺序重排 SEC。\n• 未关联/失效关联 FeedLine：已正确关联的数据库馈线段先视为占用；其余数据库馈线段按自然顺序分配，真实数量不足时才新建缺少数量。\n• 已经关联错误的 FeedLine 不自动覆盖，只在报告中标红，避免静默改错已有模型。\n• FeedLine 回写安全副本：app=6500000, p_ReportType=1, state=20, voltype=dms_section_device.BV_ID, keyid=Expected KeyID。\n• 馈线模块拥有独立的【馈线汇总】和【馈线段明细】HTML / CSV 报告，不改变 RMU 模块已经取消馈线判断的规则。": "• Feeder validation supports single-feeder drawings and composite-drawing auditing according to the current drawing classifier.\n• Feeder ownership uses the configured authoritative source; a non-empty G root facID has highest priority.\n• Feeder main table: 13500 / dms_feeder_device; feeder section table: 13503 / dms_section_device; default Domain: 1.\n• G feeder-section objects are <FeedLine>. Existing associations are validated only for correct table/domain and same-feeder ownership; geometric SEC order is not used to invalidate correct links.\n• Correct linked FeedLines are preserved. Unlinked/stale FeedLines first consume unused database sections in deterministic order, and only the real shortage is created.\n• Cross-feeder associations remain hard errors and are never silently overwritten.\n• FeedLine safe-copy write-back: app=6500000, p_ReportType=1, state=20, voltype=dms_section_device.BV_ID, keyid=Expected KeyID.\n• Feeder Model has independent Feeder Summary and Feeder Section Details HTML / CSV reports; RMU Model remains independent of feeder validation.",
})

EN_TO_ZH = {v: k for k, v in ZH_TO_EN.items()}


def normalize_language(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"en", "en_us", "english"}:
        return LANG_EN
    return LANG_ZH


def tr(text: object, language: str | None) -> str:
    source = "" if text is None else str(text)
    if normalize_language(language) == LANG_EN:
        value = ZH_TO_EN.get(source, source)
    else:
        value = EN_TO_ZH.get(source, source)
    # Device names are always read from Text objects. Keep older help strings
    # from exposing the retired alternate-text fallback in either language.
    return value.replace("Text / DText", "Text").replace("Text/DText", "Text")


_RUNTIME_REPLACEMENTS = [
    # v4.1.26: presentation-only runtime/console translations.
    ("语言已切换为简体中文。", "Language switched to Simplified Chinese."),
    ("RMU 环网柜模型校验、候选选择及安全回写。", "RMU model validation, candidate selection, and safe write-back."),
    ("馈线模型校验、数据库缺失馈线段补齐及安全回写。FACID、文件名、人工输入三种馈线来源相互独立；单文件与批量目录使用同一解析规则。组合大图忽略根 facID，按单馈线 XML 指纹和连接拓扑审计 FeedLine 的 FEEDER_ID 一致性。", "Feeder model validation, completion of missing database feeder sections, and safe write-back. FACID, file-name, and manual feeder sources are independent; single files and batch folders use the same resolver. Composite drawings ignore root facID and audit FeedLine FEEDER_ID consistency using single-feeder XML fingerprints and connection topology."),
    ("馈线模型校验、数据库缺失馈线段补齐及安全回写。目标馈线使用与柱上开关、柱上变压器一致的图形识别方式：识别馈线源 CBreaker，分配其最近有效 Text，再用该图上名称唯一查询 13500。文件名、G 根 facID 和人工输入均不作为馈线识别来源；其余馈线段逻辑保持不变。", "Feeder model validation, completion of missing database feeder sections, and safe write-back. The target feeder uses the same graphical recognition pattern as Pole Switch and Pole Transformer: identify the feeder source CBreaker, assign its nearest eligible Text, then uniquely query 13500 with that graphical name. File name, G-root facID, and manual input are not feeder-resolution inputs; all other feeder-section logic remains unchanged."),
    ("馈线段 / dms_section_device", "Feeder Section / dms_section_device"),
    ("FACID_EMPTY: 当前 G 文件 facID 为空；请选择【仅使用文件名】或【仅使用人工输入】。", "FACID_EMPTY: current G-file facID is empty; select Use File Name Only or Use Manual Input Only."),
    ("无法确定馈线段命名前缀，或无法从 feeder.ST_ID -> 402/voltagelevel -> 401/basevoltage 找到允许的 110/33/13.8kV 电压等级，禁止自动创建馈线段。", "Unable to determine the feeder-section naming prefix, or no allowed 110/33/13.8 kV voltage level can be resolved through feeder.ST_ID -> 402/voltagelevel -> 401/basevoltage; automatic feeder-section creation is blocked."),
    ("区域", "region"),
    ("条", " rows"),
    (" 条；唯一写表=13503/dms_section_device。", " rows; only writable table=13503/dms_section_device."),
    # These phrases are emitted by existing business code; only their display
    # text is translated. No validation/association/database logic changes.
    ("本次模型校验已锁定 remote_input 快照；后续模型关联必须使用同一快照，不会再次从服务器下载。", "This validation has locked the remote_input snapshot; subsequent model association must use the same snapshot and will not download from the server again."),
    ("每次模型校验均重新从服务器获取当前最新 G 文件；不会使用历史下载缓存。", "Every model validation fetches the current latest G files from the server; historical download cache is never used."),
    ("服务器最终一致性检查通过：所有已选 G 文件在模型校验开始前均为最新稳定版本。", "Final server consistency check passed: all selected G files are the latest stable versions before model validation starts."),
    ("已完成已选馈线段的轻量数据库复核、剩余段重算与精确回写；不再对整张 G 图重新循环校验。", "Completed lightweight database revalidation, remaining-section recalculation, and precise write-back for the selected feeder sections; the entire G drawing is not revalidated again."),
    ("已完成已选设备的轻量数据库复核与精确回写；不再对整张 G 图重新循环校验。", "Completed lightweight database revalidation and precise write-back for the selected devices; the entire G drawing is not revalidated again."),
    ("模型关联写入完成，开始对 g_output 中的安全副本执行最终模型校验。", "Model association write-back completed; starting final model validation on the safe copies in g_output."),
    ("馈线段校验仅检查同馈线归属与Domain；已有正确关联不检查SEC/几何顺序。未关联或失效关联按当前馈线未占用数据库记录顺序从小到大分配；数量不足时只创建实际短缺数量；ls>2 仍按2参与建库。", "Feeder-section validation checks only same-feeder ownership and Domain. Correct existing links are not checked against SEC/geometric order. Unlinked or stale links are assigned from unused database records of the current feeder in ascending deterministic order; only the actual shortage is created; ls>2 still uses 2 for database creation."),
    ("执行模型关联：仅复核已选择的 ", "Applying model association: revalidating only the selected "),
    (" 个环网柜、", " RMUs, "),
    (" 个设备，不再重新扫描整张 G 图。", " devices; the entire G drawing will not be rescanned."),
    ("本次模型关联完成：选中=", "Model association completed: selected="),
    ("本次馈线模型关联完成：选中对象=", "Feeder model association completed: selected objects="),
    ("本次模型校验已锁定 remote_input 快照", "This validation has locked the remote_input snapshot"),
    ("后续模型关联必须使用同一快照", "subsequent model association must use the same snapshot"),
    ("不会再次从服务器下载", "no additional server download will occur"),
    ("模型校验已生成可关联馈线对象清单：", "Model validation generated the eligible feeder-object list: "),
    ("模型校验已生成可关联设备清单：", "Model validation generated the eligible device list: "),
    ("模型校验已生成可关联清单：", "Model validation generated the eligible-object list: "),
    ("可关联/重新关联设备 ", "eligible/relinkable devices "),
    ("可回写设备 ", "writable devices "),
    ("开始执行模型关联：重新验证 Oracle 数据库连接。", "Starting Model Association: revalidating the Oracle database connection."),
    ("正在执行模型关联，请查看实时日志……", "Applying model association. See the live console log for progress..."),
    ("正在执行环网柜模型关联：", "Applying RMU model association: "),
    ("已选设备=", "selected devices="),
    ("正在执行馈线模型关联：文件=", "Applying feeder model association: file="),
    ("正在执行馈线模型关联：", "Applying feeder model association: "),
    ("已选对象=", "selected objects="),
    ("正在复制 G 文件到安全输出目录：", "Copying G file to the safe output directory: "),
    ("正在回写 G 文件安全副本：", "Writing back the safe G-file copy: "),
    ("正在建立 G 文件回写索引：", "Building the G-file write-back index: "),
    ("目标对象数=", "target objects="),
    ("G 文件回写进度：", "G-file write-back progress: "),
    ("待写设备数=", "devices to write="),
    ("待写FeedLine数=", "FeedLines to write="),
    ("正在生成本次模型关联执行报告……", "Generating the model-association execution report..."),
    ("模型关联完成：本次选择=", "Model association completed: selected="),
    ("成功写回=", "written successfully="),
    ("执行时跳过=", "skipped at execution="),
    ("原始 G 文件未修改", "original G files unchanged"),
    ("输出目录=", "output directory="),
    ("关联完成 HTML：", "Association Result HTML: "),
    ("关联完成馈线汇总 CSV：", "Association Feeder Summary CSV: "),
    ("关联完成馈线段明细 CSV：", "Association Feeder Section Details CSV: "),
    ("关联完成环网柜 CSV：", "Association RMU CSV: "),
    ("关联完成设备 CSV：", "Association Device CSV: "),
    ("模型修改记录 CSV：", "Model Change Log CSV: "),
    ("馈线汇总 CSV：", "Feeder Summary CSV: "),
    ("馈线段明细 CSV：", "Feeder Section Details CSV: "),
    ("环网柜 CSV：", "RMU CSV: "),
    ("设备 CSV：", "Device CSV: "),
    ("任务完成。本次运行目录：", "Task completed. Run directory: "),
    ("保存关联完成 console.log 失败：", "Failed to save association console.log: "),
    ("保存 console.log 失败：", "Failed to save console.log: "),
    ("Oracle 数据库连接失败：", "Oracle database connection failed: "),

    ("，跳过=", ", skipped="),
    ("数据库新增馈线段=", "database-created feeder sections="),
    ("；区域=", "; regions="),
    (" 在 13500 中不存在", " does not exist in 13500"),
    ("；状态=", "; status="),
    ("已创建 G 文件备份：", "Created G-file backup: "),
    ("模型关联失败：", "Model Association Failed: "),
    (" 个。", "."),
    ("禁止该RMU及柜内设备自动关联", "automatic association of this RMU and its devices is blocked"),
    # RMU validation/runtime diagnostics.
    ("环网柜名称候选解析异常：", "RMU name candidate resolution error: "),
    ("正在处理环网柜 ", "Processing RMU "),
    ("RMU devref模板结构校验异常：", "RMU devref template-structure validation error: "),
    ("RMU类型交叉校验不一致：", "RMU type cross-check mismatch: "),
    ("柜型交叉验证告警：", "RMU type cross-check warning: "),
    ("当前环网柜校验未通过：", "Current RMU validation failed: "),
    ("矩形框 XML ID=", "Frame XML ID="),
    ("矩形框XML ID=", "Frame XML ID="),
    ("矩形框XML=", "Frame XML="),
    ("类型来源=", "type source="),
    ("智能标识=", "smart markers="),
    ("图内文字=", "graphical text="),
    ("柜内Y/Q文字类型=", "in-RMU Y/Q text type="),
    ("devref类型=", "devref type="),
    ("Y类devref模板=", "Y devref templates="),
    ("Q类devref模板=", "Q devref templates="),
    ("Y类模板=", "Y templates="),
    ("Q类模板=", "Q templates="),
    ("最终类型来源=", "final type source="),
    ("最终按有效devref类型", "final type uses the valid devref type"),
    ("最终采用有效devref类型", "the final type uses the valid devref type"),
    ("数据库记录数=", "database rows="),
    ("当前 G 文件处理完成", "Current G file completed"),
    ("复核环网柜 ", "Revalidating RMU "),
    ("数据库设备已更新：", "Database device changed: "),
    ("安全复制 G 文件：", "Safe-copy G file: "),
    ("写回完成：", "Write-back completed: "),
    ("修改设备数=", "modified devices="),
    ("无需关联：", "No association required: "),
    ("已正确关联", "already linked correctly"),
    ("执行时数据库事实发生变化，未写回", "database facts changed during execution; no write-back was performed"),
    ("执行时跳过", "skipped during execution"),
    ("跳过：", "Skipped: "),
    ("当前模型关联到了其他环网柜，可重新关联", "The current model points to another RMU and can be relinked"),
    ("重新关联到当前环网柜（覆盖旧模型关联）", "Relink to the current RMU (overwrite the old model association)"),
    ("旧模型关联已过期或错误，可重新关联", "The old model association is stale or incorrect and can be relinked"),
    ("重新关联（覆盖旧模型关联）", "Relink (overwrite the old model association)"),
    ("模型已关联且正确", "Model is linked correctly"),
    ("模型已关联，无需关联", "Model is already linked; no association required"),
    ("已人工关联，正在检查", "Manually linked; validating"),
    ("检查现有人工关联", "Validate existing manual association"),
    ("已人工关联，CODE与环网柜归属校验通过", "Manually linked; CODE and RMU ownership validation passed"),
    ("保留人工关联；RMU数据库记录异常需人工复核", "Keep the manual association; abnormal RMU database records require manual review"),
    ("禁止自动关联，请检查数据库设备归属", "Automatic association is blocked; check database device ownership"),
    ("需要关联", "Association required"),
    ("未关联", "Unlinked"),
    ("禁止自动关联", "Automatic association blocked"),
    ("图上环网柜名称解析/核验异常", "Graphical RMU name resolution/verification error"),
    ("图上环网柜名称未解析出来", "Graphical RMU name was not resolved"),
    ("请检查图上的环网柜名称是否应为“", "Check whether the RMU name on the drawing should be \""),
    ("未能从环网柜内图上文字唯一识别开关名称，请检查该环网柜命名方式", "Unable to uniquely resolve the breaker name from graphical text inside the RMU; check this RMU's naming"),
    ("在当前配置的环网柜名称方向内未解析到有效名称文字", "No valid RMU name text was resolved in the configured RMU-name directions"),
    ("已找到候选文字对象，但解析后的环网柜名称为空", "Candidate text objects were found, but the resolved RMU name is empty"),
    ("未解析出环网柜名称", "RMU name was not resolved"),
    ("环网柜名称解析/核验异常", "RMU name resolution/verification error"),
    ("环网柜身份无法可靠确定", "RMU identity cannot be determined reliably"),
    ("环网柜身份未确定", "RMU identity is undetermined"),
    ("环网柜身份未可靠确定", "RMU identity is not reliably determined"),
    ("环网柜必须唯一", "The RMU must be unique"),
    ("数据库中未找到唯一对应记录", "No unique corresponding database record was found"),
    ("数据库存在多条同名记录", "The database contains multiple records with the same name"),
    ("请检查数据库模型或图内环网柜名称", "Check the database model or the RMU name on the drawing"),
    ("请检查环网柜名称方向配置、图内名称文字及其与矩形框的位置关系", "Check the RMU-name direction settings, graphical name text, and its position relative to the frame"),
    ("柜内所有设备的现有KeyID均可反查，并且全部来自同一个数据库环网柜", "All existing device KeyIDs in the RMU can be reverse-resolved and all belong to the same database RMU"),
    ("因此现有RMU归属关联一致且正确，无需重新关联", "therefore the existing RMU ownership associations are consistent and correct; no relink is required"),
    ("当前能够反查的已关联设备均来自同一个数据库环网柜", "All currently reverse-resolvable linked devices belong to the same database RMU"),
    ("现有已关联设备的RMU归属一致", "the RMU ownership of existing linked devices is consistent"),
    ("由于图上名称仍未可靠解析，禁止自动新增或改绑；现有一致关联无需修改", "Because the graphical name is still not reliably resolved, automatic creation/rebinding is blocked; existing consistent associations require no change"),
    ("模型已关联且正确；图上RMU名称未解析，但柜内设备归属一致", "Model is linked correctly; the graphical RMU name is unresolved, but device ownership inside the RMU is consistent"),
    ("保留现有关联；请核对图上环网柜名称", "Keep existing associations; verify the RMU name on the drawing"),
    ("当前设备关联无需修改", "Current device association requires no change"),
    ("当前图形环网柜=", "current graphical RMU="),
    ("当前KeyID设备所属环网柜=", "current KeyID device RMU="),
    ("旧KeyID设备所属环网柜=", "old KeyID device RMU="),
    ("当前KeyID设备所属环网柜ID=", "current KeyID device RMU ID="),
    ("环网柜NAME=", "RMU NAME="),
    ("同一G图环网柜内已关联设备实际来自多个环网柜ID", "linked devices inside the same G-file RMU actually belong to multiple RMU IDs"),
    ("图上环网柜名称未可靠解析，且柜内已关联设备实际来自多个数据库环网柜ID", "the graphical RMU name is not reliably resolved and linked devices inside the RMU actually belong to multiple database RMU IDs"),
    ("无法反推出唯一环网柜", "a unique RMU cannot be inferred"),
    ("图上名称=", "graphical name="),
    ("数据库中不存在对应 CODE", "the database has no matching CODE"),
    ("数据库存在多条相同 CODE", "the database has multiple identical CODE records"),
    ("请检查该环网柜开关命名方式", "check the breaker naming for this RMU"),
    ("请检查该环网柜命名方式或数据库设备", "check this RMU's naming or the database device records"),
    ("数据库中不存在该设备", "the device does not exist in the database"),
    ("数据库中存在多条匹配设备", "multiple matching devices exist in the database"),

    ("CODE/图上逻辑CODE", "CODE / graphical logical CODE"),
    ("环网柜名称=", "RMU name="),
    ("同一个数据库设备ID=", "the same database device ID="),
    ("详情=", "details="),
    ("RMU_DUPLICATE_IN_DATABASE: 已解析环网柜名称=", "RMU_DUPLICATE_IN_DATABASE: resolved RMU name="),
    ("RMU_NOT_FOUND_IN_DATABASE: 已解析环网柜名称=", "RMU_NOT_FOUND_IN_DATABASE: resolved RMU name="),
    ("，但数据库存在多条同名记录；环网柜必须唯一，禁止自动关联。", ", but the database contains multiple rows with the same name; the RMU must be unique and automatic association is blocked."),
    ("，但数据库中未找到唯一对应记录；请检查数据库模型或图内环网柜名称，禁止自动关联。", ", but no unique corresponding database row was found; check the database model or RMU name on the drawing. Automatic association is blocked."),
    ("旧combined_id=", "old combined_id="),
    ("目标combined_id=", "target combined_id="),
    ("DEVICE_ID已变化(current=", "DEVICE_ID changed (current="),
    ("TABLE_ID不匹配(current=", "TABLE_ID mismatch (current="),
    ("DOMAIN不匹配(current=", "DOMAIN mismatch (current="),
    ("KEYID已变化或不匹配(current=", "KEYID changed or mismatched (current="),
    ("另有未关联设备=", "additional unlinked devices="),
    ("无法反查所属RMU的已关联设备=", "linked devices whose RMU cannot be reverse-resolved="),
    ("已通过柜内现有KeyID反查到唯一数据库环网柜（", "existing KeyIDs inside the RMU reverse-resolve to one unique database RMU ("),
    ("仅检查柜内CBreakerDis，ZhaiWaiJieDiDaoZha等其它图元不参与", "only in-RMU CBreakerDis objects are checked; ZhaiWaiJieDiDaoZha and other object types do not participate"),
    ("请检查同类Y/Q开关是否混用了不同devref模板", "check whether Y/Q switches of the same class mix different devref templates"),
    ("请检查该环网柜的Y/Q文字命名与开关devref模板是否一致", "check whether this RMU's Y/Q text naming is consistent with the breaker devref templates"),
    ("当前记录数=", "current row count="),
    ("图上逻辑名称=", "graphical logical name="),
    ("数据库 BV_ID 为空，禁止生成模型回写", "database BV_ID is empty; model write-back cannot be generated"),
    ("没有可执行的模型关联结果", "There is no executable model-association result"),
    ("RMU 配置在模型校验后发生变化，请重新执行模型校验", "RMU settings changed after model validation; run model validation again"),
    ("未提供安全 G 文件输出目录", "No safe G-file output directory was provided"),
    ("当前没有已选择的设备", "No devices are currently selected"),
    ("G 文件在模型校验后发生变化，请重新校验", "The G file changed after model validation; revalidate it"),
    ("准备执行", "Preparing execution"),
    ("本次模型关联成功", "This model association succeeded"),
    ("已完成", "completed"),
    # Unified drawing-feeder candidate diagnostics.
    ("[馈线识别候选] 类型=", "[Feeder candidate] type="),
    ("；结果=", "; result="),
    ("采用：数据库唯一匹配", "selected: unique database match"),
    ("跳过：数据库无匹配记录", "skipped: no database match"),
    ("跳过：数据库匹配 ", "skipped: database matches "),
    (" 条，不唯一", " rows; not unique"),
    ("跳过：唯一记录 FEEDER_ID 为空", "skipped: unique record has empty FEEDER_ID"),
    ("[发现馈线] ", "[Feeder found] "),
    ("图级馈线识别通过：", "Graph feeder resolution passed: "),
    ("图级馈线识别失败：", "Graph feeder resolution failed: "),
    # Feeder validation/runtime diagnostics.
    ("组合大图审计：", "Composite drawing audit: "),
    ("单馈线指纹跳过：", "Single-feeder fingerprint skipped: "),
    ("馈线精准匹配通过：", "Exact feeder match passed: "),
    ("馈线精准匹配失败：", "Exact feeder match failed: "),
    ("人工输入馈线不存在：", "Manual feeder does not exist: "),
    ("人工输入馈线不唯一：", "Manual feeder is not unique: "),
    ("本次人工输入是绝对目标，不会回退使用当前 facID 或文件名。", "The manual input is the absolute target for this run; the current facID and file name will not be used as fallbacks."),
    ("数据库精确匹配数=", "database exact matches="),
    ("禁止自动选择", "automatic selection is blocked"),
    ("输入馈线不存在=", "input feeder does not exist="),
    ("文件名馈线识别通过：", "File-name feeder resolution passed: "),
    ("文件名馈线识别失败：", "File-name feeder resolution failed: "),
    ("变电站输入/解析值=", "substation input/resolved value="),
    ("已尝试=", "attempted="),
    ("数据库未找到唯一站点下的馈线记录", "the database did not return feeder records for one unique substation"),
    ("；数据库未找到该站馈线记录。", "; no feeder records were found for this substation in the database."),
    ("；匹配数=", "; matches="),
    ("；候选=", "; candidates="),
    ("] 使用 G.facID=", "] Using G.facID="),
    ("(FACID / 13500 精确ID匹配)", "(FACID / exact ID match in 13500)"),
    ("目录馈线模式：使用当前所选馈线识别来源逐文件独立解析；已建立可信单馈线指纹=", "Directory feeder mode: resolve each file independently using the selected feeder source; trusted single-feeder fingerprints="),
    (" 与本次", " versus current "),
    ("目标 FEEDER_ID=", "target FEEDER_ID="),
    (" 不同；已启用人工覆盖，将在模型关联时允许覆盖根 facID 和错误馈线段关联。", " differs; explicit override is enabled, so model association may replace the root facID and incorrect cross-feeder section links."),
    (" 不同；未启用人工覆盖，现有跨馈线关系将保持阻断。", " differs; explicit override is not enabled, so existing cross-feeder relationships remain blocked."),
    ("变电站=", "substation="),
    ("文件馈线号=", "file feeder token="),
    ("13500 站内唯一匹配", "unique match within the substation in 13500"),
    ("当前 G.facID=", "current G.facID="),
    ("已启用人工覆盖", "explicit override enabled"),
    ("未启用人工覆盖", "explicit override not enabled"),
    ("目录馈线模式：使用当前所选馈线识别来源逐文件独立解析；", "Directory feeder mode: resolve each file independently using the selected feeder source; "),
    ("(13500 唯一精准匹配)", "(unique exact match in 13500)"),
    ("(FACID_FORCED / 13500 精确ID匹配)", "(FACID_FORCED / exact ID match in 13500)"),
    ("目录馈线模式：单馈线图只允许 facID；已建立可信单馈线指纹=", "Directory feeder mode: single-feeder drawings require facID; trusted single-feeder fingerprints="),
    ("正在处理馈线模型：", "Processing feeder model: "),
    ("图纸类型=", "drawing type="),
    ("识别馈线区域=", "resolved feeder regions="),
    ("数据库缺失馈线段计划=", "missing database feeder-section plan="),
    ("命名规则=", "naming rule="),
    ("创建电压等级=", "creation voltage level="),
    ("指纹候选=", "fingerprint candidates="),
    ("有效母线=", "effective busbars="),
    ("源分支=", "source branches="),
    ("标题锚点=", "title anchors="),
    ("置信度=", "confidence="),
    ("判据=", "criterion="),
    ("馈线区域", "Feeder region "),
    ("勾选FeedLine=", "selected FeedLines="),
    ("未选中已占用数据库段=", "unselected occupied database sections="),
    ("当前可分配数据库段=", "currently available database sections="),
    ("准备创建选中 FeedLine 对应的缺失馈线段 ", "preparing to create missing feeder sections for selected FeedLines: "),
    ("唯一写表=", "only writable table="),
    ("数据库新增馈线段：", "Database feeder section created: "),
    ("跳过 FeedLine XML=", "Skipped FeedLine XML="),
    ("馈线模型安全副本处理完成：", "Feeder-model safe-copy processing completed: "),
    ("修改FeedLine数=", "modified FeedLines="),
    ("根facID回写=", "root facID written="),
    ("归一化=", "normalized="),
    ("G 根节点 facID 回写完成：", "G root facID write-back completed: "),
    ("本次仅关联馈线根节点facID；Breaker/Busbar/FeedLine状态不参与该根关联。", "This run associates only the feeder root facID; Breaker/Busbar/FeedLine status does not participate in this root association."),
    ("已经属于馈线 ", "already belongs to feeder "),
    ("馈线模型校验完成", "feeder model validation completed"),
    ("当前连接区域没有可信已关联环网柜，禁止自动关联馈线段", "the current connection region has no trusted linked RMU; automatic feeder-section association is blocked"),
    ("当前连接区域的可信环网柜来自不同FEEDER_ID，禁止自动关联，请人工确认", "trusted RMUs in the current connection region belong to different FEEDER_ID values; automatic association is blocked and manual confirmation is required"),
    ("RMU拓扑馈线识别：", "RMU-topology feeder resolution: "),
    ("拓扑连接区域=", "topology connection regions="),
    ("G馈线标题候选=", "G feeder-title candidates="),
    ("清洗后锚点=", "anchors after cleanup="),
    ("数据库唯一确认=", "unique database confirmations="),
    ("G馈线锚点：", "G feeder anchors: "),
    ("RMU框XML=", "RMU frame XML="),
    ("可信参考=", "trusted references="),
    ("忽略参考=", "ignored references="),
    ("连接区域", "Connection region "),
    ("可信RMU=", "trusted RMUs="),
    ("忽略RMU=", "ignored RMUs="),
    ("可关联=", "eligible="),
    ("错误=", "errors="),
    ("参考=", "reference="),
    ("馈线=", "feeder="),
    ("精确匹配数=", "exact matches="),
    ("AJWD 6 与 AJWD 06 按不同馈线处理", "AJWD 6 and AJWD 06 are treated as different feeders"),
    ("忽略当前 ", "ignoring current "),
    (" 选择，强制使用 facID", " selection; facID is forced"),
    ("facID 非空时禁止文件名/人工输入兜底", "file-name/manual fallback is prohibited when facID is non-empty"),
    ("facID 非空，不允许退回文件名或人工输入", "facID is non-empty; fallback to file name or manual input is not allowed"),
    ("当前FeedLine实际feeder_id=", "current FeedLine feeder_id="),
    ("期望feeder_id=", "expected feeder_id="),
    ("禁止自动跨馈线重关联", "automatic cross-feeder relinking is blocked"),
    ("允许值：2->0, 1->1, 空->3", "allowed values: 2->0, 1->1, empty->3"),
    ("数据库存在", "database contains "),
    ("已匹配当前馈线现有未占用馈线段", "matched an existing unused feeder section of the current feeder"),
    ("无法可靠判定单馈线/组合大图；只报告，不自动关联", "cannot reliably classify single-feeder vs composite drawing; report only, no automatic association"),
    ("目录模式下单馈线图只允许使用非空 G.facID", "in directory mode, single-feeder drawings require a non-empty G.facID"),
    ("G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验", "the G file changed after validation; stale results are blocked, revalidate"),
    ("执行阶段发现 G.facID 已非空，禁止使用文件名/人工输入结果覆盖", "execution found a non-empty G.facID; file-name/manual results cannot overwrite it"),
    ("数据库剩余馈线段数量不足", "insufficient remaining database feeder sections"),
    ("当前馈线未占用数据库馈线段不足，实际短缺=", "unused database feeder sections for the current feeder are insufficient; actual shortage="),
    ("仅创建缺少数量后继续按当前未关联FeedLine顺序关联", "create only the shortage, then continue association for the currently unlinked FeedLines"),
    ("当前馈线段和feeder_id均正确，仅域号错误", "the current feeder section and feeder_id are correct; only the Domain is wrong"),
    ("当前13503馈线段和feeder_id均正确，仅域号错误", "the current 13503 feeder section and feeder_id are correct; only the Domain is wrong"),
    ("保持device_id不变并重写KeyID", "keep device_id unchanged and rewrite KeyID"),
    ("旧13503设备已不存在", "the old 13503 device no longer exists"),
    ("全新图按FeedLine顺序使用数据库现有馈线段", "for a new drawing, use existing database feeder sections in FeedLine order"),
    ("保留已有正确关联，并按数据库剩余记录顺序从小到大重新关联", "preserve correct existing links and relink using remaining database records in ascending order"),
    ("全新图按顺序关联", "new drawing: associate in order"),
    ("保留已有正确关联；按当前馈线未占用数据库记录顺序从小到大关联", "preserve correct existing links; associate using unused database records of the current feeder in ascending order"),
    ("当前KeyID对应的13503设备已不存在", "the 13503 device referenced by the current KeyID no longer exists"),
    ("将在当前已确认馈线内优先使用剩余馈线段，数量不足时仅创建缺少数量", "remaining feeder sections of the confirmed feeder will be used first; only the shortage will be created"),
    ("数据库馈线段 BV_ID 为空，无法写入 FeedLine voltype", "database feeder-section BV_ID is empty; FeedLine voltype cannot be written"),
    ("当前馈线段BV_ID为空，禁止重写模型", "current feeder-section BV_ID is empty; model rewrite is blocked"),
    ("同一数据库馈线段被多个FeedLine重复关联", "the same database feeder section is linked by multiple FeedLines"),
    ("数据库事实仍唯一，可选择需要重新分配的FeedLine", "database facts remain unique; the FeedLine requiring reassignment may be selected"),
    ("当前FeedLine旧关联不属于本连接区域确认的馈线、表号/域号不正确或重复占用，将从剩余馈线段中重新分配", "the current FeedLine's old association is outside the feeder confirmed for this connection region, has an incorrect table/domain, or is duplicated; it will be reassigned from remaining feeder sections"),
    ("当前数据库馈线段被多个FeedLine重复占用；该行可由用户选择重新分配", "the current database feeder section is occupied by multiple FeedLines; this row may be selected for reassignment"),
    ("无法从 Bus 附近文字或文件名识别馈线名称", "unable to resolve the feeder name from text near Bus or from the file name"),
    ("组合图中馈线标识 ", "feeder identifier in the composite drawing "),
    (" 出现多个独立空间锚点，禁止自动分配该区域馈线段", " has multiple independent spatial anchors; automatic feeder-section assignment for this region is blocked"),
    ("图上馈线=", "graphical feeder="),
    ("数据库直接匹配数=", "direct database matches="),
    ("FeedLine错误=", "FeedLine errors="),
    ("仍可自动关联=", "still automatically eligible="),

    ("RMU_REFERENCE_IGNORED: 环网柜名称数据库记录不是唯一1条", "RMU_REFERENCE_IGNORED: the RMU-name database result is not exactly one row"),
    ("RMU_REFERENCE_IGNORED: RMU ID或FEEDER_ID为空", "RMU_REFERENCE_IGNORED: RMU ID or FEEDER_ID is empty"),
    ("RMU_REFERENCE_IGNORED: 环网柜当前未关联任何模型", "RMU_REFERENCE_IGNORED: the RMU currently has no linked model"),
    ("RMU_REFERENCE_IGNORED: 没有可验证的正确模型作为馈线依据", "RMU_REFERENCE_IGNORED: there is no verifiable correct model to use as feeder evidence"),
    ("TRUSTED_RMU_REFERENCE: 已验证", "TRUSTED_RMU_REFERENCE: validated "),
    ("条现有模型，FEEDER_ID=", " existing model rows, FEEDER_ID="),
    ("RMU_REFERENCE_IGNORED: 当前已有模型中存在", "RMU_REFERENCE_IGNORED: existing models contain "),
    ("条错误关联", " incorrect association rows"),
    ("该空间区域已有KeyID反查到多个feeder_id=", "existing KeyIDs in this spatial region reverse-resolve to multiple feeder_id values="),
    ("G文件无FeedLine，仅需将根节点facID关联到已唯一确认的馈线；不会创建13503馈线段", "the G file has no FeedLine; only associate the root facID to the uniquely confirmed feeder; no 13503 feeder section will be created"),
    ("G文件无FeedLine，无馈线段需要校验或创建", "the G file has no FeedLine; no feeder section needs validation or creation"),
    ("已有KeyID反查馈线=", "existing KeyID reverse-resolved feeder="),
    ("与图上馈线标题不一致", "does not match the feeder title on the drawing"),
    ("已有KeyID反查状态=", "existing KeyID reverse-resolution status="),
    ("没有可执行的馈线模型校验候选结果", "There is no executable feeder-model validation candidate result"),
    ("馈线模型配置在模型校验后发生变化，请重新执行模型校验", "Feeder-model settings changed after validation; run model validation again"),
    ("当前没有勾选任何可关联馈线段", "No eligible feeder section is currently selected"),
    ("所有勾选馈线对象在执行时均被阻断，没有可安全写回的对象", "All selected feeder objects were blocked during execution; there is no object that can be safely written back"),
    ("G根节点 facID", "G root facID"),
    ("人工确认=", "manual confirmation="),
    ("自动识别=", "auto detection="),
    ("_NOT_EXACTLY_ONE: 输入=", "_NOT_EXACTLY_ONE: input="),
    ("仅关联馈线本体，不创建馈线段", "associate only the feeder itself; do not create feeder sections"),
    ("keyid=<创建后计算>", "keyid=<calculated after creation>"),
    ("无法定位 G 文件安全副本：", "Unable to locate the safe G-file copy: "),
    ("COMPOSITE_UNLINKED: 区域内 FeedLine 未关联", "COMPOSITE_UNLINKED: FeedLine in the region is unlinked"),
    ("当前关联feeder_id=", "current linked feeder_id="),
    ("但本图期望feeder_id=", "but this drawing expects feeder_id="),
    ("EXEC_FEEDER_ROOT_BLOCKED: 仅允许已确认的单馈线图使用 MANUAL/FILENAME 唯一馈线结果回写根 facID", "EXEC_FEEDER_ROOT_BLOCKED: only a confirmed single-feeder drawing may use the unique MANUAL/FILENAME feeder result to write the root facID"),
    # SSH snapshot/runtime diagnostics.
    ("SSH只读文件源：", "SSH read-only file source: "),
    ("获取最新文件：", "Fetching latest file: "),
    ("远程快照下载完成：", "Remote snapshot downloaded: "),
    ("远程文件在下载过程中发生变化：", "Remote file changed during download: "),
    ("正在重新获取服务器最新稳定版本……", "Refetching the latest stable server version..."),
    ("无法取得稳定的服务器文件版本：", "Unable to obtain a stable server file version: "),
    ("次下载期间均发生变化，请稍后重新执行模型校验", "download attempts; the file kept changing. Run model validation again later"),
    ("服务器最终一致性检查发现 ", "Final server consistency check found "),
    (" 个文件在批量下载期间再次更新，正在重新获取最新版本", " files updated again during batch download; refetching the latest versions"),
    ("无法在模型校验开始前取得一组稳定的最新服务器文件：", "Unable to obtain a stable set of latest server files before model validation: "),
    ("请稍后重新执行", "run again later"),
    ("没有选择任何远程 G 文件", "No remote G files are selected"),

    # Strict XML diagnostics remain strict; only the explanatory display text
    # is translated in English mode.
    ("G 文件 XML 解析失败，同时无法读取原始文件进行诊断", "G-file XML parsing failed and the source file could not be read for diagnostics"),
    ("源 G 文件不是可按其 XML 声明正常解析的合法 XML，任务已停止", "The source G file is not valid XML that can be parsed according to its XML declaration; the task has stopped"),
    ("文件：", "File: "),
    ("完整路径：", "Full path: "),
    ("文件大小：", "File size: "),
    ("XML 声明编码：", "XML declared encoding: "),
    ("解析器错误：", "Parser error: "),
    ("诊断读取错误：", "Diagnostic read error: "),
    ("错误位置：", "Error location: "),
    ("第 ", "line "),
    (" 行，第 ", ", column "),
    (" 列", ""),
    ("解析器未提供明确行/列", "The parser did not provide an explicit line/column"),
    ("编码一致性检查：XML 未声明 encoding，无法执行声明编码一致性检查", "Encoding consistency check: XML does not declare encoding, so declared-encoding consistency cannot be checked"),
    ("编码一致性检查：失败；XML 声明了未知/不支持的编码 ", "Encoding consistency check failed: XML declares an unknown/unsupported encoding "),
    ("编码一致性检查：文件字节可以按声明编码 ", "Encoding consistency check: file bytes can be strictly decoded using declared encoding "),
    (" 严格解码；因此更可能是 XML 语法或非法 XML 字符问题", "; therefore the issue is more likely XML syntax or an invalid XML character"),
    ("编码一致性检查：失败；文件声明编码=", "Encoding consistency check failed: declared encoding="),
    ("，但原始字节无法按该编码严格解码", ", but the raw bytes cannot be strictly decoded with that encoding"),
    ("首个解码错误：", "First decode error: "),
    ("约第", "approximately line "),
    ("行/第", "/byte column "),
    ("字节列", ""),
    ("错误附近原始字节(HEX)：", "Raw bytes near error (HEX): "),
    ("错误位置附近原始字节(HEX)：", "Raw bytes around error location (HEX): "),
    ("错误行预览（仅按声明编码用于诊断，不参与解析）：", "Error-line preview (declared encoding only for diagnostics; not used for parsing): "),
    ("判断：该 G 文件可能存在", "Assessment: the G file may contain "),
    ("混合编码、非法字节", "mixed encodings or invalid bytes"),
    ("或其他不符合 XML 规范的字符/语法", "or other characters/syntax that do not conform to XML"),
    ("程序处理策略：严格 XML 解析；不会自动尝试 GBK/GB18030 等其他编码", "Program policy: strict XML parsing; GBK/GB18030 or other encodings are not tried automatically"),
    ("不会自动转码、替换非法字符或修改源 G 文件", "the program does not automatically transcode, replace invalid characters, or modify the source G file"),
    ("处理建议：请从源系统重新导出该 G 文件，确保整个文件使用单一且与 XML declaration 一致的编码", "Recommended action: re-export the G file from the source system and ensure the entire file uses one encoding consistent with its XML declaration"),
    ("如需人工修复，建议统一保存为 UTF-8 并保持 ", "if manual repair is required, save consistently as UTF-8 and keep "),
    (" 一致，确认文件可被标准 XML 解析器打开后再重新执行模型校验", " consistent; confirm the file opens in a standard XML parser before rerunning model validation"),
    ("未声明", "not declared"),
    ("XML 声明中的编码名称无法被 Python 识别", "The encoding name in the XML declaration is not recognized by Python"),
    ("无法按 XML 声明编码生成诊断预览", "Unable to generate a diagnostic preview using the XML-declared encoding"),

    ("XML encoding 声明与实际字节不一致", "XML encoding declaration does not match the actual bytes"),
    ("编码一致性检查：执行失败：", "Encoding consistency check execution failed: "),
    # Common dynamic field labels used inside diagnostic strings.
    ("当前模型需要修复，但数据库BV_ID为空", "The current model requires repair, but database BV_ID is empty"),
    ("数据库设备 BV_ID 为空，无法重新写入 voltype", "Database device BV_ID is empty; voltype cannot be rewritten"),
    ("数据库设备 BV_ID 为空，无法写入 voltype", "Database device BV_ID is empty; voltype cannot be written"),
    ("旧KeyID对应数据库记录已不存在或无法读取", "The database record referenced by the old KeyID no longer exists or cannot be read"),
    ("数据库当前目标设备唯一且有效，允许重新关联", "the current database target device is unique and valid; relinking is allowed"),
    ("数据库当前目标设备唯一且符合规则，允许重新关联", "the current database target device is unique and satisfies the rules; relinking is allowed"),
    ("当前KeyID基础信息与期望一致，但旧模型环网柜归属无法完整验证", "The current KeyID base information matches expectations, but old-model RMU ownership cannot be fully verified"),
    ("当前G文件KeyID格式错误", "The current G-file KeyID format is invalid"),
    ("当前模型需要修复", "The current model requires repair"),
    ("当前模型关联到了其他环网柜", "The current model is linked to another RMU"),
    ("已人工关联，但关联到了其他环网柜", "Manually linked, but linked to another RMU"),
    ("已关联，但关联到了其他环网柜", "Linked, but linked to another RMU"),
    ("已关联，但同一环网柜内设备来自多个数据库环网柜", "Linked, but devices inside the same RMU belong to multiple database RMUs"),
    ("禁止自动处理，请检查已有模型关联", "Automatic processing is blocked; check existing model associations"),
    ("禁止自动关联，请检查现有模型", "Automatic association is blocked; check the existing model"),
    ("禁止自动关联，请检查现有人工模型", "Automatic association is blocked; check the existing manual model"),
    ("逻辑CODE=", "logical CODE="),
    ("在同一环网柜内被多个G图元使用", "is used by multiple G objects inside the same RMU"),
    ("被多个G图元占用", "is occupied by multiple G objects"),
    ("当前环网柜ID=", "current RMU ID="),
    ("设备combined_id=", "device combined_id="),
    ("数据库当前目标设备已通过CODE/图上逻辑CODE及RMU归属校验，允许强制重新关联", "the current database target device passed CODE/graphical logical CODE and RMU ownership validation; forced relinking is allowed"),
    ("本环网柜已关联设备涉及多个combined_id=", "linked devices in this RMU involve multiple combined_id values="),
    ("环网柜数据库记录为0条或多条，当前设备未关联，禁止自动关联", "the RMU database result has zero or multiple rows; the current device is unlinked and automatic association is blocked"),
    ("当前图形环网柜", "current graphical RMU"),
    ("环网柜", "RMU"),
    ("馈线", "feeder"),
    ("数据库", "database"),
    ("当前", "current"),
    ("类型", "type"),
    ("智能", "smart"),
    ("原因", "reason"),
    ("配网模型管理工具", "Distribution Model Manager"),
    ("已启动", "started"),
    ("工作流：", "Workflow: "),
    ("安全模式：", "Safety mode: "),
    ("原始 G 文件永不修改", "original G files are never modified"),
    ("执行关联时只处理 Workspace 中的安全副本", "association modifies only safe copies in Workspace"),
    ("勾选可关联对象", "select eligible objects"),
    ("执行模型关联", "apply model association"),
    ("输入已变化，请重新执行模型校验：", "Input changed. Run Model Validation again: "),
    ("远程 G 文件选择和搜索条件已清空", "remote G-file selection and search filter cleared"),
    ("远程 G 文件选择发生变化", "remote G-file selection changed"),
    ("模型校验", "model validation"),
    ("正在处理", "Processing"),
    ("正在连接 Oracle 数据库", "Connecting to Oracle database"),
    ("Oracle 预检查：正在验证数据库连接", "Oracle pre-check: validating database connection"),
    ("Oracle 预检查：通过", "Oracle pre-check: passed"),
    ("Oracle 数据库预检查通过", "Oracle database pre-check passed"),
    ("正在生成 HTML / CSV 报告", "Generating HTML / CSV reports"),
    ("任务处理完成", "Task completed"),
    ("开始执行", "Starting"),
    ("文件来源", "File source"),
    ("本次输入", "Current input"),
    ("模型校验已生成可关联馈线对象清单", "Model validation generated the eligible feeder object list"),
    ("可关联对象", "eligible objects"),
    ("文件准备失败", "File preparation failed"),
    ("正在进行 Oracle 数据库预检查", "Running Oracle database pre-check"),
    ("关联完成，正在重新校验安全副本", "Association completed; revalidating the safe copy"),
    ("正在生成模型关联完成报告", "Generating the model association result report"),
    ("模型关联写入完成", "Model association write-back completed"),
    ("最终校验", "Final validation"),
    ("当前版本暂未开放", "is not available in the current version"),
    ("请先选择", "Please select"),
    ("目录不存在", "Directory does not exist"),
    ("文件或目录不存在", "File or directory does not exist"),
    ("成功", "Succeeded"),
    ("失败", "Failed"),
    ("保存目录", "Saved to"),
    ("已选择", "Selected"),
    ("个设备", "devices"),
    ("个馈线对象", "feeder objects"),
    ("请在工作区表格中勾选需要处理的设备", "Select the devices to process in the workspace table"),
    ("请在工作区表格中勾选需要处理的馈线或馈线段", "Select the feeders or feeder sections to process in the workspace table"),
    ("检测到 G.facID=", "Detected G.facID="),
    ("馈线已由 facID 强制锁定", "feeder ownership is locked by facID"),
    ("文件名和人工输入禁止参与查询", "file-name and manual input are excluded from resolution"),
    ("当前 G 文件 facID=", "Current G-file facID="),
    ("馈线归属已经由 facID 确定", "feeder ownership has already been determined by facID"),
    ("禁止使用文件名或人工输入重新查询馈线", "file-name or manual feeder re-resolution is prohibited"),
    ("运行日志已复制", "Run log copied"),
    ("打开结果目录", "Open Result Directory"),
    ("关闭", "Close"),
    ("SSH连接通过：", "SSH connection passed: "),
    ("只读模式", "read-only mode"),
    ("已加载", "loaded"),
    ("个 .g 文件", ".g files"),
    ("SSH远程目录：", "SSH remote directory: "),
    ("已排除", "excluded"),
    ("总数", "Total"),
    ("当前显示", "Visible"),
    ("文件来源已切换", "file source changed"),
    ("远程文件列表已刷新", "remote file list refreshed"),
]


def _contains_cjk_text(value: object) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", "" if value is None else str(value)))


# Presentation-only round-trip cache.  It records the exact English rendering
# produced from one Chinese runtime source in this process, so switching back to
# Chinese can restore the original string without reverse-replacing generic
# English words inside engineering/database values.
_RUNTIME_RENDERED_TO_SOURCE: dict[str, str] = {}


def _restore_runtime_chinese(text: object) -> str:
    value = "" if text is None else str(text)
    exact = EN_TO_ZH.get(value)
    if exact is not None:
        return exact
    remembered = _RUNTIME_RENDERED_TO_SOURCE.get(value)
    if remembered is not None:
        return remembered
    return value


def translate_runtime_text(text: object, language: str | None) -> str:
    lang = normalize_language(language)
    source = "" if text is None else str(text)
    if lang != LANG_EN:
        # Chinese is the canonical/source UI.  Restore only exact catalog entries
        # or exact English renderings produced earlier in this process.  Do not
        # reverse generic English fragments, because engineering values may contain
        # words such as current/type/status/region legitimately.
        return _restore_runtime_chinese(source)

    value = tr(source, lang)
    # Preserve engineering/status codes and raw DB/XML values; only replace
    # stable user-facing Chinese phrases embedded in dynamic messages.
    for zh, en in sorted(
        _RUNTIME_REPLACEMENTS,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        value = value.replace(zh, en)
    # Normalize Chinese punctuation that belongs to the presentation text.
    # Engineering values/status codes remain untouched.
    value = (
        value.replace("；", "; ")
        .replace("：", ": ")
        .replace("，", ", ")
        .replace("。", ".")
    )
    if value != source:
        _RUNTIME_RENDERED_TO_SOURCE[value] = source
    return value


def retranslate_qt_tree(root, language: str | None) -> None:
    """Translate an already-created Qt widget tree without touching business data.

    v4.2.13 also tracks *dynamic* presentation changes.  Several integrated pages
    update labels/status rows after the first language pass (Admin state, element
    cache status, model settings, etc.).  Older builds remembered only the first
    source string, so later Chinese text could reappear in English mode.  The
    source/last-rendered pair below promotes a genuinely new UI value to the new
    canonical source before translating it.
    """
    try:
        from PySide6.QtCore import Qt, QObject
        from PySide6.QtWidgets import (
            QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit,
            QListWidget, QTabWidget, QTableWidget, QPlainTextEdit, QTextEdit,
        )
    except Exception:
        return

    lang = normalize_language(language)

    def _canonical_source(current: str, saved, last_rendered) -> str:
        """Keep Chinese as the immutable presentation source across language switches.

        A runtime widget may be created while English mode is active, or feature code
        may update its text after translation.  Never promote an English rendering over
        a saved Chinese source.  If the current English text can be reversed through the
        exact/runtime catalogs, store the recovered Chinese source instead.
        """
        current = "" if current is None else str(current)
        if saved is None:
            recovered = _restore_runtime_chinese(current)
            return recovered if recovered != current else current

        source = str(saved)
        last = None if last_rendered is None else str(last_rendered)
        if current == source or (last is not None and current == last):
            return source

        # New Chinese feature text is a genuine source update.
        if _contains_cjk_text(current):
            return current

        # A known English rendering is never a new canonical source.
        recovered = _restore_runtime_chinese(current)
        if recovered != current:
            return recovered

        # Protect an existing Chinese source from arbitrary English renderings.
        if _contains_cjk_text(source):
            return source

        # Pure engineering / non-localized values may legitimately change.
        return current

    def _source(obj, key: str, current: str) -> str:
        source_prop = f"_i18n_source_{key}"
        rendered_prop = f"_i18n_rendered_{key}"
        saved = obj.property(source_prop)
        last_rendered = obj.property(rendered_prop)
        source = _canonical_source(current, saved, last_rendered)
        if saved is None or str(saved) != source:
            obj.setProperty(source_prop, source)
        return source

    def _render(obj, key: str, current: str) -> str:
        source = _source(obj, key, current)
        rendered = translate_runtime_text(source, lang)
        obj.setProperty(f"_i18n_rendered_{key}", rendered)
        return rendered

    objects = [root]
    try:
        objects.extend(root.findChildren(QObject))
    except Exception:
        pass

    for obj in objects:
        try:
            if isinstance(obj, QGroupBox):
                obj.setTitle(_render(obj, "title", obj.title()))
            elif isinstance(obj, (QLabel, QAbstractButton)):
                obj.setText(_render(obj, "text", obj.text()))

            if hasattr(obj, "toolTip") and hasattr(obj, "setToolTip"):
                current_tip = obj.toolTip()
                if current_tip:
                    obj.setToolTip(_render(obj, "tooltip", current_tip))
            if hasattr(obj, "statusTip") and hasattr(obj, "setStatusTip"):
                current_status_tip = obj.statusTip()
                if current_status_tip:
                    obj.setStatusTip(_render(obj, "statustip", current_status_tip))

            if isinstance(obj, QLineEdit):
                current = obj.placeholderText()
                if current:
                    obj.setPlaceholderText(_render(obj, "placeholder", current))

            if isinstance(obj, (QPlainTextEdit, QTextEdit)) and obj.isReadOnly():
                current = obj.toPlainText()
                if current:
                    obj.setPlainText(_render(obj, "plainText", current))

            if isinstance(obj, QComboBox):
                role_source = int(Qt.UserRole) + 91
                role_rendered = int(Qt.UserRole) + 93
                for i in range(obj.count()):
                    current = obj.itemText(i)
                    source = obj.itemData(i, role_source)
                    last = obj.itemData(i, role_rendered)
                    canonical = _canonical_source(current, source, last)
                    if source is None or str(source) != canonical:
                        obj.setItemData(i, canonical, role_source)
                    source = canonical
                    rendered = translate_runtime_text(source, lang)
                    obj.setItemData(i, rendered, role_rendered)
                    obj.setItemText(i, rendered)

            if isinstance(obj, QListWidget):
                role_source = int(Qt.UserRole) + 91
                role_rendered = int(Qt.UserRole) + 93
                for i in range(obj.count()):
                    item = obj.item(i)
                    current = item.text()
                    source = item.data(role_source)
                    last = item.data(role_rendered)
                    canonical = _canonical_source(current, source, last)
                    if source is None or str(source) != canonical:
                        item.setData(role_source, canonical)
                    source = canonical
                    rendered = translate_runtime_text(source, lang)
                    item.setData(role_rendered, rendered)
                    item.setText(rendered)

            if isinstance(obj, QTabWidget):
                for i in range(obj.count()):
                    widget = obj.widget(i)
                    current = obj.tabText(i)
                    source = widget.property("_i18n_tab_text")
                    last = widget.property("_i18n_tab_rendered")
                    canonical = _canonical_source(current, source, last)
                    if source is None or str(source) != canonical:
                        widget.setProperty("_i18n_tab_text", canonical)
                    source = canonical
                    rendered = translate_runtime_text(source, lang)
                    widget.setProperty("_i18n_tab_rendered", rendered)
                    obj.setTabText(i, rendered)

            if isinstance(obj, QTableWidget):
                header_source_role = int(Qt.UserRole) + 92
                header_rendered_role = int(Qt.UserRole) + 94
                for i in range(obj.columnCount()):
                    item = obj.horizontalHeaderItem(i)
                    if item is None:
                        continue
                    current = item.text()
                    source = item.data(header_source_role)
                    last = item.data(header_rendered_role)
                    canonical = _canonical_source(current, source, last)
                    if source is None or str(source) != canonical:
                        item.setData(header_source_role, canonical)
                    source = canonical
                    rendered = translate_runtime_text(source, lang)
                    item.setData(header_rendered_role, rendered)
                    item.setText(rendered)

                # Body cells can contain UI-owned states such as "服务器图元库" /
                # "READY · 服务器已同步".  Engineering IDs, names and paths are
                # untouched because the translator has no mapping for them.
                cell_source_role = int(Qt.UserRole) + 95
                cell_rendered_role = int(Qt.UserRole) + 96
                signals_were_blocked = obj.signalsBlocked()
                obj.blockSignals(True)
                try:
                    for row in range(obj.rowCount()):
                        for col in range(obj.columnCount()):
                            item = obj.item(row, col)
                            if item is None:
                                continue
                            current = item.text()
                            source = item.data(cell_source_role)
                            last = item.data(cell_rendered_role)
                            canonical = _canonical_source(current, source, last)
                            if source is None or str(source) != canonical:
                                item.setData(cell_source_role, canonical)
                            source = canonical
                            rendered = translate_runtime_text(source, lang)
                            item.setData(cell_rendered_role, rendered)
                            if current != rendered:
                                item.setText(rendered)
                finally:
                    obj.blockSignals(signals_were_blocked)
        except RuntimeError:
            continue

# v4.1.109 fixed Jeddah RMU strict outside-frame TOP-only naming.
ZH_TO_EN.update({
    "上方（固定）": "Top (Fixed)",
    "右侧（禁用）": "Right (Disabled)",
    "左侧（禁用）": "Left (Disabled)",
    "下方（禁用）": "Bottom (Disabled)",
    "框外图上文字：仅上方（固定）": "Outside-frame Text: Top Only (Fixed)",
    "吉达现场环网柜名称始终以 RMU 矩形框为几何基准，只允许使用完整位于矩形框外、且在矩形框上方的 Text。右侧、左侧、下方和全局兜底全部禁用；上方找不到有效 Text 就直接判定环网柜名称识别失败。框内 Text 永远不能作为环网柜名称。": "Jeddah RMU names use the RMU rectangle as the geometry reference. Only Text whose entire bounding box is outside every RMU frame and above the target frame is allowed. Right, left, bottom, and global fallback are disabled; if no valid top Text exists, RMU name recognition fails.",
})


# v4.2.8 integrated Jeddah English UI completeness.
# These are presentation-only translations for the merged Model + Graphics application.
ZH_TO_EN.update({
    "图形工作区": "Graphics Workspace",
    "图元管理": "Element Management",
    "公共配置同步": "Shared Configuration Sync",
    "中央服务器": "Central Server",
    "中央服务器用户名": "Central Server Username",
    "中央服务器密码": "Central Server Password",
    "中央配置目录": "Central Configuration Directory",
    "保存本机连接配置": "Save Local Connection Settings",
    "连接并同步中央配置": "Connect and Sync Central Configuration",
    "保存并发布全部配置": "Save and Publish All Configuration",
    "抢占 Admin 权限": "Take Over Admin",
    "当前机器已是 Admin": "This Machine Is Admin",
    "释放 Admin 权限": "Release Admin",
    "公共配置同步说明": "Shared Configuration Sync Help",
    "软件启动只读取本机缓存，不会自动访问中央仓库。普通客户端可以修改并保存本机配置，也可以手动同步中央共享配置；只有上传/发布配置到中央仓库需要 Admin 权限。任何机器都可以手动抢占 Admin。当 Admin 被其他机器抢占后，本机仅后台检查很小的 instance.json 并自动降权；该检查不会同步数据库、服务器或图元配置。": "At startup the application reads local cache only and does not contact the central repository. Standard clients may edit and save local settings and manually sync shared configuration. Publishing to the central repository requires Admin permission. Any machine may explicitly take over Admin. If another machine takes ownership, this client only checks the small instance.json ownership record in the background and automatically drops Admin rights; this check never syncs database, server, or element settings.",
    "中央仓库连接配置已保存到本机；未访问服务器。": "Central repository connection settings were saved locally; no server was contacted.",
    "保存中央仓库连接配置失败": "Failed to Save Central Repository Connection Settings",
    "读取中央配置": "Sync Central Configuration",
    "中央配置已手动同步，并已覆盖本机的图元标记、数据库和文件服务器缓存。": "Central configuration was synced manually and replaced the local element marks, database settings, and file-server cache.",
    "读取中央配置失败": "Central Configuration Sync Failed",
    "中央配置发布完成": "Central Configuration Published",
    "中央配置发布失败": "Central Configuration Publish Failed",
    "Admin 抢占完成": "Admin Takeover Complete",
    "抢占 Admin 失败": "Admin Takeover Failed",
    "初始化中央配置": "Initialize Central Configuration",
    "中央配置初始化完成": "Central Configuration Initialized",
    "中央配置初始化失败": "Central Configuration Initialization Failed",
    "Admin 权限已释放": "Admin Released",
    "释放 Admin 失败": "Release Admin Failed",
    "语言切换立即生效，并自动保存最后一次选择。": "Language changes take effect immediately and the last selection is saved automatically.",
    "安全策略": "Safety Policy",
    "异常小尺寸图元处理": "Abnormal Small Element Processing",
    "ID 检查与修复": "ID Check & Repair",
    "环网柜处理": "RMU Processing",
    "Poke 跳转处理": "Poke Navigation Processing",
    "通用基础处理": "General Processing",
    "馈线图合并": "Feeder Diagram Merge",
    "图形边距调整": "Drawing Margin Adjustment",
    "图框添加": "Drawing Frame",
    "线路正交化": "Orthogonalize Lines",
    "吉达图形批处理": "Jeddah Graphics Batch Processing",
    "柱上变压器熔断器替换": "Pole Transformer + Fuse Replacement",
    "环网柜 EFI 保护图元添加": "RMU EFI Protection Element Addition",
    "图形处理类型": "Graphics Operation",
    "同步主程序配置到图形工作区": "Sync Main Settings to Graphics Workspace",
    "主程序图元管理": "Main Element Management",
    "主程序数据库/连接": "Main Database / Connections",
    "首次进入时加载图形处理模块……": "Loading the graphics module for first use...",
    "吉达图形处理已合并到自动模型关联软件。模型业务继续使用 Jeddah DMM 规则；图形处理继续使用 GFileStudio v2.18.257 的成熟处理引擎。": "Jeddah graphics processing is integrated into the automatic model-association application. Model workflows continue to use Jeddah DMM rules, while graphics workflows continue to use the mature GFileStudio v2.18.257 processing engine.",
    "统一入口：这里直接处理 G 图形；原始 G 永不覆盖。现场批处理继续遵守“只有实际修改过的 G 才输出”的规则。": "Unified entry point for G-graphics processing. Original G files are never overwritten. Site batch processing continues to output only files that were actually modified.",
    "仅把当前 DMM 本机缓存中的 Oracle、业务 G 文件 SSH、图元目录和中央仓库参数投影到图形工作区；不会连接网络。": "Projects the current local DMM Oracle, business G-file SSH, element-directory, and central-repository settings into the Graphics Workspace without any network connection.",
    "图形工作区配置已同步": "Graphics Workspace Settings Synced",
    "图元定义来源": "Element Definition Source",
    "刷新图元列表": "Refresh Element List",
    "下载所选图元": "Download Selected Elements",
    "载入本地标记": "Load Local Marks",
    "保存到本地缓存": "Save to Local Cache",
    "保存并同步到中央仓库": "Save and Publish to Central Repository",
    "同步中央配置仓库配置": "Sync Central Repository Configuration",
    "导入共享配置": "Import Shared Configuration",
    "导出共享配置": "Export Shared Configuration",
    "更多操作": "More Actions",
    "标记搜索": "Mark Search",
    "筛选": "Filter",
    "输入图元文件名、完整路径、分类标记或备注": "Enter element file name, full path, classification mark, or remark",
    "图元定义文件": "Element Definition File",
    "标准来源": "Standard Source",
    "分类标记": "Classification Mark",
    "备注": "Remark",
    "尚未手动同步服务器图元；当前仅使用本地缓存。": "Server elements have not been refreshed manually; local cache is currently in use.",
    "维护服务器图元文件与设备分类标记。进入页面只读取本地缓存，不会自动访问服务器；只有点击“刷新图元列表”才会重新读取。普通客户端可以修改并保存本机缓存；配置操作分为三个独立动作：保存到本地缓存、Admin 保存并同步到中央仓库、手动同步中央配置仓库并覆盖本地共享配置。原始服务器文件只读，不会被修改。": "Maintain server element files and device classification marks. Opening this page reads local cache only and never contacts the server automatically; the server is accessed only when Refresh Element List is clicked. Standard clients may edit and save local cache. Configuration actions are separate: save locally, Admin publish to the central repository, or manually sync central shared configuration over the local cache. Source server files remain read-only and are never modified.",
    "仅保存当前图元服务器设置和图元分类标记到本机缓存，不访问中央仓库。": "Save the current element-server settings and classification marks to local cache only; do not contact the central repository.",
    "仅 Admin 可用：先保存到本地缓存，再把当前本机共享配置发布到中央仓库。": "Admin only: save locally first, then publish the current shared configuration to the central repository.",
    "手动读取中央共享配置并覆盖本机缓存；普通客户端也可使用。": "Manually read the central shared configuration and replace the local cache; available to standard clients too.",
    "当前操作会把共享配置上传到中央仓库，只有 Admin 可以执行；请先到【设置】抢占 Admin。": "This action uploads shared configuration to the central repository and requires Admin permission. Take over Admin in Settings first.",
    "一键多模型关联": "Multi-Model Association",
    "一键多模型关联配置": "Multi-Model Association Settings",
    "柱上开关模型": "Pole Switch Model",
    "柱上变压器模型": "Pole Transformer Model",
    "熔断器模型": "Fuse Model",
    "配网主站设备关联": "Master Station Device Association",
    "全选": "Select All",
    "全不选": "Select None",
    "请选择需要关联的模型，然后先执行模型校验。": "Select the models to associate, then run Model Validation first.",
    "本页只负责调用现有独立模型，不复制、不重写任何业务规则。勾选哪些模块，一键执行时就按固定安全顺序调用这些模块；每个独立模型仍可在上方‘模型类型’中单独校验和关联。": "This page only orchestrates existing independent models and does not copy or rewrite any business rule. Selected modules are called in a fixed safe order, while each model remains independently available from Model Type.",
    "固定执行顺序：RMU → 柱上开关 → 柱上变压器 → 熔断器 → 配网主站设备 → 馈线。前一模块的安全回写结果会继续作为后一模块的输入。": "Fixed order: RMU → Pole Switch → Pole Transformer → Fuse → Master Station Devices → Feeder. Safe write-back output from each module becomes the input to the next module.",
    "安全规则：一键模式只编排现有模块；原始 G 文件和 SSH 服务器文件不修改，所有写回累计在同一份 Workspace 安全副本中。": "Safety rule: multi-model mode only orchestrates existing modules. Original G files and SSH server files are never modified; all write-back accumulates in the same Workspace safe copy.",
    "馈线自动关联完整逻辑（只读说明）": "Feeder Automatic Association Logic (Read-only)",
    "馈线数据库补齐选项": "Feeder Database Completion Options",
    "RMU 自动关联完整逻辑（只读说明）": "RMU Automatic Association Logic (Read-only)",
    "柱上开关自动关联完整逻辑（只读说明）": "Pole Switch Automatic Association Logic (Read-only)",
    "柱上变压器自动关联完整逻辑（只读说明）": "Pole Transformer Automatic Association Logic (Read-only)",
    "熔断器自动关联完整逻辑（只读说明）": "Fuse Automatic Association Logic (Read-only)",
    "配网主站设备自动关联完整逻辑（只读说明）": "Master Station Device Automatic Association Logic (Read-only)",
    "1. 识别哪些设备": "1. Devices Recognized",
    "2. 怎样找图上名称": "2. Graphical Name Resolution",
    "2. 怎样找柱上变压器名称": "2. Pole Transformer Name Resolution",
    "2. 先找最近柱上变压器": "2. Find the Nearest Pole Transformer First",
    "2. 怎样确定厂站 / 馈线 / 间隔": "2. Resolve Substation / Feeder / Bay",
    "2. 柜内设备如何命名": "2. In-cabinet Device Naming",
    "2. 怎样处理 G 文件中的馈线段": "2. Process Feeder Sections in the G File",
    "3. 查询数据库前怎样处理名称": "3. Normalize Name Before Database Query",
    "3. 怎样得到熔断器名称": "3. Fuse Name Resolution",
    "3. 数据库和馈线校验": "3. Database and Feeder Validation",
    "3. 数据库怎样校验": "3. Database Validation",
    "3. 怎样从数据库选目标设备": "3. Select the Target Database Device",
    "3. 数据库补齐边界": "3. Database Completion Boundary",
    "4. 数据库关联链路": "4. Database Association Path",
    "4. 当前模型如何判断": "4. Current Model State",
    "4. 当前 KeyID 如何判断": "4. Current KeyID Evaluation",
    "4. 关联前安全校验": "4. Pre-association Safety Validation",
    "4. KeyID 与安全校验": "4. KeyID and Safety Validation",
    "5. 真正执行时回写哪些字段": "5. Fields Written During Execution",
    "6. 模块边界": "6. Module Boundary",
})

_RUNTIME_REPLACEMENTS.extend([
    ("当前仅使用本机缓存；启动未访问中央仓库。本机配置可修改保存，可手动同步中央配置；发布中央仓库需要 Admin。", "Using local cache only; startup did not contact the central repository. Local settings may be edited and saved, and central configuration may be synced manually; publishing requires Admin."),
    ("尚未读取中央配置；本机配置可修改保存，发布中央仓库需要 Admin。", "Central configuration has not been read yet; local settings may be edited and saved, and publishing requires Admin."),
    ("中央配置当前没有 Admin；任意客户端都可以抢占 Admin。", "The central configuration currently has no Admin; any client may take over Admin."),
    ("中央共享配置尚未初始化；请先抢占 Admin，再用本机配置发布。", "Central shared configuration is not initialized; take over Admin first, then publish the local configuration."),
    ("中央配置暂时不可用，将继续使用本机缓存。", "Central configuration is temporarily unavailable; local cache will continue to be used."),
    ("中央配置同步已关闭。", "Central configuration sync is disabled."),
    ("状态：", "Status: "),
    ("当前 Admin：", "Current Admin: "),
    ("当前机器为 Admin", "this machine is Admin"),
    ("本机为普通客户端", "this machine is a standard client"),
    ("未记录机器信息", "machine information not recorded"),
    ("连接参数：", "Connection settings: "),
    ("可用图元定义：", "Available element definitions: "),
    ("图元分类标记：", "Element classification marks: "),
    (" 项", " items"),
])


# v4.2.8 English console/runtime completeness for all model modules.
ZH_TO_EN.update({
    "\n[批量校验 ": "\n[Batch Validation ",
    "批量校验完成：": "Batch validation completed: ",
    "批量写回冲突检查：发现 ": "Batch write-back conflict check: found ",
    " 个属性冲突；冲突对象将在批量确认列表中禁用。": " attribute conflicts; conflicting objects will be disabled in the batch confirmation list.",
    "批量写回冲突检查：通过。": "Batch write-back conflict check: passed.",
    "批量模型校验完成": "Batch model validation completed",
    "\n[批量关联 ": "\n[Batch Association ",
    "：候选 ": ": candidates ",
    "，成功写回 ": ", written successfully ",
    "批量模型关联完成": "Batch model association completed",
    "批量校验：": "Batch validation: ",
    "批量关联：": "Batch association: ",
    "：本次没有需要写回的对象，跳过。": ": no objects require write-back in this run; skipped.",
    "] 柱上开关识别完成：devref目标=": "] Pole-switch recognition completed: devref targets=",
    "；图级馈线=": "; graph feeder=",
    "[发现柱上开关] 文件=": "[Pole switch found] file=",
    "；名称=": "; name=",
    "；方向=": "; direction=",
    "；距离=": "; distance=",
    "正在处理柱上开关 ": "Processing pole switch ",
    "] 配网主站设备识别完成：图元=": "] Master-station device recognition completed: objects=",
    "] 主站设备上下文已由文件名确定：ST_ID=": "] Master-station context resolved from file name: ST_ID=",
    "] 主站设备关联阻断：": "] Master-station association blocked: ",
    "文件名馈线/Bay上下文无法唯一确定。": "The file-name feeder/Bay context cannot be uniquely resolved.",
    "：文件名馈线=": ": file-name feeder=",
    "正在处理主站设备 ": "Processing master-station device ",
    "] 馈线识别通过：来源=": "] Feeder resolution passed: source=",
    "；锚点=": "; anchor=",
    "目录馈线模式：逐文件仅按文件名 → 405/substation → 13500/dms_feeder_device 确定馈线；已建立可信单馈线指纹=": "Directory feeder mode: each file resolves its feeder only through file name → 405/substation → 13500/dms_feeder_device; trusted single-feeder fingerprints built=",
    "] 熔断器识别完成：FUSE总数=": "] Fuse recognition completed: total FUSE=",
    "；已独占匹配柱上变压器=": "; exclusively matched pole transformers=",
    "；仅统计不处理=": "; counted only / not processed=",
    "[发现熔断器] 文件=": "[Fuse found] file=",
    "；变压器分配=": "; transformer assignment=",
    "；最近柱上变压器=": "; nearest pole transformer=",
    "；变压器XML_ID=": "; transformer XML_ID=",
    "；设备距离=": "; device distance=",
    "；变压器占用FUSE=": "; transformer assigned FUSE=",
    "；分配说明=": "; assignment note=",
    "；变压器名称方向=": "; transformer-name direction=",
    "；变压器名称距离=": "; transformer-name distance=",
    "；变压器名称判定=": "; transformer-name decision=",
    "；熔断器名称=": "; fuse name=",
    "正在处理熔断器 ": "Processing fuse ",
    "RMU 保护/EFI 分类标记：RMU_PWBH_EFI；已加载标记图元记录=": "RMU protection/EFI classification: RMU_PWBH_EFI; loaded marked-element records=",
    "；运行时按当前 G devref 精确匹配任意一条标记记录，不依赖具体图元文件名。": "; at runtime, the current G devref is matched exactly against any marked record and does not depend on a specific element file name.",
    "[发现环网柜] 文件=": "[RMU found] file=",
    "；框XML_ID=": "; frame XML_ID=",
    "；数据库匹配=": "; database matches=",
    "策略清理准备：RMU=": "Policy cleanup prepared: RMU=",
    "；仅SMART策略下清除非智能环网柜已有保护/EFI关联。": "; under SMART-only policy, existing protection/EFI links are cleared from non-smart RMUs.",
    "：同名总数=": ": same-name total=",
    "；当前图级 FEEDER_ID=": "; current graph FEEDER_ID=",
    "；当前馈线内匹配=": "; matches within current feeder=",
    "] 柱上变压器识别完成：POLE_TRANSFORMER=": "] Pole-transformer recognition completed: POLE_TRANSFORMER=",
    "[发现柱上变压器] 文件=": "[Pole transformer found] file=",
    "正在处理柱上变压器 ": "Processing pole transformer ",
    "[柱上变压器回写] XML ID=": "[Pole transformer write-back] XML ID=",
    "；输出=": "; output=",
    "[柱上变压器回写确认] XML ID=": "[Pole transformer write-back verification] XML ID=",
    "；已从输出 G 复核成功": "; verified successfully from output G",
    "[馈线识别] 唯一来源=文件名；文件=": "[Feeder resolution] only source=file name; file=",
    "；目标NAME=": "; target NAME=",
    "[发现馈线] 文件名唯一确定：FEEDER_ID=": "[Feeder found] uniquely resolved from file name: FEEDER_ID=",
    "；站点=": "; substation=",
    "；路径=": "; path=",
    "图级馈线识别通过：唯一来源=文件名 -> 405/substation -> 13500/dms_feeder_device；FEEDER_ID=": "Graph feeder resolution passed: only source=file name -> 405/substation -> 13500/dms_feeder_device; FEEDER_ID=",
    "\n开始批量模型校验：": "\nStarting batch model validation: ",
    "批量模型关联完成：候选=": "Batch model association completed: candidates=",
    "；原始 G 文件未修改；最终输出目录=": "; original G files unchanged; final output directory=",
    "批量任务失败：": "Batch task failed: ",
    "关联失败 CSV：": "Association Failures CSV: ",
    "本次批量校验已锁定同一 remote_input 快照；后续所有勾选模块和批量关联均使用这一快照。": "This batch validation locked one remote_input snapshot; all selected modules and the subsequent batch association use the same snapshot.",
    "批量确认：": "Batch confirmation: ",
    " 个跨模块冲突对象已在待关联列表中禁用，其余 ": " cross-module conflict objects are disabled in the candidate list; the remaining ",
    " 个安全对象可由用户确认后执行。": " safe objects can be executed after user confirmation.",
    "保存批量关联 console.log 失败：": "Failed to save batch-association console.log: ",
    "柱上开关 CSV：": "Pole Switch CSV: ",
    "关联完成失败明细 CSV：": "Association Result Failure Details CSV: ",
    "图形工作区配置桥接失败：": "Graphics Workspace configuration bridge failed: ",
    "柱上变压器 CSV：": "Pole Transformer CSV: ",
    "熔断器 CSV：": "Fuse CSV: ",
    "关联完成柱上开关 CSV：": "Association Result Pole Switch CSV: ",
    "模型校验已生成可关联柱上开关清单：可关联/重新关联设备 ": "Model validation generated the eligible Pole Switch list: eligible/relinkable devices ",
    "配网主站设备 CSV：": "Master Station Device CSV: ",
    "关联完成柱上变压器 CSV：": "Association Result Pole Transformer CSV: ",
    "模型校验已生成可关联熔断器清单：可关联/重新关联设备 ": "Model validation generated the eligible Fuse list: eligible/relinkable devices ",
    "关联完成熔断器 CSV：": "Association Result Fuse CSV: ",
    "模型校验已生成可关联配网主站设备清单：可关联/重新关联设备 ": "Model validation generated the eligible Master Station Device list: eligible/relinkable devices ",
    "模型校验已生成可关联柱上变压器清单：可关联/重新关联设备 ": "Model validation generated the eligible Pole Transformer list: eligible/relinkable devices ",
    "关联完成配网主站设备 CSV：": "Association Result Master Station Device CSV: ",
})

# Keep reverse lookup complete for strings added by the merged-app v4.2.8 updates.
EN_TO_ZH.update({value: key for key, value in ZH_TO_EN.items()})

# v4.2.13 English UI completeness hardening.
# The unified application contains several late-added static help/status paragraphs
# and model-description cards that were created after the original i18n catalog.
# Keep the Chinese source as canonical UI text and translate only at presentation time.
ZH_TO_EN.update({
    # Settings / central configuration runtime text.
    "当前仅使用本机缓存；软件启动不会访问中央配置。只有手动点击【连接并同步中央配置】才会读取并覆盖本机共享配置缓存。":
        "Using local cache only. Application startup does not access central configuration. The local shared-configuration cache is read and replaced only after the operator explicitly clicks Connect and Sync Central Configuration.",
    "普通客户端可修改、测试、刷新并保存本机配置，也可手动同步中央配置；只有【保存并同步到中央仓库】需要先抢占 Admin。":
        "Standard clients may edit, test, refresh, and save local configuration, and may manually sync central configuration. Only Save and Publish to Central Repository requires Admin ownership.",
    "服务器图元库": "Server Element Library",
    "本地缓存": "Local Cache",
    "服务器图元已更新（本地标记已保留，请确认）": "UPDATED · server element changed; local mark preserved, please confirm",
    "本地缓存与服务器一致": "READY · synchronized with server",
    "服务器新增图元（待标记）": "NEW · server element, pending classification",
    "服务器不存在（本地标记已保留）": "MISSING · not on server; local mark preserved",
    "已读取": "READY · server element loaded",
    "已保存标记": "LOCAL · classification saved",
    "MISSING · 服务器不存在": "MISSING · Not on Server",
    "READY · 服务器已同步": "READY · Server Synchronized",
    "NEW · 待标记": "NEW · Pending Classification",
    "UPDATED · 请确认": "UPDATED · Please Confirm",
    "ERROR · 读取失败": "ERROR · Read Failed",
    "WARN · 属性解析失败": "WARN · Attribute Parse Failed",
    "READY · 服务器已读取": "READY · Loaded from Server",
    "LOCAL · 已保存标记": "LOCAL · Classification Saved",
    "普通客户端可修改、测试、刷新并保存本机配置，也可手动同步中央配置；只有【保存并同步到中央仓库】需要先抢占 Admin。":
        "Standard clients may edit, test, refresh, and save local configuration, and may manually sync central configuration. Only Save and Publish to Central Repository requires Admin ownership.",

    # RMU model settings visible in English mode.
    "按指定方向": "Use Fixed Direction",
    "保护 / EFI 关联范围": "Protection / EFI Association Scope",
    "所有环网柜都关联保护 / EFI": "Associate Protection / EFI for All RMUs",
    "仅 SMART 智能环网柜关联保护 / EFI": "Associate Protection / EFI for SMART RMUs Only",
    "环网柜名称来源": "RMU Name Source",
    "RMU 环网柜只有在矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 时才识别。环网柜名称始终以 RMU 矩形框为基准，只允许识别完整位于矩形框外、且在矩形框上方的 Text；右侧、左侧、下方和全局兜底全部禁用。上方找不到名称即判定环网柜名称识别失败。设备命名规则固定使用图上文字，不再读取三类设备 XML 的 p_NameString：CBreakerDis 使用图上名称，接地刀闸使用开关名+D，BusDis 固定使用 BUS。RMU 内保护/EFI 图元只认图元管理中的 RMU_PWBH_EFI 分类标记：可同时标记多个图元文件，默认按环网柜 ID 查询 13533 dms_relay_sig，仅 CODE=EFI INDICATOR 才参与关联，默认回写 value 域 keyid1（域号 40）；设备表号和域号属于固定工程规则，不允许用户修改。单线图中的环网柜关联会先按 G 文件名唯一确定图级馈线，并只在该 FEEDER_ID 下选择同名环网柜；其它馈线上的同名记录不会阻断。合成图和环网图保持原 RMU 逻辑；同一 G 图内环网柜名称重复时仍按原规则阻断。":
        "An RMU is recognized only when its rectangle contains CBreakerDis, BusDis, and ZhaiWaiJieDiDaoZha. The RMU rectangle is always the geometry reference for its name: only Text fully outside and above the rectangle is accepted; right, left, bottom, and global fallback are disabled. If no valid top Text exists, RMU-name resolution fails. Device names always come from graphical text and never from XML p_NameString: CBreakerDis uses its graphical name, the grounding switch uses paired-breaker-name + D, and BusDis is always BUS. RMU protection/EFI objects are recognized only through the RMU_PWBH_EFI classification in Element Management. Multiple element files may carry that mark. Association queries 13533/dms_relay_sig by RMU ID and uses only CODE=EFI INDICATOR, writing keyid1 in the value slot with Domain 40. Table/domain definitions are fixed engineering rules. For single-line drawings, the graph feeder is uniquely resolved from the G filename first and same-name RMUs are selected only inside that FEEDER_ID; same-name records on other feeders do not block. Composite/ring drawings retain the existing RMU rules, and duplicate RMU names inside one G drawing remain blocked.",
    "吉达现场环网柜名称始终以 RMU 矩形框为几何基准，只允许使用完整位于矩形框外、且在矩形框上方的 Text。右侧、左侧、下方和全局兜底全部禁用；上方找不到有效 Text 就直接判定环网柜名称识别失败。框内 Text 永远不能作为环网柜名称。开关名称不再读取 XML p_NameString。CBreakerDis 仅使用环网柜内图上文字；接地刀闸逻辑名称=配对开关名+D；BusDis 固定为 BUS。保护/EFI 不绑定具体图元文件名；凡图元管理分类标记为 RMU_PWBH_EFI 的 pwbh 图元都按固定 CODE=EFI INDICATOR 关联；数据库表号和域号为固定工程规则。当选择“仅 SMART”时，NORMAL 环网柜不会新增保护/EFI关联；如果已有 EFI KeyID，执行关联时会自动清除关联值，保留原属性键，回到现场未关联 EFI 的属性状态。图上名称无法唯一识别，或与数据库 CODE 校验失败时，会明确告警对应环网柜。单线图必须先由 G 文件名唯一确定图级馈线，并校验目标环网柜属于该 FEEDER_ID；数据库其它馈线上的同名环网柜会被忽略。当前馈线下没有同名环网柜，或当前馈线下仍有多条同名记录时禁止关联；facID 不作为环网柜名称匹配条件。":
        "At the Jeddah site, the RMU rectangle is always the geometry reference for the cabinet name. Only Text fully outside and above the rectangle is allowed. Right, left, bottom, and global fallback are disabled; if no valid top Text exists, RMU-name resolution fails. Text inside the frame can never be the RMU name. Breaker naming no longer reads XML p_NameString. CBreakerDis uses only graphical text inside the RMU; the grounding-switch logical name is paired-breaker-name + D; BusDis is always BUS. Protection/EFI is not tied to a specific element filename: every pwbh element classified as RMU_PWBH_EFI in Element Management is associated using fixed CODE=EFI INDICATOR; the database table/domain are fixed engineering rules. With SMART-only scope, NORMAL RMUs do not receive new protection/EFI links; if an EFI KeyID already exists, association clears the linked value while preserving the original attribute keys, returning the object to the field unlinked-EFI state. A non-unique graphical name or database CODE mismatch produces an explicit RMU warning. A single-line drawing must first resolve one graph feeder from the G filename and the target RMU must belong to that FEEDER_ID. Same-name RMUs on other feeders are ignored. If the current feeder has zero or multiple same-name RMUs, association is blocked. facID is not an RMU-name matching condition.",
    "1. 环网柜如何识别": "1. RMU Recognition",
    "只有矩形框内同时包含 CBreakerDis、BusDis、ZhaiWaiJieDiDaoZha 才识别为 RMU。RMU 名称只从完整位于矩形框外、且在矩形框上方的 Text 获取；不允许右侧、左侧、下方或全局兜底。上方没有有效名称时直接 FAIL；框内 Text 永不作为柜名。同一 G 图内 RMU 名称重复时，重复名称对应的环网柜全部阻断自动关联。":
        "A rectangle is recognized as an RMU only when it contains CBreakerDis, BusDis, and ZhaiWaiJieDiDaoZha. The RMU name is taken only from Text fully outside and above the frame; right, left, bottom, and global fallback are prohibited. If no valid top name exists, the RMU is FAIL. Text inside the frame is never used as the cabinet name. Duplicate RMU names in the same G drawing block automatic association for all affected RMUs.",
    "CBreakerDis 只使用柜内图上文字，不读取 XML p_NameString；ZhaiWaiJieDiDaoZha 的逻辑名称=配对开关名称+D；BusDis 的逻辑名称固定为 BUS。保护/EFI 只认【图元管理】分类标记 RMU_PWBH_EFI，并按固定 CODE=EFI INDICATOR 处理。保护范围仍由左侧“保护 / EFI 关联范围”选项控制。":
        "CBreakerDis uses only graphical text inside the cabinet and never XML p_NameString. The ZhaiWaiJieDiDaoZha logical name is paired-breaker-name + D, and BusDis is always BUS. Protection/EFI is recognized only through the RMU_PWBH_EFI mark in Element Management and uses fixed CODE=EFI INDICATOR. The left-side Protection / EFI Association Scope option controls which RMUs are included.",
    "先用 RMU 名称定位 13501 环网柜；单线图先按图级 FEEDER_ID 过滤同名记录，只有当前馈线内唯一记录才继续。柜内 CBreakerDis 对应固定 13502 / Domain 40，接地刀闸对应 13514 / Domain 40，BusDis 对应 13506 / Domain 1；这些设备按数据库 CODE 与图上逻辑名称校验，并要求目标设备属于当前 RMU。RMU_PWBH_EFI 使用 13533 / dms_relay_sig，固定 CODE=EFI INDICATOR、Domain 40。数据库 0 条、多条、CODE 不一致、设备归属不一致、BV_ID/Expected KeyID 无效时均禁止自动关联。":
        "Locate the RMU in 13501 by RMU name first. For a single-line drawing, filter same-name records by graph FEEDER_ID and continue only when exactly one record remains on the current feeder. In-cabinet CBreakerDis uses fixed 13502 / Domain 40, the grounding switch uses 13514 / Domain 40, and BusDis uses 13506 / Domain 1. These devices are validated by database CODE against the graphical logical name and must belong to the current RMU. RMU_PWBH_EFI uses 13533 / dms_relay_sig with fixed CODE=EFI INDICATOR and Domain 40. Zero/multiple database rows, CODE mismatch, ownership mismatch, or invalid BV_ID/Expected KeyID blocks automatic association.",
    "当前 KeyID 只用于判断 PASS / UNLINKED / RELINK / RMU_RELINK。当前关联已正确则保持不动；旧设备 ID、旧 KeyID、旧表号/域号已经过期，但数据库当前目标唯一且属于本 RMU 时，允许安全重关联。单线图还必须满足目标 RMU 的 FEEDER_ID 与图级馈线一致；facID 不作为 RMU 名称匹配条件。":
        "The current KeyID is used only to classify PASS / UNLINKED / RELINK / RMU_RELINK. A correct current association is preserved. If an old device ID, KeyID, table, or domain is stale but the current database target is unique and belongs to this RMU, safe relinking is allowed. For a single-line drawing, the target RMU FEEDER_ID must also equal the graph feeder. facID is not an RMU-name matching condition.",
    "CBreakerDis / ZhaiWaiJieDiDaoZha：app=6500000、voltype=数据库 BV_ID、p_ReportType=1、state=41、keyid=Expected KeyID。BusDis：app=6500000、voltype=数据库 BV_ID、p_ReportType=1、state=15、keyid=Expected KeyID。RMU_PWBH_EFI：app/app1=6500000、voltype1=0、p_ReportType1=1、state1=41、keyid1=Expected KeyID。选择“仅 SMART”时，NORMAL RMU 已有关联的 EFI 按既有策略清回未关联属性状态。所有修改只写 Workspace 安全副本，原始 G 文件不修改。":
        "CBreakerDis / ZhaiWaiJieDiDaoZha: app=6500000, voltype=database BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID. BusDis: app=6500000, voltype=database BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID. RMU_PWBH_EFI: app/app1=6500000, voltype1=0, p_ReportType1=1, state1=41, keyid1=Expected KeyID. With SMART-only scope, an existing EFI link on a NORMAL RMU is cleared back to the unlinked attribute state using the existing policy. All changes are written only to Workspace safe copies; original G files are never modified.",

    # Help page – current v4.2.x wording.
    "1. 在【数据库】页面确认 Oracle 配置，可先点击‘测试数据库连接’。\n2. 进入【模型工作区】，选择 RMU 环网柜模型或馈线模型，并选择 G 文件/目录。\n3. 各独立模块页面直接展示完整的设备识别、数据库关联、安全校验和 G 文件回写逻辑；固定工程表号/域号不再作为模型页面编辑项。\n4. 点击底部【模型校验】执行校验，并生成 HTML / CSV 以及可关联清单。\n5. 在可关联清单中勾选需要处理的设备或 FeedLine，然后点击【执行模型关联】。\n6. 执行前会显示最终确认摘要；模型关联只修改 Workspace 中的安全副本，原始 G 文件不变。\n7. 关联完成后生成本次执行 HTML / CSV、model_change_log.csv，并写入【运行历史】。":
        "1. Confirm Oracle settings on the Database page; optionally click Test Database Connection.\n2. Open Model Workspace, select the RMU Model or Feeder Model, and choose a G file/folder.\n3. Each standalone module page directly shows its complete device-recognition, database-association, safety-validation, and G-file write-back logic. Fixed engineering table/domain definitions are no longer editable model-page fields.\n4. Click Model Validation at the bottom to validate and generate HTML / CSV reports plus the eligible-object list.\n5. Select the devices or FeedLines to process, then click Apply Model Association.\n6. Review the final confirmation summary. Association modifies only safe Workspace copies; original G files remain unchanged.\n7. After association, execution HTML / CSV and model_change_log.csv are generated and recorded in Run History.",
    "• 环网柜只有在矩形框内同时存在 CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 三类图元时才识别为 RMU。\n• RMU 柜型：柜内 Y*/Q* 文字与 CBreakerDis.devref 模板结构独立计算并交叉验证；devref 不解析任何现场图元关键字，只检查 Y 类同模板、Q 类同模板且 Y/Q 模板可区分。有效 devref 与文字冲突时仍以 devref 为准，同时 WARN。\n• 环网柜名称只识别完整位于矩形框外、且在矩形框上方的 Text；右侧、左侧、下方和全局兜底全部禁用，上方找不到名称即 FAIL；框内 Text 永不作为柜名。\n• 每个 RMU 只保留一个名称；每个 Text 全局只分配给距离最近的一个环网柜。\n• 绿色依据 G 文件属性判断：lc=0,255,0 或 lcc=#00ff00；实际名称读取 Text 的 ts 属性。\n• 环网柜名称始终按字符串处理，支持 42646、RMU-42646、ABC_123、JED-RMU-01、ABC.01 等常见工程名称，不会强制转换成数字。":
        "• An RMU is recognized only when its rectangle contains CBreakerDis, ZhaiWaiJieDiDaoZha, and BusDis.\n• RMU type: in-cabinet Y*/Q* text and CBreakerDis.devref template structure are calculated independently and cross-validated. devref does not parse any site-specific symbol keywords; it checks only that Y devices share one template, Q devices share one template, and Y/Q templates are distinguishable. If a valid devref conflicts with text, devref remains authoritative and the row is WARN.\n• RMU names are recognized only from Text fully outside and above the rectangle. Right, left, bottom, and global fallback are disabled. If no top name is found, the RMU is FAIL. Text inside the frame is never a cabinet name.\n• Each RMU keeps one name, and each Text is globally assigned only to its nearest RMU.\n• Green is determined from G-file attributes: lc=0,255,0 or lcc=#00ff00. The actual name comes from Text.ts.\n• RMU names are always treated as strings. Common engineering names such as 42646, RMU-42646, ABC_123, JED-RMU-01, and ABC.01 are supported and are never forced to numeric values.",
    "• 13502 / CBreakerDis：先在当前 RMU + 当前文件名馈线范围内按 NAME 精确匹配；NAME 为 0 条时才按同值 CODE 精确兜底；NAME 或 CODE 多条都禁止自动选择。\n• 13514 / ZhaiWaiJieDiDaoZha：Y* 优先 NAME=KY*，Q* 优先 NAME=KQ*；NAME 为 0 条时才使用原 CODE=Y*D/Q*D 兜底。\n• 13506 / BusDis：逻辑 CODE 固定 BUS，并同样强制校验当前 RMU 与当前文件名馈线归属。\n• 目标 RMU 必须属于文件名确定的 FEEDER_ID；柜内设备必须同时属于该 RMU 且 FEEDER_ID 相同。\n• 匹配只针对 G 文件实际存在的图元；其它无关数据库记录不参与数量比较。":
        "• 13502 / CBreakerDis: exact-match NAME inside the current RMU + current filename feeder first. Only if NAME returns zero rows may the same-value CODE be used as fallback. Multiple NAME or CODE rows block automatic selection.\n• 13514 / ZhaiWaiJieDiDaoZha: Y* prefers NAME=KY* and Q* prefers NAME=KQ*. Only when NAME returns zero rows may original CODE=Y*D/Q*D be used as fallback.\n• 13506 / BusDis: logical CODE is fixed to BUS, with the same current-RMU and filename-feeder ownership checks.\n• The target RMU must belong to the FEEDER_ID resolved from the filename; in-cabinet devices must belong to both that RMU and the same FEEDER_ID.\n• Matching considers only objects actually present in the G file; unrelated database rows are excluded from count checks.",
    "绿色 PASS：设备模型校验正常；已有人工关联且名称匹配、环网柜归属、馈线归属均正确时也可显示绿色。\n黄色 WARN：设备尚未关联，但满足自动关联条件。\n黄色 WARN：设备当前未关联，但数据库当前目标唯一有效，可以关联。\n橙色 RELINK：旧设备 ID、KeyID、表号或域号已过期/错误，或旧设备被删除重建；数据库当前目标唯一有效，可以重新关联。\n紫色 RMU_RELINK：旧 KeyID 指向其他环网柜，但当前 RMU 内已唯一确定正确设备，可以强制重新关联。\n红色 FAIL：数据库当前事实无法唯一确定安全目标，例如 RMU 0/多条、NAME/CODE 0/多条、目标设备不属于当前 RMU、设备不属于文件名馈线、Expected KeyID/BV_ID 无效。\nRMU 报告会携带文件名确定的图级馈线，并把它作为 RMU 与柜内设备的硬约束。":
        "Green PASS: model validation is correct. An existing manual link is also green when name matching, RMU ownership, and feeder ownership are all correct.\nYellow WARN: the device is unlinked but satisfies automatic-association conditions.\nYellow WARN: the device is currently unlinked, while the current database target is unique and valid and can be associated.\nOrange RELINK: the old device ID, KeyID, table, or domain is stale/incorrect, or the old database device was deleted and recreated; the current database target is unique and valid and can be relinked.\nPurple RMU_RELINK: the old KeyID points to another RMU, but the correct device is uniquely identified inside the current RMU and may be forcibly relinked.\nRed FAIL: current database facts cannot uniquely determine a safe target, such as zero/multiple RMUs, zero/multiple NAME/CODE matches, target device outside the current RMU, device outside the filename feeder, or invalid Expected KeyID/BV_ID.\nThe RMU report carries the graph feeder resolved from the filename and enforces it as a hard constraint for the RMU and its child devices.",
    "建议先执行【模型校验】，在可关联清单中确认 Expected KeyID 和待处理对象后再执行关联。\n真正执行模型关联时，程序会重新检查数据库及预览有效性，然后复制所有选中 G 文件到 Workspace/g_output，只修改副本。原始 G 文件绝不修改。\n\nCBreakerDis / ZhaiWaiJieDiDaoZha 回写：\napp=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\nBusDis 回写：\napp=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\n模型关联不会修改图上设备名称，也不会读取 XML p_NameString 作为设备名称。图级馈线只由文件名确定；RMU 必须属于该馈线，柜内设备必须同时属于当前 RMU 和该馈线。CBreakerDis 按 NAME 优先/CODE 兜底，接地刀闸按 KY*/KQ* NAME 优先、Y*D/Q*D CODE 兜底。旧 KeyID 仅用于识别 PASS / RELINK / RMU_RELINK，不会阻止修复已经过期的模型关联。":
        "Run Model Validation first and review Expected KeyID and the selected targets before association.\nDuring Model Association, the database and validated preview are rechecked. All selected G files are copied to Workspace/g_output and only the copies are modified. Original G files are never changed.\n\nCBreakerDis / ZhaiWaiJieDiDaoZha write-back:\napp=6500000, voltype=database device BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\nBusDis write-back:\napp=6500000, voltype=database device BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\nAssociation never changes graphical device names and never uses XML p_NameString as a device name. The graph feeder is determined only from the filename; the RMU must belong to that feeder and child devices must belong to both the current RMU and that feeder. CBreakerDis uses NAME first with CODE fallback; grounding switches use KY*/KQ* NAME first and Y*D/Q*D CODE fallback. Old KeyID is used only to classify PASS / RELINK / RMU_RELINK and does not prevent repair of stale model links.",
})

_RUNTIME_REPLACEMENTS.extend([
    # Settings safety policy lines and late dynamic central-state messages.
    ("• 当前工作目录下自动生成的报告保留 30 天", "• Automatically generated reports in the current Workspace are retained for 30 days"),
    ("• 软件启动不检查 Oracle/SSH/中央服务器；只有显式操作才连接。成为 Admin 后仅每 10 秒轻量检查一次 Admin 所有权", "• Startup does not check Oracle/SSH/central servers; connections occur only on explicit actions. After becoming Admin, only a lightweight Admin-ownership check runs every 10 seconds"),
    ("• 每次执行模型任务时才进行 Oracle 预检查", "• Oracle pre-check runs only when a model task is executed"),
    ("• 模型回写必须先生成校验候选", "• Model write-back requires validated candidates first"),
    ("• 原始 G 文件不修改；关联前先复制到 Workspace 安全副本", "• Original G files are never modified; safe Workspace copies are created before association"),
    ("• 回写目标必须通过 G 图元类型 + XML ID 唯一定位", "• Write-back targets must be uniquely located by G object type + XML ID"),
    ("• G 文件采用临时文件写入后原子替换", "• G files are written through a temporary file followed by atomic replacement"),
    ("• 文件与目录选择会自动记住上一次位置", "• File and folder dialogs remember the last location"),
    ("• SSH 文件服务器严格只读；每次模型校验重新下载当前最新版本，关联锁定该次快照", "• The SSH file server is strictly read-only; every validation downloads the current latest version and association uses that locked snapshot"),
    ("当前仅使用本机缓存；软件启动不会访问中央配置。只有手动点击【连接并同步中央配置】才会读取并覆盖本机共享配置缓存。", "Using local cache only. Startup does not access central configuration. The local shared-configuration cache is read and replaced only after an explicit Connect and Sync Central Configuration action."),
    ("普通客户端可修改、测试、刷新并保存本机配置，也可手动同步中央配置；只有【保存并同步到中央仓库】需要先抢占 Admin。", "Standard clients may edit, test, refresh, and save local configuration, and may manually sync central configuration. Only Save and Publish to Central Repository requires Admin ownership."),
    ("服务器图元库", "Server Element Library"),
    ("服务器已同步", "Server Synchronized"),
    ("待标记", "Pending Classification"),
    ("服务器不存在", "Not on Server"),
])

ZH_TO_EN.update({
    "【设备名称规则（固定）】\n• CBreakerDis：只使用环网柜内图上文字；XML p_NameString 完全不参与设备命名。\n• ZhaiWaiJieDiDaoZha：与柜内开关一对一配对；Y1/Y2/Y3 优先匹配数据库 NAME=KY1/KY2/KY3，Q1/Q2/Q3 优先匹配 NAME=KQ1/KQ2/KQ3；NAME 找不到时再用原 CODE=Y1D/Y2D/Y3D/Q1D/Q2D/Q3D 兜底。\n• BusDis：逻辑名称固定为 BUS。\n• CBreakerDis：图上识别到 Y1/Y2/Y3/Q1/Q2/Q3... 后，先在当前 RMU 且当前文件名馈线内匹配数据库 NAME；NAME 找不到时才用同值 CODE 兜底。\n• 所有柜内目标设备必须同时满足：COMBINED_ID 属于当前唯一 RMU，FEEDER_ID 等于文件名确定的图级馈线；任一不满足都禁止关联。\n\n【RMU 柜型识别】\n• 第一套：柜内 Y1/Y2/Y3... 每个计 L；Q1/Q2/Q3... 每个计 T，形成文字柜型。\n• 第二套：只分析 CBreakerDis.devref 模板结构；Y 类同模板、Q 类同模板，且 Y/Q 模板必须不同。ZhaiWaiJieDiDaoZha/RMU_ES 等不参与，且不解析任何现场 devref 名称含义。\n• 两套结果都存在时必须交叉验证；冲突时最终采用 devref 柜型，同时产生 WARN 并指出具体环网柜。\n\n• 环网柜数据库记录为 0 条或多条时，环网柜汇总直接 FAIL。若 G 设备未关联，禁止自动关联。\n• 环网柜数据库记录为 0 条或多条，但 G 设备已经有人为 KeyID 时，不丢弃该模型：继续反解当前设备并校验 CODE/图上逻辑名称 和实际所属环网柜。\n• 唯一 RMU 下，若旧 KeyID 实际属于其它环网柜，使用紫色 RMU_RELINK 标记，可以覆盖旧模型并重新关联到当前 RMU；只有 RMU 本身不唯一时才继续作为硬阻断。\n• RMU 模块不再通过任何设备反推馈线；所有图统一只认 G 文件名 → 405/substation → 13500/dms_feeder_device 得到的唯一 FEEDER_ID。RMU 本身不属于该馈线时禁止关联。\n• 唯一 RMU 下以当前数据库为准：NAME 优先/CODE 兜底匹配、目标设备 RMU 归属和 FEEDER_ID 均通过后，即使旧设备 ID、表号、域号、KeyID 已失效，也允许重新关联。":
        "[Fixed Device Naming Rules]\n• CBreakerDis uses only graphical text inside the RMU; XML p_NameString never participates in device naming.\n• ZhaiWaiJieDiDaoZha is paired one-to-one with an in-cabinet breaker. Y1/Y2/Y3 prefer database NAME=KY1/KY2/KY3 and Q1/Q2/Q3 prefer NAME=KQ1/KQ2/KQ3; only when NAME is absent does the original CODE=Y1D/Y2D/Y3D/Q1D/Q2D/Q3D serve as fallback.\n• BusDis logical name is fixed to BUS.\n• After Y1/Y2/Y3/Q1/Q2/Q3... is recognized graphically for CBreakerDis, database NAME is matched inside the current RMU and current filename feeder first; only if NAME is absent is the same-value CODE used as fallback.\n• Every in-cabinet target must satisfy both conditions: COMBINED_ID belongs to the unique current RMU and FEEDER_ID equals the graph feeder resolved from the filename. Any failure blocks association.\n\n[RMU Type Recognition]\n• Text method: each Y1/Y2/Y3... counts as L and each Q1/Q2/Q3... counts as T to form the text-based RMU type.\n• Template method: only CBreakerDis.devref template structure is analyzed. Y devices must share one template, Q devices another, and Y/Q templates must differ. ZhaiWaiJieDiDaoZha/RMU_ES do not participate, and no site-specific meaning is parsed from devref names.\n• When both results exist, they are cross-validated. If they conflict, the devref type is authoritative, the row becomes WARN, and the specific RMU is reported.\n\n• If the RMU database query returns zero or multiple rows, RMU Summary is FAIL. If the G device is unlinked, automatic association is blocked.\n• If the RMU database query returns zero or multiple rows but a G device already has a manual KeyID, the model is not discarded: the current device is reverse-resolved and its CODE/graphical logical name and actual RMU ownership are validated.\n• Under one unique RMU, if the old KeyID actually belongs to another RMU, the row is marked purple RMU_RELINK and the stale model can be overwritten and relinked to the current RMU. Only a non-unique RMU remains a hard block.\n• The RMU module no longer infers the feeder from any device. Every drawing uses only G filename → 405/substation → 13500/dms_feeder_device to obtain one FEEDER_ID. Association is blocked if the RMU does not belong to that feeder.\n• Under one unique RMU, the current database is authoritative: after NAME-first/CODE-fallback matching, RMU ownership, and FEEDER_ID all pass, relinking is allowed even if the old device ID, table, domain, or KeyID is stale.",
    "•【环网柜汇总】严格按 G 文件环网柜序号排列，每个 G 环网柜只显示一行；数据库 0 条或多条直接 FAIL，不展开多个 ID。\n•【设备明细】只显示 G 文件实际存在的 RMU 设备图元，并展示逻辑设备名称、数据库 CODE、当前 KeyID 和实际所属环网柜。\n• RMU 数据库记录异常时，已有人为 KeyID 的设备仍继续校验；未关联设备则直接阻断自动关联。\n• 当选择图上文字模式时，报告中的逻辑设备名称 表示用于校验的逻辑 图上逻辑名称，不是 XML 原属性。\n• 每次模型校验和模型关联都会自动生成 HTML / CSV，并写入【运行历史】。\n• 模型关联额外生成 model_change_log.csv，逐项记录 XML ID、属性、修改前值和修改后值；Workspace 历史按软件保留策略自动清理。":
        "• RMU Summary follows G-file RMU order and shows one row per G RMU. Zero/multiple database rows are immediate FAIL and duplicate IDs are not expanded.\n• Device Details shows only RMU device objects actually present in the G file and includes logical device name, database CODE, current KeyID, and actual RMU ownership.\n• When RMU database rows are abnormal, devices with a manual KeyID continue validation; unlinked devices are blocked from automatic association.\n• In graphical-text mode, Logical Device Name in the report means the logical graphical name used for validation, not the original XML attribute.\n• Every Model Validation and Model Association automatically generates HTML / CSV and is written to Run History.\n• Model Association additionally generates model_change_log.csv recording XML ID, attribute, old value, and new value; Workspace history is cleaned automatically according to the retention policy.",
    "• 当前版本仅处理单馈线 G 图，不处理一个文件内多馈线总图。\n• 馈线名称优先从 <Bus> 周围最近的有效 Text 获取，例如 AJWD-07；若找不到，再从文件名提取。\n• 数据库可读馈线名称由站名 + dms_feeder_device.NAME 组合；名称匹配忽略横线、下划线和空格：AJWD-07 → AJWD07；JED CTL AJWD + 07 → JEDCTLAJWD07。\n• 馈线主表：13500 / dms_feeder_device；馈线段表：13503 / dms_section_device；默认域号：1。\n• G 馈线段图元为 <FeedLine>。已有关联时，当前 KeyID 必须反解到 13503 / Domain 1 且数据库记录属于当前馈线。\n• 已关联 FeedLine：13503、Domain、FEEDER_ID 均正确即保持原关联，不按几何顺序重排 SEC。\n• 未关联/失效关联 FeedLine：已正确关联的数据库馈线段先视为占用；其余数据库馈线段按自然顺序分配，真实数量不足时才新建缺少数量。\n• 已经关联错误的 FeedLine 不自动覆盖，只在报告中标红，避免静默改错已有模型。\n• FeedLine 回写安全副本：app=6500000, p_ReportType=1, state=20, voltype=dms_section_device.BV_ID, keyid=Expected KeyID。\n• 馈线模块拥有独立的【馈线汇总】和【馈线段明细】HTML / CSV 报告，不改变 RMU 模块已经取消馈线判断的规则。":
        "• The current feeder workflow processes single-feeder G drawings and does not automatically treat a multi-feeder overview as one feeder.\n• Feeder identification uses the current Jeddah filename/database resolver; legacy nearby-Bus text remains only as report context where applicable.\n• Database-readable feeder names combine the station and dms_feeder_device.NAME, while matching normalizes separators such as hyphens, underscores, and spaces.\n• Feeder table: 13500 / dms_feeder_device; feeder-section table: 13503 / dms_section_device; default Domain: 1.\n• G feeder-section objects are <FeedLine>. For an existing link, the current KeyID must reverse-resolve to 13503 / Domain 1 and the database row must belong to the current feeder.\n• A linked FeedLine whose 13503, Domain, and FEEDER_ID are correct is preserved and is not reordered by geometry.\n• For unlinked/stale FeedLines, correctly linked database sections are treated as occupied first; remaining database sections are assigned in deterministic order and only the actual shortage is created.\n• A FeedLine linked to the wrong target is never silently overwritten; it is reported as an error/block for operator review.\n• FeedLine safe-copy write-back: app=6500000, p_ReportType=1, state=20, voltype=dms_section_device.BV_ID, keyid=Expected KeyID.\n• The Feeder module has independent Feeder Summary and Feeder Section Details HTML / CSV reports and does not alter RMU model rules.",
    "• SSH 模式只允许读取目录、读取文件属性和下载 G 文件；程序没有上传、覆盖、删除、重命名服务器文件的功能。\n• IP/主机、端口、用户名、密码和远程目录都可以自定义；点击【保存 SSH 配置】后写入本地 Workspace 配置，下次启动自动恢复最后一次保存值。\n• 点击【刷新 G 文件列表】只刷新浏览列表；搜索只在当前已加载列表中本地过滤。\n• RMU 环网柜模型与馈线模型使用完全相同的 SSH 文件源。无论当前模型类型是哪一个，每次点击【模型校验】都会重新从服务器下载当前勾选文件的最新版本，历史 remote_input 或本地缓存绝不会作为新一次校验输入。\n• 下载采用 stat-before → download → stat-after 稳定性检查；如果 size/mtime 在下载期间变化，会自动重新下载，最多 3 次。\n• 下载成功后写入本次 run/remote_input，并计算 SHA256；该快照即为本次模型校验的固定输入。\n• 同一次校验后的【执行模型关联】禁止再次从服务器下载。关联必须使用本次 remote_input 快照复制到 g_output 后修改，从而保证“校验哪个版本，就修改哪个版本”。\n• 若服务器文件后来发生变化，需要重新点击【模型校验】取得新的最新快照。":
        "• SSH mode allows directory listing, file-attribute reading, and G-file download only. The application has no server upload, overwrite, delete, or rename capability.\n• IP/host, port, username, password, and remote directory are configurable. Save SSH Settings stores them in the local Workspace configuration and restores the last saved values on next launch.\n• Refresh G File List refreshes the browser only; search filters the currently loaded list locally.\n• RMU and Feeder models use exactly the same SSH source. Regardless of model type, every Model Validation downloads the latest version of the currently selected files from the server; historical remote_input files or local cache are never used as a new validation input.\n• Download uses stat-before → download → stat-after stability checks. If size/mtime changes during download, it retries automatically up to 3 times.\n• A successful download is written to the current run/remote_input and SHA256 is calculated; this snapshot becomes the fixed input for the validation.\n• Apply Model Association after that validation is forbidden from downloading again. It must copy the same remote_input snapshot to g_output and modify only that copy, guaranteeing that the version validated is the version modified.\n• If the server file later changes, run Model Validation again to obtain a new latest snapshot.",
    "• 执行模型关联前建议保留 G 文件源目录的额外工程备份。\n• 如果图上设备文字本身错误，图上文字模式也会得到错误名称，因此必须查看报告后再执行关联。\n• 模型页面不再提供表号/域号编辑入口；固定工程定义只以关联逻辑说明呈现，避免误操作改变 Expected KeyID。\n• 本工具为团队内部工程工具，不建议在未验证的数据库或未知版本 G 文件上直接批量回写。":
        "• Keep an additional engineering backup of the G-file source directory before Model Association.\n• If graphical device text is wrong, graphical-text recognition will also produce the wrong name; review the report before association.\n• Model pages no longer expose table/domain editing. Fixed engineering definitions are shown only in association-logic descriptions to prevent accidental changes to Expected KeyID.\n• This is an internal engineering tool. Direct bulk write-back against an unverified database or unknown G-file version is not recommended.",
})

# v4.2.13 final English-mode audit: cover literal and dynamic text introduced by
# the unified batch/model pages after the original v4.1 i18n layer.
ZH_TO_EN.update({
    "批量校验与模型工作区共用同一文件来源配置和同一远程文件选择。": "Batch validation shares the same file-source configuration and remote-file selection as Model Workspace.",
    "安全说明：批量模式与独立模块共用本地/SSH文件来源；本地原始 G 文件和 SSH 服务器文件均不修改。SSH 模式每次【批量校验】都会重新下载服务器当前最新稳定版本到 remote_input；同一次校验后的【执行批量关联】只使用该次快照，并仅修改 Workspace 中的安全副本。": "Safety: batch mode shares the same local/SSH file source as standalone modules. Original local G files and SSH server files are never modified. Every Batch Validation in SSH mode downloads the current stable server version to remote_input; Apply Batch Association after that validation uses only that snapshot and modifies only the safe Workspace copy.",
    "勾选一个或多个模块后统一执行。批量模式不会复制或改写各模块的识别规则，而是按固定依赖顺序调用现有独立模块；未勾选的模块即使作为依赖参与计算，也不会被写回。批量校验完成后会列出待关联设备，可在真正写回前逐项取消；独立模块仍保留用于专项处理。": "Select one or more modules and execute them together. Batch mode does not copy or rewrite module recognition rules; it calls the existing standalone modules in a fixed dependency order. Modules not selected are never written back even when used as dependencies. After batch validation, eligible objects are listed and can be deselected before write-back; standalone modules remain available for focused work.",
    "待关联设备（批量校验后确认）": "Eligible Objects (Confirm After Batch Validation)",
    "完成批量校验后，这里会列出所有可安全关联对象。": "After batch validation, all objects that can be associated safely are listed here.",
    "取消全选": "Clear Selection",
    "所有通过独立模块现有校验的对象默认勾选；跨模块写回冲突对象会显示但禁止选择。取消勾选只影响本次批量执行，不会改变任何独立模块的识别、数据库校验或写回逻辑。": "Objects that pass the existing standalone-module validation are selected by default. Cross-module write-back conflicts remain visible but cannot be selected. Deselecting an item affects only this batch run and does not change any standalone recognition, database validation, or write-back logic.",
    "请选择模型类型。": "Select a model type.",
    "待关联设备（一键多模型校验后确认）": "Eligible Objects (Confirm After Multi-Model Validation)",
    "完成一键多模型校验后，这里会列出所有可安全关联对象。": "After multi-model validation, all objects that can be associated safely are listed here.",
    "所有通过独立模块现有校验的对象默认勾选；跨模块写回冲突对象会显示但禁止选择。取消勾选只影响本次一键执行，不会改变任何独立模型的识别、数据库校验或写回规则。": "Objects that pass the existing standalone-model validation are selected by default. Cross-module write-back conflicts remain visible but cannot be selected. Deselecting an item affects only this multi-model run and does not change recognition, database validation, or write-back rules of any standalone model.",
    "文件来源（批量关联）": "File Source (Batch Association)",
    "环网柜名称位置": "RMU Name Position",
    "馈线模块不再展示可编辑的表号/域号表格。页面直接说明当前程序的完整自动识别、数据库补齐和 G 文件回写流程；原有馈线业务逻辑保持不变。": "The Feeder module no longer exposes editable table/domain fields. This page describes the complete automatic recognition, database completion, and G-file write-back workflow used by the application; existing feeder business logic is unchanged.",
    "数据库写入边界：模型校验永远不写数据库；真正执行关联时也只允许按该选项 INSERT 缺失馈线段。其它模型模块仍保持各自既有数据库只读/回写边界。": "Database write boundary: Model Validation never writes to the database. During actual association, this option permits only INSERT of missing feeder sections. Other model modules keep their existing database read-only/write-back boundaries.",
    "配网主站设备模块不提供表号、域号等工程定义的编辑入口。页面只说明程序实际执行的识别、数据库定位、安全校验和 G 文件回写流程；运行时仍使用吉达项目已经固定的业务规则。": "The Master Station Device module does not expose editable engineering definitions such as table or domain. This page describes the recognition, database targeting, safety validation, and G-file write-back actually executed by the program; runtime behavior continues to use the fixed Jeddah project rules.",
    "模块": "Module",
    "图上名称": "Graphical Name",
    "数据库目标": "Database Target",
    "说明": "Description",
    "正在准备批量校验输入……": "Preparing batch-validation input…",
    "正在执行批量模型关联……": "Applying batch model association…",
    "批量模型关联完成，最终累计安全副本已生成": "Batch model association completed; the final accumulated safe copy has been generated",
    "批量任务失败": "Batch Task Failed",
    "批量任务失败，请查看 Console 日志。": "Batch task failed. Check the Console log.",
    "SSH模式：请选择远程 G 文件后执行批量校验。": "SSH mode: select remote G files before running batch validation.",
    "本地模式：请选择 G 文件或目录后执行批量校验。": "Local mode: select G files or a directory before running batch validation.",
    "批量校验准备中……": "Preparing batch validation…",
    "SSH只读模式：批量校验会重新下载服务器当前最新稳定版本 G 文件，并锁定本次快照。": "SSH read-only mode: batch validation downloads the current latest stable G files from the server and locks this snapshot.",
    "图纸范围提醒：配网主站设备、馈线模型只允许在单线图中执行关联；如果后续勾选这两个模块，合成图或环网图会在批量校验阶段自动阻断，不会写回。其他模块仍按各自独立模块的现有规则校验。": "Drawing-scope notice: Master Station Device and Feeder association is allowed only on single-line drawings. If either module is selected later, composite or ring-network drawings are blocked during batch validation and are not written back. Other modules continue to use their existing standalone validation rules.",
    "尚未选择批量关联模块": "No batch-association module selected",
    "正在从 SSH 服务器获取本次批量校验的最新稳定 G 文件快照……": "Downloading the latest stable G-file snapshot from the SSH server for this batch validation…",
    "批量文件准备失败": "Batch File Preparation Failed",
    "正在读取服务器图元文件列表，请稍候……": "Reading the server element-file list…",
    "正在手动同步中央配置仓库，请稍候……": "Synchronizing the central configuration repository…",
    "正在测试图元服务器 SSH/SFTP 只读连接……": "Testing the read-only element-server SSH/SFTP connection…",
    "图元服务器 SSH/SFTP 连接正常；远程图元文件为只读。": "Element-server SSH/SFTP connection is available; remote element files are read-only.",
    "图元服务器 SSH 配置已保存；下次启动将自动恢复。": "Element-server SSH settings saved; they will be restored on next launch.",
    "有未保存的图元标记修改；模型校验仍会使用上一次已保存的配置。": "There are unsaved element-classification changes; Model Validation will continue to use the last saved configuration.",
    "SSH只读模式：模型校验会重新下载服务器当前最新 G 文件。": "SSH read-only mode: Model Validation downloads the current latest G files from the server.",
})

_RUNTIME_REPLACEMENTS.extend([
    ("SSH只读模式：模型校验会重新下载服务器当前最新 G 文件。", "SSH read-only mode: Model Validation downloads the current latest G files from the server."),
    ("SSH只读模式：批量校验会重新下载服务器当前最新稳定版本 G 文件，并锁定本次快照。", "SSH read-only mode: batch validation downloads the current latest stable G files from the server and locks this snapshot."),
])
EN_TO_ZH.update({value: key for key, value in ZH_TO_EN.items()})

_RUNTIME_REPLACEMENTS.extend([
    ("正在批量校验：", "Running batch validation: "),
    ("批量关联完成：候选 ", "Batch association completed: candidates "),
    ("批量校验结果已失效：", "Batch validation result is stale: "),
    (" 个模块均无需要写回的对象。", " selected modules have no objects requiring write-back."),
    ("；请执行批量校验。", "; run Batch Validation."),
    ("批量校验完成：共 ", "Batch validation completed: total "),
    (" 个候选；可安全关联 ", " candidates; safely associable "),
    (" 个，跨模块冲突 ", ", cross-module conflicts "),
    (" 个已禁用。请确认下方待关联设备。", " disabled. Confirm the eligible objects below."),
    (" 个模块，共 ", " modules, total "),
    (" 个可关联对象；请在下方确认待关联设备。", " eligible objects; confirm the eligible objects below."),
    ("SSH最新快照准备完成：", "Latest SSH snapshot prepared: "),
    (" 个 G 文件。", " G files."),
    ("已选择：", "Selected: "),
])

_RUNTIME_REPLACEMENTS.extend([
    ("已载入本地缓存：", "Loaded local cache: "),
    (" 条（相同图元路径已合并）；不会自动访问服务器。", " records (duplicate element paths merged); the server was not contacted automatically."),
    ("正在下载 ", "Downloading "),
    (" 个图元文件，请稍候……", " element files…"),
    ("图元下载失败：", "Element download failed: "),
    ("读取失败：", "Read failed: "),
    ("已保存 ", "Saved "),
    (" 条图元标记到本机缓存。后续模型识别会按图元文件标识匹配。", " element marks to the local cache. Subsequent model recognition will match by element-file identity."),
    ("已导出 ", "Exported "),
    (" 条图元标记共享配置；文件不包含 SSH 主机、用户名和密码。", " element-mark records to shared configuration; the file contains no SSH host, username, or password."),
    ("已导入 ", "Imported "),
    (" 条共享标记，等待确认保存到本机。", " shared marks; waiting for confirmation to save locally."),
    ("已保存到本机缓存，并已同步到中央仓库（版本 ", "Saved to the local cache and synchronized to the central repository (version "),
    ("，图元标记 ", ", element marks "),
    ("图元服务器连接失败：", "Element-server connection failed: "),
    ("服务器读取完成，但本地自动保存失败：", "Server read completed, but automatic local save failed: "),
    ("已保存图元服务器配置和 ", "Saved element-server settings and "),
    (" 条图元标记到本机缓存；未访问中央仓库。", " element marks to the local cache; the central repository was not accessed."),
])
