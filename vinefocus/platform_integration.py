"""操作系统集成的统一入口。

目前只负责 Windows 用户启动项和 macOS 登录项；业务层只接收成功/失败结果，
不会直接导入 winreg 或写入 LaunchAgents。
"""

from __future__ import annotations

import plistlib
import os
import subprocess
import sys
from pathlib import Path


APP_ID = "com.vinefocus.desktop"


def configure_platform_app() -> None:
    """设置稳定的平台应用标识；能力不可用时保持静默。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def foreground_is_exclusive_fullscreen() -> bool:
    """仅在 Windows 检测覆盖整块屏幕的前台窗口；其他平台安全返回 False。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        window = user32.GetForegroundWindow()
        if not window:
            return False
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        if process_id.value == os.getpid():
            return False

        rect = wintypes.RECT()
        if not user32.GetWindowRect(window, ctypes.byref(rect)):
            return False

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        monitor = user32.MonitorFromWindow(window, 2)
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        tolerance = 2
        return (
            rect.left <= info.rcMonitor.left + tolerance
            and rect.top <= info.rcMonitor.top + tolerance
            and rect.right >= info.rcMonitor.right - tolerance
            and rect.bottom >= info.rcMonitor.bottom - tolerance
        )
    except (AttributeError, OSError, TypeError):
        return False


def _launch_arguments() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    main_file = Path(__file__).resolve().parents[1] / "main.py"
    return [str(Path(sys.executable).resolve()), str(main_file)]


def set_start_with_system(enabled: bool) -> tuple[bool, str]:
    """设置当前用户级开机启动；返回是否成功以及适合展示的简短消息。"""
    try:
        if sys.platform == "win32":
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    command = subprocess.list2cmdline(_launch_arguments())
                    winreg.SetValueEx(key, "VineFocus", 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, "VineFocus")
                    except FileNotFoundError:
                        pass
            return True, "开机启动已开启" if enabled else "开机启动已关闭"

        if sys.platform == "darwin":
            path = Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "Label": APP_ID,
                    "ProgramArguments": _launch_arguments(),
                    "RunAtLoad": True,
                }
                temporary = path.with_suffix(".plist.tmp")
                with temporary.open("wb") as stream:
                    plistlib.dump(payload, stream)
                temporary.replace(path)
            else:
                path.unlink(missing_ok=True)
            return True, "登录时启动已开启" if enabled else "登录时启动已关闭"

        return False, "当前系统暂不支持自动启动设置"
    except (OSError, ValueError) as exc:
        return False, f"无法更新开机启动：{exc}"
