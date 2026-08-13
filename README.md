# 配网模型管理工具 v3.4.0

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
