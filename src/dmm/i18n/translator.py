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
    "G 图元类型": "G Object Type",
    "表号（Table ID）": "Table ID",
    "域号（Domain）": "Domain",
    "恢复 RMU 默认配置": "Restore RMU Defaults",
    "馈线识别与数据库补齐": "Feeder Resolution and Database Completion",
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

# Additional field-work UI strings.
ZH_TO_EN.update({
    "IP / 主机": "IP / Host",
    "远程目录": "Remote Directory",
    "SSH 用户名": "SSH Username",
    "图纸类型确认": "Drawing Type Confirmation",
    "自动识别（默认，按 G 图拓扑）": "Auto Detect (Default, G-file Topology)",
    "强制单馈线图（本次文件/目录）": "Force Single-feeder Drawing (Current File/Folder)",
    "强制组合图（本次文件/目录）": "Force Composite Drawing (Current File/Folder)",
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
    "• 13502 / CBreakerDis：CODE 不得为空，且 CODE 必须等于当前图上逻辑设备名称；NAME 不参与判断。\n• 13514 / ZhaiWaiJieDiDaoZha：CODE 不得为空，且 CODE 必须等于当前图上逻辑设备名称（开关名称+D）；NAME 不参与判断。\n• 13506 / BusDis：CODE 不得为空，且 CODE 必须等于当前图上逻辑设备名称；图上文字模式固定为 BUS；NAME 不参与判断。\n• 设备校验以 G 文件实际存在的图元为准，只查询这些图元最终需要的 CODE。\n• 数据库中与 G 图元 CODE 无关的其它设备记录忽略，不参与数量比较。\n• G 图元需要的 CODE 不存在，或同一 CODE 匹配到多条记录时，才作为设备模型错误并阻止关联。":
        "• 13502 / CBreakerDis: CODE must be non-empty and equal the current graphical logical device name; NAME is ignored.\n• 13514 / ZhaiWaiJieDiDaoZha: CODE must be non-empty and equal the current graphical logical name (breaker name + D); NAME is ignored.\n• 13506 / BusDis: CODE must be non-empty and equal the current graphical logical name; graphical mode is fixed to BUS; NAME is ignored.\n• Device validation is authoritative to objects actually present in the G file and queries only the CODE values required by those objects.\n• Other database rows unrelated to G-file object CODE values are ignored.\n• Association is blocked only when a required CODE is missing or matches multiple rows.",
    "绿色 PASS：设备模型校验正常；已有人工关联且 CODE、环网柜归属均正确时也可显示绿色。\n黄色 WARN：设备尚未关联，但满足自动关联条件。\n黄色 WARN：设备当前未关联，但数据库当前目标唯一有效，可以关联。\n橙色 RELINK：旧设备 ID、KeyID、表号或域号已过期/错误，或旧设备被删除重建；数据库当前目标唯一有效，可以重新关联。\n紫色 RMU_RELINK：旧 KeyID 指向其他环网柜，但当前 RMU 内已唯一确定正确设备，可以强制重新关联。\n红色 FAIL：数据库当前事实无法唯一确定安全目标，例如 RMU 0/多条、CODE 0/多条、CODE/图上逻辑名称 不一致、目标设备不属于当前 RMU、Expected KeyID/BV_ID 无效。\nRMU 报告不输出馈线状态；馈线模块使用独立报告。":
        "Green PASS: device model validation is correct; existing manual links are also green when CODE and RMU ownership are correct.\nYellow WARN: device is unlinked but satisfies automatic association conditions.\nYellow WARN: the current database target is uniquely valid and can be associated.\nOrange RELINK: old device ID, KeyID, table ID, or Domain is stale/incorrect, or the old device was recreated; the current database target is uniquely valid and can be relinked.\nPurple RMU_RELINK: old KeyID points to another RMU, but the correct device is uniquely determined inside the current RMU and can be force-relinked.\nRed FAIL: current database facts cannot uniquely determine a safe target, such as zero/multiple RMUs, zero/multiple CODE matches, CODE/graphical-name mismatch, wrong RMU ownership, or invalid Expected KeyID/BV_ID.\nRMU reports do not include feeder status; the feeder module has separate reports.",
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
    "【设备名称规则（固定）】\n• CBreakerDis：只使用环网柜内图上文字；XML p_NameString 完全不参与设备命名。\n• ZhaiWaiJieDiDaoZha：逻辑名称=配对开关图上名称+D。\n• BusDis：逻辑名称固定为 BUS。\n• 图上开关名称必须与当前 RMU 下数据库 CODE 唯一对应；失败时明确告警对应环网柜并提示检查命名方式。\n\n【RMU 柜型识别】\n• 第一套：柜内 Y1/Y2/Y3... 每个计 L；Q1/Q2/Q3... 每个计 T，形成文字柜型。\n• 第二套：只分析 CBreakerDis.devref 模板结构；Y 类同模板、Q 类同模板，且 Y/Q 模板必须不同。ZhaiWaiJieDiDaoZha/RMU_ES 等不参与，且不解析任何现场 devref 名称含义。\n• 两套结果都存在时必须交叉验证；冲突时最终采用 devref 柜型，同时产生 WARN 并指出具体环网柜。\n\n• 环网柜数据库记录为 0 条或多条时，环网柜汇总直接 FAIL。若 G 设备未关联，禁止自动关联。\n• 环网柜数据库记录为 0 条或多条，但 G 设备已经有人为 KeyID 时，不丢弃该模型：继续反解当前设备并校验 CODE/图上逻辑名称 和实际所属环网柜。\n• 唯一 RMU 下，若旧 KeyID 实际属于其它环网柜，使用紫色 RMU_RELINK 标记，可以覆盖旧模型并重新关联到当前 RMU；只有 RMU 本身不唯一时才继续作为硬阻断。\n• RMU 模块中的馈线判断已完全关闭；馈线模型关联由独立的【馈线模型】模块处理。\n• 唯一 RMU 下以当前数据库为准：CODE/图上逻辑名称 和目标设备 RMU 归属通过后，即使旧设备 ID、表号、域号、KeyID 已失效，也允许重新关联。": "[Fixed Device Naming Rules]\n• CBreakerDis: use only graphical text inside the RMU; XML p_NameString is never used for device naming.\n• ZhaiWaiJieDiDaoZha: logical name = paired breaker graphical name + D.\n• BusDis: logical name is always BUS.\n• The graphical breaker name must uniquely match database CODE under the current RMU; failures identify the affected RMU and request a naming check.\n\n[RMU Type Recognition]\n• Source 1: Y1/Y2/Y3... each count as L; Q1/Q2/Q3... each count as T.\n• Source 2: only CBreakerDis.devref template structure is analyzed. Y devices share one template, Q devices share one template, and Y/Q templates must differ. ZhaiWaiJieDiDaoZha/RMU_ES does not participate and no site-specific devref words are interpreted.\n• When both sources exist they are cross-checked; on conflict the final type uses devref and WARN identifies the RMU.\n\n• Zero or multiple RMU database rows makes the RMU summary FAIL. If a G device is unlinked, automatic association is blocked.\n• If the RMU database result is zero/multiple but a G device already has a manual KeyID, the existing model is retained for reverse-resolution and CODE/graphical-name/actual-RMU checks.\n• Under a unique RMU, an old KeyID belonging to another RMU is marked purple RMU_RELINK and may be corrected; only non-unique RMU identity is a hard block.\n• Feeder validation is disabled inside the RMU module and is handled by the independent Feeder Model.\n• Under a unique RMU, current database truth is authoritative: once CODE/graphical-name and target-RMU ownership pass, stale device ID/table/domain/KeyID may be relinked.",
    "建议先执行【模型校验】，在可关联清单中确认 Expected KeyID 和待处理对象后再执行关联。\n真正执行模型关联时，程序会重新检查数据库及预览有效性，然后复制所有选中 G 文件到 Workspace/g_output，只修改副本。原始 G 文件绝不修改。\n\nCBreakerDis / ZhaiWaiJieDiDaoZha 回写：\napp=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\nBusDis 回写：\napp=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\n模型关联不会修改图上设备名称，也不会读取 XML p_NameString 作为设备名称。馈线信息完全不参与判断；数据库当前唯一 RMU 和 CODE/图上逻辑名称 匹配结果是关联依据。旧 KeyID 仅用于识别 PASS / RELINK / RMU_RELINK，不会阻止修复已经过期的模型关联。": "Run Model Validation first and review Expected KeyID and the selected targets before association.\nDuring Model Association the database and validated result are rechecked, selected G files are copied to Workspace/g_output, and only those copies are modified. Original G files are never changed.\n\nCBreakerDis / ZhaiWaiJieDiDaoZha write-back:\napp=6500000, voltype=database device BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\nBusDis write-back:\napp=6500000, voltype=database device BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\nAssociation never changes graphical device names and never uses XML p_NameString as the device name. Feeder information is excluded from RMU validation; the unique current RMU and CODE/graphical-name database match are authoritative. Old KeyID is used only to classify PASS / RELINK / RMU_RELINK and does not block repair of stale associations.",
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


def translate_runtime_text(text: object, language: str | None) -> str:
    value = tr(text, language)
    if normalize_language(language) != LANG_EN:
        return value
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
    return value


def retranslate_qt_tree(root, language: str | None) -> None:
    """Translate already-created Qt widgets while preserving their source text.

    This deliberately works at the presentation layer only. Item userData and
    all engineering values remain unchanged.
    """
    try:
        from PySide6.QtCore import Qt, QObject
        from PySide6.QtWidgets import (
            QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit,
            QListWidget, QTabWidget, QTableWidget,
        )
    except Exception:
        return

    lang = normalize_language(language)
    objects = [root]
    try:
        objects.extend(root.findChildren(QObject))
    except Exception:
        pass

    for obj in objects:
        try:
            if isinstance(obj, QGroupBox):
                source = obj.property("_i18n_source_title")
                if source is None:
                    source = obj.title()
                    obj.setProperty("_i18n_source_title", source)
                obj.setTitle(tr(source, lang))
            elif isinstance(obj, (QLabel, QAbstractButton)):
                source = obj.property("_i18n_source_text")
                if source is None:
                    source = obj.text()
                    obj.setProperty("_i18n_source_text", source)
                obj.setText(tr(source, lang))

            if isinstance(obj, QLineEdit):
                source = obj.property("_i18n_source_placeholder")
                if source is None:
                    source = obj.placeholderText()
                    obj.setProperty("_i18n_source_placeholder", source)
                obj.setPlaceholderText(tr(source, lang))

            if isinstance(obj, QComboBox):
                for i in range(obj.count()):
                    role = int(Qt.UserRole) + 91
                    source = obj.itemData(i, role)
                    if source is None:
                        source = obj.itemText(i)
                        obj.setItemData(i, source, role)
                    obj.setItemText(i, tr(source, lang))

            if isinstance(obj, QListWidget):
                for i in range(obj.count()):
                    item = obj.item(i)
                    role = int(Qt.UserRole) + 91
                    source = item.data(role)
                    if source is None:
                        source = item.text()
                        item.setData(role, source)
                    item.setText(tr(source, lang))

            if isinstance(obj, QTabWidget):
                for i in range(obj.count()):
                    widget = obj.widget(i)
                    source = widget.property("_i18n_tab_text")
                    if source is None:
                        source = obj.tabText(i)
                        widget.setProperty("_i18n_tab_text", source)
                    obj.setTabText(i, tr(source, lang))

            if isinstance(obj, QTableWidget):
                role = int(Qt.UserRole) + 92
                for i in range(obj.columnCount()):
                    item = obj.horizontalHeaderItem(i)
                    if item is None:
                        continue
                    source = item.data(role)
                    if source is None:
                        source = item.text()
                        item.setData(role, source)
                    item.setText(tr(source, lang))
        except RuntimeError:
            # A QObject may be deleted while a task switches pages.
            continue
