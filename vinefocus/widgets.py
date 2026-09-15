"""轻量通用界面组件。

包含应用内提示、统计卡片和桌面迷你计时器；这些组件只展示状态，
不直接保存设置或专注记录。
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .styles import THEME_TOKENS


class Toast(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(self.label)
        self.resize(360, 84)
        self.apply_theme("夜色流光")

    def apply_theme(self, theme_name: str):
        token = THEME_TOKENS.get(theme_name, THEME_TOKENS["夜色流光"])
        self.label.setStyleSheet(
            f"background:{token['shell']};color:{token['text']};"
            f"border:1px solid {token['border_focus']};border-radius:15px;"
            "padding:14px 20px;font-size:13px;font-weight:650;"
        )

    def show_message(self, text: str, duration_ms: int = 3500):
        self.label.setText(text)
        self.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 72)
        self.show()
        self.raise_()
        QTimer.singleShot(duration_ms, self.hide)


def make_card(title: str, value: str, subtitle: str = "") -> QFrame:
    frame = QFrame()
    frame.setObjectName("statCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("cardTitle")
    value_label = QLabel(value)
    value_label.setObjectName("cardValue")
    value_label.setWordWrap(True)
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("cardSub")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    if subtitle:
        layout.addWidget(subtitle_label)
    layout.addStretch()
    return frame


class WindowControlButton(QPushButton):
    """用相同画布和线宽绘制标题栏按钮，避免字体符号大小、基线不一致。"""

    def __init__(self, kind: str, parent=None):
        super().__init__("", parent)
        self.kind = "close" if kind == "close" else "minimize"
        self.setObjectName("titleButton")
        self.setProperty("controlKind", self.kind)
        self.setFixedSize(34, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("关闭" if self.kind == "close" else "最小化")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self.palette().buttonText().color(), 1.55)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setCosmetic(True)
        painter.setPen(pen)
        center = self.rect().center()
        half = 5.2
        if self.kind == "close":
            painter.drawLine(
                QPointF(center.x() - half, center.y() - half),
                QPointF(center.x() + half, center.y() + half),
            )
            painter.drawLine(
                QPointF(center.x() + half, center.y() - half),
                QPointF(center.x() - half, center.y() + half),
            )
        else:
            painter.drawLine(
                QPointF(center.x() - half, center.y() + 1.5),
                QPointF(center.x() + half, center.y() + 1.5),
            )


class GrowthRing(QWidget):
    """成长看板中的环形生长进度，保持无第三方图表依赖。"""

    def __init__(self, value: int = 0, parent=None):
        super().__init__(parent)
        self.value = max(0, min(100, int(value)))
        self.setFixedSize(126, 126)

    def set_value(self, value: int):
        self.value = max(0, min(100, int(value)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ring = QRectF(13, 13, self.width() - 26, self.height() - 26)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(76, 103, 126, 95), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, 0, 360 * 16)
        gradient = QLinearGradient(ring.topLeft(), ring.bottomRight())
        gradient.setColorAt(0.0, QColor("#58E7D2"))
        gradient.setColorAt(1.0, QColor("#3AB8C4"))
        painter.setPen(QPen(gradient, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, 90 * 16, -int(360 * 16 * self.value / 100.0))
        painter.setPen(QColor("#F3F6FB"))
        font = QFont("Segoe UI", 20, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(0, -8, 0, 0), Qt.AlignmentFlag.AlignCenter, f"{self.value}%")
        painter.setPen(QColor("#91A6B5"))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.drawText(self.rect().adjusted(0, 31, 0, 0), Qt.AlignmentFlag.AlignCenter, "生长进度")


class TrendChart(QWidget):
    """七日/三十日的柱线组合图，复刻设计稿的数据表现。"""

    def __init__(self, values=None, parent=None):
        super().__init__(parent)
        self.values = list(values or [])
        self.setMinimumSize(360, 190)

    def set_values(self, values):
        self.values = list(values)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(38, 18, self.width() - 54, self.height() - 46)
        painter.setPen(QPen(QColor(109, 153, 178, 42), 1))
        for index in range(4):
            y = area.top() + area.height() * index / 3.0
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        if not self.values:
            painter.setPen(QColor("#91A6B5"))
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "完成一次专注后，这里会出现趋势")
            return
        values = self.values[-14:]
        peak = max([value for _, value in values] + [1])
        step = area.width() / max(1, len(values))
        points = []
        for index, (label, value) in enumerate(values):
            x = area.left() + step * (index + 0.5)
            height = area.height() * value / peak
            bar = QRectF(x - min(17.0, step * 0.26), area.bottom() - height, min(34.0, step * 0.52), height)
            gradient = QLinearGradient(bar.topLeft(), bar.bottomLeft())
            gradient.setColorAt(0.0, QColor(88, 231, 210, 188))
            gradient.setColorAt(1.0, QColor(35, 130, 137, 94))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(bar, 5, 5)
            points.append(QPointF(x, area.bottom() - height))
            if len(values) <= 8 or index % 2 == 0:
                painter.setPen(QColor("#91A6B5"))
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(QRectF(x - step / 2, area.bottom() + 5, step, 18), Qt.AlignmentFlag.AlignCenter, str(label))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#A78BFA"), 2))
        for first, second in zip(points, points[1:]):
            painter.drawLine(first, second)
        painter.setBrush(QColor("#B6A4FF"))
        painter.setPen(Qt.PenStyle.NoPen)
        for point in points:
            painter.drawEllipse(point, 3.3, 3.3)


class MiniButton(QWidget):
    """主面板隐藏时出现的单实例迷你计时器。"""

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.drag_pos = None
        self.always_on_top = True
        self.time_text = "25:00"
        self.awaiting_output = False
        self.expanded = False
        self.setWindowTitle("花藤专注 · 迷你计时器")
        self.apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.shell = QFrame()
        self.shell.setObjectName("miniShell")
        row = QHBoxLayout(self.shell)
        row.setContentsMargins(8, 6, 7, 6)
        row.setSpacing(6)
        self.open_btn = QPushButton("❧  25:00")
        self.open_btn.setObjectName("miniOpen")
        self.open_btn.setToolTip("打开花藤专注")
        self.open_btn.clicked.connect(self.show_panel)
        self.action_btn = QPushButton("Ⅱ")
        self.action_btn.setObjectName("miniAction")
        self.action_btn.setToolTip("暂停或继续")
        self.action_btn.clicked.connect(self.toggle_timer)
        row.addWidget(self.open_btn, stretch=1)
        row.addWidget(self.action_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.shell)
        self.width_animation = QPropertyAnimation(self, b"size", self)
        self.width_animation.setDuration(180)
        self.width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.width_animation.valueChanged.connect(lambda *_: self._keep_right_edge())
        self.width_animation.finished.connect(self._keep_right_edge)
        self.action_btn.hide()
        self.open_btn.setText("❧")
        self.resize(52, 52)
        self.apply_theme("夜色流光")
        self.move_to_bottom_right()

    def apply_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def apply_theme(self, theme_name: str):
        token = THEME_TOKENS.get(theme_name, THEME_TOKENS["夜色流光"])
        self.setStyleSheet(f"""
            QFrame#miniShell {{ background:{token['shell']}; border:1px solid {token['border']}; border-radius:20px; }}
            QPushButton {{ color:{token['text']}; background:transparent; border:none; font-weight:750; }}
            QPushButton#miniOpen {{ min-height:36px; text-align:left; font-size:15px; padding:0 8px; }}
            QPushButton#miniAction {{ min-width:36px; max-width:36px; min-height:36px; max-height:36px;
                padding:0; background:{token['accent_soft']}; border:1px solid {token['border']}; border-radius:18px; }}
            QPushButton:hover {{ color:{token['border_focus']}; }}
        """)

    def set_always_on_top(self, enabled: bool):
        was_visible = self.isVisible()
        self.always_on_top = enabled
        self.apply_window_flags()
        if was_visible:
            self.show()

    def update_state(self, time_text: str, running: bool, awaiting_output: bool = False):
        self.time_text = time_text
        self.awaiting_output = awaiting_output
        label = "待记录" if awaiting_output else time_text
        self.open_btn.setText(f"❧  {label}" if self.expanded else "❧")
        self.action_btn.setText("Ⅱ" if running else "▶")
        self.action_btn.setEnabled(not awaiting_output)

    def set_expanded(self, expanded: bool):
        if self.expanded == expanded:
            return
        self.expanded = expanded
        label = "待记录" if self.awaiting_output else self.time_text
        self.open_btn.setText(f"❧  {label}" if expanded else "❧")
        self.action_btn.setVisible(expanded)
        self.width_animation.stop()
        self.width_animation.setStartValue(self.size())
        self.width_animation.setEndValue(QSize(176 if expanded else 52, 52))
        self.width_animation.start()

    def _keep_right_edge(self):
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 24, min(self.y(), area.bottom() - self.height() - 24))

    def enterEvent(self, event):
        self.set_expanded(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(180, lambda: self.set_expanded(False) if not self.underMouse() else None)
        super().leaveEvent(event)

    def toggle_timer(self):
        if self.panel.running:
            self.panel.pause()
        else:
            self.panel.start()

    def move_to_bottom_right(self, screen=None):
        screen = screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 24)

    def show_panel(self):
        self.hide()
        self.panel.show_panel()

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
