# 发布检查清单

正式向团队分发前建议按以下顺序检查：

1. 执行 `powershell -ExecutionPolicy Bypass -File .\release_check.ps1`
2. 启动 GUI，确认数据库、模型工作区、运行历史、设置、帮助页面可正常切换
3. Oracle 连接测试通过
4. RMU 单图模型校验
5. RMU 大图/组合图模型校验
6. RMU 选择性模型关联，检查执行前确认摘要
7. 馈线模型校验与选择性关联
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
