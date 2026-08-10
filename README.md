# 配网模型管理工具 v3.0.13

## 状态颜色

| 状态 | 颜色 | 含义 |
|---|---|---|
| PASS | 绿色 | 校验正常 |
| WARN | 黄色 | 未关联，但 RMU 唯一、CODE 唯一存在、馈线一致，可自动关联 |
| FEEDER | 橙色 | 馈线不一致，禁止自动关联 |
| BLOCKED | 蓝色 | 已有人工作出关联且当前 CODE/馈线检查通过，但 RMU 名称不唯一，只能人工保留/复核，禁止自动关联 |
| FAIL | 红色 | 硬错误，例如 RMU 不存在、RMU 重复且设备未关联、CODE 不存在/重复、KeyID 无效 |

HTML 报告和【帮助】模块都包含颜色说明。

## 环网柜重复

环网柜名称查询出多条记录时：

```text
自动关联：始终禁止
```

设备当前没有 KeyID：
```text
红色 FAIL
环网柜存在多个，当前设备未关联，禁止自动关联
```

设备已经有 KeyID：
```text
继续反解当前 KeyID
→ 读取当前数据库设备
→ 检查当前 CODE 与用于校验的 p_NameString
→ 检查当前设备 FEEDER_ID 与 G 文件馈线
```

如果馈线不一致：
```text
橙色 FEEDER
```

如果 CODE 和馈线都正确：
```text
蓝色 BLOCKED
当前人工关联可保留/人工复核，但程序禁止自动关联或自动改写
```

## 环网柜唯一

只校验 G 文件实际需要的 CODE：

```text
CODE = 最终用于校验的 p_NameString
```

0 条：红色 FAIL，数据库不存在该设备。  
1 条：继续检查馈线、当前 KeyID。  
多条：红色 FAIL，CODE 重复。  

数据库其它无关设备全部忽略。

## 馈线

馈线不一致不使用红色，而使用橙色 FEEDER。

例如：

```text
G文件 = JED-NTH-ABH-06.sln.pic.g
G文件馈线 = ABH-06
数据库环网柜/设备馈线 = JED NTH ABH 09
```

结果为橙色 FEEDER，并禁止自动关联。

## 目录

```text
源码运行：项目根目录/workspace/
EXE运行：EXE同级/workspace/
发布目录：release/
```
