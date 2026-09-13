"""VineFocus 独立设置窗口。

按“计时、外观、行为与数据”组织低频配置。窗口只持有控件与视觉，
设置的读取、保存和业务副作用由 PomodoroPanel 统一处理。
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .botanical_assets import BotanicalAssets
from .config import GROWTH_LAYOUTS, UI_THEMES, VINE_THEMES
from .styles import build_app_qss


class SettingsDialog(QDialog):
    """由主面板长期持有的非模态单实例设置窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("花藤专注 · 设置")
        self.setModal(False)
        self.setMinimumSize(640, 720)
        self.resize(700, 850)
        self.build_ui()
        self.setStyleSheet(build_app_qss())

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("设置")
        title.setObjectName("brandTitle")
        subtitle = QLabel("低频选项集中在这里；正在运行的本轮计时不会被意外改写")
        subtitle.setObjectName("brandSub")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_timer_tab(), "计时")
        self.tabs.addTab(self.build_appearance_tab(), "外观")
        self.tabs.addTab(self.build_behavior_tab(), "行为与数据")
        root.addWidget(self.tabs, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.done_btn = QPushButton("完成")
        self.done_btn.setObjectName("primaryButton")
        self.done_btn.setMinimumWidth(128)
        self.done_btn.clicked.connect(self.hide)
        footer.addWidget(self.done_btn)
        root.addLayout(footer)

    @staticmethod
    def section(title_text: str, hint_text: str = "") -> tuple[QFrame, QFormLayout]:
        frame = QFrame()
        frame.setObjectName("settingSection")
        layout = QFormLayout(frame)
        layout.setContentsMargins(17, 15, 17, 16)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(12)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        heading = QLabel(title_text)
        heading.setObjectName("sectionTitle")
        layout.addRow(heading)
        if hint_text:
            hint = QLabel(hint_text)
            hint.setObjectName("sectionHint")
            hint.setWordWrap(True)
            layout.addRow(hint)
        return frame, layout

    @staticmethod
    def slider(minimum: int, maximum: int) -> QSlider:
        control = QSlider(Qt.Orientation.Horizontal)
        control.setRange(minimum, maximum)
        control.setSingleStep(1)
        return control

    def build_timer_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        frame, form = self.section("专注节奏", "预设适合快速开始；时长和轮次从下一轮开始生效。")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["25+5", "45+10", "60+10", "自定义"])
        self.focus_spin = QSpinBox()
        self.focus_spin.setRange(1, 180)
        self.focus_spin.setSuffix(" 分钟")
        self.rest_spin = QSpinBox()
        self.rest_spin.setRange(1, 60)
        self.rest_spin.setSuffix(" 分钟")
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(1, 12)
        self.rounds_spin.setSuffix(" 轮")
        form.addRow("模式", self.preset_combo)
        form.addRow("专注时长", self.focus_spin)
        form.addRow("休息时长", self.rest_spin)
        form.addRow("循环轮次", self.rounds_spin)
        layout.addWidget(frame)
        layout.addStretch()
        return page

    def build_appearance_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # 组合框仍作为稳定的数据接口，视觉层改为概念稿里的可预览选择卡。
        self.ui_theme_combo = QComboBox(page)
        self.ui_theme_combo.addItems(UI_THEMES)
        self.ui_theme_combo.hide()
        self.theme_combo = QComboBox(page)
        self.theme_combo.addItems(list(VINE_THEMES.keys()))
        self.theme_combo.hide()
        self.growth_layout_combo = QComboBox(page)
        self.growth_layout_combo.addItems(GROWTH_LAYOUTS)
        self.growth_layout_combo.hide()
        self.choice_buttons: dict[str, dict[str, QPushButton]] = {
            "ui": {}, "plant": {}, "layout": {}
        }

        ui_frame, ui_form = self.section("界面氛围", "玻璃层级、字体与高亮色会整体切换。")
        ui_choices = QWidget()
        ui_row = QHBoxLayout(ui_choices)
        ui_row.setContentsMargins(0, 0, 0, 0)
        ui_row.setSpacing(8)
        ui_notes = {
            "夜色流光": "深蓝玻璃\n科技感",
            "温室晨雾": "柔暖象牙\n自然感",
            "薄荷汽水": "清透薄荷\n年轻感",
        }
        for name in UI_THEMES:
            button = QPushButton(f"{name}\n{ui_notes[name]}")
            button.setObjectName("choiceCard")
            button.setCheckable(True)
            button.setMinimumHeight(68)
            button.clicked.connect(lambda checked=False, value=name: self.ui_theme_combo.setCurrentText(value))
            self.choice_buttons["ui"][name] = button
            ui_row.addWidget(button)
        ui_form.addRow(ui_choices)
        layout.addWidget(ui_frame)

        plant_frame, plant_form = self.section("花藤品种", "每种植物拥有独立枝形、叶片和开花习性，不混合生长。")
        plant_frame.setMinimumHeight(265)
        plant_choices = QWidget()
        plant_choices.setMinimumHeight(204)
        plant_grid = QGridLayout(plant_choices)
        plant_grid.setContentsMargins(0, 0, 0, 0)
        plant_grid.setHorizontalSpacing(8)
        plant_grid.setVerticalSpacing(8)
        plant_notes = {
            "月白花藤": "安静 · 月光叶脉",
            "樱雾花枝": "轻盈 · 雾粉花苞",
            "流苏紫藤": "流动 · 错落花序",
            "极光荧藤": "通透 · 克制微光",
        }
        for index, name in enumerate(VINE_THEMES):
            button = QPushButton(f"{name}\n{plant_notes[name]}")
            button.setObjectName("plantChoiceCard")
            button.setCheckable(True)
            button.setIcon(QIcon(BotanicalAssets.base(name)))
            button.setIconSize(QSize(82, 70))
            button.setFixedHeight(96)
            button.clicked.connect(lambda checked=False, value=name: self.theme_combo.setCurrentText(value))
            self.choice_buttons["plant"][name] = button
            plant_grid.addWidget(button, index // 2, index % 2)
        plant_form.addRow(plant_choices)
        layout.addWidget(plant_frame)

        layout_frame, layout_form = self.section("生长构图", "默认只保留一株；需要仪式感时再切换环屏。")
        layout_choices = QWidget()
        layout_row = QHBoxLayout(layout_choices)
        layout_row.setContentsMargins(0, 0, 0, 0)
        layout_row.setSpacing(7)
        for name in GROWTH_LAYOUTS:
            button = QPushButton(name)
            button.setObjectName("segmentChoice")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=name: self.growth_layout_combo.setCurrentText(value))
            self.choice_buttons["layout"][name] = button
            layout_row.addWidget(button)
        layout_form.addRow(layout_choices)

        self.display_combo = QComboBox()
        self.display_combo.addItem("跟随主面板")
        # 保留隐藏组合框作为旧版插件/设置的兼容接口；正式界面使用连续滑动条。
        self.density_combo = QComboBox()
        self.density_combo.addItems(["清爽", "标准", "茂盛"])
        self.density_combo.hide()
        self.density_slider = self.slider(0, 100)
        self.density_slider.setValue(50)
        self.density_slider.setPageStep(10)
        self.density_slider.setToolTip("只改变枝叶、侧枝和花位数量，不改变植物尺寸与透明度")
        density_control = QWidget()
        density_layout = QVBoxLayout(density_control)
        density_layout.setContentsMargins(0, 0, 0, 0)
        density_layout.setSpacing(5)
        density_header = QHBoxLayout()
        density_header.setContentsMargins(0, 0, 0, 0)
        density_header.addWidget(QLabel("清爽"))
        density_header.addStretch()
        self.density_value_label = QLabel("标准 · 50%")
        self.density_value_label.setObjectName("densityValue")
        density_header.addWidget(self.density_value_label)
        density_header.addStretch()
        density_header.addWidget(QLabel("茂盛"))
        density_layout.addLayout(density_header)
        density_layout.addWidget(self.density_slider)
        self.density_slider.valueChanged.connect(self._update_density_label)
        layout_form.addRow("显示器", self.display_combo)
        layout_form.addRow("枝叶密度", density_control)
        layout.addWidget(layout_frame)

        presence_frame, presence_form = self.section("存在感", "默认保持安静；完成产出时才短暂提高亮度。")
        self.presence_slider = self.slider(20, 70)
        self.opacity_slider = self.slider(20, 70)
        self.reduce_motion_check = QCheckBox("减少动效")
        self.glass_effect_check = QCheckBox("玻璃效果")
        presence_form.addRow("植物尺寸", self.presence_slider)
        presence_form.addRow("植物透明度", self.opacity_slider)
        presence_form.addRow(self.reduce_motion_check)
        presence_form.addRow(self.glass_effect_check)
        layout.addWidget(presence_frame)
        self.ui_theme_combo.currentTextChanged.connect(self._sync_choice_cards)
        self.theme_combo.currentTextChanged.connect(self._sync_choice_cards)
        self.growth_layout_combo.currentTextChanged.connect(self._sync_choice_cards)
        self._sync_choice_cards()
        layout.addStretch()
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    def _update_density_label(self, value: int):
        """把连续数值翻译成人能快速理解的视觉档位。"""
        name = "清爽" if value < 34 else "茂盛" if value >= 70 else "标准"
        self.density_value_label.setText(f"{name} · {value}%")
        self.density_combo.blockSignals(True)
        self.density_combo.setCurrentText(name)
        self.density_combo.blockSignals(False)

    def _sync_choice_cards(self, *_):
        if not hasattr(self, "choice_buttons"):
            return
        selections = {
            "ui": self.ui_theme_combo.currentText(),
            "plant": self.theme_combo.currentText(),
            "layout": self.growth_layout_combo.currentText(),
        }
        for group, buttons in self.choice_buttons.items():
            for value, button in buttons.items():
                button.setChecked(value == selections[group])

    def build_behavior_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        behavior, behavior_form = self.section("启动与显示")
        self.close_behavior_combo = QComboBox()
        self.close_behavior_combo.addItems(["收起到托盘 / 菜单栏", "直接退出"])
        self.mini_when_hidden_check = QCheckBox("主面板隐藏时显示迷你计时器")
        self.cumulative_growth_check = QCheckBox("多个专注轮次累计生长")
        self.skip_final_rest_check = QCheckBox("最后一轮完成后跳过休息")
        self.start_minimized_check = QCheckBox("启动后显示迷你计时器")
        self.always_on_top_check = QCheckBox("主面板始终置顶")
        self.start_with_system_check = QCheckBox("开机启动")
        behavior_form.addRow("关闭主面板时", self.close_behavior_combo)
        behavior_form.addRow(self.mini_when_hidden_check)
        behavior_form.addRow(self.cumulative_growth_check)
        behavior_form.addRow(self.skip_final_rest_check)
        behavior_form.addRow(self.start_minimized_check)
        behavior_form.addRow(self.always_on_top_check)
        behavior_form.addRow(self.start_with_system_check)
        layout.addWidget(behavior)

        feedback, feedback_form = self.section("完成提醒")
        self.notifications_check = QCheckBox("专注完成通知")
        self.sound_check = QCheckBox("柔和完成音")
        feedback_form.addRow(self.notifications_check)
        feedback_form.addRow(self.sound_check)
        layout.addWidget(feedback)

        records, records_form = self.section("数据与文件", "记录只保存在本机，写入失败时不会清空输入。")
        self.records_dir_label = QLabel("")
        self.records_dir_label.setObjectName("path")
        self.records_dir_label.setWordWrap(True)
        buttons = QWidget()
        button_row = QHBoxLayout(buttons)
        button_row.setContentsMargins(0, 0, 0, 0)
        self.open_dir_btn = QPushButton("打开")
        self.choose_dir_btn = QPushButton("选择")
        button_row.addWidget(self.open_dir_btn)
        button_row.addWidget(self.choose_dir_btn)
        button_row.addStretch()
        records_form.addRow(self.records_dir_label)
        records_form.addRow(buttons)
        layout.addWidget(records)
        layout.addStretch()
        return page

    def apply_theme(self, theme_name: str, glass_effect: bool = True):
        self.setStyleSheet(build_app_qss(theme_name, glass_effect))

    def show_for_parent(self):
        """显示并激活现有设置窗口，避免重复创建多个实例。"""
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
