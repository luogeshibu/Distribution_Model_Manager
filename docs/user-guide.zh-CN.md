## v3.0.24 馈线判断策略

RMU 模块不再进行任何馈线相关判断。

不会再使用以下信息参与模型校验或模型关联：

- G 文件名中的馈线号。
- 环网柜 `feeder_id`。
- `dms_feeder_device` 表的馈线名称。
- 设备表中的 `feeder_id`。
- G 图上 Bus 周围的馈线名称。

当前 RMU 自动关联的核心条件为：

1. 环网柜名称在 `dms_combined_device` 中唯一。
2. G 图元逻辑 `p_NameString` 有效。
3. 对应数据库设备 CODE 唯一存在。
4. 数据库 CODE 与逻辑 `p_NameString` 一致。
5. Expected KeyID 校验正确。
6. 如果 G 图元已经存在 KeyID，当前模型必须属于当前环网柜。
7. 如果已有 KeyID 关联到了其它环网柜，则属于 `RMU_LINK` 硬错误。

馈线不会产生 PASS / WARN / FAIL，也不会阻断模型关联。

# 配网模型管理工具 v2.8.5 用户帮助

## Workspace

用户无需选择输出目录。程序自动创建：

```text
workspace/
├─ config.json
├─ logs/
└─ runs/
   └─ YYYYMMDD_HHMMSS/
      ├─ g_output/
      ├─ report/
      │  ├─ report.html
      │  ├─ report_环网柜汇总.csv
      │  └─ report_设备明细.csv
      └─ console.log
```

源码运行时 `workspace` 位于项目目录。
EXE 运行时 `workspace` 位于 EXE 所在目录。
超过 30 天的数据自动删除。

## 原始 G 文件保护

原始 G 文件永远不修改。
执行模型关联时，程序会把全部选中的 G 文件复制到本次 `g_output`，
再只修改副本。

## 关联前强制校验策略

- CBreakerDis：CODE 不得为空；CODE 必须等于当前用于校验的 p_NameString；NAME 不参与判断。
- ZhaiWaiJieDiDaoZha：逻辑 p_NameString=开关名+D；CODE 必须一致。
- BusDis：表号 13506（dms_bs_device），默认域号 1；CODE 必须等于用于校验的 p_NameString；图上文字模式固定 BUS。
- 三类设备 G 图元数量必须和数据库 combined_id 下记录数完全一致。
- 已有关联 KeyID 时继续核对当前 Device ID、Table ID、Domain、combined_id、Expected KeyID。
- 已正确关联：无需重复关联。
- 已错误关联：禁止自动覆盖。

## Oracle EXE 打包

v2.8.5 增加专用 `hooks/hook-oracledb.py`，
构建时同时收集 oracledb 包、隐藏模块和 metadata。
