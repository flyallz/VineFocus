"""生成版本验收图。

只负责在无界面环境渲染花藤与设置页，便于发布前检查贴边、叶片锚点、
花簇层次和连续密度控件；不参与正式应用运行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vinefocus.config import VINE_THEMES  # noqa: E402
from vinefocus.overlay import VineOverlay  # noqa: E402
from vinefocus.panel import PomodoroPanel  # noqa: E402


PREVIEWS = ROOT / "previews"


def render_overlay(
    theme: str,
    density: int,
    background: str,
    path: Path,
    layout_name: str = "侧边攀援",
    flower_count: int = 5,
) -> None:
    overlay = VineOverlay()
    overlay.resize(1600, 900)
    overlay.set_theme(theme)
    overlay.set_layout(layout_name)
    overlay.set_density(density)
    overlay.set_presentation(44, 62, True)
    overlay.set_progress(1.0)
    overlay.set_open_flower_count(flower_count)
    image = QImage(1600, 900, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))
    painter = QPainter(image)
    overlay.render(painter, QPoint())
    painter.end()
    image.save(str(path))


def render_settings(path: Path) -> None:
    overlay = VineOverlay()
    panel = PomodoroPanel(overlay)
    panel.ui_theme_combo.setCurrentText("夜色流光")
    panel.density_slider.setValue(72)
    dialog = panel.settings_dialog
    dialog.tabs.setCurrentIndex(1)
    dialog.resize(700, 850)
    QApplication.processEvents()
    image = QImage(dialog.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#08111D"))
    painter = QPainter(image)
    dialog.render(painter, QPoint())
    painter.end()
    image.save(str(path))
    dialog.close()
    panel.close()
    overlay.close()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for index, theme in enumerate(VINE_THEMES):
        background = "#F4F6F7" if index % 2 == 0 else "#101820"
        render_overlay(
            theme,
            74,
            background,
            PREVIEWS / f"VineFocus_v17_{index + 1}_{VINE_THEMES[theme]['profile']}_side.png",
        )
    render_overlay(
        "月白花藤",
        82,
        "#F4F6F7",
        PREVIEWS / "VineFocus_v171_perimeter_four_progress_points.png",
        layout_name="环屏生长",
        flower_count=4,
    )
    # 设置页需在 Windows/macOS 真机字体环境截图；offscreen 插件不可靠加载中文字体。
    app.quit()


if __name__ == "__main__":
    main()
