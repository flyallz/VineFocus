"""Windows 系统托盘与 macOS 菜单栏控制。

负责托盘图标、菜单和面板显示状态切换，不保存业务数据。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .panel import PomodoroPanel
from .styles import build_menu_qss

class TrayController:
    def __init__(self, panel: PomodoroPanel):
        self.panel = panel
        self.tray = QSystemTrayIcon(panel)
        self.tray.setIcon(self.create_icon())
        self.tray.setToolTip("花藤专注")
        # 菜单不挂在主面板 QWidget 样式树下；否则浅色系统菜单会继承面板的
        # 浅色文字，形成截图中的“白底白字”。Windows/Linux 使用明确主题，
        # macOS 则保留原生菜单外观。
        self.menu = QMenu()
        self.panel.set_tray_controller(self)

        self.show_panel_action = QAction("显示控制面板", self.menu)
        self.show_panel_action.triggered.connect(self.panel.show_panel)
        self.hide_panel_action = QAction("隐藏到托盘", self.menu)
        self.hide_panel_action.triggered.connect(self.panel.hide_panel_only)
        self.show_mini_action = QAction("显示桌面小圆点", self.menu)
        self.show_mini_action.triggered.connect(self.panel.show_mini)
        self.hide_mini_action = QAction("隐藏桌面小圆点", self.menu)
        self.hide_mini_action.triggered.connect(self.panel.hide_mini)
        for action in (
            self.show_panel_action,
            self.hide_panel_action,
            self.show_mini_action,
            self.hide_mini_action,
        ):
            self.menu.addAction(action)

        self.menu.addSeparator()
        for text, fn in [("开始 / 继续", self.panel.start), ("暂停", self.panel.pause), ("重置", self.panel.reset), ("成长看板", self.panel.show_dashboard)]:
            action = QAction(text)
            action.triggered.connect(fn)
            self.menu.addAction(action)

        self.menu.addSeparator()
        self.always_on_top_action = QAction("始终置顶")
        self.always_on_top_action.setCheckable(True)
        self.always_on_top_action.setChecked(self.panel.always_on_top_check.isChecked())
        self.always_on_top_action.triggered.connect(self.toggle_always_on_top)
        self.menu.addAction(self.always_on_top_action)

        self.menu.addSeparator()
        quit_action = QAction("退出软件")
        quit_action.triggered.connect(self.panel.real_quit)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.menu.aboutToShow.connect(self.update_action_states)
        self.apply_theme(self.panel.ui_theme_combo.currentText())
        self.tray.show()
        self.status_timer = QTimer(self.tray)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.update_status_text)
        self.status_timer.start()

    def apply_theme(self, theme_name: str):
        """让托盘菜单与主面板主题同步，同时保留 macOS 原生菜单。"""
        self.menu.setStyleSheet("" if sys.platform == "darwin" else build_menu_qss(theme_name))

    def create_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(75, 128, 61))
        painter.drawEllipse(8, 8, 48, 48)
        painter.setBrush(QColor(235, 246, 228))
        painter.drawEllipse(20, 18, 14, 24)
        painter.drawEllipse(30, 22, 18, 12)
        painter.setPen(QPen(QColor(235, 246, 228), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(24, 42, 39, 25)
        painter.end()
        icon = QIcon(pixmap)
        if sys.platform == "darwin":
            icon.setIsMask(True)
        return icon

    def toggle_always_on_top(self, checked: bool):
        self.panel.always_on_top_check.setChecked(checked)
        self.panel.option_changed()

    def update_action_states(self):
        panel_visible = self.panel.display_mode == "panel" and self.panel.isVisible()
        mini_visible = bool(self.panel.mini_button and self.panel.mini_button.isVisible())
        self.show_panel_action.setEnabled(not panel_visible)
        self.hide_panel_action.setEnabled(panel_visible)
        self.show_mini_action.setEnabled(not mini_visible)
        self.hide_mini_action.setEnabled(mini_visible)
        self.always_on_top_action.setChecked(self.panel.always_on_top_check.isChecked())
        self.update_status_text()

    def update_status_text(self):
        """让托盘/菜单栏提示与主面板、迷你计时器保持同一时间。"""
        phase = self.panel.phase_label.text()
        self.tray.setToolTip(f"花藤专注 · {phase} · {self.panel.time_label.text()}")

    def show_message(self, title: str, message: str):
        """发送系统提示；平台不支持时主流程仍由应用内提示兜底。"""
        if QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4500)

    def toggle_panel(self):
        """使用显式显示状态切换，避免隐藏窗口被误判为最小化窗口。"""
        if self.panel.display_mode == "panel" and self.panel.isVisible():
            self.panel.hide_to_mini()
        else:
            self.panel.show_panel()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # macOS 点击状态图标优先展示菜单；Windows 单击则切换现有面板。
            if sys.platform != "darwin":
                QTimer.singleShot(0, self.toggle_panel)
