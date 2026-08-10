from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox

class FeederSettingsWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0)

        info = QLabel(
            "馈线模型模块已纳入平台架构。当前尚未配置馈线对应的数据库表、"
            "G 图元类型、匹配规则及域号，因此暂不开放执行，避免使用未经确认的业务规则。"
        )
        info.setWordWrap(True)
        info.setObjectName("moduleDescription")
        root.addWidget(info)

        box = QGroupBox("馈线模型后续配置项")
        lay = QVBoxLayout(box)
        text = QLabel(
            "后续需要明确：\n"
            "• 馈线唯一性与数据库查询规则\n"
            "• G 文件中的馈线识别规则\n"
            "• 图元与数据库表映射\n"
            "• 关联域号\n"
            "• Expected KeyID 计算规则\n"
            "• 模型关联预览\n"
            "• G 文件安全回写"
        )
        text.setWordWrap(True)
        lay.addWidget(text)
        root.addWidget(box)
        root.addStretch()

    def collect_settings(self):
        return {}

