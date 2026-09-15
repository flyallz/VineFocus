"""番茄钟主控制面板。

组合计时、任务、设置、记录和看板流程；花藤绘制与托盘实现由独立模块提供。
"""

from __future__ import annotations

import math
import os
import time
from datetime import date, datetime

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import (
    GROWTH_LAYOUTS,
    PERIMETER_GROWTH_MODES,
    SCENE_TASKS,
    UI_THEMES,
    normalize_theme_name,
)
from .botanical_assets import BotanicalPreview
from .dialogs import DashboardDialog, FirstRunDialog, OutputDialog
from .overlay import VineOverlay
from .platform_integration import foreground_is_exclusive_fullscreen, set_start_with_system
from .settings_dialog import SettingsDialog
from .state import AppState
from .styles import build_app_qss
from .widgets import MiniButton, Toast, WindowControlButton

class PomodoroPanel(QWidget):
    def __init__(self, overlay: VineOverlay):
        super().__init__()
        self.state = AppState()
        self.overlay = overlay
        self.toast = Toast()
        self.mini_button = None
        self.phase = "focus"
        self.current_round = 1
        self.elapsed_before_pause = 0.0
        self.start_time = None
        self.running = False
        self.drag_pos = None
        self.finished = False
        self.awaiting_output = False
        self.demo_mode = False
        # 一次任务开始后冻结时长和总轮数；设置改动留给下一次任务，避免
        # 运行中分母或倒计时突然改变。恢复快照时会还原这三个值。
        self.session_focus_seconds: int | None = None
        self.session_rest_seconds: int | None = None
        self.session_total_rounds: int | None = None
        self.session_cumulative_growth: bool | None = None
        self.always_on_top = True
        self.display_mode = "panel"
        self._quitting = False
        self._first_close_notice_shown = bool(self.state.get("first_close_notice_shown", False))
        self.tray_controller = None
        self.pending_output_dialog = None
        self.dashboard_dialog = None
        self.last_focus_effective = True
        self.rest_visual_progress = 1.0
        self.last_tick_monotonic = time.monotonic()
        self.last_safe_elapsed = 0.0

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.update_timer)
        self.snapshot_timer = QTimer(self)
        self.snapshot_timer.setInterval(5000)
        self.snapshot_timer.timeout.connect(self.save_session_snapshot)
        self.snapshot_timer.start()
        self.overlay_visibility_timer = QTimer(self)
        self.overlay_visibility_timer.setInterval(1500)
        self.overlay_visibility_timer.timeout.connect(self.refresh_overlay_visibility)
        self.overlay_visibility_timer.start()

        self.setWindowTitle("花藤专注")
        self.apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.build_ui()
        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(lambda *_: self.refresh_display_options())
            app.screenRemoved.connect(lambda *_: self.refresh_display_options())
        self.apply_saved_settings()
        self.move_to_bottom_right()
        self.mini_button = MiniButton(self)
        self.mini_button.set_always_on_top(self.always_on_top)
        self.mini_button.apply_theme(self.ui_theme_combo.currentText())
        self.mini_button.hide()
        self.reset(confirm=False, clear_snapshot=False)
        self.restore_session_snapshot()
        if self.state.get("start_minimized", False):
            QTimer.singleShot(150, self.hide_to_mini)
        elif not self.state.get("onboarding_complete", False) and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QTimer.singleShot(260, self.show_first_run)

    def apply_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_always_on_top(self, enabled: bool):
        display_mode = self.display_mode
        self.always_on_top = enabled
        self.apply_window_flags()
        if self.mini_button:
            self.mini_button.set_always_on_top(enabled)
        if display_mode == "panel" and self.mini_button:
            self.show_panel()

    def build_ui(self):
        """创建只包含高频操作的紧凑主工作台。"""
        self.container = QWidget(self)
        self.container.setObjectName("appShell")
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(18, 15, 18, 16)
        main_layout.setSpacing(12)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 品牌标题栏：最小化遵循系统习惯，关闭按设置收起到托盘/菜单栏。
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        brand_column = QVBoxLayout()
        brand_column.setSpacing(0)
        self.title_label = QLabel("花藤专注")
        self.title_label.setObjectName("brandTitle")
        brand_subtitle = QLabel("让时间在桌面上生长")
        brand_subtitle.setObjectName("brandSub")
        brand_column.addWidget(self.title_label)
        brand_column.addWidget(brand_subtitle)
        self.minimize_btn = WindowControlButton("minimize")
        self.minimize_btn.setToolTip("最小化")
        self.minimize_btn.clicked.connect(self.showMinimized)
        self.close_btn = WindowControlButton("close")
        self.close_btn.setToolTip("隐藏到系统托盘")
        self.close_btn.clicked.connect(self.hide_panel_only)
        title_row.addLayout(brand_column)
        title_row.addStretch()
        title_row.addWidget(self.minimize_btn)
        title_row.addWidget(self.close_btn)

        # 计时卡：只突出时间和唯一主操作，其他状态退到辅助层级。
        self.focus_card = QFrame()
        self.focus_card.setObjectName("focusCard")
        self.focus_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        focus_layout = QVBoxLayout(self.focus_card)
        focus_layout.setContentsMargins(18, 14, 18, 16)
        focus_layout.setSpacing(8)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.phase_label = QLabel("专注")
        self.phase_label.setObjectName("phasePill")
        self.round_label = QLabel("第 1 / 4 轮")
        self.round_label.setObjectName("metaText")
        self.today_label = QLabel("今日 0 次")
        self.today_label.setObjectName("metaText")
        meta_row.addWidget(self.phase_label)
        meta_row.addWidget(self.round_label)
        meta_row.addStretch()
        meta_row.addWidget(self.today_label)

        self.time_label = QLabel("25:00")
        self.time_label.setObjectName("time")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("准备开始：选择场景、任务和本轮目标")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.start_btn = QPushButton("开始专注")
        self.start_btn.setObjectName("primaryButton")
        self.pause_btn = QPushButton("暂停")
        self.reset_btn = QPushButton("重置")
        self.start_btn.clicked.connect(self.start)
        self.pause_btn.clicked.connect(self.pause)
        self.reset_btn.clicked.connect(self.on_reset_clicked)
        button_row.addWidget(self.start_btn, stretch=2)
        button_row.addWidget(self.pause_btn)
        button_row.addWidget(self.reset_btn)

        focus_layout.addLayout(meta_row)
        focus_layout.addWidget(self.time_label)
        focus_layout.addWidget(self.status_label)
        focus_layout.addLayout(button_row)

        # 概念稿中的卡片内植物水印：使用与桌面覆盖层同源的高清资产，
        # 只作氛围层且鼠标穿透，不挤压计时信息的布局空间。
        self.focus_botanical = BotanicalPreview(parent=self.focus_card)
        self.focus_botanical.resize(116, 154)
        self.focus_botanical.set_visual("月白花藤", 0.72, 0)
        self.focus_botanical.set_visual_opacity(0.34)

        # 本轮任务：保留开始专注前真正需要频繁修改的字段。
        self.task_card = QFrame()
        self.task_card.setObjectName("taskCard")
        self.task_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        task_layout = QVBoxLayout(self.task_card)
        task_layout.setContentsMargins(15, 13, 15, 15)
        task_layout.setSpacing(9)

        task_header = QHBoxLayout()
        task_title_label = QLabel("本轮任务")
        task_title_label.setObjectName("sectionTitle")
        self.task_edit_btn = QPushButton("编辑")
        self.task_edit_btn.setObjectName("quietButton")
        self.task_edit_btn.setFixedWidth(62)
        self.task_edit_btn.clicked.connect(self.toggle_task_editor)
        task_header.addWidget(task_title_label)
        task_header.addStretch()
        task_header.addWidget(self.task_edit_btn)

        self.task_scene_badge = QLabel("科研论文")
        self.task_scene_badge.setObjectName("phasePill")
        self.task_scene_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.task_scene_badge.setMaximumWidth(118)
        self.task_summary_title = QLabel("论文写作")
        self.task_summary_title.setObjectName("taskSummaryTitle")
        self.task_summary_goal = QLabel("目标未填写 · 点击编辑补充本轮目标")
        self.task_summary_goal.setObjectName("brandSub")
        self.task_summary_goal.setWordWrap(True)
        summary_layout = QVBoxLayout()
        summary_layout.setSpacing(5)
        summary_layout.addWidget(self.task_scene_badge)
        summary_layout.addWidget(self.task_summary_title)
        summary_layout.addWidget(self.task_summary_goal)

        self.scene_combo = QComboBox()
        self.scene_combo.addItems(list(SCENE_TASKS.keys()))
        self.scene_combo.currentTextChanged.connect(self.scene_changed)
        self.task_combo = QComboBox()
        self.task_combo.currentTextChanged.connect(self.task_changed)
        self.custom_task_label = QLabel("任务名")
        self.custom_task_label.setObjectName("fieldLabel")
        self.custom_task_edit = QLineEdit()
        self.custom_task_edit.setPlaceholderText("例如：剪视频、练琴、整理房间")
        self.custom_task_edit.textChanged.connect(self.custom_task_changed)
        self.goal_edit = QLineEdit()
        self.goal_edit.setPlaceholderText("例如：完成一段论文修改或刷 20 道题")
        self.goal_edit.textChanged.connect(self.goal_changed)

        def form_row(label_text, widget):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(label_text)
            label.setObjectName("fieldLabel")
            label.setFixedWidth(46)
            row.addWidget(label)
            row.addWidget(widget, stretch=1)
            return row

        self.task_editor = QWidget()
        editor_layout = QVBoxLayout(self.task_editor)
        editor_layout.setContentsMargins(0, 7, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(form_row("场景", self.scene_combo))
        editor_layout.addLayout(form_row("任务", self.task_combo))
        self.custom_task_row = QHBoxLayout()
        self.custom_task_row.setSpacing(10)
        self.custom_task_label.setFixedWidth(46)
        self.custom_task_row.addWidget(self.custom_task_label)
        self.custom_task_row.addWidget(self.custom_task_edit, stretch=1)
        editor_layout.addLayout(self.custom_task_row)
        editor_layout.addLayout(form_row("目标", self.goal_edit))
        self.task_editor.hide()

        task_layout.addLayout(task_header)
        task_layout.addLayout(summary_layout)
        task_layout.addWidget(self.task_editor)

        # 低频设置移入独立页签窗口，主面板高度不再随设置展开。
        self.settings_dialog = SettingsDialog(self)
        settings_controls = (
            "preset_combo",
            "focus_spin",
            "rest_spin",
            "rounds_spin",
            "density_combo",
            "density_slider",
            "density_value_label",
            "theme_combo",
            "ui_theme_combo",
            "growth_layout_combo",
            "perimeter_growth_combo",
            "display_combo",
            "presence_slider",
            "opacity_slider",
            "reduce_motion_check",
            "glass_effect_check",
            "cumulative_growth_check",
            "start_minimized_check",
            "mini_when_hidden_check",
            "notifications_check",
            "sound_check",
            "start_with_system_check",
            "skip_final_rest_check",
            "close_behavior_combo",
            "always_on_top_check",
            "records_dir_label",
            "open_dir_btn",
            "choose_dir_btn",
        )
        for control_name in settings_controls:
            setattr(self, control_name, getattr(self.settings_dialog, control_name))

        self.preset_combo.currentTextChanged.connect(self.change_preset)
        self.focus_spin.valueChanged.connect(self.settings_changed)
        self.rest_spin.valueChanged.connect(self.settings_changed)
        self.rounds_spin.valueChanged.connect(self.settings_changed)
        self.density_slider.valueChanged.connect(self.change_density)
        self.density_slider.sliderReleased.connect(self.save_current_settings)
        self.settings_dialog.done_btn.clicked.connect(self.save_current_settings)
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        self.ui_theme_combo.currentTextChanged.connect(self.change_ui_theme)
        self.growth_layout_combo.currentTextChanged.connect(self.change_growth_layout)
        self.perimeter_growth_combo.currentTextChanged.connect(self.change_perimeter_growth_mode)
        self.display_combo.currentIndexChanged.connect(self.change_display_target)
        self.presence_slider.valueChanged.connect(self.change_plant_presentation)
        self.opacity_slider.valueChanged.connect(self.change_plant_presentation)
        self.reduce_motion_check.stateChanged.connect(self.change_plant_presentation)
        self.glass_effect_check.stateChanged.connect(self.change_ui_theme)
        self.cumulative_growth_check.stateChanged.connect(self.option_changed)
        self.start_minimized_check.stateChanged.connect(self.option_changed)
        self.mini_when_hidden_check.stateChanged.connect(self.option_changed)
        self.notifications_check.stateChanged.connect(self.option_changed)
        self.sound_check.stateChanged.connect(self.option_changed)
        self.start_with_system_check.stateChanged.connect(self.option_changed)
        self.skip_final_rest_check.stateChanged.connect(self.option_changed)
        self.close_behavior_combo.currentTextChanged.connect(self.option_changed)
        self.always_on_top_check.stateChanged.connect(self.option_changed)
        self.choose_dir_btn.clicked.connect(self.choose_records_dir)
        self.open_dir_btn.clicked.connect(self.open_records_dir)

        # 今日生长摘要让用户不用打开看板也能理解本轮带来的变化。
        self.growth_card = QFrame()
        self.growth_card.setObjectName("growthCard")
        self.growth_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        growth_layout = QHBoxLayout(self.growth_card)
        growth_layout.setContentsMargins(15, 12, 15, 12)
        growth_layout.setSpacing(10)
        self.growth_botanical = BotanicalPreview()
        self.growth_botanical.setFixedSize(66, 52)
        self.growth_botanical.set_visual("月白花藤", 0.78, 0)
        self.growth_botanical.set_visual_opacity(0.60)
        growth_text = QVBoxLayout()
        growth_text.setSpacing(1)
        growth_title = QLabel("今日生长")
        growth_title.setObjectName("sectionTitle")
        self.growth_summary_label = QLabel("新叶 0 · 花苞 0")
        self.growth_summary_label.setObjectName("brandSub")
        growth_text.addWidget(growth_title)
        growth_text.addWidget(self.growth_summary_label)
        growth_layout.addWidget(self.growth_botanical)
        growth_layout.addLayout(growth_text)
        growth_layout.addStretch()

        tool_row = QHBoxLayout()
        tool_row.setSpacing(7)
        self.demo_btn = QPushButton("30 秒演示")
        self.demo_btn.setObjectName("quietButton")
        self.demo_btn.clicked.connect(self.demo)
        self.dashboard_btn = QPushButton("成长看板")
        self.dashboard_btn.clicked.connect(self.show_dashboard)
        self.settings_toggle_btn = QPushButton("设置")
        self.settings_toggle_btn.clicked.connect(self.toggle_settings_frame)
        tool_row.addWidget(self.demo_btn)
        tool_row.addWidget(self.dashboard_btn)
        tool_row.addStretch()
        tool_row.addWidget(self.settings_toggle_btn)

        main_layout.addLayout(title_row)
        main_layout.addWidget(self.focus_card)
        main_layout.addWidget(self.task_card)
        main_layout.addWidget(self.growth_card)
        main_layout.addLayout(tool_row)

        self._apply_glass_depth()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.container)

        self.setStyleSheet(build_app_qss())
        self.setMinimumWidth(430)
        self.resize(468, 540)
        QTimer.singleShot(0, self._fit_panel_to_content)
        QTimer.singleShot(0, self._position_visual_accents)

    def _apply_glass_depth(self):
        """用跨平台的柔和投影建立玻璃层级，不依赖 Windows/macOS 私有模糊 API。"""
        self._glass_shadows = []
        for widget, blur, offset_y, alpha in (
            (self.focus_card, 28.0, 7.0, 88),
            (self.task_card, 20.0, 5.0, 58),
            (self.growth_card, 16.0, 4.0, 46),
        ):
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(blur)
            effect.setOffset(0.0, offset_y)
            effect.setColor(QColor(1, 7, 14, alpha))
            widget.setGraphicsEffect(effect)
            self._glass_shadows.append(effect)

    def _position_visual_accents(self):
        """保持计时卡植物贴在右下角，不参与文字布局。"""
        if not hasattr(self, "focus_botanical"):
            return
        x = max(0, self.focus_card.width() - self.focus_botanical.width() - 3)
        y = max(0, self.focus_card.height() - self.focus_botanical.height() - 5)
        self.focus_botanical.move(x, y)
        self.focus_botanical.lower()

    def sync_botanical_previews(self):
        if not hasattr(self, "focus_botanical"):
            return
        theme_name = self.theme_combo.currentText() if hasattr(self, "theme_combo") else "月白花藤"
        # 管理面板里的装饰植物仍沿用既有“目标推进”花朵口径。本轮新增的
        # 逐轮花期只作用于桌面覆盖层，不能反向改写面板花朵或密度设置。
        progress = max(0.0, min(1.0, float(self.overlay.progress)))
        _, effective_units, _ = self.state.growth_state()
        flowers = max(0, int(effective_units))
        self.focus_botanical.set_visual(theme_name, progress, flowers)
        self.growth_botanical.set_visual(theme_name, progress, flowers)

    def sync_desktop_growth_from_state(self, *, animate_bloom: bool = False):
        """只同步桌面藤蔓：长度按当前植株目标，花期映射到既有花位。"""
        completed, _, chapter = self.state.growth_state()
        target = self.state.growth_target()
        self.overlay.set_growth_chapter(chapter)
        self.overlay.set_progress(min(1.0, completed / max(1, target)))
        self.overlay.set_bloom_progress(
            self.state.bloom_progress(completed, target),
            animate=animate_bloom,
        )

    def _fit_panel_to_content(self):
        """让主面板高度始终跟随可见内容，避免恢复后留下大块空白。"""
        if not hasattr(self, "container"):
            return
        layout = self.container.layout()
        if layout is not None:
            layout.activate()
        target_height = max(1, self.container.sizeHint().height())
        old_bottom = self.y() + self.height()
        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height)
        if self.height() != target_height:
            self.resize(self.width(), target_height)
            if self.isVisible():
                self.move(self.x(), old_bottom - target_height)
        if self.isVisible():
            self.ensure_window_visible()

    def toggle_settings_frame(self):
        self.settings_dialog.show_for_parent()

    def show_first_run(self):
        """首次运行只出现一次；所有选择复用正式设置控件与保存逻辑。"""
        dialog = FirstRunDialog(self)
        dialog.setStyleSheet(build_app_qss(self.ui_theme_combo.currentText(), True))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            preset, theme_name, layout_name = dialog.choices()
            self.preset_combo.setCurrentText(preset)
            self.theme_combo.setCurrentText(theme_name)
            self.growth_layout_combo.setCurrentText(layout_name)
            self.state.data["onboarding_complete"] = True
            self.save_current_settings()
            self.toast.show_message("第一株花藤已经准备好，开始专注吧")
        else:
            self.state.data["onboarding_complete"] = True
            self.state.save()

    def apply_saved_settings(self):
        widgets = [
            self.scene_combo, self.task_combo, self.preset_combo, self.focus_spin, self.rest_spin,
            self.rounds_spin, self.density_combo, self.density_slider, self.theme_combo, self.ui_theme_combo,
            self.growth_layout_combo, self.perimeter_growth_combo,
            self.presence_slider, self.opacity_slider,
            self.reduce_motion_check, self.glass_effect_check, self.start_minimized_check,
            self.mini_when_hidden_check, self.notifications_check, self.sound_check,
            self.start_with_system_check, self.skip_final_rest_check, self.close_behavior_combo,
            self.always_on_top_check,
            self.cumulative_growth_check, self.custom_task_edit, self.goal_edit,
        ]
        for w in widgets:
            w.blockSignals(True)
        scene = self.state.get("last_scene_mode", "科研论文")
        if scene not in SCENE_TASKS:
            scene = "科研论文"
        self.scene_combo.setCurrentText(scene)
        self.update_task_options(scene, save=False)
        last_task = self.state.get("last_task_type", "")
        tasks = SCENE_TASKS.get(scene, SCENE_TASKS["自定义"])
        self.task_combo.setCurrentText(last_task if last_task in tasks else tasks[0])
        self.preset_combo.setCurrentText(self.state.get("preset", "25+5"))
        self.focus_spin.setValue(int(self.state.get("focus_minutes", 25)))
        self.rest_spin.setValue(int(self.state.get("rest_minutes", 5)))
        self.rounds_spin.setValue(int(self.state.get("rounds", 1)))
        density_value = max(0, min(100, int(self.state.get("plant_density", 50))))
        self.density_slider.setValue(density_value)
        self.settings_dialog._update_density_label(density_value)
        ui_theme = self.state.get("ui_theme", "夜色流光")
        self.ui_theme_combo.setCurrentText(ui_theme if ui_theme in UI_THEMES else "夜色流光")
        self.theme_combo.setCurrentText(
            normalize_theme_name(self.state.get("vine_theme", "月白花藤"))
        )
        layout_name = self.state.get("growth_layout", "静谧单株")
        self.growth_layout_combo.setCurrentText(layout_name if layout_name in GROWTH_LAYOUTS else "静谧单株")
        perimeter_mode = self.state.get("perimeter_growth_mode", "四边同步")
        self.perimeter_growth_combo.setCurrentText(
            perimeter_mode if perimeter_mode in PERIMETER_GROWTH_MODES else "四边同步"
        )
        self.presence_slider.setValue(int(self.state.get("plant_presence", 36)))
        self.opacity_slider.setValue(int(self.state.get("plant_opacity", 40)))
        self.reduce_motion_check.setChecked(bool(self.state.get("reduce_motion", False)))
        self.glass_effect_check.setChecked(bool(self.state.get("glass_effect", True)))
        self.start_minimized_check.setChecked(bool(self.state.get("start_minimized", False)))
        self.mini_when_hidden_check.setChecked(bool(self.state.get("mini_when_hidden", True)))
        self.notifications_check.setChecked(bool(self.state.get("notifications", True)))
        self.sound_check.setChecked(bool(self.state.get("completion_sound", True)))
        self.start_with_system_check.setChecked(bool(self.state.get("start_with_system", False)))
        self.skip_final_rest_check.setChecked(bool(self.state.get("skip_final_rest", False)))
        self.close_behavior_combo.setCurrentText(self.state.get("close_behavior", "收起到托盘 / 菜单栏"))
        self.always_on_top_check.setChecked(bool(self.state.get("always_on_top", False)))
        self.cumulative_growth_check.setChecked(bool(self.state.get("cumulative_growth", True)))
        self.custom_task_edit.setText(self.state.get("last_custom_task", ""))
        self.goal_edit.setText(self.state.get("last_goal", ""))
        self.update_custom_task_visibility()
        self.refresh_task_summary()
        for w in widgets:
            w.blockSignals(False)
        self.overlay.set_density(self.density_slider.value())
        self.overlay.set_theme(self.theme_combo.currentText())
        self.overlay.set_layout(self.growth_layout_combo.currentText())
        self.overlay.set_perimeter_growth_mode(self.perimeter_growth_combo.currentText())
        self.refresh_display_options()
        self.overlay.set_presentation(
            self.presence_slider.value(),
            self.opacity_slider.value(),
            self.reduce_motion_check.isChecked(),
        )
        self.sync_desktop_growth_from_state()
        self.settings_dialog._sync_choice_cards()
        self.sync_botanical_previews()
        self.apply_ui_theme()
        self.set_always_on_top(self.always_on_top_check.isChecked())
        self.refresh_records_dir_label()
        self.refresh_today_label()

    def update_task_options(self, scene: str, save: bool = True):
        current = self.task_combo.currentText()
        tasks = SCENE_TASKS.get(scene, SCENE_TASKS["自定义"])
        was_blocked = self.task_combo.blockSignals(True)
        self.task_combo.clear()
        self.task_combo.addItems(tasks)
        self.task_combo.setCurrentText(current if current in tasks else tasks[0])
        self.task_combo.blockSignals(was_blocked)
        if save:
            self.save_current_settings()

    def save_current_settings(self):
        self.state.data["preset"] = self.preset_combo.currentText()
        self.state.data["focus_minutes"] = self.focus_spin.value()
        self.state.data["rest_minutes"] = self.rest_spin.value()
        self.state.data["rounds"] = self.rounds_spin.value()
        self.state.data["plant_density"] = self.density_slider.value()
        self.state.data["density"] = self.overlay.density_name
        self.state.data["ui_theme"] = self.ui_theme_combo.currentText()
        self.state.data["vine_theme"] = self.theme_combo.currentText()
        self.state.data["growth_layout"] = self.growth_layout_combo.currentText()
        self.state.data["perimeter_growth_mode"] = self.perimeter_growth_combo.currentText()
        self.state.data["display_target"] = self.display_combo.currentData() or "follow"
        self.state.data["plant_presence"] = self.presence_slider.value()
        self.state.data["plant_opacity"] = self.opacity_slider.value()
        self.state.data["reduce_motion"] = self.reduce_motion_check.isChecked()
        self.state.data["glass_effect"] = self.glass_effect_check.isChecked()
        self.state.data["start_minimized"] = self.start_minimized_check.isChecked()
        self.state.data["mini_when_hidden"] = self.mini_when_hidden_check.isChecked()
        self.state.data["always_on_top"] = self.always_on_top_check.isChecked()
        self.state.data["cumulative_growth"] = self.cumulative_growth_check.isChecked()
        self.state.data["notifications"] = self.notifications_check.isChecked()
        self.state.data["completion_sound"] = self.sound_check.isChecked()
        self.state.data["start_with_system"] = self.start_with_system_check.isChecked()
        self.state.data["skip_final_rest"] = self.skip_final_rest_check.isChecked()
        self.state.data["close_behavior"] = self.close_behavior_combo.currentText()
        self.state.data["last_scene_mode"] = self.scene_combo.currentText()
        self.state.data["last_task_type"] = self.task_combo.currentText()
        self.state.data["last_custom_task"] = self.custom_task_edit.text().strip()
        self.state.data["last_goal"] = self.goal_edit.text().strip()
        self.state.save()

    def should_show_custom_task(self) -> bool:
        return self.scene_combo.currentText() == "自定义" or self.task_combo.currentText() == "自定义任务"

    def update_custom_task_visibility(self):
        visible = self.should_show_custom_task()
        self.custom_task_label.setVisible(visible)
        self.custom_task_edit.setVisible(visible)

    def get_display_task_type(self) -> str:
        task = self.task_combo.currentText()
        custom = self.custom_task_edit.text().strip()
        if self.should_show_custom_task() and custom:
            return custom
        return task

    def custom_task_changed(self, *args):
        self.save_current_settings()
        self.refresh_task_summary()

    def toggle_task_editor(self):
        """展开或收起低频任务字段，默认保持主面板简洁。"""
        visible = not self.task_editor.isVisible()
        self.task_editor.setVisible(visible)
        self.task_edit_btn.setText("收起" if visible else "编辑")
        QTimer.singleShot(0, self._fit_panel_to_content)

    def refresh_task_summary(self):
        if not hasattr(self, "task_summary_title"):
            return
        self.task_scene_badge.setText(self.scene_combo.currentText())
        self.task_summary_title.setText(self.get_display_task_type() or "未选择任务")
        goal = self.goal_edit.text().strip()
        self.task_summary_goal.setText(goal or "目标未填写 · 点击编辑补充本轮目标")

    def is_cumulative_growth(self) -> bool:
        if self.session_cumulative_growth is not None:
            return self.session_cumulative_growth
        return self.cumulative_growth_check.isChecked()

    def visual_progress_for_focus(self, phase_progress: float) -> float:
        phase_progress = max(0.0, min(1.0, phase_progress))
        if not self.is_cumulative_growth():
            return phase_progress
        completed, _, _ = self.state.growth_state()
        target = self.state.growth_target()
        base = 0 if completed >= target else completed
        return min(1.0, (base + phase_progress) / max(1, target))

    def visual_progress_for_round_end(self, _effective: bool) -> float:
        if not self.is_cumulative_growth():
            return 1.0
        completed, _, _ = self.state.growth_state()
        return min(1.0, completed / max(1, self.state.growth_target()))

    def refresh_today_label(self):
        growth_mode = "累计" if self.is_cumulative_growth() else "单轮"
        self.today_label.setText(f"今日 {self.state.today_completed()} 次 · {growth_mode}生长")
        if hasattr(self, "growth_summary_label"):
            completed, effective_units, chapter = self.state.growth_state()
            target = self.state.growth_target()
            stage = self.state.growth_stage_name(completed, effective_units, target)
            self.growth_summary_label.setText(
                f"第 {chapter} 株 · 成长 {completed}/{target} · 当前阶段 {stage} · 目标推进 {effective_units} 次"
            )

    def refresh_records_dir_label(self):
        path = str(self.state.get_records_dir())
        self.records_dir_label.setText("..." + path[-33:] if len(path) > 36 else path)

    def choose_records_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择记录保存目录", str(self.state.get_records_dir()))
        if folder:
            try:
                self.state.set_records_dir(folder)
            except OSError as exc:
                QMessageBox.warning(self, "无法使用该目录", f"请确认目录可写，或选择其他位置。\n\n{exc}")
                return
            self.refresh_records_dir_label()
            self.toast.show_message("📁 记录保存目录已更新")
            self.status_label.setText("记录目录已更新，后续 JSON 和 Markdown 会保存到新目录")

    def open_records_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.state.get_records_dir())))

    def scene_changed(self, scene: str):
        self.update_task_options(scene, save=False)
        self.update_custom_task_visibility()
        self.save_current_settings()
        self.refresh_task_summary()
        self.status_label.setText(f"已切换到：{scene}")

    def task_changed(self, *args):
        self.update_custom_task_visibility()
        self.save_current_settings()
        self.refresh_task_summary()

    def goal_changed(self, *args):
        self.save_current_settings()
        self.refresh_task_summary()

    def refresh_display_options(self):
        """重建显示器列表；使用屏幕名称保存选择，避免排序变化导致漂移。"""
        if not hasattr(self, "display_combo"):
            return
        saved = self.state.get("display_target", "follow")
        self.display_combo.blockSignals(True)
        self.display_combo.clear()
        self.display_combo.addItem("跟随主面板", "follow")
        self.display_combo.addItem("主显示器", "primary")
        screens = QGuiApplication.screens()
        for index, screen in enumerate(screens, start=1):
            screen_name = screen.name() or f"screen-{index}"
            self.display_combo.addItem(f"显示器 {index} · {screen_name}", f"screen:{screen_name}")
        target_index = self.display_combo.findData(saved)
        if target_index < 0:
            # 曾选择的外接屏已断开：迁回主屏，并保存可预测的新选择。
            saved = "primary"
            target_index = self.display_combo.findData(saved)
            self.state.data["display_target"] = saved
            self.state.save()
        self.display_combo.setCurrentIndex(max(0, target_index))
        self.display_combo.blockSignals(False)
        self.sync_overlay_geometry()

    def selected_overlay_screen(self):
        target = self.display_combo.currentData() if hasattr(self, "display_combo") else "follow"
        if target == "primary":
            return QGuiApplication.primaryScreen()
        if isinstance(target, str) and target.startswith("screen:"):
            name = target.split(":", 1)[1]
            return next((screen for screen in QGuiApplication.screens() if screen.name() == name), None)
        center = self.frameGeometry().center()
        return (
            next(
                (screen for screen in QGuiApplication.screens() if screen.geometry().contains(center)),
                None,
            )
            or self.screen()
            or QGuiApplication.primaryScreen()
        )

    def sync_overlay_geometry(self):
        """一株植物只绘制在一个完整屏幕，不跨不同 DPI 的显示器。"""
        screen = self.selected_overlay_screen()
        if screen is None:
            return
        # 植物属于桌面边缘装饰，应按完整屏幕而非扣除任务栏/Dock 后的工作区定位。
        geometry = screen.geometry()
        if self.overlay.geometry() != geometry:
            self.overlay.setGeometry(geometry)

    def refresh_overlay_visibility(self):
        """全屏视频、演示或游戏运行时暂时隐藏植物，离开后自动恢复。"""
        if foreground_is_exclusive_fullscreen():
            self.overlay.hide()
        elif not self._quitting and not self.overlay.isVisible():
            self.overlay.show()

    def change_display_target(self, *args):
        self.sync_overlay_geometry()
        self.save_current_settings()
        self.status_label.setText(f"花藤显示位置：{self.display_combo.currentText()}")

    def preferred_screen(self):
        """优先使用鼠标所在屏幕，适配多显示器和不同 DPI。"""
        return (
            QGuiApplication.screenAt(QCursor.pos())
            or self.screen()
            or QGuiApplication.primaryScreen()
        )

    def move_to_bottom_right(self, screen=None):
        screen = screen or self.preferred_screen()
        if not screen:
            return
        area = screen.availableGeometry()
        margin = 22
        self.move(
            area.right() - self.width() - margin + 1,
            area.bottom() - self.height() - margin + 1,
        )

    def ensure_window_visible(self):
        """将窗口限制在某块屏幕的可用范围内，避免托盘恢复到屏幕外。"""
        screens = QGuiApplication.screens()
        center = self.frameGeometry().center()
        screen = next(
            (candidate for candidate in screens if candidate.availableGeometry().contains(center)),
            None,
        )
        if screen is None:
            self.move_to_bottom_right(self.preferred_screen())
            return

        area = screen.availableGeometry()
        margin = 12
        max_x = max(area.left() + margin, area.right() - self.width() - margin + 1)
        max_y = max(area.top() + margin, area.bottom() - self.height() - margin + 1)
        x = min(max(self.x(), area.left() + margin), max_x)
        y = min(max(self.y(), area.top() + margin), max_y)
        self.move(x, y)

    def activate_after_restore(self):
        if self.display_mode != "panel":
            return
        self.setWindowOpacity(1.0)
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.ensure_window_visible()
        self.raise_()
        self.activateWindow()
        handle = self.windowHandle()
        if handle is not None:
            handle.requestActivate()

    def show_panel(self):
        """从托盘或小圆点可靠恢复为普通窗口。"""
        self.display_mode = "panel"
        if self.mini_button:
            self.mini_button.hide()
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.setWindowOpacity(1.0)
        self.showNormal()
        self.ensure_window_visible()
        self.show()
        self._fit_panel_to_content()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self.activate_after_restore)
        QTimer.singleShot(0, self._fit_panel_to_content)
        QTimer.singleShot(80, self.activate_after_restore)

    def hide_panel_only(self):
        if self.close_behavior_combo.currentText() == "直接退出":
            self.real_quit()
            return
        self.save_current_settings()
        self.settings_dialog.hide()
        self.hide()
        if self.mini_when_hidden_check.isChecked() and (self.running or self.awaiting_output):
            self.display_mode = "mini"
            if self.mini_button:
                self.mini_button.move_to_bottom_right(self.preferred_screen())
                self.mini_button.show()
                self.mini_button.raise_()
        else:
            self.display_mode = "tray"
            if self.mini_button:
                self.mini_button.hide()
        if not self._first_close_notice_shown:
            self._first_close_notice_shown = True
            self.state.data["first_close_notice_shown"] = True
            self.state.save()
            self.toast.show_message("应用仍在后台运行，可从托盘或菜单栏恢复")

    def hide_to_mini(self):
        self.save_current_settings()
        self.display_mode = "mini"
        self.settings_dialog.hide()
        self.hide()
        if self.mini_button:
            self.mini_button.move_to_bottom_right(self.preferred_screen())
            self.mini_button.show()
            self.mini_button.raise_()

    def hide_mini(self):
        if self.mini_button:
            self.mini_button.hide()
        if self.display_mode == "mini":
            self.display_mode = "tray"

    def show_mini(self):
        if self.mini_button:
            self.display_mode = "mini"
            self.settings_dialog.hide()
            self.hide()
            self.mini_button.move_to_bottom_right(self.preferred_screen())
            self.mini_button.show()
            self.mini_button.raise_()

    def real_quit(self):
        self._quitting = True
        self.save_current_settings()
        self.save_session_snapshot()
        self.settings_dialog.close()
        QApplication.quit()

    def set_tray_controller(self, controller):
        self.tray_controller = controller
        if hasattr(controller, "apply_theme"):
            controller.apply_theme(self.ui_theme_combo.currentText())

    def notify_completion(self, title: str, message: str):
        panel_is_foreground = self.display_mode == "panel" and self.isVisible() and self.isActiveWindow()
        if self.notifications_check.isChecked() and self.tray_controller is not None and not panel_is_foreground:
            self.tray_controller.show_message(title, message)

    def option_changed(self, *args):
        requested_startup = self.start_with_system_check.isChecked()
        previous_startup = bool(self.state.get("start_with_system", False))
        if requested_startup != previous_startup:
            success, message = set_start_with_system(requested_startup)
            if not success:
                self.start_with_system_check.blockSignals(True)
                self.start_with_system_check.setChecked(previous_startup)
                self.start_with_system_check.blockSignals(False)
            self.toast.show_message(message)
        self.save_current_settings()
        self.set_always_on_top(self.always_on_top_check.isChecked())
        self.refresh_today_label()

    def change_preset(self, text: str):
        if self.running:
            self.status_label.setText("运行中暂不切换模式，请先暂停或重置")
            return
        presets = {"25+5": (25, 5), "45+10": (45, 10), "60+10": (60, 10)}
        if text in presets:
            focus, rest = presets[text]
            self.focus_spin.blockSignals(True)
            self.rest_spin.blockSignals(True)
            self.focus_spin.setValue(focus)
            self.rest_spin.setValue(rest)
            self.focus_spin.blockSignals(False)
            self.rest_spin.blockSignals(False)
        self.demo_mode = False
        self.save_current_settings()
        self.reset()

    def settings_changed(self, *args):
        if self.running:
            return
        self.demo_mode = False
        current_focus, current_rest = self.focus_spin.value(), self.rest_spin.value()
        if current_focus == 25 and current_rest == 5:
            matched = "25+5"
        elif current_focus == 45 and current_rest == 10:
            matched = "45+10"
        elif current_focus == 60 and current_rest == 10:
            matched = "60+10"
        else:
            matched = "自定义"
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(matched)
        self.preset_combo.blockSignals(False)
        self.save_current_settings()
        self.reset()

    def change_density(self, value: int):
        self.overlay.set_density(value)
        # 密度只重建可用节点；桌面花期百分比和面板花朵口径各自保持不变。
        self.sync_botanical_previews()
        self.status_label.setText(
            f"枝叶密度：{self.overlay.density_name} · {self.overlay.density_value}%"
        )

    def change_theme(self, name: str):
        self.overlay.set_theme(name)
        self.sync_botanical_previews()
        self.save_current_settings()
        self.status_label.setText(f"花藤主题已切换为：{name}")

    def change_growth_layout(self, name: str):
        self.overlay.set_layout(name)
        self.sync_botanical_previews()
        self.save_current_settings()
        self.status_label.setText(f"生长布局已切换为：{name}")

    def change_perimeter_growth_mode(self, mode: str):
        self.overlay.set_perimeter_growth_mode(mode)
        self.save_current_settings()
        self.status_label.setText(f"环屏节奏：{self.overlay.perimeter_growth_mode}")

    def change_plant_presentation(self, *args):
        self.overlay.set_presentation(
            self.presence_slider.value(),
            self.opacity_slider.value(),
            self.reduce_motion_check.isChecked(),
        )
        self.save_current_settings()

    def apply_ui_theme(self):
        theme_name = self.ui_theme_combo.currentText() if hasattr(self, "ui_theme_combo") else "夜色流光"
        glass = self.glass_effect_check.isChecked() if hasattr(self, "glass_effect_check") else True
        qss = build_app_qss(theme_name, glass)
        self.setStyleSheet(qss)
        self.settings_dialog.apply_theme(theme_name, glass)
        self.toast.apply_theme(theme_name)
        if self.mini_button:
            self.mini_button.apply_theme(theme_name)
        if self.tray_controller is not None:
            self.tray_controller.apply_theme(theme_name)

    def change_ui_theme(self, *args):
        self.apply_ui_theme()
        self.save_current_settings()

    def get_focus_seconds(self) -> int:
        if self.session_focus_seconds is not None:
            return self.session_focus_seconds
        return 30 if self.demo_mode else self.focus_spin.value() * 60

    def get_rest_seconds(self) -> int:
        if self.session_rest_seconds is not None:
            return self.session_rest_seconds
        return 8 if self.demo_mode else self.rest_spin.value() * 60

    def get_total_rounds(self) -> int:
        if self.session_total_rounds is not None:
            return self.session_total_rounds
        return 1 if self.demo_mode else self.rounds_spin.value()

    def prepare_session_plan(self):
        """在任务首次开始时冻结节奏；已完成的半株按原分母继续。"""
        if (
            self.session_focus_seconds is not None
            and self.session_rest_seconds is not None
            and self.session_total_rounds is not None
            and self.session_cumulative_growth is not None
        ):
            return
        requested_cumulative = self.cumulative_growth_check.isChecked()
        self.session_cumulative_growth = requested_cumulative
        self.session_focus_seconds = 30 if self.demo_mode else self.focus_spin.value() * 60
        self.session_rest_seconds = 8 if self.demo_mode else self.rest_spin.value() * 60
        requested_rounds = 1 if self.demo_mode else self.rounds_spin.value()
        if requested_cumulative and not self.demo_mode:
            completed, _, _ = self.state.growth_state()
            target = self.state.growth_target()
            if 0 < completed < target:
                # 应用重启或重置后继续同一株，不能让设置滑块改写它的分母。
                requested_rounds = target
                self.current_round = max(self.current_round, min(target, completed + 1))
        self.session_total_rounds = max(1, int(requested_rounds))

    def clear_session_plan(self):
        self.session_focus_seconds = None
        self.session_rest_seconds = None
        self.session_total_rounds = None
        self.session_cumulative_growth = None

    def get_phase_total_seconds(self) -> int:
        return self.get_focus_seconds() if self.phase == "focus" else self.get_rest_seconds()

    def get_elapsed(self) -> float:
        if self.running and self.start_time is not None:
            return self.elapsed_before_pause + (time.monotonic() - self.start_time)
        return self.elapsed_before_pause

    def start(self):
        if self.awaiting_output:
            effective = self.capture_output_after_focus()
            if effective is not None:
                self.finish_focus_record(effective)
            return
        if self.finished:
            self.reset(confirm=False)
        if not self.running:
            if self.phase == "focus":
                self.prepare_session_plan()
                if self.is_cumulative_growth():
                    completed, _, chapter = self.state.begin_next_growth_chapter(
                        self.get_total_rounds()
                    )
                else:
                    # 单轮生长每轮完成一株；暂停/继续时 completed 仍为 0，
                    # 因而不会换株，下一轮真正开始前才创建新株。
                    completed, _, chapter = self.state.begin_next_growth_chapter(
                        1,
                        replace_incomplete=True,
                    )
                self.overlay.set_growth_chapter(chapter)
                if self.elapsed_before_pause <= 0.0:
                    if self.is_cumulative_growth():
                        self.sync_desktop_growth_from_state()
                    else:
                        self.overlay.set_progress(0.0)
                        self.overlay.set_bloom_progress(0.0)
                    self.refresh_today_label()
                    self.sync_botanical_previews()
            self.save_current_settings()
            self.running = True
            self.start_time = time.monotonic()
            self.last_tick_monotonic = self.start_time
            self.last_safe_elapsed = self.elapsed_before_pause
            self.timer.start()
            if self.phase == "focus":
                scene, task, goal = self.scene_combo.currentText(), self.get_display_task_type(), self.goal_edit.text().strip()
                self.status_label.setText(f"专注中：{scene}｜{task}｜{goal or '本轮目标未填写'}")
                self.overlay.set_rest_mode(False)
            else:
                self.status_label.setText("休息中：花藤保持当前生长状态并轻轻呼吸")
                self.overlay.set_rest_mode(True)
            self.start_btn.setText("进行中")
            self.refresh_labels()
            self.save_session_snapshot()

    def pause(self):
        if self.running:
            self.elapsed_before_pause = self.get_elapsed()
            self.start_time = None
            self.running = False
            self.timer.stop()
            self.status_label.setText("已暂停：当前状态已保留")
            self.start_btn.setText("继续")
            self.refresh_labels()
            self.save_session_snapshot()

    def on_reset_clicked(self):
        """计时阶段是重置；休息阶段则按产品语义跳过休息。"""
        if self.phase == "rest" and not self.finished and not self.awaiting_output:
            self.skip_rest()
        else:
            self.reset()

    def skip_rest(self):
        if self.phase != "rest" or self.awaiting_output:
            return
        self.running = False
        self.timer.stop()
        if self.current_round < self.get_total_rounds():
            self.current_round += 1
            self.phase = "focus"
            self.elapsed_before_pause = 0.0
            self.start_time = None
            self.overlay.set_rest_mode(False)
            self.status_label.setText("休息已跳过：下一轮已经准备好")
            self.refresh_labels()
            self.save_session_snapshot()
            return
        self.finish_all_rounds()

    def finish_all_rounds(self):
        """统一结束入口，避免自然结束和跳过休息产生不同状态。"""
        self.running = False
        self.finished = True
        self.timer.stop()
        self.overlay.set_rest_mode(False)
        self.overlay.set_progress(self.rest_visual_progress)
        self.status_label.setText("全部轮次完成！可以查看成长看板")
        self.toast.show_message("全部轮次完成！建议查看成长看板", 4500)
        self.refresh_labels()
        self.state.clear_session_snapshot()

    def reset(self, checked=False, *, confirm: bool = True, clear_snapshot: bool = True):
        has_active_state = self.running or self.elapsed_before_pause > 0 or self.awaiting_output or self.phase == "rest"
        if confirm and has_active_state:
            answer = QMessageBox.question(
                self,
                "重置本轮？",
                "本轮尚未提交的生长和计时进度会被放弃，任务文字会保留。",
                QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Reset:
                return
        self.running = False
        self.timer.stop()
        self.phase = "focus"
        self.current_round = 1
        self.clear_session_plan()
        self.elapsed_before_pause = 0.0
        self.start_time = None
        self.finished = False
        self.awaiting_output = False
        self.last_focus_effective = True
        self.rest_visual_progress = 0.0 if self.is_cumulative_growth() else 1.0
        self.overlay.set_rest_mode(False)
        if self.is_cumulative_growth():
            completed, _, chapter = self.state.growth_state()
            target = self.state.growth_target()
            if 0 < completed < target:
                # 已提交的轮次属于永久成长；重置只放弃当前未提交计时，
                # 再开始时从下一轮接着长，而不是把藤蔓退回第一轮。
                self.session_total_rounds = target
                self.current_round = min(target, completed + 1)
            self.overlay.set_growth_chapter(chapter)
            self.overlay.set_progress(min(1.0, completed / max(1, target)))
            self.overlay.set_bloom_progress(self.state.bloom_progress(completed, target))
        else:
            self.overlay.set_progress(0.0)
            self.overlay.set_bloom_progress(0.0)
        self.sync_botanical_previews()
        self.status_label.setText("准备开始：选择场景、任务和本轮目标")
        self.start_btn.setText("开始")
        self.refresh_today_label()
        self.refresh_labels()
        if clear_snapshot:
            self.state.clear_session_snapshot()

    def save_session_snapshot(self):
        """保存未完成会话；离线时间永远不计入专注。"""
        active = self.running or self.elapsed_before_pause > 0 or self.awaiting_output or self.phase == "rest"
        if not active or self.finished:
            if self.finished:
                self.state.clear_session_snapshot()
            return
        self.state.save_session_snapshot({
            "phase": self.phase,
            "current_round": self.current_round,
            "elapsed": self.get_elapsed(),
            "remaining_seconds": max(0, self.get_phase_total_seconds() - int(self.get_elapsed())),
            "awaiting_output": self.awaiting_output,
            "demo_mode": self.demo_mode,
            "last_focus_effective": self.last_focus_effective,
            "session_focus_seconds": self.get_focus_seconds(),
            "session_rest_seconds": self.get_rest_seconds(),
            "session_total_rounds": self.get_total_rounds(),
            "session_cumulative_growth": self.is_cumulative_growth(),
            "task": {
                "scene": self.scene_combo.currentText(),
                "task_type": self.task_combo.currentText(),
                "custom_name": self.custom_task_edit.text().strip(),
                "goal": self.goal_edit.text().strip(),
            },
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        })

    def restore_session_snapshot(self):
        snapshot = self.state.load_session_snapshot()
        if not snapshot:
            return
        phase = snapshot.get("phase")
        if phase not in ("focus", "rest"):
            return
        self.phase = phase
        self.demo_mode = bool(snapshot.get("demo_mode", False))
        self.session_cumulative_growth = bool(snapshot.get(
            "session_cumulative_growth",
            self.cumulative_growth_check.isChecked(),
        ))
        completed, _, _ = self.state.growth_state()
        target = self.state.growth_target()
        fallback_rounds = (
            target
            if self.is_cumulative_growth() and 0 < completed < target
            else (1 if self.demo_mode else self.rounds_spin.value())
        )
        self.session_focus_seconds = max(
            1,
            int(snapshot.get(
                "session_focus_seconds",
                30 if self.demo_mode else self.focus_spin.value() * 60,
            )),
        )
        self.session_rest_seconds = max(
            1,
            int(snapshot.get(
                "session_rest_seconds",
                8 if self.demo_mode else self.rest_spin.value() * 60,
            )),
        )
        self.session_total_rounds = max(
            1, int(snapshot.get("session_total_rounds", fallback_rounds))
        )
        self.current_round = max(
            1,
            min(int(snapshot.get("current_round", 1)), self.get_total_rounds()),
        )
        self.elapsed_before_pause = max(0.0, float(snapshot.get("elapsed", 0.0)))
        self.awaiting_output = bool(snapshot.get("awaiting_output", False))
        self.last_focus_effective = bool(snapshot.get("last_focus_effective", True))
        task = snapshot.get("task", {})
        if isinstance(task, dict):
            scene = task.get("scene")
            if scene in SCENE_TASKS:
                self.scene_combo.setCurrentText(scene)
            task_type = task.get("task_type")
            if task_type:
                self.task_combo.setCurrentText(str(task_type))
            self.custom_task_edit.setText(str(task.get("custom_name", "")))
            self.goal_edit.setText(str(task.get("goal", "")))
        self.running = False
        self.start_time = None
        self.finished = False
        self.last_safe_elapsed = self.elapsed_before_pause
        self.last_tick_monotonic = time.monotonic()
        if self.awaiting_output:
            self.status_label.setText("上次专注已完成，等待记录本轮产出")
        else:
            self.status_label.setText("已恢复上次会话，并为你暂停")
        self.overlay.set_rest_mode(self.phase == "rest")
        phase_total = max(1, self.get_phase_total_seconds())
        progress = min(1.0, self.elapsed_before_pause / phase_total)
        self.overlay.set_progress(
            self.visual_progress_for_focus(progress) if self.phase == "focus" else self.rest_visual_progress
        )
        self.sync_botanical_previews()
        self.refresh_labels()

    def demo(self):
        self.running = False
        self.timer.stop()
        self.clear_session_plan()
        self.demo_mode = True
        self.phase = "focus"
        self.current_round = 1
        self.elapsed_before_pause = 0.0
        self.start_time = None
        self.finished = False
        self.last_focus_effective = True
        self.rest_visual_progress = 1.0
        self.overlay.set_rest_mode(False)
        self.overlay.set_progress(0.0)
        if not self.goal_edit.text().strip():
            self.goal_edit.setText("演示：完成一次专注并记录产出")
        self.status_label.setText("演示模式：30秒专注生长 + 成长看板数据更新")
        self.start()

    def capture_output_after_focus(self) -> bool | None:
        scene_mode = self.scene_combo.currentText()
        raw_task_type = self.task_combo.currentText()
        custom_task_name = self.custom_task_edit.text().strip()
        task_type = self.get_display_task_type()
        goal = self.goal_edit.text().strip()
        if self.pending_output_dialog is None:
            self.pending_output_dialog = OutputDialog(scene_mode, task_type, goal, self)
            self.pending_output_dialog.setStyleSheet(
                build_app_qss(self.ui_theme_combo.currentText(), self.glass_effect_check.isChecked())
            )
        dialog = self.pending_output_dialog
        dialog.exec()
        result = dialog.get_result_data()
        if not result:
            return None
        effective = bool(result.get("effective", False))
        record = {
            "date": str(date.today()),
            "time": datetime.now().strftime("%H:%M:%S"),
            "scene_mode": scene_mode,
            "task_type": task_type,
            "raw_task_type": raw_task_type,
            "custom_task_name": custom_task_name,
            "goal": goal,
            "effective": effective,
            "output": result.get("output", ""),
            "notes": result.get("notes", ""),
            "next_step": result.get("next_step", ""),
            "metric_name": result.get("metric_name", "成果数据"),
            "metric_unit": result.get("metric_unit", ""),
            "metric_value": int(result.get("metric_value", 0)),
            "focus_minutes": self.focus_spin.value() if not self.demo_mode else 0,
            "growth_mode": "累计生长" if self.is_cumulative_growth() else "单轮生长",
        }
        try:
            self.state.add_focus_record(record)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "记录保存失败",
                f"输入内容仍然保留，请检查记录目录后重试。\n\n{exc}",
            )
            dialog.result_data = None
            return None
        self.pending_output_dialog = None
        chapter_size = self.get_total_rounds() if self.is_cumulative_growth() else 1
        completed_units, _, chapter = self.state.commit_growth(effective, chapter_size)
        self.overlay.set_growth_chapter(chapter)
        self.state.add_completed_focus()
        self.refresh_today_label()
        if self.is_cumulative_growth():
            target = self.state.growth_target()
            self.overlay.set_progress(min(1.0, completed_units / max(1, target)))
            # 每一轮诚实完成都会让桌面藤蔓进入下一花期；“目标有推进”
            # 仅增加庆祝与复盘标记。花期不会增建花位或改变浓密度。
            self.overlay.set_bloom_progress(
                self.state.bloom_progress(completed_units, target),
                animate=True,
            )
        else:
            self.overlay.set_progress(1.0)
            self.overlay.set_bloom_progress(1.0, animate=True)
        self.sync_botanical_previews()
        if effective:
            self.overlay.celebrate()
        return effective

    def finish_focus_record(self, effective: bool):
        """记录成功后进入已准备的休息状态，不自动开始倒计时。"""
        self.awaiting_output = False
        self.last_focus_effective = effective
        self.rest_visual_progress = self.visual_progress_for_round_end(effective)
        if effective:
            self.toast.show_message("已记录本轮进展，花藤正在向下一阶段生长")
            self.status_label.setText("专注完成：本轮进展已保存，准备开始休息")
        else:
            self.toast.show_message("这一轮专注已保留，枝叶会继续生长")
            self.status_label.setText("专注完成：本轮记录已保存，准备开始休息")
        self.phase = "rest"
        self.elapsed_before_pause = 0.0
        self.start_time = None
        self.running = False
        self.overlay.set_rest_mode(True)
        if self.current_round >= self.get_total_rounds() and self.skip_final_rest_check.isChecked():
            self.finish_all_rounds()
            return
        self.refresh_labels()
        self.save_session_snapshot()

    def complete_phase(self):
        if self.sound_check.isChecked():
            QApplication.beep()
        self.running = False
        self.timer.stop()

        if self.phase == "focus":
            self.awaiting_output = True
            self.overlay.set_progress(self.visual_progress_for_focus(1.0))
            self.status_label.setText("本轮专注完成：记录产出后进入休息")
            self.notify_completion("专注完成", "记录本轮进展后进入休息；每轮专注都会推动植物生长。")
            effective = self.capture_output_after_focus()
            if effective is None:
                self.refresh_labels()
                self.save_session_snapshot()
            else:
                self.finish_focus_record(effective)
            return

        if self.current_round < self.get_total_rounds():
            self.current_round += 1
            self.phase = "focus"
            self.elapsed_before_pause = 0.0
            self.start_time = None
            self.running = False
            self.overlay.set_rest_mode(False)
            self.status_label.setText("休息结束：下一轮已经准备好")
            self.toast.show_message("休息结束，准备好后再开始下一轮")
            self.notify_completion("休息结束", "下一轮已经准备好，不会自动开始。")
            self.refresh_labels()
            self.save_session_snapshot()
            return

        self.finish_all_rounds()

    def update_timer(self):
        now = time.monotonic()
        if self.running and now - self.last_tick_monotonic > 8.0:
            # 系统睡眠/锁屏后不把离线时长算入专注，回到最近一次安全 tick。
            self.elapsed_before_pause = self.last_safe_elapsed
            self.start_time = None
            self.running = False
            self.timer.stop()
            self.status_label.setText("已从休眠或长时间中断恢复，本轮已为你暂停")
            self.refresh_labels()
            self.save_session_snapshot()
            return
        self.last_tick_monotonic = now
        elapsed = self.get_elapsed()
        self.last_safe_elapsed = elapsed
        phase_total = max(1, self.get_phase_total_seconds())
        progress = min(1.0, elapsed / phase_total)
        if self.phase == "focus":
            self.overlay.set_rest_mode(False)
            self.overlay.set_progress(self.visual_progress_for_focus(progress))
        else:
            self.overlay.set_progress(self.rest_visual_progress)
            self.overlay.set_rest_mode(True)
            self.overlay.set_rest_wave(time.monotonic())
        self.sync_botanical_previews()
        self.refresh_labels()
        if progress >= 1.0:
            self.complete_phase()

    def refresh_labels(self):
        elapsed = self.get_elapsed()
        phase_total = max(1, self.get_phase_total_seconds())
        remaining = max(0, int(math.ceil(phase_total - elapsed)))
        self.time_label.setText(f"{remaining // 60:02d}:{remaining % 60:02d}")
        phase_text = "专注中" if self.phase == "focus" else "休息中"
        if not self.running and not self.finished:
            phase_text = "专注" if self.phase == "focus" else "休息"
        if self.awaiting_output:
            phase_text = "待记录"
        if self.finished:
            phase_text = "已完成"
        self.phase_label.setText(phase_text)
        if self.finished or self.awaiting_output:
            phase_state = "done"
        elif self.phase == "rest":
            phase_state = "rest"
        elif self.running:
            phase_state = "focus"
        elif self.elapsed_before_pause > 0:
            phase_state = "paused"
        else:
            phase_state = "ready"
        if self.phase_label.property("phaseState") != phase_state:
            self.phase_label.setProperty("phaseState", phase_state)
            self.phase_label.style().unpolish(self.phase_label)
            self.phase_label.style().polish(self.phase_label)
        self.round_label.setText(f"第 {self.current_round} / {self.get_total_rounds()} 轮")
        if self.awaiting_output:
            self.start_btn.setText("记录产出")
        elif self.running:
            self.start_btn.setText("专注中" if self.phase == "focus" else "休息中")
        elif self.finished:
            self.start_btn.setText("开始专注")
        elif self.elapsed_before_pause > 0:
            self.start_btn.setText("继续")
        else:
            self.start_btn.setText("开始专注")
        self.pause_btn.setEnabled(self.running)
        self.reset_btn.setText("跳过休息" if self.phase == "rest" and not self.finished else "重置")
        if self.mini_button:
            self.mini_button.update_state(self.time_label.text(), self.running, self.awaiting_output)
        self.sync_botanical_previews()

    def show_dashboard(self):
        if self.dashboard_dialog is None:
            self.dashboard_dialog = DashboardDialog(self.state, self.overlay.progress, self)
        dialog = self.dashboard_dialog
        dialog.current_progress = self.overlay.progress
        dialog.rebuild_dashboard()
        dialog.setStyleSheet(
            build_app_qss(self.ui_theme_combo.currentText(), self.glass_effect_check.isChecked())
        )
        dialog.exec()
        self.refresh_today_label()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
        event.accept()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "display_combo") and self.display_combo.currentData() == "follow":
            QTimer.singleShot(0, self.sync_overlay_geometry)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_visual_accents)

    def closeEvent(self, event):
        """系统关闭按钮等路径统一转为隐藏到托盘。"""
        if self._quitting:
            event.accept()
            return
        self.hide_panel_only()
        event.ignore()


# =========================
# 托盘
# =========================
