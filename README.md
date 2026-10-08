# Distribution Model Manager - Jeddah v4.2.23

## v4.2.23 Full G-file before/after visual reports

- The before/after report diagrams are no longer simplified topology sketches. They redraw the complete source G using its original canvas, coordinates, XML order, line geometry, Text/DText, RMU frames, visible poke boxes, status icons, switch/ground/protection symbols, NOP images and drawing-frame content.
- White/yellow objects that were designed for a black runtime canvas are only remapped for readability on the report's white canvas; geometry and object placement remain source-authoritative.
- Every rendered SVG object carries the source G metadata in an SVG title tooltip (id/name/devref/key_name/link/node_area when present). External icon-library geometry is not embedded in business G files, so those GIcon objects use deterministic vector surrogates inside their exact source x/y/w/h/rotate footprint.
- The before view overlays numbered red/orange problem markers directly on the complete original G. The after view redraws the repaired complete G and overlays green repair markers, including a translucent highlight on modified line objects.
- Directory/SSH batch behavior from v4.2.22 is retained: one independent report set per G plus one total HTML/CSV summary, and one failed file does not stop the rest.
- Connectivity business rules remain unchanged: no feeder ownership, no NOP topology semantics, no Bus feeder-name lookup and no Oracle/model-database access.

## v4.2.20 Connectivity-only whole-graph topology repair

- Graphics Workspace now exposes **整图拓扑连接检查/修复** for Jeddah.
- This page no longer determines feeder ownership, recognizes NOP, reads the feeder name above Bus, or queries Oracle/model databases.
- It scans G-file line endpoints directly. Unique ConnectLine↔FeedLine gaps up to 25G are repaired by extending FeedLine orthogonally and adding reciprocal `link` / `node_area`.
- Tiny collinear ConnectLine↔ConnectLine splits are repaired only up to 3G. Larger symbol/open-switch gaps (commonly about 18G) are intentionally protected from auto-repair.
- Large feeder-propagation/RMU/NOP/SVG analysis is no longer run from this Jeddah page, so large G files are substantially faster.
- Source G files are never overwritten; the tool emits a validated `*.topology-fixed.sln.pic.g` plus compact HTML/CSV repair details.

## v4.2.18 Whole-graph feeder topology in Graphics Workspace (superseded on the Jeddah page)

- v4.2.18 originally added feeder/NOP-aware whole-graph analysis. v4.2.20 keeps the legacy engine in source for compatibility/regression coverage but the Jeddah page no longer calls it.

## v4.2.17 Jeddah graphics batch workflow cleanup

This release removes the former Jeddah graphics-batch step that forced every `<FeedLine>` to `ls=1`. FeedLine line style is now preserved exactly as it is in the input G file. All other Jeddah graphics-batch steps keep their v4.2.16 behavior, including the large-run performance optimizations.

## v4.2.16 Jeddah graphics batch performance

This release optimizes only the **Graphics Workspace → Jeddah Graphics Batch Processing** orchestration for large 100~300+ file runs. Standalone graphics modules keep their existing business logic. The batch now buffers high-volume UI logs, reuses RMU identification results within one unchanged XML state, combines the RMU-name presentation pass with the following in-memory visual pass, avoids redundant intermediate pretty-print/self-parse cycles, skips the redundant post-ID margin recheck, and records per-stage timings for field diagnosis. SSH remains read-only and remote snapshots are still downloaded/validated before processing.


## v4.2.15 one-click multi-model batch stability

This release changes only the one-click multi-model orchestration layer. Individual model association rules remain unchanged. Large SSH batches now prepare their stable snapshot in the worker thread; candidate filtering also runs in the worker; batch log pressure and candidate-table population are reduced; cumulative report paths are rebased so the final Feeder stage can reuse its validated topology report after earlier modules have generated staged G files; and final G publication shows per-file progress.


## v4.2.15 bilingual switch stability

- Simplified Chinese remains the canonical UI and is fully restored after switching from English.
- English-mode completeness from v4.2.13 is retained.
- Dynamic labels, status banners, model help cards, table states, and late-created pages can switch EN -> ZH -> EN without contaminating the source language.
- Business logic is unchanged.

# Distribution Model Manager - Jeddah v4.2.13

## v4.2.13 English UI full audit

- English mode is audited across Settings, Help, Element Management, Graphics Workspace, and Model Workspace.
- Dynamic Admin/status/cache text is retranslated after runtime refreshes instead of reverting to Chinese.
- Embedded GFileStudio runtime translation is active inside the unified application, including lazy dialogs/pages.
- Engineering data such as IDs, XML names, database values, file names, PASS/FAIL codes, KeyID and FEEDER_ID remain unchanged.
- Business logic is unchanged; this release is presentation/i18n hardening only.

## v4.2.11：图形工作区统一浅色选中高亮

## v4.2.12 图形工作区表格选中样式统一

- 图形工作区所有表格选中行统一使用浅绿色高亮，不再出现 Windows 默认深蓝色导致文字看不清。
- 覆盖馈线合并顺序、查询并导入 G 文件、主母线人工分组、SSH 文件列表、ID/图元相关表格以及后续懒加载弹窗。
- 仅调整 UI 展示，不改变任何图形处理或模型业务规则。


- 图形工作区所有表格的选中行统一使用浅绿色高亮和深色文字，避免 Windows 默认深蓝选中背景遮挡文件名、状态等内容。
- “查询并导入 G 文件”、馈线合并顺序、主母线人工分组、SSH G 文件列表、图元表、ID/图元升级表等统一视觉规则。
- 仅修改 UI 选中状态显示，不改变任何图形处理业务逻辑。


## v4.2.8 - English UI completeness

- Completed an English-mode audit of the merged Jeddah application after the DMM + GFileStudio integration.
- Added English translations for the shared-central-configuration Settings section, Safety Policy, Graphics Workspace, Element Management, multi-model association controls, and model logic section headings.
- The DMM language switch now propagates into every embedded GFileStudio graphics page, including pages created lazily after the switch.
- Embedded GFileStudio runtime translation can resolve the Graphics Workspace ancestor language manager, so dynamically updated graphics-page labels use the same language as the main application.
- Dynamic Admin/central-repository status text is rebuilt in the active language.
- No model recognition, Oracle query/write, SSH read-only, G-file write-back, feeder, RMU, or graphics-processing business rule was changed.

# Distribution Model Manager - Jeddah v4.2.7

## v4.2.7 失效历史路径静默清理

- 上次保存的输入/输出/最近浏览/模板导出目录已经不存在时，不再弹出“上次路径不存在”或“上次目录不存在”告警。
- 失效记录自动从本机设置中清除，并回退到当前模块默认目录或最近可用父目录。
- 特别解决旧 GFileStudio workspace/runs 目录被清理、程序移动盘符后启动被历史路径弹窗打断的问题。


## v4.2.6 馈线完整层级按 405 -> 404 -> 13500 显式解析

- 文件名解析规则保持不变：`JED-<AREA>-<STATION>-NN` 使用 `NN -> AH3NN`；`JED-<AREA>-<STATION>-AGNN` 使用 `AGNN -> AG4NN`。例如 `ABH-03 -> AH303`，`MDN-AG04 -> AG404`。
- 先用文件名站名精确唯一查询 `405/substation.NAME`，取得 `substation.ID` 与 `SUBAREA_ID`。
- 再用 `SUBAREA_ID -> 404/subcontrolarea.ID` 解析真实调控区域。若 `subcontrolarea.CODE` 为空，则自动使用 `NAME`（例如 `JED-CTL`）并与父级 `JED` 组装为 `JED CTL`。
- 最后仅在 `13500/dms_feeder_device.ST_ID = substation.ID` 范围内按文件名规则生成的 NAME 精确唯一锁定馈线。
- RMU HTML“文件名馈线概览”现在显示：G文件、调控区域、所属站/厂站、13500馈线NAME、数据库验证馈线全名；CSV 同步写入同一套数据库验证结果。
- 例如：`JED-CTL-ADF-34.sln.pic.g -> JED CTL / ADF / AH334 -> JED CTL ADF AH334`。
- 调控区域层级仅用于报告完善；若旧库缺失 404 层级数据，不会改变已唯一确认的 405 + 13500 馈线关联结果，报告退回 `厂站 + 馈线`。

## v4.2.5 RMU 报告写入数据库验证馈线全名

- RMU 文件名馈线仍严格按 `G 文件名 -> 405/substation -> 13500/dms_feeder_device` 唯一确认，不改变任何模型关联规则。
- 13500 唯一馈线确认后，使用数据库关系 `13500.ST_ID -> 405/substation.SUBAREA_ID -> subcontrolarea` 生成完整馈线路径。
- RMU 汇总、设备明细、失败明细以及 HTML 的“文件名馈线概览”优先显示完整数据库馈线名，例如 `JED CTL ADF AH334`。
- CSV 同时保留 `调控区域路径`、`厂站名称`、`13500馈线NAME`、`数据库验证馈线全名`、`图级馈线ID`，便于现场核对；中文界面仍同步输出 CN / EN 两份且业务数据一致。
- 当旧数据库接口没有完整层级字段时自动退回原有馈线 NAME（例如 `AH334`），不影响既有流程。

## v4.2.4 模型工作区 CSV 双语交付

中文界面下，模型工作区生成的每一种 CSV 都同时输出 CN 和 EN 两个版本。两个版本来自同一份校验/关联结果、行数与业务数据一致，仅列名和既有说明类文本按语言展示。批量模式、失败明细和模型修改记录同样遵守该规则。

## v4.2.3 统一中央仓库、Admin 与图元分类

- 一体化程序只使用一个中央配置根目录：`/home/up8000/nari-international/distribution-model-manager/config`。
- 图形工作区不再保留/继承独立 GFileStudio 中央目录；`id_rules.json` 与主程序 `instance.json`、`database.json`、`file_server.json`、`element_marks.json` 位于同一目录。
- 图形工作区复用主程序 `machine_id` 和当前 Admin epoch；主程序成为/失去 Admin 后，已打开及后续懒加载的 ID 页面会同步启用/禁用“发布到中央”。
- 图元分类仍以主程序“图元管理”保存的 `element_marks.json` 为唯一权威来源；模型工作区与图形工作区共享同一份分类。
- 旧独立 GFileStudio AppData 仅保留处理参数/缓存兼容，不再决定中央仓库路径或 Admin 身份。


> **一体化版本**：以 Jeddah Distribution Model Manager v4.1.111 为模型业务基线，内嵌 G File Studio v2.18.257 图形处理能力；Jazan v4.1.131 仅作为“模型工作区 + 图形工作区”集成形态参考。

## v4.2.2 图形工作区图元管理收口

- 删除图形工作区下拉框中的“服务器图元同步管理”；统一只使用主程序一级菜单“图元管理”。
- 主程序“图元管理”保存后，图元定义元数据与分类标记会本地桥接到图形处理引擎缓存；图形模块不再要求用户进入第二套图元同步页面。
- 吉达批处理、柱上变压器+熔断器、Poke、正交化等提示统一改为指向主程序“图元管理”。
- 修正图形工作区顶部“主程序图元管理 / 主程序数据库/连接”两个快捷按钮的页面索引。
- 服务器图元文件仍严格只读；桥接动作只转换本机已保存的图元目录信息，不自动访问 SSH。
- 验证：图形/集成专项 34 passed；完整回归 `447 passed / 1 skipped / 32 failed`，32 个历史失败与 v4.2.1 基线一致。

## v4.2.1 模型工作区整合

- “批量关联”不再作为独立一级菜单；已并入“模型工作区”的“模型类型”下拉框，名称为“一键多模型关联”。
- 一键模式和独立模型共用同一文件来源、Workspace、进度、Console 日志和报告入口；批量候选在模型工作区内统一确认。
- 业务规则仍由 RMU / 柱上开关 / 柱上变压器 / 熔断器 / 配网主站设备 / 馈线独立模块负责，一键模式只负责编排。

## v4.2.0 一体化入口

左侧新增 **图形工作区**。模型关联继续由原吉达 DMM 规则执行，图形处理在同一个程序内提供异常小图元、ID、RMU、Poke、通用处理、合并、边距、图框、线路正交化、吉达图形批处理、柱上变压器+熔断器替换、RMU EFI 添加等模块；服务器图元定义与分类统一由主程序“图元管理”维护。

- 原始 G 文件不覆盖；所有模型/图形操作仍输出到 Workspace/运行目录。
- 图形工作区延迟加载，启动阶段不自动连接 Oracle/SSH/中央仓库。
- 主程序的 Oracle、业务 G 文件 SSH、图元目录会投影到图形工作区本机缓存；图元分类标记也会本地桥接。
- 为避免配置格式冲突，v4.2.0 保留现有 GFileStudio 的图形专用 ID/服务器图元缓存与中央分类文件格式；后续可以在不改变业务规则的前提下继续收口配置存储。
- 现场批处理继续遵守“**只有实际修改过的 G 才输出**”的规则。

> 当前版本：v4.1.111。吉达 RMU 名称严格只识别环网柜矩形框完整外部、且位于矩形框正上方的 Text；Text 框与任意 RMU 框有几何重叠即排除，上方无有效名称直接 FAIL。

# 配网模型管理工具 / Distribution Model Manager v4.1.111




## v4.1.111：配网主站设备改为文件名直接确定馈线

- 主站模型不再通过附近 CBreaker、RMU 框、RMU 内已有 KeyID 或 13501.FEEDER_ID 反查所属馈线。
- 所属厂站/馈线统一走现有吉达文件名链路：文件名 → 405/substation.NAME → 13500/dms_feeder_device(ST_ID+NAME) → 唯一 FEEDER_ID。
- 普通两位编号仍为 `NN → AH3NN`；`AGNN` 仍为 `AG4NN`，例如 `JED-XXX-MDN-AG06.sln.pic.g → MDN / AG406`。
- 得到文件名馈线后，原主站逻辑继续：使用厂站与馈线名称/代码在 406/Bay 中定位唯一 BAY_ID，再按 BAY_ID 查询 407/408/409。
- 目标设备馈线归属校验、Disconnector 一对一排序、Domain、Expected KeyID、Preview/Apply、执行前重新校验和安全副本回写规则均保持不变。
- 专项测试 5 passed；完整回归 `438 passed / 1 skipped / 32 failed`，失败节点与 v4.1.110 完全一致。


## v4.1.110：吉达 AGNN 文件名馈线规则

- 在原有 `JED-<区域>-<站名>-NN.sln.pic.g` → `AH3NN` 规则基础上，新增 `AGNN` 文件名分支。
- `JED-XXX-MDN-AG06.sln.pic.g` 解析站名为 `MDN`，文件馈线 token 为 `AG06`，程序插入固定数字 `4` 后得到数据库馈线名 `AG406`。
- 查询链保持不变：`405/substation.NAME=MDN` 必须唯一 → 获取站 ID → `13500/dms_feeder_device.ST_ID=站ID AND NAME=AG406` 必须唯一 → 该记录 ID 即图级 `FEEDER_ID`。
- 原有两位编号文件名仍保持 `03 → AH303`、`16 → AH316`，没有改变。
- 数据库找不到目标 `AG4NN` 馈线时仍直接阻断，并提示“馈线不存在，请检查该图的馈线是否已创建”。


## v4.1.109：吉达 RMU 名称严格“框外 + 上方”

- RMU 名称候选必须是完整位于 RMU 矩形框外部的 Text；Text 矩形框与任意已识别 RMU 矩形框发生几何重叠时直接排除。
- 只允许目标 RMU 正上方 Text；Text 整体必须结束在 RMU 顶边之前/顶边处，右侧、左侧、下方、GLOBAL 全部禁止。
- 仍保持最大 200 G 单位、一对一 Text 归属、名称排除字符串和数据库/馈线安全校验。
- 上方没有符合“完整框外 + 正上方”的有效 Text 时，直接判定 `RMU_NAME_NOT_PARSED`，禁止该 RMU 自动关联。

## v4.1.108：吉达 RMU 名称固定为 TOP ONLY

- RMU 名称以识别出的 RMU 矩形框为唯一几何基准，只允许使用矩形框**上方**的框外 `Text`。
- 右侧、左侧、下方以及 `GLOBAL` 全局兜底全部禁用；上方找不到距离不超过 200 G 单位的有效名称时，直接 `RMU_NAME_NOT_PARSED / FAIL`。
- 柜内 Text 仍严格禁止作为任何 RMU 的名称；同一 Text 仍只允许分配给一个 RMU。
- RMU 模块、馈线侧共享 RMU 解析、拓扑辅助解析统一使用 TOP-only 规则。
- 其它 RMU 结构识别、文件名馈线、数据库精确匹配、柜内设备归属/馈线校验、KeyID 和安全回写规则不变。

## v4.1.107：吉达 RMU 名称改为框外 TOP → RIGHT → GLOBAL

- 环网柜结构识别仍以 RMU 矩形框为准：框内必须同时存在 `CBreakerDis + ZhaiWaiJieDiDaoZha + BusDis`。
- 环网柜名称只允许来自 **RMU 框外 Text**。Text 中心位于任意 RMU 框内时，直接排除，绝不会拿柜内设备文字当柜名，也不会借给旁边 RMU。
- 名称固定优先级：**上方 → 右侧 → 全局兜底**。当前 RMU 有上方候选时只取上方最近候选；没有上方才找右侧；两者都没有才在其它框外方向全局兜底。
- “全局兜底”仍受 RMU 名称最大距离 **200 G 单位**约束，并继续保持同一 Text 只归属最近的一个 RMU。
- 大字体 Text 的矩形可以轻微压到 RMU 边缘；只要 Text 中心仍在所有 RMU 框外，就可以按框外候选参与。
- RMU 名称排除字符串、数据库名称精确匹配、同图重名阻断、文件名确定 FEEDER_ID、RMU/柜内设备馈线硬校验均保持 v4.1.106 逻辑不变。
- 新规则专项 5 条；RMU 相关组合专项 18 passed；完整回归 421 passed / 1 skipped / 32 failed，失败节点与 v4.1.106 完全一致。


## v4.1.106：所有模型新增关联失败 CSV

- 在 v4.1.105 基线上新增统一失败导出：每次模型校验/关联生成原有 CSV 的同时，额外生成 `report_关联失败.csv`；英文模式生成 `report_association_failures.csv`。
- 失败 CSV 严格跟随 HTML 报告颜色规则，只收集报告中显示为红色的行，不把黄色 UNLINKED/WARN、橙色 RELINK/CREATE、蓝色 BLOCKED 等混入。
- RMU 模块同时收集【环网柜汇总】和【设备明细】中的红色行；馈线模块同时收集【馈线汇总】和【馈线段明细】中的红色行；柱上开关、柱上变压器、熔断器、配网主站设备分别收集自身明细中的红色行。
- 新 CSV 增加【报告分类】列，便于区分失败来源；原报告字段完整保留。即使当前没有红色失败，也仍会生成带表头的空失败 CSV，保证所有模型模块产物一致。
- `RMU_LINK` 等在 HTML 中按红色显示的历史硬错误状态也会进入失败 CSV，导出规则与页面颜色保持一致。
- 验证/关联运行产物中新增 `failure_csv` 路径，并在 Console 中输出失败 CSV 文件位置。
- 新增 v4.1.106 专项测试；完整回归 416 passed / 1 skipped / 32 failed，32 个失败节点与 v4.1.105 基线完全一致，无新增失败。


## v4.1.105：柱上变压器标准图元优先识别

- 柱上变压器设备类型识别第一优先级改为 G 图元 devref 精确指向 `Transformer_OH.pb.icn.g`；命中后直接认定为柱上变压器，不依赖图元管理分类。
- 未命中标准图元时，再使用【图元管理】中的 `TRANSFORMER_OH` 分类标记作为第二级兜底，可继续支持现场自定义/替代图元。
- 标准图元匹配为精确文件名匹配（大小写归一化），支持 devref 的目录路径与 `:root_id` 后缀，不做模糊包含。
- 柱上变压器后续名称识别规则保持不变：纯数字 + 白色 + 无背景，TOP → RIGHT → GLOBAL，矩形最小边缘距离 ≤300，Text 一对一。
- 数据库与馈线规则保持不变：图级馈线仍只由严格 JED 文件名确定，13505 / dms_tr_device 的目标设备 FEEDER_ID 必须等于图级 FEEDER_ID。
- 双 KeyID 校验、Preview/Apply、安全副本回写逻辑保持不变。
- 柱上变压器/FUSE 相关专项回归 45 passed；完整回归 407 passed / 1 skipped / 32 failed，32 个失败节点与 v4.1.104 基线完全一致。

## v4.1.104：RMU 设备 NAME 优先 + CODE 兜底，并强制馈线归属

- RMU 图级馈线对所有图统一由严格 G 文件名 → 405/substation → 13500/dms_feeder_device 唯一确定；不再只对单线图启用馈线约束。
- RMU 本身必须属于该文件名馈线；当前馈线下没有同名 RMU 或存在多条同名 RMU 时禁止关联。
- CBreakerDis：在“当前 RMU + 当前文件名 FEEDER_ID”范围内先按 `NAME=Y1/Y2/Y3/Q1/Q2/Q3...` 精确匹配；NAME 为 0 条时才使用同值 `CODE` 兜底；NAME/CODE 多条均阻断。
- ZhaiWaiJieDiDaoZha：与柜内开关保持原一对一空间配对；Y* 优先 `NAME=KY*`，Q* 优先 `NAME=KQ*`；NAME 为 0 条时继续使用原 `CODE=Y*D/Q*D` 兜底。
- BusDis 保持 `CODE=BUS` 原规则，但新增设备 FEEDER_ID 必须等于文件名馈线的硬校验。
- 柜内目标设备必须同时满足 `COMBINED_ID = 当前 RMU.ID` 且 `FEEDER_ID = 文件名确定的 FEEDER_ID`；任一不满足均禁止关联。
- 执行模型关联阶段同步采用同一 NAME→CODE 优先级和 RMU/FEEDER 双重归属复核，避免校验与实际写回规则不一致。
- 报告设备明细新增最终匹配字段、数据库设备 FEEDER_ID、文件名目标 FEEDER_ID，便于现场核对。
- 专项回归 33 passed；完整回归 402 passed / 1 skipped / 32 failed，失败节点与 v4.1.103 基线完全一致。

## v4.1.103：文件名馈线概览增加所属站

- 概览改为 `G文件 / 所属站 / 馈线` 三列。
- 例如 `JED-NTH-ABH-16.sln.pic.g | ABH | AH316`。
- 馈线不存在时仍显示文件名中的所属站，并提示检查该图馈线是否已创建。
- 不改变文件名唯一权威的馈线判定逻辑。


## v4.1.103：文件名馈线概览简化

- “文件名馈线概览”只保留 G 文件名与最终馈线结果。
- 数据库找到时直接显示：`数据库已找到，馈线：AH3xx`。
- 数据库未找到时直接显示：`数据库未找到馈线，请检查该图的馈线是否已创建。`
- 不再向现场用户展示馈线来源、405/13500 内部判定路径、FEEDER_ID 等实现细节。
- v4.1.101 的文件名唯一馈线判定、数据库只读查询和设备 FEEDER_ID 归属校验逻辑保持不变。

## v4.1.101：吉达馈线仅按文件名确定

- G 文件名是图级馈线唯一来源；严格支持两种格式：`JED-<三位区域代码>-<站名>-<两位馈线号>.sln.pic.g`（例如 `JED-NTH-ABH-03.sln.pic.g` → `AH303`），以及新增的 `JED-<三位区域代码>-<站名>-AG<两位馈线号>.sln.pic.g`（例如 `JED-XXX-MDN-AG06.sln.pic.g` → 站 `MDN`、馈线 `AG406`）。其它格式直接 FAIL，并提示用户先修改文件名。
- 从文件名取得站名 `ABH`，精确查询 `405 / substation.NAME=ABH`；必须恰好 1 条并取得 `405.ID`。
- 程序固定拼接 `AH3 + 两位编号`：`03 -> AH303`、`16 -> AH316`。
- 最终只按 `13500 / dms_feeder_device.ST_ID=<405.ID> AND NAME=AH3xx` 精确查询；恰好 1 条时，其 `13500.ID` 即本图唯一 `FEEDER_ID`。
- `13500` 中找不到目标馈线时直接阻断，并提示：**“馈线不存在，请检查该图的馈线是否已创建。”** 多条时按数据库馈线不唯一阻断。
- RMU、柱上开关、柱上变压器、G 根 `facID`、源侧 CBreaker、人工输入都不再参与馈线判定，也不能覆盖文件名确定的馈线。
- 后续所有设备关联都必须校验其数据库 `FEEDER_ID` 等于文件名确定的图级 `FEEDER_ID`；不属于该馈线的设备单独阻断。
- 报告中的“图级馈线概览”改为“文件名馈线概览”，不再用图中设备 FEEDER_ID 数量决定本图馈线。
- 数据库查询仍为只读 `SELECT`；现有 13503 缺失馈线段补齐与 Workspace 安全副本回写规则保持不变。

## v4.1.99：完整逻辑说明卡片统一背景

- RMU、柱上开关、柱上变压器、熔断器、配网主站设备、馈线六个模型页面的逻辑步骤卡片统一使用相同浅色背景、文字颜色和边框。
- 取消第 1 条逻辑说明的单独绿色强调背景；所有步骤属于同一说明层级，视觉保持一致。
- 继续保持 v4.1.98 的紧凑间距和自然高度，不恢复纵向拉伸。
- 仅修改 UI 样式与版本说明；识别、数据库查询、FEEDER_ID、KeyID、关联判断和 G 文件安全回写逻辑全部保持不变。

## v4.1.98：RMU 完整逻辑说明紧凑布局

- 右侧五个逻辑步骤卡片统一靠上连续排列，不再把工作区剩余高度平均分散到步骤之间。
- 逻辑说明外框按内容自然高度显示，并在左右布局中顶部对齐；多余纵向空间只留在列表底部。
- 仅修改 UI 布局；RMU 名称识别、柜内设备命名、数据库表/域、FEEDER_ID 校验、KeyID 判断和安全回写逻辑全部保持 v4.1.97。

## v4.1.97：设备名称识别统一为“矩形最小边缘距离”

- 统一距离定义：先计算两个矩形在 X/Y 方向不重叠部分的间距 `dx`、`dy`；若某一轴投影重叠，该轴间距为 0；最终距离为 `sqrt(dx² + dy²)`。水平相邻时自然等于 `dx`，垂直相邻时自然等于 `dy`，斜向时取两矩形最近边之间的欧氏距离。
- **彻底移除设备名称识别中的中心点距离**：长文字（例如 `LBS973248-972459`）不会再因为 Text 中心离设备很远而被误判；只要文字矩形最近边实际靠近设备，就按真实最小边缘距离参与识别。
- 统一覆盖：RMU 环网柜名称、RMU 柜内开关图上名称、柱上开关名称、柱上变压器名称、FUSE 继承的柱上变压器名称，以及馈线模块中 Bus/源侧设备附近的名称 Text 识别。
- 方向判定同样只依据矩形相对位置，不使用中心点向量；原有业务优先级和过滤规则保持不变。
- 原有阈值保持：RMU 名称 200、柱上开关 200、柱上变压器/FUSE 名称 300；馈线名称识别原有范围限制保持不变。
- FUSE → 最近 `TRANSFORMER_OH` 本身此前已经使用矩形到矩形的最短距离，本版继续保持。
- 仅改变“设备与名字 Text 的几何距离/方向判定”；数据库查询、FEEDER_ID、KeyID、安全回写和各模块其它业务规则保持原逻辑。

## v4.1.88：柱上变压器同样改为“分类标记唯一权威”

- 柱上变压器只认【图元管理】中的 `TRANSFORMER_OH` 分类标记，不再把 `TransformerDis` 当作设备类型限制。
- 被标记图元无论实际 XML 元素名称是什么，都进入原有柱上变压器名称、13505、馈线、双 KeyID 校验与回写流程。
- 写回使用识别到的真实 XML tag；FUSE 复用的最近柱上变压器链路也自动继承该规则。
- 原有名称规则保持不变：纯数字 + 白色 + 无背景、TOP → RIGHT → GLOBAL、最大距离 300、Text 一对一。


## v4.1.87：柱上开关识别改为“分类标记唯一权威”

- 柱上开关不再要求 G XML 元素必须是 `CBreakerDis`。
- 只要图元的 `devref` 在【图元管理】中对应的分类标记为 `LBS`、`SEC` 或 `AR`，该图元就作为柱上开关处理，XML 元素类型完全不参与过滤。
- 名称规则、200 距离、非白色显式颜色、TOP→RIGHT→GLOBAL、一对一 Text、数据库查询名前去点号/横杠/空格、13501→13502、馈线校验与回写字段全部保持不变。
- 回写时保留并使用该目标在 G 文件中的真实 XML tag，确保未来分类到其它元素类型时仍能准确修改对应图元。

## v4.1.86：模型页面改为“完整关联逻辑说明”

模型工作区不再展示“数据库表号 / 域号定义”表格，而是把每个独立模块实际执行的完整逻辑直接写在模块页面中：

- **RMU**：RMU 矩形框识别、上方名称、柜内 CBreakerDis / 接地刀闸 / BusDis / RMU_PWBH_EFI 命名与数据库校验、PASS/RELINK/RMU_RELINK 判断、各对象实际回写字段。
- **柱上开关**：LBS / SEC / AR 分类、非白色有颜色 Text、200 距离、TOP→RIGHT→GLOBAL、数据库查询前去 `. - 空格`、13501→13502、图级馈线校验、实际回写字段。
- **柱上变压器**：TRANSFORMER_OH、纯数字白色无背景 Text、中心点→Text 锚点 300、TOP→RIGHT→GLOBAL、13505、图级馈线、双槽位 keyid1/keyid2 回写。
- **FUSE**：最近 Transformer_OH 独占分配、复用柱上变压器名称、FUSE+变压器名称、13513 + 图级馈线、实际回写字段。
- **配网主站设备**：CBreaker 锚点→最近 RMU→框内已有 KeyID→13501→FEEDER_ID/BAY_ID→407/408/409，及 CBreaker / Disconnector / GroundDisconnector 的回写字段。
- **馈线**：RMU→柱上开关→柱上变压器首个唯一 FEEDER_ID、13500 确认、FeedLine/13503 分配、仅 INSERT 缺失馈线段、根 facID 与 FeedLine 回写。

本版**不修改任何独立模块业务实现**：`src/dmm/application/modules/*.py` 与 v4.1.85 文件哈希完全一致。模型页面仅从“数据库定义表格”改成“业务流程说明”，避免用户误以为固定工程规则是可调整参数。

本环境完整回归：345 passed / 1 skipped / 38 failed；v4.1.85 基线为 342 passed / 1 skipped / 38 failed，历史失败数量未增加。


## v4.1.85：配网主站设备数据库定义改为固定只读

配网主站设备模块不再允许用户编辑表号和域号，固定工程定义为：

- `CBreaker`：Table ID `407`，Domain `40`，数据库表 `breaker`
- `Disconnector`：Table ID `408`，Domain `30`，数据库表 `disconnector`
- `GroundDisconnector`：Table ID `409`，Domain `30`，数据库表 `grounddisconnector`

界面只读展示这些定义；旧版本缓存中过去保存的自定义值会在配置层被忽略。独立模块业务实现文件保持不变，识别、数据库查询、KeyID、安全写回等逻辑均未重写。

本环境完整回归：342 passed / 1 skipped / 38 failed；v4.1.84 基线为 338 passed / 1 skipped / 38 failed，失败节点完全一致。

## v4.1.84：RMU 数据库表号 / 域号改为固定工程定义

RMU 模型工作区右侧不再提供表号、域号编辑框，而是以只读说明展示固定工程映射：

- `CBreakerDis`：Table ID `13502`，Domain `40`
- `ZhaiWaiJieDiDaoZha`：Table ID `13514`，Domain `40`
- `BusDis`：Table ID `13506`，Domain `1`
- `RMU_PWBH_EFI / pwbh`：Table ID `13533`，Domain `40`，`dms_relay_sig.CODE=EFI INDICATOR`，回写 `value.keyid1`

这些值属于吉达项目固定模型规则，界面不可编辑；旧版本本地缓存里的自定义值也不会再参与运行。RMU 识别、数据库查询、KeyID、安全回写及其它独立模块业务代码保持不变。

本环境回归：338 passed / 1 skipped / 38 failed；v4.1.83 基线为 336 passed / 1 skipped / 38 failed，失败节点集合一致。

## v4.1.83：批量校验后增加待关联设备确认层

- 独立模块代码逻辑完全不改；批量功能仍只做外层调度。
- 批量校验完成后新增“待关联设备”列表，逐项展示模块、G 文件、XML ID、图上名称、数据库目标、状态和说明。
- 所有通过现有独立模块校验的安全对象默认勾选，用户可在真正写 G 文件前取消任意对象。
- 跨模块写回冲突对象继续显示，但在确认列表中禁用，不能进入批量写回。
- “执行批量关联”按钮会动态显示本次实际勾选数量；未勾选对象不会写回。
- 过滤动作只裁剪各模块已经生成的 `changes_by_file`，不复制、不重写、不修改 RMU / 柱上开关 / 柱上变压器 / FUSE / 配网主站设备 / 馈线的任何业务规则。

## v4.1.82：批量关联操作按钮视觉优化

批量关联页面的核心按钮改为独立操作面板：批量校验为轻量描边绿色按钮，执行批量关联为主品牌绿色按钮；增大点击区域并补充 Hover/Pressed/Disabled 状态。业务逻辑、执行顺序和安全写回规则均未改变。


## v4.1.81：批量关联页面直接管理完整文件来源

- 【批量关联】不再只显示“当前来源摘要”，而是直接提供与【模型工作区】相同风格的完整文件来源区域。
- 本地模式可直接在批量页面选择 G 文件或目录。
- SSH 只读模式可直接在批量页面配置 IP、端口、用户名、密码、远程目录，测试/保存连接，刷新、搜索、勾选和下载远程 G 文件。
- 两个页面共用同一套配置和远程文件选择状态，不会形成两套独立来源；批量校验仍锁定同一份最新稳定快照。
- 批量页面采用整页滚动，下面继续保留模块勾选、批量校验/关联、进度、Console 和汇总报告入口。


## v4.1.80：批量关联独立为左侧一级菜单

- 左侧新增【批量关联】一级菜单，批量功能不再占用模型工作区纵向空间。
- 【模型工作区】继续保留所有独立模型；【批量关联】只负责统一选择、调度、汇总和安全执行。
- 批量页显示当前本地/SSH 文件来源摘要，文件选择仍由模型工作区的公共文件源统一维护。
- 批量页拥有独立进度、Console 日志和批量汇总报告入口。


## v4.1.79：新增批量模型关联编排器，独立模块继续保留

- 新增批量模型关联编排器，可一次勾选一个或多个模块：RMU、柱上开关、柱上变压器、FUSE、配网主站设备、馈线。
- 独立模块不删除、不合并，仍用于专项校验、逐设备选择、排错和规则调试。批量功能只是统一调度现有模块。
- 批量校验锁定一份共同 G 文件快照；SSH 模式只下载一次，本次所有模块使用同一个 `remote_input`。
- 批量关联按 **RMU → 柱上开关 → 柱上变压器 → FUSE → 配网主站设备 → 馈线** 的顺序执行；后一个模块基于前一个模块写过的累计安全副本继续处理。
- 每个模块执行时仍运行自己的执行前数据库/文件复核；不会因为进入批量模式而绕过原来的安全规则。
- 执行前检查跨模块属性写回冲突；同一个 G 文件、同一个 XML、同一个属性若被两个模块计划写成不同值，则整批阻断。
- 成功后只在 `batch_g_output` 中发布每个原始 G 文件的一份累计结果；原始 G 文件永不修改。
- 批量模式会处理每个勾选模块本次校验得到的全部安全候选；如需只选部分设备，继续使用原来的独立模块。
- 批量校验和批量关联都会生成汇总 HTML/CSV；每个模块仍有自己的详细 HTML/CSV。

## v4.1.78：柱上开关名称改为“有颜色且非白色”

- 柱上开关名称 Text 必须显式设置颜色，且颜色不能是白色；不再限定为红色，也不再区分红色深浅。
- 红色、深红色、黄色、蓝色、绿色及其他显式非白色颜色都可参与候选；未设置颜色和白色 Text 继续排除。
- 几何识别保持：距离 ≤ 200、TOP → RIGHT → GLOBAL、同级最近、Text 一对一。
- 原有几何、Text 一对一及单位/注释过滤保持不变；本版只调整颜色门槛。
- 图上名称不改写；普通名称只在查询 13501 前删除 `. - 空格`，例如 `SEC-2385` → `SEC2385`。若分类为 AR/LBS/SEC 且名称严格为“设备族+数字-数字”的复合业务格式（如 `LBS96527-21240`），中间横杠保留并按原名查询。


## v4.1.77：恢复深红色柱上开关名称 + 明确“图上名称 / 数据库查询名称”

- 图上名称识别仍按原有规则：只认红色 Text、距离 ≤ 200、TOP → RIGHT → GLOBAL、Text 一对一。
- 吉达图纸中的 `170,0,0 / #aa0000` 属于红色，与 `255,0,0 / #ff0000` 一样允许作为柱上开关名称。
- `SEC-2385 / SEC 2385 / SEC.2385` 的去点号、横杠、空格只用于查询数据库，图上原名称不修改；`LBS96527-21240` 这类严格复合业务名属于例外，按原名查询。
- 报告把原始图上名称和数据库查询名称并排显示，并使用更直白的中文说明失败原因。

## v4.1.76：柱上开关数据库查询名称标准化 + 报告说明优化

- 柱上开关仍按现有图形规则识别：仅红色 Text、距离不超过 200、方向优先级 TOP → RIGHT → GLOBAL、Text 一对一。
- 在查询 13501 / dms_combined_device 前，仅对柱上开关数据库查询值做标准化：普通名称删除点号 `.`、横杠 `-` 和所有空白；若分类与名称前缀一致，且名称严格符合 `AR/ARC/LBS/SEC + 数字-数字` 的复合业务格式，则保留中间横杠。
  - `SEC-2385` → `SEC2385`
  - `SEC 2369` → `SEC2369`
  - `SEC.2270` → `SEC2270`
- 图上的原始名称仍原样保留在报告中；报告单独显示最终“数据库查询名称”，方便核对普通标准化名称与复合业务原名。
- 图级馈线判定中的柱上开关候选也使用相同标准化查询规则，避免模型校验与馈线识别不一致。
- HTML 报告“说明”改为更直白的中文描述；内部诊断码仍保留在程序数据/CSV中，便于排查。
- 13501 → 13502、FEEDER_ID、Domain=40、Expected KeyID 和 G 文件回写逻辑均未改变。

## v4.1.74：柱上开关名称只允许红色 Text

- 柱上开关名称 Text 现在 **只允许红色**；黄色、蓝色、绿色、橙色、白色、默认白色及其他颜色全部排除。
- 名称距离上限继续保持 **200**。
- 方向优先级继续保持 **TOP → RIGHT → GLOBAL**，同一级别按距离最近，Text 一对一。
- 13501 / 13502、FEEDER_ID、Domain=40、KeyID 与 G 文件回写逻辑不变。

## v4.1.73：柱上开关名称距离上限调整为 200

- 柱上开关模型的设备到名称 Text 最大距离由 **300** 调整为 **200**。
- 方向优先级仍为 **TOP → RIGHT → GLOBAL**；红色优先、其他非白色兜底、白色排除等现有颜色规则不变。
- 同一优先级内仍按现有距离算法选择最近候选，Text 一对一、13501/13502、馈线校验、KeyID 与 G 文件回写逻辑均不变。

## v4.1.72：FUSE 保留柱上变压器图形名称，数据库不唯一单独阻断

- FUSE 与柱上变压器模型统一采用同一份图形名称结果。
- 13505 匹配数不是 1 时，不再清空已经找到的柱上变压器名称；报告仍显示该名称、Text XML ID、方向、距离和 `FUSE+名称`。
- 13505 不唯一仍然禁止关联和回写，只是错误原因改为数据库不唯一，而不是“名称未找到”。





## v4.1.72：柱上开关名称增加固定颜色优先级

- 柱上开关名称 Text **禁止白色/默认白色**；未设置 `lc/lcc` 的 Text 按默认白色处理，因此不参与柱上开关名称判定。
- 名称颜色优先级固定为：**红色 RED → 其他非白色**。
- 在同一个颜色级别内继续保持 v4.1.70 的方向优先级：**TOP 上方 → RIGHT 右方 → GLOBAL 全局兜底**。
- 同一颜色、同一方向优先级内仍按距离最近选择；最大距离仍为 **300**，Text 一对一分配规则不变。
- 13501/13502、FEEDER_ID 校验、Domain=40、KeyID 与 G 文件回写逻辑均未修改。

## v4.1.70：柱上开关名称方向改为“上 → 右 → 全局”优先级

- 仅调整吉达**柱上开关模型**的名称方向选择顺序；仍只识别图元管理中分类标记为 `LBS / SEC / AR` 的 `CBreakerDis`。
- 名称候选仍从整张 G 图扫描，原有基础 Text 合法性规则保持不变；不新增纯数字、白色、无背景等柱上变压器专属过滤条件。
- 名称方向优先级固定为 **上方（TOP）→ 右方（RIGHT）→ 全局兜底（GLOBAL）**；只要存在可分配的 TOP 候选，就不会选择 RIGHT/GLOBAL；无 TOP 时才进入 RIGHT；两者都没有才使用其他方向。
- 柱上开关原有最大名称距离 **300**、现有距离计算方式、同一优先级内距离最近、一对一 Text 独占规则保持不变；多个柱上开关争用同一 Text 时仍由物理距离更近的设备获得。
- 13501/13502 数据库链路、图级馈线识别与 FEEDER_ID 校验、Domain=40、Expected KeyID 与 G 文件安全回写逻辑全部不变。

## v4.1.69：柱上变压器名称方向改为“中心点 → Text 锚点”判定，距离上限 300

- 吉达柱上变压器仍全局识别图元管理中分类为 `Transformer_OH` 的全部图元；名称候选仍严格限制为**纯数字 + 白色 + 无背景 Text**。
- 名称优先级仍为 **上方 → 右方 → 全局兜底**，但方向不再使用 Text 外接框中心判断，改为使用 `TransformerDis` 中心点 → `Text.x/Text.y` 锚点的向量主方向。
- 同一方向优先级内仍按 `TransformerDis` 中心点 → `Text.x/Text.y` 锚点的欧氏距离最近；名称最大距离由 **200 调整为 300**。
- 现场 `JED-STH-ADEL-19.sln.pic.g` 回归：`115001120` 中心 `(2582, 4243)`，名称 `96757` 锚点 `(2636, 4239)`，`dx=+54 / dy=-4`，因此方向应为 **RIGHT**，距离约 `54.148`，不应再显示为 bottom/GLOBAL。
- FUSE 仍先锁定自身最近的 `Transformer_OH`，随后复用上述柱上变压器名称规则，因此 FUSE→Transformer 分配、13505/13513、馈线校验、Domain、KeyID 与安全回写逻辑均不变。


## v4.1.68：FUSE 跟随柱上变压器“上 → 右 → 全局”名称规则

- 熔断器模型仍然**先找几何位置最近的 `Transformer_OH`**，这一层设备选择规则不变。
- 多个 FUSE 争用同一最近柱上变压器时，仍由距离更近的 FUSE 获得；其他 FUSE 只统计、不关联，也不回退到第二近变压器。
- 锁定最近柱上变压器以后，该变压器名称不再使用 v4.1.65 的“任意方向最近白色 Text”兼容规则，而是与吉达柱上变压器模型完全一致：全图候选必须为**纯数字 + 白色 + 无背景 Text**，方向优先级固定为 **上方 → 右方 → 全局兜底**。
- 同一优先级内继续按 `TransformerDis` 中心点到 `Text.x/Text.y` 锚点距离最近，最大距离仍为 200；Transformer_OH 之间的 Text 一对一独占规则保持不变。
- 图形阶段选定柱上变压器名称后，只校验该名称在 `13505 / dms_tr_device` 是否唯一；不会因为数据库不唯一再切换到另一条 Text，避免 FUSE 与柱上变压器模型对同一变压器给出不同名称。
- 熔断器最终仍按 `FUSE + 柱上变压器名称` 查询 `13513 / dms_disconnector_device`，图级 FEEDER_ID 校验、Domain=40、KeyID 计算与安全回写逻辑不变。


## v4.1.67：吉达柱上变压器名称增加“上 → 右 → 全局”优先级

- 仅调整“柱上变压器模型”自身的名称识别；全图继续识别所有图元管理中分类为 `Transformer_OH` 的图元。
- 名称候选改为严格的 **纯数字 + 白色 + 无背景 Text**，候选 Text 仍从整张 G 图全局扫描。
- 名称方向优先级固定为：**上方 → 右方 → 全局兜底**。只要有可分配的上方候选，就不使用右方或其他方向；没有上方候选才找右方；两者都没有才使用其余方向。
- 同一优先级内继续按 `TransformerDis` 中心点到 `Text.x/Text.y` 锚点的距离从近到远，最大距离仍为 200；Text 一对一独占规则保持不变。
- 13505 唯一匹配、FEEDER_ID 校验、双 KeyID 计算与安全回写逻辑不变。
- FUSE 保持 v4.1.65/v4.1.66 的既有逻辑，不套用此次柱上变压器“上/右”方向优先级，因此 `117000344 -> 115000015 -> 971765 -> FUSE971765` 的修复不会回退。

## v4.1.66：新增 `setup.ps1` 一键环境初始化脚本

- 项目根目录新增 `setup.ps1`，用于 Windows PowerShell 一键准备运行环境。
- 运行 `./setup.ps1` 或 `.\setup.ps1`：自动检测 Python 3.11+、创建 `.venv`、升级 pip/setuptools/wheel、安装 `requirements.txt` 并校验核心依赖；完成后默认启动 `app.py`。
- 仅安装/更新环境、不启动程序：`.\setup.ps1 -NoRun`。
- 如果 PowerShell 执行策略阻止脚本，可使用：`powershell -ExecutionPolicy Bypass -File .\setup.ps1 -NoRun`。
- 此版本不改变模型识别、数据库匹配、KeyID、G 文件写回或报告业务逻辑。

## v4.1.65：FUSE 柱上变压器名称改为“变压器中心 → Text 锚点”

- FUSE 仍先锁定自身几何位置最近的 `Transformer_OH`，这一层设备选择逻辑不变。
- 锁定柱上变压器后，不再用 Text 外接矩形边缘计算名称距离；改为以该 `TransformerDis` GIcon **中心点**为基准，计算到 `Text.x/Text.y` **锚点**的欧氏距离。
- 候选仍只允许白色 Text、任意方向、最大距离 200，并按距离从近到远做 `13505 / dms_tr_device` 唯一匹配；首个唯一匹配名称就是该柱上变压器名称。
- 熔断器名称仍严格为 `FUSE + 柱上变压器名称`。现场 `JED-STH-ADEL-04.sln.pic.g` 中，FUSE `117000344` 最近柱上变压器为 `115000015`，其名称应识别为 `971765`，因此熔断器名称为 `FUSE971765`；不再错误取相邻变压器的 `971488`。
- FUSE 明细报告增加“变压器名称距离基准”，用于明确审计 `TRANSFORMER_CENTER_TO_TEXT_XY_ANCHOR`。

## v4.1.64：HTML 报告勾选行统一蓝色高亮

- 所有带复选框的 HTML 报告在勾选后都会把整行切换为浅蓝色，并显示蓝色边框，便于横向核对长表格。
- 取消勾选后恢复该行原来的 PASS / WARN / RELINK / BLOCKED / FAIL 等状态颜色。
- 文字筛选和颜色筛选只控制行的显示/隐藏，不会清除已经勾选的状态；重新显示后仍保持蓝色高亮。
- 覆盖环网柜、馈线、柱上开关、柱上变压器、熔断器、配网主站设备 HTML 报告。
- 不修改模型识别、数据库匹配、馈线判定、KeyID 计算或 G 文件回写逻辑。

## v4.1.63：HTML 报告筛选运行脚本修复

- 修复柱上变压器 HTML 报告的颜色筛选和文字筛选下拉/输入框只有界面、没有实际执行脚本的问题。
- 同步补齐柱上开关、熔断器、配网主站设备报告的表格筛选脚本，避免相同问题。
- 不修改任何模型识别、数据库匹配、馈线判断或 G 文件回写逻辑。


## v4.1.62：柱上变压器 KeyID 回写强制复核

- 柱上变压器执行关联后，立即从输出 G 文件重新读取 `keyid1/keyid2` 并逐个核对 Expected KeyID；缺失或不一致直接报错，不再出现“界面显示执行完成但 G 中没有 KeyID”的静默状态。
- Console 明确输出每个 TransformerDis XML ID、Expected KeyID、输出 G 路径及回读确认结果。
- 柱上变压器写回结果纳入 `model_change_log.csv`，可直接检查 `keyid1/keyid2` 的修改前后值。
- 柱上变压器名称识别、FUSE、RMU、柱上开关、馈线等其他业务逻辑不变。



## v4.1.61：Release 包名称加入 Jeddah

- `build_exe.ps1` 最终生成的 release ZIP 改为：`Distribution_Model_Manager_Jeddah_v<版本号>.zip`。
- 本版实际输出示例：`release\Distribution_Model_Manager_Jeddah_v4.1.61.zip`。
- EXE 与 dist 目录仍保持 `Distribution_Model_Manager_v4.1.61`，仅最终交付 ZIP 增加 Jeddah 标识。
- 业务功能不变。


## v4.1.60：柱上变压器名称距离改为中心点到 Text 锚点

- 仅修改“柱上变压器模型”自身的名称分配流程；FUSE、图级馈线识别及其他模型保持 v4.1.59 逻辑不变。
- 柱上变压器仍先全图收集 `Transformer_OH`，并只使用白色 Text；方向不限，最大距离仍为 200。
- 名称距离改为：`TransformerDis GIcon 中心点 -> Text.x/Text.y 锚点` 的欧氏距离，不再使用 Text 外接矩形最近边缘，避免长文字框向相邻设备延伸导致抢名。
- 候选仍按全局距离做一对一最近分配：一个 Transformer 只分配一个 Text，一个 Text 只归属一个 Transformer；图形名称确定后才查询 13505。
- 使用现场 `JED-CTL-AJWD-30.sln.pic.g` 验证：`115000667 -> 991890`、`115000672 -> 99969`、`115000814 -> 99964`、`115000820 -> 99963`。


## v4.1.59：柱上变压器模型恢复纯图形全局最近名称分配

- 仅修改“柱上变压器模型”自身的名称分配流程；FUSE、图级馈线识别等其他模块逻辑保持 v4.1.58 不变。
- 先收集整张 G 图内全部 `Transformer_OH` 柱上变压器，再收集任意方向、距离不超过 200 的白色 Text。
- 在所有柱上变压器与候选白色 Text 之间按几何距离做全局一对一最近分配：一个变压器只取一个 Text，一个 Text 只归属一个变压器。
- 名称归属阶段不查询 13505；图形名称固定后，才进入 13505 唯一性、FEEDER_ID 和 KeyID 校验。


## v4.1.58：柱上变压器名称改为全局任意方向 + 白色 Text

- 柱上变压器仍只识别图元管理中分类为 **`Transformer_OH`** 的 `TransformerDis`。
- 名称查找不再限制上方/右方，而是在**整张 G 图任意方向**扫描 Text；原有最大距离 **200** 保持不变。
- 只有**白色 Text**可以作为柱上变压器名称候选；红色、绿色、黄色等非白色文字直接排除。G 文件未显式设置文字颜色时按默认白色处理。
- 候选仍按几何距离从近到远尝试，并通过 `13505 / dms_tr_device` 唯一匹配确认名称；同一 Text 仍不能被多个目标柱上变压器重复使用。
- 图级馈线识别中的“柱上变压器兜底”与 FUSE 模块复用同一套新规则，因此三处不会出现名称判断差异。
- `FUSE -> 最近 Transformer_OH -> 变压器名称 -> FUSE+名称` 的链路不变，只是其中的“变压器名称”改为任意方向、200 距离、白色 Text。

## v4.1.57：RMU 保护/EFI 改为图元分类标记驱动

- RMU 内保护/EFI 信号不再绑定任何具体图元文件名；识别依据固定为图元管理中的分类标记 **`RMU_PWBH_EFI`**。
- 程序读取本地缓存的 `element_catalog`，检查所有被标记为 `RMU_PWBH_EFI` 的图元定义；同一分类标记可以对应多个图元文件，只要 G 对象的 devref 精确匹配其中任意一个就作为 EFI 信号处理。
- 后续即使服务器上的 EFI 图元文件改名，只要图元管理同步/保存后的对应记录仍标记为 `RMU_PWBH_EFI`，RMU 关联逻辑无需改代码。
- 未带 `RMU_PWBH_EFI` 分类标记的 `pwbh` 图元即使文件名历史上叫 `NariPd_Normal` 也不会被当作 RMU EFI；反过来，新文件名只要被正确分类就能参与。
- EFI 后续数据库规则不变：按当前 RMU 查询 `13533 / dms_relay_sig`，只接受唯一 `CODE=EFI INDICATOR`，默认 Domain=40，回写仍使用 `keyid1`。
- `ALL / SMART_ONLY` 保护策略、SMART_ONLY 下非智能 RMU 已关联 EFI 的清理逻辑、属性键保留规则均保持不变。


## v4.1.56：RMU 名称固定上方 + SMART-only 保护/EFI策略

- RMU 环网柜名称在吉达现场固定只从**矩形框上方**寻找，最大距离仍为 200；右侧、左侧、下方不再作为 RMU 名称候选。
- 新增“保护 / EFI 关联范围”选项：
  - **所有环网柜都关联保护 / EFI**：保持原行为。
  - **仅 SMART 智能环网柜关联保护 / EFI**：只有 SMART/SMR 环网柜关联 `NariPd_Normal / EFI INDICATOR`。
- 选择“仅 SMART”后，NORMAL 环网柜如果已有 EFI 模型关联，会作为强制策略清理项执行：保留属性键，只清空关联值；`p_ReportType1` 回到 `0`。
- NORMAL 环网柜若本来就没有 EFI 关联，只统计、不回写，也不会因为策略禁用而被判定为设备缺失。
- 强制清理不会删除任何 XML 属性键；已存在的 `voltype1` 只将值清空。
- 保护策略只影响当前固定 EFI 信号，不改变 CBreakerDis、接地刀闸、BusDis 的既有 RMU 关联规则。


## v4.1.55：熔断器与柱上变压器改为一对一独占匹配

- 每个 `FUSE` 只提名**几何位置最近的一个** `Transformer_OH` 柱上变压器。
- 同一个柱上变压器只能被一个 FUSE 使用；如果多个 FUSE 的最近变压器是同一台，则按 FUSE→变压器距离比较，由距离更近的 FUSE 获得该变压器。
- 竞争失败的 FUSE **不再寻找第二近变压器**，仅进入报告和统计，`association_ready=NO`、`writeback_needed=NO`，不会查询 13513、不会进入关联选择、不会回写 G 文件。
- 只有成功独占分配柱上变压器的 FUSE 才继续名称链路：`FUSE -> 已分配 Transformer_OH -> 以该变压器为中心查上方/右方 Text -> 首个 13505 唯一名称 -> FUSE+名称`。
- 柱上变压器名称仍完全复用柱上变压器模块规则：方向只允许上方/右方，距离不超过 200，并使用共享 Text 所有权，避免同一名称 Text 被多个已分配 FUSE 重复消费。
- 熔断器报告新增“一对一分配统计”，明确展示 FUSE 总数、成功分配柱上变压器数量、仅统计不处理数量和数据库可关联数量；明细增加分配状态、占用 FUSE XML ID 等字段。
- 使用现场 `JED-STH-ADEL-06.sln.pic.g` 几何数据回归验证：24 个 FUSE、22 个 Transformer_OH，最终 22 个独占匹配、2 个仅统计不处理；重复争用的远端 FUSE 不再错误复用已占用变压器。

## v4.1.54：修正熔断器 → 柱上变压器 → 名称链路

- 熔断器识别顺序固定为：**FUSE 分类标记 → 最近 Transformer_OH 柱上变压器设备 → 以该柱上变压器为中心查名称 → FUSE + 柱上变压器名称**。
- 找到最近柱上变压器以后，FUSE 不再围绕自身寻找 Text，也不会因为名称候选失败而改找另一台变压器。
- 柱上变压器名称仍严格只看**上方或右侧**、距离不超过 **200** 的 Text；不恢复名称格式、颜色或背景过滤。
- 对这些几何合法候选按距离依次检查 `13505 / dms_tr_device`；首个数据库唯一匹配的名称才确认为该柱上变压器名称。这样可跳过附近属于其它设备的文字，例如 `LBS1197`，继续采用真正的右侧变压器名称 `96210`。
- 派生熔断器名称后仍按 `13513 / dms_disconnector_device` 的 `NAME + 图级 FEEDER_ID` 唯一匹配，并继续使用 Domain=40。


## v4.1.53：新增熔断器模型 / Fuse Model

- 只处理图元管理中分类标记为 **FUSE** 的图元，图元类型识别完全以本地/中央图元分类标记为准。
- 每个熔断器先寻找图形位置最近的 **Transformer_OH 柱上变压器**；柱上变压器名称直接复用现有识别逻辑：只找设备上方或右侧、距离不超过 200 的最近有效 Text。
- 熔断器数据库名称固定为 **FUSE + 柱上变压器名称**。例如柱上变压器名称 `973360`，熔断器名称就是 `FUSE973360`。
- 目标表固定为 **13513 / dms_disconnector_device**；使用 `NAME + 图级 FEEDER_ID` 精确查询，必须得到唯一记录。
- 图级馈线继续使用现有统一规则：**环网柜 → 柱上开关 → 柱上变压器**，逐个设备尝试，首个数据库唯一匹配且带有效 FEEDER_ID 的设备确定单线图馈线。熔断器目标记录的 `13513.FEEDER_ID` 必须与图级馈线完全一致。
- 熔断器 Domain 固定为 **40**，Expected KeyID 使用 `13513.ID + (40 << 32)` 计算，并在模型校验和真正执行回写前通过数据库再次验证。
- 安全回写字段固定为 `app`、`voltype`、`p_ReportType`、`state`、`keyid`；原始 G 文件不修改，只写 Workspace/g_output 安全副本。
- 新增熔断器模型设置页、候选选择表、HTML/CSV 报告和 Console 日志。


## v4.1.52：馈线识别改为“逐个设备，首个唯一即采用”

- 图级馈线仍按 **环网柜 → 柱上开关 → 柱上变压器** 的优先级识别，但不再要求高优先级设备“必须全部可用”或“同类唯一设备的 FEEDER_ID 必须全部一致”。
- 环网柜逐个查询 `13501 / dms_combined_device`：名称匹配 0 条或多条时跳过继续下一个；首个唯一匹配且带有效 `FEEDER_ID` 的 RMU 立即作为馈线判定设备。
- 如果所有 RMU 都无法唯一判定，继续逐个检查柱上开关；柱上开关同样查询 `13501`，首个唯一记录立即采用。
- 如果柱上开关也全部无法唯一判定，最后逐个检查柱上变压器；柱上变压器查询 `13505 / dms_tr_device`，首个唯一记录立即采用。
- 成功取得 `FEEDER_ID` 后仍必须查询 `13500 / dms_feeder_device` 确认最终馈线。若唯一设备给出的 FEEDER_ID 在 13500 不存在，则作为数据库完整性错误阻断，不静默换用其它设备。
- Console 日志记录每个实际尝试的候选设备及“0 条 / 多条不唯一 / FEEDER_ID 为空 / 最终采用”结果；报告继续只展示最终真正采用的判定设备。
- RMU 自身关联仍不要求先识别图级馈线；柱上开关、柱上变压器、馈线及其它需要馈线约束的模块仍必须证明目标设备属于最终识别出的图级 FEEDER_ID。

## v4.1.51：报告增加简洁馈线判定说明

- 馈线、柱上开关、柱上变压器以及配网主站设备报告增加简洁的“馈线判定”说明。
- 报告明确显示本次实际采用的判定设备，例如“环网柜 96680”“柱上开关 LBS1115”或“柱上变压器 973360”。
- 判定过程只显示短链路：上方/右方最近名称 → 13501/13505 唯一匹配 → 读取 FEEDER_ID → 查询 13500 确认最终馈线；不再展开内部超长证据链。
- 馈线报告现在同步保存判定锚点设备，便于 HTML 报告展示；馈线识别优先级、设备归属校验和关联逻辑均不变化。


## v4.1.50：柱上开关报告精简图级馈线判定依据

- 柱上开关 HTML/CSV/公开 report.json 不再展示“图级馈线判定依据 / Graph Feeder Evidence”字段，避免超长证据链占用明细表宽度。
- “图级馈线识别方式”“图级馈线 ID/名称”等结果字段继续保留。
- 馈线判定证据仍保留在程序内部，用于校验、设备归属检查和 Console 日志，不改变任何馈线识别或关联逻辑。




## v4.1.49：柱上开关/柱上变压器取消名称格式、颜色、背景强制过滤

- 柱上开关和柱上变压器设置页删除“设备名称筛选条件（强制过滤）”区域，不再让用户选择名称格式、文字颜色或文字背景。
- 名称识别继续强制采用吉达规则：只看设备**上方或右侧**的 Text，并保留原距离阈值（柱上开关 300、柱上变压器 200）。
- 业务逻辑不再读取或应用 `name_format / name_colors / name_has_background`；旧本地缓存中即使仍存在这些字段也会被忽略。
- 仍保留基础 Text 合法性排除（例如 kV、A、V 等明显单位/注释文字），避免把非设备名称当成目标名称。
- 馈线识别优先级、设备馈线归属、数据库匹配、KeyID 校验与安全回写逻辑不变。


## v4.1.47：图元配置三按钮分离 / Local Save, Admin Publish, Central Pull

- 图元管理页把配置动作明确拆成三个独立按钮：**保存到本地缓存**、**保存并同步到中央仓库**、**同步中央配置仓库配置**。
- “保存到本地缓存”只保存当前图元服务器设置和图元分类标记到用户本机缓存，不访问中央仓库；共享配置仍仅 Admin 可编辑。
- “保存并同步到中央仓库”仅 Admin 可用：先落盘本地缓存，再由服务器校验 Admin machine_id/admin_epoch 后发布中央共享配置。
- “同步中央配置仓库配置”对普通客户端和 Admin 均可用，只有用户手动点击才读取中央仓库，并按既有规则用中央数据库、文件服务器、图元标记覆盖本机共享缓存。
- 软件启动行为不变：不自动读取中央仓库，不自动测试 Oracle/SSH。


## v4.1.46：吉达固定单馈线图、统一上方/右侧名称识别与设备日志

- 馈线模块移除“自动识别 / 强制单馈线图 / 强制组合图”选择，吉达现场固定按单馈线图工作。
- 环网柜、柱上开关、柱上变压器的名称搜索方向统一硬限制为 **上方或右侧**；原有名称格式、颜色、背景、距离阈值和一对一 Text 分配规则保持不变。
- 柱上开关继续使用 300 距离上限，柱上变压器继续使用 200 距离上限，RMU 继续使用既有 RMU 距离规则。
- Console 日志新增发现环网柜、柱上开关、柱上变压器、馈线识别候选和最终馈线信息，便于现场审计。
- 馈线识别优先级、设备馈线归属校验、13503 分配/创建、KeyID 校验和安全副本写回逻辑不变。

## v4.1.45：Admin 随时抢占与自动降权 / Admin Takeover

- 任意普通客户端都可以手动点击“抢占 Admin 权限”；抢占只更新很小的 `instance.json` 所有权信息，不自动同步或发布数据库、服务器、图元配置。
- Admin 所有权新增 `admin_epoch`。每次抢占都会递增，发布与释放时服务器同时校验 `machine_id + admin_epoch`，避免旧 Admin 或同机旧进程继续发布。
- 当前 App 在明确成为 Admin 后，每 10 秒后台只读取一次 `instance.json`。发现 Admin 已被其他客户端抢占时立即自动降权为普通客户端；该检查不读取 `database.json`、`file_server.json`、`element_marks.json`。
- 软件启动仍然完全本地优先：启动阶段不访问中央仓库，不检查 Oracle/SSH。只有手动同步、抢占、发布/释放或成为 Admin 后的所有权检查才会访问中央服务器。
- 普通客户端的数据库、G 文件 SSH、图元服务器和图元分类配置均为只读，只能手动同步中央共享配置；抢占 Admin 后才允许修改、保存本地共享配置并手动发布。
- 中央配置发布继续与本地保存分离；后台 Admin 检查失败不会因临时网络故障自动降权，真正发布时仍由服务器再次强校验所有权。

## v4.1.44：本地配置优先 / Manual Central Sync

- 软件启动严格只读取本机配置缓存，不自动访问中央配置、Oracle 或 SSH/SFTP 服务器。
- 图元分类标记、数据库配置、G 文件服务器/图元服务器配置及中央仓库连接参数均保存在本机用户缓存；替换程序目录后仍可恢复。
- 本机用户可以自由修改并保存配置；普通保存不会自动发布到中央仓库。
- 只有点击“连接并同步中央配置”才读取中央仓库；同步成功后中央数据库、文件服务器和图元标记会覆盖本机对应缓存。
- “初始化并设为 Admin”“保存并发布全部配置”“发布图元配置”“释放 Admin”均保持为显式人工操作。
- Oracle/SSH 连通性不在启动阶段检查，仅在用户点击测试或实际执行相关功能时连接并按需报错。


## v4.1.43：统一馈线识别优先级 / Unified Feeder Ownership

- 除 RMU 环网柜关联本身外，所有模型关联都必须先识别图级馈线，并证明目标数据库设备属于该馈线。
- 馈线识别采用固定优先级：**环网柜 → 柱上开关 → 柱上变压器**。只有图内不存在更高优先级设备时，才允许使用下一类设备。
- 环网柜和柱上开关都使用 `13501 / dms_combined_device` 的唯一数据库记录取得 `FEEDER_ID`；柱上变压器使用 `13505 / dms_tr_device` 的唯一记录。
- 同一优先级存在多个可唯一匹配设备时，它们的 `FEEDER_ID` 必须全部一致；冲突时直接阻断。
- 文件名、G 根 `facID`、源侧 `CBreaker` 名称和人工选择均不参与馈线识别。
- Feeder、Pole Switch、Pole Transformer、Master Station 在执行阶段都会重新识别图级馈线；非馈线模块同时重新验证目标设备的馈线归属。

## v4.1.42：馈线按自身图元自动识别 / Feeder Graphical Recognition

- 馈线识别方式与柱上开关、柱上变压器保持一致：`目标图元 -> 最近有效 Text -> 数据库唯一匹配`。
- 馈线自己的目标图元为源侧 `CBreaker`；使用现有名称格式、颜色、背景过滤规则，在 400 图形距离内选择最近 Text。
- 将该图上 Text 作为馈线名称证据，唯一匹配 `13500 / dms_feeder_device` 后得到 `FEEDER_ID`。
- **不会**读取柱上开关/柱上变压器的 `feeder_id` 来反推馈线。
- 文件名、G 根 `facID`、人工馈线输入均不再作为馈线识别来源。
- 13503 分配/补齐、SECTION_TYPE、BV_ID、KeyID 校验、Workspace 安全副本等其它逻辑保持不变。

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

单线图中会进一步校验图级 FEEDER_ID；数据库其它馈线上的同名 RMU 不再阻断，只要求当前馈线内唯一匹配。

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

从 v4.1.97 开始，RMU 在单线图中会进一步校验图级馈线：先沿用现有设备识别规则确定 FEEDER_ID，再只在该馈线下选择同名环网柜。数据库其它馈线上的同名 RMU 不再造成阻断；合成图和环网图保持原 RMU 行为。

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