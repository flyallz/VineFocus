"""生成版本验收图。

只负责在无界面环境渲染花藤与设置页，便于发布前检查贴边、叶片锚点、
花簇层次和连续密度控件；不参与正式应用运行。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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
    progress: float = 1.0,
) -> None:
    overlay = VineOverlay()
    overlay.resize(1600, 900)
    overlay.set_theme(theme)
    overlay.set_layout(layout_name)
    overlay.set_density(density)
    overlay.set_presentation(44, 62, True)
    overlay.set_progress(progress)
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


def render_panel(path: Path) -> None:
    """在隔离设置目录中生成紧凑主面板验收图，不改动用户真实配置。"""
    with tempfile.TemporaryDirectory() as folder, patch(
        "vinefocus.state.Path.home", return_value=Path(folder)
    ):
        overlay = VineOverlay()
        overlay.set_progress(4 / 24)
        overlay.set_open_flower_count(4)
        panel = PomodoroPanel(overlay)
        panel.state.data.update({
            "growth_completed_units": 4,
            "growth_effective_units": 4,
        })
        panel.reset(confirm=False)
        panel._fit_panel_to_content()
        QApplication.processEvents()
        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("#E8EDF1"))
        painter = QPainter(image)
        panel.render(painter, QPoint())
        painter.end()
        image.save(str(path))
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
        "樱雾花枝",
        82,
        "#F4F6F7",
        PREVIEWS / "VineFocus_v173_perimeter_four_rounds.png",
        layout_name="环屏生长",
        flower_count=4,
        progress=4 / 24,
    )
    render_overlay(
        "极光荧藤",
        74,
        "#F4F6F7",
        PREVIEWS / "VineFocus_v173_aurora_perimeter.png",
        layout_name="环屏生长",
        flower_count=12,
        progress=12 / 24,
    )
    render_panel(PREVIEWS / "VineFocus_v173_glass_panel.png")
    # 设置页需在 Windows/macOS 真机字体环境截图；offscreen 插件不可靠加载中文字体。
    app.quit()


if __name__ == "__main__":
    main()
