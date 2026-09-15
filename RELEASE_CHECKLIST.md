# 发布检查清单

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
