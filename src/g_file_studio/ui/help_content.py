from __future__ import annotations

APP_HELP: dict[str, tuple[str, str]] = {
    "jeddah_batch": (
        "吉达图形批处理说明",
        """
<h3>用途</h3>
<p>仅用于吉达现场的批量单馈线标准化。每张输入 G 文件独立处理并独立输出，不执行馈线合并。</p>
<h3>固定流程</h3>
<ol>
<li>首先复用“通用基础处理 → 图形组合处理”的“彻底取消图形组合”能力：删除全部 &lt;Merge&gt;，并将识别到的 RMU 外框置于设备底层；</li>
<li>删除异常小尺寸 ConnectLine / FeedLine / Bus / BusDis；</li>
<li>RMU 本体必须是 rect 框内同时存在 BusDis、CBreakerDis、ZhaiWaiJieDiDaoZha 的组合；柜名只从环网柜框正上方的 Text 中按全图一对一规则识别，未找到上方名称时保持为空。识别后的柜名文字统一改为白色、字号固定为 50，并移动到所属环网柜上边框正中间上方，文字下边缘与上边框保持 10 个图形单位净间距；</li>
<li>最终按柜内 SMART 文字统一 RMU 外框：存在 SMART 的柜为红色；没有 SMART 的柜强制为白色；</li>
<li>RMU 图元类型以当前元素原始 devref/图元文件名为准：名称含 Circuit_Breaker 按 Circuit Breaker 处理，名称含 Load_Breaker_Switch 按 LBS 处理；Y/Q 显示名称不覆盖该类型。有 SMART 的柜使用分类标记 CIRCUIT_BREAKER_SMART / LOAD_BREAKER_SWITCH_SMART 指向的目标；无 SMART 的柜使用 CIRCUIT_BREAKER_NO_SMART / LOAD_BREAKER_SWITCH_NO_SMART。目标完全来自本地已保存分类标记，不再从同图其他柜学习或猜测版本。接地刀闸不替换。</li>
<li>对精确 SMR 标识做吉达专用智能处理：若对应柜内已经存在 SMART，只删除外部 SMR 并将外框保持红色；若柜内没有 SMART，则将 SMR 转为顶部居中的 SMART（字号固定 20）；之后再次执行 SMART 图元检查。</li>
<li>复用“服务器图元更新检查”的当前服务器标准执行环网柜图元检查；吉达批处理中的独立线路、拓扑和连接规范化不在本流程执行。</li>
<li>删除带 Bus 的环网柜矩形框，并将对应标题移动到母线上方；</li>
<li>将馈线名称移动到母线上方；</li>
<li>删除带 BusDis 的 RMU 所属 channel_status 红色 Status 点；归属判断直接复用现有“移动环网柜红色状态点”规则，只把最终动作从移动改为删除；</li>
<li>删除精确匹配的 H.T 文字标识（忽略大小写和首尾空白，不做子串删除）；</li>
<li>对现有 RMU 识别引擎识别出的全部配网环网柜检查 SMART 标识；同一柜内有多个 SMART 时保留 XML 中原有第一个，删除后续重复项，不移动或重写保留项；</li>
<li>仅当两个独立 Text 分别精确为 2000.00 与 UPDATED_MEASURMENT，且位于同一视觉行并水平相邻（间距不超过 10）时才成对删除；距离不相邻时不处理；</li>
<li>使用全局已确认 ID 模板执行 ID 检查与修复；</li>
<li>调用现有图形边距调整能力，默认将主体图形左、上、右、下边距设为 500；</li>
<li>最后调用现有图框添加能力，为每张处理后的单馈线图添加所选图框模板。</li>
</ol>
<h3>设计原则</h3>
<p>本页面仅编排已有处理能力。RMU 柜体/柜型/SMART 识别统一复用严格的公共识别器：rect 框内必须同时存在 BusDis、CBreakerDis、ZhaiWaiJieDiDaoZha，柜名固定只查框上方 Text；其他模块的默认名称模式与设置不受影响。吉达专用参数使用独立配置，不覆盖其他模块设置。</p>
""",
    ),
    "site_profile": (
        "图元管理帮助",
        """
<h3>中央配置</h3>
<p>“连接与环境”页面单独显示中央配置仓库的服务器、端口、账号和目录。推荐目录为 <code>/home/up8000/nari-international/gfilestudio/config/</code>，默认直接填入该路径，现场如有需要可以修改并保存到本机。目录中统一存放 <code>instance.json</code>、<code>database.json</code>、<code>file_server.json</code>、<code>id_rules.json</code> 和 <code>symbol_classification.json</code>。</p>
<h3>本地与中央</h3>
<p>每台工作站都可以维护自己的本地图元分类、文件服务器、Oracle、ID 规则和操作习惯。所有存在中央配置的模块统一使用“保存到本地 / 从中央同步 / 发布到中央”三类动作：保存到本地只写本机；从中央同步会明确提示并覆盖对应本机缓存；发布到中央仅当前 Admin 可用。【连接与环境】顶部中央仓库区域只保留测试、保存和“一键同步全部中央配置”；文件服务器与 Oracle 数据库各自提供单项同步/发布按钮，避免顶部出现重复入口。“一键同步全部中央配置”一次读取并校验 database.json、file_server.json、id_rules.json 和 symbol_classification.json，全部读取成功后再覆盖对应本机缓存。启动时所有页面只恢复本机 AppData 缓存，不读取中央 instance.json / symbol_classification.json / database.json / file_server.json / id_rules.json，也不测试 SSH/Oracle。首次启动即使本机没有任何配置，也保持未配置状态，绝不自动拉取中央配置。。新工作站必须先在“连接与环境”手工确认并保存中央仓库地址；未确认保存时禁止抢占 Admin 和发布任何中央配置，避免把某一现场的默认 IP 误用于其他现场。</p>
<h3>管理员</h3>
<p>同一时间只有 <code>instance.json</code> 记录的机器可以发布中央配置。管理员权限必须显式释放，释放后其他机器才能接管。关闭软件不会自动释放中央管理员。</p>
<h3>服务器图元</h3>
<p>原始 <code>element</code> 图元目录始终只读；中央配置文件位于独立的 gfilestudio/config 目录，不修改任何原始图元。</p>
""",
    ),
    "small_elements": (
        "异常小尺寸图元检测帮助",
        """
<h3>用途</h3>
<p>独立扫描 &lt;ConnectLine&gt;、&lt;FeedLine&gt;、&lt;Bus&gt;、&lt;BusDis&gt;。当 w 和 h 同时小于用户阈值（默认 10）时，作为疑似误画后残留的小尺寸图元输出报告。Bus 不区分水平、垂直或其他方向。</p>
<h3>报告与删除</h3>
<p>每次扫描都会输出带时间戳的 CSV 和 HTML，并列出文件名、元素类型、XML ID、x/y/w/h、keyid，不覆盖历史报告。结果表按普通表格方式支持单元格/区域选择和 Ctrl+C 复制；需要处理的异常图元通过首列复选框单选、多选或全选，再统一执行。执行后会生成修改后的 G 文件和本次处理报告，原文件不覆盖。</p>
<p>如果选中元素存在非空 keyid，删除前必须再次确认，并明确显示所在文件、元素类型、XML ID 与 keyid。</p>
<h3>与馈线合并的关系</h3>
<p>主母线合并不再使用 w&lt;10 的特殊过滤条件。所有异常短线 Bus 统一在本模块发现和清理。</p>
""",
    ),
    "rmu": (
        "环网柜处理帮助",
        """
<h3>RMU 基础识别与汇总（必需）</h3>
<p>RMU 基础识别是本页面所有后续功能的共同前置能力，固定识别全部有效 RMU 且不可关闭，并强制生成 RMU 汇总 CSV / HTML 报告。有效 RMU 必须是 rect 框内同时存在 BusDis、CBreakerDis、ZhaiWaiJieDiDaoZha 的组合；柜名只从页面勾选的方向识别，并按具体 Text 对象一对一分配，未找到所选方向名称时保持为空。用户只需要维护柜名方向、柜名排除字符串和“智能 RMU 标记字符”。智能标记默认 SMART / SMR，可扩展 NEWSMART、SMART-SE 等任意完整 Text；程序全图扫描这些标记并唯一归属最近的有效 RMU，同时自动把这些标记从柜名候选中排除。</p>
<h3>环网柜图元处理</h3>
<p>环网柜页面可选择“不处理”或“组合所有环网柜”。彻底取消图形组合已移动到“通用基础处理 → 图形组合处理”：该操作删除整个 G 文件 Layer 中全部 &lt;Merge&gt;，并将识别到的 RMU 外框置于设备底层；除 XML 顺序外不修改设备属性、坐标、ID 或引用。</p>
<p>SMART/SMR 外框改色和 channel_status 状态点位置均沿用原基础处理中的既有算法；另外可单独启用“将已识别的环网柜名称统一改成白色”，并复用本页面所选方向的严格柜名结果。Poke 跳转已经从本页面完全抽离到左侧独立“Poke 跳转处理”模块，本次不改变其业务流程。</p>
<p>“服务器图元更新检查”是独立通用工具：检查模式只读；需要时可按当前服务器标准在 workspace 生成纠正副本，用于纠正标准中已定义设备图元的变体/devref 和设备几何。它不修改服务器源文件，也不承担全图拓扑判定；线路或设备关系应由具体设备处理流程按用户选择单独分析。SMR 等现场特殊柜不参与通用 NORMAL 学习；该工具不改变原“开始环网柜处理”流程。</p>
<h3>RMU 识别规则</h3>
<p>直接解析 G 文件，不使用 OCR。有效 RMU 必须是 rect 框内同时存在 BusDis、CBreakerDis、ZhaiWaiJieDiDaoZha 的组合；其他图形不识别为环网柜。柜名只查页面勾选方向的 Text，按具体 Text 对象一对一分配；没有符合条件的名称时保持为空，同一文字内容出现多次按多个独立文字处理。多个候选按颜色、字符格式、与框的距离及同方向布局综合排序，优先选择更符合现场模式的候选。柜型优先按 Y/Q 名称统计，必要时回退设备 devref；用户配置的智能标记统一归类为智能环网柜，并且每个标记只允许属于一个 RMU。</p>
""",
    ),
    "basic": (
        "通用基础处理帮助",
        """
<h3>输入方式</h3>
<p>基础处理支持单个 G 文件和 G 文件目录。单文件模式只处理所选文件；目录模式批量处理目录第一层中的所有 .g 文件。</p>
<h3>规则化处理</h3>
<p>“替换元素属性值”和“删除匹配元素”默认关闭。点击“扫描元素与属性”可从当前单个输入文件或输入目录中生成元素标签和属性名下拉选项。</p>
<p><b>处理范围：</b>只处理 G 根节点直属 Layer 的直接子元素，不修改 G、Theme、Layer 外内容，也不递归修改图元内部子元素。</p>
<ul>
<li>属性替换：元素标签、属性名、旧值全部精确匹配后写入新值。</li>
<li>元素删除：元素标签、属性名、属性值全部精确匹配后删除整个元素子树。</li>
</ul>
<p>删除后会在当前 Layer 范围内清理 link、node_area 和 p_FatherObjId 中指向已删除真实图元的引用。</p>
<p><b>ID 功能：</b>已从基础处理抽离到独立“ID 检查与修复”页面。</p>
<h3>同类图元版本升级</h3>
<p>用于同一设备语义、同一主体 XML 类型的旧版图元 → 新版图元升级。OLD 和 NEW 两侧都可以从本地选择 G 文件，也可以直接从主程序“图元管理”已桥接到本机 AppData 的图元缓存中选择；从服务器选择只读本机缓存，不会再次访问 SSH。OLD/NEW 文件名可以不同，可自动配对或手工指定；程序读取 w/h、AlignCenter、pin 并保持电气锚点绝对位置。SMART/NORMAL 用错等“图元类型/变体使用错误”不属于版本升级，应先由“服务器图元更新检查”发现并告警，再走对应纠正流程。</p>
<h3>线路与母线样式</h3>
<p>可分别调整 &lt;FeedLine&gt;、&lt;ConnectLine&gt;、&lt;BusDis&gt; 和 &lt;Bus&gt; 的颜色与线型。颜色同步写入 lc/lcc；线型使用 ls：实线=1、虚线=2，选择“保持原样”时不修改 ls。颜色与线型可独立设置，不修改填充色、线宽 lw、坐标、ID 或引用。</p>
<h3>输出冲突</h3>
<p>当输入输出路径相同，或输出目录中已存在同名文件时，程序会提示选择：自动添加统一时间戳（推荐）、安全覆盖或取消任务。安全覆盖先写临时文件并重新解析验证，成功后才替换原文件。</p>
""",
    ),
    "id_rules": (
        "元素 ID 规则模板帮助",
        """
<h3>唯一规则来源</h3>
<p>本模块以用户主动选择的 G 图形样本作为 ID 规则统计来源。切换到 SSH 远程 G 文件后，先在服务器列表中勾选有代表性的 G 文件，再点击“扫描选中 G 文件 ID 规则”；程序只读下载这些选中文件到 workspace，不再全量遍历服务器目录。扫描后跨已选文件聚合同类元素并展示主流候选，用户逐类确认后才加入本机规则。</p>
<p>规则配置同样遵循统一的本地/中央流程：可点击“保存到本地”明确固化本机 <code>id_rules.json</code>；“从中央同步”会覆盖本机规则缓存；“发布到中央”只由当前 Admin 把本机规则发布成中央正式配置。启动时不会自动读取中央规则。</p>
<h3>扫描当前 G</h3>
<p>ID 检查与修复始终使用当前本机已确认的规则版本，不会把普通“扫描当前 G 文件（只检查 ID）”里的候选直接写入模板。选中样本不足以稳定推断的类型只记录告警，不擅自猜测。确认加入本机后，普通用户只在本地使用；当前 Admin 可再点击“发布到中央”把审核后的 id_rules.json 发布到中央仓库。</p>
<h3>重复 ID 修复</h3>
<p>修复时保留第一处重复 ID，后续重复元素只允许按照该元素类型的当前模板，从当前同类最大流水号继续分配；不补历史空号。未知、禁用或未同步的类型禁止生成新 ID。</p>
""",
    ),
    "merge": (
        "馈线图合并帮助",
        """
<h3>文件与顺序</h3>
<ul>
<li>文件名任意，但后缀必须是 <b>.sln.pic.g</b>。</li>
<li>不解析站点、馈线号，也不判断是否属于同一站。</li>
<li>点击“加载 / 检查”时显示加载进度，并检查 XML、对齐基准和图框类型。</li>
<li>点击“查询并导入”，可按文件名关键字模糊查询，选择或全选匹配文件后导入列表。</li>
<li>支持 Ctrl/Shift 多选并点击“删除所选”，只保留需要合并的文件；此操作不会删除磁盘文件。</li>
<li>使用上移、下移、置顶、置底自由定义剩余文件顺序，第一行作为基准。</li>
<li>点击“导入全部可用”可把全部通过检查的文件按自然顺序导入。</li>
<li>G File Studio 内置图框会在合并前从内存副本中自动移除；客户或来源不明图框禁止参与合并。</li>
<li>图框识别不读取标题、Draw、Approve、Issue、姓名或日期文字内容。</li>
</ul>
<h3>垂直对齐</h3>
<ul>
<li>只识别标签严格等于 <b>&lt;Bus&gt;</b> 的非零长度水平母线，&lt;BusDis&gt; 不参与。</li>
<li>存在 Bus 时选择 Y 最小的最上方 Bus；同一 Y 时优先最长 Bus。</li>
<li>没有 Bus 时使用该文件位置坐标中的最小 Y，也就是最高图元。</li>
<li>所有后续文件都与第一张基准文件的统一 Y 对齐。</li>
</ul>
<h3>主母线合并</h3>
<ul>
<li>启用“主网母线处理”后先选择单母线或双母线。单母线只检查 Y 最小的最高有效水平 &lt;Bus&gt;；双母线检查最高母线和同方向下方长度大致相同的第二条有效水平 &lt;Bus&gt;。小尺寸 Bus 不再在本模块特殊过滤，由“异常小尺寸图元检测”统一处理。只有被选中的主母线必须有非空 keyid；不同 keyid 永远不会互相连接。同一 keyid 必须在馈线排序中连续，并且合并后必须处在同一水平线上，否则拒绝执行。文件名只作人工提醒，不作为硬性拦截条件。</li>
<li>保留第一条 Bus，从第一张馈线母线起点连续延伸到最后一张馈线母线终点；其余顶部主母线删除。</li>
<li>所有原馈线连接关系同步改接到保留 Bus；&lt;BusDis&gt; 和非顶部 Bus 不处理。</li>
<li>输出后继续按“ID 检查与修复”中用户确认的 ID 规则强制检查和规范。</li>
</ul>
<h3>合并后处理</h3>
<ul>
<li>“合并完成后自动添加 Poke 跳转”默认勾选。程序直接复用现有 Poke 跳转模块，对合并结果执行 RMU、AR/LBS/SEC 设备和站点跳转 Poke，不重新实现第二套识别逻辑。</li>
<li>处理顺序固定为：<b>馈线合并 → Poke 跳转 → 可选图框</b>。Poke 在图框之前执行，避免图框模板中的文字或图元进入 Poke 识别候选。</li>
<li>Poke 使用本机已同步的图元分类缓存和当前 Oracle 配置；服务器 G 文件仍保持只读。Poke 处理报告会与合并结果一起保存在本次 workspace 运行目录。</li>
</ul>
""",
    ),
    "margin": (
        "图形边距调整帮助",
        """
<h3>主体图形边距</h3>
<p>程序识别 Layer 中的主体图形边界，整体平移后使主体距离画布左、上、右、下达到用户设置值，默认均为 500。</p>
<h3>已有图框</h3>
<p>只有可确认的 G File Studio 内置图框会自动处理：图框及其标题栏、签字栏不参与主体边界计算，新画布生成后保持原图框四边距，拉伸外框线，并按锚点移动附属组件。</p><p>检测到客户图框或无法确认来源的图框时，程序会停止并提示先在图形编辑器中删除图框。</p>
<p>标题、Draw、Approve、Issue、日期、字体、颜色、线宽和表格内容都不会被修改。</p>
<h3>输入方式</h3>
<p>支持单个 G 文件和目录批量处理。输出保持源文件名不变并写入独立输出目录，不覆盖原文件。</p>
""",
    ),
    "orthogonalize": (
        "线路正交化帮助",
        """
<h3>用途</h3>
<p>逐个读取 G 文件中的 ConnectLine、FeedLine、BusDis、Bus、ACLine 和 line，并在当前文件内读取线路 d 端点及 node_area/link 端点引用。模块优先使用主程序“图元管理”已经缓存到本机 AppData 的图元 w/h、旋转和标准 Pins（不会自动访问 SSH）。若线路端点与唯一标准 Pin 之间存在小间隙，会先安全延长/吸附到精确 Pin 并补齐设备与线路 reciprocal link/node_area；对识别到的 RMU/环网柜，会检查所有穿出柜框的出线（不区分 Y1/Y2/Q1/Y3/Y4），沿 reciprocal link/node_area 穿过中间 ConnectLine 追溯到柜内实际 LOAD_BREAKER_SWITCH/CIRCUIT_BREAKER 的出线 Pin。对于旧图中缺少中间 ConnectLine 的 reciprocal 引用、但几何上只有唯一的同轴重叠/微小间隙时，会在同一 RMU 内使用保守几何回退继续追踪；柜内中间连接线、柜框出口蓝线和外部 FeedLine 最终必须与真实 Pin 严格同轴。普通正交化完成后还会再做一次 RMU 出线最终校验，消除后续处理重新产生的 1 个图形单位小台阶，再通过拉长现有 ConnectLine/FeedLine 关闭短缺口；不移动 RMU 设备本体。</p>
<h3>安全规则</h3>
<p>已有设备/Pin 引用优先；没有引用时，只在标准 Pin 唯一、未被其他线路占用、与线路末段方向一致、距离不超过安全阈值且延长路线不穿过其他设备时才自动连接。多个候选、冲突引用、距离过大或障碍冲突全部跳过并记录。同一标准图元只有在明确形成横排或竖列且端点引用无歧义时才会对齐。Text、DText、Poke 不作为电气连接依据。原线路 ID 保留；需要补连接时只补齐正确的 link/node_area。</p>
<h3>输出</h3>
<p>原始 G 文件不会覆盖。单文件或目录处理结果写入本次 workspace 运行目录，并保留源文件名。“重画”采用原位替换 d 路径，不删除重建 XML 图元，因此不会造成引用断裂。</p>
""",
    ),
    "frame": (
        "图框添加帮助",
        """
<h3>输入方式</h3>
<p>图框添加支持单个 G 文件和 G 文件目录。单文件模式只处理所选文件；目录模式批量处理目录第一层中的所有 .g 文件。</p>
<h3>程序内置模板</h3>
<p>内置模板随 App 一起打包，不依赖开发电脑路径。程序会按四边距调整外框，移动左上和右下组件，并修改标题、Draw、Approve、Issue 和日期。</p>
<h3>客户自定义模板</h3>
<p>程序同样按四边距调整外框线长度，并让模板组件保持相对于最近外框边缘的位置；但不会修改任何 Text 内容、姓名、日期、字体、颜色、线宽或表格内容。</p>
<h3>模板升级</h3>
<p>内置模板是 resources/templates 中独立的 .g 文件，并在 templates.json 中记录版本。以后替换模板文件并重新打包即可发布新版。</p>
<p>两种模式都会重新分配模板图元 ID，避免与目标图中的 ID 冲突。</p>
""",
    ),
    "help": (
        "帮助中心",
        """
<h3>推荐流程</h3>
<ol>
<li>先使用“异常小尺寸图元检测”发现并按需清理疑似残留图元，再在“ID 检查与修复”中确认元素 ID 规则并按需检查/修复重复 ID；需要环网柜处理时进入独立“环网柜处理”，之后再进入“通用基础处理”。</li>
<li>需要多张馈线图时，再使用“馈线图合并”。</li>
<li>按需执行“图形边距调整”和“图框添加”。</li>
</ol>
<p>各页面独立执行、独立选择输入与输出，便于检查每一步结果。</p>
<h3>最近目录</h3>
<p>每个页面会记住用户选择的业务文件/目录和模板位置。外部业务路径被删除或移动时会提示重新选择；workspace 属于可随时删除的运行目录，缺失时静默忽略并在实际运行时自动重建。</p>
<h3>程序图标与发布</h3>
<p>项目内置绿色 app.ico/app.png。PyInstaller 打包脚本使用 app.ico 设置 EXE 图标，App 启动时使用同一图标设置窗口和任务栏图标。</p>
<p>文件夹模式打包后，需要把 dist/GFileStudio 整个目录压缩成 ZIP 分享，不能只发送 GFileStudio.exe。</p>
""",
    ),
}

FIELD_HELP: dict[str, str] = {
    "input_dir": "选择单个待处理 G 文件或包含多个 G 文件的目录。",
    "merge_input_dir": "选择包含 .sln.pic.g 文件的目录。内置图框可自动移除；非内置图框不会参与合并。",
    "output_dir": "输出由程序统一写入 workspace/runs 的本次运行目录。路径只读、不可修改；运行记录仅保留 30 天，需要长期保存请自行复制。",
    "template": "默认使用 App 内置模板，也可以选择客户自定义 .sln.pic.g 模板。",
    "feeder_gap": "相邻两张图真实坐标边界之间的水平距离，默认 300。",
    "merge_margin": "合并图形距离画布四边的距离。数值框不响应鼠标滚轮。",
    "frame_margin": "图框外边线距离目标 G 画布边缘的距离。内置和自定义模板均使用此参数。",
    "content_margin": "主体图形距离 G 画布对应边缘的距离，默认 500。仅 G File Studio 内置图框会被排除并同步调整；其他图框需先删除。",
    "title": "仅内置模板使用；留空时自动取输入文件名去掉 .sln.pic.g 后的内容。",
    "output_name": "合并输出统一使用 .sln.pic.g 后缀；留空生成 MERGED-时间戳.sln.pic.g。",
    "output_suffix": "所有一对一 G 文件处理均固定保持源文件名；不同运行批次由 workspace 运行目录隔离。",
    "draw": "仅内置模板使用。日期默认当前日期，可点击日历按钮修改。",
    "approve": "仅内置模板使用。日期默认当前日期，可点击日历按钮修改。",
    "issue": "仅内置模板使用。日期默认当前日期，可点击日历按钮修改。",
}


APP_HELP_EN: dict[str, tuple[str, str]] = {
    "jeddah_batch": (
        "Jeddah Graphics Batch Processing Help",
        """
<h3>Purpose</h3>
<p>For Jeddah-only batch standardization of single-feeder diagrams. Each input G file is processed and output independently; feeder diagrams are not merged.</p>
<h3>Fixed workflow</h3>
<ol>
<li>First reuse Basic Processing &gt; Graphic Group Processing &gt; Fully Ungroup Graphics: remove every &lt;Merge&gt; and send recognized RMU frames behind devices.</li>
<li>Remove abnormal small ConnectLine / FeedLine / Bus / BusDis elements.</li>
<li>Keep RMU cabinet/type/SMART recognition strict: a rect must contain BusDis, CBreakerDis and ZhaiWaiJieDiDaoZha, and the cabinet name is assigned one-to-one only from Text above the frame. Then set the recognized name text to white at font size 50, centered above its RMU top frame with a 10-unit clear gap.</li>
<li>Finalize RMU frame color from the cabinet-local SMART marker: SMART present = red; no SMART = white.</li>
<li>Determine each RMU switch role from its original devref/symbol filename: names containing Circuit_Breaker are Circuit Breakers and names containing Load_Breaker_Switch are LBS; Y/Q display labels never override that role. SMART cabinets use the targets marked CIRCUIT_BREAKER_SMART / LOAD_BREAKER_SWITCH_SMART, while cabinets without SMART use CIRCUIT_BREAKER_NO_SMART / LOAD_BREAKER_SWITCH_NO_SMART. Targets come only from locally saved classification markers; peer cabinets no longer select or guess a revision. Ground disconnectors are not replaced.</li>
<li>Apply conditional SMR handling: when SMART already exists inside the matched RMU, remove only the external SMR and keep the existing SMART label unchanged; otherwise convert SMR to a top-centered SMART label at font size 20, then run the SMART device validation again.</li>
<li>Reuse the current GLOBAL Symbol Standard connection-normalization rule: for standard-covered two-pin devices, calculate the real break from authoritative pins plus ConnectLine/FeedLine/BusDis endpoints; when each side uniquely reaches a standard pin, snap endpoints, repair reciprocal link/node_area, and remove the bypass ConnectLine. For one-pin symbols, snap only small, unambiguous skew to horizontal/vertical and translate the device with its pin. Ambiguous or large offsets are left unchanged.</li>
<li>Remove RMU rectangles containing Bus and move the corresponding title above the bus.</li>
<li>Move feeder names above buses.</li>
<li>Remove RMU channel_status red Status points. Association reuses the existing RMU red-status positioning rule; only the final action changes from repositioning to deletion.</li>
<li>Remove exact H.T Text markers (case-insensitive after trimming; no substring matching).</li>
<li>Check every distribution RMU recognized by the existing RMU engine for duplicate SMART labels. If one cabinet contains multiple SMART Texts, preserve the first/original XML label and remove only later duplicates without moving or restyling the preserved label.</li>
<li>Remove the exact Text pair 2000.00 + UPDATED_MEASURMENT only when the two separate Text elements are on the same visual line and horizontally adjacent (gap no greater than 10). Distant matches are preserved.</li>
<li>Run ID check and repair using the globally confirmed ID templates.</li>
<li>Reuse Drawing Margin Adjustment with default body margins of 500 on all four sides.</li>
<li>Finally reuse Drawing Frame to add the selected frame template to every processed feeder diagram.</li>
</ol>
<h3>Design principle</h3>
<p>This page only orchestrates existing processing capabilities. RMU cabinet/type/SMART recognition uses the shared strict resolver: a rect must contain BusDis, CBreakerDis and ZhaiWaiJieDiDaoZha, and the cabinet name is accepted only from Text above the frame. Other modules keep their existing default name mode and settings. Jeddah-specific parameters do not overwrite other module settings.</p>
""",
    ),
    "site_profile": ("Symbol Standard Check Help", """<h3>Purpose</h3><p>Business graphic G files provide inspection evidence only. The read-only server symbol-definition library is the only authoritative standard source. The page does not read the server automatically and does not provide manual symbol upload.</p><h3>Manual workflow</h3><p>Click “Read Server Standard (check only)” to read, parse, cache and compare the server catalog. This action does not update the current standard. The operator inventory keeps the symbol-definition path, size, AlignCenter, Pins, source, classification and status visible. The XML element-tag field is intentionally not shown.</p><h3>Authoritative standard library</h3><p>The page reuses shared SSH credentials and recursively reads the configured server symbol root (/home/up8000/data/graph/element by default). It compares path/size/mtime, caches parseable .g files locally, parses authoritative devref/body/size/AlignCenter/pins, and reports same-name content conflicts by SHA256. The server is never modified. Business drawings never contribute authoritative geometry.</p><h3>Versions</h3><p>Server changes are reported only. Nothing is applied until the user explicitly chooses the manual update action; opening or leaving the page does not start a server read.</p><h3>Check and correct</h3><p>Check Symbol Standard is read-only. Instances are found using the active standard and compared with XML/devref, size, AlignCenter and Pins. Correct Standard Issues writes corrected copies only under the workspace; ambiguous cases are skipped and reported rather than guessed.</p><h3>Runtime safety</h3><p>Standard symbols and Profiles are persistent assets in the user-data directory. Files, reports and logs under workspace/runs are disposable runtime output; cleaning runtime output never removes the standards.</p>"""),
    "small_elements": ("Abnormal Small Element Detection Help", """<h3>Purpose</h3><p>Scans &lt;ConnectLine&gt;, &lt;FeedLine&gt;, &lt;Bus&gt; and &lt;BusDis&gt; independently. An element is reported when both w and h are below the user threshold (default 10). Bus orientation is not restricted.</p><h3>Reports and deletion</h3><p>Each scan exports CSV and HTML details including file, element type, XML ID, x/y/w/h and keyid. Select one or more findings using the first-column checkboxes, then process them together. If a selected element has a non-empty keyid, deletion requires explicit confirmation.</p><h3>Relation to feeder merge</h3><p>Main-bus merge no longer applies a special w&lt;10 filter. Suspicious short Bus elements are handled in this module.</p>"""),
    "rmu": ("RMU Processing Help", """<h3>RMU graphic processing</h3><p>The RMU page can leave grouping unchanged or group all recognized RMUs. Whole-file ungrouping is available under Basic Processing → Graphic Group Processing; it removes every &lt;Merge&gt; and sends recognized RMU frames behind devices without changing device attributes, coordinates, IDs or references.</p><p>Poke jump processing has been removed from this page and moved to the standalone Poke Jump Processing module. That module still calls the exact same identify_rmus() engine and reads the same RMU exclusion and smart-marker settings, so future shared RMU-recognition updates are inherited automatically.</p><p>Site RMU Device Profile is an independent tool: the user assigns standard samples to a site, scans them to learn SMART LBS / Circuit Breaker devrefs, saves the profile, and can then run a standalone SMART-device consistency check. It does not participate in the existing Start RMU Processing flow.</p><h3>RMU summary</h3><p>G files are parsed directly without OCR. A valid RMU requires a rect containing BusDis, CBreakerDis and ZhaiWaiJieDiDaoZha. Its name is accepted only from Text above the frame and each concrete Text object can belong to only one RMU; no name is kept when no valid top label exists. ConnectLine, FeedLine, BusDis and Bus are never equipment targets. Cabinet type is primarily derived from Y/Q names with devref as fallback when required. SMART and SMR are classified as intelligent RMUs while preserving the recognition source.</p>"""),
    "basic": ("Basic Processing Help", """<h3>Input</h3><p>Basic Processing supports one G file or a directory of G files.</p><h3>Rule-based processing</h3><p>General attribute replacement and element deletion operate only on direct children of the root Layer. They do not recursively modify internal symbol children.</p><h3>Feeder title positioning</h3><p>When enabled, feeder titles are identified from valid horizontal &lt;Bus&gt; geometry and nearby &lt;Text&gt; content. key_name and keyid are not used. Only the target Text x/y position is changed.</p><h3>Connection repair</h3><p>Uses conservative incremental repair. Existing port numbers and references are preserved; ambiguous or invalid candidates are skipped.</p><h3>Line and bus styles</h3><p>Color changes only lc/lcc. Line style changes only ls: solid=1 and dashed=2. Fill, lw, coordinates, IDs and references are not modified.</p><h3>Output conflicts</h3><p>Safe overwrite writes to a temporary file and validates it before replacing the destination.</p>"""),
    "id_rules": ("Element ID Rule Template Help", """<h3>Selected-sample rule discovery</h3><p>In SSH mode, select representative G files in the remote list and click “Scan Selected G Files for ID Rules”. Only those selected files are downloaded read-only to the workspace and analyzed; the whole server directory is not scanned.</p><p>Candidate prefixes and total lengths are never applied automatically. The operator reviews each candidate and only confirmed rows are added to the local rule cache. A current Admin may then explicitly publish the reviewed local rules to the central id_rules.json; ordinary clients cannot publish.</p><h3>Scan current G</h3><p>“Scan Current G File (ID only)” remains a check/report action. It does not silently add candidates to the template.</p><h3>Duplicate ID repair</h3><p>The first duplicate ID is preserved. Later duplicates receive IDs from the confirmed template, starting after the current maximum valid ID of the same type. Historical gaps are not filled. Unknown, disabled or unconfirmed types cannot generate new IDs.</p>"""),
    "merge": ("Feeder Diagram Merge Help", """<h3>Files and order</h3><p>Input files must end with .sln.pic.g. The user-defined list order is the merge order; the first row is the baseline. Built-in G File Studio frames are removed from in-memory copies before merge, while unknown/customer frames are blocked.</p><h3>Vertical alignment</h3><p>Only non-zero horizontal &lt;Bus&gt; elements are used. &lt;BusDis&gt; does not participate. The topmost Bus is selected; if no Bus exists, the highest graphic element is used.</p><h3>Main-bus processing</h3><p>Supports single- and double-bus processing with manual bus groups. Files in one group must be contiguous. Upper and lower buses remain separate in double-bus mode. Output IDs are validated against confirmed global ID templates.</p><h3>Optional drawing frame</h3><p>“Add drawing frame after merge” is disabled by default. When enabled, feeder merge completes first and then reuses the existing Drawing Frame processor with the selected template and the default 50-unit frame margins. The merge algorithm itself is unchanged.</p>"""),
    "margin": ("Drawing Margin Adjustment Help", """<h3>Main drawing margins</h3><p>The main drawing is translated so its left, top, right and bottom margins match the configured values.</p><h3>Existing frames</h3><p>Only confirmed G File Studio built-in frames are adjusted automatically. Customer or unknown frames stop processing and must be removed first.</p><h3>Input</h3><p>Supports one G file or directory batch processing. Output keeps the original source filename.</p>"""),
    "orthogonalize": ("Orthogonalize Lines Help", """<h3>Purpose</h3><p>Processes each G file independently and analyzes ConnectLine, FeedLine, BusDis, Bus, ACLine and line paths, including d endpoints and node_area/link references. The module first uses symbol w/h, rotation and authoritative Pins already cached by main DMM Element Management in local AppData (no automatic SSH access). A small visual gap to a unique standard Pin is safely extended/snapped to the exact Pin and reciprocal device/line link/node_area is repaired. For recognized RMUs, every branch that exits the cabinet frame is handled alike (Y1/Y2/Q1/Y3/Y4 are not hard-coded): reciprocal link/node_area is followed through intermediate ConnectLines back to the real outgoing Pin of the cabinet LOAD_BREAKER_SWITCH/CIRCUIT_BREAKER. The internal middle line, cabinet-exit blue line and external FeedLine are aligned to that exact Pin axis; same-side external ways are then normalized to one outward axis and short gaps are closed by lengthening existing lines before the normal alignment and orthogonal routing passes.</p><h3>Safety</h3><p>Existing device/Pin references have priority. A reference-free endpoint is attached only when the Pin candidate is unique, unoccupied, direction-compatible with the terminal segment, within the safety distance and the extension does not cross another device. Ambiguous candidates, conflicting references, excessive distance or obstacle collisions are skipped and reported. Text, DText and Poke are never used as electrical topology evidence. Original line IDs are preserved.</p><h3>Output</h3><p>Source G files are never overwritten. Results are written to the managed workspace run directory with the original filenames. Redrawing replaces the path in place rather than deleting and recreating the XML element, so references remain intact.</p>"""),
    "frame": ("Drawing Frame Help", """<h3>Input</h3><p>Supports one G file or a directory of G files.</p><h3>Built-in template</h3><p>The bundled template is adjusted to the configured margins. Title and signature fields are updated only for the built-in template.</p><h3>Custom template</h3><p>Custom frame geometry is adapted without changing Text content, names, dates, fonts, colors, line widths or table content.</p><h3>Template upgrades</h3><p>The built-in template is packaged under resources/templates and versioned in templates.json.</p>"""),
    "help": ("Help Center", """<h3>Recommended workflow</h3><ol><li>Detect abnormal small elements, then check/repair IDs, process RMUs when needed, and run Basic Processing.</li><li>Use Feeder Diagram Merge when multiple feeder drawings must be combined.</li><li>Run Drawing Margin Adjustment and Drawing Frame as required.</li></ol><h3>Recent folders</h3><p>Each page remembers its own recent input and output locations.</p><h3>Packaging</h3><p>The packaged dist/GFileStudio folder must be distributed as a complete folder or ZIP, not as the EXE alone.</p>"""),
}

FIELD_HELP_EN: dict[str, str] = {
    "input_dir": "Select one G file or a directory containing G files.",
    "merge_input_dir": "Select a directory containing .sln.pic.g files. Built-in frames may be removed automatically; unknown frames are blocked.",
    "output_dir": "Output is written to the managed workspace/runs directory. The path is read-only and run data is retained for 30 days.",
    "template": "Use the built-in template or select a custom .sln.pic.g template.",
    "feeder_gap": "Horizontal gap between adjacent drawing coordinate bounds. Default: 300.",
    "merge_margin": "Margins around the merged drawing. Mouse-wheel changes are disabled.",
    "frame_margin": "Distance between the drawing-frame border and the target G canvas edge.",
    "content_margin": "Distance from the main drawing to the corresponding G canvas edge. Default: 500.",
    "title": "Built-in template only. If empty, the input filename without .sln.pic.g is used.",
    "output_name": "Merged output always uses .sln.pic.g. If empty, a timestamped MERGED filename is generated.",
    "output_suffix": "One-to-one G-file processing always preserves the source filename; run folders isolate separate executions.",
    "draw": "Built-in template only. The date defaults to today and can be changed with the calendar button.",
    "approve": "Built-in template only. The date defaults to today and can be changed with the calendar button.",
    "issue": "Built-in template only. The date defaults to today and can be changed with the calendar button.",
}

# v2.18.90 standalone Poke processing help.
APP_HELP["poke"] = (
    "Poke 跳转处理帮助",
    """
<h3>用途</h3>
<p>Poke 跳转已从“环网柜处理”独立出来，统一复用公共 Oracle 数据库和公共 RMU 识别能力。</p>
<h3>前置条件</h3>
<p>不再要求 G 根节点 facID。facID 为空也可以执行设备明细 Poke 与站点跳转 Poke；它只作为报告中的可选源文件信息保留。</p>
<h3>RMU Poke</h3>
<p>严格调用与“环网柜处理”相同的 identify_rmus()；Poke 模块中的 RMU 柜名只认柜体上方 Text，并继续使用同一组名称排除项和智能标记设置。识别出智能 RMU 柜名后，数据库按 DMS_COMBINED_DEVICE.NAME → FEEDER_ID → DMS_FEEDER_DEVICE.NAME/ST_ID → SUBSTATION.NAME/SUBAREA_ID → SUBCONTROLAREA.NAME，为每个 RMU 独立得到所属馈线完整业务名，再追加该 RMU 名。因此同一张变电站馈线总图即使包含多条馈线，也不会被根节点 facID 限制。GRAPH_NAME 不参与命名。</p>
<h3>AR / LBS / SEC 设备 Poke（独立）</h3>
<p>该分支已经从 RMU Poke 独立抽离，可通过“跳转类型”中的独立勾选项单独启用或关闭。它只读取主程序“图元管理”已保存的 <b>AR、LBS、SEC</b> 三种分类标记，并据此找到当前 G 文件中对应的真实设备图元，不做全图设备猜测。</p>
<p><b>名称识别是硬规则：</b>候选必须是 Text，并且必须有明确字体/线颜色且不能是白色。红色（lc=255,0,0 或 lcc=#FF0000）始终优先；只有仍未分配名称的设备才允许使用其他非白色颜色兜底。位置仍按<b>上方 → 右侧 → 全局</b>三级优先级识别，名称到设备的最小矩形间距必须 ≤ 200；这样长名称不会再因为 Text 中心点过远被误判为超距。每个目标设备最多分配一个名称 Text，每个具体 Text 实例/ID 也最多属于一个设备。</p>
<p><b>文字内容不是唯一键。</b>两个 Text 即使 ts 内容完全相同，只要 XML Text ID 不同，就是两个独立名称实例，可以分别分配给两个不同设备。并且一个具体 Text 在 <b>AR/LBS/SEC 设备名称、RMU 名称、站点跳转名称</b> 三种角色之间全局互斥：一旦被某一角色占用，其他角色不再使用。名称识别之外的逻辑保持不变：分配成功后仍沿用原设备明细 Poke 的 Oracle 数据库解析与目标命名规则。<b>AR/LBS/SEC 设备名称查询 Oracle 时按名称格式规范化：</b>视觉分隔符仍会去除，例如 <code>LBS.1103</code> → <code>LBS1103</code>、<code>SEC-2385</code> → <code>SEC2385</code>、<code>SEC 2369</code> → <code>SEC2369</code>；但形如 <code>LBS96527-21240</code>、<code>LBS33513-97376</code> 的“字母前缀 + 数字段 + 横杠 + 数字段”复合编号，横杠属于真实设备名，数据库按原复合编号查询，不删除该横杠。原始名称仍用于报告、Poke 元数据和目标文件名。目标仍为 <code>{区域}-{变电站}-{馈线}-{设备名}.com.pic.g</code>。</p>
<h3>站点跳转 Poke</h3>
<p>站点跳转必须同时满足全部条件：Text 是字母+数字格式（例如 ANS2-44，纯数字不接受）、Text 下方/周围存在<b>独立的可见彩色背景对象</b>、<b>名称 Text 本身不能是红色</b>，并且该 Text 没有被 RMU 或 AR/LBS/SEC 设备名称占用。Text 自身的 fc/fcc 属性不算背景。通过这些强制条件后，仍按 SUBSTATION.NAME → SUBAREA_ID → SUBCONTROLAREA.NAME 查询得到完整站点名；数据库查询逻辑不变。若站点名称 100 以内存在括号环网柜名（例如 (35033)），优先追加对应 <code>locateLabel</code>；多个候选时只取距离最近的一个；如果没有合格环网柜名，则把站点间隔后缀按 AH3+数字转换，例如 RDS-09 → <code>AH309</code>，目标为 <code>JED-CTL-RDS.sln.pic.g?locateLabel=AH309&amp;&amp;scaleFlag=true</code>。条件不满足时不创建或更新站点 Poke。</p>
<p>已有 Poke 或几何形状都不能替代彩色背景。相邻括号环网柜名距离必须不超过 100；若有多个候选，只取距离站点名称最近的一个；只有没有合格环网柜名时才使用站点间隔后缀备用规则。数据库唯一匹配成功后才允许修改，多个相关 Poke 删除多余项仅保留一个。</p>
<h3>Poke 目标文件命名规则</h3>
<p>智能环网柜名字 Poke 目标文件：<code>{区域}-{变电站}-{馈线}-{RMU}.com.pic.g</code></p>
<p>AR / LBS / SEC 设备名字 Poke 目标文件：<code>{区域}-{变电站}-{馈线}-{设备名}.com.pic.g</code></p>
<p>站点跳转 Poke 目标文件：<code>{区域}-{变电站}.sln.pic.g</code></p>
<h3>样式</h3>
<p>RMU Poke 继续使用既有蓝色/Invisible 属性规则。站点跳转 Poke 则统一使用用户提供的 JM2-J2 参考 Poke 属性模板：除每个对象自己的 id、x/y/w/h、ahref 及 G File Studio 跟踪元数据外，其余 Poke 属性完全复制参考对象；已有站点 Poke 也会按该模板规范化。</p>
<h3>处理报告</h3>
<p>每次成功执行都会在本次运行目录生成 CSV/HTML Poke 报告。报告汇总公共 RMU 识别数量、智能 RMU 数、AR/LBS/SEC 分类设备及名称分配数量、新增/更新设备明细 Poke、站点跳转候选与成功解析数量、新增/更新站点跳转 Poke、重复 Poke 清理数量；明细会记录实际写入的 ahref，以及每个未加跳转候选的具体原因。</p>
""",
)
APP_HELP_EN["poke"] = (
    "Poke Jump Processing Help",
    """
<h3>Purpose</h3>
<p>Poke jump processing is independent from RMU Processing and reuses the shared Oracle service and shared RMU recognition engine.</p>
<h3>Requirement</h3>
<p>A root facID is no longer required. Blank facID does not block equipment-detail or station-jump Pokes; it is kept only as optional source metadata in the report.</p>
<h3>RMU Poke</h3>
<p>The module calls the same identify_rmus() used by RMU Processing and reads the same name-direction, exclusion and smart-marker settings. Each recognized smart RMU name independently resolves DMS_COMBINED_DEVICE.NAME → FEEDER_ID → DMS_FEEDER_DEVICE.NAME/ST_ID → SUBSTATION.NAME/SUBAREA_ID → SUBCONTROLAREA.NAME. This allows one station overview drawing to contain RMUs from multiple feeders without relying on the root facID. GRAPH_NAME is not used.</p>
<h3>AR / LBS / SEC device Poke (independent)</h3>
<p>This branch is separated from RMU Poke. It can be enabled independently or run directly with the “AR/LBS/SEC Only” button. It uses only the locally saved server-symbol classifications <b>AR, LBS and SEC</b> to select real target device instances in the current G file.</p>
<p><b>Name recognition is a hard contract:</b> the candidate must have an explicit non-white Text font/line color. Red (lc=255,0,0 or lcc=#FF0000) is always assigned first; only devices still unnamed may use another non-white color. White Text is never accepted. Candidates keep the strict <b>TOP → RIGHT → GLOBAL</b> location priority and must stay within 200 geometric units, measured by the minimum visual gap between the Text rectangle and device rectangle. Each device receives at most one name and each concrete Text instance/ID can belong to at most one device.</p>
<p>The rendered text content is <b>not</b> the identity key. Two Text elements with the same ts content remain independent when their XML Text IDs differ, so they can be assigned to different devices. A concrete Text is globally exclusive across the <b>AR/LBS/SEC device-name, RMU-name and station-jump-name</b> roles: once one role owns it, the other roles cannot reuse it. Everything after name recognition is unchanged. <b>For AR/LBS/SEC only, the Oracle lookup name is format-aware:</b> visual separators are removed (<code>LBS.1103</code> → <code>LBS1103</code>, <code>SEC-2385</code> → <code>SEC2385</code>, <code>SEC 2369</code> → <code>SEC2369</code>), but a compound ID shaped as letters + digits + hyphen + digits keeps that internal hyphen, e.g. <code>LBS96527-21240</code> remains <code>LBS96527-21240</code>. The original rendered name is retained in reports, Poke metadata and target filenames. The target naming rule remains <code>{area}-{substation}-{feeder}-{device}.com.pic.g</code>.</p>
<h3>Station-jump Poke</h3>
<p>A station-jump label must satisfy every hard condition: its Text must contain both letters and digits (for example ANS2-44; a pure number is rejected), it must sit on a <b>separate visible colored background object</b>, <b>the name Text itself must not be red</b>, and that Text must not already be owned by an RMU or AR/LBS/SEC device name. The Text element's own fc/fcc attributes do not count as a background. Only then does the existing SUBSTATION.NAME → SUBAREA_ID → SUBCONTROLAREA.NAME lookup run. A parenthesized RMU name within 100 drawing units is preferred as <code>locateLabel</code>; when several qualify, only the nearest one is used; when no qualifying RMU name is available, a numeric station suffix is converted with the AH3 prefix, for example RDS-09 → <code>AH309</code>, producing <code>JED-CTL-RDS.sln.pic.g?locateLabel=AH309&amp;&amp;scaleFlag=true</code>. If any condition fails, no station Poke is created or updated.</p>
<p>An existing Poke or geometry alone cannot replace the colored background. Ambiguous adjacent RMU names do not produce a guessed locate parameter; the station-interval fallback is used only when no RMU name is available. Only a unique Oracle match may modify XML, and duplicate related Pokes are reduced to one.</p>
<h3>Target drawing files</h3>
<p><b>RMU Poke</b> targets use <code>{area}-{substation}-{feeder}-{RMU}.com.pic.g</code>, for example <code>JED-NTH-ABH-AH303-34661.com.pic.g</code>.</p>
<p><b>AR / LBS / SEC device Poke</b> targets use <code>{area}-{substation}-{feeder}-{device}.com.pic.g</code>.</p>
<p><b>Station-jump Poke</b> targets use <code>{area}-{substation}.sln.pic.g</code>, for example <code>JED-CTL-DHN.sln.pic.g</code>.</p>
<p>The Poke module only writes/repairs ahref values in the current G file; it does not generate those target drawings. Prepare the target G files in advance, make sure the actual filenames exactly match the ahref values, and keep them accessible to the runtime system; otherwise clicking the Poke cannot open the target drawing.</p>
<h3>Style</h3>
<p>RMU Pokes keep the existing blue/Invisible property rule. Station-jump Pokes use the user-provided JM2-J2 reference Poke as their canonical property template: every non-geometric Poke property is copied from the reference, while id, x/y/w/h, ahref and G File Studio tracking metadata remain target-specific.</p>
<h3>Processing Report</h3>
<p>Each successful run writes CSV/HTML Poke reports to the run directory. The report summarizes shared RMU recognition, smart RMUs, AR/LBS/SEC classified devices and name assignments, added/updated equipment-detail Pokes, station-jump candidates/resolutions, added/updated station Pokes, duplicate cleanup, the exact written ahref, and the specific reason for every candidate whose jump was not added.</p>
""",
)
