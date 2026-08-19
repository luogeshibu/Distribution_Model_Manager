# 发布检查清单

正式向团队分发前建议按以下顺序检查：

1. 执行 `powershell -ExecutionPolicy Bypass -File .\release_check.ps1`
2. 启动 GUI，确认数据库、模型工作区、运行历史、设置、帮助页面可正常切换
3. Oracle 连接测试通过
4. RMU 单图模型校验
5. RMU 大图/组合图模型校验
6. RMU 选择性模型关联，检查执行前确认摘要
7. 馈线模型校验与选择性关联
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
