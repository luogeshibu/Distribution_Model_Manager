# 配网模型管理工具 v3.0.23

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
