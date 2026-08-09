# 配网模型管理工具 v2.8.0

## v2.8.0 当前模型关联校验

本版本新增对 G 文件“当前已经关联的模型”的完整校验。

设备报告新增：

- 设备是否已关联模型
- 当前 KeyID
- 当前设备 ID
- 当前表号
- 当前域号
- 当前模型数据库表
- 当前模型设备 CODE / NAME
- 当前模型所属环网柜 ID
- 当前模型环网柜 ID 是否正确
- 当前模型是否正确
- 当前模型状态
- 处理建议
- 是否需要回写

正确关联的设备：

```text
模型已关联且正确
处理建议 = 模型已关联，无需关联
是否需要回写 = NO
```

未关联设备：

```text
当前模型状态 = 未关联
处理建议 = 需要关联
是否需要回写 = YES
```

错误关联设备不会自动覆盖：

```text
当前模型状态 = 模型已关联但关联错误
处理建议 = 禁止自动关联，请检查现有模型
```

RMU 本身在 `dms_combined_device` 中不唯一时，整个 RMU 阻断，
柜内已有 KeyID 也不能被判定为正确。

数据库设备数超过 G 图元数时，RMU 的关联阻断原因统一显示：

```text
一个环网柜下找到了超过设备总数量的设备，请检查数据库模型。
```

### 构建

统一使用：

```bat
build.bat
```

Release ZIP 改为 Python `zipfile` 创建并自动重试，不再使用
PowerShell `Compress-Archive`。

---

## 构建方式

团队统一只执行：

```bat
build.bat
```

不要直接双击或手工执行 `build.ps1`。

`build.bat` 会自动使用：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

调用真正的 PowerShell 构建脚本。

本版本的 `build.ps1` 已改为纯 ASCII 英文内容，避免 Windows PowerShell 5.1 因 UTF-8/BOM/中文字符串导致乱码和 ParserError。

构建成功后才会生成：

```text
Release/
├─ Distribution_Model_Manager_v2.7.2/
└─ Distribution_Model_Manager_v2.7.2.zip
```

---

## v2.7.1 界面优化

### 模型工作区改为最外层单滚动条

模型工作区不再通过内部 `QScrollArea + QSplitter` 压缩 RMU 配置。

当前结构：

```text
模型工作区（最外层滚动）
├─ 模型任务
├─ RMU / Feeder 完整配置
├─ 任务进度
├─ Console 日志
└─ 操作按钮
```

RMU 配置自身没有纵向滚动条。窗口高度不足时，只在整个模型工作区最右侧显示一个纵向滚动条。

### 数据库按钮

【测试数据库连接】与【保存数据库配置】默认均为普通白色按钮。

仅在：

- 鼠标悬停；
- 鼠标按下；
- 键盘焦点；

时提供绿色反馈，不再让“测试数据库连接”按钮长期保持绿色。

### 其它

业务校验、Oracle 查询、KeyID、自动 HTML/CSV 报告以及 G 文件回写逻辑均未改变。

---

## v2.6.0 主要调整

本版本重新整理了“日志 / 报告 / 进度”的模块归属。

### 1. 模型工作区内直接显示进度和结果

不再使用左侧独立“报告”一级菜单。

模型工作区现在包含：

```text
模型任务
模型专属配置
任务进度
本次结果
运行日志
```

模型校验/关联预览完成后，会自动切换到【本次结果】页。

### 2. 任务进度条

运行模型任务时显示 0~100% 进度。

RMU 模块会按：

- Oracle 数据库预检查；
- 当前 G 文件；
- 当前 RMU 环网柜处理数量；
- 最终结果整理；

持续更新进度和当前处理说明。

### 3. 数据库日志归数据库模块

【数据库】页面增加独立的“数据库运行日志”。

手工点击“测试数据库连接”时，日志只显示在数据库模块中，
不会再要求用户到其它报告页面查看。

模型任务自己的 Oracle 预检查日志仍属于本次模型任务，
显示在模型工作区【运行日志】中。

### 4. 历史输入路径检查

程序继续自动记录：

```json
{
  "input_path": "",
  "last_file_path": "",
  "last_folder_path": ""
}
```

启动软件时，如果上一次使用的 `input_path` 已不存在：

- 模型工作区显示警告；
- 自动弹出“历史路径不存在”提示；
- 用户需要重新选择有效 G 文件或目录。

运行任务时也会再次检查文件/目录是否存在。

### 5. 报告导出目录单独记忆

新增：

```json
{
  "last_report_export_dir": ""
}
```

HTML / CSV 导出目录和 G 文件输入目录分开记录。

第一次没有报告导出历史时，会使用当前可用目录；
从第二次开始，导出对话框默认进入“上一次报告导出目录”。

### 6. Release

运行：

```text
build.bat
```

正式交付文件仍输出到：

```text
Release/
├─ Distribution_Model_Manager_v2.6.0/
└─ Distribution_Model_Manager_v2.6.0.zip
```

---

团队内部使用的 PySide6 配网 G 文件模型管理工具。

## v2.5.1 界面与发布结构优化

- `RMU 环网柜识别` 与 `RMU 设备数据库表与域配置` 改为同一行左右布局。
- 模型专属配置区加入滚动容器，小分辨率或窗口高度不足时不再压缩控件。
- 原 `RMU 设备模型关联规则` 更名为 `RMU 设备数据库表与域配置`，更准确反映该区域用途。
- Table ID / Domain 继续使用原生 SpinBox；上下按钮可点击，直接输入有效，鼠标滚轮不会修改数值。
- 模型类型、处理方式、开关名称来源下拉框同样禁止滚轮误切换。
- 底部 `运行当前任务 / 执行模型关联 / 数据库设置` 三个按钮统一为相同尺寸。
- 新增正式 `Release/` 发布目录。运行 `build.bat` 后会生成：

```text
Release/
├─ Distribution_Model_Manager_v2.5.1/
│  ├─ Distribution_Model_Manager_v2.5.1.exe
│  └─ ...运行依赖文件
└─ Distribution_Model_Manager_v2.5.1.zip
```

团队交付时直接发送 `Release/Distribution_Model_Manager_v2.5.1.zip` 即可。

## 既有功能说明

团队内部使用的 PySide6 配网 G 文件模型校验、关联预览与安全回写工具。

## v2.3.0 RMU 核心规则

### CBreakerDis（默认表号 13502 / 域号 40）

开关名称来源可以在 App 中选择：

- `使用 p_NameString`
- `使用环网柜内图上文字`

图上文字模式采用：RMU 框内 Text/DText + 与 CBreakerDis 最近唯一空间关系。找不到、近距离歧义、文字被多个开关竞争时直接 FAIL，不猜测。

数据库强制规则：

- `CODE` 不能为空；
- `NAME` 不能为空；
- `CODE == 当前用于校验的 p_NameString`；NAME 不参与判断；
- `CODE == 当前选择的开关名称`。

当名称来源选择 p_NameString 时，`CODE` 还必须等于 p_NameString。
当名称来源选择图上文字时，图上文字是权威名称；p_NameString 为空或与图上文字不一致会 WARN，但不会仅因此阻止关联，因为该模式就是 p_NameString 的备用方案。

### ZhaiWaiJieDiDaoZha（默认表号 13514 / 域号 40）

接地刀闸不独立猜名字。程序先将每个接地刀闸与 RMU 内对应 CBreakerDis 做一对一最近空间配对：

```text
Expected Ground CODE = Breaker Name + "D"
```

例如：

```text
Y1 -> Y1D
Y2 -> Y2D
Q1 -> Q1D
```

强制规则：

- DB `CODE` 不能为空；
- DB `CODE == BreakerName + D`；
- G 元素 `p_NameString` 不能为空；
- DB `CODE == G p_NameString`；
- DB `NAME` 可以与 CODE 不同。

### BusDis（默认表号 13506 / 域号 0）

强制规则：

- DB `CODE` 不能为空；
- G `p_NameString` 不能为空；
- DB `CODE == p_NameString`；
- DB `NAME` 可以与 CODE 不同。

## 数量一致性是关联硬门槛

对每个 RMU、每一类图元：

```text
G 图元数量 == combined_id 下数据库记录数
```

必须严格相等。

例如 G 中有 3 个接地刀闸，但数据库查出 4 条，则该 RMU：

- 报告 `DEVICE_COUNT_MISMATCH`；
- 多余数据库设备也会在设备明细中显示；
- `RMU可关联 = NO`；
- 关联预览会跳过整个 RMU。

数据库完整性也会全量扫描，包括：

- CODE 为空；
- 13502 NAME 为空；
- 同一个 RMU 同一个设备表存在重复 CODE。

## Expected KeyID

仍使用：

```text
Expected KeyID = Device ID + Domain * 2^32
```

并通过 Oracle：

```sql
long2_to_long1(:keyid)
get_tab_no(:keyid)
get_col_no(:keyid)
```

反向验证 Device ID / Table ID / Domain，全部正确后才允许进入关联预览。

## 模型关联回写

v2.3.0 已接入 RMU 的关联预览和安全回写流程。

写入属性：

### CBreakerDis / ZhaiWaiJieDiDaoZha

```xml
app="6500000"
voltype="0"
p_ReportType="1"
state="41"
keyid="<Expected KeyID>"
```

### BusDis

```xml
app="6500000"
voltype="0"
p_ReportType="1"
state="15"
keyid="<Expected KeyID>"
```

回写安全机制：

1. 必须先生成 Association Preview；
2. 校验失败的 RMU 整体跳过；
3. Apply 前再次确认；
4. Apply 前再次测试 Oracle；
5. 如果 G 文件在 Preview 后发生变化，拒绝回写；
6. 如果 RMU 配置在 Preview 后发生变化，拒绝回写；
7. 修改前备份原 G 文件；
8. 仅通过 `G Tag + XML ID` 唯一定位；
9. 只修改目标元素开始标签，不重新序列化整个 G 文件；
10. 临时文件完成后原子替换。

## 报告

报告继续包含：

- 环网柜汇总
- 设备明细
- 运行日志

新增：

- 图上名称
- 名称来源
- 最终设备名称
- 配对开关名称
- 可关联
- RMU 可关联
- 设备数量问题
- 数据库字段问题
- 关联阻断原因

## 构建

```text
build.bat
```

输出：

```text
dist\Distribution_Model_Manager_v2.3.0\
```


## v2.5.1 名称来源逻辑

当“开关名称来源”选择“使用环网柜内图上文字”时，设备校验完全不再读取三类目标图元 XML 中原来的 `p_NameString`：

- CBreakerDis：逻辑 p_NameString = 图上识别名称；
- ZhaiWaiJieDiDaoZha：逻辑 p_NameString = 配对 CBreakerDis 名称 + `D`；
- BusDis：逻辑 p_NameString = 固定 `BUS`。

其他数据库完整性、数量一致性、Expected KeyID、关联预览与安全回写逻辑保持不变。

软件左侧新增【帮助】页面，源码同时提供 `docs/用户帮助.md`。构建 Release 时会把 `用户帮助.md` 一并复制到可发布 APP 目录中。
