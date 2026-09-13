"""应用单实例守卫。

使用 Qt 本地进程通信保证 Windows 与 macOS 上只存在一个 VineFocus 实例；
第二次启动只向首个实例发送“恢复主面板”消息，不创建第二套窗口或托盘图标。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceGuard(QObject):
    activate_requested = Signal()

    def __init__(self, key: str = "com.vinefocus.desktop.v15"):
        super().__init__()
        self.key = key
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self._clients: list[QLocalSocket] = []

    def acquire_or_notify(self) -> bool:
        """首个实例返回 True；后续实例通知首个实例后返回 False。"""
        probe = QLocalSocket(self)
        probe.connectToServer(self.key)
        if probe.waitForConnected(350):
            probe.write(b"activate\n")
            probe.flush()
            probe.waitForBytesWritten(350)
            probe.disconnectFromServer()
            return False

        # 异常退出可能留下失效端点；确认无法连接后再清理。
        QLocalServer.removeServer(self.key)
        return self.server.listen(self.key)

    def _accept_connections(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            self._clients.append(socket)
            socket.readyRead.connect(lambda current=socket: self._read_message(current))
            socket.disconnected.connect(lambda current=socket: self._discard_client(current))

    def _read_message(self, socket: QLocalSocket):
        if b"activate" in bytes(socket.readAll()):
            self.activate_requested.emit()

    def _discard_client(self, socket: QLocalSocket):
        if socket in self._clients:
            self._clients.remove(socket)
        socket.deleteLater()
