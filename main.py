"""VineFocus 桌面应用入口。

只负责创建 QApplication、花藤覆盖层、主面板与托盘控制器。
"""

import sys

from PySide6.QtWidgets import QApplication

from vinefocus.overlay import VineOverlay
from vinefocus.panel import PomodoroPanel
from vinefocus.platform_integration import configure_platform_app
from vinefocus.single_instance import SingleInstanceGuard
from vinefocus.tray import TrayController


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VineFocus")
    app.setOrganizationName("VineFocus")
    app.setApplicationVersion("1.7.2")
    app.setQuitOnLastWindowClosed(False)
    configure_platform_app()

    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire_or_notify():
        return 0

    overlay = VineOverlay()
    # 普通透明工具窗口不会在 macOS 创建独立的全屏 Space。
    overlay.show()

    panel = PomodoroPanel(overlay)
    panel.show()

    tray = TrayController(panel)
    instance_guard.activate_requested.connect(panel.show_panel)
    app._vinefocus_objects = (instance_guard, overlay, panel, tray)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
