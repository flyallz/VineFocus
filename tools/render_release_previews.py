"""生成 v1.7.4 版本验收图。

只负责在无界面环境渲染花藤与主面板，便于发布前检查逐轮花期、环屏节奏、
密度正交、器官间距和标题按钮；不参与正式应用运行。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vinefocus.config import VINE_THEMES  # noqa: E402
from vinefocus.overlay import VineOverlay  # noqa: E402
from vinefocus.panel import PomodoroPanel  # noqa: E402


PREVIEWS = ROOT / "previews"


def overlay_image(
    theme: str,
    density: int,
    background: str,
    layout_name: str = "侧边攀援",
    progress: float = 1.0,
    bloom_progress: float = 1.0,
    perimeter_mode: str = "四边同步",
    size: tuple[int, int] = (1600, 900),
) -> QImage:
    overlay = VineOverlay()
    overlay.resize(*size)
    overlay.set_theme(theme)
    overlay.set_layout(layout_name)
    overlay.set_perimeter_growth_mode(perimeter_mode)
    overlay.set_density(density)
    overlay.set_presentation(44, 62, True)
    overlay.set_progress(progress)
    overlay.set_bloom_progress(bloom_progress)
    image = QImage(*size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))
    painter = QPainter(image)
    overlay.render(painter, QPoint())
    painter.end()
    overlay.close()
    return image


def render_overlay(
    theme: str,
    density: int,
    background: str,
    path: Path,
    layout_name: str = "侧边攀援",
    progress: float = 1.0,
    bloom_progress: float = 1.0,
    perimeter_mode: str = "四边同步",
) -> None:
    image = overlay_image(
        theme, density, background, layout_name, progress, bloom_progress, perimeter_mode
    )
    image.save(str(path))


def render_contact_sheet(
    panels: list[tuple[str, QImage]],
    columns: int,
    path: Path,
) -> None:
    """用小标题组合对照图，便于一眼检查阶段之间是否真的变化。"""
    cell_width, cell_height, label_height = 800, 450, 42
    rows = (len(panels) + columns - 1) // columns
    sheet = QImage(
        cell_width * columns,
        (cell_height + label_height) * rows,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    sheet.fill(QColor("#071321"))
    painter = QPainter(sheet)
    painter.setFont(QFont("Microsoft YaHei UI", 14, QFont.Weight.DemiBold))
    for index, (label, panel) in enumerate(panels):
        column, row = index % columns, index // columns
        x = column * cell_width
        y = row * (cell_height + label_height)
        painter.drawImage(QRect(x, y, cell_width, cell_height), panel)
        painter.setPen(QColor("#DCEAF2"))
        painter.drawText(
            QRect(x + 18, y + cell_height, cell_width - 36, label_height),
            0x0081,
            label,
        )
    painter.end()
    sheet.save(str(path))


def render_settings(path: Path) -> None:
    with tempfile.TemporaryDirectory() as folder, patch(
        "vinefocus.state.Path.home", return_value=Path(folder)
    ):
        overlay = VineOverlay()
        panel = PomodoroPanel(overlay)
        panel.ui_theme_combo.setCurrentText("夜色流光")
        panel.growth_layout_combo.setCurrentText("环屏生长")
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
        panel = PomodoroPanel(overlay)
        panel.state.data.update({
            "growth_completed_units": 2,
            "growth_effective_units": 1,
            "growth_target_units": 4,
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
            PREVIEWS / f"VineFocus_v174_{index + 1}_{VINE_THEMES[theme]['profile']}_side.png",
        )

    four_round_panels = []
    for round_index in range(1, 5):
        progress = round_index / 4
        bloom = 1.0 if round_index == 4 else progress ** 1.15
        four_round_panels.append((
            f"第 {round_index}/4 轮 · 花期 {round(bloom * 100)}%",
            overlay_image(
                "樱雾花枝", 72, "#F4F6F7", "环屏生长", progress, bloom,
                size=(800, 450),
            ),
        ))
    render_contact_sheet(
        four_round_panels, 2, PREVIEWS / "VineFocus_v174_four_round_bloom.png"
    )

    density_panels = []
    for density, label in ((18, "清爽"), (50, "标准"), (88, "茂盛")):
        density_panels.append((
            f"{label} · {density}%（相同 3/4 花期）",
            overlay_image(
                "极光荧藤", density, "#F4F6F7", "环屏生长", 0.75,
                0.75 ** 1.15, size=(800, 450),
            ),
        ))
    render_contact_sheet(
        density_panels, 3, PREVIEWS / "VineFocus_v174_density_comparison.png"
    )

    timing_panels = []
    for mode in ("四边同步", "等时接力", "自然接力"):
        timing_panels.append((
            f"{mode} · 相同 42% 时间",
            overlay_image(
                "流苏紫藤", 62, "#101820", "环屏生长", 0.42,
                0.42 ** 1.15, mode, size=(800, 450),
            ),
        ))
    render_contact_sheet(
        timing_panels, 3, PREVIEWS / "VineFocus_v174_perimeter_timing.png"
    )

    full_theme_panels = []
    for theme in VINE_THEMES:
        full_theme_panels.append((
            f"{theme} · 茂盛终态",
            overlay_image(
                theme, 88, "#F4F6F7", "环屏生长", 1.0, 1.0,
                size=(800, 450),
            ),
        ))
    render_contact_sheet(
        full_theme_panels, 2, PREVIEWS / "VineFocus_v174_all_themes_full.png"
    )
    render_panel(PREVIEWS / "VineFocus_v174_glass_panel.png")
    render_settings(PREVIEWS / "VineFocus_v174_settings.png")
    # offscreen 插件不可靠加载中文字体；此图只验收结构，字形仍需真机确认。
    app.quit()


if __name__ == "__main__":
    main()
