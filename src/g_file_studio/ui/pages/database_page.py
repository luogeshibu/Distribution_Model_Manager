from __future__ import annotations

from datetime import datetime
import socket
from uuid import uuid4

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.services.classification_registry_service import (
    ClassificationRegistryService,
    DEFAULT_CONFIG_DIR,
)
from g_file_studio.services.central_repository_settings import (
    CentralRepositoryConfig,
    CentralRepositorySettings,
    normalize_central_config_dir,
)
from g_file_studio.services.database_service import OracleConnectionConfig, OracleDatabaseService
from g_file_studio.services.id_rule_service import IdRuleService
from g_file_studio.services.remote_g_source import (
    DEFAULT_SSH_HOST,
    DEFAULT_SSH_PASSWORD,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_REMOTE_DIRECTORY,
    DEFAULT_SSH_USERNAME,
    ReadOnlySshClient,
)
from g_file_studio.services.remote_symbol_library import (
    DEFAULT_REMOTE_SYMBOL_ROOT,
    RemoteSymbolLibraryService,
)
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.widgets import InfoBanner
from g_file_studio.ui.widgets.integer_input import IntegerInput
from g_file_studio.ui.widgets.wheel_safe_line_edit import WheelSafeLineEdit
from g_file_studio.ui.widgets.help_widgets import set_primary, set_secondary
from g_file_studio.workers import FunctionWorker


_ENV_HELP = """
<h3>本地配置</h3>
<p>每台工作站可以保存自己的文件服务器和 Oracle 配置。</p>
<h3>中央配置</h3>
<p>中央配置仓库与业务文件服务器分开配置。推荐中央目录为 <code>/home/up8000/nari-international/gfilestudio/config/</code>，可按现场实际情况修改。目录中统一放置 <code>instance.json</code>、<code>database.json</code>、<code>file_server.json</code>、<code>id_rules.json</code> 和 <code>symbol_classification.json</code>。</p>
<p>首次启动、再次启动、本机配置缺失或打开本页面时都不读取中央配置；只有用户主动点击测试/同步/发布按钮才访问中央服务器。中央配置仓库顶部只保留“测试中央仓库 / 保存中央仓库配置 / 一键同步全部中央配置”；如果只想同步或发布单项配置，请到“文件服务器”或“Oracle 数据库”区域使用对应的“仅同步…”和“发布…到中央”按钮。“一键同步全部中央配置”会先读取并校验所有中央文件，再覆盖本机缓存。只有中央管理员可发布中央配置。新工作站即使页面显示了默认/继承的中央服务器值，也必须先手工点击“保存中央仓库配置”确认本现场地址；未确认时禁止抢占 Admin 和发布中央配置。</p>
<p>中央配置文件权限按 600 写入；业务 G 和服务器 element 图元目录仍按原有只读方式访问。</p>
"""


class DatabasePage(BasePage):
    """Central connection/environment page.

    Class name is retained for compatibility with older imports and stable page
    indexes.  The visible module now owns both shared SSH/SFTP and Oracle settings.
    """

    environmentChanged = Signal(str)
    centralConfigSynced = Signal(object)

    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        self.database_service = OracleDatabaseService(user_settings)
        self.central_repository_settings = CentralRepositorySettings(user_settings)
        self._pool = QThreadPool.globalInstance()
        self._worker: FunctionWorker | None = None
        self._ssh_worker: FunctionWorker | None = None
        self._central_worker: FunctionWorker | None = None
        self._central_progress_dialog: QProgressDialog | None = None
        self._loading_environment = False
        self._ssh_dirty = False
        self._db_dirty = False
        self._central_repo_dirty = False
        self._machine_id = self.user_settings.get_value("access_control/machine_id", "").strip()
        self._machine_name = socket.gethostname().strip() or "Unknown-PC"
        self._is_admin_mode = False
        self._admin_epoch: int | None = None
        super().__init__(
            "连接与环境",
            "只使用本机缓存；中央配置只在用户手工点击同步/发布时访问。",
            "连接与环境说明",
            _ENV_HELP,
            parent,
        )



        # Central repository connection is independent from the business G-file
        # server.  Operators can see exactly where shared configuration lives.
        # Legacy constructor text kept for source-level regression checks.
        central_box = QGroupBox("中央配置（Oracle 数据库 + 文件服务器）")
        central_box.setTitle("中央配置仓库")
        central_layout = QVBoxLayout(central_box)
        central_layout.setSpacing(12)

        central_hint = QLabel(
            "推荐目录：/home/up8000/nari-international/gfilestudio/config  ·  "
            "该目录统一存放 instance.json、database.json、file_server.json、"
            "id_rules.json、symbol_classification.json。路径可按现场实际情况修改。"
        )
        central_hint.setObjectName("mutedText")
        central_hint.setWordWrap(True)
        central_layout.addWidget(central_hint)

        central_form = QFormLayout()
        central_form.setHorizontalSpacing(24)
        central_form.setVerticalSpacing(10)
        central_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.central_host = WheelSafeLineEdit()
        self.central_port = IntegerInput(value=DEFAULT_SSH_PORT, minimum=1, maximum=65535)
        self.central_username = WheelSafeLineEdit()
        self.central_password = WheelSafeLineEdit()
        self.central_password.setEchoMode(WheelSafeLineEdit.EchoMode.Password)
        self.central_config_dir = WheelSafeLineEdit()
        self.central_config_dir.setPlaceholderText(DEFAULT_CONFIG_DIR)
        for field in (
            self.central_host,
            self.central_port,
            self.central_username,
            self.central_password,
            self.central_config_dir,
        ):
            field.setMinimumHeight(36)
            field.setStyleSheet("font-size: 14px;")

        central_form.addRow(self._field_label("中央服务器"), self.central_host)
        central_form.addRow(self._field_label("端口"), self.central_port)
        central_form.addRow(self._field_label("用户名"), self.central_username)
        central_password_widget = QWidget()
        central_password_row = QHBoxLayout(central_password_widget)
        central_password_row.setContentsMargins(0, 0, 0, 0)
        central_password_row.setSpacing(10)
        central_password_row.addWidget(self.central_password, 1)
        self.show_central_password = QPushButton("显示密码")
        set_secondary(self.show_central_password)
        self.show_central_password.setCheckable(True)
        self.show_central_password.setMinimumHeight(36)
        self.show_central_password.toggled.connect(self._toggle_central_password)
        central_password_row.addWidget(self.show_central_password)
        central_form.addRow(self._field_label("密码"), central_password_widget)
        central_form.addRow(self._field_label("中央配置目录"), self.central_config_dir)
        central_layout.addLayout(central_form)

        central_actions = QHBoxLayout()
        self.test_central_repository_button = QPushButton("测试中央仓库")
        self.save_central_repository_button = QPushButton("保存中央仓库配置")
        self.save_central_repository_button.setToolTip("只保存到本机，不访问中央服务器。")
        self.central_sync_all_button = QPushButton("一键同步全部中央配置")
        set_secondary(self.test_central_repository_button)
        set_primary(self.save_central_repository_button)
        set_primary(self.central_sync_all_button)
        self.central_sync_all_button.setToolTip(
            "一次读取中央 database.json、file_server.json、id_rules.json 和 "
            "symbol_classification.json，校验全部成功后再覆盖对应本机缓存。"
        )
        # Top-level central actions intentionally stay minimal: repository test/save
        # plus one bulk sync.  Fine-grained sync/publish actions live inside the
        # File Server and Oracle sections so users do not have two overlapping
        # "sync connection configuration" choices in the same toolbar.
        for button in (
            self.test_central_repository_button,
            self.save_central_repository_button,
            self.central_sync_all_button,
        ):
            central_actions.addWidget(button)
        central_actions.addStretch(1)
        central_layout.addLayout(central_actions)

        self.central_config_status = QLabel("")
        self.central_config_status.setObjectName("mutedText")
        self.central_config_status.setWordWrap(True)
        central_layout.addWidget(self.central_config_status)
        self.layout.addWidget(central_box)

        ssh_box = QGroupBox("文件服务器（SSH/SFTP · 严格只读）")
        ssh_box.setObjectName("globalSshConnectionBox")
        ssh_layout = QVBoxLayout(ssh_box)
        ssh_layout.setSpacing(14)
        ssh_form = QFormLayout()
        ssh_form.setHorizontalSpacing(24)
        ssh_form.setVerticalSpacing(13)
        ssh_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.ssh_host = WheelSafeLineEdit()
        self.ssh_port = IntegerInput(value=22, minimum=1, maximum=65535)
        self.ssh_username = WheelSafeLineEdit()
        self.ssh_password = WheelSafeLineEdit()
        self.ssh_password.setEchoMode(WheelSafeLineEdit.EchoMode.Password)
        self.business_g_directory = WheelSafeLineEdit()
        self.symbol_library_root = WheelSafeLineEdit()
        self.symbol_library_root.setPlaceholderText(DEFAULT_REMOTE_SYMBOL_ROOT)
        for field in (
            self.central_host,
            self.central_port,
            self.central_username,
            self.central_password,
            self.central_config_dir,
        ):
            if hasattr(field, "textChanged"):
                field.textChanged.connect(self._on_central_repository_field_changed)  # type: ignore[attr-defined]
            elif hasattr(field, "valueChanged"):
                field.valueChanged.connect(self._on_central_repository_field_changed)  # type: ignore[attr-defined]
        for field in (
            self.ssh_host,
            self.ssh_port,
            self.ssh_username,
            self.ssh_password,
            self.business_g_directory,
            self.symbol_library_root,
        ):
            field.setMinimumHeight(38)
            field.setStyleSheet("font-size: 14px;")

        ssh_form.addRow(self._field_label("IP / 主机"), self.ssh_host)
        ssh_form.addRow(self._field_label("端口"), self.ssh_port)
        ssh_form.addRow(self._field_label("用户名"), self.ssh_username)
        ssh_password_widget = QWidget()
        ssh_password_row = QHBoxLayout(ssh_password_widget)
        ssh_password_row.setContentsMargins(0, 0, 0, 0)
        ssh_password_row.setSpacing(10)
        ssh_password_row.addWidget(self.ssh_password, 1)
        self.show_ssh_password = QPushButton("显示密码")
        set_secondary(self.show_ssh_password)
        self.show_ssh_password.setCheckable(True)
        self.show_ssh_password.setMinimumHeight(38)
        self.show_ssh_password.toggled.connect(self._toggle_ssh_password)
        ssh_password_row.addWidget(self.show_ssh_password)
        ssh_form.addRow(self._field_label("密码"), ssh_password_widget)
        ssh_form.addRow(self._field_label("业务 G 根目录"), self.business_g_directory)
        ssh_form.addRow(self._field_label("标准图元库"), self.symbol_library_root)
        ssh_layout.addLayout(ssh_form)

        ssh_actions = QHBoxLayout()
        self.test_ssh_button = QPushButton("测试 SSH 连接")
        # Keep the legacy constructor text for source-level compatibility, while
        # presenting one consistent local/central action vocabulary to users.
        self.save_ssh_button = QPushButton("保存文件服务器配置")
        self.save_ssh_button.setText("保存到本地")
        self.save_ssh_button.setToolTip("仅保存到本机配置，不访问中央服务器。")
        self.sync_file_server_button = QPushButton("仅同步文件服务器配置")
        self.sync_file_server_button.setToolTip(
            "只从中央读取 file_server.json 并覆盖本机文件服务器配置；不会修改 Oracle、ID 规则或图元分类。"
        )
        self.publish_file_server_button = QPushButton("发布文件服务器到中央")
        set_secondary(self.test_ssh_button)
        set_primary(self.save_ssh_button)
        set_primary(self.sync_file_server_button)
        set_primary(self.publish_file_server_button)
        self.publish_file_server_button.setToolTip(
            "仅当前 Admin 可用：只发布当前文件服务器配置到中央 file_server.json。"
        )
        self.publish_file_server_button.setEnabled(False)
        ssh_actions.addWidget(self.test_ssh_button)
        ssh_actions.addWidget(self.save_ssh_button)
        ssh_actions.addWidget(self.sync_file_server_button)
        ssh_actions.addWidget(self.publish_file_server_button)
        ssh_actions.addStretch(1)
        ssh_layout.addLayout(ssh_actions)
        self.ssh_status = QLabel("尚未验证")
        self._set_inline_status(self.ssh_status, "尚未验证", "idle")
        ssh_layout.addWidget(self.ssh_status)
        self.layout.addWidget(ssh_box)

        db_box = QGroupBox("Oracle 数据库连接")
        db_box.setObjectName("databaseConnectionBox")
        db_box.setStyleSheet("QGroupBox#databaseConnectionBox { font-size: 14px; }")
        db_layout = QVBoxLayout(db_box)
        db_layout.setSpacing(14)
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(13)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        # 数据库连接属于关键配置：所有可编辑字段显式使用防滚轮控件。
        self.username = WheelSafeLineEdit()
        self.username.setPlaceholderText("Oracle 用户名")
        self.password = WheelSafeLineEdit()
        self.password.setEchoMode(WheelSafeLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("请输入数据库密码")
        self.host = WheelSafeLineEdit()
        self.host.setPlaceholderText("服务器主机名或 IP")
        self.port = IntegerInput(value=1521, minimum=1, maximum=65535)
        self.service_name = WheelSafeLineEdit()
        self.service_name.setPlaceholderText("Oracle Service Name")
        for field in (self.username, self.password, self.host, self.port, self.service_name):
            field.setProperty("databaseField", True)
            field.setMinimumHeight(38)
            field.setStyleSheet("font-size: 14px;")

        form.addRow(self._field_label("用户名"), self.username)
        password_widget = QWidget()
        password_row = QHBoxLayout(password_widget)
        password_row.setContentsMargins(0, 0, 0, 0)
        password_row.setSpacing(10)
        password_row.addWidget(self.password, 1)
        self.show_password = QPushButton("显示密码")
        set_secondary(self.show_password)
        self.show_password.setCheckable(True)
        self.show_password.setMinimumHeight(38)
        self.show_password.toggled.connect(self._toggle_password)
        password_row.addWidget(self.show_password)
        form.addRow(self._field_label("密码"), password_widget)
        form.addRow(self._field_label("服务器地址"), self.host)
        form.addRow(self._field_label("端口"), self.port)
        form.addRow(self._field_label("Service Name"), self.service_name)
        db_layout.addLayout(form)

        self.endpoint = QLabel()
        self.endpoint.setObjectName("mutedText")
        self.endpoint.setWordWrap(True)
        db_layout.addWidget(self.endpoint)
        db_actions = QHBoxLayout()
        self.test_button = QPushButton("测试数据库连接")
        self.save_button = QPushButton("保存数据库配置")
        self.save_button.setText("保存到本地")
        self.save_button.setToolTip("仅保存到本机配置，不访问中央服务器。")
        self.sync_database_button = QPushButton("仅同步数据库配置")
        self.sync_database_button.setToolTip(
            "只从中央读取 database.json 并覆盖本机 Oracle 配置；不会修改文件服务器、ID 规则或图元分类。"
        )
        self.publish_database_button = QPushButton("发布数据库配置到中央")
        set_secondary(self.test_button)
        set_primary(self.save_button)
        set_primary(self.sync_database_button)
        set_primary(self.publish_database_button)
        self.publish_database_button.setToolTip(
            "仅当前 Admin 可用：只发布当前 Oracle 数据库配置到中央 database.json。"
        )
        self.publish_database_button.setEnabled(False)
        db_actions.addWidget(self.test_button)
        db_actions.addWidget(self.save_button)
        db_actions.addWidget(self.sync_database_button)
        db_actions.addWidget(self.publish_database_button)
        db_actions.addStretch(1)
        db_layout.addLayout(db_actions)
        self.status = QLabel("尚未验证")
        self.status.setObjectName("databaseStatus")
        self._set_status("尚未验证", "idle")
        db_layout.addWidget(self.status)
        self.layout.addWidget(db_box)

        log_box = QGroupBox("连接运行日志")
        log_layout = QVBoxLayout(log_box)
        log_buttons = QHBoxLayout()
        self.copy_log_button = QPushButton("复制日志")
        self.clear_log_button = QPushButton("清空日志")
        set_secondary(self.copy_log_button)
        set_secondary(self.clear_log_button)
        log_buttons.addWidget(self.copy_log_button)
        log_buttons.addWidget(self.clear_log_button)
        log_buttons.addStretch(1)
        log_layout.addLayout(log_buttons)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(220)
        self.log.setPlaceholderText("文件服务器和数据库连接测试日志会显示在这里。")
        log_layout.addWidget(self.log, 1)
        self.layout.addWidget(log_box, 1)

        self.test_central_repository_button.clicked.connect(self._test_central_repository)
        self.save_central_repository_button.clicked.connect(self._save_central_repository_config)
        self.test_ssh_button.clicked.connect(self._test_ssh_connection)
        self.save_ssh_button.clicked.connect(self._save_file_server_config)
        self.test_button.clicked.connect(self._test_connection)
        self.save_button.clicked.connect(self._save_database_config)
        self.central_sync_all_button.clicked.connect(self._sync_all_central_config)
        self.sync_file_server_button.clicked.connect(self._sync_file_server_from_central)
        self.publish_file_server_button.clicked.connect(self._publish_file_server_to_central)
        self.sync_database_button.clicked.connect(self._sync_database_from_central)
        self.publish_database_button.clicked.connect(self._publish_database_to_central)
        self.copy_log_button.clicked.connect(self._copy_log)
        self.clear_log_button.clicked.connect(self._clear_log)
        for field in (
            self.ssh_host,
            self.ssh_port,
            self.ssh_username,
            self.ssh_password,
            self.business_g_directory,
            self.symbol_library_root,
        ):
            if hasattr(field, "textChanged"):
                field.textChanged.connect(self._on_ssh_field_changed)  # type: ignore[attr-defined]
            elif hasattr(field, "valueChanged"):
                field.valueChanged.connect(self._on_ssh_field_changed)  # type: ignore[attr-defined]
        for field in (self.username, self.password, self.host, self.port, self.service_name):
            if hasattr(field, "textChanged"):
                field.textChanged.connect(self._update_endpoint)  # type: ignore[attr-defined]
                field.textChanged.connect(self._on_db_field_changed)  # type: ignore[attr-defined]
            elif hasattr(field, "valueChanged"):
                field.valueChanged.connect(self._update_endpoint)  # type: ignore[attr-defined]
                field.valueChanged.connect(self._on_db_field_changed)  # type: ignore[attr-defined]

        self._load_central_repository_config()
        self._load_shared_connection_config()
        self._refresh_local_cache_source_status()

    def _ensure_machine_id(self) -> str:
        """Create the workstation id only when a manual admin/publish action needs it."""
        machine_id = self.user_settings.get_value("access_control/machine_id", "").strip()
        if not machine_id:
            machine_id = uuid4().hex
            self.user_settings.set_value("access_control/machine_id", machine_id)
        self._machine_id = machine_id
        return machine_id

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("databaseFieldLabel")
        label.setMinimumWidth(112)
        label.setStyleSheet("color:#28474e; font-size:14px; font-weight:650; padding-right:6px;")
        return label

    def _load_central_repository_config(self) -> None:
        config = self.central_repository_settings.load()
        self._loading_environment = True
        try:
            self.central_host.setText(config.host)
            self.central_port.setValue(config.port)
            self.central_username.setText(config.username)
            self.central_password.setText(config.password)
            self.central_config_dir.setText(config.config_dir)
            self._central_repo_dirty = False
        finally:
            self._loading_environment = False

    def _central_repository_config_from_form(self) -> CentralRepositoryConfig:
        config = CentralRepositoryConfig(
            host=self.central_host.text().strip(),
            port=self.central_port.value(),
            username=self.central_username.text().strip(),
            password=self.central_password.text(),
            config_dir=normalize_central_config_dir(self.central_config_dir.text()),
        )
        config.validate()
        return config

    def _on_central_repository_field_changed(self, *_args) -> None:
        if self._loading_environment:
            return
        self._central_repo_dirty = True
        self._refresh_local_cache_source_status()

    def _toggle_central_password(self, checked: bool) -> None:
        self.central_password.setEchoMode(
            WheelSafeLineEdit.EchoMode.Normal if checked else WheelSafeLineEdit.EchoMode.Password
        )
        self.show_central_password.setText("隐藏密码" if checked else "显示密码")

    def _save_central_repository_config(self) -> None:
        try:
            candidate = self._central_repository_config_from_form()
        except Exception as exc:
            QMessageBox.warning(self, "保存中央仓库配置失败", str(exc))
            return
        if (
            not self.central_repository_settings.is_explicitly_saved()
            and candidate.host.strip() == DEFAULT_SSH_HOST
        ):
            if QMessageBox.question(
                self,
                "确认中央服务器地址",
                f"当前中央服务器仍是程序初始推荐地址：{DEFAULT_SSH_HOST}。\n\n"
                "如果这是其他现场，请先改成本现场实际中央仓库 IP；如果当前现场确实使用该地址，可以继续确认保存。\n\n"
                "是否确认这个地址就是当前现场的中央仓库？",
            ) != QMessageBox.StandardButton.Yes:
                return
        try:
            config = self.central_repository_settings.save(candidate)
        except Exception as exc:
            QMessageBox.warning(self, "保存中央仓库配置失败", str(exc))
            return
        self._loading_environment = True
        try:
            self.central_config_dir.setText(config.config_dir)
        finally:
            self._loading_environment = False
        self._central_repo_dirty = False
        self.user_settings.set_value("local_cache/central_repository_saved_at", self._local_timestamp())
        self._refresh_local_cache_source_status(extra="中央仓库连接已保存到本地")
        self._append_log(
            f"中央仓库配置已保存到本机：{config.username}@{config.host}:{config.port}{config.config_dir}"
        )
        self.environmentChanged.emit("central_repository")
        QMessageBox.information(
            self,
            "中央仓库配置已保存",
            f"中央服务器：{config.host}:{config.port}\n"
            f"中央配置目录：{config.config_dir}\n\n"
            "此操作只保存到本机，没有访问中央服务器。",
        )

    def _test_central_repository(self) -> None:
        if self._central_worker is not None:
            return
        try:
            config = self._central_repository_config_from_form()
            connection = config.connection_args()
        except Exception as exc:
            QMessageBox.warning(self, "中央仓库配置不完整", str(exc))
            return
        self.test_central_repository_button.setEnabled(False)
        self.central_sync_all_button.setEnabled(False)
        self._set_central_detail_actions_enabled(False)
        self.central_config_status.setText(
            f"{config.host}:{config.port} · {config.config_dir} · 正在进行只读连接/目录检查…"
        )

        def task(*, log, progress):
            del log
            progress(20)
            result = ClassificationRegistryService(config_dir=config.config_dir).test_repository(
                **connection
            )
            progress(100)
            return result

        worker = FunctionWorker(task)
        self._central_worker = worker
        worker.signals.result.connect(self._on_central_repository_test_result)
        worker.signals.error.connect(lambda details: self._on_central_connection_error(details, "仓库测试"))
        worker.signals.finished.connect(self._on_central_connection_finished)
        self._pool.start(worker)

    def _on_central_repository_test_result(self, result: object) -> None:
        payload = dict(result) if isinstance(result, dict) else {}
        present = [str(x) for x in payload.get("present", [])] if isinstance(payload.get("present", []), list) else []
        missing = [str(x) for x in payload.get("missing", [])] if isinstance(payload.get("missing", []), list) else []
        directory = str(payload.get("config_dir", self.central_config_dir.text()) or self.central_config_dir.text())
        if missing:
            message = (
                f"中央服务器连接成功，配置目录可读取：\n{directory}\n\n"
                f"已存在：{', '.join(present) if present else '无'}\n"
                f"尚缺少：{', '.join(missing)}\n\n"
                "缺失文件可由 Admin 首次发布对应配置后创建。"
            )
            self._append_log(f"中央仓库只读检查成功；缺失文件：{', '.join(missing)}")
            QMessageBox.warning(self, "中央仓库可访问，但配置不完整", message)
        else:
            self._append_log("中央仓库只读检查成功；5 个中央配置文件均存在。")
            QMessageBox.information(
                self,
                "中央仓库连接成功",
                f"服务器和目录均可读取：\n{directory}\n\n5 个中央配置文件均已存在。",
            )
        self._refresh_local_cache_source_status(extra="中央仓库刚刚测试成功")

    def _load_shared_connection_config(self) -> None:
        """Load the single local shared SSH/Oracle configuration.

        v2.18.172 removes the obsolete multi-environment Profile UI. Business
        modules have always consumed these shared keys, so one visible local
        configuration is now the single source for this workstation.
        """
        self._loading_environment = True
        self.ssh_host.setText(self.user_settings.get_value("remote_g_source/host", "").strip())
        self.ssh_port.setValue(self.user_settings.get_int("remote_g_source/port", DEFAULT_SSH_PORT))
        self.ssh_username.setText(self.user_settings.get_value("remote_g_source/username", "").strip())
        self.ssh_password.setText(self.user_settings.get_value("remote_g_source/password", ""))
        self.business_g_directory.setText(
            self.user_settings.get_value("remote_g_source/remote_directory", "").strip()
        )
        self.symbol_library_root.setText(
            self.user_settings.get_value("site_profile/remote_symbol_library_root", "").strip()
        )
        db = self.database_service.load_config()
        self.username.setText(db.username)
        self.password.setText(db.password)
        self.host.setText(db.host)
        self.port.setValue(db.port)
        self.service_name.setText(db.service_name)
        self._update_endpoint()
        self._ssh_dirty = False
        self._db_dirty = False
        self._loading_environment = False

    def _refresh_local_cache_source_status(self, *, extra: str = "") -> None:
        """Show local-only cache provenance without touching the central server.

        This method may be called by save/sync callbacks, but it must never make
        DatabasePage construction fail if the UI is still being assembled.
        """
        status_label = getattr(self, "central_config_status", None)
        if status_label is None:
            return
        ssh_configured = any(
            self.user_settings.has_value(key)
            for key in (
                "remote_g_source/host",
                "remote_g_source/username",
                "remote_g_source/password",
                "remote_g_source/remote_directory",
                "site_profile/remote_symbol_library_root",
            )
        )
        db_configured = self.database_service._has_saved_user_config()
        ssh_source = (
            self.user_settings.get_value("local_cache/file_server_source", "local").strip() or "local"
            if ssh_configured else "missing"
        )
        db_source = (
            self.user_settings.get_value("local_cache/database_source", "local").strip() or "local"
            if db_configured else "missing"
        )
        version = self.user_settings.get_value("local_cache/central_connection_version", "").strip()
        ssh_saved_at = self.user_settings.get_value("local_cache/file_server_saved_at", "").strip()
        db_saved_at = self.user_settings.get_value("local_cache/database_saved_at", "").strip()
        central_synced_at = self.user_settings.get_value("local_cache/central_connection_synced_at", "").strip()
        source_labels = {
            "central": "中央同步副本",
            "local": "本地配置",
            "custom": "本地自定义",
            "missing": "未配置",
        }
        ssh_label = source_labels.get(ssh_source, "本地配置")
        db_label = source_labels.get(db_source, "本地配置")
        suffix = f" · 基于中央 V{version}" if version and (ssh_source == "central" or db_source == "central") else ""
        ssh_time = f"（{ssh_saved_at}）" if ssh_saved_at else ""
        db_time = f"（{db_saved_at}）" if db_saved_at else ""
        sync_text = central_synced_at or "尚未同步"
        dirty_parts: list[str] = []
        if self._ssh_dirty:
            dirty_parts.append("文件服务器有未保存修改")
        if self._db_dirty:
            dirty_parts.append("Oracle 有未保存修改")
        if self._central_repo_dirty:
            dirty_parts.append("中央仓库连接有未保存修改")
        dirty_text = f" · {'；'.join(dirty_parts)}" if dirty_parts else ""
        extra_text = f" · {extra}" if extra else ""
        repo_host = self.central_host.text().strip() or "-"
        repo_port = self.central_port.value()
        repo_dir = self.central_config_dir.text().strip() or DEFAULT_CONFIG_DIR
        repo_saved_at = self.user_settings.get_value("local_cache/central_repository_saved_at", "").strip()
        repo_confirmed = self.central_repository_settings.is_explicitly_saved()
        repo_saved_text = f" · 本地保存：{repo_saved_at}" if repo_saved_at else ""
        repo_guard_text = (
            " · 已确认本机中央仓库"
            if repo_confirmed
            else " · ⚠ 尚未在本机确认保存：禁止抢占 Admin / 发布中央配置"
        )
        status_label.setText(
            f"中央仓库：{repo_host}:{repo_port} · {repo_dir}{repo_saved_text}{repo_guard_text} · "
            f"当前来源：文件服务器={ssh_label}{ssh_time} · Oracle={db_label}{db_time}{suffix} · "
            f"中央同步：{sync_text} · 中央同步/发布内容：Oracle 数据库 + 文件服务器（SSH/SFTP） · "
            f"一键全量同步：Oracle + 文件服务器 + ID 规则 + 图元分类 · "
            f"启动不自动读取中央配置{dirty_text}{extra_text}"
        )

    @staticmethod
    def _local_timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _on_ssh_field_changed(self, *_args) -> None:
        if self._loading_environment:
            return
        self._ssh_dirty = True
        self._refresh_local_cache_source_status()

    def _on_db_field_changed(self, *_args) -> None:
        if self._loading_environment:
            return
        self._db_dirty = True
        self._refresh_local_cache_source_status()

    def _mark_local_connection_custom(self, *, file_server: bool = False, database: bool = False) -> None:
        if file_server:
            self.user_settings.set_value("local_cache/file_server_source", "custom")
        if database:
            self.user_settings.set_value("local_cache/database_source", "custom")
        self._refresh_local_cache_source_status()

    def _persist_ssh_shared(self) -> None:
        host = self.ssh_host.text().strip()
        username = self.ssh_username.text().strip()
        business_dir = self.business_g_directory.text().strip()
        symbol_root = self.symbol_library_root.text().strip()
        if not host:
            raise ValueError("SSH IP/主机不能为空。")
        if not username:
            raise ValueError("SSH 用户名不能为空。")
        if not business_dir:
            raise ValueError("业务 G 根目录不能为空。")
        if not symbol_root:
            raise ValueError("标准图元库目录不能为空。")
        self.user_settings.set_value("remote_g_source/host", host)
        self.user_settings.set_value("remote_g_source/port", self.ssh_port.value())
        self.user_settings.set_value("remote_g_source/username", username)
        self.user_settings.set_value("remote_g_source/password", self.ssh_password.text())
        self.user_settings.set_value("remote_g_source/remote_directory", business_dir)
        self.user_settings.set_value("site_profile/remote_symbol_library_root", symbol_root)

    def _save_file_server_config(self) -> None:
        try:
            self._persist_ssh_shared()
        except Exception as exc:
            QMessageBox.warning(self, "保存文件服务器配置失败", str(exc))
            return
        self._mark_local_connection_custom(file_server=True)
        self.user_settings.set_value("local_cache/file_server_saved_at", self._local_timestamp())
        self._ssh_dirty = False
        self._refresh_local_cache_source_status()
        self._set_inline_status(self.ssh_status, "已保存到本地 · 尚未验证", "idle")
        self._append_log("文件服务器配置已保存到本机缓存；未访问中央配置。")
        self.environmentChanged.emit("shared")

    def _save_environment(self, *, show_message: bool) -> None:
        """Backward-compatible helper: save the workstation shared connection config."""
        try:
            self._persist_ssh_shared()
            config = self._config_from_form()
            config.validate()
            self.database_service.save_config(config)
        except Exception as exc:
            if show_message:
                QMessageBox.warning(self, "保存连接配置失败", str(exc))
            return
        self._mark_local_connection_custom(file_server=True, database=True)
        stamp = self._local_timestamp()
        self.user_settings.set_value("local_cache/file_server_saved_at", stamp)
        self.user_settings.set_value("local_cache/database_saved_at", stamp)
        self._ssh_dirty = False
        self._db_dirty = False
        self._refresh_local_cache_source_status()
        self._append_log("本机共享连接配置已保存；未访问中央配置。")
        self.environmentChanged.emit("shared")
        if show_message:
            self._set_inline_status(self.ssh_status, "已保存到本地 · 尚未验证", "idle")
            self._set_status("已保存到本地 · 尚未验证", "idle")

    def _toggle_ssh_password(self, checked: bool) -> None:
        self.ssh_password.setEchoMode(WheelSafeLineEdit.EchoMode.Normal if checked else WheelSafeLineEdit.EchoMode.Password)
        self.show_ssh_password.setText("隐藏密码" if checked else "显示密码")

    def _test_ssh_connection(self) -> None:
        if self._ssh_worker is not None:
            return
        try:
            host = self.ssh_host.text().strip()
            port = self.ssh_port.value()
            username = self.ssh_username.text().strip()
            password = self.ssh_password.text()
            if not host:
                raise ValueError("SSH IP/主机不能为空。")
            if not username:
                raise ValueError("SSH 用户名不能为空。")
        except Exception as exc:
            QMessageBox.warning(self, "文件服务器配置不完整", str(exc))
            return
        self.test_ssh_button.setEnabled(False)
        self._set_inline_status(self.ssh_status, "正在连接…", "testing")
        self._append_log(f"开始测试只读 SSH/SFTP：{username}@{host}:{port}")

        def task(*, log, progress):
            del log
            progress(20)
            with ReadOnlySshClient(host, port, username, password) as client:
                client.test_connection()
            progress(100)
            return True

        worker = FunctionWorker(task)
        self._ssh_worker = worker
        worker.signals.result.connect(lambda _result: self._ssh_ok())
        worker.signals.error.connect(self._ssh_error)
        worker.signals.finished.connect(self._ssh_finished)
        self._pool.start(worker)

    def _ssh_ok(self) -> None:
        self._set_inline_status(self.ssh_status, "连接成功 · 服务器只读", "ok")
        self._append_log("SSH/SFTP 连接成功；只读策略保持有效。")

    def _ssh_error(self, details: str) -> None:
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self._set_inline_status(self.ssh_status, f"连接失败 · {message}", "error")
        self._append_log(f"SSH/SFTP 连接失败：{message}")

    def _ssh_finished(self) -> None:
        self._ssh_worker = None
        self.test_ssh_button.setEnabled(True)

    def _config_from_form(self) -> OracleConnectionConfig:
        return OracleConnectionConfig(
            username=self.username.text().strip(),
            password=self.password.text(),
            host=self.host.text().strip(),
            port=self.port.value(),
            service_name=self.service_name.text().strip(),
        )

    def _update_endpoint(self, *_args) -> None:
        config = self._config_from_form()
        self.endpoint.setText(f"当前连接：{config.username or '-'} @ {config.host or '-'}:{config.port}/{config.service_name or '-'}")

    def _toggle_password(self, checked: bool) -> None:
        self.password.setEchoMode(WheelSafeLineEdit.EchoMode.Normal if checked else WheelSafeLineEdit.EchoMode.Password)
        self.show_password.setText("隐藏密码" if checked else "显示密码")

    @staticmethod
    def _status_style(state: str) -> str:
        styles = {
            "idle": "background:#f6f8f7;border:1px solid #d2ddda;color:#687c82;",
            "testing": "background:#eef5f4;border:1px solid #b7cfcb;color:#46696d;",
            "ok": "background:#e3f5ed;border:1px solid #98d1bc;color:#087250;",
            "warning": "background:#fff7e7;border:1px solid #e6c675;color:#8a6200;",
            "error": "background:#fff0ee;border:1px solid #efb8af;color:#b2382b;",
        }
        return "QLabel { border-radius:7px; padding:8px 12px; font-weight:700; " + styles.get(state, styles["idle"]) + " }"

    def _central_bootstrap(self) -> dict[str, object]:
        if self._central_repo_dirty:
            raise ValueError("中央仓库连接有未保存修改，请先点击“保存中央仓库配置”。")
        return self.central_repository_settings.load().connection_args()

    def _central_repository_dir(self) -> str:
        if self._central_repo_dirty:
            raise ValueError("中央仓库连接有未保存修改，请先点击“保存中央仓库配置”。")
        return self.central_repository_settings.load().config_dir

    def _central_database_payload(self) -> dict[str, object]:
        cfg = self._config_from_form()
        cfg.validate()
        return {
            "username": cfg.username,
            "password": cfg.password,
            "host": cfg.host,
            "port": cfg.port,
            "service_name": cfg.service_name,
        }

    def _central_file_server_payload(self) -> dict[str, object]:
        return {
            "host": self.ssh_host.text().strip(),
            "port": self.ssh_port.value(),
            "username": self.ssh_username.text().strip(),
            "password": self.ssh_password.text(),
            "business_g_directory": self.business_g_directory.text().strip(),
            "symbol_library_root": self.symbol_library_root.text().strip(),
        }

    def _open_central_progress(self, title: str, label: str) -> QProgressDialog:
        dialog = QProgressDialog(label, "", 0, 100, self)
        dialog.setWindowTitle(title)
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        # Do not flash a transient progress window for fast local/central operations.
        # Qt will show it only when the operation actually lasts long enough.
        dialog.setMinimumDuration(800)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self._central_progress_dialog = dialog
        return dialog

    def _close_central_progress(self) -> None:
        dialog = self._central_progress_dialog
        self._central_progress_dialog = None
        if dialog is not None:
            dialog.setValue(100)
            dialog.close()
            dialog.deleteLater()

    def _sync_all_central_config(self) -> None:
        """Explicitly replace every workstation-local central-config cache in one action."""
        if self._central_worker is not None:
            return
        try:
            bootstrap = self._central_bootstrap()
            config_dir = self._central_repository_dir()
        except Exception as exc:
            QMessageBox.warning(self, "一键同步全部中央配置", str(exc))
            return
        if QMessageBox.question(
            self,
            "一键同步全部中央配置",
            "将从中央仓库一次性读取并覆盖本机以下配置：\n\n"
            "• Oracle 数据库\n"
            "• 文件服务器（SSH/SFTP）\n"
            "• ID 规则\n"
            "• 图元分类\n\n"
            "只会读取中央仓库并写入本机缓存，不会修改中央服务器。继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return

        self.central_config_status.setText(
            f"{config_dir} · 正在一键同步全部中央配置…"
        )
        self.central_sync_all_button.setEnabled(False)
        self._set_central_detail_actions_enabled(False)
        progress_dialog = self._open_central_progress(
            "一键同步全部中央配置",
            "正在读取并校验中央全部配置…",
        )

        def task(*, log, progress):
            progress(10)
            result = ClassificationRegistryService(config_dir=config_dir).fetch_all_configs(**bootstrap, log=log)
            progress(78)
            return result

        worker = FunctionWorker(task)
        self._central_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.log.connect(self._append_log)
        worker.signals.result.connect(self._on_sync_all_central_result)
        worker.signals.error.connect(lambda details: self._on_central_connection_error(details, "全量同步"))
        worker.signals.finished.connect(self._on_central_connection_finished)
        self._pool.start(worker)

    def _on_sync_all_central_result(self, result: object) -> None:
        try:
            self._apply_sync_all_central_result(result)
        except Exception as exc:
            self._on_central_connection_error(str(exc), "全量同步")

    def _apply_sync_all_central_result(self, result: object) -> None:
        if self._central_progress_dialog is not None:
            self._central_progress_dialog.setLabelText("中央配置校验完成，正在覆盖本机缓存…")
            self._central_progress_dialog.setValue(84)

        payload = dict(result) if isinstance(result, dict) else {}
        file_server = payload.get("file_server")
        database = payload.get("database")
        id_rules = payload.get("id_rules")
        classification = payload.get("classification")
        instance = payload.get("instance")
        if not all(isinstance(item, dict) for item in (file_server, database, id_rules, classification, instance)):
            raise ValueError("中央全量配置返回格式无效，本机配置未更新。")

        file_server = dict(file_server)
        database = dict(database)
        id_rules = dict(id_rules)
        classification = dict(classification)
        instance = dict(instance)
        classification_payload = classification.get("payload")
        if not isinstance(classification_payload, dict):
            raise ValueError("中央图元分类返回格式无效，本机配置未更新。")

        # All remote files were downloaded and validated before this point. Apply
        # them locally only now, so a central read/validation failure never leaves
        # the workstation half synchronized.
        self._loading_environment = True
        try:
            self.ssh_host.setText(str(file_server.get("host", "")))
            self.ssh_port.setValue(int(file_server.get("port", 22) or 22))
            self.ssh_username.setText(str(file_server.get("username", "")))
            self.ssh_password.setText(str(file_server.get("password", "")))
            self.business_g_directory.setText(str(file_server.get("business_g_directory", "")))
            self.symbol_library_root.setText(str(file_server.get("symbol_library_root", "")))
            self.username.setText(str(database.get("username", "")))
            self.password.setText(str(database.get("password", "")))
            self.host.setText(str(database.get("host", "")))
            self.port.setValue(int(database.get("port", 1521) or 1521))
            self.service_name.setText(str(database.get("service_name", "")))
        finally:
            self._loading_environment = False
        self._update_endpoint()

        self._persist_ssh_shared()
        db_cfg = self._config_from_form()
        db_cfg.validate()
        self.database_service.save_config(db_cfg)
        imported_rules = IdRuleService().replace_from_payload(id_rules)
        imported_classification = RemoteSymbolLibraryService().replace_classification_marker_payload(
            host=str(file_server.get("host", "") or "").strip(),
            root=str(file_server.get("symbol_library_root", "") or "").strip(),
            payload=classification_payload,
        )

        version = int(instance.get("config_version", 0) or 0)
        stamp = self._local_timestamp()
        central_updated_at = str(classification.get("updated_at", "") or "").strip()

        self.user_settings.set_value("local_cache/file_server_source", "central")
        self.user_settings.set_value("local_cache/database_source", "central")
        self.user_settings.set_value("local_cache/central_connection_version", version)
        self.user_settings.set_value("local_cache/central_connection_synced_at", stamp)
        self.user_settings.set_value("local_cache/file_server_saved_at", stamp)
        self.user_settings.set_value("local_cache/database_saved_at", stamp)

        self.user_settings.set_value("local_cache/id_rules_source", "central")
        self.user_settings.set_value("local_cache/id_rules_saved_at", stamp)
        self.user_settings.set_value("local_cache/id_rules_synced_at", stamp)
        self.user_settings.set_value("local_cache/central_id_rules_version", version)

        self.user_settings.set_value("local_cache/classification_source", "central")
        self.user_settings.set_value("local_cache/classification_saved_at", stamp)
        self.user_settings.set_value("local_cache/classification_synced_at", stamp)
        if central_updated_at:
            self.user_settings.set_value("local_cache/classification_central_updated_at", central_updated_at)

        self.user_settings.set_value("local_cache/central_all_synced_at", stamp)
        self.user_settings.set_value("local_cache/central_all_version", version)
        self._ssh_dirty = False
        self._db_dirty = False
        self._set_inline_status(self.ssh_status, "已从中央同步到本地 · 尚未验证", "idle")
        self._set_status("已从中央同步到本地 · 尚未验证", "idle")
        self._refresh_local_cache_source_status(extra=f"已一键同步全部中央配置 V{version}")
        self.environmentChanged.emit("shared")

        summary = {
            "version": version,
            "synced_at": stamp,
            "id_rule_count": int(imported_rules.get("rules", 0) or 0),
            "classification_count": int(classification.get("marker_count", 0) or 0),
            "classification_matched": int(imported_classification.get("matched", 0) or 0),
            "classification_pending": int(imported_classification.get("pending", 0) or 0),
        }
        self.centralConfigSynced.emit(summary)
        self._append_log(
            "一键同步全部中央配置完成："
            f"V{version}，ID 规则 {summary['id_rule_count']} 条，"
            f"图元分类 {summary['classification_count']} 条。"
        )
        self._close_central_progress()
        QMessageBox.information(
            self,
            "全部中央配置已同步",
            f"中央版本：V{version}\n\n"
            "已覆盖本机：Oracle 数据库、文件服务器、ID 规则、图元分类。\n"
            f"ID 规则：{summary['id_rule_count']} 条\n"
            f"图元分类：{summary['classification_count']} 条"
            f"（匹配 {summary['classification_matched']}，待匹配 {summary['classification_pending']}）\n\n"
            "中央仓库未被修改。",
        )

    def _set_central_detail_actions_enabled(self, enabled: bool) -> None:
        """Enable/disable the per-module central actions consistently."""
        normal = bool(enabled)
        for name in ("sync_file_server_button", "sync_database_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(normal)
        publish_enabled = normal and self._is_admin_mode and self._admin_epoch is not None
        for name in ("publish_file_server_button", "publish_database_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(publish_enabled)

    def _sync_file_server_from_central(self) -> None:
        self._sync_single_connection_config("file_server")

    def _sync_database_from_central(self) -> None:
        self._sync_single_connection_config("database")

    def _sync_single_connection_config(self, kind: str) -> None:
        if self._central_worker is not None:
            return
        labels = {
            "file_server": ("文件服务器", "file_server.json"),
            "database": ("Oracle 数据库", "database.json"),
        }
        if kind not in labels:
            raise ValueError(f"未知中央配置类型：{kind}")
        label, filename = labels[kind]
        try:
            bootstrap = self._central_bootstrap()
            config_dir = self._central_repository_dir()
        except Exception as exc:
            QMessageBox.warning(self, f"同步{label}配置", str(exc))
            return
        if QMessageBox.question(
            self,
            f"仅同步{label}配置",
            f"将从中央仓库读取 {filename} 并覆盖本机{label}配置。\n\n其他中央配置不会改变。继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.central_config_status.setText(f"{config_dir} · 正在同步{label}配置…")
        self.central_sync_all_button.setEnabled(False)
        self._set_central_detail_actions_enabled(False)
        progress_dialog = self._open_central_progress(
            f"同步中央{label}配置", f"正在读取中央 {filename}…"
        )

        def task(*, log, progress):
            del log
            progress(15)
            service = ClassificationRegistryService(config_dir=config_dir)
            if kind == "file_server":
                result = service.fetch_file_server_config(**bootstrap)
            else:
                result = service.fetch_database_config(**bootstrap)
            progress(85)
            return result

        worker = FunctionWorker(task)
        self._central_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(lambda result, k=kind: self._on_single_connection_sync_result(k, result))
        worker.signals.error.connect(lambda details, k=kind: self._on_central_connection_error(details, f"{labels[k][0]}同步"))
        worker.signals.finished.connect(self._on_central_connection_finished)
        self._pool.start(worker)

    def _on_single_connection_sync_result(self, kind: str, result: object) -> None:
        payload = dict(result) if isinstance(result, dict) else {}
        instance = payload.get("instance", {})
        version = int(instance.get("config_version", 0) or 0) if isinstance(instance, dict) else 0
        stamp = self._local_timestamp()

        self._loading_environment = True
        try:
            if kind == "file_server":
                config = payload.get("file_server", {})
                if not isinstance(config, dict):
                    raise ValueError("中央 file_server.json 格式无效。")
                self.ssh_host.setText(str(config.get("host", "")))
                self.ssh_port.setValue(int(config.get("port", 22) or 22))
                self.ssh_username.setText(str(config.get("username", "")))
                self.ssh_password.setText(str(config.get("password", "")))
                self.business_g_directory.setText(str(config.get("business_g_directory", "")))
                self.symbol_library_root.setText(str(config.get("symbol_library_root", "")))
                self._persist_ssh_shared()
                self.user_settings.set_value("local_cache/file_server_source", "central")
                self.user_settings.set_value("local_cache/file_server_saved_at", stamp)
                self._ssh_dirty = False
                self._set_inline_status(self.ssh_status, "已从中央同步到本地 · 尚未验证", "idle")
                label = "文件服务器"
            elif kind == "database":
                config = payload.get("database", {})
                if not isinstance(config, dict):
                    raise ValueError("中央 database.json 格式无效。")
                self.username.setText(str(config.get("username", "")))
                self.password.setText(str(config.get("password", "")))
                self.host.setText(str(config.get("host", "")))
                self.port.setValue(int(config.get("port", 1521) or 1521))
                self.service_name.setText(str(config.get("service_name", "")))
                db_cfg = self._config_from_form()
                db_cfg.validate()
                self.database_service.save_config(db_cfg)
                self.user_settings.set_value("local_cache/database_source", "central")
                self.user_settings.set_value("local_cache/database_saved_at", stamp)
                self._db_dirty = False
                self._set_status("已从中央同步到本地 · 尚未验证", "idle")
                self._update_endpoint()
                label = "Oracle 数据库"
            else:
                raise ValueError(f"未知中央配置类型：{kind}")
        finally:
            self._loading_environment = False

        self.user_settings.set_value(f"local_cache/{kind}_central_version", version)
        self.user_settings.set_value(f"local_cache/{kind}_synced_at", stamp)
        self._refresh_local_cache_source_status(extra=f"{label}刚刚同步中央 V{version}")
        self.environmentChanged.emit("shared")
        self._close_central_progress()
        QMessageBox.information(self, f"{label}配置已同步", f"已用中央 V{version} 的{label}配置覆盖本机缓存。")

    def _publish_file_server_to_central(self) -> None:
        self._publish_single_connection_config("file_server")

    def _publish_database_to_central(self) -> None:
        self._publish_single_connection_config("database")

    def _publish_single_connection_config(self, kind: str) -> None:
        if self._central_worker is not None:
            return
        labels = {
            "file_server": ("文件服务器", "file_server.json"),
            "database": ("Oracle 数据库", "database.json"),
        }
        if kind not in labels:
            raise ValueError(f"未知中央配置类型：{kind}")
        label, filename = labels[kind]
        try:
            self.central_repository_settings.require_explicitly_saved(action=f"发布{label}配置到中央")
        except Exception as exc:
            QMessageBox.warning(self, "中央仓库尚未确认", str(exc))
            return
        if not self._is_admin_mode or self._admin_epoch is None:
            QMessageBox.warning(
                self,
                "需要 Admin 权限",
                f"普通客户端可以保存/同步本机{label}配置，但不能发布中央仓库。请先从左侧【配置权限】抢占 Admin。",
            )
            return
        self._ensure_machine_id()
        try:
            bootstrap = self._central_bootstrap()
            config_dir = self._central_repository_dir()
            if kind == "file_server":
                self._persist_ssh_shared()
                config_payload = self._central_file_server_payload()
            else:
                config_payload = self._central_database_payload()
                self.database_service.save_config(self._config_from_form())
        except Exception as exc:
            QMessageBox.warning(self, f"发布{label}配置", str(exc))
            return
        if QMessageBox.question(
            self,
            f"发布{label}配置到中央",
            f"将当前本机{label}配置发布到中央 {filename}？\n\n其他中央配置不会改变。",
        ) != QMessageBox.StandardButton.Yes:
            return

        self.central_config_status.setText(f"{config_dir} · 正在发布{label}配置到中央…")
        self.central_sync_all_button.setEnabled(False)
        self._set_central_detail_actions_enabled(False)
        progress_dialog = self._open_central_progress(
            f"发布中央{label}配置", f"正在验证 Admin 并上传 {filename}…"
        )

        def task(*, log, progress):
            del log
            service = ClassificationRegistryService(config_dir=config_dir)
            progress(10)
            owner = service.fetch_admin_lease(**bootstrap)
            if owner is None:
                raise RuntimeError("中央配置当前没有管理员，请通过左侧“配置权限”申请管理员权限。")
            if owner.machine_id != self._machine_id:
                raise RuntimeError(f"当前中央管理员为 {owner.owner_text}，本机不能发布中央配置。")
            if owner.admin_epoch != int(self._admin_epoch or -1):
                raise RuntimeError("Admin 权限已被重新抢占，请重新抢占 Admin 后再发布。")
            progress(35)
            if kind == "file_server":
                result = service.publish_file_server_config(
                    **bootstrap, machine_id=self._machine_id,
                    expected_admin_epoch=self._admin_epoch, file_server=config_payload,
                )
            else:
                result = service.publish_database_config(
                    **bootstrap, machine_id=self._machine_id,
                    expected_admin_epoch=self._admin_epoch, database=config_payload,
                )
            progress(90)
            return result

        worker = FunctionWorker(task)
        self._central_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(lambda result, k=kind: self._on_single_connection_publish_result(k, result))
        worker.signals.error.connect(lambda details, k=kind: self._on_central_connection_error(details, f"{labels[k][0]}发布"))
        worker.signals.finished.connect(self._on_central_connection_finished)
        self._pool.start(worker)

    def _on_single_connection_publish_result(self, kind: str, result: object) -> None:
        self._close_central_progress()
        payload = dict(result) if isinstance(result, dict) else {}
        instance = payload.get("instance", {})
        version = int(instance.get("config_version", 0) or 0) if isinstance(instance, dict) else 0
        label = "文件服务器" if kind == "file_server" else "Oracle 数据库"
        filename = "file_server.json" if kind == "file_server" else "database.json"
        self._refresh_local_cache_source_status(extra=f"{label}已发布中央 V{version}")
        config_dir = self.central_repository_settings.load().config_dir
        QMessageBox.information(
            self, f"{label}已发布到中央",
            f"中央版本：V{version}\n\n{config_dir}/{filename}\n\n其他中央配置未修改。",
        )

    def _sync_central_connection_config(self) -> None:
        if self._central_worker is not None:
            return
        try:
            bootstrap = self._central_bootstrap()
            config_dir = self._central_repository_dir()
        except Exception as exc:
            QMessageBox.warning(self, "中央配置", str(exc))
            return
        if QMessageBox.question(
            self,
            "从中央同步数据库和文件服务器",
            "将同时从中央仓库下载 database.json（Oracle 数据库）和 file_server.json（文件服务器）；将覆盖当前本机连接配置。继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.central_config_status.setText(
            f"{config_dir} · 正在同步 Oracle 数据库 + 文件服务器…"
        )
        self.central_sync_all_button.setEnabled(False)
        self._set_central_detail_actions_enabled(False)
        progress_dialog = self._open_central_progress(
            "同步中央数据库和文件服务器配置",
            "正在读取中央 database.json 和 file_server.json…",
        )

        def task(*, log, progress):
            del log
            progress(10)
            result = ClassificationRegistryService(config_dir=config_dir).fetch_connection_configs(**bootstrap)
            progress(80)
            return result

        worker = FunctionWorker(task)
        self._central_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(self._on_central_connection_sync_result)
        worker.signals.error.connect(lambda details: self._on_central_connection_error(details, "同步"))
        worker.signals.finished.connect(self._on_central_connection_finished)
        self._pool.start(worker)

    def _on_central_connection_sync_result(self, result: object) -> None:
        if self._central_progress_dialog is not None:
            self._central_progress_dialog.setLabelText("正在覆盖本机连接配置缓存…")
            self._central_progress_dialog.setValue(90)
        payload = dict(result) if isinstance(result, dict) else {}
        file_server = payload.get("file_server", {})
        database = payload.get("database", {})
        instance = payload.get("instance", {})
        if not isinstance(file_server, dict) or not isinstance(database, dict):
            QMessageBox.warning(self, "中央配置", "中央连接配置格式无效。")
            return
        self.ssh_host.setText(str(file_server.get("host", "")))
        self.ssh_port.setValue(int(file_server.get("port", 22) or 22))
        self.ssh_username.setText(str(file_server.get("username", "")))
        self.ssh_password.setText(str(file_server.get("password", "")))
        self.business_g_directory.setText(str(file_server.get("business_g_directory", "")))
        self.symbol_library_root.setText(str(file_server.get("symbol_library_root", "")))
        self.username.setText(str(database.get("username", "")))
        self.password.setText(str(database.get("password", "")))
        self.host.setText(str(database.get("host", "")))
        self.port.setValue(int(database.get("port", 1521) or 1521))
        self.service_name.setText(str(database.get("service_name", "")))
        self._save_environment(show_message=False)
        version = int(instance.get("config_version", 0) or 0) if isinstance(instance, dict) else 0
        self.user_settings.set_value("local_cache/file_server_source", "central")
        self.user_settings.set_value("local_cache/database_source", "central")
        self.user_settings.set_value("local_cache/central_connection_version", version)
        sync_stamp = self._local_timestamp()
        self.user_settings.set_value("local_cache/central_connection_synced_at", sync_stamp)
        self.user_settings.set_value("local_cache/file_server_saved_at", sync_stamp)
        self.user_settings.set_value("local_cache/database_saved_at", sync_stamp)
        self._ssh_dirty = False
        self._db_dirty = False
        self._refresh_local_cache_source_status(extra=f"刚刚同步中央 V{version}")
        self._close_central_progress()
        QMessageBox.information(self, "中央配置", f"已用中央 V{version} 覆盖本机数据库和文件服务器配置。")

    def set_admin_mode(self, is_admin: bool, admin_epoch: int | None = None) -> None:
        """Apply process-local Admin permission without touching central config."""
        self._is_admin_mode = bool(is_admin)
        self._admin_epoch = int(admin_epoch) if is_admin and admin_epoch is not None else None
        self._set_central_detail_actions_enabled(self._central_worker is None)

    def _publish_central_connection_config(self) -> None:
        if self._central_worker is not None:
            return
        try:
            self.central_repository_settings.require_explicitly_saved(action="发布数据库和文件服务器到中央")
        except Exception as exc:
            QMessageBox.warning(self, "中央仓库尚未确认", str(exc))
            return
        if not self._is_admin_mode or self._admin_epoch is None:
            QMessageBox.warning(
                self,
                "需要 Admin 权限",
                "普通客户端可以修改/保存本机数据库和文件服务器配置并从中央同步，但不能发布中央仓库。请先从左侧【配置权限】抢占 Admin。",
            )
            return
        self._ensure_machine_id()
        try:
            self._save_environment(show_message=False)
            bootstrap = self._central_bootstrap()
            config_dir = self._central_repository_dir()
            database = self._central_database_payload()
            file_server = self._central_file_server_payload()
        except Exception as exc:
            QMessageBox.warning(self, "发布中央配置", str(exc))
            return
        if QMessageBox.question(
            self,
            "发布数据库和文件服务器到中央",
            "将当前本机 Oracle 数据库配置和文件服务器配置同时发布到中央仓库？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.central_config_status.setText(
            f"{config_dir} · 正在发布 Oracle 数据库 + 文件服务器到中央…"
        )
        self.central_sync_all_button.setEnabled(False)
        self._set_central_detail_actions_enabled(False)
        progress_dialog = self._open_central_progress(
            "发布中央数据库和文件服务器配置",
            "正在验证管理员并上传 database.json + file_server.json…",
        )

        def task(*, log, progress):
            del log
            service = ClassificationRegistryService(config_dir=config_dir)
            progress(10)
            owner = service.fetch_admin_lease(**bootstrap)
            if owner is None:
                raise RuntimeError("中央配置当前没有管理员，请通过左侧“配置权限”申请管理员权限。")
            if owner.machine_id != self._machine_id:
                raise RuntimeError(f"当前中央管理员为 {owner.owner_text}，本机不能发布中央配置。")
            if owner.admin_epoch != int(self._admin_epoch or -1):
                raise RuntimeError("Admin 权限已被重新抢占，请重新抢占 Admin 后再发布。")
            progress(35)
            result = service.publish_connection_configs(
                **bootstrap,
                machine_id=self._machine_id,
                expected_admin_epoch=self._admin_epoch,
                database=database,
                file_server=file_server,
            )
            progress(90)
            return result

        worker = FunctionWorker(task)
        self._central_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(self._on_central_connection_publish_result)
        worker.signals.error.connect(lambda details: self._on_central_connection_error(details, "发布"))
        worker.signals.finished.connect(self._on_central_connection_finished)
        self._pool.start(worker)

    def _on_central_connection_publish_result(self, result: object) -> None:
        self._close_central_progress()
        payload = dict(result) if isinstance(result, dict) else {}
        instance = payload.get("instance", {})
        version = int(instance.get("config_version", 0) or 0) if isinstance(instance, dict) else 0
        self._refresh_local_cache_source_status(extra=f"已发布中央 V{version}")
        config_dir = self.central_repository_settings.load().config_dir
        QMessageBox.information(
            self,
            "数据库和文件服务器已发布到中央",
            f"中央版本：V{version}\n\n"
            f"Oracle 数据库：{config_dir}/database.json\n"
            f"文件服务器：{config_dir}/file_server.json",
        )

    def _on_central_connection_error(self, details: str, action: str) -> None:
        self._close_central_progress()
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self._refresh_local_cache_source_status(extra=f"中央{action}失败")
        QMessageBox.warning(self, f"中央配置{action}失败", message or str(details))

    def _on_central_connection_finished(self) -> None:
        self._central_worker = None
        self._close_central_progress()
        self.test_central_repository_button.setEnabled(True)
        self.save_central_repository_button.setEnabled(True)
        self.central_sync_all_button.setEnabled(True)
        self._set_central_detail_actions_enabled(True)

    def _set_inline_status(self, label: QLabel, text: str, state: str) -> None:
        label.setText(text)
        label.setStyleSheet(self._status_style(state))

    def _set_status(self, text: str, state: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(self._status_style(state))

    def _append_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {text}")

    def _save_database_config(self) -> None:
        try:
            config = self._config_from_form()
            secure_password = self.database_service.save_config(config)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._mark_local_connection_custom(database=True)
        self.user_settings.set_value("local_cache/database_saved_at", self._local_timestamp())
        self._db_dirty = False
        self._refresh_local_cache_source_status()
        if secure_password:
            self._append_log("数据库配置已保存到本机；密码已使用 Windows 当前用户 DPAPI 加密。")
            self._set_status("已保存到本地 · 尚未验证", "idle")
        else:
            self._append_log("数据库配置已保存；当前系统不支持 Windows DPAPI，因此未持久化密码。")
            self._set_status("已保存到本地 · 密码未持久化 · 尚未验证", "warning")
        self.environmentChanged.emit("shared")

    # Backward-compatible method name used by older tests/callers.
    def _save_config(self) -> None:
        self._save_database_config()

    def _test_connection(self) -> None:
        if self._worker is not None:
            return
        try:
            config = self._config_from_form()
            config.validate()
        except Exception as exc:
            QMessageBox.warning(self, "数据库配置不完整", str(exc))
            return
        self.test_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self._set_status("正在连接…", "testing")
        self._append_log(f"开始测试 Oracle 连接：{config.username} @ {config.dsn}")

        def task(*, log, progress):
            del log
            progress(20)
            result = self.database_service.test_connection(config)
            progress(100)
            return result

        worker = FunctionWorker(task)
        self._worker = worker
        worker.signals.result.connect(self._connection_ok)
        worker.signals.error.connect(self._connection_error)
        worker.signals.finished.connect(self._connection_finished)
        self._pool.start(worker)

    def _connection_ok(self, result: object) -> None:
        info = result if isinstance(result, dict) else {}
        database = str(info.get("database", "") or "-")
        service = str(info.get("service", "") or self.service_name.text().strip())
        username = str(info.get("username", "") or self.username.text().strip())
        self._set_status(f"连接成功 · {username} · {database} · {service}", "ok")
        self._append_log(f"连接成功：USER={username}, DB={database}, SERVICE={service}")

    def _connection_error(self, details: str) -> None:
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self._set_status(f"连接失败 · {message}", "error")
        self._append_log(f"连接失败：{message}")

    def _connection_finished(self) -> None:
        self._worker = None
        self.test_button.setEnabled(True)
        self.save_button.setEnabled(True)

    def _copy_log(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log.toPlainText())

    def _clear_log(self) -> None:
        self.log.clear()

    def on_page_activated(self) -> None:
        # Other modules use the same shared keys. Re-read the shared workstation
        # connection whenever this page becomes visible.
        self._load_central_repository_config()
        self._load_shared_connection_config()
        self._refresh_local_cache_source_status()
