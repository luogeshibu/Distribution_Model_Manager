## v4.1.135：主网入口背景标签自动扩框 / 两行居中排版

- “主网入口背景标签修正”在替换括号外主网名称后，会按修正后的文字长度重新计算标签宽度。
- 自动调整承载背景的 Poke / Rect / RoundRect 或其它可见填充对象大小，避免新主网名称超出背景框。
- 两段式标签统一排版为“主网名称”在上、“(目标RMU)”在下；两行水平居中，并作为整体在背景内垂直居中。
- 背景对象以原中心点为锚点扩展，尽量保持原跳转线与标签位置关系；原始 G 文件仍不覆盖，只输出安全副本。
- 即使文字内容已经是正确主网名称（UNCHANGED），也会继续检查并修正旧背景尺寸和两行对齐。
- HTML/CSV 修正报告新增原/新背景几何与两行文字几何信息。

## v4.1.134：整图馈线源唯一性收紧 / NOP 两侧唯一主站名称

- 整图馈线拓扑分析新增“馈线源唯一性”硬规则：一个主站出线有且只能有一个馈线名字。
- 主网 Bay/CBreaker + 馈线标题继续作为权威源；如果现场没有主站设备、只在线路末端写 `TRUB-BH21` 这类主站/馈线名称，则仅允许在“无主网设备源 + 拓扑末端”区域作为文字兜底源。
- 沿线名字不再全部直接作为馈线锚点：中段文字、已有主网设备源区域中的文字、重复同名源都会被排除，不参与传播。
- 同一个主站/馈线名称若出现多个同等级文字源候选，直接报 `SOURCE_NAME_DUPLICATE_ERROR`；同一个源端拓扑区域出现多个不同主站名字，报 `SOURCE_COMPONENT_MULTIPLE_NAMES_ERROR`，不再让多个名字同时扩散成设备多馈线冲突。
- 同名文字重复时，如果只有一个候选直接位于 NOP 另一侧的源端区域，优先保留该唯一 NOP 侧候选，其余重复文字仅报告并排除。
- NOP 两侧判断同步收紧：每一个物理侧必须最终得到且只能得到一个主站/馈线名称；0 个报告 `ERROR_SOURCE_NOT_FOUND_ON_SIDE`，多个报告 `ERROR_MULTI_SOURCE_ON_SIDE`。
- HTML 报告新增“馈线源唯一性检查”表，区分权威主网源、仅文字主站源、被排除重复源和源唯一性错误；最终馈线锚点表只展示真正参与传播的唯一源。
- 继续强制排除“有背景色 + (目标环网柜名称)”跳转标签，不得成为馈线候选。
- 既有“环网柜馈线拓扑分析”和“馈线段所属馈线分析”逻辑不修改。

## v4.1.133：主网入口背景跳转标签修正 + 整图馈线候选强制排除

- 新增图形工作区模块 `主网入口背景标签修正`。
- 识别“有背景色 + 馈线样式文字 + `(目标环网柜名称)`”的跳转标签；在唯一主网 CBreaker 300G 范围内，将括号外文字修正为主网已确认馈线名，括号目标保持不变。
- 背景识别不绑定固定 RGB，支持填充 Poke/Rect 和 Text 背景属性。
- 多主网候选不自动处理；原 G 不覆盖，只生成安全副本和 HTML/CSV 报告。
- 整图馈线拓扑分析新增强制排除：上述背景跳转标签在 Bay/沿线馈线锚点识别前即加入排除集，永远不能参与馈线计算。
- 新增整图 HTML 表 `已排除的背景跳转标签（绝不作为馈线锚点）` 及顶部计数。

## v4.1.132：整图拓扑图独立缩放 / 全屏查看

- “整图馈线拓扑分析”HTML 报告中的“修复前拓扑图”和“修复后拓扑图”各自增加独立控制：缩小、当前缩放比例、放大、重置、适应窗口、全屏查看。
- 缩放范围为 20%～400%，每次调整 20%；两张图状态互不影响。
- 图像区域支持 `Ctrl + 鼠标滚轮` 缩放，放大后保留横向/纵向滚动查看能力。
- 全屏模式保留当前图的标题、图例和缩放按钮，按 Esc 或再次点击“全屏查看”退出。
- 本次仅修改 HTML 报告交互与版本信息，不改变整图拓扑识别、NOP、自动补链、安全修复 G，也不修改既有“环网柜馈线拓扑分析”和“馈线段所属馈线分析”业务逻辑。

## v4.1.131：整图拓扑断点诊断、前后图谱与安全修复 G

- 整图拓扑分析新增断点诊断：从无馈线孤立区反查与唯一馈线区之间的线端点小间隙。
- 自动修复范围限定为 `3G < distance <= 4.5G`，并要求端点双方候选唯一。
- 自动修复前先模拟传播，只有错误减少且不新增多馈线冲突时才接受。
- 自动补链写入 `link` 与 `node_area` 双向引用，原始 G 不覆盖。
- 输出修复版 `*.topology-fixed...g`，并在生成后再次完整复核；复核不通过自动删除修复版。
- HTML 同时嵌入修复前 / 修复后两张 SVG 拓扑图，红色 × 标断点，绿色标已修复连接。
- 新增 `whole_graph_topology_repairs.csv` 记录断点对象、端点索引、距离、影响节点、修复前后错误数量和判定依据。
- 样例修复验证：`34000376 ↔ 35001786`，3.162G，`NO_FEEDER_ERROR 177 -> 5`，`MULTI_FEEDER_ERROR 0 -> 0`。
- 测试：498 passed，46 个既有历史失败，1 skipped；本次定向新增/相关测试 16 项通过。

## v4.1.130：环网柜馈线拓扑纳入 Pole 显式连接节点

- 修复【环网柜馈线拓扑分析】中 FeedLine 经 `Pole.node_area/link` 连续转接时，Pole 被旧基础网络过滤导致主网馈线传播中断的问题。
- 仅在 RMU 拓扑模块中新增 `Pole` 显式拓扑节点；只读取 G 文件已有 `link/node_area` 关系，不做 Pole 几何邻近猜测。
- 典型 `TNM-AH324 -> FeedLine -> Pole -> FeedLine -> Pole -> FeedLine -> 9002.Y2` 链路现在可以完整传播。
- NOP 规则保持不变：`9002.Y1` 仍作为 `MKN-AH341` 的红色 NOP 截止点；同柜非 NOP `Y2/Q1` 唯一到达 `TNM-AH324` 后，RMU 9002 所属馈线判为 `TNM-AH324`。
- 新增 Pole 链路回归测试；不修改【馈线段所属馈线分析】业务代码。
- 【整图馈线拓扑分析】原本已支持 Pole 显式节点，本次保持该逻辑不变。

## v4.1.129：红色 NOP 改为颜色范围识别

- 修复现场红色 NOP 使用 `#ff2b05 / 255,43,5` 等非纯红颜色时无法识别的问题。
- `_is_red_nop_text` 从精确 `#ff0000` 白名单升级为 HSV + RGB 双重判定：H 0~20° 或 340~360°、S≥45%、V≥30%，且 R 分量必须分别大于 G/B 的 1.5 倍。
- 绿色、黄绿色、黄色、青色、蓝色、白色继续严格排除，不会因为放宽红色范围被误判为 NOP。
- 兼容 `lc=R,G,B`、`R,G,B,A`、`lcc=#RRGGBB` 和历史 8 位 ARGB/RGBA 颜色格式。
- 仅改变红色 NOP 的颜色识别入口；RMU/NOP 归属、Y/Q 开关匹配、拓扑断点和馈线传播逻辑保持不变。

## v4.1.128：RMU 端口严格几何补链修复

- 修复 Makkah 环网柜馈线拓扑中视觉连接存在、但 `link/node_area` 缺失导致 `SOURCE_ENTRY_NOT_FOUND` / `UNRESOLVED_NON_NOP_PORTS` 的问题。
- 新增严格端子补链：只允许线对象端点与 RMU 内命名 Y*/Q* `CBreakerDis`、RMU `BusDis`、主站 Bay 唯一 `CBreaker` 在 <= 6 G 单位范围内建立缺失边。
- 线端点若位于图元内部深处不连接；多个候选同距时不自动猜测。
- `9002` 类 NOP 柜场景：NOP 端口继续截断来向馈线，非 NOP 端口可通过修复后的几何拓扑确认另一主网馈线，并据此确定 RMU 所属馈线。
- 整图馈线拓扑分析复用同一严格端子补链。
- 馈线段所属馈线分析模块保持不变。
- 新增 v4.1.128 回归测试覆盖缺失 `link/node_area` 的 RMU Y/Q、BusDis、主站出线几何连接，以及深度穿入图元时禁止误补链。

## v4.1.127：整图拓扑强校验 + RMU 所属馈线独立表

- 只修改新【整图馈线拓扑分析】，不改既有 RMU-only / FeedLine-only 拓扑模块。
- 除 NOP 开关外，所有电气对象必须且只能属于一条 feeder：0 条为 `NO_FEEDER_ERROR`，>1 条为 `MULTI_FEEDER_ERROR`，均进入 HTML 拓扑异常表。
- 新增 RMU 汇总：同柜非 NOP Y*/Q* 端口必须各自唯一且全部一致；NOP 端口不参与归属；不允许多数投票兜底。
- HTML 新增 RMU 所属馈线独立表、异常设备独立表；新增 `whole_graph_rmu_feeders.csv`。

## v4.1.126：新增整图馈线拓扑分析（纯图形 / 单 G 文件）

- 【图形工作区】新增全新独立任务【整图馈线拓扑分析】；既有环网柜馈线拓扑分析和馈线段所属馈线分析代码保持不变。
- 一次只处理一个 G 文件，只分析图形，不访问 Oracle、不做模型表校验、不修改 G。
- 主网 Bay CBreaker + 标题继续作为馈线锚点；新增 FeedLine 沿线完整馈线名识别，例如 `TURB-BH-04`，解决主站只在线路上标一个馈线名称的场景。
- 为避免把 `SLBS-2002` / `SAR-2216` 等设备名误当 feeder，沿线名称必须贴近 FeedLine，且不能更贴近柱上开关/设备。
- 红色 NOP 能归属 RMU 时复用现有 Y*/Q* 端口断点识别；未归属 RMU 的红色 NOP 全部按柱上开关 NOP 处理。
- NOP 开关本身不分配 feeder；对每个 NOP 分别输出 LEFT/RIGHT/TOP/BOTTOM 邻接侧的 feeder 归属，传播不穿过 NOP。
- 新整图图构建额外纳入 `Pole` 和其它显式 `link/node_area` 电气节点，修复线路经 Pole 转接时旧图构建器无法继续传播的问题；严格几何补链仍保持端点≤3G、端点到线段≤2G。
- 输出 `whole_graph_topology_report.html`、`whole_graph_device_feeders.csv`、`whole_graph_nop_boundaries.csv`、`whole_graph_feeder_anchors.csv`。

## v4.1.125：RMU 拓扑馈线硬约束 + 已关联 RMU FEEDER_ID 可控修正

- RMU 模型正式复用环网柜馈线拓扑分析结果；未关联 RMU 只在所属 13500 FEEDER_ID 下查 13501。
- 新增【强制修正已关联 RMU 所属馈线】复选开关，默认关闭。
- 已关联且设备 KeyID 能证明 13501 身份时，允许在开关开启后把错误 `dms_combined_device.FEEDER_ID` 修正为拓扑馈线 ID。
- 修正 SQL 带旧 FEEDER_ID 条件、影响行数校验、更新后回查及事务回滚保护。
- 新增 DB-only 的 `RMU_FEEDER_ID` 可选择修正项，因此即使 G 图设备已经全部正确关联，也可以单独执行所属馈线修正。
- 新增 3 项 RMU 馈线保护定向测试并通过；原 v4.1.124 馈线段拓扑相关定向测试继续通过。

## v4.1.124：馈线模型按 FeedLine 拓扑所属馈线分别复用/创建 13503

- 馈线模型不再把本图所有已确认馈线下的 13503 合并成统一资源池。
- 直接复用 v4.1.123【馈线段所属馈线分析】的主网源、link/node_area、严格几何补链与红色 NOP 支路级断点逻辑，先得到每条 FeedLine 的唯一 `primary_feeder`。
- 图形所属馈线再映射到 13500/dms_feeder_device；只有唯一数据库馈线匹配时才允许关联。
- 已有关联必须满足 `13503.FEEDER_ID == FeedLine 拓扑所属 FEEDER_ID`；跨馈线旧关联进入 RELINK，不再因为“属于本图任意已确认馈线”而被误判为正确。
- 未关联/失效/跨馈线 FeedLine 只从自己所属馈线的空闲 13503 中分配；不足部分在该馈线下按既有 SECnnn / BV_ID / SECTION_TYPE 规则创建。
- 同一个 G 图可以同时为多条馈线分别创建缺失 13503；执行阶段按 `FEEDER_ID` 分组并分别调用数据库创建。
- `CONFLICT` / `UNRESOLVED` FeedLine 阻断自动建库和模型关联，不做跨馈线兜底猜测。
- 修复执行阶段跨分组重关联：同一源文件中已选择迁移的 FeedLine，其旧 13503 不再被其它 FEEDER_ID 分组错误保护。
- 馈线段 HTML/CSV 明细新增拓扑所属馈线、拓扑候选馈线、拓扑目标 FEEDER_ID 等字段。

## v4.1.123：新增馈线段所属馈线分析模块

- 【图形工作区】新增独立任务【馈线段所属馈线分析】。
- 保持 v4.1.122 已验证的【环网柜馈线拓扑分析】核心逻辑不变；新模块只复用其已验证的主网馈线源、严格拓扑补链、红色 NOP 及端口级支路停止规则。
- FeedLine 所属 feeder 通过“从主网 CBreaker 是否能沿真实电气拓扑到达该 FeedLine”判断；碰到红色 NOP 对应 Y*/Q* 开关的支路立即停止，其它分支继续。
- `CONFIRMED`=唯一 feeder 可达；`CONFLICT`=多 feeder 可达；`UNRESOLVED`=没有 feeder 可达。
- 新增独立 HTML/CSV 审计报告；模块只读 G 文件，不访问 Oracle。

## v4.1.122：RMU-only 拓扑传播 + NOP 支路级停止

- 环网柜馈线拓扑分析只输出 RMU 所属 feeder，不再把 FeedLine 当业务归属对象。
- FeedLine / ConnectLine / Bus / BusDis 只作为网络路径参与搜索。
- 每条主网 feeder 独立 BFS 传播，只有当前路径碰到红色 NOP Y*/Q* 开关才停止，其它分支继续。
- 移除“首柜 NOP 导致 feeder 全局删除”的传播语义，首柜 NOP 只表示对应入口支路当场截止。

## v4.1.121：NOP 水平对齐识别 + 支路级传播断点

- 【图形工作区 → 环网柜馈线拓扑分析】只处理红色 NOP，非红色 NOP 继续全部忽略。
- NOP 仍先归属最近 RMU，但对应开关只允许从该 RMU 框内的 Y*/Q* CBreakerDis 中选择；绝不跨柜。
- NOP 位于 RMU 左/右侧时，优先按中心 Y 的水平对齐程度选择开关；同一水平行有多个开关时再按实际几何距离选择最近者。NOP 位于上/下侧时镜像按中心 X 对齐。
- 修复 Q1 场景：即使 Y1 的矩形边缘距离更近，只要 Q1 与 NOP 明显处于同一水平行，Q1 就会被识别为 NOP 开关。
- 馈线传播按支路执行：只有真正经过 NOP 开关的支路在该开关处停止，同一 RMU 的其它非 NOP 端口和其它支路继续传播；首柜入线开关本身就是 NOP 时才排除该主网馈线。
- 删除“FeedLine 外接矩形中心落入 RMU 就作为 feeder 证据”的旧补充逻辑，避免长折线经过附近时给无关 RMU 制造 CONFLICT；RMU 归属只使用真实 Y*/Q* 电气端口拓扑证据。
- NOP HTML 汇总增加 NOP 相对 RMU 方位、对齐轴和对齐差，便于现场审计为什么选中某个 Y/Q 开关。

## v4.1.120：环网柜馈线拓扑分析只认红色 NOP

- 麦加【图形工作区 → 环网柜馈线拓扑分析】改为严格红色白名单：只有可见文字颜色为红色（`lc=255,0,0` / `lcc=#ff0000` 等等价格式）的 `NOP / N.O.P / N-O-P / N_O_P` 才参与拓扑。
- 绿色、黄绿色（例如 `#55ff00`）以及其它所有非红色 NOP 全部忽略：不归属 RMU、不匹配 Y*/Q* 开关、不形成断点、不触发主网首柜馈线排除，也不进入 NOP 汇总。
- 主网首柜规则、NOP 最近 RMU/最近 Y-Q 开关规则、NOP 柜非 NOP 端口归属规则保持不变。
- 修复 `#55ff00` 这类现场绿色 NOP 未被 v4.1.119 的纯绿色过滤识别，导致拓扑被错误切断的问题。

## v4.1.119：环网柜馈线拓扑分析忽略绿色 NOP

- 麦加【图形工作区 → 环网柜馈线拓扑分析】中，所有绿色 `NOP / N.O.P / N-O-P / N_O_P` Text 直接忽略，不再归属 RMU、不匹配 Y*/Q* 开关、不形成拓扑断点，也不会触发主网首柜馈线排除。
- 非绿色 NOP 继续按现有规则：先归属最近 RMU，再在柜内按实际几何距离选择最近的唯一 Y*/Q* `CBreakerDis`；该开关作为馈线传播断点。
- 主网首柜规则保持不变：只有主网实际接入的 Y*/Q* 开关正好是有效 NOP 开关时，才排除该主网馈线。
- NOP 边界柜归属规则保持不变：NOP 侧馈线在开关处截止，RMU 所属馈线由同柜非 NOP 端口的唯一一致馈线决定。
- HTML 报告中的 NOP 数量和 “NOP所属RMU / 开关汇总” 只统计有效的非绿色 NOP。

## v4.1.118：NOP边界RMU所属馈线按非NOP端口确定

- NOP 开关连接的馈线在该开关处截止；该馈线仅作为边界/截止馈线记录，不再参与整个 RMU 的所属馈线判定。
- 同柜非 NOP Y*/Q* 端口若解析出唯一一致馈线，则该馈线作为 RMU 所属馈线；不唯一时保持 CONFLICT/UNRESOLVED，不猜测。
- 报告新增 RMU 所属馈线、NOP 截止馈线和归属判定依据。

## v4.1.117：源端 NOP 馈线排除与 NOP 归属汇总

- 环网柜馈线拓扑分析新增主网源端门控：仅当首个直连 RMU 的**实际入线 Y*/Q*** 同时也是 NOP 所属开关时，整条主网馈线才不参与任何配网设备候选。
- 首柜其它开关存在 NOP 不会误伤主网馈线；`MNA4-AH332 → 17296/Y1`、NOP=`Y3` 的场景继续参与。
- NOP→开关改为同柜内几何最近的唯一 Y*/Q* `CBreakerDis`。
- HTML 新增 `NOP所属RMU / 开关汇总`，并在主网源表列出首柜、入线端口、NOP命中与候选状态。
- 只读属性保持不变：不修改 G，不连接/查询/写入 Oracle。

## v4.1.116：麦加主网馈线标题保留 _X / _Y 后缀

- 主网 Bay 框外馈线标题现在支持 `SHM1-AH341_X`、`SHM1-AH341_Y`、`HRM2-AH308_X` 这类现场命名。
- `_X` / `_Y` 被视为馈线编号的一部分：`SHM1-AH341_X` 固定解析为变电站 `SHM1`、馈线 `AH341_X`，数据库查询时不会丢掉后缀。
- 颜色不限、无背景、Bay 距离、全局一对一、主站设备关联、馈线模型与拓扑分析的其余规则全部保持 v4.1.115 不变。

## v4.1.115：麦加 RMU / 主站名称颜色完全不参与识别

- RMU 环网柜名称：红色、绿色、白色及其它颜色全部等价，颜色不再参与候选过滤、自动聚类样式评分或单柜兜底选择；仍严格执行 RIGHT → BOTTOM → GLOBAL、最大 300 G、柜外 Text、一柜一名 / 一 Text 一柜。
- 配网主站设备关联：主网 Bay 附近馈线标题取消“必须白色”限制；只保留无背景、标题格式、最大距离和 Bay/Text 全局一对一约束。
- 馈线模型、主网 Poke、环网柜馈线拓扑分析共用同一主网 Bay 标题识别器，因此同步支持任意文字颜色。
- 界面帮助与只读说明同步更新，明确“颜色不限”。

# Changelog

## v4.1.114

- 图形工作区新增“环网柜馈线拓扑分析”独立模块，使用主网 Bay 馈线源、`link/node_area`、严格几何补链和 NOP 断点分析 RMU 所属馈线。
- NOP 不再按“最近距离+20G”同时切多个开关；先归属最近 RMU，再按左右侧和中心 Y 对齐精确选择唯一 Y*/Q* `CBreakerDis` 作为传播边界。
- 普通 RMU 输出唯一所属馈线；NOP 边界柜保留两侧馈线及 NOP 端口，不强行归为单一馈线；冲突与无证据分别标记 `CONFLICT` / `UNRESOLVED`。
- 分析模块严格只读：不修改源 G、不生成改写 G、不写数据库；输出 HTML 总报告以及 RMU、端口、FeedLine 审计 CSV。
- 使用麦加实际 `OSLA-08-MNA2-35-MNA4-32-MNA3-29-MNA4-12-ARF2-0` 图验证：9 条主网馈线、84 个 RMU，其中 76 个唯一归属、8 个 NOP 边界柜、0 冲突、0 未确定；97 条 FeedLine 中 94 条拓扑确认。

## v4.1.113
- 同步麦加馈线模型只读说明到 v4.1.112 的真实集合校验逻辑。
- 页面明确显示 7 步流程：全部主网馈线识别、405/13500 唯一确认、已有 FeedLine 合法集合校验、空闲 13503 资源池、优先复用、缺少才创建、HTML 全量报告。
- 固定规则提示改为“优先复用本图有效馈线下空闲馈线段，不足时仅创建缺少数量”。
- 本版本不改变 v4.1.112 馈线关联业务算法。

## v4.1.112：麦加多馈线集合校验 + HTML 全量馈线清单

- 麦加馈线模型校验不再要求已有 FeedLine 必须属于扫描顺序第一条馈线；只要当前 13503 的 `FEEDER_ID` 属于本 G 图主网 Bay 已确认馈线集合，即判定为正确关联并原样保留。
- Domain 错误但 13503/FEEDER_ID 正确时，仅保持原 13503.ID 并修复 Domain/KeyID。
- 未关联、失效或归属图外馈线的 FeedLine，优先从本图所有已确认馈线下的未占用 13503 组成的统一资源池中稳定分配。
- 资源池全部耗尽后，仅创建实际短缺数量；创建目标在本图已确认馈线中按主网 Bay 顺序稳定选择第一条具备有效命名前缀和 BV_ID 的馈线。
- 馈线模型 HTML 新增“本图识别馈线（全部）”表，完整显示主网 Bay 找出的每个馈线标题及 13500 数据库匹配结果；未匹配/不唯一项也保留显示。
- 馈线段明细增加目标馈线 ID / 名称，便于核对跨多馈线资源池的实际分配结果。

# v4.1.111 - 麦加 FeedLine 相邻对齐 / 跨距外扩轨道

- `馈线避让调整` 改为按 RMU 列做全局轨道规划，不再逐条把碰撞馈线吸附到同一个 X。
- 同一 RMU 列中，相邻环网柜之间且 Y 范围不重叠的 FeedLine 复用同一条内侧轨道，保持视觉对齐。
- 跨越其它 RMU 区间的长 FeedLine 因与相邻区间重叠，会按层级依次分配到更外侧轨道；右侧向 +X 外扩，左侧向 -X 镜像外扩。
- 仍只处理压住 RMU 名称或 `NOP / N.O.P` 的 FeedLine；RMU、名称、NOP、设备、连接端点和 `link / node_area / keyid` 均保持不变。
- 新增可配置参数：文字安全间距、错落轨道间距、同列判定范围、最大外移、处理右侧馈线、处理左侧馈线；配置保存到当前用户设置。
- 现场样例 `OSLA-08-MNA2-35-MNA4-32-MNA3-29-MNA4-12-ARF2-0...g` 验证：短的相邻 RMU 馈线统一到 X=4400，跨越多柜的长馈线自动放到外层 X=4450（默认轨道间距 50 G），40 条碰撞馈线全部完成调整，0 条未解决。
- 版本升级至 `v4.1.111`。

# v4.1.110 - 馈线错落防重叠初版

- 在 v4.1.109 文字避让基础上增加馈线最小间距，避免多条已移动竖直主干完全重合。
- 该版本仍按逐段顺序寻找安全 X；v4.1.111 已进一步替换为相邻对齐 / 跨距外扩的全局轨道规划。

# v4.1.109 - 麦加 FeedLine 文字避让

- 图形工作区新增独立处理项 `馈线避让调整`，专门处理 FeedLine 压住环网柜名称或 `NOP / N.O.P` 文字的问题。
- 硬规则：只移动 `FeedLine`；环网柜名称、NOP、RMU 本体、设备和其它图元均保持原位。没有文字碰撞的 FeedLine 完全不修改。
- 识别保护文字时复用麦加 RMU 名称 `RIGHT -> BOTTOM -> GLOBAL` 一对一解析，并额外收集 `NOP / N.O.P` Text。
- 当近似竖直 FeedLine 线段与保护文字相交时，保留原线段两端连接点，在右侧插入正交绕行主干；默认文字安全间距 `20 G`，默认最大右移 `500 G`。
- 仅修改 Workspace 安全副本中的 `FeedLine.d` 和对应 `x/y/w/h` 包围框；`link / node_area / keyid` 等拓扑关联属性保持不变。
- 仅靠向右避让无法安全解决的水平/非正交碰撞标记为未解决，不做猜测；CSV/HTML 报告记录碰撞馈线、移动线段、最大右移和未解决数量。
- 使用现场样例 `OSLA-08-MNA2-35-MNA4-32-MNA3-29-MNA4-12-ARF2-0...g` 实测：97 条 FeedLine 中识别 40 条文字碰撞馈线，40 条均成功向右避让，0 条未解决。
- 版本升级至 `v4.1.109`。

# v4.1.108 - RMU 名称强制框外 + 用户选择图元直接认定

- 麦加 RMU 名称新增硬规则：名称 Text 的中心点必须位于所有已识别 RMU 外框之外；只要 Text 中心落入任意 RMU 框内，就在 RIGHT / BOTTOM / GLOBAL 三个阶段之前直接排除，GLOBAL 兜底也不能使用柜内文字。
- 保持 `RIGHT -> BOTTOM -> GLOBAL fallback` 三阶段一对一分配和 `<=300 G` 最大距离不变；允许外部大字体 Text 的外接框轻微触碰/重叠边框，只要 Text 中心仍在所有 RMU 框外。
- 柱上开关设备识别改为完全服从用户维护的图元文件名单：移除 `RMU_*` 前缀安全排除，也不再因为同一 devref 同时出现在柱上变压器名单中而否决柱上开关；XML 标签、颜色、几何形状、内部结构均不参与设备身份判断。
- 柱上变压器继续以用户维护的 `transformer_element_files` 为唯一设备身份依据，具体 XML 标签不构成限制。设备名称 Text 的现有距离、噪声过滤、一对一分配和数据库唯一性规则保持不变。
- 版本升级至 `v4.1.108`。

# v4.1.107 - 麦加环网柜名称三阶段一对一分配

- 麦加环网柜名称分配改为真正的三阶段一对一规则：第一阶段全图先分配 RIGHT（<=300），第二阶段仅未命中的 RMU 分配 BOTTOM（<=300），第三阶段才对剩余 RMU/Text 做 GLOBAL 最近距离兜底（<=300）。
- 移除 RIGHT/BOTTOM 阶段之前的“Text 必须先属于全局最近 RMU”前置限制，修复名称位于某 RMU 右侧、但几何上更靠近下一只 RMU 左侧时被错误抢走的问题。
- 同一个 Text 仍只允许分配一次，同一个 RMU 仍只允许获得一个名称；NOP、Poke 同步移动及柱上开关原名精确查库规则保持不变。

## v4.1.106 - 麦加环网柜名称识别距离扩大到 300

- 麦加 RMU 名称识别硬距离上限由 `200 G` 调整为 `300 G`。
- `RIGHT -> BOTTOM -> GLOBAL fallback` 三个阶段统一使用 `RMU_LABEL_SEARCH_MAX_DISTANCE = 300.0`。
- 超过 300 G 单位的 Text 不参与 RMU 名称识别；全局最近 RMU 的 Text 一对一所有权规则保持不变。
- 图形位置调整、Poke 跟随、NOP 与 Y*/Q* 水平中心对齐以及其它模型的名称距离均保持不变。
- 版本升级至 `v4.1.106`。

# v4.1.105 - 麦加柱上开关名称原样查询数据库

- 麦加柱上开关查询 13501 / `dms_combined_device.NAME` 时，直接使用 G 文件 `Text.ts` 原始名称。
- 不再删除或替换名称中的空格、横线 `-`、点号 `.` 等字符，也不做大小写或格式标准化。
- 13501 SQL 改为 `WHERE name = :device_name`，不再对柱上开关 NAME 使用 `TRIM(name)`。
- 图上名称选择仍保留现有几何/一对一规则；仅数据库查询值改为原始 Text，其他柱上开关 13501 唯一、13502 唯一、Domain=40、安全副本规则不变。
- 版本升级至 `v4.1.105`。

# v4.1.104 - 环网柜名称优先级与 Poke 同步移动

- 麦加环网柜名称识别固定为 `RIGHT -> BOTTOM -> GLOBAL fallback`，不再使用纯全局最近作为第一选择。
- 每个名称 Text 仍只归属其全局最近的 RMU，再在该 RMU 内按 RIGHT、BOTTOM、GLOBAL 顺序选择，避免相邻柜抢占名称。
- “NOP / 环网柜名称位置调整”移动 RMU 名称时，同时移动与该 Text 绑定的 Poke 点击区域，X/Y 位移与名称完全一致。
- Poke 绑定优先识别 `gfs_rmu_text_id` / `dmm_rmu_text_id` / `dmm_source_text_id`；对旧 G 文件增加 `ahref + 高重合几何区域`兼容兜底。
- CSV/HTML 位置报告增加“名称 Poke 找到/移动”统计。
- NOP 与 Y*/Q* 开关水平中心对齐规则保持不变。
- 版本升级至 `v4.1.104`。

# v4.1.103 - NOP 与环网柜名称位置调整

- 图形工作区新增 `NOP / 环网柜名称位置调整` 独立处理项。
- NOP 对应设备限定为当前 RMU 内可识别为 `Y*` / `Q*` 的 `CBreakerDis`；优先读取 `p_NameString`，缺失时复用现有可见开关名称解析。
- NOP 配对以中心 Y 差为第一排序条件；移动后 NOP 中心 Y 与对应开关中心 Y 完全一致，只允许放在柜体左/右侧。
- NOP 位置支持自动保持原左右侧、强制左侧、强制右侧。
- 环网柜名称按现有麦加全局一对一名称识别，支持外框上/右/下/左四边中点布局。
- 处理继续遵守安全副本原则：源 G 文件不改，输出写入 Workspace `g_output`，同时生成 CSV/HTML 报告。
- 版本升级至 `v4.1.103`。

# v4.1.102 - RMU 逻辑说明补充 Channel Status 状态图元写入

- RMU 自动关联只读说明新增 Channel Status 独立步骤，完整展示柜内状态图元识别、数据库唯一查询、KeyID 校验和回写字段。
- 固定数据库规则新增 Channel Status：表 13566 / Domain 40。
- 明确 `Status` + `channel_status.zt.icn.g` 必须在当前已唯一确定的 RMU 框内且最多 1 个。
- 明确 `dms_terminal_info.COMBINED_ID → dms_channel_info` 联查、排除 `CHAN_NAME` 以 `DR` 结尾、候选唯一、`ID + (40 << 32)` 构造 Expected KeyID。
- 明确状态图元写入 `app=6600000, voltype=-1, p_ReportType=1, state=39, keyid=Expected KeyID`，并清理历史 `app1/voltype1/p_ReportType1/state1/keyid1`。
- 原 v4.1.101 实际关联逻辑不变，本版主要让界面中的业务逻辑说明与真实执行逻辑完全一致。

# v4.1.101 - 麦加 RMU 复用积攒 Channel Status 关联逻辑

- 保持麦加 RMU 框识别、名称分配和 RMU 数据库唯一解析不变；新增柜内 `Status` + `channel_status.zt.icn.g` 精确识别。
- 复用积攒 v4.1.63 的数据库查询：通过 RMU 13501 ID 匹配 `dms_terminal_info.COMBINED_ID`，联查 `dms_channel_info` 并排除 `CHAN_NAME` 以 `DR` 结尾的记录。
- 仅数据库唯一 channel 可关联；使用 `dms_channel_info.ID + (40 << 32)` 构造 KeyID，并验证 table=13566、domain=40。
- Channel Status 精确回写 `app=6600000, voltype=-1, p_ReportType=1, state=39, keyid=<Expected KeyID>`，并支持删除历史 `app1/voltype1/p_ReportType1/state1/keyid1` 残留字段。
- 多个 Channel Status 图元、数据库 0/多条、KeyID 校验失败均阻断；执行阶段再次实时查询并验证后才写入 Workspace 安全副本。
- 麦加仍不引入积攒的图级 FEEDER_ID 校验；Channel Status 从“已唯一确定的麦加 RMU”开始复用积攒后续逻辑。

# v4.1.100 - 熔断器改为用户维护 devref 图元名单

- 新增 `fuse_element_files` 本地配置，熔断器识别只按用户维护的 devref 文件 basename 精确匹配，不再读取图元管理 FUSE 分类。
- 默认麦加熔断器图元：`Fuse_arrow.zwk.icn.g`、`Fuse_NON_SMART.zwk.icn.g`。
- 熔断器配置页复用柱上开关/柱上变压器交互：动态名单、服务器只读搜索、勾选批量添加、搜索面板收起、删除/恢复默认。
- 熔断器名单修改后自动写入 per-user settings 缓存，也支持显式“保存到本地用户缓存”。
- 熔断器数据库、最近柱上变压器、名称派生、KeyID、安全副本逻辑保持不变；报告/帮助同步改为 devref 名单识别表述。

# v4.1.99 - 柱上设备图元名单显式保存到本地用户缓存

- 柱上变压器配置新增“保存到本地用户缓存”按钮；服务器搜索添加、删除、恢复默认后仍会自动保存，也可由用户手动再次保存确认。
- 柱上开关配置同步新增同样的“保存到本地用户缓存”入口，两个模型的配置交互保持一致。
- 保存使用现有 per-user settings 缓存（Windows 下位于当前用户 APPDATA 的 DistributionModelManager/settings.json），替换程序目录后仍可加载；Workspace/config.json 继续作为兼容副本。
- 配置区增加保存状态提示，明确当前名单已写入本地用户缓存以及图元数量。

# v4.1.98 - 柱上变压器配置与柱上开关统一

- 柱上变压器图元名单改为动态高度，减少单个图元时的大块空白；最多直接显示 12 行，超出后内部滚动。
- 新增共享图元服务器只读搜索，复用【图元管理】SSH 配置；搜索区域默认收起，可按需展开。
- 搜索结果使用复选框，支持全选/全部取消、批量添加和双击单项添加；加入名单后直接作为柱上变压器识别图元。
- 移除柱上变压器手工文本输入添加框，使柱上开关/柱上变压器两个模型的配置交互和视觉结构保持一致。

# v4.1.97 - 柱上开关服务器搜索区域支持收起

- “从图元服务器搜索并添加”改为可折叠区域，默认收起，避免服务器搜索框/结果列表一直占据模型配置页面。
- 新增“展开服务器搜索 / 收起服务器搜索”切换按钮，并在展开区域内提供“收起搜索”快捷按钮。
- 收起搜索不会删除柱上开关名单或服务器配置；重新展开即可继续使用只读 SSH 搜索。
- 原有复选框批量添加、双击添加、RMU_* 安全排除和动态名单高度保持不变。

# v4.1.96 - 图元服务器搜索结果改为勾选添加

- 柱上开关图元服务器搜索结果新增明确的复选框，用户勾选后再加入柱上开关图元名单。
- 新增“全选可添加 / 全部取消”，批量添加更直观。
- “添加选中到柱上开关名单”改为“添加勾选到柱上开关名单”；未勾选时按钮保持禁用。
- RMU_* 搜索结果仍显示但不可勾选、不可添加；双击普通图元仍可直接添加。
- 柱上开关正式识别规则、数据库唯一性规则和动态名单高度保持不变。

# v4.1.95 - 柱上开关从图元服务器搜索添加

- 柱上开关图元名单新增图元服务器只读搜索：复用【图元管理】SSH 主机、账号和 element_directory，按关键字递归检索 `.g` 图元。
- 搜索结果支持多选/双击添加，列表展示服务器相对路径，实际保存仍为 devref 文件名；RMU_* 图元继续禁止加入。
- 柱上开关名单改为按项目数量动态增高：少量图元不留大块空白，增多时逐行长高，超过 12 行后内部滚动。

# v4.1.94 - 柱上开关图元名单取消 AR/LBS/SEC 分类

- 柱上开关模型配置改为纯 devref 文件名名单：用户加入的每个图元都直接视为柱上开关，不再选择或维护 AR/LBS/SEC。
- UI 删除设备族下拉框与设备族说明，图元列表压缩为紧凑高度，默认 4 行直接可见，避免大块空白。
- 识别与名称分配均不再使用设备族；`RMU_*` 安全排除和柱上变压器优先排除保持不变。
- 13501 按 NAME 唯一命中后，13502 子设备必须恰好 1 条；0 条或多条均阻断关联，不再按设备族消歧。
- 普通名称继续做既有标准化；合法 `前缀+数字-数字` 复合名称由图上名称本身识别并保留横杠，不依赖设备族配置。
- 自动兼容/迁移 v4.1.93 `pole_switch_element_rules`，只提取 `file_name`。

# v4.1.93 - 麦加柱上开关 / 柱上变压器改为用户维护图元名单

- 柱上开关模型不再依赖【图元管理】LBS / SEC / AR 分类；改为用户维护精确 devref 图元文件名单，每个图元同时配置 AR/LBS/SEC 设备族用于 13502 多子设备消歧。
- 麦加默认柱上开关图元：`SEC_S.zwk.icn.g`、`SEC_NON.zwk.icn.g`、`SEC_NON_H.zwk.icn.g`、`AR_NON_H.zwk.icn.g`。
- 柱上变压器模型不再依赖【图元管理】TRANSFORMER_OH 分类；改为用户维护精确 devref 图元文件名单，默认 `Transformer_OH.pb.icn.g`。
- 两个模型配置页新增图元名单维护，可添加、删除、恢复麦加默认；配置保存到本地用户设置。
- 柱上开关硬排除 `RMU_*` 图元，避免环网柜内部 LBS/Breaker 因误配置进入柱上开关模型。
- FUSE 的最近柱上变压器识别同步复用用户维护的柱上变压器图元名单。
- 原有名称距离、Text 一对一、数据库 NAME 唯一性、KeyID 与安全副本回写规则保持不变。

# v4.1.92 - 麦加柱上变压器固定图元优先识别

- 柱上变压器优先精确识别 `Transformer_OH.pb.icn.g`，命中后直接作为柱上变压器。
- `TRANSFORMER_OH` 图元分类调整为第二级兜底。
- 柱上开关模型显式排除该固定图元，即使旧图元管理配置误标为 LBS/SEC/AR 也不会重复识别。
- 跨模型名称 Text 锁同步认可固定图元，保证柱上变压器与柱上开关不重复占用同一个 Text。

# v4.1.91 - channel_status 距边数值完整显示

- 修复 channel_status “距边” SpinBox 在高 DPI / 大字体环境下后缀 `px` 被裁切、只显示为 `p` 的问题。
- 单功能 channel_status 移动页和组合处理页统一把距边输入框宽度从 100 调整为 140，确保 `0~1000 px` 均可完整显示。
- 保留 v4.1.90 的深绿色高对比上下按钮和全局禁用滚轮改值规则。

# v4.1.91 - SpinBox 上下按钮高对比优化

- 优化全程序 QSpinBox 的上/下微调按钮：由浅灰背景改为与应用统一的深绿色按钮，现场显示器和 Windows 高 DPI 下更清晰。
- 上/下按钮使用白色箭头图标，并补充 hover/pressed 状态；按钮宽度和输入区右侧留白同步调整，避免数值与按钮重叠。
- 仅调整视觉和可点击性；v4.1.88 起的“鼠标滚轮不修改 ComboBox/SpinBox 值、继续滚动页面”规则保持不变。

# v4.1.89 - 组合处理 Poke 参数补充全选 / 全部取消

- 「图形工作区 → 组合处理（一键）」的 `Poke 参数` 区新增“全选”和“全部取消”。
- “全选”同时勾选主网馈线标题 Poke 与 SMART / SMR 智能 RMU Poke；“全部取消”同时取消两项。
- 组合任务运行期间这两个批量选择按钮会与其它处理参数一起禁用，避免执行过程中修改配置。
- 原有组合处理步骤区的“全选 / 全部取消”保持不变，两组勾选区域现在都有一致的批量选择操作。

# v4.1.88 - 图形组合处理流水线 + 全局禁用控件滚轮修改

- 图形工作区新增“组合处理（一键）”：可勾选环网柜网络图元清理、channel_status 移动、Poke 跳转，按固定顺序作用于同一份 Workspace 安全副本。
- 每个 G 文件只有全部勾选步骤成功后才发布到最终 g_output；单文件失败不生成半成品，并继续处理其它文件。
- 组合处理生成统一 HTML/CSV 总报告，同时保留每个文件各步骤的详细报告。
- 全程序拦截 QComboBox / QAbstractSpinBox 的鼠标滚轮修改；滚轮继续用于页面滚动，点击和键盘编辑不受影响。

# v4.1.87 - 图形工作区本地文件源自适应高度

- 修复图形工作区选择“本地文件 / 目录”时仍按隐藏 SSH 页面高度预留空间、产生大块空白的问题。
- 文件来源页改为只根据当前可见页计算 `sizeHint/minimumSizeHint`：本地模式自动收缩为单行路径选择；切到 SSH 时再自动展开完整 SSH 参数、远程文件表。
- Windows 高 DPI 下切换本地/SSH来源后主动刷新布局几何，避免残留旧高度。
- 仅调整图形工作区文件来源布局；Poke、网络图元清理、channel_status 移动和文件处理逻辑不变。

# v4.1.86 - 图形工作区运行修复与导航顺序调整

- 修复图形工作区多个任务在文件准备阶段调用已删除 `_refresh_poke_source_summary()` 所导致的运行时异常。
- 图形任务文件准备完成后统一调用现有 `_sync_poke_source_from_workspace(rebuild_remote=False)`，本地与 SSH 两种来源均可正常继续执行。
- 左侧菜单将“图形工作区”移动到“模型工作区”正下方；数据库、图元管理顺延。
- 同步修复模型工作区“数据库设置”按钮的导航行号。

# v4.1.85 - 麦加环网柜 channel_status 状态点移动

- 图形工作区新增“环网柜 channel_status 移动”，与 Poke 跳转、环网柜网络图元清理并列在“图形处理类型”中。
- 处理算法直接复用用户提供的 G File Studio v2.18.244 现场逻辑：只认有效 RMU 外框（BusDis + CBreakerDis + ZhaiWaiJieDiDaoZha），优先取中心位于外框内的 `channel_status.zt.icn.g:channel_status` Status；兼容旧图时允许外框扩展 40 像素；多个候选取距 BusDis 中心最近者，同一 Status 只允许归属一个 RMU。
- 支持 8 个框内目标位置：左上、上中、右上、左中、右中、左下、下中、右下，并支持 0~1000 px 距边设置；默认左下角、5 px，与 G File Studio 默认保持一致。
- 只对 channel_status Status 做刚体平移，更新其 `x/x1/x2/cx/mergex`、`y/y1/y2/cy/mergey` 和 `d` 路径坐标；不修改 ID、devref、颜色、尺寸、RMU 外框、母线、设备、文字或连接线。
- 已用用户提供的 4 个麦加现场 G 文件与 G File Studio v2.18.244 做逐 Status 坐标对比，结果完全一致；原始 G 文件 SHA256 保持不变。
- 仍采用图形工作区共用的本地/SSH只读来源，只写 Workspace `g_output` 安全副本，并输出 HTML/CSV 移动报告。

# v4.1.84 - 麦加环网柜网络图元清理

- 图形工作区新增“环网柜网络图元清理”任务，与 Poke 跳转并列在“图形处理类型”下。
- 固定删除 `<Status>` 图元的三类 devref：`NariPd_Generator.zt.icn.g`、`NariPd_Temporary_Cable.zt.icn.g`、`NariPd_General_Note.zt.icn.g`；兼容现场需求中出现的 `General_Note.zt.icg.g` 旧拼写。
- 规则不做距离、RMU 名称或数据库推断。对用户提供的 4 个麦加样本核对后，三类图元数量与 RMU 数量逐文件完全一致：125/74/41/16，每个 RMU 各一组 G/L/N。
- 图形工作区的本地/SSH只读文件来源提升为所有图形任务共用；原始 G 文件不修改，清理结果只写 Workspace `g_output` 安全副本，并输出 HTML/CSV 清理报告。

# v4.1.83

- 将左侧“图形处理”改为与模型工作区一致的一级“图形工作区”，使用标准侧栏配色、对齐和选中状态。
- 删除左侧 Poke 二级菜单和折叠分组，避免导航层级继续膨胀。
- 图形工作区新增“图形任务 / 图形处理类型”下拉编排，当前提供“Poke 跳转处理”，并预留后续其它图形操作。
- 新增“当前图形帮助”，Poke 文件源、执行逻辑、SSH 只读和 Workspace 安全副本规则保持不变。

# v4.1.82

- 【图形处理】左侧导航最终采用“可折叠一级分组 + 缩进二级功能”的结构，视觉层级参考现场批处理工具。
- 一级分组增加 `▾ / ▸` 箭头、绿色同主题圆角边框；不使用蓝黑色卡片，整体配色继续与现有主侧栏保持一致。
- 【Poke 跳转】保持二级缩进，当前功能仍使用原金色选中态；运行历史/设置/帮助继续位于分组之后。
- 分组自定义行设置显式高度，避免 Windows 高 DPI 下出现重叠覆盖。
- 本版只调整左侧导航视觉与折叠行为，不改变 Poke、主网设备、Bus 或数据库关联逻辑。

# v4.1.81

- 配网主站设备安全回写统一采用现场既有主网规则：CBreaker / Disconnector / GroundDisconnector / Bus 的 `app` 均固定为 `100000`；CBreaker `state=41`，Disconnector / GroundDisconnector `state=31`，Bus `state=10`；`voltype` 使用数据库最新 `BV_ID`，`p_ReportType=1`，`keyid=Expected KeyID`。
- 执行【模型关联】前会对每个文件重新运行主网数据库/上下文校验；只有执行前解析出的 table/domain/device/Expected KeyID 与用户校验阶段确认的目标完全一致时才允许写回。目标变化、目标消失或不再唯一时直接跳过并报告，不会静默改绑到新目标。
- 左侧导航按现场要求简化为普通一级“图形处理” + 缩进二级“Poke 跳转”；“图形处理”与模型工作区/数据库/图元管理保持完全相同的一级对齐、颜色和高度，不再使用单独卡片或整体缩进。

# v4.1.80

- 左侧【图形处理】分组整体向右缩进，不再与一级菜单保持同一横向基线；视觉参考现场批处理分组。
- 【Poke 跳转】在分组内部再次缩进，形成清晰的“一级分组 → 二级功能”层级。
- 颜色继续使用主侧栏绿色体系；分组标题使用同色系深绿圆角块，Poke 选中态继续使用全局金色。


- 图形处理二级导航统一回主侧栏配色：父级/子级使用 `#004E3D / #006650`，选中 Poke 子项使用与主导航一致的金色 `#B58A36`。
- 删除蓝黑色 `navGroupButton` 卡片视觉，父级只承担展开/收起，不与子页同时高亮。
- 复合导航背后的 QListWidgetItem 不再绘制可见标题，修复 Windows 高 DPI 下的文字叠层/露底。
- 业务逻辑不变。

# v4.1.78

- 主网 `Bus` 保持固定使用 `410 / busbarsection`、Domain=`40`，但关联范围从 `BAY_ID` 改为 **只检查变电站 `ST_ID`**；Bus 不再校验或要求 410 记录的 `BAY_ID` 与当前主网框一致。
- 同一主网框有多个 Bus 时，从该 `ST_ID` 下未使用的 410 记录中任意一对一分配；已有正确的 410/Domain 40 关联优先保留。为保证重复运行稳定，实际实现使用 G XML 顺序 + 数据库 ID 顺序作为“任意”配对顺序。
- 只要同站 410 可用记录数不少于图形 Bus 数即可处理；数据库同站记录多于图形 Bus 时只取所需数量，少于图形 Bus 时阻断并报告记录不足。
- CBreaker / Disconnector / GroundDisconnector 仍保持现有 BAY_ID 关联规则不变；Bus 回写属性继续使用 `app=100000`、`p_ReportType=1`、`state=10`、数据库 `BV_ID` 和 410/Domain 40 KeyID。

# v4.1.77

- 修复左侧【图形处理】二级菜单在 Windows / 高 DPI 下发生重叠、覆盖【运行历史】的问题。
- 【图形处理】分组标题与【Poke 跳转】改为同一个 QListWidget 复合行，由单一高度统一管理，不再使用两个独立 setItemWidget 行。
- 展开时固定为“圆角分组标题 + 缩进子菜单”，收起时只保留分组标题；切换语言或缩放后同步重算组高度。
- 右侧 Poke 页面、Bus 关联、数据库访问及所有模型业务逻辑均保持 v4.1.76 不变。

# v4.1.76

- 左侧“图形处理”改为可折叠的分组式二级菜单，视觉参考现场批处理工具：圆角分组标题 + 展开/收起箭头 + 下方缩进子功能，不再把“图形处理”和“Poke 跳转”渲染成两个同级大按钮。
- “图形处理”分组标题只负责展开/收起；点击“Poke 跳转”进入现有右侧全宽 Poke 页面，右侧业务界面与处理逻辑保持不变。
- 当前进入 Poke 功能时，分组采用轻量激活态，不再出现大面积金色父菜单块；后续新增图形处理小功能可继续按同一分组结构向下扩展。
- 主网 Bus、Poke、模型校验、数据库关联和安全回写规则均保持 v4.1.75 不变。

# v4.1.75

- 主网 `Bus` 继续固定使用 `410 / busbarsection`、Domain=`40`，但关联方式调整为 **Bay 内按数量一对一任意配对**：同一主网框内有 N 个 Bus，数据库该 BAY_ID 下有 N 条 410 记录时即可关联，不再要求 410 唯一。
- “任意配对”使用稳定顺序实现（优先保留已经正确的 410/Domain 40 关联，其余按 G XML 顺序与数据库 ID 顺序配对），避免同一文件重复校验时结果随机变化。
- 如果 G 图 Bus 数量与数据库 410 数量不一致，则阻断 Bus 自动关联并报告数量差异，不猜测、不复用同一 410 记录。
- 参考现场既有已关联 G 文件，主网 Bus 安全副本回写使用 `app=100000`、`p_ReportType=1`、`state=10`、`voltype=busbarsection.BV_ID`、`keyid=410/Domain40 Expected KeyID`。

# v4.1.74

- 图形处理改为真正的主侧栏二级菜单：`Poke 跳转` 直接显示在 `图形处理` 下方，右侧仍保持全宽 Poke 工作页，不再增加页面内嵌导航。
- 配网主站设备关联新增主网 `Bus`：固定使用 `410 / busbarsection`，Domain=`40`。
- `Bus` 与 `CBreaker` 共用已确认的主网 Bay 上下文：通过白色馈线标题确定 405 站点与唯一 406 `BAY_ID`，再按该 `BAY_ID` 查询 410；只有唯一 busbarsection 才允许关联。
- 同一个主网 Bay 内如果 G 图由多个 `Bus` 图形片段表示同一物理母线段，允许这些 Bus 图元写入同一个 410 设备 KeyID；数据库同一 Bay 存在多条 410 时不按顺序/距离猜测，直接阻断。
- Bus 回写继续使用 `app=6500000`、`p_ReportType=1`、`state=10`、数据库 `BV_ID -> voltype`，KeyID 按 `410 + Domain 40` 校验后写入 Workspace 安全副本。

# v4.1.73

- 【图形处理】页面取消左侧嵌套二级绿色导航，Poke 跳转改为整页全宽布局，避免“画中画”视觉。
- 将模型工作区的本地/SSH只读文件来源能力直接加入 Poke 跳转页面：来源切换、SSH 参数、测试/保存、刷新远程 G 列表、搜索、选择、下载均可在当前页面完成。
- Poke 页面与模型工作区共用同一份文件来源和远程文件选择状态；两边选择保持同步，不改变 SSH 只读安全策略。
- 远程 G 文件表在图形处理页面按需刷新，隐藏页面不重复重建大表，避免无意义的 UI 性能损耗。
- Poke 处理逻辑、主网馈线跳转规则、智能 RMU Poke 规则及 Workspace 安全副本策略保持不变。

# v4.1.72

- 麦加现场版新增左侧一级【图形处理】模块，二级功能新增【Poke 跳转】。
- 主网馈线标题（如 GVCM-AH304）通过 405 / SUBSTATION.NAME 精确站名匹配读取 GRAPH_NAME，生成 `<GRAPH_NAME>?locateLabel=AH304&&scaleFlag=true`；名称上没有相关 Poke 时自动新增，已有相关 Poke 时复用/修复并清理重复项。
- Poke 几何严格包住已识别的馈线标题 Text，Poke 运行属性复制 G File Studio v2.18.240 的 RMU Poke 基线。
- 智能 RMU（SMART / SMR）同步加入 Poke 跳转：复用麦加 RMU 识别，按 `DMS_COMBINED_DEVICE.NAME -> FEEDER_ID -> DMS_FEEDER_DEVICE -> SUBSTATION -> SUBCONTROLAREA` 生成 `<区域>-<站>-<馈线>-<RMU>.com.pic.g`。
- 图形处理沿用模型工作区的本地/SSH只读文件来源；任何 Poke 修改只写入 Workspace `g_output` 安全副本，并生成 HTML / CSV Poke 报告。

# v4.1.71

- 麦加所有模型的 HTML 报告统一新增“图形馈线”结果表，直接列出当前 G 图中识别到的全部馈线及 13500 / dms_feeder_device 数据库匹配结果。
- 所有模型导出 CSV 时同步生成独立的 `*_图形馈线.csv`（英文环境为 `*_graph_feeders.csv`），字段仅保留 G 文件、图形馈线、数据库 FEEDER_ID/CODE/NAME/ST_ID 和匹配结果。
- 图形馈线即使数据库未找到或出现多条，也会保留在报告中并显示 NOT_FOUND / MULTIPLE 等结果，不再因为数据库未确认而从报告中消失。
- 馈线模型 HTML/CSV 隐藏识别方式、判定依据、拓扑归属证据等内部算法字段，只展示结果；“任选一条馈线创建/关联 13503 馈线段”的执行规则保持不变。
- 模型校验和模型关联完成后的最终报告均携带相同的图形馈线结果。

# v4.1.70

- 麦加环网图馈线识别改为严格主网链路：最内层含 CBreaker 的 Bay 框 → 最近主网标题 → substation.NAME → substation.ID → dms_feeder_device.ST_ID → 馈线 NAME/CODE。
- 主网标题支持 GVCM-AH304 / ARF4-AH348 / ARF4-AH3101 这类完整馈线编码。
- 每次执行任意模型时，Console 统一输出当前 G 图全部数据库确认馈线（标题、变电站、ST_ID、馈线名、FEEDER_ID）。
- 馈线模型从完整馈线列表中取第一条作为整图目标；全部 FeedLine 归入该馈线，缺少的 13503 仍必须全部创建后再关联。
- 文件名 token、根 facID、自由 Text 不再作为麦加环网图主网馈线清单的权威来源。

# v4.1.69 - 2026-09-29

- 麦加馈线模型放宽环网图识别：当前 G 图只要能唯一确认任意 1 条真实馈线，就足以作为整张图的目标馈线。
- 馈线识别证据按当前 G 图主网 Bay、当前 G 文件名中的馈线 token、当前 G 图严格格式 Text 依次尝试；不再要求识别环网图内全部馈线。
- 一旦找到 1 条馈线，当前 G 图全部 FeedLine 都归入该馈线；优先使用该馈线已有未占用 13503，数量不足时仅创建缺少数量，再执行关联。
- `MAKKAH_RING_FEEDER_NOT_FOUND` 仅在当前 G 图通过以上三种证据仍无法唯一确认任何馈线时出现。

# v4.1.68 - 2026-09-29

- 修复模型类型切换时“上一模型/上一说明样式短暂闪现”的问题。
- 模型切换流程恢复为与吉达 v4.1.96 一致：解除旧高度 → 切换 QStackedWidget 页面 → 激活新页面布局 → 下一事件循环校准最终高度。
- 移除 v4.1.67 新增的 QStackedWidget `setUpdatesEnabled(False/True)` 冻结重绘逻辑，避免同步 `currentChanged` 高度计算与二次强制重绘叠加造成闪烁。
- 仅修改界面切换时序，不改变麦加任何模型识别、数据库匹配、关联和安全回写规则。

# v4.1.67 - 2026-09-29

- 模型关联逻辑说明区的显示结构、卡片最大高度、边距和间距对齐吉达 v4.1.96。
- 模型切换改为原子式页面切换：切换期间暂停 QStackedWidget 重绘，完成新页面布局和高度计算后再一次性显示，避免短暂闪回上一模型。
- 仅调整 UI 显示与切换行为，麦加既有识别、数据库关联和安全回写规则不变。

# v4.1.66 - 2026-09-29

- UI only: restored the model workflow explanation cards to the exact Jeddah v4.1.93 QLabel layout behavior.
- Removed CompactLogicLabel from RMU, pole-switch, pole-transformer, fuse, feeder and master-station explanation panels.
- Workflow cards now use normal word-wrapped QLabel + QSizePolicy.Maximum so each row follows its natural text height without large blank gaps.
- Makkah business rules and association algorithms are unchanged.

# v4.1.65 - 2026-09-29

- 修复模型“自动关联完整逻辑”说明卡片在宽屏下文字只有一行但卡片仍保留多行高度的问题。
- 新增 CompactLogicLabel：卡片按当前实际宽度重新计算 WordWrap 所需高度，单行说明只保留文字高度和少量内边距，多行内容才自动增高。
- RMU、配网主站、柱上开关、柱上变压器、熔断器、馈线说明卡片统一使用紧凑自适应高度；业务识别和关联逻辑不变。

# v4.1.64 - 2026-09-29

- 麦加模型工作区的只读“自动关联完整逻辑”说明区显示样式与吉达 v4.1.93 对齐：说明框按工作区宽度横向展开，不再使用居中固定最大宽度。
- 柱上开关、柱上变压器、熔断器说明控件直接采用吉达相同的 QGroupBox 结构；卡片边距、间距与 padding 同步吉达。
- 配网主站设备、馈线说明区移除居中限宽；RMU 双栏说明区按吉达比例和卡片样式显示。
- 本版本仅调整界面展示，不改变麦加现有设备识别、名称匹配、数据库关联及安全回写逻辑。

# v4.1.63 - 2026-09-29

- 修复模型逻辑说明面板因仅设置 maximumWidth 而被 Qt 压缩成狭窄竖条的问题。
- 柱上开关、柱上变压器、熔断器、配网主站、馈线说明面板改为 900~1180 px 的可扩展居中布局；RMU 双栏说明区同步扩大到 680~900 px。
- 本次仅调整 UI 布局，不改变任何设备识别、数据库匹配、KeyID 或写回逻辑。

# v4.1.62 - 2026-09-29

- 移除 RMU 多名称方向选择时的提示弹窗；保存设置时不再打断用户操作。
- RMU 实际名称匹配、全局最近距离、Text 一次性占用和 200 距离规则保持不变。

# v4.1.61 - 2026-09-28

- Makkah device-name matching is now global-nearest within each model: RMU, pole switch and pole transformer all use rectangle-to-rectangle minimum-edge distance only, with a hard 200-unit limit.
- Text ownership is strictly one-to-one. Once a Text XML ID is assigned to one device in the current model run, it is removed from the candidate pool and cannot be reused by another device. Identical text content with different Text IDs remains independently assignable.
- RMU keeps its dedicated noise exclusions (pure decimals, phone-like values, hyphenated strings, NOP/SFI/DAS/OK and descriptive RMU/SMART labels); the old pure-integer priority and TOP/RIGHT/GLOBAL priority no longer affect ownership.
- Main-network Bay captions also use one-to-one nearest ownership and a 200-unit maximum while retaining their white/no-background feeder-title rule.
- RMU internal breaker visible-label distance now uses rectangle minimum-edge distance instead of center-point distance.
- Read-only workflow panels are narrower and more compact so they do not occupy the full work-area width.

# v4.1.59 - 2026-09-28

- 修复熔断器模型校验完成后导出 HTML 报告时报 `NameError: _table_interaction_script is not defined` 的问题。
- 恢复公共 HTML 表格筛选/行选择脚本，熔断器报告可正常生成并打开。
- 不修改任何 RMU、柱上开关、柱上变压器、熔断器、馈线的识别或关联业务逻辑。

# v4.1.58 - 2026-09-28

- Unified all Makkah model workflow explanations to the same read-only step-card layout used by the reference Jeddah screen.
- RMU and main-station descriptions were split from long paragraphs into separate numbered cards; pole switch, transformer, fuse and feeder cards now use the same spacing/padding.
- This release changes presentation only; model discovery, database association and writeback logic remain unchanged from v4.1.57.

# v4.1.57 - 2026-09-28

- Makkah unified all device-to-name geometry to rectangle minimum-edge distance; removed center/anchor distance from RMU, pole switch, pole transformer, fuse-derived transformer naming and main-station Bay captions.
- Makkah feeder model simplified: select the first database-unique feeder actually present in the current ring drawing, assign every FeedLine in that G file to that feeder, create missing 13503 sections as needed, and relink old cross-feeder section links to the selected feeder.
- Rewrote model pages with explicit read-only step-by-step association rules.

# v4.1.56 - Makkah pole-device alignment with Jeddah

- Pole switch recognition/name allocation follows Jeddah rules; Makkah DB association remains NAME-only and does not validate FEEDER_ID.
- Pole transformer recognition/name allocation follows Jeddah TRANSFORMER_OH rules (numeric white/no-background, TOP→RIGHT→GLOBAL, max 300); DB association uses unique 13505.NAME only.
- Added FUSE model based on Jeddah nearest-Transformer_OH exclusive assignment; Makkah uses unique 13505.NAME and 13513.NAME without FEEDER_ID validation.
- Added FUSE UI selection, reports, CSV/HTML export, execution workflow, and read-only rule descriptions.

## v4.1.54

- Added root-level `setup.ps1` for Windows local setup.
- `setup.ps1` detects Python 3.11+, creates or reuses `.venv`, upgrades pip, installs `requirements.txt`, and starts the application by default.
- Use `./setup.ps1 -NoRun` to prepare the environment without launching the application.

## [4.1.50] - 2026-09-27

### Makkah pole-switch exact NAME association
- Pole-switch graphical names now match only `dms_combined_device.NAME` (table 13501) by exact trimmed string.
- Removed the previous `CODE` fallback; `FEEDER_ID` is not queried or validated for Makkah pole-switch association.
- Exactly one NAME match continues to the existing 13502 child-device resolution and KeyID association; zero or multiple NAME matches are blocked.
- Existing pole-switch device discovery, name format/color/background filters, 300-unit distance limit, and Text-ID one-time assignment remain unchanged.

## [4.1.48] - 2026-09-27

### Makkah central configuration parity with Jeddah
- Ported only the Jeddah v4.1.65 central-configuration ownership/save/sync workflow into the Makkah build; RMU, feeder, main-station, pole-device, EFI and other site-specific business logic remain unchanged.
- Startup is local-cache only and performs no central/Oracle/SSH connection. A central pull occurs only after the operator explicitly clicks `连接并同步中央配置`.
- Central shared files use `/home/up8000/nari-international/distribution-model-manager/config` with `element_marks.json`, `database.json`, `file_server.json`, and `instance.json`.
- Normal clients may edit/test/refresh and save local database, SSH/file-server and element-mark settings. Only publishing shared configuration to the central repository is Admin-gated.
- Any machine may explicitly take over Admin. Takeover changes only `instance.json`; it does not automatically pull or publish database/file-server/element configuration.
- Active Admin sessions check only `instance.json` every 10 seconds. If another client takes ownership, the old Admin session automatically downgrades while retaining local edit/save/sync rights.
- Admin ownership is protected by `admin_machine_id` + `admin_epoch`; publish/release revalidate ownership server-side to block stale sessions.
- Central writes use a lock directory, temporary JSON files, server-side atomic replacement, directory reuse, and mode 0600 for shared config files.
- Complete local settings are persisted in the per-user cache outside the application/workspace, while `workspace/config.json` remains a compatibility copy.
- Element Management now exposes the same three independent Jeddah actions: local-cache save, Admin publish to central, and manual central pull.

## [4.1.47] - 2026-09-27

### Makkah RMU numeric-name priority
- RMU cabinet-name selection now prefers a pure integer label over pure-letter or alphanumeric candidates on the same configured side of the same cabinet.
- The existing geometry rules still apply first: candidates must be in the configured direction and within the 200-unit RMU name-distance limit.
- Decimal numeric annotations such as `21.449047` and `39.555820` remain hard-excluded; telephone-like long numbers beginning with `0` and hyphenated labels remain excluded as before.
- Example: for nearby labels `902`, `RMU`, `21.449047`, and `39.555820`, the resolved RMU name is `902`.
- The new priority is enabled only by the RMU model and does not change pole-switch, pole-transformer, feeder, or generic parser behavior.

## [4.1.46] - 2026-09-27

### Makkah RMU name noise filtering
- RMU cabinet-name discovery now rejects telephone-like long pure-numeric labels that start with `0` (for example `0551491216`).
- RMU cabinet-name discovery now rejects any candidate containing `-`, so engineering labels such as `V2-W-H-0008` and `V2-W-M-H-0009` cannot be selected as RMU names.
- Normal numeric cabinet names such as `42213` remain valid.
- The new rules are scoped to the RMU model cabinet-name recognition and do not change feeder, pole-switch, or pole-transformer name rules.

## [4.1.45] - 2026-09-27

### RMU PWBH EFI discovery
- Replaced the hard-coded `NariPd_Normal.pwbh.icn.g` discovery rule with the Element Management classification `RMU_PWBH_EFI`.
- At runtime the RMU module first reads element-catalog records carrying `RMU_PWBH_EFI`, then uses those marked definition file names/paths to recognize `pwbh` instances in the current G drawing.
- Only matching `pwbh` instances already inside the current RMU frame are treated as EFI; matching symbols outside the RMU are ignored.
- The downstream EFI association logic is unchanged: current RMU ownership, table 13533 by default, exact `CODE=EFI INDICATOR`, Domain 40 by default, KeyID verification, and `keyid1` writeback remain intact.
- Removed the old hard-coded filename fallback: without an `RMU_PWBH_EFI` mark, the file is not auto-classified as EFI.
- Added focused regression tests for classified-file matching, no legacy fallback, non-EFI classification rejection, and RMU-frame scoping.

## [4.1.44] - 2026-09-27

### Packaging
- Makkah build artifacts now include the site tag `makkah` in the PyInstaller application name, dist folder, EXE name, and release ZIP name.
- `build_exe.ps1` now produces `Distribution_Model_Manager_makkah_v<version>.zip` to avoid mixing site-specific releases.

# v4.1.43

- Pole-switch and pole-transformer name resolution no longer uses global device/Text ownership during discovery. Target devices are processed one by one.
- Name format, configured color class, configured background state, and module distance limit are hard candidate gates before nearest-name selection (pole switch <= 300 G units; pole transformer <= 200 G units).
- Text allocation identity is the Text XML id (with xml_index fallback only when no id exists): once a Text id is assigned, it is removed from all later device calculations.
- Equal visible name content may still be assigned multiple times when it comes from different Text ids, matching drawings that legitimately contain repeated device names.
- Persisted module-specific name settings (`pole_switch_name_*` / `transformer_name_*`) are honored as a fallback when generic active-panel `name_*` values are absent.
- Updated the pole-switch and pole-transformer settings descriptions to document one-device-at-a-time matching and one-time Text-id allocation.
- The previously discarded Element Management `.g`-only display requirement remains excluded.

# v4.1.42

- Added hard name-distance limits in G-file coordinate units: RMU cabinet name <= 200, pole-switch name <= 300, and pole-transformer name <= 200.
- Candidates beyond the corresponding limit are removed before nearest-name ranking, so a far-away label can never be selected as a fallback.
- RMU selected-direction recognition now enforces `RMU_LABEL_SEARCH_MAX_DISTANCE`; the optional auto-cluster path is capped by the same limit.
- Pole switch and pole transformer share the same global Text resolver but use independent hard limits (300 / 200).
- No Element Management `.g`-only filtering change is included; that discarded requirement remains excluded.

# v4.1.41

- Reworked Makkah main-network Bay recognition around the actual drawing structure: only the innermost rectangle containing a `CBreaker` is considered a main-network Bay frame.
- Bay captions must be the nearest feeder-like `Text` within 120 G units, with white visible text color and no background. Labels such as `MNA4-12` / `ARF2-07` are parsed into station and feeder hints; red/background/far-away captions are rejected instead of borrowed from adjacent Bays.
- Added explicit station -> feeder -> Bay resolution. Station table 405 is resolved from the station prefix, feeder table 13500 is matched only inside that station, and Bay table 406 is matched from the resolved feeder identity.
- The unique breaker row in table 407 is used to cross-check the resolved station/BAY_ID. A missing or non-unique breaker blocks automatic association.
- Main-network devices inside a confirmed frame are now associated by the same BAY_ID: CBreaker -> 407, Disconnector -> 408, GroundDisconnector -> 409. `key_name` is no longer required when the Bay contains a unique row of that device type; ambiguous same-type Bay records are blocked instead of guessed.
- Objects outside a qualified CBreaker frame are ignored by the main-station module, avoiding accidental association of ring-side switches that are not part of a main-network Bay.
- Feeder source-anchor discovery now uses the same CBreaker-frame + white/no-background title rule, so source-feeder counting and main-station association share one visual business rule.
- Added focused v4.1.41 regression tests for frame qualification, white/no-background caption filtering, direct BAY_ID association without `key_name`, ambiguity blocking, and far-caption rejection.

# v4.1.40

- Added Makkah multi-feeder ring **Feeder Ownership Resolution** for composite G drawings.
- Main-station `CBreaker` + nearby feeder title is resolved against feeder table 13500 and used as a strong source anchor. Duplicate source breakers for the same database feeder are deduplicated by FEEDER_ID when counting feeders.
- Trusted already-associated RMU / pole-switch / pole-transformer devices provide local FEEDER_ID evidence. Global nearest-device distance is no longer the primary ownership rule for multi-feeder drawings.
- NOP labels are converted into propagation barriers. Different feeders may exist on opposite sides of a NOP without becoming a conflict.
- Missing XML connectivity is repaired conservatively: explicit `link/node_area` first, then only endpoint-to-endpoint <= 3 G units and endpoint-to-segment <= 2 G units.
- A strict connected component with more than one feeder becomes `CONFLICT`; a component with no reliable feeder evidence becomes `UNRESOLVED`. Both are blocked from automatic write-back.
- Composite drawings continue to leave root `facID` untouched; each FeedLine is grouped under its resolved FEEDER_ID and shares that feeder's section pool.
- Feeder reports now expose ownership status/method/evidence, candidate FEEDER_IDs, confirmed source-feeder count, NOP boundary count, and strict geometry repair count.
- Added focused v4.1.40 tests for NOP splitting, conflict blocking, strict endpoint repair, ownership-based validation without global nearest-device dependency, and multi-feeder grouping.

# v4.1.39

- 馈线识别来源 UI 改为按当前模式显示：FACID 仅显示 FACID 相关状态；文件名模式仅显示批量变电站输入；人工模式仅显示人工目标馈线输入。
- 人工目标馈线在 MANUAL 模式下始终可编辑、可删除、可清空；未选中的输入框不再以 disabled 状态占据界面。
- “允许覆盖现有 facID 和馈线段关联”仅在文件名/人工模式显示；FACID 模式隐藏。
- 仅调整 UI/i18n 表现，FACID / FILENAME / MANUAL 三种业务解析与 v4.1.38 保持一致。

# v4.1.38

- Manual feeder input is now an absolute target. `ABH AH303` resolves only that station+feeder; zero matches return `MANUAL_FEEDER_NOT_FOUND` and never fall back to current facID or file-name resolution. Multiple exact matches are blocked.
- File-name batch mode may use one operator-supplied substation name such as `ABH` for every selected file. Each file independently extracts its final feeder token.
- Automatic station resolution now supports region-prefixed file identifiers: `JED-NTH-ABH-03` first tries the full site identifier and then safely falls back to the actual substation segment `ABH` when 405/substation.NAME does not include region prefixes.
- Numeric file token `03` is matched only inside the resolved station feeder set and resolves uniquely to a business feeder such as `AH303`; a full token such as `AH303` is used directly.
- Existing facID remains current-state evidence only. A different manual/file-name target remains the selected target; write-back is blocked until the explicit override option is enabled.
- Single-file and batch-folder processing continue to share the same resolver. Composite drawing safety boundaries and all existing section/Domain/create/write-back rules are unchanged.
- Chinese and English presentation updated together.
- Regression: 240 passed, 1 skipped.

# v4.1.36

- Optimized **Refresh G File List** only; no RMU/feeder/Oracle/write-back business rules changed.
- After the read-only SFTP directory check, compares `(name, size, mtime)` with the currently loaded list. If unchanged, reuses the existing 2k+ row table, selection, search visibility, validation snapshot, and association table instead of rebuilding them.
- When the remote list really changed, disables continuous `ResizeToContents` while rows are populated and calculates column widths only once after the batch, matching the fast table-update pattern used by GFileStudio.
- Chinese and English refresh status messages both indicate whether the table rebuild was skipped.

# v4.1.35

- English UI presentation-only fix: `Apply Model Association` action buttons now size to the full translated caption instead of clipping.
- Model-association confirmation/completion dialogs, final task status, and completion action buttons are fully localized in English mode.
- No RMU/feeder validation, Oracle, KeyID, candidate-selection, association, or G-file write-back business logic changed.

# Distribution Model Manager v4.1.34

- UI-only refinement: Task Progress / 任务进度 title now uses the same white background as the Console card, removing the pale-green title patch.
- No validation, Oracle, RMU, feeder, KeyID, association, write-back, SSH, report-data, or execution logic changed.

# Distribution Model Manager v4.1.33

- Model Association now executes Oracle revalidation, RMU/feeder association, and G-file write-back in a background QThread while the Qt GUI event loop remains responsive.
- The association progress bar stays in indeterminate/busy mode (left-right animation) for the whole association/write-back/report phase; exact counts remain in the status text and Console log.
- Completion restores the normal percentage progress bar at 100%; failure restores it at 0%.
- This is execution scheduling/presentation only. Validated snapshots, Oracle queries, RMU/feeder decisions, KeyID calculation, target selection, write-back attributes, and report data rules are unchanged.
- Simplified Chinese and English status text are both supported.

## v4.1.31

- SSH remote G-file refresh now performs connection/SFTP directory listing in a background QThread so slow `listdir_attr` operations no longer freeze the Qt GUI.
- Refresh status now reports elapsed wait time while the remote read is running; the refresh button is temporarily disabled to prevent duplicate refresh jobs.
- Remote file selection/filtering, read-only SSH behavior, RMU/feeder validation, Oracle logic, KeyID calculation and G-file write-back rules are unchanged.
- Chinese and English refresh status text are both supported.

- Optimized G-file bulk write-back by indexing requested `(tag, XML ID)` targets once instead of rescanning the complete G file for every selected object.
- Added live batch write-back progress logs for large RMU/feeder associations.
- No RMU/feeder validation, Oracle matching, KeyID calculation, association decision, or write-back attribute rules were changed.

## v4.1.29

- Model Association now repaints the console and progress message continuously during synchronous execution.
- RMU execution logs the current RMU, safe-copy stage, and G-file write-back stage in real time.
- Feeder execution logs the current feeder region, safe-copy stage, and G-file write-back stage in real time.
- Presentation/progress only: no RMU, feeder, Oracle, KeyID, validation, allocation, or write-back decision logic changed.
- Chinese and English runtime messages are both supported.

# v4.1.28

- Added an independent status-color filter to every searchable HTML report table.
- Existing fuzzy text filtering is unchanged; text and color filters can now be combined.
- Color choices are localized in Simplified Chinese and English.
- No RMU, feeder, Oracle, SSH, XML parsing, validation, association, or write-back business logic was changed.

# v4.1.27

- Added configurable RMU name exclusion strings in RMU Recognition. Default exclusions: `N.O.P`, `NOP`, `N-O-P`, `N_O_P`, `SFI`, `DAS/OK`. Matching is exact (case-insensitive after whitespace normalization), not substring-based.
- The exclusion list is saved with workspace settings and is applied consistently to RMU name recognition, including feeder-side RMU anchor analysis.
- Fixed large-font RMU labels whose XML Text bounding box overlaps the RMU frame edge even though the text center is clearly on the selected side. Normal labels keep the previous edge-gap scoring; center-gap is used only as an overlap fallback.
- Verified the supplied `JED-CTL-BABJ.sln.pic.g`: RMU frame XML ID `2001193` now owns label `38995` (Text XML ID `8001222`) from the Top direction.
- Added Chinese/English UI strings for the new exclusion setting.
- No database association, KeyID, devref, feeder, SSH, or write-back rules were changed.

# v4.1.26

- English-mode Console, progress messages, validation diagnostics, feeder/RMU runtime messages, SSH snapshot messages, and strict XML diagnostics are now translated at the presentation layer.
- No business logic changed: RMU/feeder recognition, Oracle queries/writes, SSH behavior, validation rules, association rules, KeyID calculation, report data, and G-file write-back remain identical to v4.1.25.
- Engineering/status codes and raw engineering values remain untranslated.
- Added regression coverage that fails if user-visible Console log literals still contain Chinese after English translation.

# v4.1.25

- English release hardening: English mode removes the remaining Chinese presentation text reported in the header edition label, Run History, Settings/Safety Policy, About information and current-model help.
- `QApplication` application/display name now follows the selected UI language so the Windows title bar does not append the Chinese product name in English mode.
- Dynamic artifact buttons and selected feeder facID notices now follow the current language after an immediate language switch.
- English CSV export localizes user-facing reason/action/status-description fields while preserving engineering codes, IDs, XML values and database data.
- RMU name recognition adds a deliberately narrow field naming pattern for `number + space + suffix`, e.g. `66 B` / `123 C2`. Arbitrary descriptive labels with internal spaces remain rejected.
- Real-file verification: `JED-CTL-AMR.sln.pic.g`, RMU frame XML ID `2000597`, uniquely receives the top label `66 B`; compared with v4.1.24, no other RMU name candidate changes.
- Full regression: 194 passed, 1 skipped.

# v4.1.24

- 修复 SSH 远程 G 文件列表在点击“清空选择和搜索 / Clear Selection & Search”时的 UI 卡顿/Windows“未响应”问题。
- 根因：v4.1.23 清空搜索后会在 GUI 主线程重新创建全部远程文件表格行；当目录包含 2000+ 个 G 文件时会同步创建数千个 QTableWidgetItem。
- 远程文件表改为“刷新目录时创建一次，搜索时只隐藏/显示已有行”；清空按钮不再重建表格。
- 批量清空/全选时暂停表格 signals 和 repaint，完成后一次刷新，避免每个 checkbox 单独触发 UI 更新。
- 搜索输入增加 120 ms debounce，快速输入时不再每个字符立即遍历/刷新远程列表。
- “全选当前结果 / Select Visible Results”仍严格只作用于当前可见搜索结果；“清空选择和搜索 / Clear Selection & Search”中英文行为保持一致。
- SSH 远程目录仍只读，本次性能优化不会增加任何服务器访问或写操作。

# v4.1.23

- SSH 远程 G 文件列表删除“取消当前结果 / Unselect Visible Results”按钮，避免与全局清空操作重复。
- 原“清空全部选择”升级为“清空选择和搜索 / Clear Selection & Search”：一次清空全部远程文件勾选状态、清空搜索关键字，并恢复完整文件列表。
- “全选当前结果 / Select Visible Results”仍只勾选当前筛选可见结果。
- 新增操作及输入变化提示同步支持中文/英文即时切换。
- 保留 v4.1.22 全部 i18n、RMU、馈线、SSH 只读、严格 XML 校验与安全回写逻辑。

# v4.1.22

- 新增统一 i18n 国际化层，应用支持 `简体中文 / English` 两种语言并可在设置页面即时切换。
- 语言选择保存到 Workspace 配置中的 `language` 字段，程序下次启动自动恢复最后一次选择。
- 主导航、数据库/SSH 配置、模型工作区、RMU/馈线设置、常用提示与用户可见运行日志接入统一翻译。
- RMU/馈线 HTML 报告支持中英文标题、表头、状态说明和筛选控件；CSV 报告支持中英文表头及英文文件名。
- `PASS / FAIL / RELINK / CREATE_PENDING`、错误码、XML/G 图元类型、KeyID/FEEDER_ID/BV_ID/Domain 及数据库工程数据保持原值，不随 UI 语言翻译。
- 保留 v4.1.21 的 RMU devref 模板结构识别、N.O.P 过滤和严格 XML 编码校验逻辑。

# v4.1.21

- RMU `devref` 柜型识别改为现场无关的模板结构判断，不再依赖 `Load_Breaker`、`Circuit_Breaker`、`RMU_LBS`、`RMU_BRK` 等任何固定名称。
- `devref` 柜型统计严格只分析 RMU 矩形框内的 `CBreakerDis`；`ZhaiWaiJieDiDaoZha`（例如 `RMU_ES`）、`BusDis` 及其它图元完全不参与 2L1T/3L1T 判断。
- Y 类 `CBreakerDis` 必须使用同一个 devref 模板，Q 类必须使用同一个 devref 模板；同时存在 Y/Q 时，两组模板必须不同，才能形成有效 devref 类型。
- devref 名称只做规范化后相等性比较，不解释名称含义；支持吉达、麦加以及未来其它现场自定义图元库名称。
- 同类模板混用、devref 缺失、Y/Q 使用相同模板或元素无法归入 Y/Q 时，`devref类型=UNKNOWN` 并输出 WARN，不根据关键字猜测类型；如图内 Y/Q 文字有效，则仅用文字类型作为最终显示类型。
- 保留既有规则：当有效 devref 类型与图内文字类型都存在但不一致时，最终采用有效 devref 类型，同时保留交叉校验 WARN。
- 真实文件回归：麦加样例 149 个 RMU（143×2L1T、6×3L1T）devref 结构全部通过；吉达 ADF-16 样例 5 个 RMU（3×2L1T、2×3L1T）全部通过；`RMU_ES` 进入柜型统计数量为 0。

# v4.1.20

- 保留 RMU 名称候选过滤 N.O.P/NOP 等 Normally Open Point 状态标识。
- 撤销异常 G 文件的 UTF-8 -> GB18030 自动回退，不再猜测、转换或修复源文件编码。
- XML 解析失败时输出详细诊断：文件名、声明编码、错误行列、原始字节、文本预览和处理建议。
- 回写恢复标准 UTF-8 处理，异常编码文件必须先修复源 G 文件。

# v4.1.19

- RMU 名称候选过滤 N.O.P/NOP 等 Normally Open Point 状态标识。
- 曾加入异常编码兼容逻辑；该逻辑已于 v4.1.20 撤销。

# v4.1.18

- SSH 只读文件源新增“保存 SSH 配置”按钮，支持保存用户自定义的 IP/主机、端口、用户名、密码和远程目录。
- 保存后的 SSH 配置与 Oracle 数据库配置一样持久化到 Workspace 配置文件，下次启动自动恢复最后一次保存值。
- SSH 配置读取改为与默认配置深度合并，后续新增 SSH 配置字段时旧配置不会覆盖掉新默认项。
- 保存前增加 SSH 主机、端口、用户名和远程目录基础校验；保存配置不发起网络连接，也不会修改远程服务器。

# v4.1.17

- RMU 名称未解析/解析异常时继续检查柜内已有设备 KeyID，不再因 `rmu_name` 为空直接把正确设备误报为 `RMU_LINK_MISMATCH`。
- 已有关联设备通过 KeyID 反查 `combined_id`；若均来自同一个数据库 RMU，则记录推断出的 RMU ID/NAME，并在 RMU 汇总说明及 RMU 级阻断原因中明确说明“名称未解析但现有 RMU 归属关联一致”。
- 当柜内所有设备均已有可反查 KeyID 且归属同一个 RMU 时，说明明确标记现有 RMU 归属关联一致且正确、无需重新关联，并提示核对图上名称是否应为该数据库 RMU NAME。
- 名称未解析的设备行如果现有 KeyID、CODE 和实际 RMU 归属检查均通过，保持 PASS / 无需回写；`当前模型环网柜名称是否正确` 显示 `N/A`，避免把“无名称可比较”误解释成错误。
- 同一图形 RMU 内已有设备指向多个 combined_id 时仍保持红色硬错误；名称未解析时仍禁止自动新增或改绑。
- 新增 3 个专项回归测试覆盖：名称未解析但单一 RMU 关联正确、报告反推 ID/NAME、跨多个 RMU 仍硬错误。

# v4.1.16

- RMU 名称未解析时明确输出 `RMU_NAME_NOT_PARSED`，环网柜汇总使用红色 FAIL。
- RMU 名称候选解析/核验发生异常时转换为 `RMU_NAME_RESOLUTION_ERROR` 红色 FAIL，不再因异常直接丢失该 RMU 报告记录。
- `RMU级关联阻断原因` 改为按实际失败原因输出：名称未解析、名称解析/核验异常、数据库无记录、数据库重名分别描述。
- 名称身份未可靠确定时禁止该 RMU 及柜内设备自动关联。
- 报告层保留名称解析失败原始原因，不再错误降级为 `RMU_NOT_FOUND_IN_DATABASE`。
- 新增 RMU 名称未解析与解析异常的报告/颜色/阻断原因回归测试。

# v4.1.15

- 馈线 HTML 报告新增独立的橙色 `CREATE` 状态，用于明确区分“已有数据库馈线段直接关联”和“需要先新建 13503 再关联”的 FeedLine。
- `severity=CREATE_PENDING` 的馈线段明细行现在使用浅橙色背景，不再与普通黄色 WARN 混在一起。
- 状态颜色说明新增“橙色 CREATE”：数据库可用 13503 数量不足时，该 FeedLine 需要先创建新的 `dms_section_device`，再生成正确 KeyID 并回写关联。
- 黄色 WARN 继续仅表示已找到本馈线下现有可用数据库馈线段，可直接关联；红色 FAIL 不再把“数据库馈线段数量不足但可安全新建”描述为硬错误。
- 新增 HTML 报告回归测试，验证 CREATE_PENDING 行、图例与 CSS 颜色均正确输出。

# v4.1.14

- 调整部分已关联馈线图的剩余 FeedLine 分配策略：不再要求 1 对 1 唯一剩余，也不再因多个未关联项 + 多个候选段而 BLOCKED。
- 已正确关联的 FeedLine 仍严格保留，只校验同 FEEDER_ID 与 Domain；不检查 SEC/图形顺序。
- 未关联或旧 KeyID 失效的 FeedLine 依次使用本馈线未占用 13503：NAME 含 SECnnn 时按 SEC 数字升序，否则按数据库 device ID 升序。
- 数据库现有段不足时，先分配全部可用段，再仅对真实短缺行生成 `SECTION_NOT_AVAILABLE` / `CREATE_PENDING`，新建数量等于实际短缺数量。
- 部分已关联图新建 NAME 继续使用第一个未占用的 `*_SECnnn`，不会依据已有 FeedLine 的几何位置重排历史模型。
- 新增/更新回归测试覆盖：4 已关联 + 2 未关联、非 SEC 历史名称按 ID 顺序、现有段不足后仅创建短缺数量。

# v4.1.13

- 馈线段既有模型校验进一步收敛：只检查当前 KeyID 是否能解析到 13503、数据库记录是否属于当前已确认 FEEDER_ID，以及 Domain 是否正确。
- 取消既有/部分已关联模型的 SEC001/SEC002 几何顺序校验；数据库 NAME、CODE、SEC 后缀、上下/左右顺序均不再作为既有关联正确性的判据。
- 只有“全新图”（本图所有 FeedLine 均无 KeyID）允许使用从上到下、同高度从左到右的图形顺序进行首次馈线段分配，并在数据库数量不足时按该顺序创建缺少的 SEC。
- 只要图中存在任何已关联 FeedLine，即进入 `PRESERVE_EXISTING_NO_ORDER` 模式；多个未关联项与多个候选馈线段并存时不再按顺序猜测，改为 BLOCKED。
- 非全新图仅剩 1 个未解析 FeedLine + 1 个未占用同馈线 13503 时，可按唯一剩余事实直接关联，不依赖顺序。
- 非全新图仅剩 1 个未解析 FeedLine且数据库无剩余 13503 时，允许只创建 1 条；新 NAME 使用当前馈线第一个未使用的 SEC 后缀，不使用该 FeedLine 的几何序号。
- 同一馈线、正确 Domain 的既有关联直接 PASS；按当前业务规则不再额外检查同一 13503 是否被多个 FeedLine 重复引用。
- 新增 5 个专项回归测试覆盖：全新图按序首次关联、部分图多候选禁止按序、唯一剩余安全关联、重复同馈线/同 Domain 不额外报错、单条短缺创建不使用几何序号。

# v4.1.12

- 修复“已正确关联的同馈线 FeedLine 因几何顺序与 SECnnn 顺序不同而被误报 RELINK”的问题。
- 已有关联只要 KeyID 解析到 13503、Domain 正确、数据库记录仍属于当前已确认 FEEDER_ID，即直接 PASS；不再按图形从上到下/从左到右强制重排 SEC。
- Domain-only 错误仍保持同一 device_id，仅重写正确 Domain 的 KeyID。
- 未关联或旧 KeyID 失效的 FeedLine，继续优先分配当前馈线未占用的现有 13503；只有真实数量不足时才按短缺数量创建。
- SECnnn 规则仅用于新建缺失馈线段的 NAME；若首选 SECnnn 已被现有正确关联占用，则自动选择当前馈线下第一个未使用的 SEC 序号，避免重复创建/抢占。
- 新增 ADF-15 真实排列场景回归：SEC001、SEC004、SEC002、SEC005、SEC003、SEC006 均保持原正确关联，不产生无意义 RELINK。

# v4.1.11

- 修复馈线 G 中旧 KeyID 指向已不存在 13503 记录时无法继续分配的问题。
- 失效旧关联先使用当前已确认 FEEDER_ID 下未占用的现有馈线段。
- 现有馈线段仍不足时，仅按实际短缺 FeedLine 数量生成 CREATE_PENDING 计划。
- 执行阶段仅创建用户选中的短缺馈线段，创建后重新查询数据库并计算 KeyID。
- 非创建行按验证阶段已选定的 device_id 精确执行，兼容历史拓扑式馈线段 NAME。

# v4.1.10

- 馈线 HTML 报告的“馈线汇总”和“馈线段明细”新增独立模糊搜索框，支持按馈线名、馈线段名、状态、ID 或其它可见字符整行筛选。
- 修复同一 13503 馈线段仅 Domain 编码错误时被报为不可处理 `MODEL_LINK_WRONG` 的问题。
- 当当前 KeyID 指向 13503、本数据库记录仍属于当前 FEEDER_ID、但 Domain 不等于配置值（默认 1）时，标记为 `RELINK` 并允许重写 KeyID。
- Domain-only RELINK 保持原 device_id / 馈线段不变，只重算并回写正确 KeyID；执行阶段禁止重新分配到其它 SEC。
- 不同 feeder_id、错误 table、数据库记录缺失等场景仍保持硬错误，不放宽跨馈线安全边界。
- 增加 Domain-only RELINK 与馈线 HTML 双搜索框专项回归测试。

# v4.1.9

- 馈线图 AUTO 分型改为 CBreaker 优先：严格统计 `<CBreaker>`，1 个判定单馈线图，2 个及以上判定多馈线组合图。
- `<CBreakerDis>` 仅表示 RMU/馈线内部开关，不参与源馈线数量统计。
- 仅当 `<CBreaker>` 为 0 时，才启用有效母线、源分支、FeedLine 连通域和馈线标题锚点的拓扑兜底。
- 增加分型置信度与 CBreaker 数量日志；保留 AUTO / 强制单馈线 / 强制组合图人工覆盖。
- 加入 TEST88、AJWD-03、ABH-03、ABH 组合图真实文件回归。

## [4.1.8] - 2026-08-19

- 馈线配置新增“图纸类型确认”：AUTO / 强制单馈线图 / 强制组合图；选择对本次文件或目录中的文件生效。
- AUTO 继续使用 v4.1.2+ 的 G 电气拓扑分型；人工覆盖时日志与报告同时保留自动识别结果和最终分型判据。
- 单馈线根 facID 关联与 Breaker、Busbar、FeedLine/13503 校验解耦：人工输入/文件名唯一确认 13500 馈线后，可独立勾选并回写 G 根 facID。
- 即使 FeedLine/section 区域校验被阻断，已验证的单馈线根关联仍可单独执行；不会因此修改或创建其它设备模型。
- 组合图继续禁止将整张 G 根节点绑定到单一 FEEDER_ID。
- 馈线报告新增图纸类型设置、自动拓扑识别和最终分型判据列。

## [4.1.7] - 2026-08-19

- 馈线模型允许“零 FeedLine 的馈线图”：先完成 13500 馈线唯一解析，再判断是否存在馈线段；FeedLine=0 不再导致整条馈线 FAIL。
- 人工输入/文件名唯一确定馈线且 G 根 facID 为空时，新增“馈线根 facID”可选关联项；执行只回写 `<G facID>`，不会创建任何 13503 馈线段。
- 馈线汇总在零 FeedLine 场景也正确显示 13500 匹配数、FEEDER_ID、数据库馈线名和所属变电站。
- 明确变电站名称使用 405/substation.NAME（例如 `AJWD`）；`JED CTL` 属于区域信息，不参与馈线段前缀。
- 馈线段原 `AJWD_43_SEC001` 命名规则、拓扑图纸分型和跨馈线保护保持不变。

## [4.1.6] - 2026-08-19

### Fixed
- 修复馈线段旧命名规则在完整站名场景下的前缀错误：`JED CTL AJWD + 43` 不再错误生成 `JED_CTL_AJWD_43_SEC001`，而是匹配数据库实际的 `AJWD_43_SEC001`。
- 馈线段前缀优先从当前 `FEEDER_ID` 下已有 `dms_section_device.NAME` 的唯一 `*_SECnnn` 前缀推断；无既有馈线段时，再使用站名最后业务代码 + 馈线名生成。
- 避免数据库已存在馈线段却被误判为缺失并生成错误 CREATE 计划。

## [4.1.5] - 2026-08-19
- 修复馈线模型在目标 SECnnn 已存在于数据库时调用不存在的 `OracleClient.make_expected_keyid()` 导致模型校验崩溃的问题。
- 馈线段期望 KeyID 改为使用项目统一的 D5000 编码规则：`DeviceID + (Domain << 32)`。
- 修正回归测试：Fake DB 不再伪造真实 OracleClient 不存在的方法，并新增真实接口形状的专项测试，避免同类问题再次漏测。
- 保留 v4.1.4 的 RMU 报告筛选、DEVREF 柜型优先规则，以及 v4.1.3/v4.1.2 的 SEC 命名、跨馈线保护和拓扑分型逻辑。

## [4.1.4] - 2026-08-19
- 修复 `build_exe.ps1` 仍硬编码 v4.1.3 的问题；打包名称现在自动从 `APP_VERSION` 派生，避免版本升级后 EXE/ZIP 名称滞后。

### RMU report filtering and field-rule update

- Added independent fuzzy-search inputs above both RMU HTML report tables: `环网柜汇总` and `设备明细`. Search is case-insensitive and matches any visible row text, including RMU names.
- Changed RMU type conflict rule: when Y/Q text-derived type and `CBreakerDis.devref` type disagree, the final RMU type now follows `devref`; the mismatch still remains WARN for review.
- Changed the report-facing `是否智能` value from `YES/NO` to `SMART/NORMAL`. Internal smart-marker detection and the existing `智能标识` column remain unchanged.

## [4.1.3] - 2026-08-19

### Restore original feeder-section naming + hard feeder ownership guard
- Keep v4.1.2 topology-first classification for SINGLE_FEEDER vs MULTI_FEEDER_COMPOSITE.
- Revert the v4.1.1 topology endpoint naming rule for FeedLine sections.
- Feeder-section targets again use the original resolved-feeder prefix plus positional SEC number: `..._SEC001`, `..._SEC002`, etc.
- G `link` / `node_area` topology no longer determines section NAME or association target.
- Existing `ls>2 -> 2` normalization remains unchanged.
- During validation, an already-linked FeedLine whose 13503 row belongs to a different `feeder_id` is a hard `FEEDER_MISMATCH`.
- Cross-feeder mismatches are never silently converted into automatic RELINK operations.
- Same-feeder exact SEC-order mismatches can still follow the original explicit RELINK behavior.
- Composite drawings remain audit-only and retain their feeder-owner consistency checks.

## [4.1.2] - 2026-08-18

### Topology-first drawing classification
- Fixed false composite detection caused by counting every XML `Bus` object.
- Tiny Bus point-nodes (for example 6x6 junction objects) no longer count as physical busbars.
- Drawing type now uses effective busbars plus independent source branches after removing the busbar backbone from the explicit G link graph.
- Two or more independent bus-to-breaker-to-FeedLine branches are a strong composite signal.
- Distinct feeder-title anchors near effective busbars remain a second independent composite signal for sparse overview drawings.
- Multiple raw Bus objects alone never force `MULTI_FEEDER_COMPOSITE`.
- Validation logs now expose raw Bus count, effective busbars, feeder source branches, title anchors, and the classification reason.

## [4.1.1] - 2026-08-18

### Topology-based feeder section creation
- FeedLine section NAME is derived from real G `link` / `node_area` topology,
  not from SEC001/SEC002 order.
- Endpoint order is top-to-bottom, then left-to-right.
- Supported examples include `B303_22545-Y1`,
  `22545-Y3_22521-Y2`, and `8664-Y1_22520`.
- Remote RMU ports are never guessed when the G file exposes only the cabinet
  number.
- Existing topology-named 13503 rows become exact targets; wrong same-feeder
  links can be RELINK candidates.
- `ls=1` -> SECTION_TYPE=1, `ls=2` -> 0, empty -> 3.
- Any numeric `ls>2` is treated as 2 before validation/database creation and
  every such FeedLine is rewritten to `ls="2"` in the local g_output safe copy.
- SSH server and local original G files remain unchanged.
- Added `下载所选 G 文件` to the SSH read-only browser; each file is re-statted
  immediately before download.

## [4.1.0] - 2026-08-18

### Single-feeder vs composite feeder audit
- Added structural drawing classification using Bus count:
  SINGLE_FEEDER / MULTI_FEEDER_COMPOSITE / AMBIGUOUS.
- Local directory mode requires non-empty root facID for every single-feeder
  drawing; filename/manual feeder lookup is not used for directory singles.
- Composite drawings ignore root facID completely.
- Directory single-feeder drawings build trusted FeedLine XML-ID fingerprints.
- Composite regions with 100% fingerprint match receive an authoritative
  Expected FEEDER_ID from the matching single-feeder facID.
- Remaining composite FeedLines are grouped by FeedLine/ConnectLine topology
  components and audited for current FEEDER_ID consistency.
- Exact-fingerprint wrong-feeder rows are reported as FEEDER_MISMATCH; topology
  minority-owner rows are reported as TOPOLOGY_FEEDER_CONFLICT.
- Composite/ambiguous drawings are audit-only in this release and are never
  automatically rewritten.
- Existing single-feeder 13503 creation, 401/402 BV_ID selection, facID policy,
  SSH read-only snapshots and FeedLine writeback remain unchanged.

## [4.0.9] - 2026-08-17

### Hard facID lock and empty-facID writeback
- Fixed local single-G facID detection regex.
- Non-empty G.facID is now reflected as a hard UI lock after validation,
  including SSH snapshot validation.
- Attempts to choose filename/manual while facID is locked show an explicit
  warning and immediately return to FACID.
- When original G.facID is empty and FILENAME/MANUAL uniquely identifies the
  feeder, successful association writes the final FEEDER_ID into root G.facID
  in the Workspace/g_output safe copy.
- Existing non-empty facID is never overwritten.
- FeedLine five-field writeback, 401/402 BV_ID selection, 13503 INSERT boundary,
  transactions and SSH read-only behavior remain unchanged.

## [4.0.8] - 2026-08-17

### facID authority + precise fallback matching
- Non-empty G root facID is always authoritative (`FACID_FORCED`).
- Filename/manual selections are ignored whenever facID is populated.
- Invalid or unresolved non-empty facID blocks processing; no fallback occurs.
- Only an empty facID enables filename or manual feeder identification.
- Filename/manual matching preserves numeric text exactly:
  `AJWD 6` and `AJWD 06` are different feeders.
- Local single-file loading locks the feeder selection UI to facID when a
  populated facID is detected.
- Existing 401/402 BV_ID selection, 13503 creation, ID allocation,
  transaction safety, SSH read-only behavior, and G write-back remain unchanged.

## [4.0.7] - 2026-08-17

### Independent feeder identification modes
- Removed feeder AUTO mode.
- Default feeder identification is FACID.
- FACID, FILENAME and MANUAL are fully independent:
  selecting one mode uses only that source.
- No fallback or cross-check is performed against the other two sources.
- The selected source must independently resolve to one unique 13500 /
  dms_feeder_device record, otherwise processing is blocked.
- Existing 401/402 BV_ID selection, 13503 creation, ID allocation, transaction,
  SSH read-only behavior, FeedLine association and five-field G write-back
  remain unchanged.

## [4.0.6] - 2026-08-17

### Feeder name canonicalization
- Fixed false `FEEDER_NAME_FACID_MISMATCH` when the database feeder name uses
  an unpadded numeric suffix and the G filename uses a zero-padded suffix.
- Numeric feeder-name tokens now ignore leading zeros during comparison:
  `AJWD 6 == AJWD 06 == AJWD-006`.
- The canonicalization is used consistently for facID/file/manual cross-checks.
- True feeder-number mismatches such as `AJWD 6` vs `AJWD 16` still block.
- No database creation, ID allocation, voltage-level BV_ID selection, SSH,
  FeedLine association, or G write-back behavior changed.

## [4.0.5] - 2026-08-17

### Feeder section BV_ID from voltage level
- New 13503 feeder-section rows no longer use `substation.BV_ID`.
- Resolve station from `dms_feeder_device.ST_ID`.
- Query 402 `voltagelevel`, join 401 `basevoltage` by BV_ID.
- Only 110kV, 33kV and 13.8kV are eligible; if multiple exist, use the
  numerically smallest one and its `voltagelevel.BV_ID`.
- AJWD with 110kV + 13.8kV therefore uses 13.8kV BV_ID
  `112871465660973067`.
- Existing ID allocation, SECTION_TYPE, transaction and G write-back logic
  remain unchanged.

## [4.0.4] - 2026-08-17

### Feeder report aligned with direct feeder identification
- Removed obsolete RMU/topology feeder-identification columns from feeder HTML
  and feeder CSV reports.
- Removed trusted/ignored RMU counts, RMU FEEDER_ID evidence, topology region
  fields, and old topology explanatory text from feeder reporting.
- Feeder summary now focuses on:
  - identification source: FACID / FILENAME / MANUAL
  - identification evidence
  - unique 13500 match
  - feeder ID/name
  - station name/BV_ID from 405
  - section name prefix
  - existing/required 13503 section counts
  - FeedLine association results
- FeedLine detail no longer exports topology component / cross-region fields.
- Added `ls`, planned `SECTION_TYPE`, and database-create-needed information to
  FeedLine detail for the new feeder-section creation workflow.
- No feeder database creation, ID allocation, association, SSH, RMU model, or
  five-field G write-back logic changed.

## [4.0.3] - 2026-08-17

### Feeder wording cleanup
- Removed all remaining feeder UI/help wording that suggested RMU, ring-main-unit
  topology, connection topology, or FEEDER_ID could be used to determine a feeder.
- Feeder identification is now documented consistently as exactly three sources:
  1. G root facID
  2. filename
  3. manual input
- All three sources must ultimately resolve to one unique 13500 /
  dms_feeder_device record; otherwise the feeder file is blocked.
- No database creation, ID allocation, FeedLine association, SSH, RMU-model,
  or G write-back business logic changed.

## [4.0.2] - 2026-08-17

### Feeder resolution UX
- Disabled mouse-wheel changes on the feeder resolution strategy combo box.
- Clicking the combo box and keyboard selection still work normally.
- No feeder, database, SSH, creation, association or G write-back logic changed.

## [4.0.1] - 2026-08-17

### Feeder ownership simplified
- Removed RMU topology as a feeder-identification source.
- Removed the obsolete `RMU 拓扑自动识别` feeder UI.
- A feeder must now be confirmed only from:
  1. G root `facID` -> exact 13500 / `dms_feeder_device.ID`
  2. filename engineering-name match
  3. manual feeder-name match
- AUTO order is `facID -> filename -> manual input`.
- Filename/manual matching requires one unique normalized full/suffix engineering
  name match. If explicit manual text conflicts with facID/filename, creation
  and association are blocked.

### Database write boundary
- 13500 / `dms_feeder_device`: read only.
- 405 / `substation`: read only.
- 13503 / `dms_section_device`: the only table that can be written, and only
  through INSERT of genuinely missing feeder sections.
- No UPDATE or DELETE SQL exists in the application database layer.
- Every newly allocated ID is checked with `COUNT(*) WHERE id=:id` before
  INSERT, while the 13503 table remains locked for the allocation transaction.

### Exact section preparation
- Each G FeedLine order maps to its exact target SEC name
  (`..._SEC001`, `..._SEC002`, ...).
- A different existing section such as SEC010 does not satisfy a missing SEC002.
- Selected missing target sections are created first, then 13503 is re-queried,
  then the existing FeedLine link/relink logic runs.
- G write-back remains limited to:
  `app`, `p_ReportType`, `state`, `voltype`, `keyid`.

## [4.0.0] - 2026-08-16

### FeedLine database preparation + automatic association
- Added feeder resolution sources:
  - G root `facID` exact lookup (preferred)
  - manual feeder text
  - G filename such as `JED-CTL-ADF-16.sln.pic.g`
  - existing RMU topology fallback for composite/ambiguous drawings
- Feeder context resolves `dms_feeder_device.ST_ID -> substation` and uses
  `substation.NAME + "_" + feeder.NAME` as the section prefix, e.g. `ADF_16`.

### Missing DMS_SECTION_DEVICE creation
- Model validation remains read-only and produces CREATE_PENDING candidates.
- During explicit `执行模型关联`, when enabled, only actually missing
  `DMS_SECTION_DEVICE` rows are INSERTed.
- Existing rows are never recreated, UPDATEd or DELETEd.
- `FeedLine.ls` maps to `SECTION_TYPE`:
  - `ls="2"` -> `0`
  - `ls="1"` -> `1`
  - empty/missing `ls` -> `3`
  - unknown values are blocked from automatic creation.
- New section names follow the G FeedLine order:
  `STATION_FEEDER_SEC001`, `SEC002`, ...

### D5000 ID allocation
- New section IDs follow the confirmed D5000 pattern:
  `KEYID_TO_LONG3(13503, 0, 0, code_id)`.
- The transaction locks `DMS_SECTION_DEVICE`, derives the area-0 legal range,
  compares the current table MAX(id) with `deleted_record` MAX(id), then
  allocates sequential IDs above the larger value.
- A feeder creation batch is atomic: any error causes ROLLBACK.
- After COMMIT the database is queried again before Expected KeyID calculation.

### G write-back boundary
FeedLine association writes only these five attributes:
- `app="6500000"`
- `p_ReportType="1"`
- `state="20"`
- `voltype="dms_section_device.BV_ID"`
- `keyid="Expected KeyID"`

No `key_name`, `ls`, geometry, line style, color or other G attributes are
changed by FeedLine association.

### Existing behavior preserved
- Existing correct links remain unchanged.
- UNLINKED / RELINK / DUPLICATE_LINK allocation logic remains in place.
- SSH is still strictly read-only and server files are never written.
- Association still modifies only Workspace `g_output` copies.

## [3.9.3] - 2026-08-16

### SSH connection status UX
- Moved SSH/SFTP connection status directly below the SSH action buttons.
- Connection success/failure and remote-list loading results are now shown
  in the SSH configuration area where the user can see them immediately.
- No SSH read-only, latest-file snapshot, RMU, feeder, database, KeyID/BV_ID
  or write-back logic changed.

## [3.9.2] - 2026-08-16

### SSH source explicitly shared by RMU and feeder
- The LOCAL / SSH input source is now explicitly treated as a Model Workspace
  common capability shared by both RMU and FEEDER modules.
- FEEDER model can use the same SSH read-only browser, search, multi-select and
  latest-file snapshot download as RMU.
- Switching between RMU and FEEDER preserves the source selector and refreshes
  the source panel geometry rather than rebuilding/hiding it.
- Both model types follow the same hard rules:
  every validation re-downloads the latest stable selected server files;
  association uses only that validation snapshot and never re-downloads or
  writes to the server.
- No RMU/FEEDER validation, topology, database, KeyID/BV_ID or write-back
  business rules changed.

## [3.9.1] - 2026-08-16

### Input source layout fix
- Fixed the large blank area shown when `本地文件 / 目录` is selected.
- Local source mode is restored to the compact single-row layout used before SSH support.
- SSH source mode still expands to show connection fields, search and the remote G-file table.
- Switching between LOCAL and SSH now recalculates the source panel height for the current page only.
- No SSH freshness, read-only, snapshot, RMU, feeder, database, KeyID, BV_ID or write-back business logic changed.

## [3.9.0] - 2026-08-16

### Local + SSH dual G-file source
- Model Workspace now supports two input sources:
  - Local file / directory
  - SSH file server (strict read-only)
- Default SSH field configuration:
  - host `172.16.21.27`
  - port `22`
  - user `up8000`
  - remote directory `/home/up8000/data/graph/display/sln`
- Remote browser supports refresh, local instant search, multi-select,
  select current search results, cancel current results and clear selection.
- Remote listing accepts only filenames ending exactly in `.g`; `.g.h`,
  `.g.data` and `.g.png` are excluded.

### Server read-only hard boundary
- Added a dedicated `ReadOnlySshClient`.
- The SSH infrastructure exposes only:
  `test_connection`, `list_g_files`, `stat_file`, `download_file`, `close`.
- No upload / put / remove / delete / rename / mkdir / remote-write API is
  implemented.
- Association never writes to or uploads to the SSH server.

### Always-latest validation rule
- Every new `模型校验` in SSH mode downloads every currently selected G file
  again from the server.
- Previous `remote_input`, cached file content or an earlier run is never
  reused as a new validation input.
- File-list caching is only for browsing/search and never determines the
  validation file content.

### Stable remote snapshot
- Each selected file uses:
  `stat before -> download -> stat after`.
- Size and remote mtime must be unchanged and the downloaded byte count must
  match the final remote size.
- If the server file changes during download, the partial local file is
  discarded and the latest version is retried up to 3 times.
- A stable download is stored under the current run's `remote_input/`.
- SHA256, remote size, remote mtime and download time are recorded in
  `run_manifest.json`.

### Validation/association consistency
- After validation starts, the downloaded `remote_input` files are the fixed
  snapshot for that validation.
- `执行模型关联` never re-downloads from SSH.
- Association uses the exact validation snapshot, copies it to `g_output`,
  and modifies only the local Workspace copy.
- Therefore the product guarantees:
  `the version validated is the version associated`.
- To use a newer server version, the user must run `模型校验` again.

### Packaging
- Added `paramiko>=3.4`.
- EXE build verification and PyInstaller collection include Paramiko,
  bcrypt and PyNaCl.

### Scope
- RMU / feeder recognition, database matching, logical CODE, cabinet type,
  SMART/SMR, Expected KeyID, BV_ID and write-back business rules are unchanged.

## [3.8.0] - 2026-08-15

### Formal internal delivery workflow
- Added a dedicated `运行历史` page.
- Every validation/association run writes `run_manifest.json`.
- Run history can open the run directory, HTML report and association change log.

### Association audit trail
- Every successful association run generates `model_change_log.csv`.
- The change log records source/output G file, tag, XML ID, attribute,
  value before write-back and value after write-back.
- Added `打开修改记录 CSV` result button.

### Safer execution UX
- Final association confirmation now shows selected object count,
  affected G-file count and selected candidate status breakdown.
- Completion dialog now includes selected/success/skipped counts and
  direct actions to open the result directory or HTML report.

### About / delivery information
- Help page now includes application name, version, build date,
  edition and data-safety statement.
- Added `release_check.ps1` and `RELEASE_CHECKLIST.md`.

### Scope
- RMU/feeder recognition, database matching, logical CODE, type recognition,
  SMART/SMR, Expected KeyID, BV_ID, model selection and write-back business
  rules are unchanged.

## [3.7.1] - 2026-08-15

### RMU report cleanup
- Removed the `状态类型` column from RMU HTML summary and
  `环网柜汇总.csv`.
- `状态` and `说明` remain.
- Internal severity/status classification is still retained for business
  logic and row coloring; only the duplicated report column was removed.
- No validation, candidate, association, database, feeder, KeyID/BV_ID,
  SMART/SMR, or write-back logic was changed.

## [3.7.0] - 2026-08-15

### Baseline
- This version is rebuilt directly from the original v3.6.9 source package.

### Unified RMU report
- Removed the separate `环网柜档案.csv`.
- Merged its RMU-level fields into `环网柜汇总.csv`.
- HTML `环网柜汇总` uses the same unified RMU fields.
- Removed the `打开环网柜档案 CSV` button and `rmu_profile_csv` artifact.

### Unchanged from v3.6.9
- Simplified workflow remains:
  `模型校验 -> 勾选候选 -> 执行模型关联`.
- No separate association-preview button was reintroduced.
- RMU/feeder recognition, candidate generation, selected-only execution,
  database recheck, KeyID/BV_ID write-back, SMART/SMR, logical CODE,
  and all other validation/association logic are unchanged.

## [3.6.9] - 2026-08-15

### Simplified model-association workflow
- Removed the user-facing `模型关联预览` button.
- The workspace now exposes only:
  `模型校验` -> select validated candidates -> `执行模型关联`.
- RMU and feeder validation each perform one analysis pass and immediately
  populate the selectable association table from the same validated snapshot.
- The former `preview_association()` module function is retained only as an
  internal candidate builder; it is no longer a separate user task.

### Faster selected execution
- `执行模型关联` consumes the current validation snapshot and only the rows
  explicitly checked by the user.
- Source-file fingerprints and current database facts are still rechecked
  immediately before write-back.
- RMU execution continues to avoid a second full-drawing validation pass.
- Feeder execution now also avoids a second full-drawing validation pass:
  selected topology regions refresh the current `dms_section_device` pool,
  protect unselected valid links, recalculate only selected FeedLine targets,
  write exact selected XML IDs, and build an operation-scoped report directly.
- Association result HTML/CSV contains only the objects selected in this
  execution, including selected rows skipped because execution-time facts
  changed.

### UI wording
- Startup workflow text is now:
  `模型校验 -> 勾选可关联对象 -> 执行模型关联`.
- Removed user-facing wording that implied a separate association-preview step.

## [3.6.8] - 2026-08-15

### RMU HTML report
- Removed the `环网柜档案` section from RMU HTML only.
- `环网柜档案.csv` remains generated independently and unchanged.
- All other model validation, association, database, feeder and UI logic remains unchanged.

## [3.6.7] - 2026-08-13

### Startup fix
- Fixed the Help page startup crash:
  `NameError: name 'policy_text' is not defined`.
- The broken leftover variables `policy_text`, `policy_layout`, and `policy`
  were removed.
- The device-name help group now correctly uses its own
  `naming_text`, `naming_layout`, and `naming` widgets.

### Business naming refactor
- Renamed the RMU device business field from `p_name_string` to
  `logical_code`.
- `logical_code` now has one clear meaning:
  the logical device CODE derived from the visible G drawing and used to
  compare with the database `CODE`.
- `CBreakerDis.logical_code` = resolved graphical switch text.
- `ZhaiWaiJieDiDaoZha.logical_code` = paired graphical breaker code + `D`.
- `BusDis.logical_code` = `BUS`.
- The default RMU row no longer seeds any logical value from the raw XML
  `p_NameString` attribute.
- Renamed `CODE_EQUALS_PNAME` to `CODE_EQUALS_LOGICAL_CODE`.
- Renamed PNAME-oriented validation/error identifiers to logical-CODE
  terminology.

### Raw XML isolation
- The G parser raw XML accessor is now explicitly named
  `xml_p_name_string`.
- It exists only for parsing/debug compatibility and is not used by RMU
  business naming.
- Generic RMU/feeder visible-text recognition now reads `Text/DText.ts`
  instead of falling back to raw XML `p_NameString`.

### UI / report readability
- RMU work-table and reports use `逻辑CODE（图上规则）`.
- Internal association execution reads `logical_code`.
- `p_NameString` remains mentioned only in help text that explicitly says
  the raw XML attribute is ignored.

### Regression
- Added startup-help regression checks for the removed `policy_*` variables.
- Added a test proving the default RMU device row never copies XML
  `p_NameString` into `logical_code`.
- Added a source-level regression check ensuring the RMU business layer no
  longer contains the old `p_name_string` field.

## [3.6.6] - 2026-08-13

### Switch naming is graphical-text-only
- Removed the user-selectable `p_NameString` / graphical-text switch-name mode.
- `CBreakerDis` device names now ALWAYS come from visible text inside the RMU.
- XML `CBreakerDis.p_NameString` is never used as a device-name source.
- `ZhaiWaiJieDiDaoZha` logical name is always:
  `paired graphical breaker name + D`.
- `BusDis` logical name is always `BUS`.
- RMU settings UI now displays the fixed rule:
  `环网柜内图上文字（固定）`.
- Old persisted `P_NAME_STRING` configuration values are ignored safely.

### Graphical device-name database validation
- Every graphical breaker name is checked against database CODE under the
  current uniquely resolved RMU.
- A graphical name that cannot be resolved, has no corresponding CODE, or
  matches duplicate CODE rows produces an explicit device error telling the
  user to check that RMU's switch naming.
- Device report wording now uses `图上逻辑名称` instead of presenting the
  internal compatibility field as an XML p_NameString.

### RMU type two-stage recognition
- Rule 1 (authoritative):
  use cabinet Text/DText Y1/Y2/Y3/... and Q1/Q2/Q3/... .
  Each Y = one L; each Q = one T.
- Rule 2 (fallback only):
  if NO Y/Q text is recognized at all, use CBreakerDis.devref:
  `Load_Breaker => L`, `Circuit_Breaker => T`.
- When both rule outputs are available, they are ALWAYS cross-checked.
- A mismatch never overrides the text-derived type and does not by itself
  block a database-valid model association.

### Explicit type cross-check warning
- Added `柜型校验状态` and `柜型交叉校验说明` to RMU HTML/CSV reports.
- If text type and devref type differ:
  - status = WARN when no more severe RMU/device issue exists;
  - the report names the RMU (or rectangle XML ID if the RMU name cannot be
    resolved);
  - the report includes both type values;
  - the message asks the user to inspect Y/Q naming and switch devref template.
- Console prints the same targeted warning.

### Help/UI
- RMU help now documents one fixed device-name source only.
- RMU help documents the two-stage cabinet-type algorithm and mandatory
  cross-validation.
- Feeder trusted-RMU processing uses the same graphical-text-only RMU device
  naming behavior.

## [3.6.5] - 2026-08-13

### RMU type recognition: Y/Q text is absolutely authoritative
- RMU cabinet type is determined first from Text/DText located inside the RMU:
  - Y1/Y2/Y3/Y4/... => one L each
  - Q1/Q2/Q3/Q4/... => one T each
- Y/Q labels are naturally ordered as Y1,Y2,... then Q1,Q2,...
- As long as at least one Y/Q label is recognized, the text-derived type is
  the final type.
- `CBreakerDis.devref` is now only a fallback when NO Y/Q label can be
  recognized at all.
- When both text and devref are available, devref is only cross-check data and
  never overrides the text result.

### Smart RMU recognition
- Added global SMART/SMR recognition across the entire G drawing.
- Every exact SMART or SMR Text/DText marker is assigned to the nearest RMU.
- There is no maximum-distance cutoff, because SMART is commonly inside the
  cabinet while SMR may be outside.
- Either SMART or SMR makes the RMU smart.
- If both SMART and SMR belong to one RMU, it is still one smart RMU and the
  marker field records `SMART, SMR`.
- Feeder trusted-RMU diagnostics reuse the same smart metadata.

### RMU reports
- RMU HTML summary now includes:
  - cabinet type;
  - type source;
  - text/devref cross-check;
  - smart YES/NO;
  - SMART/SMR marker types;
  - database/device completeness.
- Added a new compact HTML `环网柜档案` table.

### New RMU profile CSV
- Every RMU validation/association report now creates:
  `report_环网柜档案.csv`.
- Exactly one row per RMU containing:
  - G file;
  - RMU sequence and rectangle XML ID;
  - RMU name;
  - RMU type and source;
  - smart status and SMART/SMR markers;
  - database record count;
  - whether the RMU database record is unique;
  - RMU ID;
  - G device count;
  - uniquely matched database device count;
  - whether RMU devices are complete;
  - validation status and explanation.
- `设备是否完整=YES` means the RMU itself is database-unique and every G
  device participating in validation uniquely resolves to a database device
  under the same RMU. Old/wrong G KeyID does not by itself make database
  inventory incomplete.

### UI and help
- Added `打开环网柜档案 CSV` result button.
- RMU and feeder help pages now document strict Y/Q priority, devref fallback,
  SMART/SMR global nearest-RMU assignment, and the RMU profile report.

### Regression
- Existing tests updated to the final field rule: partial Y/Q text still wins
  over devref.
- Added SMART+SMR nearest-RMU tests and RMU profile CSV/HTML tests.
- Actual `JED-CTL-AJWD-26.sln.pic.g` regression:
  - 37 structural RMUs detected;
  - 11 RMUs receive SMART markers;
  - RMU `25583` (Rect XML ID 2000567) => `2L1T`,
    source `TEXT_YQ`, labels `Y1,Y2,Q1`, devref cross-check `2L1T`.

## [3.6.4] - 2026-08-13

### RMU type recognition
- Added RMU cabinet type recognition such as `2L1T` and `3L1T`.
- Primary rule reads Y/Q Text or DText inside the RMU rectangle: each `Y*` is one L and each `Q*` is one T.
- Added devref cross-check/fallback: `Load_Breaker` -> L and `Circuit_Breaker` -> T.
- Complete Y/Q text is authoritative; devref is used when text is incomplete.
- Text/devref mismatch is reported but does not block existing RMU association eligibility.
- RMU summary HTML/CSV now exposes type, recognition source and consistency.
- Feeder trusted-RMU diagnostics now include the RMU type.
- Updated RMU and feeder module help pages with the new rules.

### Uploaded AJWD-26 regression
- Verified RMU `25583` (frame XML ID `2000567`) as `2L1T`.
- Its G XML contains Y1, Y2, Q1 and devrefs with two Load_Breaker plus one Circuit_Breaker; both rules agree.
- Across the uploaded file, 35 RMUs resolve to `2L1T` and 2 RMUs resolve to `3L1T`; text and devref results agree for all detected RMUs.

# Changelog

## [3.6.3] - 2026-08-13

- 同步更新 RMU 环网柜模型帮助：补充三类图元结构硬条件、数据库事实优先修复原则、环网柜筛选与仅执行勾选设备规则。
- 同步更新馈线模型帮助：明确不依赖馈线名称，使用可信 RMU + FEEDER_ID + 拓扑区域确定馈线归属。
- 补充 FeedLine 未关联、旧关联、设备重建、表号/域号错误以及 DUPLICATE_LINK 的可选择修复说明。
- 帮助页与 v3.6.x 当前实际校验/关联逻辑保持一致。


## [3.6.2] - 2026-08-13

### RMU structural hard rule
- RMU recognition now explicitly requires the candidate rectangle to contain all three core G object types: `CBreakerDis`, `ZhaiWaiJieDiDaoZha`, and `BusDis` (at least one of each).
- Missing any one of the three types means the rectangle is not an RMU candidate.
- The same structural rule is used by the standalone RMU module and by the feeder module when it discovers RMUs as topology references.
- Existing selected-direction/global Text/DText cabinet-name recognition remains unchanged.

### FeedLine selectable association table
- The feeder model now uses the same explicit-selection interaction as the RMU model.
- After feeder validation, the workspace shows `可关联馈线段选择（模型校验结果）`.
- Rows can be filtered by FEEDER_ID, FeedLine XML ID, target section name, or explanation text.
- Only database-safe `UNLINKED`, `RELINK`, or `DUPLICATE_LINK` rows are checkable.
- Execution processes only the FeedLine rows selected by the user; unselected FeedLines remain untouched.
- The table keeps a fixed 38 px row height and tooltip access to full long text.

### Duplicate FeedLine repair
- When multiple FeedLines use the same valid `dms_section_device`, ALL duplicated rows are now reported as `DUPLICATE_LINK` rather than treating the first row as PASS.
- Duplicate rows are repairable when the topology region has one confirmed FEEDER_ID and the database section pool is unique.
- If the user selects only one duplicated row, unselected duplicate rows reserve their current database section and the selected row is reassigned to another available section.
- If multiple duplicate rows are selected, they re-enter the region allocation pool together and are assigned in FeedLine top-to-bottom / left-to-right order from currently available sections.
- Execution refreshes the current `dms_section_device` pool before write-back and writes only selected XML IDs.

### HTML report
- Feeder summary and FeedLine detail tables continue to provide report-only checkboxes.
- Checking a report row keeps the entire row highlighted while horizontally scrolling; these HTML checkboxes never change model association behavior.

### Regression
- Added tests confirming that an RMU rectangle missing one of the three required G device types is rejected.
- Added tests confirming that all repeated FeedLine links are exposed as selectable duplicate-repair candidates.

# Changelog

All notable changes to Distribution Model Manager are documented here.



































## [3.6.0] - 2026-08-13

### Feeder model: RMU-topology architecture
- Replaced feeder-name/spatial-title association as the automatic feeder source.
- Single-feeder and merged overview G drawings now use one unified pipeline:
  `trusted RMU -> RMU.FEEDER_ID -> G topology component -> dms_section_device`.
- FeedLine ownership no longer depends on ABH-xx / AJWD-xx text.

### Trusted RMU reference rules
- An RMU can be used as a feeder reference only when:
  - its G RMU name resolves to exactly one dms_combined_device record;
  - RMU ID and FEEDER_ID are valid;
  - at least one existing RMU device KeyID can be verified;
  - every currently linked RMU device used as evidence resolves to its expected table/domain and belongs to that same RMU.
- The following RMUs are reported but ignored as feeder references:
  - no current model link;
  - database RMU name 0/multiple records;
  - missing FEEDER_ID;
  - existing incorrect/cross-RMU model links.

### Topology consistency guard
- G XML network objects are grouped by connection geometry using FeedLine, ConnectLine, Bus and major electrical switch objects.
- RMU frames bridge the network branches that physically enter the cabinet.
- A topology region with no trusted RMU is `NO_TRUSTED_RMU_REFERENCE` and cannot auto-associate.
- If trusted RMUs in one connected region expose different FEEDER_ID values, the whole region is blocked as `FEEDER_RMU_CONFLICT` and requires manual confirmation.
- No majority vote is used.
- Disconnected fragments independently confirmed to the same FEEDER_ID are consolidated into one allocation pool, preventing duplicate SECxxx assignment.

### FeedLine allocation
- Once one FEEDER_ID is confirmed, the validator queries the real rows from dms_section_device for that FEEDER_ID.
- Correct existing FeedLine links reserve their database section first.
- Wrong-feeder, wrong table/domain or duplicate old links become RELINK candidates.
- Unlinked + RELINK FeedLines are ordered top-to-bottom, then left-to-right.
- Remaining database sections are naturally ordered by actual SEC number and assigned from smallest to largest.
- Database section numbers are never generated by the application.
- Expected KeyID remains table 13503 / domain 1 and voltype remains dms_section_device.BV_ID.

### Feeder HTML report row markers
- Added a checkbox column to both `馈线汇总` and `馈线段明细` HTML tables.
- Checking a row keeps the entire row highlighted while horizontally scrolling.
- These checkboxes are report-only manual markers and do not participate in validation or write-back.
- Feeder summary now exposes trusted RMU count, ignored RMU count, trusted RMU names, trusted FEEDER_ID values and ignored-RMU reasons.

### UI
- Removed the meaningful distinction between single/multi feeder processing modes.
- Feeder page now shows the fixed mode `RMU 拓扑自动识别（固定）` because the same topology algorithm handles both drawing forms.
- Updated current-module help to document RMU trust, FEEDER_ID consistency and blocking rules.

### Tests
- Added topology tests covering:
  - two trusted RMUs with the same FEEDER_ID;
  - conflicting FEEDER_ID values blocking the whole connected region;
  - unlinked RMU ignored while a trusted peer still confirms the region;
  - existing correct section reservation + smallest remaining SEC allocation;
  - HTML checkbox/highlight markers.

## [3.5.1] - 2026-08-13

### Composite feeder title recognition fix
- Fixed a critical v3.5.0 design issue where a G feeder title had to be
  uniquely resolved in Oracle BEFORE it could become a spatial feeder anchor.
- G XML is now authoritative for feeder-title spatial detection:
  - `<Text ts="ABH-03">` and similar engineering titles are extracted first;
  - composite regions are built from the G titles even when the initial DB
    title lookup returns zero or multiple rows;
  - Oracle resolution now confirms the title after the region is established.
- This prevents a large merged drawing from incorrectly collapsing to:
  `AMBIGUOUS / 识别馈线区域=1`.

### Feeder title cleanup
- Added canonical feeder token extraction:
  - `ABH-03` -> `ABH-03`
  - `AJWD_07` -> `AJWD-07`
  - `BAY NO + ABH-17` -> `ABH-17`
- Clean standalone feeder titles have higher priority than nearby descriptive
  `BAY NO ...` annotations.
- A nearby low-quality annotation for the same feeder no longer creates an
  extra region.
- Two genuinely separate clean titles with the same feeder name are preserved
  and flagged as duplicate composite anchors instead of being silently merged.

### Existing-model reverse confirmation
- When G-title -> Oracle feeder-name lookup cannot uniquely resolve a region,
  the validator now uses existing linked FeedLine models as a second source:
  `KeyID -> dms_section_device -> feeder_id -> dms_feeder_device`.
- The fallback is accepted only when all resolvable linked FeedLines in the
  region point to one feeder and that feeder name is compatible with the G
  title.
- If linked FeedLines in one spatial region resolve to multiple feeder IDs,
  the region is reported as inconsistent and is not auto-associated.

### Feeder database display-name consistency
- `get_feeder_info()` now returns the same
  `station.name + feeder.name` display name used by
  `find_feeders_by_name_hint()`.
- This makes reverse KeyID ownership checks compatible with titles such as
  `ABH-03` versus database display names such as `JED NTH ABH 03`.

### Diagnostics
- Feeder validation console now logs:
  - raw G title candidate count;
  - cleaned G anchor count;
  - database-uniquely-resolved anchor count;
  - the actual cleaned G feeder-title list.

### Actual uploaded ABH composite regression
- The uploaded `JED-NTH-ABH.sln.pic.g` structure was inspected directly.
- Its XML contains 398 FeedLine objects and clean top feeder titles including
  ABH-03 through ABH-49.
- The corrected detector identifies 47 clean title anchors in this source
  layout instead of one unresolved region.
- The source drawing contains two clean `ABH-26` titles and no clean `ABH-27`
  title; both ABH-26 anchors are intentionally retained and reported as a
  duplicate-title data issue.

## [3.5.0] - 2026-08-13

### Feeder composite-drawing support
- Feeder model now supports three drawing modes in the desktop UI:
  - `AUTO` / 自动识别（推荐）;
  - `SINGLE` / 单馈线图;
  - `MULTI` / 多馈线组合图.
- AUTO mode detects a multi-feeder composite when two or more feeder-name anchors above/near Bus objects are uniquely confirmed by the Oracle feeder master data.
- Single-feeder behavior remains backward-compatible: Bus-near text first, then filename fallback.

### Multi-feeder recognition
- Long horizontal Bus objects no longer contribute only one nearest Text. All plausible engineering labels immediately above the Bus span are retained as feeder-name candidates.
- A top-band feeder-title scan is also used so feeder titles placed in the intentional gap between two Bus segments are not missed.
- Candidate labels are confirmed against `dms_feeder_device`; device numbers and common labels such as SMART/Q1/Y1/BUS are not accepted as feeder anchors.
- Feeder names continue to use punctuation-insensitive normalized matching, e.g. `ABH-06` -> `ABH06` and can match database display names such as `JED NTH ABH 06`.

### FeedLine region assignment
- Confirmed feeder anchors are sorted by X coordinate.
- Composite drawings are partitioned into feeder regions using the midpoint between adjacent anchors.
- Each `<FeedLine>` is assigned to the corresponding spatial feeder region before database validation.
- Every feeder region independently performs the existing section validation and assignment logic:
  - validate existing KeyID/table/domain/owner feeder;
  - reserve correctly/currently referenced database sections;
  - order unlinked FeedLine elements top-to-bottom then left-to-right;
  - allocate remaining `dms_section_device` rows in natural SEC sequence.
- Existing links are therefore checked against the feeder region in which the FeedLine is actually drawn.

### Topology consistency guard
- Added a lightweight endpoint-connectivity guard for FeedLine/ConnectLine geometry.
- Topology is deliberately secondary to spatial regions: future drawings may intentionally connect two feeder regions, so a cross-region connection is reported and never used to merge two feeders automatically.
- Feeder section reports expose topology component/cross-region metadata for troubleshooting.

### Safety / ambiguous composite handling
- If the same database feeder is detected at multiple independent composite anchors, both affected regions are blocked from automatic section allocation to prevent reusing the same database section sequence twice.
- If the user explicitly chooses MULTI mode but fewer than two uniquely confirmed feeder anchors can be found, the file is marked `AMBIGUOUS` and automatic association is blocked.
- Original G files remain unchanged; all write-back continues to target Workspace safety copies.

### Reports
- Feeder summary now includes drawing type, feeder-region sequence, and FeedLine assignment method.
- FeedLine detail now includes drawing type, region sequence, spatial/topology assignment information, and cross-region connectivity flags.

### Database fix
- Fixed `OracleClient.get_feeder_info()` so feeder master table 13500 is correctly resolved instead of referencing an undefined local variable.

### Validation
- Added regression coverage for automatic multi-feeder detection, spatial FeedLine partitioning, independent per-feeder section allocation, and duplicate feeder-anchor blocking.
- No smoke test added.

## [3.4.0] - 2026-08-13

### RMU execution performance
- Split RMU workflow into two explicit phases:
  - full model validation = full G/RMU/device analysis;
  - execute association = selected-device-only processing.
- Clicking `执行模型关联` no longer reruns full RMU validation for the whole G file.
- Execution only re-checks database facts for RMUs/devices explicitly selected in the in-app table.
- RMU queries and per-table device inventory queries are cached during one execution, so multiple selected devices in the same RMU do not repeat the same database query.
- G objects are written directly by `(tag + XML ID)`; the execution phase does not rediscover frames, labels or unrelated devices.

### Database refresh at execution time
- Selected devices receive a lightweight current-database re-check immediately before write-back:
  - RMU name is still unique;
  - CODE still uniquely matches the logical p_NameString inside that RMU;
  - device still belongs to that RMU;
  - BV_ID is present;
  - Expected KeyID still verifies against table/domain.
- If a previously validated device was deleted/re-created and its ID/BV_ID changed, execution refreshes the current ID/BV_ID/Expected KeyID and writes the new values.
- If database truth becomes ambiguous after validation, only that selected device is skipped; other selected valid devices continue.

### Operation-scoped report
- RMU association completion no longer generates another full validation report.
- The association report contains only RMUs and devices selected for this execution.
- RMU summary shows only selected RMUs.
- Device details show only selected devices and their execution result.
- Successful rows use `ASSOCIATION_WRITE_SUCCESS`.
- Devices skipped because database facts changed at execution time are reported as FAIL in this operation report only.
- The HTML title is now `RMU 模型关联执行报告` for operation-scoped RMU reports.

### Console
- Removed the post-write full-G validation loop and its many `无需关联` messages.
- Execution logs now focus on:
  - number of selected RMUs/devices;
  - selected RMU database re-check;
  - database target changes;
  - safety-copy write-back;
  - success / skip totals.

### Unchanged
- Original G files remain unchanged.
- Workspace safety-copy behavior is unchanged.
- RMU database-truth eligibility rules are unchanged.
- BV_ID -> voltype is unchanged.
- Feeder workflow remains unchanged.
- No smoke test added.

## [3.3.2] - 2026-08-13

### RMU selection table UI
- Kept the RMU-name live filter introduced in v3.3.1.
- Forced every row in the in-app selectable device-detail table to the same height: 38 px.
- Disabled cell word-wrapping in this table so long descriptions no longer expand individual rows.
- Long cell content is elided with `...`; the complete text remains available in the existing tooltip.
- The vertical header uses fixed section resize mode to prevent Qt from recalculating different row heights.

### Unchanged
- RMU validation and selective association logic are unchanged.
- Filtering remains display-only and never changes checkbox state or eligibility.
- Feeder behavior is unchanged.
- No smoke test added.

## [3.3.1] - 2026-08-13

### RMU selection table
- Added a fast RMU-name filter above the in-app selectable device-detail table.
- Supports partial matching such as `17613`, `RMU-42646`, or other RMU name fragments.
- Filtering is live while typing.
- Added a clear-button and a dedicated `清除筛选` action.
- The selection counter shows the number of currently visible rows when a filter is active.

### Safety
- Filtering is display-only.
- Hidden rows keep their checkbox state.
- Filtering never changes validation results, association eligibility, selected candidate keys, or write-back behavior.
- Clearing the filter restores all device rows.

### Unchanged
- Database-truth association rules remain unchanged from v3.3.0.
- Selective RMU association behavior is unchanged.
- Feeder behavior is unchanged.
- No smoke test added.

## [3.3.0] - 2026-08-12

### RMU selective association UI
- RMU model validation now also builds a read-only in-memory association candidate set; it still does not modify any G file.
- Added an in-app `可关联设备选择（模型校验结果）` table immediately below task progress.
- The table shows G-file RMU device detail rows with:
  - G file;
  - RMU sequence and name;
  - G object type;
  - logical p_NameString / selected device name;
  - current database CODE;
  - PASS / UNLINKED / RELINK / RMU_RELINK / FAIL / BLOCKED status;
  - current model state;
  - current target database device ID;
  - Expected KeyID;
  - processing reason.
- Only rows already validated as:
  `association_ready=YES` and `writeback_needed=YES`
  are checkable.
- PASS, FAIL and BLOCKED rows cannot accidentally be selected for write-back.
- Nothing is selected by default. The user must explicitly choose one or more devices.
- Added `全选可关联` and `清空选择`.

### Selective write-back
- `执行模型关联` now processes only explicitly checked RMU device rows.
- Users can select:
  - one device;
  - multiple devices in one RMU;
  - devices across multiple RMUs / G files.
- Only G files containing checked devices are copied into the current Workspace `g_output`.
- The final validation report is generated from those processed safety-copy G files.
- Device eligibility is never re-decided by the checkbox UI; the RMU validator remains the only authority.

### Database-truth rule retained
- Current database truth remains authoritative.
- A unique RMU + unique CODE/p_NameString match + correct RMU ownership + valid Expected KeyID/BV_ID is selectable.
- Old wrong KeyID/domain/device ID or an old cross-RMU link remains correctable through RELINK / RMU_RELINK.
- Database ambiguity remains a hard blocker.

### Unchanged
- Original G files are never modified.
- BV_ID -> voltype write-back is unchanged.
- Feeder module behavior is unchanged.
- No smoke test was added.

## [3.2.0] - 2026-08-12

### RMU association strategy
- Changed RMU association authority from the old G KeyID to the CURRENT database truth.
- A device is association-eligible when:
  - RMU name resolves to exactly one database RMU;
  - the G logical `p_NameString` / selected name uniquely matches one CODE inside that RMU;
  - CODE equals the logical `p_NameString`;
  - the matched current database device belongs to the same RMU;
  - Expected KeyID is valid;
  - BV_ID is available when write-back is needed.
- Device-level failures remain isolated: one missing/duplicate CODE does not block other valid devices in the same unique RMU.

### Correctable model states
- Added `RELINK` (orange):
  - old device ID changed;
  - old device record was deleted and recreated;
  - current KeyID is stale or unresolvable;
  - current table/domain is wrong;
  - current KeyID differs from the new Expected KeyID.
  These cases are no longer red FAIL when the current database target is uniquely valid.
- Added `RMU_RELINK` (purple):
  - the existing G KeyID currently points to another RMU;
  - the current unique RMU still contains one valid CODE/p_NameString target.
  The tool may overwrite the old association and link to the correct current RMU.
- Existing correct models remain green PASS.
- Unlinked but valid devices remain yellow WARN.

### Device recreation / ID changes
- If a previously linked database device was deleted and recreated with a new ID,
  the old G KeyID no longer blocks association.
- The current RMU + CODE/p_NameString match is resolved again and a new Expected KeyID,
  BV_ID/voltype and model attributes are written to the Workspace copy.

### HTML report usability
- Added a left-side selection checkbox to RMU summary and device detail rows.
- Checking a row keeps the whole row outlined in blue while horizontally scrolling,
  reducing the chance of reading the wrong KeyID/Domain/BV_ID/description row.
- Updated status legend for PASS / UNLINKED / RELINK / RMU_RELINK / BLOCKED / FAIL.

### Unchanged hard blockers
- RMU database name has 0 or multiple records.
- Current-RMU CODE match has 0 or multiple records.
- CODE does not equal the logical p_NameString.
- The current target database device does not belong to the current RMU.
- Expected KeyID validation fails.
- Required BV_ID is missing for write-back.
- RMU feeder information remains completely excluded from RMU validation.

## [3.1.4] - 2026-08-12

### Fixed
- Fixed application startup failure:
  `AttributeError: 'MainWindow' object has no attribute 'show_current_module_help'`.
- `_current_module_help_html()` and `show_current_module_help()` are now proper
  `MainWindow` class methods instead of accidentally nested local functions
  inside `_update_module_stack_height()`.
- No RMU, Feeder, database, KeyID, BV_ID, report, or write-back business logic
  was changed.

## [3.1.3] - 2026-08-12

### Feeder UI
- Feeder Table/Domain spin controls now use exactly the same dark-green up/down button style as the RMU module.
- Removed the user-editable feeder master table row from the Feeder settings page.
- The Feeder settings page now exposes only:
  - `13503 / dms_section_device`
  - Domain `1`
- The internal feeder master table remains fixed at `13500` and is no longer a user-facing setting.

### Workspace module help
- Added a dedicated `当前模型帮助` button directly in the Model Workspace task area.
- The help content changes automatically with the selected model type.
- Feeder identification rules and FeedLine association rules were removed from the main Feeder settings page and moved into Feeder model help.
- Added dedicated RMU model help in the same Model Workspace button.
- Help is displayed in a separate scrollable dialog so it does not consume normal workspace configuration height.

### Unchanged
- RMU validation and association business rules are unchanged.
- Feeder validation and association business rules are unchanged.
- BV_ID -> voltype write-back remains unchanged from v3.1.2.
- Original G files remain unchanged; write-back continues only on Workspace safety copies.

## [3.1.2] - 2026-08-12

### Model write-back
- RMU `CBreakerDis`, `ZhaiWaiJieDiDaoZha`, and `BusDis` now write `voltype` from the matched database device `BV_ID`.
- FeedLine now writes `voltype` from `dms_section_device.BV_ID`.
- Removed the old RMU write-back constant `voltype=0`.
- FeedLine section queries now include `BV_ID`.
- FeedLine detail reports now show current and target `BV_ID`.
- Association preview messages show the exact `voltype` that will be written.

### Safety
- An unlinked RMU device with an empty database `BV_ID` is blocked only for that device.
- An unlinked FeedLine with an empty database `BV_ID` is blocked only for that FeedLine.
- No new automatic model association is allowed to write an empty or zero-placeholder `voltype`.

### Unchanged
- KeyID calculation rules are unchanged.
- RMU and feeder ownership validation rules are unchanged.
- Original G files remain unchanged; write-back still operates only on Workspace safety copies.

## [3.1.1] - 2026-08-11

### UI
- Fixed RMU / Feeder module switching geometry.
- Feeder settings now use the same expanding width policy as RMU settings.
- Feeder configuration changed to a full-width two-column layout:
  feeder recognition rules on the left and database table/domain settings on the right.
- FeedLine association rules now span the full configuration width below the two columns.
- Module switching now releases the previous page's fixed height before changing the stacked page.
- The newly selected module is re-laid out using the actual workspace width before calculating its natural height.
- Only the outer workspace scroll area remains responsible for page scrolling; no local module scrollbar is introduced.

### Unchanged
- RMU validation/association business rules are unchanged.
- Feeder validation/association business rules are unchanged.
- Original G files remain read-only and all write-back continues to target Workspace safety copies.

## [3.1.0] - 2026-08-11

### Added
- Enabled the independent Feeder Model module.
- Added single-feeder name resolution from nearest Text around `<Bus>`, with filename fallback.
- Added punctuation-insensitive feeder name containment lookup against `dms_feeder_device` (13500).
- Added `<FeedLine>` model validation.
- Added `dms_section_device` (13503) / Domain 1 Expected KeyID generation and Oracle verification.
- Added validation for existing FeedLine KeyIDs and actual feeder ownership.
- Added automatic assignment for unlinked FeedLines using remaining database section records.
- Added top-to-bottom / left-to-right ordering for unlinked G FeedLine objects.
- Added natural database section ordering using SEC001, SEC002, SEC003...
- Added safe FeedLine write-back to Workspace copies only:
  `app=6500000`, `p_ReportType=1`, `state=20`, `keyid=Expected KeyID`.
- Added dedicated Feeder Summary and FeedLine Detail HTML/CSV reports.

### Safety
- Existing wrong FeedLine links are reported but are not silently overwritten.
- Existing correctly linked database sections are reserved before assigning unlinked FeedLines.
- Original G files remain unchanged.

### RMU
- RMU module continues to perform zero feeder validation. The new feeder logic exists only in the independent Feeder Model module.

## [3.0.27] - 2026-08-10

### Association
- Device-level failures no longer set the whole unique RMU to association-ineligible.
- Missing/duplicate CODE blocks only the affected G element.
- CODE/p_NameString mismatch blocks only the affected G element.
- Wrong RMU ownership or wrong existing KeyID blocks only the affected G element when the RMU itself is unique.
- Other valid devices in the same RMU remain eligible for write-back.
- RMU NAME 0/multiple remains a whole-RMU blocker.

### Reporting
- Added separate RMU-level and device-level blocker columns.
- Unique RMUs with partial device errors are reported as WARN while remaining association-eligible.

### Unchanged
- No feeder validation.
- BusDis remains Table ID 13506 / Domain 1.

## [3.0.26] - 2026-08-10

### Validation
- Made database-device RMU ownership an explicit hard rule instead of relying only on `combined_id`-scoped queries.
- Added one-to-one validation for logical `p_NameString` values inside each G-file RMU.
- Added one-to-one validation so one database device ID cannot be consumed by multiple G elements.
- Missing CODE remains a hard FAIL for the corresponding G element and blocks automatic association.
- Duplicate CODE remains a hard FAIL.
- For non-unique RMU names with existing manual KeyIDs, CODE uniqueness is now re-queried inside the actual owner RMU before accepting the manual link.
- Existing manual links across multiple same-name `combined_id` values remain a hard `RMU_LINK` error.
- Existing manual links to another RMU NAME remain a hard `RMU_LINK` error.

### Unchanged
- Unrelated extra database devices are ignored.
- No feeder validation is performed.
- BusDis remains Table ID `13506`, Domain `1`.

## [3.0.25] - 2026-08-10

### Reporting
- Removed RMU-summary columns `CODE`, `GRAPH_NAME`, `COMBINED_TYPE`, and `RUN_STATE` from HTML and CSV.

### Validation
- Added cross-device consistency validation for existing manual KeyIDs when an RMU NAME is not unique.
- Existing linked devices inside one G-file RMU must all resolve to the same actual `combined_id`.
- Multiple same-name RMU IDs used by devices inside one G RMU are now a hard `RMU_LINK` error.
- Existing KeyID resolving to another RMU NAME remains a hard `RMU_LINK` error.
- RMU NAME uniqueness, device CODE uniqueness, CODE/p_NameString equality, Expected KeyID, and actual RMU ownership remain the core checks.

### Removed
- No feeder validation or feeder reporting is reintroduced.

## [3.0.24] - 2026-08-10

### Changed
- Removed all feeder-based validation from the RMU module.
- G filename feeder hints are no longer parsed or used.
- RMU `feeder_id` is no longer resolved through `dms_feeder_device`.
- Device `feeder_id` is no longer queried or compared.
- Removed `FEEDER` / `FEEDER_MISMATCH` from RMU validation and HTML status legend.
- Removed feeder-related columns from RMU summary and device-detail reports.

### Validation
- RMU association now depends only on RMU uniqueness, CODE uniqueness,
  logical p_NameString/CODE equality, Expected KeyID correctness, and existing
  model RMU ownership.
- Existing KeyID pointing to another RMU remains a hard `RMU_LINK` error.

### Unchanged
- BusDis remains Table ID `13506`, Domain `1`.
- Original G files remain unchanged; association writes only Workspace copies.

## [3.0.23] - 2026-08-10

### Fixed
- Corrected BusDis default domain from `0` to `1`.
- BusDis now uses Table ID `13506`, table `dms_bs_device`, Domain `1`.
- BusDis Expected KeyID therefore uses `DeviceID + (1 << 32)`.

### Migration
- Legacy saved configuration `BusDis / 13506 / Domain 0` is automatically migrated to Domain `1` on startup.

### Reporting
- Changed the HTML status-color legend from one horizontal row to a vertical list.
- Each status now has its own row with a dedicated label and explanation.

## [3.0.22] - 2026-08-10

### Fixed
- RMU NAME lookup now treats `dms_combined_device.NAME` as a native string field.
- Replaced `TRIM(TO_CHAR(name))` with `TRIM(name)` for RMU lookup.
- RMU names are never converted to integers.

### Changed
- RMU recognition now supports common engineering names containing letters,
  digits, hyphens, underscores and dots, up to 128 characters.
- Added regression coverage for names such as `RMU-42646`, `ABC_123`,
  `JED-RMU-01` and numeric-only names.

## [3.0.21] - 2026-08-10

### Changed
- Feeder mismatch is now warning-only and no longer blocks automatic model association.
- RMU feeder mismatch and device feeder mismatch use orange `FEEDER` status.
- Duplicate/missing RMU still produces a red RMU-summary error.
- Duplicate/missing RMU blocks automatic association only for unlinked G elements.
- Existing manual KeyIDs are still inspected when the RMU name is duplicated/missing.
- Existing manual links validate logical CODE/p_NameString and actual RMU ownership.
- Existing KeyID pointing to another RMU remains a hard `RMU_LINK` error.
- Duplicate-RMU device rows with a valid existing manual link can be PASS/FEEDER rather than being forced into BLOCKED.

## [3.0.20] - 2026-08-10

### UI
- Removed the model-operation combo box from the top task form.
- Added explicit bottom action buttons: Model Validation, Association Preview, Execute Association.
- Replaced ambiguous "Run Current Task" behavior with explicit task actions.
- Report buttons now use task-specific labels and are hidden when their files do not exist.

### Reporting
- Validation reports are stored under `validation_report`.
- Association-preview reports are stored under `association_preview_report`.
- After association write-back, the generated G-file copies are revalidated and a full final report is written to `association_result_report`.
- Final association report uses the same RMU/device report structure as model validation.

### Safety
- Original G files remain unchanged.
- Association write-back still targets only copies under Workspace `g_output`.

### Assets
- Rebuilt `app_logo.png` and `app_logo.ico` with transparent outer corners around the green rounded contour.

## [3.0.19] - 2026-08-10

### Fixed
- Fixed `RMU_NOT_FOUND_IN_DATABASE` rows being appended after all database-matched RMUs.
- RMU summary now always sorts strictly by G-file RMU sequence.

### Changed
- RMU summary is one row per G RMU frame.
- Duplicate Oracle RMU records no longer expand into multiple summary rows.
- Duplicate RMUs show only the database match count and a blocking error; multiple IDs are intentionally hidden.
- Removed duplicate report columns: first-frame XML ID, G match count, duplicate G RMU sequence, G frame XML IDs, and database record sequence.
- Device detail remains G-element based.

## [3.0.18] - 2026-08-10

### Changed
- RMU label color is now used only when one RMU owns multiple candidate names.
- A single candidate label is always selected directly, regardless of color.
- For multiple candidates: nearest green wins; if no green exists, nearest label wins.
- Text ownership remains one-to-one with the nearest RMU frame.

## [3.0.17] - 2026-08-10

### Fixed
- Fixed a green RMU label being reused by multiple vertically aligned RMU frames.
- Each candidate Text now belongs to exactly one nearest RMU frame.
- Fixed the reported duplicate `15953` caused by label ownership, not by Oracle.

### Changed
- RMU summary is now database-record based: one `dms_combined_device.ID`
  produces one summary row.
- Device details remain G-element based.
- If several G frames point to the same database RMU ID, their frame
  indices/XML IDs are aggregated on the single database summary row.

## [3.0.16] - 2026-08-10

### Fixed
- Restored the missing `RmuValidator._make_expected_keyid()` method.
- KeyID generation now explicitly uses `DeviceID + (Domain << 32)`.
- Fixed the runtime crash encountered during CBreakerDis validation.

### Added
- Added KeyID encoding regression tests for Domain 0 and Domain 40.
- Added a validator private-method integrity test that detects undefined
  `self._xxx()` method calls before release.

### Architecture
- Kept `src/dmm` intentionally. `dmm` is the Python package namespace for
  Distribution Model Manager, not a second application.

## [3.0.15] - 2026-08-10

### Added
- Added color-aware RMU label recognition from G-file Text lc/lcc attributes.
- Green RMU labels can be found across long directional distances.
- Added nearest-green selection when multiple labels exist above/beside an RMU.
- Added support for engineering RMU names such as AK-900841 instead of numeric-only labels.
- Added current-KeyID RMU-name verification via device combined_id -> dms_combined_device.
- Added purple RMU_LINK status for links that point to another RMU even on the same feeder.
- Added current linked RMU name/ID fields to device details.

### Changed
- Non-green RMU labels retain the legacy search-distance limit as a safe fallback.
- Existing-link correctness now validates RMU identity independently from feeder identity.

## [3.0.13] - 2026-08-10

### Added
- Added independent visual states: PASS / WARN / FEEDER / BLOCKED / FAIL.
- Added status-color legends to HTML reports and Help.
- Duplicate RMUs now permit read-only inspection of existing manual KeyID links.

### Changed
- Feeder mismatch uses orange FEEDER instead of red FAIL.
- Duplicate RMU remains a permanent automatic-association block.
- Under duplicate RMUs, unlinked devices are red FAIL; linked devices are inspected for CODE/feeder consistency and become orange FEEDER or blue BLOCKED.
- Unrelated database devices remain ignored.

## [3.0.12] - 2026-08-10

### Fixed
- Fixed `NameError: g_file is not defined`; feeder extraction now uses the parsed G-file path.

### Added
- Added strict feeder consistency checks for every unique RMU.
- Added feeder consistency checks for each uniquely CODE-matched database device.
- Device details now show the exact matched database device plus G-file feeder and database-device feeder.

### Changed
- RMU name 0 rows or multiple rows remains a hard association block.
- A unique RMU on the wrong feeder is now a hard association block.
- A requested CODE with no database row reports that the device does not exist.
- A requested CODE with multiple database rows reports a CODE duplication error.
- Unrelated extra database devices remain ignored.

## [3.0.11] - 2026-08-10

### Added
- Added G-file feeder hint extraction (`ABH-06` from `JED-NTH-ABH-06.sln.pic.g`).
- Added separator-insensitive feeder comparison for `ABH-06`, `ABH_06`, and `ABH 06`.
- Added explicit FEEDER_ID resolution through table 13500 / `dms_feeder_device`.
- Added readable database feeder composition using station name + feeder NAME.
- Added feeder validation columns to the RMU summary report.

### Changed
- Unlinked but database-matched G devices are WARN/yellow again, while remaining association-ready.
- Feeder mismatch now blocks RMU association.
- Device-detail report remains G-element-only.

## [3.0.10] - 2026-08-10

### Changed
- Device validation is now G-file-driven: only database rows whose CODE is requested by a real G element participate in validation.
- Unrelated extra database device rows under the same combined_id are ignored.
- Device detail reports contain G elements only; DATABASE_INVENTORY pseudo rows were removed.
- An unlinked G element with a unique valid CODE match is now PASS and marked as requiring write-back instead of WARN.
- Complete database inventory parity and complete-table CODE integrity scans no longer block RMU association.

### Fixed
- Relevant device quantity is now derived from one unique matched DB device per G element.
- `_cffi_backend` packaging verification now checks for the actual binary module, not merely any cffi-related file.

## [3.0.9] - 2026-08-10

### Fixed
- Added explicit `cffi` and `_cffi_backend` packaging for python-oracledb / cryptography.
- Fixed packaged Oracle Thin Mode failure: `No module named '_cffi_backend'`.
- RMU summary now orders strictly by RMU sequence (`frame_index`).
- Device detail ordering now applies only one rule: group G object types inside each RMU.

### Changed
- Removed device-name, XML ID, DB ID, status, and RMU-name ordering from device-detail reports.
- Same-type device rows preserve validator/source order.

## [3.0.8] - 2026-08-10

### Fixed
- Fixed source-mode Workspace path. Runtime data now lives at `<project>/workspace/` instead of under `src/dmm/infrastructure/filesystem/`.
- Strengthened device-detail sorting so rows are grouped deterministically by G object type inside every RMU.
- Added regression coverage for duplicate-RMU (`RMU_NOT_UNIQUE`) rows.

### Changed
- Build output directory renamed from `Release/` to lowercase `release/`.
- `.gitignore` and documentation updated to match the lowercase release directory.

## [3.0.7] - 2026-08-10

### Fixed
- Explicitly packaged `cryptography`, required by python-oracledb Thin Mode.
- Fixed packaged Oracle connection failure `DPY-3016: No module named 'cryptography'`.

### Changed
- Replaced the build script again with a strict six-step build flow.
- Removed every smoke-test code path from `app.py` and `build_exe.ps1`.
- Build script now prints its own version, path, and target at startup to prevent accidentally running an older script.

## [3.0.6] - 2026-08-10

### Fixed
- Device detail reports are now consistently sorted instead of preserving validation-generation order.
- `CBreakerDis`, `ZhaiWaiJieDiDaoZha`, and `BusDis` records are grouped by device type.
- Database-only inventory rows remain grouped with their corresponding G object type.
- HTML and CSV exports now share the exact same canonical ordering.

### Added
- Natural sorting for RMU names and device names (`Y2` sorts before `Y10`).
- Report sorting unit tests.

## [3.0.5] - 2026-08-10

### Changed
- Removed packaged-EXE smoke testing from the build process.
- Simplified `build_exe.ps1` based on the proven GFileStudio v2.17.0 packaging flow.
- The build script no longer executes the freshly generated unsigned EXE.
- Retained source dependency validation and explicit PyInstaller collection for Oracle dependencies.

## [3.0.4] - 2026-08-10

### Fixed
- Windows Application Control blocking an unsigned freshly-built EXE no longer causes a false PyInstaller build failure.
- Runtime application failure and OS execution-policy blocking are now handled separately.

### Added
- PyInstaller xref verification for `getpass`, `oracledb`, `ssl`, `socket`, and `secrets`.
- `BUILD_VERIFICATION.txt` in every Release.
- Runtime smoke test remains mandatory whenever Windows allows the generated EXE to execute.

## [3.0.3] - 2026-08-10

### Fixed
- Fixed packaged EXE failure caused by missing Python standard library module `getpass`.
- Strengthened the PyInstaller `oracledb` hook with explicit dynamic/stdlib imports.
- Added a frozen-EXE smoke test that imports `getpass`, `ssl`, `socket`, `secrets`, `oracledb`, and `PySide6`.

### Changed
- Replaced the two-layer build entry with a single root `build_exe.ps1`.
- Removed `build.bat` and `scripts/build.ps1` to eliminate build-entry ambiguity.
- Release creation only happens after the actual packaged EXE passes the smoke test.

## [3.0.2] - 2026-08-10

### Fixed
- Fixed `RmuSettingsWidget.collect_settings()` being accidentally defined outside the class.
- Restored the fixed default Oracle password `OracleDV1Dec.25`.
- Empty passwords from older workspace configuration now fall back to the default password.

### Changed
- Kept `app.py` as the clearly documented Windows development entry point.
- Added `requirements.txt` for straightforward `pip install -r requirements.txt` setup.

## [3.0.1] - 2026-08-10

### Changed
- Added a root-level `app.py` as the standard Windows development launcher.
- `python app.py` now works directly from the project root.
- PyInstaller now uses the same `app.py` entry point for packaged builds.
- The internal `src/dmm` architecture remains unchanged.

## [3.0.0] - 2026-08-10

### Changed
- Reorganized the source tree into a `src/dmm` package layout.
- Separated UI, application orchestration, domain rules, infrastructure, configuration, and resources.
- Moved RMU label spatial constants out of global application configuration into RMU-specific constants.
- Renamed label parameters for clearer intent:
  - `DEFAULT_LABEL_MAX_DISTANCE` → `RMU_LABEL_SEARCH_MAX_DISTANCE`
  - `DEFAULT_LABEL_OVERLAP_TOLERANCE` → `RMU_LABEL_EDGE_TOLERANCE`
- Replaced `requirements.txt` with `pyproject.toml` as the dependency source of truth.
- Kept only one public build entry point: `build.bat`.
- Moved the PowerShell build implementation to `scripts/build.ps1`.
- Removed development convenience scripts `run.bat` and `install.bat`.
- Runtime output remains isolated under the application-owned `workspace/`.
- Preserved safe G-file association: original G files are never modified.

### Packaging
- Retained a dedicated PyInstaller hook for `oracledb`.
- Build fails if the Oracle dependency is not found in packaged output.
## v4.1.33
- UI only: moved Task Progress into the Current Run Console area so the busy indicator and live status remain visible beside execution logs.
- Kept the v4.1.32 background association worker and indeterminate/busy progress behavior unchanged.
- No RMU, feeder, Oracle, KeyID, candidate-selection, or G-file write-back business logic changes.
