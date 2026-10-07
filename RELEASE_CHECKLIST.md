# v4.1.135 Release Checklist

## Main-station background jump label layout

- [x] Replace only the main-station/feed-line text; keep `(target RMU)` unchanged.
- [x] Recalculate feeder-label Text width after replacement.
- [x] Resize the visible background carrier to contain both text lines.
- [x] Center feeder text and target RMU text horizontally; center the two-line block vertically.
- [x] Re-layout already-correct labels whose old background geometry is stale.
- [x] Keep original G untouched and write only a safe output copy.
- [x] Keep background jump labels excluded from whole-graph feeder anchor candidates.

# v4.1.134 Release Checklist


## v4.1.134 Whole-graph source uniqueness
- [ ] One main-station outgoing feeder has exactly one feeder/source name.
- [ ] Bay/CBreaker source outranks text-only line labels.
- [ ] Text-only source is accepted only at a source-free topology terminal.
- [ ] Duplicate source names and multiple names in one source region are blocked before propagation.
- [ ] Every NOP side resolves to exactly one source name or is reported as an error.
- [ ] Background jump labels remain excluded from feeder candidates.

- [x] 图形工作区新增“主网入口背景标签修正”模块。
- [x] 300G 内唯一主网 CBreaker 才允许自动修正。
- [x] `(xxxx)` / `（xxxx）` 目标文本保持不变，只修改括号外主网文字。
- [x] 有背景色判断不绑定固定 RGB。
- [x] 整图馈线拓扑分析强制排除背景跳转标签，不作为 Bay/沿线馈线候选。
- [x] 原始 G 文件不覆盖，安全副本 + HTML/CSV 报告。
- [x] 使用现场样例验证 `MNA4-12 + (33359) -> MNA4-AH312 + (33359)`。

# v4.1.132 Release Checklist

- [x] 修复前/修复后拓扑图均有独立缩放按钮。
- [x] 缩放范围限制为 20%～400%，步进 20%。
- [x] 两张图缩放状态互不影响。
- [x] Ctrl+鼠标滚轮仅在对应图谱区域缩放。
- [x] 全屏查看保留标题、图例和控制按钮。
- [x] 原有整图拓扑分析、NOP判断、自动修复逻辑不变。

## v4.1.131 整图拓扑自动修复发布检查

- [x] 原始 G 文件绝不覆盖。
- [x] 只对整图拓扑模块启用 3G~4.5G 小间隙自动修复；旧 RMU / FeedLine 专用分析逻辑不改。
- [x] 修复候选必须端点双方唯一。
- [x] 修复前先模拟，必须减少错误且不增加多馈线冲突。
- [x] 修复后 G 再次完整分析；失败自动撤销。
- [x] HTML 包含修复前 / 修复后两张拓扑图。
- [x] 输出断点修复 CSV 与 topology-fixed G。
- [x] 现场样例 177 -> 5 无馈线错误，11231 恢复 SHR2-AH329。

## v4.1.130 RMU Pole 拓扑传播修复

- [x] 环网柜馈线拓扑分析纳入 `Pole` 显式拓扑节点。
- [x] Pole 仅通过 `link/node_area` 建边，不使用几何邻近猜测。
- [x] `TNM-AH324 -> Pole -> Pole -> 9002.Y2` 链路可以传播。
- [x] `9002.Y1` 红色 NOP 继续截断 `MKN-AH341`。
- [x] 9002 的非 NOP Y2/Q1 唯一归属 `TNM-AH324`，RMU 所属馈线正确输出。
- [x] 馈线段所属馈线分析源码哈希保持不变。
- [x] 全量测试结果保持 46 项既有历史失败，无新增失败。

## v4.1.129 红色 NOP 范围识别

- [x] `#ff2b05 / 255,43,5` 等现场偏橙红 NOP 可识别。
- [x] 纯红 `#ff0000` 继续识别。
- [x] 绿色 `#00ff00`、黄绿色 `#55ff00`、黄色、青色、蓝色、白色均不识别为红色 NOP。
- [x] 兼容 6 位 / 8 位 hex 以及 3 / 4 通道逗号颜色格式。
- [x] NOP RMU / Y-Q 匹配、支路断点与馈线传播规则不改。

## v4.1.128 RMU 端口几何补链修复

- [x] RMU Y/Q 与线路缺少 link/node_area 时，仅按线端点 <= 6G 的严格端子距离补链。
- [x] RMU BusDis 支持同样的严格端子补链，保证柜内非 NOP 端口可形成完整电气路径。
- [x] 主站 Bay 唯一 CBreaker 支持严格端子补链。
- [x] 红色 NOP 仍为硬边界，不允许馈线穿越。
- [x] 几何歧义不猜测，端点深入图元内部不补链。
- [x] 整图拓扑分析同步使用该修复。
- [x] 馈线段所属馈线分析业务代码未改动。

## v4.1.127 整图馈线拓扑强校验 / RMU 所属馈线报告

- [ ] 只修改【整图馈线拓扑分析】；`rmu_feeder_topology.py` 与 `feedline_feeder_topology.py` 保持不变。
- [ ] 除 NOP 开关外，所有设备必须且只能得到一个 feeder；0 个输出 `NO_FEEDER_ERROR`，多个输出 `MULTI_FEEDER_ERROR`。
- [ ] NOP 开关本身不分配单一 feeder，继续按端口/方向显示两侧 feeder。
- [ ] RMU 所属馈线只由同柜非 NOP Y*/Q* 开关决定；每个端口必须唯一，且所有非 NOP 端口必须一致；不得多数投票。
- [ ] HTML 存在独立【RMU 所属馈线】和【拓扑异常设备】表；异常行红色高亮。
- [ ] 输出 `whole_graph_rmu_feeders.csv`，并确认源 G 与 Oracle 均未被修改/访问。

## v4.1.124 FeedLine topology-driven section creation

- [ ] Every FeedLine is resolved by the same topology rules as Graphics Workspace → FeedLine feeder topology analysis.
- [ ] CONFIRMED FeedLine maps to exactly one 13500 feeder.
- [ ] Existing 13503 is accepted only when its FEEDER_ID equals the topology target.
- [ ] Free 13503 rows are reused only within the topology target feeder.
- [ ] Shortages are created independently under each topology target feeder.
- [ ] CONFLICT / UNRESOLVED rows are blocked and never cross-feeder allocated.
- [ ] Multi-feeder execution does not protect the old section of a FeedLine selected for cross-feeder relink.

## v4.1.111 馈线相邻对齐 / 跨距外扩检查

- [ ] `馈线避让调整` 默认参数为：文字安全间距 20 G、错落轨道间距 50 G、同列判定范围 220 G、最大外移 500 G。
- [ ] 同一 RMU 列中，相邻 RMU 之间且 Y 区间不重叠的碰撞馈线对齐到同一内侧轨道。
- [ ] 跨越多个 RMU 区间的长馈线按重叠层级依次放到更外侧轨道，不与相邻短馈线叠成同一根竖线。
- [ ] 右侧馈线仅向右外扩；左侧馈线仅向左外扩；左右两侧可分别关闭。
- [ ] RMU 名称、NOP / N.O.P、RMU、设备、FeedLine 原始连接端点及 `link / node_area / keyid` 均不被修改。
- [ ] 现场样例 `OSLA-08-MNA2-35-MNA4-32-MNA3-29-MNA4-12-ARF2-0...g` 中，短相邻馈线对齐、长跨距馈线外扩，且 40 条文字碰撞馈线 0 条未解决。

# 发布检查清单

## v4.1.109 馈线避让调整检查

- [ ] 图形处理类型下拉框存在 `馈线避让调整`，可单独执行。
- [ ] 只有 FeedLine 与环网柜名称或 NOP/N.O.P Text 发生碰撞时才允许修改；无碰撞 FeedLine 的 `d` 必须保持不变。
- [ ] 环网柜名称、NOP/N.O.P Text、RMU 本体和设备 XML 属性均不得被本模块移动或修改。
- [ ] 碰撞的近似竖直 FeedLine 只向右避让，原线段两端连接点保持不变。
- [ ] `link / node_area / keyid` 等拓扑属性在处理前后完全一致。
- [ ] 默认安全间距为 20 G，默认最大右移为 500 G，且界面可调整。
- [ ] 纯水平/非正交且无法仅靠右移安全解决的碰撞不得猜测，必须计入未解决。
- [ ] 输出 HTML/CSV 避让报告，并确认原始本地/SSH G 文件保持只读。
- [ ] 使用现场 OSLA 样例抽查：被名称/NOP 压住的竖直主干右移后，名称和 NOP 均保持原位。

## v4.1.108 RMU 框外名称 / 用户图元直接认定检查

- [ ] RMU 名称 Text 中心落在任意 RMU 框内时，RIGHT/BOTTOM/GLOBAL 三阶段全部排除。
- [ ] 外部名称仍按 RIGHT → BOTTOM → GLOBAL、<=300 G、一对一规则识别。
- [ ] 用户加入柱上开关名单的图元不再因 RMU_* 前缀、XML 标签、颜色/形状/内部结构或变压器名单重叠而被自动排除。
- [ ] 柱上变压器继续只按用户选择的 transformer_element_files 识别，任意具体 XML 标签均可命中。
- [ ] 名称 Text 过滤、距离、一对一和数据库唯一性规则未被放宽。


## v4.1.107 麦加环网柜名称三阶段分配检查

- [ ] 位于某 RMU 右侧 <=300、但几何上更接近下一只 RMU 左侧的名称，仍必须在 RIGHT 阶段分配给前一个 RMU。
- [ ] RIGHT 阶段完成后，只有未命中的 RMU 才进入 BOTTOM；RIGHT/BOTTOM 均未命中后才进入 GLOBAL 最近距离兜底。
- [ ] RMU 右侧名称边缘距离在 `(200, 300]` G 单位时仍可参与识别。
- [ ] 右侧无合法名称时，下方名称边缘距离在 `(200, 300]` G 单位时仍可参与识别。
- [ ] RIGHT / BOTTOM 均无候选时，GLOBAL fallback 在 `<= 300` G 单位内可用。
- [ ] 名称边缘距离 `> 300` G 单位时必须排除。
- [ ] 优先级仍为 `RIGHT -> BOTTOM -> GLOBAL fallback`，同一 Text 只归属其全局最近 RMU。
- [ ] 柱上开关、柱上变压器的名称距离不随本次修改变化。

## v4.1.105 麦加柱上开关原名查询检查

- [ ] 图上名称 `SEC-2385` 查询 13501 时必须仍为 `SEC-2385`，不得变成 `SEC2385`。
- [ ] 图上名称 `AR 1234` 查询 13501 时必须保留中间空格。
- [ ] 图上名称含点号、多个空格或其他合法字符时，传给数据库的绑定值必须与 G 文件 `Text.ts` 完全一致。
- [ ] 13501 查询只使用 `WHERE name = :device_name`，不得使用 `TRIM(name)`、CODE 兜底或 FEEDER_ID 条件。
- [ ] 13501 / 13502 唯一性、Domain=40、Workspace 安全副本规则保持不变。

正式向团队分发前建议按以下顺序检查：

1. 执行 `powershell -ExecutionPolicy Bypass -File .\release_check.ps1`
2. 启动 GUI，确认数据库、模型工作区、运行历史、设置、帮助页面可正常切换
3. Oracle 连接测试通过
4. RMU 单图模型校验
5. RMU 大图/组合图模型校验
6. RMU 选择性模型关联，检查执行前确认摘要
   - 执行模型关联/回写期间，进度条应持续左右来回动画；即使 Oracle/磁盘操作较慢，窗口也必须保持可拖动和可重绘
7. 馈线模型校验与选择性关联
   - 分别验证 FACID / 文件名 / 人工输入三种来源互不强制；即使 G 已有 facID，选择文件名或人工输入仍按所选来源解析
   - 单文件：验证 `JED-NTH-ABH-03` 可在 ABH 站内唯一解析为目标（如 AH303），`JED-NTH-ABH-AH303` 直接使用完整馈线号
   - 批量目录：混合 `...-03` / `...-AH304` 等命名时，每个文件必须独立解析、独立数据库唯一校验
   - 未勾选“允许覆盖”时，现有 facID 与目标不同必须阻断；勾选后仅 SINGLE_FEEDER 安全副本允许覆盖根 facID 与跨馈线 FeedLine
   - AUTO 图纸类型：抽查单馈线和组合图自动拓扑分型
   - 强制单馈线：确认唯一馈线可独立回写 G 根 facID，且不受 Breaker/Busbar/FeedLine 状态影响
   - 强制组合图：确认禁止把整张 G 根 facID 绑定到单一馈线
   - 报告应同时显示最终图纸类型、图纸类型设置、自动拓扑识别、最终分型判据
   - 馈线汇总、馈线段明细搜索框均可独立模糊筛选
   - 抽查 13503 同设备同馈线但 Domain 错误的场景：应为 RELINK，且只重写 KeyID，不更换馈线段
   - 抽查 G FeedLine 数量大于当前馈线 13503 数量：先复用未占用现有段，只对实际短缺数量生成 CREATE_PENDING 并创建
   - 既有关联 FeedLine 校验只看同 FEEDER_ID + Domain；不得因 SEC 名称/后缀或图形顺序不同要求 RELINK
   - 全新图（所有 FeedLine 均无 KeyID）允许按从上到下、同高度从左到右顺序首次分配/创建馈线段
   - 部分已关联图：先锁定已有正确关联；多个未关联 FeedLine 可按本馈线剩余 13503 数据库记录顺序继续关联，不得重排已有模型
   - 数据库剩余段排序：NAME 含 SECnnn 时按 SEC 数字升序；历史非 SEC 名称按 device ID 升序
   - 抽查数据库剩余数量不足：先用完现有未占用段，只对真实短缺数量创建，再继续关联；禁止跨馈线
   - 馈线 HTML 报告中 `CREATE_PENDING` 必须显示为独立橙色 CREATE；黄色 WARN 仅表示已有数据库段可直接关联
8. 检查 `model_change_log.csv` 中 XML ID、属性、修改前/修改后值
9. 检查运行历史能打开 HTML、修改记录和运行目录
10. 抽查 Workspace 输出 G 文件的 KeyID / Domain / voltype / app / state / p_ReportType
11. 确认原始 G 文件未被修改
12. 使用 `release_check.ps1 -BuildExe` 完成最终打包

## v4.1.101 麦加 RMU Channel Status 检查

- [ ] 麦加原有 RMU 查找/名称识别结果与 v4.1.100 保持一致。
- [ ] 每个已唯一确定 RMU 框内只识别 `Status` 且 devref 含 `channel_status.zt.icn.g` 的图元。
- [ ] 数据库查询按 RMU ID -> `dms_terminal_info.COMBINED_ID` -> `dms_channel_info.TERMINAL_ID`，并排除 `CHAN_NAME` 以 `DR` 结尾的 channel。
- [ ] 0 条或多条 channel 均禁止关联；唯一 channel 的 KeyID 必须验证为 table 13566 / domain 40。
- [ ] Preview 显示 `app=6600000 / voltype=-1 / p_ReportType=1 / state=39 / keyid=Expected KeyID`。
- [ ] Apply 前重新查询数据库并再次校验 KeyID；只修改 Workspace 安全副本。
- [ ] 若目标 Status 旧字段含 `app1/voltype1/p_ReportType1/state1/keyid1`，回写后应清理。
- [ ] 同一 RMU 中存在多个 channel_status 图元时全部阻断，不做任意选择。


## v4.1.100 熔断器图元名单检查

- [ ] 熔断器模型配置显示“熔断器图元名单”，默认名单包含 `Fuse_arrow.zwk.icn.g`、`Fuse_NON_SMART.zwk.icn.g`。
- [ ] 从图元服务器展开搜索，复选框勾选后可批量加入；名单高度随数量动态增长。
- [ ] 添加、删除、恢复默认后自动保存；“保存到本地用户缓存”可手动确认保存。
- [ ] 未加入熔断器名单的 devref 即使【图元管理】分类为 FUSE 也不得被识别；加入名单的 devref 无需 FUSE 分类即可识别。
- [ ] 熔断器最近柱上变压器、13505/13513 NAME 唯一、Domain=40 和 Workspace 安全副本规则保持不变。


## 发布包建议

- EXE
- README.md
- CHANGELOG.md
- RELEASE_CHECKLIST.md
- 必要的运行依赖目录
- 不携带实际现场数据库密码


## SSH 文件源发布检查

1. 测试 SSH 只读连接
2. 确认 `.g.h / .g.data / .g.png` 不进入远程列表
3. 选择一个远程 `.g`，执行模型校验并确认生成 `remote_input`
4. 检查 `run_manifest.json` 中 remote size / mtime / SHA256
5. 修改服务器同名 G 后重新执行模型校验，确认重新下载最新版本
6. 校验完成后再修改服务器文件，然后执行模型关联：
   必须继续使用原校验快照，不能重新下载服务器新版本
7. 检查 `g_output` 有修改结果，服务器端文件保持不变
8. 代码中不得增加 SSH `put/upload/remove/rename/delete/mkdir` 等写接口

- [ ] RMU 名称未解析/解析异常时为红色 FAIL，且 RMU级关联阻断原因准确。

- [ ] SSH 配置保存与启动恢复：自定义 host/port/username/password/remote_directory 后保存，重启可恢复。
- [ ] SSH 大目录性能：加载 2000+ 个 G 文件后，搜索、全选当前结果、清空选择和搜索均应保持界面响应，不应出现“未响应”。
- [ ] RMU devref 柜型识别仅统计 `CBreakerDis`；确认 `ZhaiWaiJieDiDaoZha/RMU_ES` 不参与。
- [ ] 抽查至少一个吉达和一个麦加 RMU：Y 类 devref 同模板、Q 类 devref 同模板、Y/Q 模板不同；不得依赖 Load_Breaker/Circuit_Breaker/RMU_LBS/RMU_BRK 关键字。
- [ ] 人工制造同一 RMU 内 Y1/Y2 devref 不同的样例，确认 devref 类型为 UNKNOWN/WARN，程序不猜测。

## 双语发布检查

- [ ] 设置页切换 `简体中文 / English` 后主界面即时刷新，无需重启。
- [ ] 保存语言后重启程序，确认自动恢复最后一次语言选择。
- [ ] 抽查数据库、SSH、RMU、馈线页面的按钮、标签、提示框和运行日志。
- [ ] 中文模式导出中文 HTML/CSV；English 模式导出英文标题、表头、筛选文字和英文报告文件名。
- [ ] `PASS / FAIL / RELINK / CREATE_PENDING`、错误码、KeyID、FEEDER_ID、BV_ID、Domain、设备名称和数据库工程数据保持原值。


## v4.1.25 English Release / RMU Name Checks

- [ ] Switch to English and verify the Windows title bar, header brand/edition, Run History page/table, Settings/Safety Policy, Help/About and current-model help contain no Chinese UI copy.
- [ ] Export one RMU and one feeder HTML/CSV report in English; headers and user-facing explanations are English while engineering codes/IDs remain unchanged.
- [ ] `JED-CTL-AMR.sln.pic.g`: RMU frame XML ID `2000597` must resolve name `66 B` from the top label.
- [ ] Verify `66 B` and `123 C2` are accepted, while arbitrary spaced labels such as `RMU 42646` remain rejected as RMU name candidates.

## v4.1.26 English Console Translation Checks

- [ ] English mode: RMU validation Console lines contain no Chinese, including RMU index, frame XML ID, type source, SMART markers and devref cross-check diagnostics.
- [ ] English mode: Feeder validation/association, SSH snapshot and strict XML diagnostic messages contain no Chinese presentation text.
- [ ] Verify engineering/status tokens and values remain unchanged: PASS/FAIL/RELINK, KeyID, FEEDER_ID, XML ID, DB IDs, file names and raw engineering values.
- [ ] Confirm Chinese mode output is unchanged.
- [ ] Confirm no RMU/feeder/Oracle/SSH/validation/association/write-back business source file changed for this release.


## v4.1.27 RMU Name Recognition Checks

- [ ] RMU Recognition shows the configurable RMU Name Exclusion Strings field in Chinese and English.
- [ ] Default exclusions contain N.O.P / NOP / N-O-P / N_O_P / SFI / DAS/OK.
- [ ] Exclusions use exact full-string matching; similar but different engineering names are not removed.
- [ ] `JED-CTL-BABJ.sln.pic.g` frame XML ID 2001193 resolves top label 38995.
- [ ] Existing normal RMU label assignment keeps legacy edge-gap scoring.
- [ ] RMU/feeder/database/SSH/write-back business rules remain unchanged.


## v4.1.35 UI-only check
- [ ] Task Progress / 任务进度 title has no pale-green background patch.
- [ ] Busy progress behavior, Console placement, and all model logic are unchanged.


## v4.1.36 refresh performance check

- Refresh the same SSH directory twice with no server changes: second completion must report no changes and must not rebuild the remote table or clear the current validation snapshot.
- Add/modify/remove one remote `.g` file: refresh must detect the metadata change, rebuild the table once, preserve still-existing selections, and invalidate the old validation snapshot.
- Confirm SSH remains read-only and model validation still performs its independent latest-file snapshot download.
## v4.1.102 RMU Channel Status 说明一致性检查

- [ ] RMU 固定数据库规则显示 Channel Status = 13566 / Domain 40。
- [ ] RMU 自动关联逻辑显示独立“步骤 6｜关联 Channel Status 状态图元”。
- [ ] 说明包含 channel_status.zt.icn.g、dms_terminal_info/dms_channel_info、排除 DR、唯一候选、KeyID=ID+(40<<32)。
- [ ] 说明包含 app=6600000 / voltype=-1 / p_ReportType=1 / state=39 / keyid=Expected KeyID。
- [ ] 说明包含清理 app1/voltype1/p_ReportType1/state1/keyid1。
- [ ] 最终安全回写说明为步骤 7，且原始 G 文件不修改。




## v4.1.103 NOP / 环网柜名称位置检查

- [ ] 图形工作区可选择“ NOP / 环网柜名称位置调整”。
- [ ] NOP 只与柜内 Y*/Q* CBreakerDis 开关配对，不与接地刀闸或其它图元配对。
- [ ] NOP 移动后中心 Y 与对应 Y*/Q* 开关中心 Y 完全相等。
- [ ] NOP 仅支持自动保持原左右侧、左侧、右侧三种横向位置。
- [ ] 环网柜名称可放置在上/右/下/左四个边框中点。
- [ ] 本地/SSH 原始 G 文件不修改；结果仅写 Workspace 安全副本。
- [ ] CSV / HTML 位置调整报告可正常生成。


## v4.1.104 环网柜名称优先级 / Poke 同步移动检查

- [ ] 同一 RMU 同时存在右侧和下方合法名称时，固定选择右侧名称，即使下方距离更近。
- [ ] 右侧没有合法名称时选择下方；右侧/下方均没有时才使用 200 G 单位内 GLOBAL fallback。
- [ ] 一个名称 Text 只归属其全局最近 RMU，不被相邻 RMU 作为远距离 BOTTOM/RIGHT 候选抢占。
- [ ] 移动已有 Poke 的 RMU 名称时，Poke 的 x/y 与名称使用完全相同的 delta，同步到新位置。
- [ ] 带 `gfs_rmu_text_id` / `dmm_rmu_text_id` / `dmm_source_text_id` 的 Poke 可精确跟随。
- [ ] 无绑定元数据但与名称高度重合且带 `ahref` 的旧 Poke 也可跟随。
- [ ] NOP 仍与 Y*/Q* CBreakerDis 水平中心对齐；本地/SSH 原始 G 文件不修改。

## v4.1.123 FeedLine feeder topology

- [ ] 图形工作区可选择“馈线段所属馈线分析”。
- [ ] 环网柜馈线拓扑分析结果与 v4.1.122 保持一致。
- [ ] FeedLine 报告输出 CONFIRMED / CONFLICT / UNRESOLVED。
- [ ] 只处理红色 NOP，支路碰到对应 Y/Q 开关才停止。
- [ ] 不修改 G，不连接/查询/写 Oracle。
