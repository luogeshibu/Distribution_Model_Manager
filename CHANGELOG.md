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
