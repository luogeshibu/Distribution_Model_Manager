## v4.1.135 主网入口背景标签自适应排版

“图形工作区 → 主网入口背景标签修正”现在不仅修正括号外的主网名称，还会同步调整背景对象尺寸并重排两行文字：主网名称在上，目标 RMU 括号名在下，两行水平居中、整体垂直居中。支持 Poke / Rect / RoundRect 以及符合可见填充条件的其它背景几何对象。原始 G 文件不覆盖。

## v4.1.134 整图馈线源唯一性规则

整图馈线拓扑分析现在把“主站/馈线源”当作严格唯一对象处理：一个主站出线只能有一个馈线名字。主网 Bay/CBreaker 标题优先；只有当现场不画主站设备、仅在线路末端写 `TRUB-BH21` 这类文字时，才允许把该末端文字作为唯一兜底源。重复同名、中段文字、已有主网设备源区域中的沿线名字均不会参与拓扑传播。

NOP 两侧同样执行唯一源规则：每侧最终必须恰好一个主站/馈线名称。报告新增“馈线源唯一性检查”，可直接查看哪些文字被选中、排除或判为源冲突。

## v4.1.133 主网入口背景跳转标签修正 / 整图馈线锚点排除

- 图形工作区新增 **主网入口背景标签修正**：识别主网 CBreaker 300G 范围内的可见背景跳转标签，例如 `MNA4-12` + `(33359)`；括号目标保持不变，只把括号外主网文字修正为主网已确认馈线名。
- 背景识别不依赖固定颜色：支持有填充的 `poke` / `rect`，也兼容 Text 自带背景属性。
- 只有 300G 内存在唯一主网 CBreaker 时才自动修改；多个主网候选时只报告 `AMBIGUOUS_MAIN_STATION`，不猜测。
- 原始 G 文件永不覆盖，输出 `*.main-station-label-fixed.sln.pic.g` 安全副本，并生成 HTML / CSV 明细。
- **整图馈线拓扑分析**在主网 Bay 标题与沿线馈线文字识别之前，先识别并排除这类背景跳转标签，确保它们绝不成为馈线锚点。
- 实测 `OSLA-08-MNA2-35-MNA4444444-32-MNA3-29-MNA4-12-ARF2-0.sln.pic.g`：识别 5 组背景跳转标签，其中 `MNA4-12 + (33359)` 修正为 `MNA4-AH312 + (33359)`；整图分析不再把 `MNA4-12` 识别成馈线。

## v4.1.132 整图拓扑图独立缩放与全屏查看
- 整图拓扑 HTML 报告中的修复前/修复后图谱各自支持 `− 缩小`、`+ 放大`、`重置`、`适应窗口`、`全屏查看`，并支持 `Ctrl + 鼠标滚轮` 独立缩放（20%～400%）。
- 图谱缩放仅影响报告查看，不参与任何拓扑判定或 G 文件修复。


- 仅增强“整图馈线拓扑分析”；既有“环网柜馈线拓扑分析”和“馈线段所属馈线分析”业务逻辑保持不变。
- 先对原始 G 做完整馈线传播，再针对 `NO_FEEDER_ERROR` 孤立拓扑区域定位疑似断点。
- 自动修复只处理线端点之间 `3G < distance <= 4.5G` 的微小缺口，并要求双方端点候选唯一。
- 每个候选都先在内存中模拟补链；只有拓扑错误数量下降、没有新增 `MULTI_FEEDER_ERROR`、补链两端最终落在同一唯一馈线时才允许写修复副本。
- 原始 G 永不覆盖；安全修复输出 `*.topology-fixed.sln.pic.g`（非标准文件名则输出 `*.topology-fixed.g`），并在 `link` 与 `node_area` 中补充双向端点引用。
- HTML 报告新增“修复前拓扑图”“修复后拓扑图”“拓扑连接修复 / 断点诊断”表；同时保留 RMU 所属馈线、NOP 边界、异常设备和最终设备归属表。
- 额外输出 `whole_graph_topology_before.svg`、`whole_graph_topology_after.svg`、`whole_graph_topology_repairs.csv`。
- 最终修复版 G 会再次完整分析；若错误未下降或新增多馈线冲突，会自动撤销修复输出。
- 现场样例 `MAK-XXX-SHR-04-SHR2-29-HNYN-18-SALR-33-SHR2-30`：自动识别并修复 `34000376 ↔ 35001786`（端点距离 3.162G），拓扑异常从 177 降至 5，`11231` 等 9 个 RMU 恢复为 `SHR2-AH329`。

## v4.1.130 RMU 馈线拓扑 Pole 显式连接修复

- 【环网柜馈线拓扑分析】现在把 `Pole` 作为纯拓扑传导节点，解决 FeedLine 通过 `Pole.node_area/link` 转接时传播被中断的问题。
- 只信任 G 文件显式 `link/node_area`；不会因为 Pole 位置靠近线路就自动连线。
- `TNM-AH324 -> Pole -> ... -> 9002.Y2` 这类现场链路可以继续传播；红色 NOP 端口仍保持硬断点。
- 现场 9002 场景应得到：RMU 所属 `TNM-AH324`，`MKN-AH341` 在 NOP Y1 截止。
- 原【馈线段所属馈线分析】代码不变；【整图馈线拓扑分析】原本已有 Pole 节点支持。

## v4.1.129 红色 NOP 范围识别

- 红色 NOP 不再只接受精确 `#ff0000` / `255,0,0`，改为 HSV + RGB 双重范围判断。
- 红色色相范围：`H <= 20°` 或 `H >= 340°`；同时要求 `S >= 45%`、`V >= 30%`。
- 额外要求 `R > 1.5 × G` 且 `R > 1.5 × B`，避免绿色、黄绿色、青色、蓝色等被误识别为红色。
- 支持 `lc=R,G,B`、`R,G,B,A`、`lcc=#RRGGBB` 及历史 8 位 ARGB/RGBA 表达。
- 现场示例 `#ff2b05 / 255,43,5` 现在可正确识别为红色 NOP；`#00ff00 / #55ff00` 仍会被忽略。
- NOP 的 RMU 归属、Y/Q 开关匹配、支路断点、馈线传播规则均不改变。

## v4.1.128 RMU 端口几何补链修复

- 修复环网柜馈线拓扑分析中“图上已连接、XML 缺少 link/node_area 时端口不可达”的问题。
- 在原有严格 `line↔line` 几何补链之外，新增非常受限的 `line endpoint ↔ RMU Y/Q / BusDis` 端子补链：仅当线端点距离设备边界不超过 6 个 G 坐标单位才连接。
- 同时支持主站 Bay 内唯一 `CBreaker` 的端子几何补链，避免主站出线视觉连接存在但 XML 引用缺失时出现 `SOURCE_ENTRY_NOT_FOUND`。
- NOP 规则不变：红色 NOP 所属 Y/Q 仍是硬边界；NOP 另一侧非 NOP 端口若唯一可达 `TNM-AH324`，则 RMU 所属馈线判为 `TNM-AH324`，NOP 一侧馈线仅记录为截止馈线。
- 端点落在设备图元内部深处不会补链；同一端点同时等距命中多个设备时也不会猜测连接。
- 新增整图拓扑模块同样复用该严格端子补链，因此整图 RMU/设备所属馈线结果同步修复。
- 原“馈线段所属馈线分析”业务模块未修改。

## v4.1.127 整图拓扑强校验 + RMU 所属馈线独立报告

- 仅更新【整图馈线拓扑分析】；既有【环网柜馈线拓扑分析】和【馈线段所属馈线分析】核心逻辑保持不变。
- 非 NOP 设备强制满足 `1 device -> 1 feeder`：唯一馈线为 `CONFIRMED`；无馈线为 `NO_FEEDER_ERROR`；多馈线为 `MULTI_FEEDER_ERROR`。后两种均作为拓扑错误，报告提示优先检查 NOP 漏设、误设、识别失败或拓扑断点错误。
- NOP 开关本身仍不要求单一所属馈线，只记录各端口/各侧的 feeder；传播仍不跨越 NOP。
- 新增 RMU 所属馈线分析：只统计同柜非 NOP Y*/Q* 开关。每个非 NOP 端口必须唯一归属，并且全部端口必须一致到同一馈线；NOP 端口只作为边界，不参与 RMU 归属，不采用多数投票。
- HTML 新增独立【RMU 所属馈线】表和【拓扑异常设备】表；异常行醒目标记。同步新增 `whole_graph_rmu_feeders.csv`。

## v4.1.126 新增整图馈线拓扑分析（纯图形 / 单 G 文件）

- 图形工作区新增独立【整图馈线拓扑分析】，不改动既有【环网柜馈线拓扑分析】和【馈线段所属馈线分析】。
- 模块一次只分析一个 G 文件，纯图形只读：不连接 Oracle，不校验 13500/13501/13502/13503，不做模型关联，也不修改 G。
- 馈线锚点同时支持主网 Bay 标题，以及直接写在 FeedLine 上的完整馈线名（例如 `TURB-BH-04`）。
- 红色 NOP 若能归属 RMU，继续复用原有 RMU Y*/Q* 端口断点规则；未归属 RMU 的红色 NOP 一律作为柱上开关 NOP。
- NOP 开关本身不判所属馈线；分别输出断点各侧所属 feeder。
- 整图图构建额外纳入 `Pole` / 显式 `link` / `node_area` 节点，避免杆塔节点把 FeedLine 拓扑截断；严格几何补链阈值保持 3G / 2G。
- 输出 HTML、整图设备 CSV、NOP 两侧 CSV、馈线锚点 CSV。

## v4.1.125 RMU 按图形拓扑所属馈线约束关联 + 可选修正 13501.FEEDER_ID

- 麦加【RMU 环网柜模型】复用【图形工作区 → 环网柜馈线拓扑分析】作为所属馈线唯一来源；每个 RMU 先得到拓扑馈线，再解析为唯一 13500 `FEEDER_ID`。
- 未关联 RMU：`dms_combined_device.NAME` 查询被严格限制在拓扑 `FEEDER_ID` 下；本馈线下找不到/重复时直接阻断，禁止跨馈线兜底。
- 已有关联 RMU：若现有子设备 KeyID 能证明当前 13501 就是该 RMU，但 `13501.FEEDER_ID` 与拓扑馈线不一致，默认只报告。
- RMU 配置新增独立复选开关【强制修正已关联 RMU 所属馈线（修改 13501.FEEDER_ID）】，默认关闭。开启后，模型校验会生成独立可选择的 `RMU_FEEDER_ID` 修正项。
- 执行修正时只更新 `dms_combined_device.FEEDER_ID`，使用 `WHERE ID=:rmu_id AND FEEDER_ID=:old_feeder_id`（旧值为空时用 `IS NULL`）的乐观锁条件；必须恰好影响 1 行并回查验证后才 COMMIT，否则 ROLLBACK。
- `CONFLICT / UNRESOLVED / 13500 不唯一` 一律禁止数据库修正。

## v4.1.124 馈线段按拓扑所属馈线分别建库

- 馈线模型直接复用【图形工作区 → 馈线段所属馈线分析】的 FeedLine 拓扑结果。
- 每条 FeedLine 必须先唯一确认所属主网馈线；CONFLICT / UNRESOLVED 不再猜测，也不进入自动建库/关联。
- 已有 13503 只有在 `FEEDER_ID` 与该 FeedLine 的拓扑所属馈线一致时才视为正确；仅 Domain 错误时保留原 13503.ID 并修正 KeyID。
- 未关联/错误关联 FeedLine 只复用自己所属馈线下的空闲 `dms_section_device`，取消跨馈线统一资源池。
- 某一馈线下 13503 不足时，只在该馈线下创建实际短缺数量；一个 G 图可同时在多条所属馈线下分别创建。
- 执行阶段修复跨馈线重关联的保护逻辑：同一文件中已选择迁移到其它馈线的 FeedLine，其旧 13503 不再被误当成“未选择占用”而阻塞其它分组。

## v4.1.123 馈线段所属馈线分析（独立图形模块）

- 图形工作区新增【馈线段所属馈线分析】，与已经现场验证通过的【环网柜馈线拓扑分析】完全独立；原 RMU 拓扑核心文件和判定逻辑不修改。
- 新模块复用同一套麦加拓扑基础规则：主网 Bay/CBreaker 馈线源、`link/node_area`、端点≤3G / 端点到线段≤2G 的严格补链、仅红色 NOP、NOP 只能在所属 RMU 框内匹配 Y*/Q* 开关、左右侧优先水平中心 Y 对齐 / 上下侧中心 X 对齐。
- 从每条主网 feeder 沿真实拓扑逐支路传播；线路可多路走，只有当前支路实际碰到红色 NOP 对应开关才停止，其它支路继续。
- 每条 `FeedLine`：唯一 feeder 可达为 `CONFIRMED`；多 feeder 同时可达为 `CONFLICT`；无 feeder 可达为 `UNRESOLVED`，绝不按全图最近馈线猜测。
- 输出独立 `feedline_feeder_topology_report.html`、`feedline_feeder_topology.csv`、`feedline_nop_boundary_summary.csv`；只读 G 文件，不修改 G，不连接/查询/写入 Oracle。

## v4.1.122 RMU-only feeder topology propagation

- 【环网柜馈线拓扑分析】业务输出只保留 RMU 所属馈线；FeedLine、ConnectLine、Bus、BusDis 仅作为拓扑寻路介质，不再输出 FeedLine 业务归属。
- 主网 feeder 从 CBreaker 按 link/node_area + 严格几何补链逐支路传播；没有遇到红色 NOP 就持续传播，分叉后的各支路独立继续。
- 红色 NOP 是端口级支路断点：只有真正走到该 Y*/Q* 开关的路径停止，同 feeder 的其它路径继续，不再做整条 feeder 全局排除。
- NOP 仍只允许在所属 RMU 框内匹配 Y*/Q* 开关；左右侧按中心 Y 水平对齐，上下侧按中心 X 对齐。

## v4.1.121 NOP 水平对齐与支路级截止

麦加【环网柜馈线拓扑分析】现在把 NOP 当作“端口级局部断点”，不是整柜/整线路断点。只处理红色 NOP。NOP 先绑定最近 RMU，然后只在该 RMU 内选择 Y*/Q*：左/右侧 NOP 优先按中心 Y 水平对齐，同一水平行有多个开关时取距离最近者；上/下侧镜像按中心 X 对齐。馈线可以多路传播，只有实际碰到 NOP 开关的那一路停止，其它非 NOP 支路继续。RMU 所属 feeder 只由真实 Y*/Q* 端口拓扑确定，不再使用 FeedLine 外接矩形中心作为辅助证据。

## v4.1.120 红色 NOP 白名单

麦加【图形工作区 → 环网柜馈线拓扑分析】现在**只处理红色 NOP**。任何非红色 NOP（包括纯绿色、黄绿色 `#55ff00`、黄色、白色等）都视为图形标注并完全忽略。其它拓扑和 RMU 所属馈线逻辑保持 v4.1.119 不变。

## v4.1.119 绿色 NOP 不参与环网柜馈线拓扑分析

麦加【图形工作区 → 环网柜馈线拓扑分析】现在把绿色 NOP 视为纯图形标注：完全忽略，不形成断点、不影响主网首柜排除，也不参与 RMU 所属馈线判断。其它颜色的 NOP 继续按最近 RMU + 最近 Y*/Q* 开关确定真实断点。

## v4.1.118 NOP边界柜所属馈线按非NOP端口判定

- 【环网柜馈线拓扑分析】中，NOP开关连接的馈线在该开关处截止，不再让该馈线占用整个NOP边界RMU的所属馈线。
- NOP柜优先汇总同柜非NOP Y*/Q*端口的拓扑馈线；只有一个一致馈线时，将其写入报告的“RMU所属馈线”。
- 例如 RMU 17296：Y3 为 NOP，MNA2-AH335 在 Y3 处截止；Y1/Y2/Q1 均解析为 MNA4-AH332，因此 17296 的所属馈线判定为 MNA4-AH332。
- HTML/CSV 增加“RMU归属判定”“在NOP处截止馈线”“端口角色”等审计字段；NOP汇总表同步显示 RMU所属馈线和截止馈线。
- 既有“主网首柜入线开关本身为NOP则整条主网馈线退出候选”规则保持不变；模块仍为纯G图形只读分析，不查询 Oracle。

## v4.1.117 麦加源端 NOP 馈线排除 + NOP/RMU/开关汇总

- 【图形工作区 → 环网柜馈线拓扑分析】新增“源端 NOP 排除”规则：从每个主网 CBreaker 沿电气拓扑找到首个直连 RMU 的实际入线 Y*/Q* 开关。只有这个**实际入线开关本身就是 NOP 所属开关**时，该主网馈线才从全部配网设备候选中排除。
- 同一首柜里虽然存在 NOP，但如果 NOP 属于其它 Y*/Q* 开关，则该主网馈线仍正常参与拓扑判断。例如 `MNA4-AH332 → RMU 17296` 实际从 Y1 接入，而 NOP 属于 Y3，因此 `MNA4-AH332` 保留。
- NOP 所属开关改为：NOP 先归属最近 RMU，再在该 RMU 内按**实际几何最近距离**确定唯一 Y*/Q* `CBreakerDis`；不再用文字显示侧作为优先条件。
- HTML 报告新增/强化 `NOP所属RMU / 开关汇总`，逐条显示 NOP Text、所属 RMU、最近 Y/Q 开关、开关 XML、距离、是否为主网首柜入线开关，以及是否因此排除对应主网馈线。
- 主网馈线报告区同时列出“识别主网馈线 / 参与候选馈线 / 源端 NOP 排除馈线”。模块仍为纯 G 文件只读分析：不连接、不查询、不写入 Oracle，也不修改 G 文件。

## v4.1.116 麦加主网馈线 `_X/_Y` 标题支持

主网框外名称可直接识别 `SHM1-AH341_X` / `AH341_X` 这一完整馈线编号；`_X/_Y` 不再被截掉。其它麦加 RMU 与主站识别规则不变。

## v4.1.115 麦加名称颜色规则

- RMU 名称识别不限制 Text 颜色；颜色不参与优先级或消歧。
- 主站 Bay 馈线标题不限制 Text 颜色；仍要求无背景、格式合法、距离合规并一对一归属。

# 配网模型管理工具 / Distribution Model Manager v4.1.133

## v4.1.114 麦加环网柜馈线拓扑分析

- 图形工作区新增独立“环网柜馈线拓扑分析”。
- 只读解析主网馈线源、`link/node_area`、严格几何连接和 NOP 对应 Y*/Q* 开关，输出 RMU 唯一归属或 NOP 两侧馈线。
- 报告包含主网馈线源、NOP 边界、RMU 归属、RMU 端口归属和 FeedLine 拓扑审计；不修改 G 文件，不写 Oracle。

## v4.1.113 麦加馈线模型只读说明同步

【馈线模型】页面的“麦加馈线自动关联逻辑（只读说明）”已与 v4.1.112 实际业务逻辑完全同步：明确展示全部主网馈线识别、已有 FeedLine 合法集合校验、全馈线空闲 13503 资源池复用、资源不足时仅创建缺少数量，以及 HTML 报告必须列出全部识别馈线和每条 FeedLine 最终关联结果。底部固定规则文案同步改为“优先复用，缺少才创建”。业务关联算法不变。


## v4.1.112 麦加馈线集合校验

麦加环网图馈线模型把主网 Bay 确认出的全部馈线作为合法集合：已有 FeedLine 只要关联到集合内任一馈线即保留；待关联 FeedLine 优先复用集合内所有未占用 13503，资源不足时才稳定选择一条已确认馈线创建实际短缺。馈线校验 HTML 会完整列出本图识别到的全部馈线及数据库匹配结果。



## v4.1.111：馈线相邻对齐、跨距外扩，左右镜像可配置

- 【图形工作区 → 馈线避让调整】只处理压住 RMU 名称或 `NOP / N.O.P` 的 FeedLine。
- 同一 RMU 列中，相邻环网柜之间、Y 范围不重叠的馈线共用同一内侧轨道；跨越其它 RMU 的长馈线依次使用更外层轨道。
- 右侧馈线向右外扩，左侧馈线向左镜像外扩；两侧可分别启用/关闭。
- 默认参数：文字安全间距 `20 G`、错落轨道间距 `50 G`、同列判定范围 `220 G`、最大外移 `500 G`。这些参数可在界面配置并保存到当前用户设置。
- RMU 名称、NOP、RMU 本体、设备和原 FeedLine 连接端点保持不动；`link / node_area / keyid` 不修改。
- 现场样例验证中，相邻短馈线对齐到同一 X，跨多柜长馈线自动向外错开一个轨道，避免所有馈线叠成一根竖线。


## v4.1.109：新增馈线避让调整

- 【图形工作区 → 图形处理类型】新增 **馈线避让调整**。
- 只移动压住环网柜名称或 `NOP / N.O.P` 文字的 `FeedLine`；文字、RMU、设备和其它图元原地不动。
- 对发生碰撞的近似竖直馈线段，只向右做正交避让并保留原始两端连接点；默认安全间距 20 G，最大右移 500 G。
- 不修改 `link / node_area / keyid`，仅修改安全副本中的 `FeedLine.d` 和几何包围框。
- 无碰撞 FeedLine 完全不处理；无法仅靠右移安全解决的情况记录为未解决，不强行改线。
- 输出 `feeder_avoidance_report.csv/html`，记录每张图的碰撞、移动、未解决和最大右移情况。



## v4.1.108：RMU 名称只从框外找；柱上设备只认用户选择图元

- RMU 名称 Text 中心必须在所有已识别 RMU 框外；柜内 Text 永远不能参与 RIGHT、BOTTOM 或 GLOBAL fallback。
- RMU 名称继续按 RIGHT → BOTTOM → GLOBAL、最大 300 G、一柜一名/一 Text 一柜执行。
- 柱上开关和柱上变压器的设备身份只由用户维护的 devref 图元文件名单决定，不再按 XML 元素类型、RMU_* 前缀、颜色、形状或内部结构二次过滤。
- 名称 Text 搜索及数据库唯一性校验保持现有规则。

## v4.1.107：麦加环网柜名称 RIGHT → BOTTOM → GLOBAL 三阶段分配

- 第一阶段先对整张图所有 RMU 执行 **RIGHT <= 300** 的一对一名称分配。
- 第二阶段只对第一阶段未命中的 RMU 执行 **BOTTOM <= 300** 的一对一名称分配。
- 第三阶段只对前两阶段仍未命中的 RMU/Text 执行 **GLOBAL <= 300** 最近距离兜底。
- RIGHT/BOTTOM 阶段不再受“Text 必须属于全局最近 RMU”的前置限制，避免名称被相邻 RMU 从左侧错误抢占。
- 超过 300 G 单位的 Text 不参与当前 RMU 名称识别；Text 全局最近 RMU 一对一所有权规则保持不变。
- 环网柜名称 Poke 同步移动、NOP 与 Y*/Q* 开关水平中心对齐等 v4.1.104/v4.1.103 规则保持不变。


## v4.1.105：麦加柱上开关原始名称精确查询

- 柱上开关从 G 文件选中的 `Text.ts` 名称直接作为 13501 / `dms_combined_device.NAME` 查询值。
- 不删除空格、横线 `-`、点号 `.`，不做大小写或其他格式标准化。
- 13501 使用 `WHERE name = :device_name` 精确查询；不使用 `TRIM(name)`、CODE 兜底或 FEEDER_ID。
- 13501 唯一 → 13502 `combined_id` 唯一 → Domain 40 → Workspace 安全副本的原有链路保持不变。

## v4.1.104：环网柜名称 RIGHT → BOTTOM → GLOBAL + Poke 同步移动

- 麦加环网柜名称识别优先级固定为 **RIGHT → BOTTOM → GLOBAL fallback**：先使用当前 RMU 右侧名称，右侧没有时再使用下方名称，最后才做 200 G 单位范围内的全局兜底。
- 名称 Text 继续保持全图一对一所有权：同一个 Text 只归属其全局最近的 RMU，避免相邻柜之间相互抢占名称。
- “NOP / 环网柜名称位置调整”移动环网柜名称时，如果该名称已有 Poke 跳转，Poke 点击区域会使用与名称完全相同的 X/Y 位移同步移动。
- Poke 优先通过 `gfs_rmu_text_id` / `dmm_rmu_text_id` / `dmm_source_text_id` 精确绑定名称；兼容没有这些元数据的旧图，旧 Poke 在与名称点击区域高度重合且存在 `ahref` 时也会同步移动。
- NOP 规则保持 v4.1.103：只匹配当前 RMU 内的 Y*/Q* CBreakerDis，并与对应开关严格水平中心对齐。
- 原始本地/SSH G 文件继续只读，只修改 Workspace 安全副本，并在位置调整报告中增加名称 Poke 找到/移动统计。

## v4.1.103：NOP / 环网柜名称位置调整

- 图形工作区新增 **NOP / 环网柜名称位置调整**。
- NOP 只匹配当前环网柜内名称可确定为 `Y*` / `Q*` 的 `CBreakerDis` 开关设备（如 Y1/Y2/Y3/Q1/Q2/Q3）。
- NOP 只放在环网柜左侧或右侧；移动后强制满足 **NOP 中心 Y = 对应开关中心 Y**，实现严格水平中心对齐。
- NOP 支持“自动保持原左右侧 / 左侧 / 右侧”，可单独配置距边距离。
- 环网柜名称支持上、右、下、左四个边框中点位置，可单独配置距边距离。
- 原始本地/SSH G 文件继续保持只读，只修改 Workspace 安全副本，并生成 HTML / CSV 位置调整报告。

## v4.1.102：RMU 只读逻辑补充 Channel Status 状态图元写入规则

- “RMU 自动关联逻辑（只读说明）”新增独立的 Channel Status 步骤，并在固定数据库规则中明确 `dms_channel_info` 表 13566 / Domain 40。
- 明确柜内只识别 `Status` + `channel_status.zt.icn.g`；同一 RMU 多个状态图元直接阻断。
- 明确从唯一 RMU_ID 开始查询 `dms_terminal_info.COMBINED_ID`，联查 `dms_channel_info`，排除 `CHAN_NAME` 以 `DR` 结尾记录，数据库必须唯一。
- UI 说明完整显示 KeyID 规则与回写字段：`ID + (40 << 32)`，`app=6600000`、`voltype=-1`、`p_ReportType=1`、`state=39`、`keyid=Expected KeyID`，并清理历史 slot-1 残留字段。
- 最终校验与回写步骤顺延为步骤 7，并明确 Channel Status 执行阶段再次实时查询和校验；实际 v4.1.101 关联实现不改变。

## v4.1.101：麦加 RMU 增加 channel_status 关联

- 麦加环网柜的查找、名称分配和 13501 唯一解析逻辑保持不变；只在已经确定的 RMU 框内识别 `channel_status.zt.icn.g` 的 `Status` 图元。
- RMU 唯一后，复用积攒 v4.1.63 的 Channel Status 数据库规则：`dms_terminal_info.COMBINED_ID = RMU_ID`，再联查 `dms_channel_info`，排除名称以 `DR` 结尾的 channel。
- 数据库必须恰好返回 1 条 channel；按 `dms_channel_info.ID + (40 << 32)` 生成 KeyID，并通过 table `13566` / domain `40` 二次校验。
- 回写字段与积攒保持一致：`app=6600000`、`voltype=-1`、`p_ReportType=1`、`state=39`、`keyid=Expected KeyID`；若历史图元残留 EFI slot-1 字段则在安全副本中清理。
- 同一个 RMU 内发现多个 `channel_status.zt.icn.g` 时不猜测，全部阻断；RMU 身份未唯一时仅在报告中显示状态图元，不允许自动关联。
- 执行关联时会重新查询 channel 并再次校验 KeyID，避免预览后数据库变化导致写入旧关联。


## v4.1.100：熔断器改为用户维护图元名单

- 熔断器不再依赖【图元管理】FUSE 分类；用户加入“熔断器图元名单”的 devref 文件名直接认定为熔断器。
- 麦加默认熔断器图元包含 `Fuse_arrow.zwk.icn.g`、`Fuse_NON_SMART.zwk.icn.g`，可由用户增删并恢复默认。
- 熔断器配置界面与柱上开关/柱上变压器统一：名单动态高度、图元服务器只读搜索、复选框批量添加、展开/收起搜索、删除、恢复默认。
- 名单变更自动保存到当前 Windows 用户本地缓存，并提供“保存到本地用户缓存”按钮；替换程序目录后仍可继续加载。
- 熔断器后续“最近柱上变压器 → FUSE+变压器名称 → 13505/13513 NAME 唯一 → Domain=40 安全回写”逻辑保持不变。


## v4.1.99：柱上设备图元名单保存到本地用户缓存

- 柱上开关、柱上变压器两个模型都增加“保存到本地用户缓存”按钮，显示格式和行为保持一致。
- 从图元服务器添加、删除、恢复默认后继续自动保存；用户也可以随时点击按钮手动保存确认。
- 本地用户缓存独立于程序目录，Windows 下保存到当前用户 APPDATA 的 `DistributionModelManager/settings.json`，重新安装或替换源码目录后仍可读取。
- Workspace 的 `config.json` 继续保留为兼容副本，不影响现有项目运行方式。


## v4.1.99：柱上变压器图元名单与柱上开关统一交互

- 柱上变压器模型配置改为与柱上开关一致的紧凑布局：名单高度随图元数量动态增长，最多直接显示 12 行，更多时内部滚动。
- 取消手工文本框直接添加，新增“从图元服务器搜索并添加”；复用【图元管理】SSH 配置，只读搜索共享图元服务器。
- 服务器搜索区域默认收起，可展开/收起；搜索结果使用复选框，支持全选、全部取消、批量添加和双击单个添加。
- 加入柱上变压器名单的图元仍直接按 devref 文件名识别为柱上变压器；数据库、名称分配、KeyID 和安全副本回写规则不变。


## v4.1.97：柱上开关服务器搜索区域可展开 / 收起

- “从图元服务器搜索并添加”改为次级可折叠区域，默认收起，避免搜索框和结果长期占用柱上开关配置页面。
- 标题右侧新增“展开服务器搜索 / 收起服务器搜索”切换按钮；展开后底部另提供“收起搜索”按钮，用户随时可关闭搜索区域。
- 收起仅隐藏搜索面板，不删除已维护的柱上开关图元名单，也不修改服务器配置；重新展开后可继续搜索。
- 原有服务器只读搜索、复选框批量添加、RMU_* 安全排除和名单动态高度规则保持不变。


## v4.1.96：柱上开关从图元服务器搜索添加 + 名单动态高度

- 柱上开关配置不再要求手工键入图元名；可直接使用【图元管理】当前 SSH 配置，在图元服务器目录中按关键字只读搜索 `.g` 图元。
- 搜索结果显示服务器相对路径，可多选或双击，将图元文件名加入柱上开关名单；加入名单后仍统一直接认定为柱上开关，不区分 AR/LBS/SEC。
- `RMU_*` 图元继续硬性安全排除，搜索结果中不可加入。
- 柱上开关名单高度随文件数量自动增长，最多显示 12 行，更多时列表内部滚动，避免少量配置时出现大片空白。



## v4.1.94：柱上开关图元名单简化为“加入即识别”

- 柱上开关配置不再要求用户选择 AR / LBS / SEC。名单中只保存 devref 图元文件名，任何加入名单的图元都直接认定为柱上开关。
- 默认名单保持：`SEC_S.zwk.icn.g`、`SEC_NON.zwk.icn.g`、`SEC_NON_H.zwk.icn.g`、`AR_NON_H.zwk.icn.g`；`RMU_*` 仍为硬安全排除。
- 配置区压缩高度，默认 4 个图元无需大块空白；更多条目通过列表滚动显示。
- 数据库关联不再按 AR/LBS/SEC 对 13502 子设备消歧：13501 唯一后，13502 也必须唯一；多条时直接阻断关联并报告，禁止任意选取。
- 自动迁移 v4.1.93 的 `pole_switch_element_rules`：只保留图元文件名并丢弃 family 字段。



## v4.1.93：麦加柱上设备改为用户维护 devref 图元名单

- 柱上开关不再依赖图元分类标记，直接按用户维护的精确 devref 图元文件名识别。默认包含 `SEC_S.zwk.icn.g`、`SEC_NON.zwk.icn.g`、`SEC_NON_H.zwk.icn.g`、`AR_NON_H.zwk.icn.g`；每个文件同时配置 AR/LBS/SEC 设备族。
- 柱上变压器同样不再依赖 `TRANSFORMER_OH` 分类，直接按用户维护的图元文件名单识别；默认 `Transformer_OH.pb.icn.g`。
- 两个模型页面支持添加、删除、恢复默认，设置保存到本机配置；`RMU_*` 始终禁止作为柱上开关，防止误识别环网柜内部设备。
- FUSE 复用同一份柱上变压器名单。



## v4.1.92：麦加柱上变压器固定图元优先识别

- 柱上变压器模型优先按 `Transformer_OH.pb.icn.g` 的精确 devref 文件名识别；命中即直接视为柱上变压器，不依赖图元管理分类。
- `TRANSFORMER_OH` 分类标记降为第二级兜底：只有固定图元未命中时才使用。
- 固定图元优先级同时覆盖跨模型 Text 占用与柱上开关排除，避免同一 `Transformer_OH.pb.icn.g` 因错误/旧分类被柱上开关模型重复识别。
- 既有柱上变压器名称分配、200 距离、Text 一对一、13505 NAME 唯一关联和写回规则保持不变。

## v4.1.91：channel_status 距边显示完整

- `channel_status` 单独处理与组合处理中的“距边”输入框统一加宽，`5 px` / `1000 px` 在 Windows 高 DPI 下都不会被上下按钮遮住或裁切。
- 上下按钮仍保持深绿色高对比样式；滚轮仍只滚动页面，不修改数字。



## v4.1.91：SpinBox 上下按钮高对比优化

- 全程序数字微调框的上/下按钮改为深绿色高对比样式，使用白色箭头，解决现场界面按钮过浅、不易识别的问题。
- hover/按下状态与现有绿色主题保持一致；数值输入区增加右侧留白，避免与按钮重叠。
- 鼠标滚轮禁用规则不变：滚轮不会修改数字，只用于页面滚动。


## v4.1.89：组合处理 Poke 参数批量选择

- 组合处理页面的 Poke 参数区新增“全选 / 全部取消”，与上方组合处理步骤保持一致。
- 可一键同时启用或取消“主网馈线标题 Poke”和“SMART / SMR 智能 RMU Poke”。
- 运行组合任务期间批量选择按钮会自动禁用，避免处理中途改变本次任务参数。

## v4.1.88：图形组合处理 + 全局滚轮保护

- 图形工作区新增“组合处理（一键）”，可一次选择网络图元清理、channel_status 移动、Poke 跳转。
- 固定顺序：网络图元清理 → channel_status 移动 → Poke 跳转；同一文件串行使用上一阶段的安全副本。
- 只有某个 G 文件的全部已选步骤成功后，才写入最终 `g_output`；单文件失败会记录报告并继续处理其它文件。
- 组合处理生成统一 HTML/CSV 总报告，并保留每个文件各步骤的详细报告。
- 所有下拉框和数字框禁止鼠标滚轮误改值；鼠标位于这些控件上滚动时转为页面滚动。

## v4.1.87：图形工作区本地文件源自适应高度

- 修复图形工作区切换到“本地文件 / 目录”后，隐藏的 SSH 页面仍撑高公共文件来源区域，导致路径选择行上方/下方出现大块空白的问题。
- 文件来源堆栈现在只按当前可见页计算高度：本地模式自动收缩；SSH 模式自动展开完整远程配置和文件列表。
- 本地/SSH 切换后主动刷新布局，兼容 Windows 高 DPI；业务处理规则不变。

## v4.1.86：图形工作区运行修复 + 导航顺序调整

- 修复“环网柜网络图元清理 / channel_status 移动 / Poke”准备文件后调用已删除 `_refresh_poke_source_summary()` 导致 `MainWindow has no attribute` 的运行时错误；统一改为刷新当前图形工作区共享文件源状态。
- 左侧导航顺序调整为：模型工作区 → 图形工作区 → 数据库 → 图元管理 → 运行历史 → 设置 → 帮助。
- 模型工作区底部“数据库设置”按钮同步跳转到新的数据库菜单位置。
- 图形处理业务规则、SSH 只读规则和 Workspace 安全副本策略不变。

## v4.1.85：环网柜 channel_status 状态点移动

图形工作区新增“环网柜 channel_status 移动”。功能直接复用 G File Studio v2.18.244 已验证的 channel_status 归属与移动算法，可选择 8 个框内锚点和距边像素；只移动 `channel_status.zt.icn.g:channel_status` Status 本身。原始 G 文件保持只读，结果写入 Workspace 安全副本，并生成 HTML/CSV 报告。

## v4.1.84：环网柜网络图元清理

图形工作区新增“环网柜网络图元清理”。按固定 `Status.devref` 删除环网柜下方 G/L/N 三个网络状态图元，不依赖位置或数据库。原始文件只读，结果写入 Workspace 安全副本。


## v4.1.83：图形工作区统一任务编排

- 左侧将“图形处理”收敛为与“模型工作区”同级、同样式的一级菜单“图形工作区”，不再在左侧展开 Poke 二级菜单。
- 右侧图形工作区新增“图形任务 / 图形处理类型”选择器，交互结构与模型工作区的“模型任务 / 模型类型”一致。
- 当前首个图形处理类型为“Poke 跳转处理”；后续线路正交化、图形清理等功能可直接作为新的图形处理类型加入同一工作区。
- Poke 原有本地/SSH 只读文件源、处理选项、进度、日志和安全副本规则保持不变。


## v4.1.82：图形处理折叠菜单最终样式

- 左侧【图形处理】采用可折叠一级分组：带 `▾ / ▸` 箭头与圆角边框，结构参考现场批处理工具。
- 【Poke 跳转】作为缩进二级菜单显示在分组下；展开/收起只影响二级功能，不改变右侧业务页面。
- 配色完全沿用现有麦加现场版：深绿色侧栏、绿色悬停、金色当前功能选中，不引入蓝黑色第二套主题。
- 分组行使用显式高度，兼容 Windows 高 DPI，避免子菜单覆盖运行历史。

## v4.1.81：主网回写规则 + 左侧菜单最终层级

- 主网 CBreaker / Disconnector / GroundDisconnector / Bus 回写统一 `app=100000`；状态分别为 41 / 31 / 31 / 10，`voltype` 取数据库 `BV_ID`，`p_ReportType=1`，`keyid=Expected KeyID`。
- 真正执行前重新校验数据库及目标有效性，并要求目标身份与用户校验时完全一致。
- 左侧菜单固定为：模型工作区、数据库、图元管理、图形处理、`  Poke 跳转`、运行历史、设置、帮助；只有 Poke 作为二级菜单缩进。


## v4.1.80：图形处理菜单层级缩进

- 图形处理分组整体向右缩进，与普通一级菜单拉开层级。
- Poke 跳转在图形处理分组内再次缩进；颜色仍保持主侧栏绿色/金色体系。


## v4.1.80：图形处理二级菜单视觉统一 / Unified Graphics Submenu

- 左侧“图形处理 / Poke 跳转”继续保持父子二级菜单结构，但完全复用主侧栏绿色 + 金色选中态，不再使用蓝黑色独立卡片。
- “图形处理”父级仅作为展开/收起标题；进入 Poke 跳转时只高亮子项，颜色与其它一级菜单选中态一致。
- 清空复合导航背后的 QListWidgetItem 可见文字，避免 Windows / 高 DPI 下出现文字重影、叠层或“画中画”效果。
- 右侧 Poke 页面与 v4.1.78 业务逻辑保持不变；主网 Bus 仍按 ST_ID 在 410 / busbarsection 中稳定任意分配。


## v4.1.78：主网 Bus 按 ST_ID 任意关联 / Main-network Bus by ST_ID

- 主网 `Bus` 固定使用 `410 / busbarsection`、Domain `40`。
- Bus 关联只检查已确认变电站 `ST_ID`，不检查 410 记录的 `BAY_ID`。
- 同站存在多条 410 时，图形 Bus 从未使用记录中任意一对一取值；已有正确 Bus 关联优先保留。数据库同站记录多于图形 Bus 时只取所需数量，少于图形 Bus 才阻断。
- CBreaker / Disconnector / GroundDisconnector 保持现有 `BAY_ID` 关联规则。

## v4.1.61：麦加全局最近名称分配 / Makkah Global Nearest Name Allocation

- RMU、柱上开关、柱上变压器均按设备矩形框与 Text 矩形框的最小边缘距离计算；当前 RMU 名称最大距离为 300 G 单位，柱上开关和柱上变压器名称最大距离仍为 200 G 单位。
- 同一个 Text XML ID 只能分配一次；一旦被某个设备占用，后续设备不再使用。文字内容相同但 Text ID 不同仍可分别分配。
- RMU 保留专用排除规则；柱上开关和柱上变压器不限制颜色、背景或字母数字格式，纯小数统一排除。
- 关联逻辑说明区改为较窄的居中卡片面板，减少对 Console 和工作区的占用。



## v4.1.41：麦加主网 Bay 框直接关联 / Makkah Main-network Bay Direct Association

- 主网不再通过“最近 RMU 已有关联”反查上下文。程序只识别**包含 CBreaker 的最内层矩形框**作为主网 Bay 框。
- 每个 Bay 框只接受附近最近的**白色、无背景**馈线标题，例如 `MNA4-12`、`ARF2-07`；红色、有背景、超出安全距离的文字均不使用。
- 标题拆分为变电站前缀和馈线号：先在 405/substation 定位厂站，再在 13500/dms_feeder_device 定位该厂站馈线，再在 406/Bay 中得到唯一 `BAY_ID`。
- 使用 407/breaker 的 `ST_ID + BAY_ID` 交叉确认 Bay。确认后，框内 `CBreaker / Disconnector / GroundDisconnector` 分别在 407/408/409 中按相同 `BAY_ID` 直接取唯一设备并生成 KeyID。
- 同一 Bay 同一设备类型出现多条数据库记录时不猜测，直接阻断并报告。框外主网图元不参与本模块自动关联。
- 馈线多源识别也复用同一套 CBreaker 框 + 白色无背景标题规则。

## v4.1.40：麦加多馈线环网图归属判定 / Makkah Multi-feeder Ownership Resolution

- 组合环网图先从主网 `CBreaker` 与附近馈线名称确认图中馈线集合，并通过 13500 数据库唯一匹配得到 `FEEDER_ID`。
- 已正确关联的 RMU、柱上开关、柱上变压器作为局部馈线证据；不再把“全图最近设备距离”作为多馈线归属主判据。
- `NOP / N.O.P / N-O-P / N_O_P` 识别为馈线传播边界；NOP 两侧允许属于不同馈线。
- G 文件缺失 `link/node_area` 时，仅允许端点重合、3 个坐标单位以内端点匹配，以及 2 个坐标单位以内的端点到线段 T 接点补链，避免把相邻但不相连的线路误连。
- 同一严格连接区域同时出现多个 `FEEDER_ID` 时标记 `CONFLICT` 并禁止自动关联；没有可靠证据时标记 `UNRESOLVED`，不猜测。
- 多馈线图继续禁止把根 `facID` 写成某一条馈线；FeedLine 按各自归属馈线查询/分配 `dms_section_device`。
- 报告新增馈线归属状态、判定方法、候选 FEEDER_ID、证据来源、NOP 边界数量和严格补链数量。


## v4.1.39：馈线来源按模式显示 / Mode-specific Feeder Source UI

- FACID、文件名、人工输入三种模式只显示当前模式真正需要的输入控件。
- Manual 模式下人工目标馈线可直接编辑、删除和清空。
- This release changes feeder-source UI only; feeder resolution business rules remain unchanged from v4.1.38.

## v4.1.38：人工目标优先 + ABH 批量站内解析 / Manual Target Priority + ABH Batch Resolution

- FACID、文件名、人工输入三种馈线来源保持完全独立；已有根 facID 只表示当前状态。
- **人工模式是绝对目标**：例如输入 `ABH AH303`，只按该变电站+馈线查询 13500；不存在直接 FAIL，不回退 facID/文件名；不唯一也禁止自动选择。
- 如果人工/文件名目标与当前 G.facID 不同，目标仍以本次选择为准；未勾选“允许覆盖”时阻断回写并提示，勾选后 SINGLE_FEEDER 安全副本允许覆盖根 facID 并重新分配跨馈线 FeedLine。
- **批量文件名模式**：可只输入变电站名 `ABH`；程序逐文件读取末尾馈线号，如 `JED-NTH-ABH-03...` 的 `03`，只在 ABH 站馈线集合内唯一解析为 `AH303`。
- 批量站名也可留空自动识别；`JED-NTH-ABH` 会先尝试完整站点标识，再安全回退实际 405/substation 名称 `ABH`。
- 文件已带完整馈线号时（如 `JED-NTH-ABH-AH303...`）直接使用 `AH303`，不会重复添加前缀。
- 单文件和批量目录严格共用同一解析器；组合大图安全边界、馈线段缺失创建、Domain 校验、Oracle INSERT 边界及 g_output 安全副本规则不变。
- 中文/English UI、日志和帮助同步更新。

## v4.1.27: RMU Name Exclusions and Large-label Recognition

- RMU Recognition now includes a configurable **RMU Name Exclusion Strings** field. Enter exact values separated by commas or semicolons, for example `N.O.P, NOP, SFI, DAS/OK`.
- Defaults already include common operational annotations so they cannot become RMU-name candidates.
- Matching is exact rather than substring-based: excluding `SFI` does not exclude `SFI-9001`.
- Large-font labels are supported when the XML text bounding box overlaps the RMU border but the text center is still clearly in the selected name direction.
- Chinese and English UI are both supported for this setting.



## v4.1.26: English Console Translation Completion

- English mode now translates runtime Console/progress/diagnostic presentation text without changing any model, database, SSH, validation, association, or write-back rules.
- Engineering/status identifiers such as PASS/FAIL/RELINK, KeyID, FEEDER_ID, XML IDs, database IDs, file names, and raw values remain unchanged.

## v4.1.25: English Release Completion + RMU `66 B` Name Support

- English mode is treated as a release UI: header/title-bar edition text, Run History, Settings/Safety Policy, Help/current-model help, About and dynamic artifact controls are fully localized.
- Engineering/status codes and raw G/Oracle values remain unchanged across languages.
- RMU name filtering now accepts the narrow field form `number + space + suffix` such as `66 B`, while arbitrary labels such as `RMU 42646` remain excluded.
- Verified against `JED-CTL-AMR.sln.pic.g`: frame XML ID `2000597` resolves `66 B` from the configured top direction.
- Regression result: `194 passed, 1 skipped`.


## v4.1.24：SSH 大目录筛选/清空性能优化 / SSH Large-Directory Performance

- 修复远程目录包含 2000+ 个 G 文件时，“清空选择和搜索 / Clear Selection & Search”可能导致界面短暂无响应的问题。
- 远程文件表现在只在“刷新 G 文件列表”后创建一次；搜索和清空只切换现有行的显示状态，不再重建数千个表格单元格。
- 搜索输入加入短延迟合并（debounce），连续输入多个字符只执行最后一次筛选。
- 批量全选/清空时暂时关闭表格信号和重绘，操作完成后统一刷新。
- 中文和 English 模式同步保持相同操作逻辑和按钮文案。


## v4.1.23：SSH 文件选择操作简化 / Simplified SSH Selection Controls

- 删除 SSH 文件列表中的“取消当前结果 / Unselect Visible Results”按钮，减少与“清空”操作的功能重叠。
- “清空全部选择”升级为“清空选择和搜索 / Clear Selection & Search”：一次清空所有已勾选远程 G 文件、清空搜索关键字，并恢复完整远程文件列表。
- “全选当前结果 / Select Visible Results”继续只作用于当前搜索结果，不影响被筛选隐藏的文件。
- 新增功能同步维护简体中文与 English 文案；工程数据与业务状态码保持不翻译。

## v4.1.22：简体中文 / English 双语切换

- 设置页新增“语言 / Language”，支持 `简体中文` 与 `English` 即时切换。
- 最后一次语言选择保存到 Workspace 配置，重启程序后自动恢复。
- 主界面、数据库/SSH、模型工作区、RMU/馈线配置、常用提示和用户可见日志使用统一 i18n 翻译层。
- HTML/CSV 报告跟随当前语言输出标题、表头、筛选和说明。
- 工程数据、数据库内容、XML 属性、设备名称、状态码与诊断代码保持原始值，不因语言切换被修改。


## v4.1.21：RMU devref 柜型识别改为模板结构判断

- 只分析环网柜矩形框内的 `CBreakerDis.devref`；`ZhaiWaiJieDiDaoZha` / `RMU_ES`、BusDis 等其它图元不参与柜型判断。
- 不再识别 devref 名称中的业务关键字；无论现场使用 `Load_Breaker...`、`Circuit_Breaker...`、`RMU_LBS...`、`RMU_BRK...` 或其它名称，都只比较模板是否相同。
- Y1/Y2/Y3... 属于 Y 类：同一个 RMU 内所有 Y 类 CBreakerDis 的 devref 必须一致；Q1/Q2... 属于 Q 类，同理必须一致。
- 同时存在 Y/Q 时，两组 devref 模板必须不同；否则 devref 无法独立区分两类开关，报告为 `UNKNOWN/WARN`，不做关键字猜测。
- 元素 Y/Q 角色优先使用 CBreakerDis 自身的 `p_NameString`，缺失时才回退使用已支持的图上 Y/Q 文字定位。
- 有效 devref 类型继续与图内文字类型交叉校验；两者不一致时仍以有效 devref 类型为准。

## v4.1.20：严格 XML 解析与异常编码诊断

- 保留 RMU 名称候选对 `N.O.P` / `NOP` / `N-O-P` / `N_O_P` 等 Normally Open Point 状态文字的过滤。
- 撤销 v4.1.19 的 GB18030 自动回退与混合编码兼容解析；G 文件继续严格遵守 XML 自身的编码声明，不对异常文件自动猜测、转换或修复编码。
- 当 XML 解析失败时输出面向现场用户的详细诊断：文件名、XML 声明编码、解析器错误、行/列、附近原始字节/文本预览，以及“编码声明与实际字节不一致或存在非法 XML 字符”的修复建议。
- 回写逻辑恢复标准 UTF-8 文本处理；异常编码 G 文件必须先由源系统重新导出或人工修复后再进入模型校验/关联。

## v4.1.19：RMU N.O.P 过滤

- RMU 名称候选明确排除 `N.O.P` / `NOP` / `N-O-P` / `N_O_P` 等 Normally Open Point 状态文字，避免误当环网柜名称。
- v4.1.19 曾加入的异常编码兼容逻辑已在 v4.1.20 撤销。


## v4.1.18：SSH 文件服务器配置可显式保存

- SSH 文件源允许自定义 IP/主机、端口、用户名、密码和远程目录。
- 点击“保存 SSH 配置”后写入 Workspace 配置，下次启动自动回填最后一次保存值。
- 保存动作只写本地配置，不连接或修改 SSH 服务器；SSH 服务器仍严格只读。


## v4.1.17：RMU 名称未解析时用现有设备关联反推实际环网柜

- 环网柜名称未解析/解析异常时，RMU 汇总仍保留红色 `FAIL` 提醒，不把名称问题隐藏掉。
- 柜内已有 KeyID 继续按“数据库事实”检查，不再因为图上 RMU 名称为空而误报 `CURRENT_MODEL_RMU_MISMATCH`。
- 如果柜内所有可反查的已关联设备都指向同一个 `dms_combined_device`，报告明确写出实际环网柜 `ID` 和 `NAME`，并说明现有 RMU 归属关联一致；已有正确设备无需重新关联。
- 如果柜内所有设备都已有有效 KeyID 且均指向同一个数据库 RMU，说明中明确写“现有 RMU 归属关联一致且正确”，并提示检查图上环网柜名称是否应为该数据库 NAME。
- 如果同一图形环网柜内设备实际指向多个不同 combined_id，继续作为红色硬错误，禁止自动处理。
- 名称仍未可靠解析时，不开放自动新增/改绑；此规则只用于保护并解释已有正确关联。

## v4.1.16：RMU 名称未解析/解析异常作为红色硬错误

- RMU 环网柜名称为空、未解析到有效图内文字时，环网柜汇总明确标记为红色 `FAIL`。
- `RMU级关联阻断原因` 区分 `RMU_NAME_NOT_PARSED`、`RMU_NAME_RESOLUTION_ERROR`、数据库 0 条和数据库重名，不再用笼统的“环网柜ID无效”覆盖真实原因。
- 环网柜名称解析/核验出现异常时，不再让整个报告流程中断，而是将对应 RMU 记录为红色 `FAIL` 并记录异常详情。
- 名称身份未确定时，整柜及柜内设备均禁止进入自动关联流程。
- 名称未解析不会再被报告层误改写成 `RMU_NOT_FOUND_IN_DATABASE`。


## v4.1.15：CREATE_PENDING 使用独立橙色

- 馈线段需要新建数据库记录再关联时，报告状态类型仍为 `CREATE_PENDING`，但整行改用独立浅橙色显示。
- 绿色 PASS：已有正确关联。
- 黄色 WARN：数据库已有可用馈线段，可直接关联。
- 橙色 CREATE：当前馈线 13503 数量不足，需要先创建新的 `dms_section_device`，再生成 KeyID 并关联。
- 红色 FAIL：跨馈线、无法唯一确定目标等真正不可安全自动处理的错误。
- 仅改变报告视觉区分，不改变 v4.1.14 的“已有优先、剩余按数据库顺序、缺几条建几条”业务逻辑。


## v4.1.14：部分已关联图允许按数据库剩余记录顺序继续关联

- 既有关联仍只校验：13503 是否属于当前 FEEDER_ID，以及 Domain 是否正确；不检查 SEC/几何顺序。
- 已正确关联的 FeedLine 先锁定，不做任何重排或换段。
- 剩余未关联/旧 KeyID 失效的 FeedLine，允许使用当前馈线尚未占用的 13503 记录继续关联，不再因“多对多剩余”而 BLOCKED。
- 数据库剩余记录排序：NAME 中存在 `SECnnn` 时按 SEC 数字从小到大；历史非 SEC 名称按数据库 `id` 从小到大。
- G 侧只对“仍未关联”的 FeedLine 按现有图形顺序逐个接收下一条可用数据库记录；该顺序绝不用于校验或推翻已有关联。
- 若剩余数据库记录数量不足，先用完已有记录，再只对真实短缺数量生成 `CREATE_PENDING`；新建后继续关联剩余 FeedLine。


## v4.1.13：既有关联只校验馈线归属 + Domain，顺序仅用于全新图

- 已有关联 FeedLine：只要 KeyID 指向 13503、该记录属于当前 FEEDER_ID、Domain 正确，即 PASS。
- 不再校验数据库馈线段 NAME/CODE、SEC001/SEC002 后缀与 G 图上下/左右顺序。
- Domain 错误但仍是同一 feeder_id / 同一 13503 device_id：保持原 device_id，仅重写正确 KeyID。
- 只有当整张单馈线图的所有 FeedLine 都没有 KeyID 时，才允许按 G 图从上到下、同高度从左到右进行首次顺序分配。
- 部分已关联模型中，如多个未关联 FeedLine 对应多个剩余数据库馈线段，禁止按顺序猜测，报告为 BLOCKED；只有 1 对 1 唯一剩余时自动关联。
- 部分已关联模型若只剩 1 个未解析 FeedLine 且数据库已无剩余段，可仅创建 1 条缺失馈线段；名称取第一个未使用 SEC 后缀，不使用几何序号。


## v4.1.12：保留正确馈线段关联，不再按几何顺序强制重排 SEC

- 已关联 FeedLine 的数据库事实优先：13503 + 正确 Domain + 同 FEEDER_ID 即 PASS。
- G 图中 FeedLine 的上下/左右顺序不再用于推翻已有正确关联。
- SEC001/SEC002… 只用于真正缺少数据库馈线段时的新建命名。
- 未关联/失效关联仍先复用当前馈线未占用 13503，实际不足几条就只新建几条。



## v4.1.11：馈线段不足按短缺数量创建 + 失效旧KeyID安全重分配

- G 中 FeedLine 数量大于当前馈线 13503 数量时，先复用仍有效的同馈线数据库段。
- 当前 KeyID 指向已删除/不存在的 13503 记录时，作为可重分配旧关联处理，不再永久 FAIL。
- 当前馈线剩余数据库段不足时，只对实际短缺的 FeedLine 生成创建计划；执行时只新增短缺数量。
- 新建仍沿用 SECnnn、BV_ID、SECTION_TYPE 以及 D5000 ID 分配规则。
- 已存在且被校验选中的数据库馈线段在执行时按 device_id 精确保留，兼容历史非 SEC 命名。

## v4.1.10：馈线报告筛选 + Domain 错误安全重关联

- `馈线汇总`、`馈线段明细` HTML 报告新增独立模糊搜索框，行为与 RMU 报告一致：输入任意字符串后，对当前表整行做不区分大小写的包含匹配。
- 对 `current_table=13503`、当前数据库馈线段属于本 `FEEDER_ID`、但 `current_domain != 1` 的场景，不再作为不可修复 FAIL。
- Domain-only 错误改为显式 `RELINK`：保持原 `dms_section_device.id` 不变，只按 `DeviceID + (Domain << 32)` 重新生成正确 KeyID 并回写。
- 如果当前 13503 记录属于其它 feeder_id，仍保持硬错误，禁止跨馈线自动重关联。
- 未选择的 Domain 错误 FeedLine 仍会占用自己的数据库馈线段，防止其它 FeedLine 在执行阶段误抢该 section。

## v4.1.9：馈线图纸类型确认与根 facID 独立关联

馈线模块新增“图纸类型确认”：

```text
自动识别（默认，按 G 图拓扑）
强制单馈线图（本次文件/目录）
强制组合图（本次文件/目录）
```

`AUTO` 继续使用 G 文件电气拓扑判断单馈线/组合图；人工强制模式用于
现场已明确知道图纸类型时覆盖自动分型。报告同时保留“最终图纸类型、
图纸类型设置、自动拓扑识别、最终分型判据”，便于追溯。

安全边界：只有最终类型为 `SINGLE_FEEDER` 时，才能把一个唯一确定的
13500 `FEEDER_ID` 写入整张 G 的根 `facID`。最终类型为组合图时禁止
这种整图归属。

当根 `facID` 为空，并通过人工输入/文件名唯一确定馈线（例如 `AJWD 43`）时，
“G 根节点 facID”作为独立可选关联项，不受 Breaker、Busbar、FeedLine、
13503 馈线段校验状态影响。即使馈线段校验失败，只要单馈线类型和 13500
馈线事实已经确定，仍可只执行根 facID 关联；不会因此修改其它设备。

## 工作流

桌面端模型工作区统一为：

```text
模型校验
  -> 一次完成模型/数据库校验并生成可关联清单
  -> 用户在表格中勾选需要处理的 RMU 设备或 FeedLine
  -> 执行模型关联
  -> 只处理勾选对象
  -> 输出本次执行报告
```

不再提供单独的“模型关联预览”按钮。

执行关联不会重新扫描整张 G 图。程序使用当前模型校验生成的内存快照，
在写回前仅进行必要的文件指纹、数据库事实和目标分配复核，然后精确修改
Workspace 安全副本中的已选 XML 图元。


## RMU 设备业务字段

业务层不再使用 `p_name_string` 这个容易误解的名字。

统一使用：

```text
logical_code
```

含义是：

```text
图上规则得到的逻辑设备 CODE
→ 与数据库 CODE 比较
```

具体为：

```text
CBreakerDis
logical_code = 柜内图上开关文字

ZhaiWaiJieDiDaoZha
logical_code = 配对开关 logical_code + D

BusDis
logical_code = BUS
```

原始 XML 的 `p_NameString` 仅保留为解析层的
`xml_p_name_string`，不参与 RMU 设备命名和数据库匹配。

## 启动修复

v3.6.6 帮助页残留的 `policy_text / policy_layout / policy`
变量已清理，恢复为正确的 `naming_text / naming_layout / naming`。


## RMU 设备名称

开关名称来源已固定，不再提供模式选择：

```text
CBreakerDis
→ 只读取 RMU 内图上文字

ZhaiWaiJieDiDaoZha
→ 配对开关图上名称 + D

BusDis
→ BUS
```

XML `p_NameString` 不再作为设备名称来源。

图上逻辑名称必须与当前唯一 RMU 下数据库 CODE 唯一对应。识别失败、
CODE 不存在或 CODE 重复时，报告会指出具体 RMU 并提示检查命名方式。

## RMU 柜型

```text
规则一（图内文字）：
Y1/Y2/Y3/... → L
Q1/Q2/Q3/... → T

规则二（devref）：
Load_Breaker    → L
Circuit_Breaker → T

两套结果冲突：最终以 devref 为准
```

两套结果同时存在时必须交叉验证。冲突时采用 devref 结果，并输出 WARN，
并在 HTML / CSV / Console 中指出具体 RMU、文字柜型、devref 柜型及检查建议。


## RMU 柜型 / 智能属性

RMU 结构仍必须同时包含：

```text
CBreakerDis
ZhaiWaiJieDiDaoZha
BusDis
```

柜型规则：

```text
图内 Text/DText：
Y1,Y2,Y3,... -> L
Q1,Q2,Q3,... -> T

CBreakerDis.devref：
Load_Breaker    -> L
Circuit_Breaker -> T

两套结果独立计算；若不一致，最终采用 devref 类型，并输出 WARN。
```

智能 RMU：

```text
全局搜索 SMART / SMR
→ 每个标识归属最近 RMU
→ SMART 或 SMR 任意一个存在 = 智能
→ SMART + SMR 同时存在仍是一个智能 RMU
```

报告新增：

```text
HTML：环网柜档案
CSV：report_环网柜档案.csv
```

该 CSV 每个 RMU 一行，集中展示柜名、柜型、智能属性、数据库唯一性和设备完整性。


## v3.6.4 RMU 类型识别

RMU 结构识别完成后，程序自动识别柜型，例如 `2L1T`、`3L1T`。

双源规则：

```text
柜内 Text / DText：Y1/Y2/... -> L，Q1/Q2/... -> T
CBreakerDis.devref：Load_Breaker -> L，Circuit_Breaker -> T
两者不一致 -> 最终采用 devref 柜型，并输出 WARN
```

柜内 Y/Q 文字和 CBreakerDis.devref 分别独立计算柜型；两种来源结果不一致时，最终环网柜类型以 devref 为准，并在报告中显示交叉校验不一致。该差异用于图元模板检查，本身不阻断原有 RMU 关联逻辑。

RMU 汇总报告增加：环网柜类型、类型识别来源、图内文字类型、devref 类型、类型交叉校验。馈线模块中的可信 RMU 日志也显示柜型。


## 本版重点

RMU 识别增加结构硬条件：只有矩形框内同时至少包含 `CBreakerDis + ZhaiWaiJieDiDaoZha + BusDis` 三类图元时，才进入环网柜名称识别。RMU 模块和馈线模块共用该条件。

馈线模型校验完成后，工作区新增与 RMU 类似的“可关联馈线段选择”表格。`UNLINKED / RELINK / DUPLICATE_LINK` 中数据库事实唯一正确的 FeedLine 可以逐条勾选，执行模型关联只修改勾选的 XML 图元。

重复关联处理：如果多个 FeedLine 当前使用同一个 `dms_section_device`，所有重复行都显示 `DUPLICATE_LINK`。只勾选其中一条时，未勾选行保留当前数据库段，勾选行从其它剩余馈线段重新分配；多条同时勾选时一起重新参与分配。

馈线 HTML 的“馈线汇总”和“馈线段明细”继续保留人工标记复选框，勾选后整行持续高亮，不参与实际模型关联。


## 馈线模型：可信 RMU + FEEDER_ID + 连接拓扑

馈线模块不再使用图上馈线名称作为自动关联依据。

统一处理链路：

```text
G 图
→ 找 RMU
→ 过滤可信 RMU
→ 读取 dms_combined_device.FEEDER_ID
→ 建立 FeedLine / ConnectLine / Bus 连接拓扑
→ 检查同一连接区域所有可信 RMU 的 FEEDER_ID 是否一致
→ 查询该 FEEDER_ID 下真实 dms_section_device
→ 保留正确已有模型
→ 未关联/错误旧模型使用剩余 SECxxx 从小到大分配
→ Workspace 安全副本回写
```

### 可信 RMU

只有同时满足以下条件才参与馈线判断：

```text
RMU 名称数据库唯一 1 条
FEEDER_ID 有效
至少存在一个可验证的当前 KeyID
当前用于证明的模型属于该 RMU
表号/域号正确
不存在已关联到其它 RMU 的错误模型证据
```

未关联、数据库 0/多条、FEEDER_ID 为空或当前模型错误的 RMU 只报告，不作为参考。

### FEEDER_ID 冲突

同一个 G 拓扑连接区域：

```text
可信 RMU feeder_id 集合 = 空
→ BLOCKED / NO_TRUSTED_RMU_REFERENCE

可信 RMU feeder_id 集合 = {A}
→ 确认该区域 FEEDER_ID=A
→ 可以自动校验/关联 FeedLine

可信 RMU feeder_id 集合 = {A,B,...}
→ BLOCKED / FEEDER_RMU_CONFLICT
→ 禁止自动关联
→ 必须人工确认
```

程序不会使用多数投票。

### FeedLine 分配

确认 FEEDER_ID 后：

```text
SELECT ...
FROM dms_section_device
WHERE feeder_id = :feeder_id
```

使用数据库实际存在的 SEC 记录，不自行补号。

正确已有模型先占用；剩余数据库记录按 SEC 自然数字顺序排序；未关联和 RELINK FeedLine 按 G 图从上到下、同高度从左到右排序，然后依次匹配。

### HTML 人工标记

馈线汇总和馈线段明细最左侧都有复选框。勾选后整行保持蓝色高亮，方便横向滚动查看长报告。复选框只用于报告阅读，不影响程序模型关联。


## 多馈线组合图：先识别 G 标题，再用数据库确认

v3.5.0 的组合图识别存在一个关键顺序问题：

```text
旧逻辑：
G Text
→ 必须先在数据库唯一匹配
→ 才能成为馈线空间锚点
```

当数据库名称查询暂时无法唯一返回时，即使 G 图上已经清楚写着：

```text
ABH-03
ABH-04
ABH-05
...
```

也会错误退化成：

```text
AMBIGUOUS
识别馈线区域 = 1
```

v3.5.1 改为：

```text
G XML Text
→ 提取馈线标题
→ 建立空间锚点/区域
→ 再逐区域用数据库确认
→ 必要时再用已有 FeedLine KeyID 反向确认
```

因此数据库查询问题不会再把 G 图上已经存在的馈线标题“抹掉”。

### 组合图标题识别

支持：

```text
ABH-03
AJWD-07
ABH_08
BAY NO + ABH-17
```

其中真正的独立标题优先级最高。

### 已有关联 FeedLine 的第二确认

当标题直接查数据库失败时：

```text
FeedLine.keyid
→ device id
→ dms_section_device.feeder_id
→ dms_feeder_device
→ 当前区域馈线
```

只有一个区域内已有关联设备全部指向同一馈线时才允许作为确认依据。

### 你这张 ABH 大图

对本次上传的 G XML 直接解析得到：

```text
FeedLine = 398
原始馈线标题候选 = 50
清洗后的独立顶部锚点 = 47
```

程序能直接读到：

```text
ABH-03
ABH-04
ABH-05
...
ABH-48
ABH-49
```

另外源 G 图自身存在：

```text
ABH-26
ABH-26
```

两个独立的干净标题，而没有独立 `ABH-27` 标题。

程序不会擅自把第二个 ABH-26 猜成 ABH-27，而是把这两个区域标记为重复馈线标题，等待图纸/数据库事实确认。


## 馈线模型支持单馈线与多馈线组合大图

馈线模块现在支持：

```text
自动识别（推荐）
单馈线图
多馈线组合图
```

### 自动识别

程序读取 G XML，不使用 OCR：

```text
Bus + Text/DText + FeedLine
        ↓
识别 Bus 上方馈线名称候选
        ↓
Oracle dms_feeder_device 唯一确认
        ↓
1 个有效锚点 → SINGLE_FEEDER
2 个及以上有效锚点 → MULTI_FEEDER_COMPOSITE
```

组合大图中，长 Bus 下面可能对应多个被拼接的馈线，因此不再只取一个“最近 Text”。程序会保留长 Bus 上方范围内的多个馈线标题，并增加顶部标题带扫描，避免馈线标题刚好位于两个 Bus 段的拼接间隔时漏识别。

### 多馈线区域

已经数据库确认的馈线名称按 X 坐标排序：

```text
ABH-03        ABH-04        ABH-05
   |             |             |
   +------边界---+------边界---+
```

相邻馈线锚点中点作为区域边界，每个 `<FeedLine>` 先归属到一个馈线区域，然后在该区域内部独立执行原有数据库校验和关联逻辑。

### 已关联 FeedLine

```text
FeedLine 当前 KeyID
→ 反解 dms_section_device
→ 检查 13503 / Domain=1
→ 检查数据库 section.feeder_id
→ 必须属于当前图形馈线区域
```

因此组合图中已经关联的 FeedLine 也可以判断“数据库实际所属馈线”和“图上空间所属馈线”是否一致。

### 未关联 FeedLine

每个馈线区域独立执行：

```text
排除已被当前正确模型占用的 section
→ 数据库 section 按 SEC001/SEC002/... 自然排序
→ G FeedLine 从上到下、从左到右排序
→ 一一匹配
→ Expected KeyID
→ BV_ID -> voltype
```

### 连接关系

程序增加 FeedLine/ConnectLine 端点连接分量检查，但连接关系只作为一致性辅助，不会自动把两个空间馈线区域合并。原因是后续大图可能存在跨馈线连接线，空间拼接区域仍是主边界。

### 安全策略

同一数据库馈线如果在组合图中出现两个独立空间锚点，不会把同一套数据库馈线段重复分配两次，而是阻断这两个区域并要求检查图纸。

如果手工选择“多馈线组合图”，但程序无法唯一确认至少两个馈线名称，图纸状态为 `AMBIGUOUS`，禁止自动关联。


## RMU 执行模型关联改为“只处理勾选设备”

模型校验仍然负责一次完整分析：

```text
扫描 G 文件
→ 识别全部 RMU
→ 查询数据库
→ 校验 CODE / p_NameString / RMU 归属
→ 计算 Expected KeyID / BV_ID
→ 生成可关联设备表
```

用户在表格勾选设备后，点击：

```text
执行模型关联
```

现在不会重新扫描整张 G 图，也不会重新循环所有环网柜。

执行阶段变为：

```text
只读取已勾选 changes
→ 按选中 RMU 缓存数据库查询
→ 轻量确认当前数据库事实
→ 如设备 ID/BV_ID 已更新则刷新目标
→ 按 tag + XML ID 精确写 Workspace G 副本
→ 生成“本次模型关联执行报告”
```

### 执行阶段仍保留必要的数据安全确认

不会直接盲写模型校验时的旧缓存。

对每个选中设备，仅确认：

```text
RMU 当前仍唯一
CODE 当前仍在该 RMU 内唯一
CODE == 逻辑 p_NameString
设备 combined_id 仍属于该 RMU
BV_ID 当前有效
Expected KeyID 当前验证通过
```

如果设备删除后重新创建导致 ID 改变，但以上事实仍正确：

```text
自动刷新 Device ID
自动刷新 BV_ID
重新计算 Expected KeyID
继续关联
```

如果执行时数据库已经变成 0 条/多条等不唯一状态，只跳过该选中设备，不影响其它已选设备。

### 本次执行报告

执行结束后的 RMU HTML/CSV 不再输出整张图。

例如只选择：

```text
RMU 29802:
Y1
Y2
Q1
Y1D
Y2D
Q1D
```

报告中的“环网柜汇总”只有 `29802`，
“设备明细”也只有这 6 条本次选中的设备。

因此“模型校验报告”和“模型关联执行报告”职责彻底分开：

```text
模型校验报告 = 全局现状
模型关联执行报告 = 本次实际操作
```


## RMU 可关联设备表支持环网柜名称快速筛选

模型校验完成后的：

```text
可关联设备选择（模型校验结果）
```

现在新增：

```text
环网柜名称筛选
```

输入例如：

```text
17613
RMU-42646
42646
```

会实时只显示环网柜名称中包含该字符串的设备行。

筛选只改变表格显示，不改变：

```text
校验结果
是否可关联
复选框已选择状态
最终 write-back changes
```

清空筛选后恢复所有设备行。


## RMU 模型校验后手工选择关联设备

v3.3.0 在“数据库事实正确即可修复”的规则上增加一层明确的用户选择。

执行：

```text
RMU 环网柜模型
→ 模型校验
```

完成后，工作区直接展示：

```text
可关联设备选择（模型校验结果）
```

每个 G 文件设备图元一行。

### 哪些行可以勾选

只有 validator 已经确认：

```text
association_ready = YES
writeback_needed  = YES
```

才显示可操作复选框。

典型可选择状态：

```text
黄色 UNLINKED     当前未关联，但数据库目标唯一
橙色 RELINK       旧 ID / KeyID / Domain / Table 已过期或错误
紫色 RMU_RELINK   旧 KeyID 指向其它 RMU，但当前 RMU 已唯一确定正确目标
```

以下记录不可勾选：

```text
PASS       已经正确，不需要回写
FAIL       当前数据库事实不能安全确定目标
BLOCKED    RMU 级或其它整体阻断
```

### 用户可以只处理部分设备

默认一个都不勾选。

用户可以：

```text
只选 1 个设备
选同一个 RMU 的 2~3 个设备
选多个 RMU 中的部分设备
跨多个 G 文件选择设备
全选全部可关联设备
```

点击“执行模型关联”后：

```text
只过滤出已勾选 changes
→ 只复制包含这些设备的 G 文件到 Workspace/g_output
→ 只写这些设备
→ 原 G 文件不修改
→ 对安全副本重新执行完整模型校验
→ 输出最终 HTML / CSV 报告
```

复选框不参与任何业务判定。能否勾选仍完全由 RMU validator 的数据库唯一性、CODE/p_NameString、RMU 归属、Expected KeyID 和 BV_ID 规则决定。


## RMU 当前数据库事实优先 + 可重新关联

v3.2.0 将 RMU 关联判定统一为：

```text
当前数据库事实决定目标设备
旧 G KeyID 只决定是否需要修复
```

### 设备可以关联的核心条件

```text
环网柜名称在数据库唯一
        ↓
当前 G 设备得到逻辑 p_NameString
        ↓
只在该环网柜内部查 CODE
        ↓
CODE == p_NameString 且匹配数 = 1
        ↓
数据库目标设备 combined_id = 当前环网柜 ID
        ↓
Expected KeyID 有效
        ↓
需要写回时 BV_ID 有效
```

满足这些条件后，该 G 图元即可独立关联，不要求同一个 RMU 内其它所有设备都正常。

### 旧模型不再反向阻断正确数据库目标

以下情况现在都可以重新关联：

```text
未关联                       → 黄色 UNLINKED
旧设备 ID 已变化             → 橙色 RELINK
旧数据库设备被删除后重新创建   → 橙色 RELINK
旧 KeyID 已失效/无法反解       → 橙色 RELINK
旧 Table / Domain 错误         → 橙色 RELINK
旧 KeyID 指向其他环网柜        → 紫色 RMU_RELINK
```

只要当前数据库仍能在当前唯一 RMU 内通过 CODE/p_NameString 唯一找到正确设备，
程序就重新计算新的 Expected KeyID，并使用当前数据库设备 BV_ID 写入 `voltype`。

### 仍然属于红色硬错误

```text
RMU 数据库 0 条或多条
当前 RMU 内 CODE 0 条或多条
CODE != 逻辑 p_NameString
目标数据库设备不属于当前 RMU
Expected KeyID 无效
需要回写但 BV_ID 为空
```

### 报告防串行阅读

RMU 汇总和设备明细最左侧新增“选择”复选框。
勾选一行后整行保持蓝色高亮，横向滚动到 KeyID、Domain、BV_ID、说明等远端列时仍能确认当前阅读的是同一条记录。


## 模型工作区帮助与馈线配置界面调整

### 馈线配置页

馈线模块主页面现在只保留真正需要用户修改的参数：

```text
馈线段 dms_section_device
Table ID = 13503
Domain   = 1
```

`dms_feeder_device / 13500` 仍然是程序内部用于识别馈线的固定业务表，但不再作为用户配置项显示。

馈线表号和域号数字输入框与 RMU 使用完全相同的深绿色上下调节按钮。

### 当前模型帮助

模型工作区的【模型任务】区域新增：

```text
当前模型帮助
```

选择：

```text
RMU 环网柜模型
```

点击后显示 RMU 专属帮助，包括环网柜名称识别、设备名称规则、CODE/p_NameString 校验、已有模型反查、BV_ID/KeyID 回写规则。

选择：

```text
馈线模型
```

点击后显示馈线专属帮助，包括 Bus 附近名称识别、文件名回退、FeedLine 排序、已有模型检查、13503/Domain 1、BV_ID/KeyID 安全回写规则。

馈线主页面不再占用空间展示“馈线识别规则”和“FeedLine 关联规则”；这些说明统一放入当前模型帮助弹窗。

业务处理逻辑保持 v3.1.2 不变。


## 模型回写统一写入 BV_ID → voltype

从 v3.1.2 开始，所有自动模型关联回写都必须把数据库实际设备记录的 `BV_ID` 写入 G 图元的 `voltype`。

### RMU 设备

```text
CBreakerDis
ZhaiWaiJieDiDaoZha
BusDis
```

数据库匹配到目标设备后：

```text
voltype = 目标数据库设备.BV_ID
```

回写示例：

```xml
<CBreakerDis
    app="6500000"
    voltype="112871465660973067"
    p_ReportType="1"
    state="41"
    keyid="Expected KeyID"
/>
```

```xml
<ZhaiWaiJieDiDaoZha
    app="6500000"
    voltype="112871465660973067"
    p_ReportType="1"
    state="41"
    keyid="Expected KeyID"
/>
```

```xml
<BusDis
    app="6500000"
    voltype="112871465660973067"
    p_ReportType="1"
    state="15"
    keyid="Expected KeyID"
/>
```

RMU 设备明细报告中的 `BV_ID` 即为实际回写的 `voltype`。

### FeedLine

数据库目标记录来自：

```text
13503 / dms_section_device
```

回写：

```xml
<FeedLine
    app="6500000"
    p_ReportType="1"
    state="20"
    voltype="dms_section_device.BV_ID"
    keyid="Expected KeyID"
/>
```

例如数据库：

```text
ID    = 3800756610523988004
BV_ID = 112871465660973067
```

则程序回写：

```text
keyid   = 3800756614818955300
voltype = 112871465660973067
```

其中 KeyID 与 BV_ID 是两套独立字段，不能混用。

### 安全规则

如果准备自动关联的数据库设备 `BV_ID` 为空：

```text
当前设备 / 当前 FeedLine = FAIL
禁止自动回写
```

不会再生成 `voltype=""` 或 `voltype="0"` 的新模型关联。

其它 RMU / FeedLine 校验和关联规则保持 v3.1.1 不变。


## 模块切换界面修复

RMU 与馈线模型现在使用统一的动态配置容器尺寸规则：

```text
切换模型
→ 释放上一模块固定高度
→ 切换 QStackedWidget 当前页
→ 当前模块强制 Expanding
→ 按工作区真实宽度重新布局
→ 重新计算当前模块自然高度
→ 只由最外层工作区滚动条负责滚动
```

馈线配置页也调整为与 RMU 类似的完整横向布局：

```text
馈线识别规则        馈线段数据库表与域配置
------------------------------------------------
FeedLine 关联规则（整行）
```

这样 RMU ↔ 馈线来回切换时，不会再出现馈线模块只缩在左侧、旧模块高度残留或配置区域显示不完整的问题。

业务校验与关联规则保持 v3.1.0 不变。


## 新增：馈线模型校验与模型关联

v3.1.0 新增独立【馈线模型】模块。RMU 模块继续保持“不做馈线判断”，两套业务逻辑完全分开。

### 当前支持范围

```text
单馈线 G 文件
G 馈线入口：<Bus>
G 馈线段：<FeedLine>

馈线主表：
13500 / dms_feeder_device

馈线段表：
13503 / dms_section_device

馈线段 Domain：
1
```

### 馈线名称识别

第一优先级：

```text
扫描 <Bus>
→ 找到距离 Bus 最近的有效工程 Text
→ 例如 AJWD-07
```

第二优先级：

```text
Bus 周围无法识别
→ 从 G 文件名提取
→ 例如 JED-CTL-AJWD-07.sln.pic.g
→ AJWD-07
```

比较时统一标准化：

```text
AJWD-07
AJWD_07
AJWD 07
→ AJWD07

数据库：
JED CTL AJWD 07
→ JEDCTLAJWD07

AJWD07 包含于 JEDCTLAJWD07
→ 匹配
```

数据库匹配使用 `station.name + dms_feeder_device.name` 形成可读馈线名称，例如站名 `JED CTL AJWD` + 馈线名 `07` = `JED CTL AJWD 07`。标准化后必须唯一匹配一条馈线。

### FeedLine 已有关联

对于已经存在 KeyID 的 `<FeedLine>`：

```text
KeyID
→ 反解 device_id
→ 反解 table_id
→ 反解 domain
→ 查询 dms_section_device
→ 检查 feeder_id
```

必须满足：

```text
table_id = 13503
domain = 1
数据库馈线段 feeder_id = 当前识别出的 feeder_id
```

正确：

```text
PASS
保留原关联
不重复写回
```

错误：

```text
FAIL
只报告
不自动覆盖已有错误 KeyID
```

### FeedLine 未关联

先把已经正确关联的数据库馈线段视为“已占用”。

剩余数据库记录：

```text
按 NAME 中 SEC001、SEC002、SEC003... 自然递增排序
```

G 文件未关联 FeedLine：

```text
从上到下
再从左到右
```

依次一一分配。

所以如果中间只有几个 FeedLine 没有关联，程序会优先使用当前馈线中尚未被已有正确 KeyID 占用的数据库馈线段，再按照递增顺序补齐。

### Expected KeyID

```text
Expected KeyID
= dms_section_device.ID + (1 << 32)
```

并再次通过 Oracle：

```text
long2_to_long1
get_tab_no
get_col_no
```

验证必须得到：

```text
device_id = 目标馈线段 ID
table_id = 13503
domain = 1
```

### 安全回写

原始 G 文件永不修改。

执行关联时只修改 Workspace 中的安全副本：

```xml
<FeedLine
    app="6500000"
    p_ReportType="1"
    state="20"
    keyid="Expected KeyID"
/>
```

已有正确关联不重复写；已有错误关联不自动覆盖。

### 独立报告

馈线模块拥有独立报告：

```text
馈线汇总
馈线段明细
```

模型校验、关联预览、关联完成后都会生成独立 HTML / CSV。


## 关联粒度调整：设备错误不再拖累同一 RMU 的其它设备

RMU 唯一时，模型关联按设备逐条执行。

例如：

```text
RMU 17613 唯一

Y1  -> CODE唯一，CODE=p_NameString，属于17613 -> 可关联
Y2  -> CODE=0条                           -> 只阻断Y2
Q1  -> CODE唯一，CODE=p_NameString，属于17613 -> 可关联
BUS -> CODE唯一，CODE=p_NameString，属于17613 -> 可关联
```

最终关联预览只生成：

```text
Y1
Q1
BUS
```

不会因为 Y2 缺失而把整个 17613 跳过。

### RMU级阻断

只有以下情况阻断整个环网柜：

```text
RMU NAME 查询 0 条
RMU NAME 查询多条
RMU 名称无法可靠识别
```

### 设备级阻断

以下问题只阻断当前设备：

```text
CODE 0 条
CODE 多条
CODE != p_NameString
p_NameString 为空
设备不属于当前 RMU
Expected KeyID 错误
已有 KeyID 错误
已有 KeyID 属于其它 RMU
同一 p_NameString 被多个 G 图元使用
同一个数据库设备被多个 G 图元占用
```

报告中分别显示：

```text
RMU级关联阻断原因
设备级阻断原因
```

唯一 RMU 存在部分设备错误时：

```text
RMU状态 = WARN
RMU可关联 = YES
```

表示可以进行“部分设备关联”。

馈线判断仍然完全关闭。


## 不可违背的设备硬规则

每个 G 文件环网柜内的设备明细必须满足：

```text
逻辑 p_NameString
        ↓
数据库 CODE
        ↓
唯一匹配
        ↓
该数据库设备必须属于当前环网柜
```

具体规则：

1. `p_NameString` 不能为空。
2. 数据库 CODE 必须与逻辑 `p_NameString` 完全对应。
3. 同一个 CODE 在目标环网柜内必须唯一；0 条表示设备缺失，>1 条表示 CODE 重复。
4. 数据库设备的 `combined_id` 必须等于当前唯一 RMU 的 ID。
5. 同一个逻辑 `p_NameString` 不能被同一 RMU 内多个 G 图元重复使用。
6. 同一个数据库设备 ID 不能被同一 RMU 内多个 G 图元重复占用。
7. 数据库可以存在与当前 G 文件无关的额外设备；这些额外设备不参与校验。
8. 如果 G 文件需要的某个设备数据库中缺失，则该 G 设备直接 FAIL，并阻断该 RMU 自动关联。

## RMU NAME 不唯一时

RMU 汇总始终 FAIL。

如果 G 设备没有人工 KeyID：

```text
FAIL
禁止自动关联
```

如果已经有人为 KeyID：

```text
反解 KeyID
→ 找到实际数据库设备
→ 检查 CODE == 逻辑 p_NameString
→ 在实际 combined_id 内重新确认 CODE 唯一
→ 检查实际 RMU NAME
→ 检查本 G RMU 所有已关联设备是否来自同一个 combined_id
```

只要出现以下任一情况就报错：

```text
设备来自其他 RMU NAME
同名 RMU 但设备跨多个 combined_id
CODE 与 p_NameString 不一致
CODE 在实际 RMU 内不存在
CODE 在实际 RMU 内有多条
同一个数据库设备被多个 G 图元占用
```

## 馈线

馈线相关判断仍然完全关闭，不参与任何 PASS/WARN/FAIL 或自动关联条件。


## RMU 汇总字段精简

环网柜汇总报告中删除以下四个数据库字段：

```text
CODE
GRAPH_NAME
COMBINED_TYPE
RUN_STATE
```

这些字段不参与当前 RMU 模型校验和模型关联判断，因此不再出现在 HTML / CSV 的环网柜汇总中。

## 当前核心判断

RMU 模块只关注：

```text
1. G 图识别的环网柜名称
2. dms_combined_device 中该 NAME 是否唯一
3. G 设备逻辑 p_NameString
4. 对应数据库设备 CODE 是否唯一
5. CODE 是否与逻辑 p_NameString 对应
6. Expected KeyID
7. 已有关联 KeyID 实际属于哪个环网柜
```

不进行任何馈线判断。

## RMU 名称不唯一 + 已有人为 KeyID

如果数据库中同一个 RMU NAME 有多条记录：

- RMU 汇总仍然是 FAIL，因为 RMU NAME 本身不唯一。
- 未关联设备仍禁止自动关联。
- 已有关联 KeyID 的设备继续反解检查。
- 所有已关联设备必须实际来自同一个 `combined_id`。
- 即使这些数据库 RMU 的 NAME 相同，只要已关联设备分别来自多个不同 `combined_id`，就判定为模型关联错误。
- 如果当前 KeyID 实际属于其它 RMU NAME，同样判定为模型关联错误。

因此：

```text
同名 RMU A(ID=100)
同名 RMU B(ID=200)

Y1 -> ID=100
Y2 -> ID=200
```

即使两个 RMU 都叫相同名字，也会直接报错，因为同一个 G 图环网柜的设备不允许跨多个实际数据库环网柜。


## RMU 模块取消全部馈线判断

从 v3.0.24 开始，RMU 模块不再根据馈线进行任何校验或关联决策。

以下逻辑全部停用：

```text
G 文件名提取馈线
Bus 周围识别馈线名称
RMU feeder_id 比较
dms_feeder_device 查询
设备 feeder_id 比较
FEEDER_MISMATCH 状态
橙色 FEEDER 报警
```

RMU 校验与自动关联只关注：

```text
环网柜名称是否唯一
        ↓
G 图元逻辑 p_NameString
        ↓
数据库 CODE 是否唯一存在
        ↓
CODE == p_NameString
        ↓
Expected KeyID 是否正确
        ↓
已有 KeyID 是否属于当前环网柜
```

### 唯一 RMU + 未关联设备

```text
RMU 唯一
CODE 唯一
CODE == p_NameString
Expected KeyID 正确
→ 黄色 WARN
→ 可以自动关联
```

### 已有模型

已有 KeyID 时仍然反解：

```text
KeyID
→ 当前数据库设备
→ current combined_id
→ dms_combined_device
→ 当前模型实际所属 RMU
```

如果属于当前 RMU：

```text
PASS
模型已关联且正确
```

如果属于其它 RMU：

```text
RMU_LINK
硬错误
禁止自动覆盖
```

### RMU 0 条或多条

RMU 汇总仍然：

```text
红色 FAIL
```

如果设备未关联：

```text
禁止自动关联
```

如果设备已经人工关联：

```text
继续检查 CODE/p_NameString
继续反查实际所属 RMU
```

馈线不参与上述任何结果。

## BusDis

BusDis 当前配置保持：

```text
Table ID = 13506
Table = dms_bs_device
Domain = 1
```

Expected KeyID：

```text
DeviceID + (1 << 32)
```


## BusDis 默认域号修正

BusDis 的数据库模型信息修正为：

```text
G图元类型：BusDis
数据库表：dms_bs_device
Table ID：13506
Domain：1
```

因此 BusDis 的 Expected KeyID 计算为：

```text
KeyID = DeviceID + (1 << 32)
      = DeviceID + 4294967296
```

例如：

```text
DeviceID = 3801601035454119950

Expected KeyID
= 3801601035454119950 + 4294967296
= 3801601039749087246
```

本版本同时处理旧配置迁移：

```text
历史 workspace/config.json
BusDis / Table 13506 / Domain 0
            ↓
启动 v3.0.23
            ↓
自动迁移为 Domain 1
```

这样升级后不会因为旧配置仍保留 0 而继续计算错误的 KeyID。

## 状态颜色说明布局

HTML 报告中的“状态颜色说明”已从横向一行改成纵向列表，每个状态单独一行：

```text
绿色 PASS
黄色 WARN
橙色 FEEDER
紫色 RMU_LINK
蓝色 BLOCKED
红色 FAIL
```

状态名称和说明分列展示，便于阅读。


## RMU 名称按字符串处理

`dms_combined_device.NAME` 作为环网柜业务名称，全程按字符串处理。

支持例如：

```text
42646
RMU-42646
ABC_123
JED-RMU-01
RMU.42646
```

Oracle 查询改为：

```sql
SELECT *
FROM dms_combined_device
WHERE TRIM(name) = :rmu_name;
```

不再使用：

```sql
TRIM(TO_CHAR(name))
```

也不会把 RMU 名称转换成整数。

注意示例：

```text
RMU-42646
```

和：

```text
RUM-42646
```

是两个不同的字符串，程序采用精确名称匹配，不会自动纠正拼写。


## v3.0.21 关联阻断规则调整

本版本把“馈线告警”和“模型关联硬错误”分离。

### 硬错误 / 阻断

```text
RMU 查询结果 = 0 条
→ 环网柜汇总红色 FAIL

RMU 查询结果 > 1 条
→ 环网柜汇总红色 FAIL

RMU 0条/多条 + G设备未关联
→ 设备明细红色 FAIL
→ 禁止自动关联

G设备需要的 CODE 找不到
→ 红色 FAIL

CODE 与用于校验的 p_NameString 不一致
→ 红色 FAIL

同一 CODE 匹配多条数据库设备
→ 红色 FAIL

当前 KeyID 反解后的设备属于其它环网柜
→ 紫色 RMU_LINK
→ 硬错误
→ 禁止自动覆盖
```

### 馈线只告警

```text
G文件馈线 != 数据库环网柜馈线
数据库设备馈线 != G文件馈线
馈线ID为空 / 馈线查询失败
```

以上统一为橙色 `FEEDER`：

```text
只告警
不作为自动关联阻断理由
```

### RMU 有多条但已经人工关联

如果环网柜数据库名称不唯一，但 G 图元已经存在 KeyID：

```text
继续反解 KeyID
→ 读取当前数据库设备
→ 检查 CODE == 逻辑 p_NameString
→ 反查 current combined_id 对应 RMU
→ 检查实际 RMU NAME == 当前 G 图 RMU 名称
→ 同时展示馈线告警
```

结果：

- CODE 正确 + 所属环网柜名称正确：保留现有人工关联。
- 馈线不一致：橙色告警，但不把已有模型判为错误。
- 实际属于其它环网柜：紫色 RMU_LINK 硬错误。
- CODE 不一致：红色 FAIL。

RMU 汇总本身仍保持红色，因为数据库 RMU 名称仍然不唯一。


## 工作区任务按钮

模型工作区顶部不再使用“处理方式”下拉框。

所有实际动作统一放在页面底部：

```text
模型校验
模型关联预览
执行模型关联
数据库设置
```

这样用户点击的按钮名称就是实际执行的任务，不再出现“运行当前任务”但不知道当前任务是什么的问题。

## 报告按钮

报告入口根据“本次实际任务”动态显示：

```text
模型校验
→ 打开校验 HTML
→ 打开校验环网柜 CSV
→ 打开校验设备 CSV

模型关联预览
→ 打开预览 HTML
→ 打开预览环网柜 CSV
→ 打开预览设备 CSV

执行模型关联完成
→ 打开关联结果 HTML
→ 打开关联结果环网柜 CSV
→ 打开关联结果设备 CSV
```

如果某个任务没有生成对应文件，按钮自动隐藏，不显示无效入口。

Workspace 内目录按任务区分：

```text
<run>/
├─ validation_report/
├─ association_preview_report/
├─ g_output/
└─ association_result_report/
```

## 模型关联完成报告

执行模型关联后：

```text
关联预览
→ 用户确认
→ 原始 G 文件复制到 Workspace/g_output
→ 只修改 g_output 中的安全副本
→ 对修改后的安全副本重新执行完整模型校验
→ 生成最终 HTML / CSV
```

因此“关联完成报告”与普通“模型校验报告”使用同一套校验逻辑和字段。

最终报告反映的是**关联后的 G 文件安全副本**，而不是关联前状态。

## App 图标

图标资源已重新制作透明边缘：

- 保留原有绿色圆角线路图形。
- 外围方形深绿色底已透明化。
- PNG 和 Windows ICO 都重新生成。
- 标题栏和 EXE 图标显示时不再明显呈现一个方形色块。


## 环网柜汇总最终规则

环网柜汇总不再展开数据库重复 ID。

```text
一个 G 环网柜框 = 汇总一行
```

并严格按照：

```text
环网柜序号 1, 2, 3, 4, ... N
```

排序。

数据库查询结果：

```text
0 条
→ 红色 FAIL
→ 数据库未找到该环网柜

1 条
→ 正常
→ 显示唯一环网柜 ID

2 条或更多
→ 红色 FAIL
→ 只显示一行
→ 说明：数据库中找到 N 个同名环网柜，请检查数据库模型和单线图中的该环网柜
→ 不展开多个环网柜 ID
→ 禁止自动关联
```

## 环网柜汇总字段精简

保留原始核心定位字段：

```text
G文件
环网柜序号
矩形框XML ID
环网柜名称
```

不再增加：

```text
首个矩形框XML ID
G匹配框数
G环网柜序号
G矩形框XML IDs
数据库记录序号
```

## 设备明细

保持不变：

```text
以 G 文件实际设备图元为准
```

CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 在 G 文件中有几个，就检查和报告几个。


## RMU 名称最终选择规则

名称 Text 先经过“最近 RMU 归属”处理，同一个 Text 不允许被多个 RMU 共用。

随后：

```text
当前 RMU 在所选方向上的候选名称数量
        ↓

只有 1 个
→ 直接取这个名称
→ 不判断颜色

多个
→ 存在绿色名称
   → 取最近绿色名称

→ 不存在绿色名称
   → 取最近名称
```

示例：

```text
上方只有：
8723（白）
=> 8723
```

```text
上方有：
AK-900841（绿）
K-00018（橙）
G-1（白）
=> AK-900841
```

```text
上方有：
ABC（白）
DEF（白）
=> 取距离 RMU 最近的那个
```

绿色只负责“多个名字时消歧”，不再作为无条件最高优先级。


## v3.0.17：RMU 名称归属修复

修复远距离绿色名称可能被多个 RMU 框重复使用的问题。

新算法：

```text
Text
  ↓
先在用户选择方向上寻找所有可能的 RMU
  ↓
Text 只归属于距离最近的一个 RMU
  ↓
当前 RMU 只看“属于自己”的文字
  ↓
有绿色 → 最近绿色
无绿色 → 最近普通文字
```

因此同一个 `15953` Text 不会再同时被
`XML ID=2000120` 和 `XML ID=2000155` 使用。

对实际 JED-NTH-ABH-06 G 文件：

```text
2000120 -> 15953
2000155 -> 8723
```

## 报告数据源

```text
环网柜汇总：
    以 dms_combined_device 数据库记录为主
    一个数据库 RMU ID = 一行

设备明细：
    以 G 文件实际设备图元为主
    G 有几个设备图元 = 检查几个
```

如果同一个数据库 RMU ID 被多个 G 框匹配：

```text
RMU 汇总仍只有一行
+ G匹配框数
+ G环网柜序号
+ G矩形框XML IDs
```

数据库不存在的 G RMU 仍保留诊断行，以便报告
`RMU_NOT_FOUND_IN_DATABASE`。


## v3.0.16 修复

修复 v3.0.15 运行模型校验时报错：

```text
AttributeError:
'RmuValidator' object has no attribute '_make_expected_keyid'
```

KeyID 计算规则：

```text
KeyID = DeviceID + (Domain << 32)
```

即：

```text
KeyID = DeviceID + Domain × 4294967296
```

例如：

```text
DeviceID = 3800475135547315502
Domain   = 40

KeyID
= 3800475135547315502 + 40 × 4294967296
= 3800475307346007342
```

Domain=0 时：

```text
KeyID = DeviceID
```

本版本增加自动测试，确保 `RmuValidator` 内部所有
`self._xxx()` 调用都有实际的方法定义，避免此类错误再次出现。

## 关于 src/dmm

当前继续保留：

```text
src/dmm/
```

`dmm` 是 `Distribution Model Manager` 的 Python 包名，而不是另一个程序。
它用于隔离正式源码、稳定 import、PyInstaller 打包和测试。

对 Windows 用户而言仍然只需要：

```text
app.py
```

开发运行：

```powershell
python app.py
```

构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

---


## 1. RMU 名称：方向扫描 + 绿色名称优先

用户勾选“上方 / 下方 / 左侧 / 右侧”以后，程序沿该方向扫描名称。

新规则：

```text
扫描所选方向上的所有候选 Text
→ 如果存在绿色文字：
     只使用距离当前 RMU 最近的绿色文字
→ 如果没有绿色文字：
     回退原来的普通名称识别
```

绿色判断来自 G 文件 Text 图元：

```text
lc="0,255,0"
或
lcc="#00ff00"
```

名称读取：

```text
ts="AK-900841"
ts="AK-500252"
ts="AK-013190"
...
```

绿色文字不再受旧的 120 坐标单位搜索距离限制，因此允许名称与 RMU 距离较远。

非绿色文字仍保持距离限制，避免把整张图的其它普通文本当成 RMU 名称。

支持的 RMU 名称不再局限于纯数字，也支持：

```text
26772
AK-900841
AK-500252
AK_500252
```

## 2. 已关联 KeyID：反查实际所属环网柜

当前 G 图元已有 KeyID 时：

```text
KeyID
→ 反解设备 ID / 表号 / 域号
→ 查询设备
→ 得到设备 combined_id
→ combined_id 查询 dms_combined_device
→ 得到实际 RMU NAME
→ 和当前 G 图中的 RMU 名称比较
```

例如：

```text
当前 G 环网柜：26772
当前 KeyID 设备实际所属环网柜：26746
```

即使两个 RMU 都属于同一个馈线，也属于错误关联：

```text
状态：RMU_LINK
颜色：紫色
自动关联：禁止
```

设备明细增加：

```text
当前模型所属环网柜ID
当前模型所属环网柜名称
当前模型环网柜ID是否正确
当前模型环网柜名称是否正确
```

## 3. 状态颜色

- 绿色 PASS：正常
- 黄色 WARN：未关联但满足自动关联条件
- 橙色 FEEDER：馈线不一致
- 紫色 RMU_LINK：当前 KeyID 实际关联到了其他环网柜
- 蓝色 BLOCKED：人工关联检查通过，但 RMU 名称不唯一，禁止自动关联
- 红色 FAIL：硬错误

## 4. 数据库设备

仍然只检查 G 文件实际需要的：

```text
CODE = 最终用于校验的 p_NameString
```

数据库中其它无关设备全部忽略。


## v3.8.0 正式内部交付增强

### 执行前确认

模型关联前会显示：

- 本次勾选对象数量
- 涉及 G 文件数量
- 候选状态分布
- 原始 G 文件不修改的安全说明

### 模型修改记录

每次模型关联额外生成：

```text
association_result_report/model_change_log.csv
```

逐属性记录：

```text
源G文件
输出G文件
G图元类型
图元XML ID
属性
修改前
修改后
```

### 运行历史

左侧新增【运行历史】。每个 run 目录保存 `run_manifest.json`，可快速打开：

- 运行目录
- HTML 报告
- 模型修改记录 CSV

### 数据库访问

Oracle 数据库仅用于查询/校验；模型关联不会对 Oracle 数据库执行写操作。

### 发布检查

```powershell
powershell -ExecutionPolicy Bypass -File .\release_check.ps1
```

需要同时构建 EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\release_check.ps1 -BuildExe
```


## v3.9.0 SSH 只读文件源

模型工作区支持：

```text
本地文件 / 目录
SSH 文件服务器（只读）
```

默认远程目录：

```text
172.16.21.27:22
/home/up8000/data/graph/display/sln
```

SSH 模式的硬规则：

```text
刷新列表
    -> 只获取文件名 / 大小 / mtime

搜索 / 多选
    -> 只操作已加载的列表

模型校验
    -> 对当前勾选的每个 G 文件重新 stat
    -> 重新下载服务器当前最新版本
    -> 再次 stat
    -> 文件稳定后保存到 run/remote_input
    -> SHA256
    -> 模型校验

执行模型关联
    -> 禁止再次从服务器下载
    -> 使用本次校验 remote_input 快照
    -> 复制到 g_output
    -> 只修改 g_output
```

服务器端不提供任何上传、覆盖、删除、重命名或写入功能。

如果服务器上的同名 G 文件之后更新，需要重新执行【模型校验】。
新一次校验会重新下载服务器当时的最新版本。
### HTML report filtering

Searchable RMU and feeder HTML tables support both fuzzy text filtering and a single status-color filter. The two filters are combined, and the UI is localized for Simplified Chinese and English.


## v4.1.32 运行体验

模型关联和 G 文件安全回写在后台工作线程执行。任务进行期间进度条使用持续左右移动的 Busy 模式，精确对象数量通过状态文字与 Console 日志显示。该变更仅影响执行调度与界面反馈，不改变 RMU/馈线/Oracle/KeyID/回写业务规则。

## v4.1.33 Console-adjacent progress
The task progress panel is displayed inside the Current Run Console section, directly above the live Console output. Long association/write-back operations continue to use the indeterminate busy indicator from v4.1.32; exact object counts remain in the status text and Console log. This is a UI layout change only.


## v4.1.35 Task Progress title styling
The Console-adjacent Task Progress group keeps the v4.1.33 layout and v4.1.32 busy-progress behavior, but its title background now matches the white card so no pale-green title chip is visible. This is presentation-only.


## v4.1.36 Remote refresh fast path

`Refresh G File List` still performs one read-only SFTP directory listing so server-side changes can be detected safely. The returned list is compared by file name, size, and modification time. When unchanged, the existing GUI table is reused and the current validation/association view is not cleared. When changed, the remote table is populated in one batch with header auto-resizing disabled during insertion, followed by one content-width calculation.