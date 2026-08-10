# 配网模型管理工具 v3.0.10

## 本版本的设备校验原则

### 1. 环网柜必须唯一

先根据识别到的环网柜名称查询 `dms_combined_device`：

```text
0 条    -> FAIL
1 条    -> 继续设备校验
> 1 条  -> FAIL
```

环网柜不唯一或不存在时，不再尝试根据设备数据库结果判定该 RMU 可关联。

### 2. G 文件是设备校验的主数据

只校验 G 文件里实际存在的：

```text
CBreakerDis
ZhaiWaiJieDiDaoZha
BusDis
```

对于每一个 G 图元，得到“用于校验的 p_NameString”后，只检查对应设备表中：

```text
CODE = 用于校验的 p_NameString
```

结果：

```text
0 条    -> FAIL（红色）
1 条    -> 数据库模型匹配成功
> 1 条  -> FAIL（CODE 对应多条数据库设备）
```

数据库中与任何 G 图元 CODE 无关的其它设备记录：

```text
忽略
不阻断 RMU
不进入设备明细
```

例如数据库中有：

```text
NAME       CODE
Q1
Y1
Y2
TR1        Q1
Y1-8723    Y1
Y2-22333   Y2
```

如果 G 文件要求：

```text
Q1
Y1
Y2
```

则只使用 CODE 为 Q1/Y1/Y2 的后三条记录。
前面 CODE 为空的 Q1/Y1/Y2 记录不参与本次 G 图元匹配，也不会因为它们存在而阻断 RMU。

### 3. 名称来源逻辑不变

仍支持：

```text
使用 XML p_NameString
使用图上文字
```

图上文字模式：

```text
CBreakerDis            = 图上识别名称
ZhaiWaiJieDiDaoZha     = 配对开关名称 + D
BusDis                 = BUS
```

### 4. 未关联不是模型数据错误

只要 G 图元名称能够唯一匹配数据库 CODE：

```text
状态 = PASS（绿色）
```

如果当前没有 KeyID：

```text
设备是否已关联模型 = NO
是否需要回写       = YES
处理建议           = 需要关联
```

如果当前 KeyID 已正确：

```text
状态 = PASS
处理建议 = 模型已关联，无需关联
```

如果当前 KeyID 指向错误设备 / 表 / 域 / 环网柜：

```text
状态 = FAIL（红色）
```

### 5. 设备明细只显示 G 文件设备

设备明细不会再生成：

```text
DATABASE_INVENTORY
```

类型的伪设备行。

数据库相关错误通过当前 G 图元的 FAIL 原因和环网柜汇总的“关联阻断原因”体现。

## 报告排序

环网柜汇总：

```text
只按环网柜序号升序
```

设备明细：

```text
每个环网柜内部只按 G 图元类型分组：
1. CBreakerDis
2. ZhaiWaiJieDiDaoZha
3. BusDis
```

同类内部保留原处理顺序。

## Workspace

源码：

```text
项目根目录/workspace/
```

EXE：

```text
EXE同级/workspace/
```

## 打包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

发布目录：

```text
release/
```

`build_exe.ps1` 不会运行生成后的 EXE。
