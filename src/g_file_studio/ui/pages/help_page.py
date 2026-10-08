from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser

from g_file_studio.ui.help_content import APP_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.widgets import InfoBanner


class HelpPage(BasePage):
    def __init__(self, parent=None) -> None:
        help_title, help_html = APP_HELP["help"]
        super().__init__(
            "帮助中心",
            "查看推荐流程、页面用途、目录说明和常见问题。按 F1 可随时打开本页面。",
            help_title,
            help_html,
            parent,
        )
        self.layout.addWidget(
            InfoBanner("鼠标停留在按钮或字段上可以查看简短提示；圆形问号可查看详细说明。")
        )

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMinimumHeight(560)
        help_body_zh = """
<h2>G File Studio 使用说明</h2>
<h3>1. 基础处理</h3>
<p>包含通用属性替换、元素删除、重复 ID 检查与修复、环网柜图元处理，以及线路和母线颜色修改。所有规则只作用于 G 根节点直属 Layer 的直接子元素。</p>
<p>含 SMART 的环网柜着色只修改对应 rect 外框，不修改 SMART 字体或其他环网柜。</p>
<h3>2. 馈线图合并</h3>
<p>把待合并文件放入任意目录即可。文件名无需包含站点或馈线号，但必须以 <b>.sln.pic.g</b> 结尾。</p>
<ul>
<li>扫描后可使用上移、下移、置顶、置底自由定义顺序；未调整时使用自然排序。</li>
<li>有顶部水平母线时按母线对齐。</li>
<li>没有母线时按最高图元对齐。</li>
<li>G File Studio 内置图框会在内存副本中移除后参与合并；客户或未知图框禁止参与。</li>
</ul>
<h3>3. 图形边距调整</h3>
<p>主体图形默认距离画布四边各 500；G File Studio 内置图框会保留并同步调整，不修改其文字和签字内容。客户图框或来源不明的图框需先删除。</p>
<h3>4. 图框添加</h3>
<p>适合给没有图框的文件添加 SLD 图框、标题和签字信息；输出文件保持源文件名不变并保存到输出目录。</p>
<h3>目录与本地持久化</h3>
<pre>
workspace/input         本地输入/临时输入
workspace/remote_input  SSH 只读下载的业务 G 快照
workspace/runs          所有模块运行输出（自动保留 30 天）
workspace/work          处理中间数据
</pre>
<p><b>workspace 是一次性工作区，整个目录可以随时删除。</b> 图元分类、服务器图元缓存、SSH/Oracle 配置、管理员状态、ID 规则和图元标准库都保存在 AppData 下，不得写入 workspace。</p>
<h3>文件安全</h3>
<ul>
<li>输入文件不会被直接覆盖。</li>
<li>输出写入临时文件后会重新解析 XML，验证通过再保存。</li>
<li>建议使用 Git 管理源码，不要提交 .venv 和 workspace 中的业务文件。</li>
</ul>
<h3>路径记忆</h3>
<p>完整路径保存在 AppData 下的独立 user_settings.ini。程序会恢复单文件/目录模式、输入路径、输出目录和客户模板路径；失效路径会提示并清除。</p>
<h3>未来扩展</h3>
<p>新的 G 文件规则优先集成到基础处理页，通过统一的“开始基础处理”按钮执行。</p>
"""
        help_body_en = """
<h2>G File Studio User Guide</h2>
<h3>1. Basic Processing</h3>
<p>Provides general attribute replacement, element deletion, ID checking and repair, RMU graphic processing, and line/bus style processing. Rules operate only on direct children of Layers directly under the G-file root.</p>
<p>SMART RMU frame coloring changes only the corresponding rect border; it does not modify SMART text or unrelated RMUs.</p>
<h3>2. Feeder Diagram Merge</h3>
<p>Place the feeder files to be merged in any directory. Filenames do not need to contain a station or feeder number, but they must end with <b>.sln.pic.g</b>.</p>
<ul>
<li>After scanning, use Move Up, Move Down, Move to Top, and Move to Bottom to define the merge order. Natural order is used if no manual ordering is applied.</li>
<li>If a top horizontal Bus exists, drawings are aligned to that Bus.</li>
<li>If no Bus exists, drawings are aligned using the highest graphic element.</li>
<li>Built-in G File Studio drawing frames are removed from in-memory copies before merging. Customer or unknown frames are not allowed to participate.</li>
</ul>
<h3>3. Drawing Margin Adjustment</h3>
<p>The default main-drawing margin is 500 on all four sides. A confirmed built-in G File Studio frame is preserved and adjusted with the drawing; its text and signature content are not changed. Customer or unknown frames must be removed first.</p>
<h3>4. Drawing Frame</h3>
<p>Adds an SLD frame, title, and signature information to drawings that do not already have a frame. Output keeps the original source filename and is written to the managed output directory.</p>
<h3>Workspace and persistent local data</h3>
<pre>
workspace/input         Local or temporary input
workspace/remote_input  Read-only business-G snapshots downloaded by SSH
workspace/runs          Output from all modules (retained for 30 days)
workspace/work          Processing intermediates
</pre>
<p><b>The entire workspace is disposable.</b> Symbol classifications, server-symbol cache, SSH/Oracle settings, administrator state, ID rules and persistent symbol standards live under AppData and must never be stored in workspace.</p>
<h3>File Safety</h3>
<ul>
<li>Input files are never overwritten directly.</li>
<li>Output is first written to a temporary file, reparsed as XML, and saved only after validation succeeds.</li>
<li>Use Git for source control and do not commit .venv or business files under workspace.</li>
</ul>
<h3>Path Memory</h3>
<p>Saved paths are stored in the dedicated user_settings.ini under AppData. The application restores single-file/directory mode, input paths, output directories, and customer template paths. Invalid saved paths are reported and cleared.</p>
<h3>Future Extensions</h3>
<p>New G-file rules should normally be integrated into Basic Processing and executed through its unified processing action.</p>
"""
        browser.setProperty("_i18n_html", help_body_zh)
        browser.setProperty("_i18n_html_en", help_body_en)
        browser.setHtml(help_body_zh)
        self.layout.addWidget(browser, 1)
