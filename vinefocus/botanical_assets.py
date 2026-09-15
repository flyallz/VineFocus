"""高清植物资产与分层生长合成。

集中负责定位内置 PNG、变换 52 个透明植物器官、兼容旧版枝叶底图，以及
给主面板/设置/看板提供统一的植物预览。计时与记录逻辑不依赖本模块。
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget


THEME_ASSETS = {
    "月白花藤": "moon_base.png",
    "樱雾花枝": "cherry_base.png",
    "流苏紫藤": "wisteria_base.png",
    "极光荧藤": "aurora_base.png",
}

# 52 个正式透明器官直接从冻结设计稿逐件提取，不重新配色或生成。
ORGAN_THEME_DIRS = {
    "月白花藤": "moon",
    "樱雾花枝": "cherry",
    "流苏紫藤": "wisteria",
    "极光荧藤": "aurora",
}

ORGAN_NAMES = (
    "stem_short", "stem_curve", "stem_fork",
    "leaf_tiny", "leaf_small", "leaf_medium", "leaf_mature",
    "tendril", "bud_closed", "bud_swollen", "bloom_half", "bloom_open", "petal",
)

# 每张器官图的连接点并不都在“底部正中央”。这里用归一化坐标记录真实
# 根部，并记录从根部指向主体的局部轴角度。合成时会把该轴精确旋转到
# 生长方向，避免叶柄、花梗和紫藤花序看似悬空。
ORGAN_TRANSFORMS = {
    "stem_short": (0.18, 0.94, -58.0),
    "stem_curve": (0.14, 0.94, -52.0),
    "stem_fork": (0.18, 0.94, -66.0),
    "leaf_tiny": (0.15, 0.93, -48.0),
    "leaf_small": (0.15, 0.94, -48.0),
    "leaf_medium": (0.14, 0.94, -47.0),
    "leaf_mature": (0.13, 0.95, -46.0),
    "tendril": (0.10, 0.95, -55.0),
    "bud_closed": (0.30, 0.94, -82.0),
    "bud_swollen": (0.31, 0.94, -82.0),
    "bloom_half": (0.33, 0.94, -82.0),
    "bloom_open": (0.34, 0.94, -82.0),
    "petal": (0.50, 0.94, -82.0),
}

# 紫藤的复叶和花序是从画面上端向下悬垂，根部语义与另外三株相反。
WISTERIA_TRANSFORMS = {
    "leaf_tiny": (0.92, 0.13, 132.0),
    "leaf_small": (0.87, 0.08, 124.0),
    "leaf_medium": (0.86, 0.06, 120.0),
    "leaf_mature": (0.57, 0.04, 94.0),
    "bud_closed": (0.50, 0.04, 90.0),
    "bud_swollen": (0.50, 0.04, 90.0),
    "bloom_half": (0.50, 0.04, 90.0),
    "bloom_open": (0.50, 0.04, 90.0),
}

# 极光荧藤使用心形下垂叶。叶柄位于叶片顶部凹口，而不是普通叶片的左下方；
# 独立锚点能让叶柄真正落在枝条上，并让叶尖顺着重力自然朝下。
AURORA_TRANSFORMS = {
    "leaf_tiny": (0.50, 0.08, 90.0),
    "leaf_small": (0.50, 0.07, 90.0),
    "leaf_medium": (0.50, 0.055, 90.0),
    "leaf_mature": (0.50, 0.05, 90.0),
}

FLOWER_QUADRANTS = {
    "月白花藤": (0, 0),
    "樱雾花枝": (1, 0),
    "流苏紫藤": (0, 1),
    "极光荧藤": (1, 1),
}

# 资源中的真实植物边界。生成图保留了大量透明安全区；桌面合成必须裁掉这些
# 留白后再定位，否则即使目标矩形贴边，肉眼看到的枝叶仍会离屏幕几十像素。
CONTENT_RECTS = {
    "月白花藤": (0, 278, 630, 976),
    "樱雾花枝": (0, 72, 682, 1182),
    "流苏紫藤": (34, 0, 838, 1210),
    "极光荧藤": (430, 247, 824, 1007),
}


def project_root() -> Path:
    """兼容源码运行与 PyInstaller 临时解包目录。"""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path:
    return project_root() / "assets" / "botanical" / name


@dataclass(frozen=True)
class PlantPlacement:
    rect: QRectF
    mirror_x: bool = False
    mirror_y: bool = False
    grow_from_top: bool = False
    opacity: float = 1.0


class BotanicalAssets:
    """进程内共享 QPixmap 缓存与桌面合成器。"""

    _cache: dict[str, QPixmap] = {}

    @classmethod
    def pixmap(cls, name: str) -> QPixmap:
        if name not in cls._cache:
            cls._cache[name] = QPixmap(str(asset_path(name)))
        return cls._cache[name]

    @classmethod
    def base(cls, theme_name: str) -> QPixmap:
        return cls.pixmap(THEME_ASSETS.get(theme_name, "moon_base.png"))

    @classmethod
    def flower_atlas(cls) -> QPixmap:
        return cls.pixmap("flower_atlas.png")

    @classmethod
    def organ_pixmap(cls, theme_name: str, organ_name: str) -> QPixmap:
        """返回从冻结设计稿逐件提取的透明植物器官。"""
        theme_dir = ORGAN_THEME_DIRS.get(theme_name, "moon")
        normalized = organ_name if organ_name in ORGAN_NAMES else "leaf_tiny"
        return cls.pixmap(f"organs/{theme_dir}/{normalized}.png")

    @classmethod
    def has_organ_atlas(cls, theme_name: str) -> bool:
        required = ("stem_curve", "leaf_tiny", "leaf_mature", "bud_closed", "bloom_open")
        return all(
            not (pixmap := cls.organ_pixmap(theme_name, name)).isNull() and pixmap.hasAlphaChannel()
            for name in required
        )

    @classmethod
    def draw_organ(
        cls,
        painter: QPainter,
        theme_name: str,
        organ_name: str,
        anchor: QPointF,
        direction: float,
        height: float,
        opacity: float = 1.0,
        mirror: bool = False,
    ) -> bool:
        """以器官真实根部为锚点绘制，朝 direction 生长；返回资源是否可用。"""
        pixmap = cls.organ_pixmap(theme_name, organ_name)
        if pixmap.isNull() or height <= 0.5 or opacity <= 0.0:
            return False
        source = QRectF(pixmap.rect())
        aspect = source.width() / max(1.0, source.height())
        width = height * aspect
        anchor_x, anchor_y, local_axis = ORGAN_TRANSFORMS.get(
            organ_name, (0.50, 0.95, -90.0)
        )
        if theme_name == "流苏紫藤":
            anchor_x, anchor_y, local_axis = WISTERIA_TRANSFORMS.get(
                organ_name, (anchor_x, anchor_y, local_axis)
            )
        elif theme_name == "极光荧藤":
            anchor_x, anchor_y, local_axis = AURORA_TRANSFORMS.get(
                organ_name, (anchor_x, anchor_y, local_axis)
            )
        if mirror:
            local_axis = 180.0 - local_axis
        painter.save()
        painter.setOpacity(painter.opacity() * max(0.0, min(1.0, opacity)))
        painter.translate(anchor)
        painter.rotate(direction - local_axis)
        if mirror:
            painter.scale(-1.0, 1.0)
        target = QRectF(-anchor_x * width, -anchor_y * height, width, height)
        painter.drawPixmap(target, pixmap, source)
        painter.restore()
        return True

    @staticmethod
    def content_rect(theme_name: str) -> QRectF:
        return QRectF(*CONTENT_RECTS.get(theme_name, CONTENT_RECTS["月白花藤"]))

    @staticmethod
    def placements(theme_name: str, layout_name: str, bounds: QRectF, presence: float) -> list[PlantPlacement]:
        w, h = bounds.width(), bounds.height()
        amount = max(0.20, min(0.70, presence))
        content = BotanicalAssets.content_rect(theme_name)
        aspect = content.width() / max(1.0, content.height())
        if layout_name == "侧边攀援":
            height = min(h * (0.76 + amount * 0.26), h * 0.96)
        elif layout_name == "环屏生长":
            height = min(h * (0.35 + amount * 0.15), h * 0.48)
        else:
            height = min(h * (0.31 + amount * 0.24), h * 0.52)
        width = min(height * aspect, w * 0.48)
        bleed = max(5.0, min(16.0, h * 0.012))

        def corner_rect(anchor: str, scale: float = 1.0) -> QRectF:
            """以真实植物边界为基准贴角，并让叶尖轻微越出屏幕。"""
            plant_height = height * scale
            plant_width = min(plant_height * aspect, w * 0.48)
            x = bounds.left() - bleed if anchor.startswith("left") else bounds.right() - plant_width + bleed
            y = bounds.top() - bleed if anchor.endswith("top") else bounds.bottom() - plant_height + bleed
            return QRectF(x, y, plant_width, plant_height)

        left_bottom = corner_rect("left_bottom")
        left_top = corner_rect("left_top")
        right_bottom = corner_rect("right_bottom")
        right_top = corner_rect("right_top")

        if layout_name == "静谧单株":
            if theme_name == "流苏紫藤":
                return [PlantPlacement(left_top, grow_from_top=True)]
            if theme_name == "极光荧藤":
                return [PlantPlacement(right_bottom)]
            return [PlantPlacement(left_bottom)]

        if layout_name == "侧边攀援":
            if theme_name == "极光荧藤":
                return [PlantPlacement(right_bottom)]
            if theme_name == "流苏紫藤":
                return [PlantPlacement(left_top, grow_from_top=True)]
            return [PlantPlacement(left_bottom)]

        # 环屏模式遵循概念稿的“不对称平衡”：一处主景、一至两处次景和一处
        # 低透明点缀。四角不再机械复制同一尺寸，桌面因此更像自然攀援。
        if theme_name == "流苏紫藤":
            return [
                PlantPlacement(corner_rect("left_top", 1.08), grow_from_top=True),
                PlantPlacement(corner_rect("right_top", 0.82), mirror_x=True, grow_from_top=True, opacity=0.82),
                PlantPlacement(corner_rect("right_bottom", 0.70), mirror_x=True, mirror_y=True, opacity=0.64),
                PlantPlacement(corner_rect("left_bottom", 0.52), mirror_y=True, opacity=0.42),
            ]
        if theme_name == "樱雾花枝":
            return [
                PlantPlacement(corner_rect("left_bottom", 1.06)),
                PlantPlacement(corner_rect("left_top", 0.78), mirror_y=True, grow_from_top=True, opacity=0.84),
                PlantPlacement(corner_rect("right_top", 0.62), mirror_x=True, mirror_y=True, grow_from_top=True, opacity=0.66),
                PlantPlacement(corner_rect("right_bottom", 0.46), mirror_x=True, opacity=0.42),
            ]
        if theme_name == "极光荧藤":
            return [
                PlantPlacement(corner_rect("right_top", 1.06), mirror_x=True, mirror_y=True, grow_from_top=True),
                PlantPlacement(corner_rect("right_bottom", 0.86), mirror_x=True, opacity=0.86),
                PlantPlacement(corner_rect("left_bottom", 0.70), opacity=0.66),
                PlantPlacement(corner_rect("left_top", 0.54), mirror_y=True, grow_from_top=True, opacity=0.48),
            ]
        return [
            PlantPlacement(corner_rect("left_bottom", 1.02)),
            PlantPlacement(corner_rect("right_top", 0.76), mirror_x=True, mirror_y=True, grow_from_top=True, opacity=0.76),
            PlantPlacement(corner_rect("right_bottom", 0.60), mirror_x=True, opacity=0.56),
            PlantPlacement(corner_rect("left_top", 0.45), mirror_y=True, grow_from_top=True, opacity=0.38),
        ]

    @staticmethod
    def _draw_mirrored(painter: QPainter, pixmap: QPixmap, target: QRectF, source: QRectF, mx: bool, my: bool):
        painter.save()
        painter.translate(target.center())
        painter.scale(-1.0 if mx else 1.0, -1.0 if my else 1.0)
        local = QRectF(-target.width() / 2.0, -target.height() / 2.0, target.width(), target.height())
        painter.drawPixmap(local, pixmap, source)
        painter.restore()

    @classmethod
    def draw_growth_layer(
        cls,
        painter: QPainter,
        theme_name: str,
        layout_name: str,
        bounds: QRectF,
        progress: float,
        presence: float,
    ) -> list[PlantPlacement]:
        pixmap = cls.base(theme_name)
        if pixmap.isNull() or progress <= 0.0:
            return []
        progress = max(0.0, min(1.0, progress))
        placements = cls.placements(theme_name, layout_name, bounds, presence)
        source_full = cls.content_rect(theme_name)
        feather = min(1.0, progress / 0.12)
        painter.save()
        painter.setOpacity(painter.opacity() * (0.22 + 0.78 * feather))
        for index, placement in enumerate(placements):
            local_progress = max(0.0, min(1.0, progress * len(placements) - index))
            if local_progress <= 0.0:
                continue
            if placement.grow_from_top:
                source = QRectF(
                    source_full.left(), source_full.top(),
                    source_full.width(), source_full.height() * local_progress,
                )
                target = QRectF(
                    placement.rect.left(), placement.rect.top(),
                    placement.rect.width(), placement.rect.height() * local_progress,
                )
            else:
                cut = source_full.top() + source_full.height() * (1.0 - local_progress)
                source = QRectF(source_full.left(), cut, source_full.width(), source_full.bottom() - cut)
                target = QRectF(
                    placement.rect.left(), placement.rect.top() + placement.rect.height() * (1.0 - local_progress),
                    placement.rect.width(), placement.rect.height() * local_progress,
                )
            painter.save()
            painter.setOpacity(painter.opacity() * placement.opacity)
            cls._draw_mirrored(painter, pixmap, target, source, placement.mirror_x, placement.mirror_y)
            painter.restore()
        painter.restore()
        return placements

    @classmethod
    def draw_open_flowers(
        cls,
        painter: QPainter,
        theme_name: str,
        placements: list[PlantPlacement],
        count: int,
        pulse: float = 0.0,
        progress: float = 1.0,
    ) -> None:
        atlas = cls.flower_atlas()
        if atlas.isNull() or not placements or count <= 0:
            return
        quadrant_x, quadrant_y = FLOWER_QUADRANTS.get(theme_name, (0, 0))
        half_w, half_h = atlas.width() / 2.0, atlas.height() / 2.0
        source = QRectF(quadrant_x * half_w, quadrant_y * half_h, half_w, half_h)
        anchors = ((0.34, 0.60), (0.43, 0.40), (0.22, 0.76), (0.52, 0.23))
        # 小型预览只有一个 placement，也要能表达初花到盛花，而不是永远只画
        # 一两处；桌面兼容模式仍按构图数量限制上限，避免花朵淹没枝叶。
        capacity = max(4, len(placements) * 2) if theme_name != "流苏紫藤" else max(2, len(placements))
        progress = max(0.0, min(1.0, progress))
        candidates = []
        for placement in placements:
            for anchor_index, (raw_x, raw_y) in enumerate(anchors):
                ax = 1.0 - raw_x if placement.mirror_x else raw_x
                ay = 1.0 - raw_y if placement.mirror_y else raw_y
                visible = ay <= progress + 0.025 if placement.grow_from_top else ay >= 1.0 - progress - 0.025
                if visible:
                    candidates.append((placement, ax, ay, anchor_index))
        max_flowers = min(count, capacity, len(candidates))
        for index in range(max_flowers):
            placement, ax, ay, anchor_index = candidates[index]
            center_x = placement.rect.left() + placement.rect.width() * ax
            center_y = placement.rect.top() + placement.rect.height() * ay
            breathing = 1.0 + 0.025 * math.sin(pulse + anchor_index * 1.7)
            if theme_name == "流苏紫藤":
                width = placement.rect.width() * 0.18 * breathing
                height = width * 1.62
            elif theme_name == "樱雾花枝":
                width = placement.rect.width() * 0.20 * breathing
                height = width
            else:
                width = placement.rect.width() * 0.17 * breathing
                height = width
            target = QRectF(center_x - width / 2.0, center_y - height / 2.0, width, height)

            glow = QRadialGradient(target.center(), max(width, height) * 0.68)
            glow.setColorAt(0.0, QColor(88, 226, 218, 32))
            glow.setColorAt(1.0, QColor(88, 226, 218, 0))
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(target.adjusted(-width * 0.24, -height * 0.24, width * 0.24, height * 0.24))
            painter.setOpacity(painter.opacity() * 0.94 * placement.opacity)
            cls._draw_mirrored(painter, atlas, target, source, placement.mirror_x, placement.mirror_y)
            painter.restore()


class BotanicalPreview(QWidget):
    """主面板、设置卡片和看板共用的小型高清植物预览。"""

    def __init__(self, theme_name: str = "月白花藤", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.progress = 1.0
        self.flower_count = 1
        self.visual_opacity = 0.82
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setMinimumSize(QSize(80, 56))

    def set_visual(self, theme_name: str, progress: float = 1.0, flower_count: int = 1):
        progress = max(0.0, min(1.0, progress))
        flower_count = max(0, flower_count)
        old = (self.theme_name, round(self.progress, 3), self.flower_count)
        new = (theme_name, round(progress, 3), flower_count)
        if old == new:
            return
        self.theme_name = theme_name
        self.progress = progress
        self.flower_count = flower_count
        self.update()

    def set_visual_opacity(self, opacity: float):
        """控制卡片内植物的氛围强度，不修改桌面花藤透明度。"""
        opacity = max(0.12, min(1.0, float(opacity)))
        if abs(self.visual_opacity - opacity) < 0.005:
            return
        self.visual_opacity = opacity
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        pixmap = BotanicalAssets.base(self.theme_name)
        if pixmap.isNull():
            return
        content = BotanicalAssets.content_rect(self.theme_name)
        height = self.height() * 1.02
        width = height * content.width() / max(1.0, content.height())
        x = self.width() - width if self.theme_name == "极光荧藤" else 0.0
        y = 0.0 if self.theme_name == "流苏紫藤" else self.height() - height
        placement = PlantPlacement(QRectF(x, y, width, height), grow_from_top=self.theme_name == "流苏紫藤")
        progress = max(0.0, min(1.0, self.progress))
        if placement.grow_from_top:
            source = QRectF(content.left(), content.top(), content.width(), content.height() * progress)
            target = QRectF(x, y, width, height * progress)
        else:
            cut = content.top() + content.height() * (1.0 - progress)
            source = QRectF(content.left(), cut, content.width(), content.bottom() - cut)
            target = QRectF(x, y + height * (1.0 - progress), width, height * progress)
        painter.setOpacity(self.visual_opacity)
        BotanicalAssets._draw_mirrored(painter, pixmap, target, source, False, False)
        BotanicalAssets.draw_open_flowers(
            painter, self.theme_name, [placement], self.flower_count, pulse=0.0,
            progress=progress,
        )
