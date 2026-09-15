"""桌面花藤视觉引擎。

把 visual_profiles.py 的主题构图渲染为可生长的 QPainter 图层，负责主藤、侧枝、
叶片、花苞、花朵、紫藤花序、落瓣和微光；不处理计时、记录、看板或托盘业务。
"""

from __future__ import annotations

import bisect
import math
import random
import time
from dataclasses import dataclass
from typing import List, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .botanical_assets import BotanicalAssets
from .config import PERIMETER_GROWTH_MODES, VINE_THEMES, normalize_theme_name
from .models import VineNode
from .visual_profiles import PROFILE_METRICS, composition_paths


@dataclass
class VineGesture:
    """一段彼此断开的攀附路径及其等距采样数据。"""

    points: List[QPointF]
    distances: List[float]
    length: float
    offset: float
    material: str


class VineOverlay(QWidget):
    """覆盖桌面边缘、鼠标可穿透的程序化植物层。"""

    def __init__(self):
        super().__init__()
        self.progress = 0.0
        self.rest_mode = False
        self.rest_wave = 0.0
        self.always_on_top = True
        self.edge_margin = 22
        self.density_name = "标准"
        self.density_value = 50
        self.density_factor = 0.92
        self.theme_name = "月白花藤"
        self.theme = VINE_THEMES[self.theme_name]
        self.profile = self.theme["profile"]
        self.layout_name = "静谧单株"
        self.perimeter_growth_mode = "四边同步"
        self.plant_presence = 0.36
        self.plant_opacity = 0.40
        self.reduced_motion = False
        self.open_flower_count = 0
        # None 表示兼容旧版的整数花位接口；0～1 表示桌面藤蔓独立花期。
        # 花期只揭示当前密度已经生成的花位，绝不反向改变枝叶密度。
        self.bloom_progress: float | None = None
        self.growth_chapter = 1
        self.completion_glow = 0.0
        self._celebration_started = 0.0
        self._bloom_transition_started = 0.0
        self._bloom_transition_from_count = 0
        self._bloom_transition_from_progress = 0.0
        self._bloom_transition_to_progress = 0.0
        self._celebration_timer = QTimer(self)
        self._celebration_timer.setInterval(33)
        self._celebration_timer.timeout.connect(self._advance_celebration)
        self._rest_animation_timer = QTimer(self)
        self._rest_animation_timer.setInterval(80)
        self._rest_animation_timer.timeout.connect(self._advance_rest_animation)
        self._bloom_animation_timer = QTimer(self)
        self._bloom_animation_timer.setInterval(33)
        self._bloom_animation_timer.timeout.connect(self._advance_bloom_animation)

        self.gestures: List[VineGesture] = []
        self.path_points: List[QPointF] = []
        self.path_distances: List[float] = []
        self.total_length = 1.0
        self.vine_chunks = []  # 保留旧版属性，第三方调用不会因升级报错。
        self.leaf_nodes: List[VineNode] = []
        self.bud_nodes: List[VineNode] = []
        self.flower_nodes: List[VineNode] = []
        self.branch_nodes: List[VineNode] = []
        self.tendril_nodes: List[VineNode] = []

        self.setWindowTitle("花藤专注覆盖层")
        self.apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        self.rebuild_path()

    def apply_window_flags(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_always_on_top(self, enabled: bool):
        was_visible = self.isVisible()
        geometry = self.geometry()
        self.always_on_top = enabled
        self.apply_window_flags()
        self.setGeometry(geometry)
        if was_visible:
            self.show()

    def set_progress(self, value: float):
        self.progress = self.clamp(value)
        # 主计时器运行期间复用当前时间，提供极轻的呼吸与风动，不增加全屏动画定时器。
        self.rest_wave = time.monotonic()
        self.update()

    def set_rest_mode(self, enabled: bool):
        enabled = bool(enabled)
        if self.rest_mode == enabled:
            return
        self.rest_mode = enabled
        if enabled and not self.reduced_motion:
            self._rest_animation_timer.start()
        else:
            self._rest_animation_timer.stop()
        self.update()

    def _advance_rest_animation(self):
        """休息暂停或计时时都保持低频呼吸，不依赖主计时器是否运行。"""
        if not self.rest_mode or self.reduced_motion:
            self._rest_animation_timer.stop()
            return
        self.rest_wave = time.monotonic()
        self.update()

    def set_rest_wave(self, value: float):
        self.rest_wave = value
        if self.rest_mode:
            self.update()

    def set_density(self, value: int | str):
        """连续控制器官数量；兼容旧版“清爽/标准/茂盛”字符串设置。"""
        if isinstance(value, str):
            value = {"清爽": 20, "标准": 50, "茂盛": 85}.get(value, 50)
        self.density_value = max(0, min(100, int(value)))
        self.density_name = (
            "清爽" if self.density_value < 34
            else "茂盛" if self.density_value >= 70
            else "标准"
        )
        if self.density_value <= 50:
            self.density_factor = 0.48 + 0.44 * (self.density_value / 50.0)
        else:
            self.density_factor = 0.92 + 0.78 * ((self.density_value - 50) / 50.0)
        self.rebuild_path()
        self.update()

    def set_layout(self, name: str):
        """切换静谧单株、侧边攀援或环屏生长，并保持当前进度。"""
        normalized = name if name in ("静谧单株", "侧边攀援", "环屏生长") else "静谧单株"
        if normalized == self.layout_name:
            return
        self.layout_name = normalized
        self.rebuild_path()
        self.update()

    def set_perimeter_growth_mode(self, mode: str):
        """选择四边同步、等时接力或按路径长度分配时间的自然接力。"""
        normalized = mode if mode in PERIMETER_GROWTH_MODES else "四边同步"
        if normalized == self.perimeter_growth_mode:
            return
        self.perimeter_growth_mode = normalized
        self.rebuild_path()
        self.update()

    def set_presentation(self, presence: int, opacity: int, reduced_motion: bool = False):
        self.plant_presence = self.clamp(float(presence) / 100.0)
        self.plant_opacity = self.clamp(float(opacity) / 100.0, 0.12, 0.72)
        self.reduced_motion = bool(reduced_motion)
        if self.rest_mode and not self.reduced_motion:
            self._rest_animation_timer.start()
        else:
            self._rest_animation_timer.stop()
        self.update()

    def set_open_flower_count(self, count: int, *, animate: bool = False):
        """提交已获得的花簇数；新花簇可从花苞平滑展开，而非瞬间跳出。"""
        count = max(0, int(count))
        previous = self.open_flower_count
        self.bloom_progress = None
        self.open_flower_count = count
        if animate and count > previous:
            self._bloom_transition_from_count = previous
            self._bloom_transition_started = time.monotonic()
            self._bloom_animation_timer.start()
        else:
            # 恢复历史状态时直接显示成熟花簇，不重复播放旧动画。
            self._bloom_transition_from_count = count
            self._bloom_transition_started = 0.0
            self._bloom_animation_timer.stop()
        self.update()

    def set_bloom_progress(self, value: float, *, animate: bool = False):
        """设置桌面藤蔓花期；0～1 仅控制既有花位的开放程度。"""
        value = self.clamp(float(value))
        previous = (
            self.bloom_progress
            if self.bloom_progress is not None
            else self.clamp(self.open_flower_count / max(1, len(self.flower_nodes)))
        )
        self.bloom_progress = value
        self.open_flower_count = (
            0 if value <= 0.0 else min(len(self.flower_nodes), math.ceil(len(self.flower_nodes) * value))
        )
        self._bloom_transition_from_count = self.open_flower_count
        if animate and value > previous and not self.reduced_motion:
            self._bloom_transition_from_progress = previous
            self._bloom_transition_to_progress = value
            self._bloom_transition_started = time.monotonic()
            self._bloom_animation_timer.start()
        else:
            self._bloom_transition_from_progress = value
            self._bloom_transition_to_progress = value
            self._bloom_transition_started = 0.0
            self._bloom_animation_timer.stop()
        self.update()

    def _advance_bloom_animation(self):
        if self._bloom_transition_started <= 0.0:
            self._bloom_animation_timer.stop()
            return
        if time.monotonic() - self._bloom_transition_started >= 1.2:
            self._bloom_transition_started = 0.0
            self._bloom_animation_timer.stop()
        self.update()

    def _animated_bloom_progress(self) -> float:
        if self.bloom_progress is None:
            return 0.0
        if self._bloom_transition_started <= 0.0:
            return self.bloom_progress
        elapsed = self.clamp((time.monotonic() - self._bloom_transition_started) / 1.2)
        eased = self._smoothstep(elapsed)
        return self._bloom_transition_from_progress + (
            self._bloom_transition_to_progress - self._bloom_transition_from_progress
        ) * eased

    def _flower_reveal_amount(self, node: VineNode) -> float:
        """返回单个花位从花苞到完全盛开的 0～1 开放度。"""
        if self.bloom_progress is not None:
            units = self._animated_bloom_progress() * len(self.flower_nodes)
            return self.clamp(units - node.unlock_rank)
        if node.unlock_rank >= self.open_flower_count:
            return 0.0
        if (
            self._bloom_transition_started > 0.0
            and node.unlock_rank >= self._bloom_transition_from_count
        ):
            elapsed = (time.monotonic() - self._bloom_transition_started) / 1.2
            return self._smoothstep(elapsed)
        return 1.0

    def set_growth_chapter(self, chapter: int):
        """章节参与稳定随机种子，使每株植物不同且跨重绘保持一致。"""
        chapter = max(1, int(chapter))
        if chapter == self.growth_chapter:
            return
        self.growth_chapter = chapter
        self.rebuild_path()
        self.update()

    def celebrate(self):
        """目标有推进后局部提亮约 1.2 秒；减少动效时只做一次静态刷新。"""
        if self.reduced_motion:
            self.completion_glow = 0.12
            self.update()
            QTimer.singleShot(180, self._finish_celebration)
            return
        self._celebration_started = time.monotonic()
        self._celebration_timer.start()

    def _advance_celebration(self):
        elapsed = time.monotonic() - self._celebration_started
        if elapsed >= 1.2:
            self._finish_celebration()
            return
        self.completion_glow = 0.24 * math.sin(math.pi * elapsed / 1.2)
        self.update()

    def _finish_celebration(self):
        self._celebration_timer.stop()
        self.completion_glow = 0.0
        self.update()

    def set_theme(self, name: str):
        normalized = normalize_theme_name(name)
        if normalized == self.theme_name:
            return
        self.theme_name = normalized
        self.theme = VINE_THEMES[normalized]
        self.profile = self.theme["profile"]
        self.rebuild_path()
        self.update()

    def tc(self, key: str, alpha: int) -> QColor:
        value = self.theme.get(key, self.theme["vine"])
        if not isinstance(value, tuple):
            value = self.theme["vine"]
        return QColor(*value, max(0, min(255, int(alpha))))

    def resizeEvent(self, event):
        self.rebuild_path()
        super().resizeEvent(event)

    @staticmethod
    def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    @staticmethod
    def shifted(point: QPointF, angle: float, distance: float) -> QPointF:
        radians = math.radians(angle)
        return QPointF(
            point.x() + math.cos(radians) * distance,
            point.y() + math.sin(radians) * distance,
        )

    def _sample_path(self, path: QPainterPath, offset: float, material: str) -> VineGesture:
        estimated = max(1.0, path.length())
        sample_count = max(24, min(240, int(estimated / 6.0)))
        points = [path.pointAtPercent(index / sample_count) for index in range(sample_count + 1)]
        distances = [0.0]
        total = 0.0
        for index in range(1, len(points)):
            a, b = points[index - 1], points[index]
            total += math.hypot(b.x() - a.x(), b.y() - a.y())
            distances.append(total)
        return VineGesture(points, distances, max(total, 1.0), offset, material)

    def rebuild_path(self):
        width, height = max(800, self.width()), max(500, self.height())
        offset = 0.0
        gestures: List[VineGesture] = []
        for path, material in composition_paths(self.profile, width, height, self.layout_name):
            gesture = self._sample_path(path, offset, material)
            gestures.append(gesture)
            offset += gesture.length
        self.gestures = gestures
        self.total_length = max(offset, 1.0)

        # 兼容旧版可检查属性；路径之间只保存数据，不会被连线绘制。
        self.path_points = []
        self.path_distances = []
        for gesture in gestures:
            self.path_points.extend(gesture.points)
            self.path_distances.extend(gesture.offset + value for value in gesture.distances)

        seed = (
            0x56494E45
            ^ (int(width) * 73856093)
            ^ (int(height) * 19349663)
            # 密度变化复用相同随机序列，避免拖动滑块时叶片左右乱跳。
            ^ (23 * 83492791)
            ^ sum(ord(char) for char in self.profile) * 2654435761
            ^ sum(ord(char) for char in self.layout_name) * 97531
            ^ self.growth_chapter * 16777619
        )
        self.build_natural_nodes(random.Random(seed & 0xFFFFFFFF))

    def _point_on_gesture(self, gesture: VineGesture, distance: float) -> Tuple[QPointF, float]:
        target = max(0.0, min(gesture.length, distance))
        index = bisect.bisect_left(gesture.distances, target)
        index = max(1, min(index, len(gesture.points) - 1))
        d0, d1 = gesture.distances[index - 1], gesture.distances[index]
        ratio = (target - d0) / max(1e-6, d1 - d0)
        a, b = gesture.points[index - 1], gesture.points[index]
        point = QPointF(a.x() + (b.x() - a.x()) * ratio, a.y() + (b.y() - a.y()) * ratio)
        angle = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
        return point, angle

    def point_at_distance(self, target: float) -> Tuple[QPointF, float]:
        target = max(0.0, min(self.total_length, target))
        for gesture in self.gestures:
            if target <= gesture.offset + gesture.length:
                return self._point_on_gesture(gesture, target - gesture.offset)
        last = self.gestures[-1]
        return self._point_on_gesture(last, last.length)

    def _inward_side(self, point: QPointF, angle: float) -> int:
        center_x, center_y = self.width() * 0.5, self.height() * 0.5
        scores = []
        for side in (1, -1):
            normal = math.radians(angle + side * 90.0)
            score = math.cos(normal) * (center_x - point.x()) + math.sin(normal) * (center_y - point.y())
            scores.append((score, side))
        return max(scores)[1]

    def _make_node(
        self,
        gesture: VineGesture,
        local_distance: float,
        rng: random.Random,
        *,
        scale: Tuple[float, float] = (0.8, 1.15),
        reach: Tuple[float, float] = (5.0, 14.0),
        variant: int | None = None,
        force_inward: bool = False,
        inward_bias: float = 0.70,
    ) -> VineNode:
        point, angle = self._point_on_gesture(gesture, local_distance)
        inward = self._inward_side(point, angle)
        side = inward if force_inward or rng.random() < inward_bias else -inward
        gesture_index = self.gestures.index(gesture)
        # distance 表示节点在整株时间轴上的出现时刻。环屏可由用户选择：
        # 四边同步、每边等时接力，或按真实藤长分配时长的自然接力。
        if self.layout_name == "环屏生长":
            local_ratio = local_distance / max(1.0, gesture.length)
            if self.perimeter_growth_mode == "四边同步":
                growth_distance = self.total_length * local_ratio
            elif self.perimeter_growth_mode == "等时接力":
                growth_distance = self.total_length * (
                    gesture_index + local_ratio
                ) / max(1, len(self.gestures))
            else:
                growth_distance = gesture.offset + local_distance
        else:
            growth_distance = gesture.offset + local_distance
        return VineNode(
            point=point,
            distance=growth_distance,
            angle=angle,
            side=side,
            scale=rng.uniform(*scale),
            variant=rng.randrange(5) if variant is None else variant,
            phase=rng.random(),
            reach=rng.uniform(*reach),
            bend=rng.uniform(-16.0, 16.0),
            gesture_index=gesture_index,
            local_distance=local_distance,
        )

    def build_nodes(self, spacing: int, start_offset: int) -> List[VineNode]:
        """兼容旧版节点接口，并保持尺寸、密度相同时结果稳定。"""
        rng = random.Random(int(self.total_length) ^ spacing ^ (start_offset << 7))
        nodes = []
        distance = float(start_offset)
        while distance < self.total_length:
            point, angle = self.point_at_distance(distance)
            side = self._inward_side(point, angle)
            nodes.append(VineNode(point, distance, angle, side, rng.uniform(0.8, 1.12), rng.randrange(5), rng.random(), 8.0, 0.0))
            distance += max(18.0, spacing * rng.uniform(0.78, 1.24))
        return nodes

    def build_natural_nodes(self, rng: random.Random):
        metrics = PROFILE_METRICS[self.profile]
        density = max(0.45, self.density_factor)
        # 单株构图将器官拆得更细、更密，但不扩大占屏范围；环屏则保留充分留白。
        layout_spacing = 0.52 if self.layout_name == "静谧单株" else 0.68 if self.layout_name == "侧边攀援" else 0.86
        self.leaf_nodes = []
        self.branch_nodes = []
        self.tendril_nodes = []
        self.bud_nodes = []
        self.flower_nodes = []

        for gesture in self.gestures:
            distance = rng.uniform(24.0, 48.0) * layout_spacing
            while distance < gesture.length - 12.0:
                self.leaf_nodes.append(
                    self._make_node(
                        gesture, distance, rng,
                        scale=(0.72, 1.16), reach=(4.0, 12.0),
                        force_inward=self.profile == "glow", inward_bias=0.66,
                    )
                )
                # 极光心形叶从顶部凹口连接；同锚点反向复制会形成明显重叠，
                # 因此由侧枝端叶提供丰满度，不再生成共用锚点的成对直属叶。
                pair_probability = (
                    0.0 if self.profile == "glow"
                    else (0.14 if self.profile == "ivy" else 0.0)
                )
                if self.profile != "glow":
                    pair_probability += max(0.0, (self.density_value - 25) / 75.0) * 0.60
                if rng.random() < pair_probability:
                    pair = self._make_node(gesture, distance + 0.01, rng, scale=(0.54, 0.82), reach=(3.0, 7.0))
                    pair.side *= -1
                    self.leaf_nodes.append(pair)
                distance += rng.uniform(0.78, 1.24) * metrics["leaf_spacing"] * layout_spacing / density

            distance = rng.uniform(80.0, 145.0) * layout_spacing
            while distance < gesture.length - 35.0:
                self.branch_nodes.append(
                    self._make_node(gesture, distance, rng, scale=(0.76, 1.10), reach=(34.0, 69.0), force_inward=True)
                )
                distance += rng.uniform(0.82, 1.20) * metrics["branch_spacing"] * layout_spacing / density

            if self.profile in ("ivy", "wisteria", "glow"):
                distance = rng.uniform(115.0, 190.0) * layout_spacing
                while distance < gesture.length - 24.0:
                    self.tendril_nodes.append(
                        self._make_node(gesture, distance, rng, scale=(0.78, 1.08), reach=(20.0, 37.0), force_inward=True)
                    )
                    distance += rng.uniform(245.0, 370.0) * layout_spacing / density

            distance = rng.uniform(95.0, 165.0) * layout_spacing
            while distance < gesture.length - 24.0:
                self.bud_nodes.append(
                    self._make_node(gesture, distance, rng, scale=(0.72, 1.05), reach=(9.0, 18.0), force_inward=True)
                )
                distance += rng.uniform(0.80, 1.18) * metrics["bud_spacing"] * layout_spacing / density

        # 花位采用有节奏的固定比例，而不是依赖超大随机间距。密度只决定
        # 可用花位数量；任务轮次只揭示这些花位，二者互不覆盖。
        base_slots = {
            # 单株路径可用长度最短；四个普通主题花位已经足够形成终态，
            # 再塞第五个会挤掉高密度极光叶片，反而破坏浓密度语义。
            "静谧单株": 3 if self.profile == "wisteria" else 4,
            "侧边攀援": 7 if self.profile == "wisteria" else 8,
            "环屏生长": 12 if self.profile == "wisteria" else 18,
        }[self.layout_name]
        # 0%～100% 对应约 35%～110% 的主题容量。低密度真正留白，
        # 高密度则增加花位；轮次推进不会触碰这个容量计算。
        slot_multiplier = 0.35 + self.density_value * 0.0075
        chapter_slot_limit = 16 if self.profile == "wisteria" else 24
        desired_slots = min(
            chapter_slot_limit,
            max(2, int(round(base_slots * slot_multiplier))),
        )
        gesture_counts = [desired_slots // len(self.gestures)] * len(self.gestures)
        for index in range(desired_slots % len(self.gestures)):
            gesture_counts[index] += 1
        flower_groups: list[list[VineNode]] = []
        for gesture_index, slot_count in enumerate(gesture_counts):
            gesture = self.gestures[gesture_index]
            group: list[VineNode] = []
            for slot in range(slot_count):
                # 每段的第一个花位靠近早期已成熟区域，确保前几轮就能跨区域
                # 看见开花；后续花位仍留有充分间隔，避免一开始就过度茂盛。
                if self.layout_name == "环屏生长":
                    # 第一组靠近四段起点，后续花位均匀铺开；不再用固定
                    # “24 个花位”推算间距，避免低密度时仍挤成高密度。
                    fraction = (
                        0.032
                        if slot_count <= 1
                        else 0.032 + 0.85 * (slot / (slot_count - 1)) ** 1.08
                    )
                    fraction += rng.uniform(-0.005, 0.005)
                else:
                    fraction = (
                        0.028
                        if slot_count <= 1
                        else 0.028 + 0.84 * (slot / (slot_count - 1)) ** 1.10
                    )
                    fraction += rng.uniform(-0.008, 0.008)
                variant = (slot + gesture_index) % 3
                node = self._make_node(
                    gesture,
                    gesture.length * self.clamp(fraction, 0.012, 0.93),
                    rng,
                    scale=(0.86, 1.08) if self.profile == "wisteria" else (0.76, 1.08),
                    reach=(6.0, 14.0) if self.profile == "wisteria" else (12.0, 24.0),
                    variant=variant,
                    force_inward=True,
                )
                if self.profile == "wisteria":
                    node.scale *= (0.84, 1.0, 1.14)[variant]
                self.flower_nodes.append(node)
                group.append(node)
            flower_groups.append(group)

        # 环屏时交替选择相距最远的路径段，形成不对称但均衡的开花节奏：
        # 第一处、对角处、另一侧、最后一侧，而不是先把左上角全部开满。
        # 每株使用稳定随机顺序选择区域：看起来有生命感，但重绘、暂停和重启
        # 都不会换位置。一个轮转周期内每段只出现一次，保证跨区域分散。
        if self.layout_name == "环屏生长" and self.perimeter_growth_mode != "四边同步":
            # 接力模式只能在已经长到的边上开花，不能先解锁尚未出现的角落。
            unlock_order = sorted(self.flower_nodes, key=lambda node: node.distance)
        else:
            gesture_order = list(range(len(flower_groups)))
            rng.shuffle(gesture_order)
            unlock_order = []
            max_slots = max((len(group) for group in flower_groups), default=0)
            for slot in range(max_slots):
                for gesture_index in gesture_order:
                    group = flower_groups[gesture_index]
                    if slot < len(group):
                        unlock_order.append(group[slot])
        for rank, node in enumerate(unlock_order):
            node.unlock_rank = rank

        # 花位优先，随后保证侧枝与直属叶；普通花苞、卷须在空间不足时让位。
        # 这样“枝叶浓密度”不会被次要装饰器官反向稀释，也不会把透明素材
        # 堆在同一个关节上。
        def is_clear(node: VineNode, blockers: list[VineNode], gap: float) -> bool:
            for other in blockers:
                point_gap = math.hypot(
                    node.point.x() - other.point.x(), node.point.y() - other.point.y()
                )
                # 不同路径在四角也可能靠得很近，必须继续检查屏幕坐标；
                # 只有路径内距离这一项可以限定在同一段手势上。
                path_too_close = (
                    node.gesture_index == other.gesture_index
                    and abs(node.local_distance - other.local_distance) < gap
                )
                if path_too_close or point_gap < gap * 0.82:
                    return False
            return True

        def spaced(
            candidates: list[VineNode], blockers: list[VineNode], gap: float, self_gap: float,
            *, allow_opposite_pair: bool = False,
        ) -> list[VineNode]:
            selected: list[VineNode] = []
            for node in sorted(candidates, key=lambda item: item.distance):
                self_blockers = selected
                if allow_opposite_pair:
                    self_blockers = [
                        other
                        for other in selected
                        if not (
                            other.gesture_index == node.gesture_index
                            and other.side != node.side
                            and abs(other.local_distance - node.local_distance) < 0.5
                        )
                    ]
                if is_clear(node, blockers, gap) and is_clear(node, self_blockers, self_gap):
                    selected.append(node)
            return selected

        def fill_to_density_floor(
            selected: list[VineNode],
            desired: int,
            blockers: list[VineNode],
            gap: float,
            self_gap: float,
            *,
            organ: str,
        ) -> list[VineNode]:
            """在净距允许的空位补足枝叶层级，避免高密度反而显得更稀。"""
            if len(selected) >= desired or not self.gestures:
                return selected
            phase_offset = 0.173 if organ == "branch" else 0.417
            attempts = max(96, desired * len(self.gestures) * 10)
            for attempt in range(attempts):
                gesture_index = attempt % len(self.gestures)
                sequence = attempt // len(self.gestures)
                gesture = self.gestures[gesture_index]
                # 黄金分割步进避免补位形成机械等距列，同时轮询路径，环屏不会
                # 为了补数量再次集中到左上角。
                unit = (
                    sequence * 0.61803398875
                    + gesture_index * 0.193
                    + phase_offset
                ) % 1.0
                local_distance = gesture.length * (0.035 + unit * 0.88)
                if organ == "branch":
                    candidate = self._make_node(
                        gesture,
                        local_distance,
                        rng,
                        scale=(0.72, 1.04),
                        reach=(30.0, 61.0),
                        force_inward=True,
                    )
                else:
                    candidate = self._make_node(
                        gesture,
                        local_distance,
                        rng,
                        scale=(0.68, 1.08),
                        reach=(4.0, 11.0),
                        force_inward=self.profile == "glow",
                        inward_bias=0.68,
                    )
                if is_clear(candidate, blockers, gap) and is_clear(
                    candidate, selected, self_gap
                ):
                    selected.append(candidate)
                    if len(selected) >= desired:
                        break
            return selected

        flower_gap = 28.0 if self.profile == "glow" else 22.0
        self.branch_nodes = spaced(self.branch_nodes, self.flower_nodes, flower_gap, 32.0)
        density_ratio = self.clamp(self.density_value / 100.0)
        branch_floor_ranges = {
            "静谧单株": (1, 3),
            "侧边攀援": (2, 7),
            "环屏生长": (5, 12),
        }
        branch_low, branch_high = branch_floor_ranges[self.layout_name]
        branch_floor = round(
            branch_low + (branch_high - branch_low) * density_ratio ** 0.9
        )
        self.branch_nodes = fill_to_density_floor(
            self.branch_nodes,
            branch_floor,
            self.flower_nodes,
            flower_gap,
            32.0,
            organ="branch",
        )
        leaf_gap = 24.0 if self.profile == "glow" else 18.0
        self.leaf_nodes = spaced(
            self.leaf_nodes,
            self.flower_nodes + self.branch_nodes,
            leaf_gap,
            16.0,
            allow_opposite_pair=self.profile != "glow",
        )
        leaf_floor_ranges = {
            "静谧单株": (3, 10),
            "侧边攀援": (6, 18),
            "环屏生长": (12, 36),
        }
        leaf_low, leaf_high = leaf_floor_ranges[self.layout_name]
        leaf_floor = round(leaf_low + (leaf_high - leaf_low) * density_ratio ** 0.9)
        self.leaf_nodes = fill_to_density_floor(
            self.leaf_nodes,
            leaf_floor,
            self.flower_nodes + self.branch_nodes,
            leaf_gap,
            16.0,
            organ="leaf",
        )
        self.bud_nodes = spaced(
            self.bud_nodes,
            self.flower_nodes + self.branch_nodes + self.leaf_nodes,
            flower_gap,
            27.0,
        )
        self.tendril_nodes = spaced(
            self.tendril_nodes,
            self.flower_nodes + self.branch_nodes + self.leaf_nodes + self.bud_nodes,
            max(20.0, leaf_gap),
            28.0,
        )

        for collection in (self.leaf_nodes, self.branch_nodes, self.tendril_nodes, self.bud_nodes, self.flower_nodes):
            collection.sort(key=lambda node: node.distance)
        if self.bloom_progress is not None:
            self.open_flower_count = (
                0
                if self.bloom_progress <= 0.0
                else min(
                    len(self.flower_nodes),
                    math.ceil(len(self.flower_nodes) * self.bloom_progress),
                )
            )

    def _path_until(self, gesture: VineGesture, local_length: float) -> QPainterPath:
        target = max(0.0, min(gesture.length, local_length))
        path = QPainterPath(gesture.points[0])
        if target <= 0.0:
            return path
        end_index = bisect.bisect_right(gesture.distances, target)
        for point in gesture.points[1:end_index]:
            path.lineTo(point)
        if end_index < len(gesture.points):
            point, _ = self._point_on_gesture(gesture, target)
            path.lineTo(point)
        return path

    def shortened_path(self, path: QPainterPath, fraction: float, samples: int = 36) -> QPainterPath:
        fraction = self.clamp(fraction)
        shortened = QPainterPath(path.pointAtPercent(0.0))
        for index in range(1, max(2, samples) + 1):
            shortened.lineTo(path.pointAtPercent(fraction * index / samples))
        return shortened

    def _resolution_scale(self) -> float:
        """在 Retina/高 DPI 屏上适度增大器官，但不按像素数量线性膨胀。"""
        return self.clamp(
            min(self.width() / 1920.0, self.height() / 1080.0), 0.90, 1.35
        )

    def _gesture_visible_length(self, gesture: VineGesture, grown_length: float) -> float:
        """按用户选择的环屏节奏返回单段路径的可见长度。"""
        if self.layout_name == "环屏生长":
            if self.perimeter_growth_mode == "四边同步":
                return gesture.length * self.progress
            if self.perimeter_growth_mode == "等时接力":
                gesture_index = self.gestures.index(gesture)
                local_progress = self.clamp(
                    self.progress * len(self.gestures) - gesture_index
                )
                return gesture.length * local_progress
        return self.clamp(
            (grown_length - gesture.offset) / max(1.0, gesture.length)
        ) * gesture.length

    def draw_main_vines(self, painter: QPainter, grown_length: float, textured: bool = False):
        """绘制连续主藤；细分器官模式下只保留克制的连接骨架。"""
        resolution_scale = self._resolution_scale()
        base_width = PROFILE_METRICS[self.profile]["base_width"] * resolution_scale
        for gesture in self.gestures:
            visible = self._gesture_visible_length(gesture, grown_length)
            if visible <= 0.0:
                continue
            path = self._path_until(gesture, visible)
            mature = self.clamp(visible / max(1.0, gesture.length))
            width = base_width * (1.08 - 0.22 * mature)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            shadow_alpha = 18 if textured else 30
            shadow = QPen(self.tc("leaf_dark", shadow_alpha), width + (2.8 if textured else 5.0))
            shadow.setCapStyle(Qt.PenCapStyle.RoundCap)
            shadow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(shadow)
            painter.drawPath(path)

            main_alpha = (148 if gesture.material != "luminous" else 132) if textured else (225 if gesture.material != "luminous" else 190)
            main = QPen(self.tc("vine", main_alpha), width)
            main.setCapStyle(Qt.PenCapStyle.RoundCap)
            main.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(main)
            painter.drawPath(path)

            painter.save()
            painter.translate(-0.65, -0.75)
            highlight_alpha = (76 if gesture.material != "luminous" else 108) if textured else (155 if gesture.material != "luminous" else 205)
            highlight = QPen(self.tc("vine_light", highlight_alpha), max(0.70, width * (0.25 if textured else 0.34)))
            highlight.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(highlight)
            painter.drawPath(path)
            painter.restore()

            if gesture.material == "luminous":
                glow = QPen(self.tc("spark", 18 if textured else 34), width + (4.5 if textured else 8.0))
                glow.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(glow)
                painter.drawPath(path)

    @staticmethod
    def _smoothstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    def _organ_age(self, grown_length: float, node: VineNode, delay: float, duration: float) -> float:
        return self._smoothstep((grown_length - node.distance - delay) / max(1.0, duration))

    def _organ_direction(self, node: VineNode, spread: float = 66.0) -> float:
        motion = 0.0 if self.reduced_motion else (2.15 if self.rest_mode else 0.20)
        wind = math.sin(self.rest_wave * 1.55 + node.phase * math.tau) * motion
        return node.angle + node.side * (spread + node.bend * 0.65) + wind

    def draw_segmented_stems(
        self,
        painter: QPainter,
        grown_length: float,
        presence_scale: float,
    ) -> None:
        """先画连续侧枝和卷须；主藤稍后覆盖根部，消除组件切口。"""
        theme = self.theme_name
        resolution_scale = self._resolution_scale()
        branch_scale = resolution_scale * (0.86 + self.plant_presence * 0.24)
        base_width = PROFILE_METRICS[self.profile]["base_width"] * resolution_scale

        # 侧枝的结构由连续曲线承担；独立木质组件只作低透明纹理，不再充当
        # 整根分枝。这样高分屏也不会出现粗大的“截断管子”。
        for index, node in enumerate(self.branch_nodes):
            if node.distance > grown_length:
                break
            age = self._organ_age(grown_length, node, 0.0, 112.0)
            if age <= 0.015:
                continue
            path = self.shortened_path(self._branch_path(node, branch_scale), age, 32)
            width = max(0.85, base_width * node.scale * (0.53 + age * 0.13))
            shadow = QPen(self.tc("leaf_dark", int(82 + age * 42)), width + 1.7)
            shadow.setCapStyle(Qt.PenCapStyle.RoundCap)
            shadow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(shadow)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            stem = QPen(self.tc("vine", int(142 + age * 48)), width)
            stem.setCapStyle(Qt.PenCapStyle.RoundCap)
            stem.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(stem)
            painter.drawPath(path)
            painter.save()
            painter.translate(-0.35, -0.45)
            highlight = QPen(self.tc("vine_light", int(72 + age * 50)), max(0.55, width * 0.28))
            highlight.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(highlight)
            painter.drawPath(path)
            painter.restore()

            # 每三处分枝只保留两处纹理组件，降低重复感；尺寸受严格上限控制。
            if age < 0.24 or index % 3 == 1:
                continue
            if age < 0.34:
                organ = "stem_short"
            elif age < 0.80 or index % 4:
                organ = "stem_curve"
            else:
                organ = "stem_fork"
            height = min(node.reach * 0.62, 15.0 + 20.0 * age) * node.scale * resolution_scale
            BotanicalAssets.draw_organ(
                painter, theme, organ, node.point,
                self._branch_direction(node), height,
                opacity=(0.16 + age * 0.25) * presence_scale, mirror=node.side < 0,
            )

        # 卷须在枝条之后出现并逐渐伸展，保持细而轻。
        for node in self.tendril_nodes:
            if node.distance > grown_length:
                break
            age = self._organ_age(grown_length, node, 18.0, 92.0)
            if age <= 0.015:
                continue
            BotanicalAssets.draw_organ(
                painter, theme, "tendril", node.point,
                self._organ_direction(node, 62.0),
                (9.0 + 27.0 * age) * node.scale * presence_scale * resolution_scale,
                opacity=0.30 + age * 0.46, mirror=node.side < 0,
            )

    def draw_segmented_foliage(
        self,
        painter: QPainter,
        grown_length: float,
        density_scale: float,
        presence_scale: float,
    ) -> None:
        """在闭合关节之上绘制端叶、直属叶、花苞和花，形成自然遮挡。"""
        theme = self.theme_name
        profile_leaf_scale = PROFILE_METRICS[self.profile]["leaf_scale"]
        resolution_scale = self._resolution_scale()
        foliage_scale = 1.24 * resolution_scale

        # 每根侧枝先在当前生长尖端长一片小叶，成熟后再展开第二片。
        for node in self.branch_nodes:
            if node.distance > grown_length:
                break
            age = self._organ_age(grown_length, node, 0.0, 112.0)
            if age <= 0.36:
                continue
            path = self._branch_path(
                node, resolution_scale * (0.86 + self.plant_presence * 0.24)
            )
            reveal = self.clamp((age - 0.36) / 0.64)
            tip = path.pointAtPercent(max(0.40, age))
            direction = self._branch_direction(node)
            stage = min(3, int(reveal * 4.0))
            organ = ("leaf_tiny", "leaf_small", "leaf_medium", "leaf_mature")[stage]
            BotanicalAssets.draw_organ(
                painter, theme, organ, tip,
                direction + node.side * 28.0,
                (11.0 + 27.0 * reveal) * node.scale * profile_leaf_scale
                * density_scale * presence_scale * foliage_scale,
                opacity=0.40 + reveal * 0.54, mirror=node.side < 0,
            )
            if age > 0.72 and self.density_value >= 34:
                child = path.pointAtPercent(0.66)
                child_reveal = self.clamp((age - 0.72) / 0.28)
                BotanicalAssets.draw_organ(
                    painter, theme, "leaf_small", child,
                    direction - node.side * 34.0,
                    (15.0 + 12.0 * child_reveal) * node.scale * profile_leaf_scale
                    * presence_scale * foliage_scale,
                    opacity=0.34 + child_reveal * 0.46, mirror=node.side > 0,
                )
            if age > 0.88 and self.density_value >= 70:
                crown = path.pointAtPercent(0.84)
                crown_reveal = self.clamp((age - 0.88) / 0.12)
                BotanicalAssets.draw_organ(
                    painter, theme, "leaf_tiny", crown,
                    direction + node.side * 54.0,
                    (11.0 + 9.0 * crown_reveal) * node.scale * profile_leaf_scale
                    * presence_scale * foliage_scale,
                    opacity=0.30 + crown_reveal * 0.40, mirror=node.side < 0,
                )

        # 一枚叶片会经历嫩芽、小叶、舒展叶和成熟叶四个离散形态。
        leaf_names = ("leaf_tiny", "leaf_small", "leaf_medium", "leaf_mature")
        for node in self.leaf_nodes:
            if node.distance > grown_length:
                break
            age = self._organ_age(grown_length, node, 10.0, 104.0)
            if age <= 0.015:
                continue
            stage = min(3, int(age * 4.0))
            # 少数成熟节点停留在“舒展叶”轮廓，打破一排同尺寸叶片的机械感。
            if stage == 3 and node.variant % 5 == 0:
                stage = 2
            base_height = 9.0 + 27.0 * age
            if self.profile == "wisteria":
                base_height *= 1.10
            elif self.profile == "ivy":
                base_height *= 1.04
            BotanicalAssets.draw_organ(
                painter, theme, leaf_names[stage], node.point,
                self._organ_direction(node, 50.0),
                base_height * node.scale * profile_leaf_scale * density_scale * presence_scale * foliage_scale,
                opacity=0.42 + age * 0.54, mirror=node.side < 0,
            )

        # 普通花苞只生长到膨大态，不会因为计时进度自动开花。
        for node in self.bud_nodes:
            if node.distance > grown_length:
                break
            age = self._organ_age(grown_length, node, 24.0, 118.0)
            if age <= 0.015:
                continue
            organ = "bud_closed" if age < 0.58 else "bud_swollen"
            BotanicalAssets.draw_organ(
                painter, theme, organ, node.point,
                self._organ_direction(node, 58.0),
                (8.0 + 21.0 * age) * node.scale * density_scale * presence_scale * foliage_scale,
                opacity=0.48 + age * 0.50, mirror=node.side < 0,
            )

        # 花位只在获得时出现，并从花苞舒展；具体朵数由植物习性决定。
        flower_names = ("bud_closed", "bud_swollen", "bloom_half", "bloom_open")
        for index, node in enumerate(self.flower_nodes):
            if node.distance > grown_length:
                break
            reveal = self._flower_reveal_amount(node)
            # 尚未进入本轮花期的规划花位完全不绘制；密度依旧只由节点生成
            # 控制。进入花期后则从花苞、半开到盛开连续舒展。
            if reveal <= 0.001:
                continue
            age = reveal
            if age <= 0.015:
                continue
            if self.profile == "wisteria":
                cluster_plan = ((0.0, 1.0, 0.0),)
                base_height = (16.0 + 53.0 * age) * node.scale
            elif self.profile == "cherry":
                cluster_plan = ((0.0, 1.0, 0.0),)
                if node.variant == 1:
                    cluster_plan += ((-31.0, 0.62, 0.14),)
                elif node.variant == 2:
                    cluster_plan += ((28.0, 0.58, 0.18),)
                base_height = (11.0 + 33.0 * age) * node.scale
            elif self.profile == "glow":
                cluster_plan = ((0.0, 1.0, 0.0),)
                if node.variant:
                    cluster_plan += (((-28.0 if node.variant == 1 else 30.0), 0.54, 0.16),)
                base_height = (11.0 + 33.0 * age) * node.scale
            else:
                cluster_plan = ((0.0, 1.0, 0.0),)
                if node.variant:
                    cluster_plan += (((-27.0 if node.variant == 1 else 29.0), 0.60, 0.15),)
                base_height = (11.0 + 33.0 * age) * node.scale

            # 组合成员共享同一真实根部并以小延迟逐个舒展，不会出现漂浮花。
            # 超过可用花位的成果只轻微提高丰满度，避免遮挡中央工作区。
            members = cluster_plan
            surplus = max(0, self.open_flower_count - len(self.flower_nodes))
            fullness = 1.0 + min(0.10, surplus * 0.012)
            base_direction = self._organ_direction(node, 57.0)
            for member_index, (angle_offset, scale, delay) in enumerate(members):
                member_age = self.clamp((age - delay) / max(0.01, 1.0 - delay))
                stage = min(3, int(member_age * 4.0))
                organ = flower_names[stage]
                full_bloom = stage == 3
                breathing = 1.0
                breath_alpha = 1.0
                if full_bloom and not self.reduced_motion:
                    wave = math.sin(
                        self.rest_wave * 1.45 + node.phase * math.tau + member_index * 0.8
                    )
                    breathing += (0.055 if self.rest_mode else 0.006) * wave
                    breath_alpha += (0.10 if self.rest_mode else 0.01) * wave
                BotanicalAssets.draw_organ(
                    painter, theme, organ, node.point,
                    base_direction + node.side * angle_offset,
                    base_height * scale * fullness * presence_scale * foliage_scale * breathing,
                    opacity=min(1.0, (0.52 + member_age * 0.46) * breath_alpha),
                    mirror=(node.side < 0) != (member_index % 2 == 1),
                )

    def draw_asset_growing_tip(self, painter: QPainter, grown_length: float) -> None:
        """用两片嫩叶形成真实生长尖端，避免回落到矢量图标画风。"""
        if self.rest_mode or grown_length <= 4.0 or grown_length >= self.total_length - 1.0:
            return
        resolution_scale = self._resolution_scale()
        size = 28.0 * resolution_scale
        tips = []
        if self.layout_name == "环屏生长":
            for gesture in self.gestures:
                visible = self._gesture_visible_length(gesture, grown_length)
                if 4.0 < visible < gesture.length - 1.0:
                    tips.append(self._point_on_gesture(gesture, visible))
        else:
            tips.append(self.point_at_distance(grown_length))
        for point, angle in tips:
            BotanicalAssets.draw_organ(
                painter, self.theme_name, "leaf_tiny", point,
                angle - 28.0, size, opacity=0.88,
            )
            BotanicalAssets.draw_organ(
                painter, self.theme_name, "leaf_tiny", point,
                angle + 30.0, size * 0.78, opacity=0.78, mirror=True,
            )

    def draw_terminal_caps(
        self,
        painter: QPainter,
        grown_length: float,
        presence_scale: float,
    ) -> None:
        """用嫩叶和花苞收住已完成路径，避免圆头主藤像被突然剪断。"""
        resolution_scale = self._resolution_scale()
        density_size = 1.0
        for gesture in self.gestures:
            visible = self._gesture_visible_length(gesture, grown_length)
            if visible < gesture.length - 0.6:
                continue
            point, angle = self._point_on_gesture(gesture, gesture.length)
            side = self._inward_side(point, angle)
            size = 20.0 * resolution_scale * density_size * presence_scale
            BotanicalAssets.draw_organ(
                painter, self.theme_name, "leaf_small", point,
                angle + side * 22.0, size,
                opacity=0.86, mirror=side < 0,
            )
            if self.density_value >= 34:
                back = self.shifted(point, angle + 180.0, 5.0 * resolution_scale)
                BotanicalAssets.draw_organ(
                    painter, self.theme_name, "leaf_tiny", back,
                    angle - side * 35.0, size * 0.64,
                    opacity=0.72, mirror=side > 0,
                )
            if self.density_value >= 70 and self.profile in ("cherry", "glow"):
                BotanicalAssets.draw_organ(
                    painter, self.theme_name, "bud_closed", point,
                    angle + side * 5.0, size * 0.72,
                    opacity=0.82, mirror=side < 0,
                )

    def _branch_direction(self, node: VineNode) -> float:
        """侧枝顺着主藤舒展，避免与边缘路径形成僵硬的九十度悬挂。"""
        return node.angle + node.side * (43.0 + node.bend * 0.48)

    def _branch_path(self, node: VineNode, length_scale: float = 1.0) -> QPainterPath:
        direction = self._branch_direction(node)
        reach = node.reach * node.scale * length_scale
        end = self.shifted(node.point, direction, reach)
        path = QPainterPath(node.point)
        path.cubicTo(
            self.shifted(node.point, node.angle, reach * 0.30),
            self.shifted(end, direction + 180.0, reach * 0.34),
            end,
        )
        return path

    def draw_side_branches(self, painter: QPainter, grown_length: float, foliage: bool):
        for node in self.branch_nodes:
            if node.distance > grown_length:
                break
            local = self.clamp((grown_length - node.distance) / 105.0)
            if local <= 0.01:
                continue
            path = self.shortened_path(self._branch_path(node), local, 22)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self.tc("leaf_dark", int((38 if not foliage else 120) * local)), 3.4 if not foliage else 1.45))
            painter.drawPath(path)
            if foliage and local > 0.58:
                end = self._branch_path(node).pointAtPercent(1.0)
                angle = node.angle + node.side * (68.0 + node.bend)
                leaf = VineNode(end, node.distance, angle, node.side, node.scale * 0.72, (node.variant + 2) % 5, node.phase, 2.0, -8.0)
                self.draw_leaf(painter, leaf, self.clamp((local - 0.58) / 0.42), int(190 * local))

    def draw_tendrils(self, painter: QPainter, grown_length: float):
        for node in self.tendril_nodes:
            if node.distance > grown_length:
                break
            local = self.clamp((grown_length - node.distance) / 90.0)
            direction = node.angle + node.side * (78.0 + node.bend)
            stem_end = self.shifted(node.point, direction, node.reach * 0.60)
            curve = QPainterPath(node.point)
            curve.cubicTo(
                self.shifted(node.point, node.angle, node.reach * 0.20),
                self.shifted(stem_end, direction + 180.0, node.reach * 0.20),
                stem_end,
            )
            center = self.shifted(stem_end, direction, 3.0)
            start = math.radians(direction + 180.0)
            for index in range(1, 19):
                t = index / 18.0
                angle = start + node.side * math.tau * 1.30 * t
                radius = (5.8 - 3.9 * t) * node.scale
                curve.lineTo(QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius))
            pen = QPen(self.tc("tendril", int(148 * local)), 1.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shortened_path(curve, local, 28))

    def leaf_shape(self, variant: int, length: float, width: float) -> QPainterPath:
        path = QPainterPath()
        if self.profile == "ivy":
            # 用连续曲线塑造三裂/五裂常春藤，避免折纸般的直线锯齿。
            path.moveTo(0.0, 0.0)
            if variant % 2 == 0:
                path.cubicTo(length * 0.10, -width * 0.08, length * 0.16, -width * 0.34, length * 0.17, -width * 0.58)
                path.cubicTo(length * 0.24, -width * 0.48, length * 0.34, -width * 0.76, length * 0.34, -width)
                path.cubicTo(length * 0.47, -width * 0.78, length * 0.57, -width * 0.65, length * 0.69, -width * 0.83)
                path.cubicTo(length * 0.72, -width * 0.49, length * 0.88, -width * 0.25, length, 0.0)
                path.cubicTo(length * 0.88, width * 0.25, length * 0.72, width * 0.49, length * 0.69, width * 0.83)
                path.cubicTo(length * 0.57, width * 0.65, length * 0.47, width * 0.78, length * 0.34, width)
                path.cubicTo(length * 0.34, width * 0.76, length * 0.24, width * 0.48, length * 0.17, width * 0.58)
                path.cubicTo(length * 0.16, width * 0.34, length * 0.10, width * 0.08, 0.0, 0.0)
            else:
                path.cubicTo(length * 0.14, -width * 0.10, length * 0.23, -width * 0.40, length * 0.27, -width * 0.66)
                path.cubicTo(length * 0.40, -width * 0.52, length * 0.48, -width * 0.83, length * 0.50, -width)
                path.cubicTo(length * 0.61, -width * 0.70, length * 0.82, -width * 0.39, length, 0.0)
                path.cubicTo(length * 0.82, width * 0.39, length * 0.61, width * 0.70, length * 0.50, width)
                path.cubicTo(length * 0.48, width * 0.83, length * 0.40, width * 0.52, length * 0.27, width * 0.66)
                path.cubicTo(length * 0.23, width * 0.40, length * 0.14, width * 0.10, 0.0, 0.0)
            path.closeSubpath()
            return path

        narrow = 0.62 if self.profile in ("cherry", "glow") else 0.82
        width *= narrow
        path.moveTo(0.0, 0.0)
        path.cubicTo(length * 0.20, -width, length * 0.72, -width * 0.92, length, 0.0)
        path.cubicTo(length * 0.72, width * 0.92, length * 0.20, width, 0.0, 0.0)
        return path

    def draw_leaf(self, painter: QPainter, node: VineNode, scale: float, alpha: int):
        total_scale = max(0.0, scale) * node.scale * PROFILE_METRICS[self.profile]["leaf_scale"]
        alpha = int(self.clamp(alpha, 0, 255))
        if total_scale <= 0.02 or alpha <= 0:
            return
        motion = 0.0 if self.reduced_motion else (2.0 if self.rest_mode else 0.65)
        wind = math.sin(self.rest_wave * 0.72 + node.phase * math.tau) * motion
        direction = node.angle + node.side * (60.0 + node.bend) + wind
        painter.save()
        painter.translate(node.point)
        painter.rotate(direction)
        reach = node.reach * total_scale
        petiole = QPen(self.tc("vine", int(alpha * 0.82)), max(0.55, 0.95 * total_scale))
        petiole.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(petiole)
        painter.drawLine(QPointF(0.0, 0.0), QPointF(reach, 0.0))
        painter.translate(reach, 0.0)

        length = (25.0 + (node.variant % 3) * 2.4) * total_scale
        width_factor = 0.46 if self.profile == "ivy" else 0.34 if self.profile == "wisteria" else 0.31
        width = length * width_factor
        shape = self.leaf_shape(node.variant, length, width)
        gradient = QLinearGradient(0.0, -width, length, width)
        gradient.setColorAt(0.0, self.tc("leaf_dark", alpha))
        gradient.setColorAt(0.54, self.tc("leaf", alpha))
        tip = self.tc("leaf", alpha).lighter(119)
        tip.setAlpha(alpha)
        gradient.setColorAt(1.0, tip)
        edge_alpha = int(alpha * (0.92 if self.profile != "glow" else 0.72))
        painter.setPen(QPen(self.tc("leaf_dark", edge_alpha), max(0.45, 0.68 * total_scale)))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(shape)

        vein_alpha = int(alpha * (0.48 if self.profile != "glow" else 0.78))
        painter.setPen(QPen(self.tc("leaf_vein", vein_alpha), max(0.36, 0.56 * total_scale)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(0.0, 0.0), QPointF(length * 0.84, 0.0))
        if self.profile == "glow":
            glow_pen = QPen(self.tc("spark", int(alpha * 0.18)), max(2.0, 3.8 * total_scale))
            painter.setPen(glow_pen)
            painter.drawPath(shape)
        painter.restore()

    def draw_bud(self, painter: QPainter, node: VineNode, scale: float, alpha: int, stage: float = 1.0):
        scale = max(0.0, scale) * node.scale
        stage = self.clamp(stage)
        alpha = int(self.clamp(alpha, 0, 255))
        if scale <= 0.02 or alpha <= 0:
            return
        direction = node.angle + node.side * (72.0 + node.bend)
        painter.save()
        painter.translate(node.point)
        painter.rotate(direction)
        stem = node.reach * scale
        painter.setPen(QPen(self.tc("vine", int(alpha * 0.86)), max(0.55, scale)))
        painter.drawLine(QPointF(), QPointF(stem, 0.0))
        painter.translate(stem, 0.0)
        painter.rotate(90.0)
        height, width = (6.5 + 9.5 * stage) * scale, (3.0 + 4.8 * stage) * scale
        shape = QPainterPath(QPointF(0.0, height * 0.52))
        shape.cubicTo(-width, height * 0.15, -width * 0.62, -height * 0.42, 0.0, -height * 0.55)
        shape.cubicTo(width * 0.62, -height * 0.42, width, height * 0.15, 0.0, height * 0.52)
        gradient = QLinearGradient(0.0, height * 0.55, 0.0, -height * 0.55)
        gradient.setColorAt(0.0, self.tc("leaf", alpha))
        gradient.setColorAt(0.40, self.tc("bud", int(alpha * (0.48 + stage * 0.52))))
        gradient.setColorAt(1.0, self.tc("flower_b", int(alpha * stage)))
        painter.setPen(QPen(self.tc("flower_edge", int(alpha * stage)), max(0.4, scale * 0.58)))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(shape)
        painter.restore()

    @staticmethod
    def petal_shape(length: float, width: float, notch: bool = False) -> QPainterPath:
        path = QPainterPath(QPointF())
        path.cubicTo(-width * 0.20, -length * 0.24, -width * 0.72, -length * 0.72, -width * 0.10, -length)
        if notch:
            path.cubicTo(-width * 0.03, -length * 0.90, width * 0.03, -length * 0.90, width * 0.10, -length)
        path.cubicTo(width * 0.72, -length * 0.72, width * 0.20, -length * 0.24, 0.0, 0.0)
        return path

    def draw_flower(self, painter: QPainter, node: VineNode, scale: float, alpha: int, open_amount: float, index: int):
        scale = max(0.0, scale) * node.scale
        open_amount = self.clamp(open_amount)
        alpha = int(self.clamp(alpha, 0, 255))
        if scale <= 0.02 or alpha <= 0:
            return
        direction = node.angle + node.side * (72.0 + node.bend)
        painter.save()
        painter.translate(node.point)
        painter.rotate(direction)
        stem = node.reach * scale
        painter.setPen(QPen(self.tc("vine", int(alpha * 0.82)), max(0.56, 0.88 * scale)))
        painter.drawLine(QPointF(), QPointF(stem, 0.0))
        painter.translate(stem, 0.0)
        breath_size = 0.0 if self.reduced_motion else (0.012 if self.rest_mode else 0.004)
        breath = 1.0 + breath_size * math.sin(self.rest_wave * 1.7 + node.phase * math.tau)
        painter.scale(breath, breath)
        painter.rotate(90.0 + math.sin(node.phase * math.tau) * 7.0)

        glow_amount = 0.72 if self.profile == "glow" else 0.18
        radius = 22.0 * scale
        radial = QRadialGradient(QPointF(), radius)
        radial.setColorAt(0.0, self.tc("spark", int(alpha * glow_amount * 0.30)))
        radial.setColorAt(1.0, self.tc("spark", 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(radial))
        painter.drawEllipse(QRectF(-radius, -radius, radius * 2.0, radius * 2.0))

        notch = self.profile == "cherry"
        length = (9.0 + 7.0 * open_amount) * scale
        width = (4.0 + 2.7 * open_amount) * scale
        petal = self.petal_shape(length, width, notch)
        gradient = QLinearGradient(0.0, 0.0, 0.0, -length)
        if self.profile == "ivy":
            gradient.setColorAt(0.0, self.tc("flower_a", alpha))
            gradient.setColorAt(0.48, self.tc("flower_b", alpha))
            gradient.setColorAt(1.0, self.tc("flower_b", int(alpha * 0.88)))
        else:
            gradient.setColorAt(0.0, self.tc("flower_a", alpha))
            gradient.setColorAt(1.0, self.tc("flower_b", int(alpha * 0.92)))
        painter.setPen(QPen(self.tc("flower_edge", int(alpha * 0.72)), max(0.38, 0.56 * scale)))
        painter.setBrush(QBrush(gradient))
        base = node.phase * 15.0 + index * 2.0
        for petal_index in range(5):
            painter.save()
            painter.rotate(base + petal_index * 72.0)
            painter.scale(0.70 + 0.30 * open_amount, 1.0)
            painter.drawPath(petal)
            painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.tc("center", alpha)))
        center = 3.2 * scale * (0.65 + 0.35 * open_amount)
        painter.drawEllipse(QRectF(-center, -center, center * 2.0, center * 2.0))
        painter.restore()

    def _draw_wisteria_floret(self, painter: QPainter, scale: float, alpha: int, openness: float, phase: float):
        if openness < 0.18:
            painter.setPen(QPen(self.tc("flower_edge", int(alpha * 0.75)), 0.45))
            painter.setBrush(QBrush(self.tc("bud", alpha)))
            painter.drawEllipse(QRectF(-2.7 * scale, -2.0 * scale, 5.4 * scale, 8.0 * scale))
            return
        petal = self.petal_shape((11.0 + 6.0 * openness) * scale, (5.2 + 2.8 * openness) * scale)
        for petal_index, rotation in enumerate((-48.0, 0.0, 48.0)):
            painter.save()
            painter.rotate(180.0 + rotation + math.sin(phase + petal_index) * 4.0)
            painter.scale(0.70 if petal_index else 0.82, 1.0)
            gradient = QLinearGradient(0.0, 0.0, 0.0, 17.0 * scale)
            gradient.setColorAt(0.0, self.tc("pearl", int(alpha * 0.68)))
            gradient.setColorAt(0.34, self.tc("flower_b", int(alpha * 0.92)))
            gradient.setColorAt(0.72, self.tc("flower_a", alpha))
            gradient.setColorAt(1.0, self.tc("flower_edge", int(alpha * 0.96)))
            painter.setPen(QPen(self.tc("flower_edge", int(alpha * 0.78)), max(0.38, 0.58 * scale)))
            painter.setBrush(QBrush(gradient))
            painter.drawPath(petal)
            painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.tc("pearl", int(alpha * 0.82))))
        painter.drawEllipse(QRectF(-1.7 * scale, -1.2 * scale, 3.4 * scale, 3.4 * scale))

    def draw_wisteria_cluster(self, painter: QPainter, node: VineNode, stage: float, alpha: int, cluster_index: int):
        stage = self.clamp(stage)
        if stage <= 0.01:
            return
        attach_angle = node.angle + node.side * (55.0 + node.bend * 0.4)
        anchor = self.shifted(node.point, attach_angle, node.reach * node.scale)
        connector = QPainterPath(node.point)
        connector.quadTo(self.shifted(node.point, node.angle, node.reach * 0.45), anchor)
        painter.setPen(QPen(self.tc("vine_light", int(alpha * stage * 0.82)), 1.15 * node.scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.shortened_path(connector, stage, 14))

        length = (78.0 + node.variant * 30.0) * node.scale
        width = (22.0 + node.variant * 6.0) * node.scale
        sway_amount = 0.0 if self.reduced_motion else (2.2 if self.rest_mode else 0.65)
        sway = math.sin(self.rest_wave * 0.68 + node.phase * math.tau) * sway_amount
        painter.save()
        painter.translate(anchor)
        painter.rotate(sway)
        aura_radius = (34.0 + node.variant * 8.0) * node.scale
        aura = QRadialGradient(QPointF(0.0, length * 0.30), aura_radius)
        aura.setColorAt(0.0, self.tc("flower_b", int(alpha * stage * 0.09)))
        aura.setColorAt(0.58, self.tc("flower_a", int(alpha * stage * 0.035)))
        aura.setColorAt(1.0, self.tc("spark", 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(aura))
        painter.drawEllipse(QRectF(-aura_radius, length * 0.30 - aura_radius, aura_radius * 2.0, aura_radius * 2.0))
        stem = QPainterPath(QPointF())
        stem.cubicTo(QPointF(width * 0.34, length * 0.26), QPointF(-width * 0.24, length * 0.68), QPointF(0.0, length))
        painter.setPen(QPen(self.tc("tendril", int(alpha * stage * 0.72)), max(0.65, 1.05 * node.scale)))
        painter.drawPath(self.shortened_path(stem, stage, 34))

        base_count = 9 + node.variant * 4
        count = max(5, int(base_count * (0.85 + self.density_value * 0.003)))
        for floret_index in range(count):
            t = (floret_index + 0.55) / count
            if t > stage:
                continue
            point = stem.pointAtPercent(t)
            side = -1 if floret_index % 2 else 1
            lateral = side * width * (0.24 + 0.22 * math.sin(t * math.pi))
            point += QPointF(lateral, 0.0)
            openness = self.clamp((stage - t * 0.58) / 0.42)
            scale = node.scale * (1.00 - 0.42 * t) * (0.90 + 0.12 * math.sin(node.phase * 9.0 + floret_index))
            painter.save()
            painter.translate(point)
            painter.rotate(side * (8.0 + 7.0 * t) + math.sin(node.phase * 6.0 + floret_index) * 5.0)
            self._draw_wisteria_floret(painter, scale, int(alpha * (0.72 + 0.28 * openness)), openness, node.phase * math.tau + floret_index)
            painter.restore()

        if stage > 0.82 and cluster_index in (0, 3):
            for lens_index, t in enumerate((0.24, 0.54)):
                point = stem.pointAtPercent(t)
                radius = (3.8 - lens_index * 0.7) * node.scale
                lens = QRadialGradient(point - QPointF(radius * 0.30, radius * 0.35), radius * 1.7)
                lens.setColorAt(0.0, self.tc("pearl", 188))
                lens.setColorAt(0.42, self.tc("flower_b", 82))
                lens.setColorAt(1.0, self.tc("spark", 0))
                painter.setPen(QPen(self.tc("pearl", 105), 0.45))
                painter.setBrush(QBrush(lens))
                painter.drawEllipse(QRectF(point.x() - radius, point.y() - radius, radius * 2.0, radius * 2.0))
        painter.restore()

    def draw_floating_petals(self, painter: QPainter):
        if self.open_flower_count <= 0 or self.progress < 0.72 or self.profile not in ("cherry", "wisteria"):
            return
        if self.profile == "wisteria":
            positions = ((0.54, 0.15, -24.0), (0.61, 0.23, 18.0), (0.67, 0.32, 52.0))
        else:
            positions = ((0.42, 0.16, 22.0), (0.52, 0.23, -18.0), (0.61, 0.31, 44.0), (0.73, 0.20, 9.0))
        reveal = self.clamp((self.progress - 0.72) / 0.28)
        for index, (x_ratio, y_ratio, rotation) in enumerate(positions):
            phase = index * 1.87 if self.reduced_motion else self.rest_wave * 0.42 + index * 1.87
            drift = 0.0 if self.reduced_motion else 2.8 if self.rest_mode else 1.2
            x = self.width() * x_ratio + math.sin(phase) * drift
            y = self.height() * y_ratio + math.cos(phase * 0.83) * drift
            scale = 0.70 + index * 0.08
            if BotanicalAssets.has_organ_atlas(self.theme_name):
                BotanicalAssets.draw_organ(
                    painter, self.theme_name, "petal", QPointF(x, y),
                    rotation + math.sin(phase) * 5.0,
                    18.0 * scale,
                    opacity=(0.34 + 0.42 * reveal), mirror=index % 2 == 1,
                )
                continue
            petal = self.petal_shape(10.5 * scale, 5.2 * scale, self.profile == "cherry")
            painter.save()
            painter.translate(x, y)
            painter.rotate(rotation + math.sin(phase) * 5.0)
            gradient = QLinearGradient(0.0, 0.0, 0.0, -11.0)
            gradient.setColorAt(0.0, self.tc("flower_a", int(155 * reveal)))
            gradient.setColorAt(1.0, self.tc("flower_b", int(210 * reveal)))
            painter.setPen(QPen(self.tc("flower_edge", int(116 * reveal)), 0.48))
            painter.setBrush(QBrush(gradient))
            painter.drawPath(petal)
            painter.restore()

    def draw_sparkles(self, painter: QPainter, grown_length: float):
        if self.open_flower_count <= 0 or self.progress < 0.68 or self.profile not in ("glow", "wisteria"):
            return
        count = 12 if self.profile == "glow" else 5
        for index in range(count):
            phase = index * 2.39 + 0.7
            side = -1 if index % 2 else 1
            x = 26.0 + (index % 4) * 24.0 if side < 0 else self.width() - 28.0 - (index % 4) * 23.0
            y = 55.0 + ((index * 97) % max(120, self.height() - 110))
            pulse = 0.70 if self.reduced_motion else 0.45 + 0.55 * math.sin(self.rest_wave * 1.25 + phase) ** 2
            radius = (1.3 + (index % 3) * 0.65) * (1.0 + pulse * 0.18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.tc("spark", int((54 if self.profile == "wisteria" else 118) * pulse))))
            painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2.0, radius * 2.0))

    def draw_growing_tip(self, painter: QPainter, grown_length: float):
        if self.rest_mode or grown_length <= 4.0 or grown_length >= self.total_length - 1.0:
            return
        point, angle = self.point_at_distance(grown_length)
        painter.save()
        painter.translate(point)
        painter.rotate(angle)
        painter.setPen(QPen(self.tc("vine_light", 215), 0.9))
        painter.setBrush(QBrush(self.tc("leaf", 220)))
        for rotation, scale in ((-29.0, 0.68), (31.0, 0.52)):
            painter.save()
            painter.rotate(rotation)
            painter.drawPath(self.leaf_shape(2, 18.0 * scale, 6.0 * scale))
            painter.restore()
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        grown_length = self.total_length * self.progress
        # 密度、尺寸与透明度完全解耦：拖动密度只增减器官数量。
        density_scale = 1.0
        rest_breath = 0.0
        if self.rest_mode and not self.reduced_motion:
            rest_breath = math.sin(self.rest_wave * 1.05)
        # 休息时整株以约 ±3% 透明度、±1.8% 尺寸缓慢呼吸；幅度足以被
        # 察觉，又不会像通知动画一样抢占注意力。
        master_opacity = min(
            0.82,
            max(0.08, (self.plant_opacity + self.completion_glow) * (1.0 + 0.075 * rest_breath)),
        )
        # 尺寸滑块拥有可感知但不过度的范围：默认 36% 约为 1.0 倍，
        # 清爽用户可缩小，想接近概念稿时可独立放大到约 1.30 倍。
        presence_scale = (0.70 + self.plant_presence * 0.85) * (1.0 + 0.018 * rest_breath)

        if BotanicalAssets.has_organ_atlas(self.theme_name):
            # 正式模式采用明确的遮挡顺序：侧枝在下、主藤封住接缝、叶花在上。
            # 这能保留 52 个细分器官的质感，又不会暴露透明素材的裁切端面。
            painter.save()
            painter.setOpacity(master_opacity)
            self.draw_segmented_stems(painter, grown_length, presence_scale)
            self.draw_main_vines(painter, grown_length, textured=True)
            self.draw_segmented_foliage(painter, grown_length, density_scale, presence_scale)
            self.draw_asset_growing_tip(painter, grown_length)
            self.draw_terminal_caps(painter, grown_length, presence_scale)
            painter.restore()
            self.draw_floating_petals(painter)
            self.draw_sparkles(painter, grown_length)
            return

        # 高清枝叶是视觉主体。按生长方向裁切资源，而非整张图突然淡入；
        # 三种布局由同一套资产重组，避免混合植物或重复维护多份静态边框。
        painter.save()
        painter.setOpacity(master_opacity)
        asset_placements = BotanicalAssets.draw_growth_layer(
            painter,
            self.theme_name,
            self.layout_name,
            QRectF(self.rect()),
            self.progress,
            self.plant_presence,
        )
        painter.restore()

        # 程序化骨架降为很轻的连接与生长提示层。资产缺失时则自动恢复为
        # 完整 QPainter 绘制，打包遗漏资源也不会导致应用启动失败。
        painter.save()
        painter.setOpacity(master_opacity if not asset_placements else min(0.07, master_opacity * 0.16))
        self.draw_side_branches(painter, grown_length, foliage=False)
        self.draw_main_vines(painter, grown_length)
        self.draw_side_branches(painter, grown_length, foliage=True)
        self.draw_tendrils(painter, grown_length)

        for node in self.leaf_nodes:
            if node.distance > grown_length:
                break
            local = self.clamp((grown_length - node.distance) / 82.0)
            self.draw_leaf(painter, node, (0.22 + 0.78 * local) * density_scale * presence_scale, int(32 + 178 * local))

        if self.progress >= 0.22:
            for node in self.bud_nodes:
                if node.distance > grown_length:
                    break
                local = self.clamp((grown_length - node.distance) / 108.0)
                stage = self.clamp((self.progress - 0.18 - node.phase * 0.09) / 0.50)
                self.draw_bud(painter, node, (0.30 + 0.70 * local) * density_scale, int(42 + 170 * local), stage)

        if self.profile == "wisteria":
            for index, node in enumerate(self.flower_nodes):
                if node.distance > grown_length:
                    continue
                local = self.clamp((grown_length - node.distance) / 150.0)
                reveal = self._flower_reveal_amount(node)
                if reveal > 0.001:
                    self.draw_wisteria_cluster(
                        painter, node, min(local, reveal), int(58 + 168 * local), index
                    )
        elif self.progress >= 0.34:
            for index, node in enumerate(self.flower_nodes):
                if node.distance > grown_length:
                    break
                local = self.clamp((grown_length - node.distance) / 128.0)
                reveal = self._flower_reveal_amount(node)
                if reveal > 0.001:
                    self.draw_flower(
                        painter,
                        node,
                        (0.46 + 0.54 * min(local, reveal)) * density_scale * presence_scale,
                        int(55 + 164 * local),
                        min(local, reveal),
                        index,
                    )

        self.draw_growing_tip(painter, grown_length)
        painter.restore()

        # 兼容旧版整株资产时，桌面花期同样驱动自然开花；休息呼吸由独立低频计时器刷新。
        painter.save()
        painter.setOpacity(master_opacity)
        pulse = 0.0 if self.reduced_motion else self.rest_wave * 1.25
        BotanicalAssets.draw_open_flowers(
            painter,
            self.theme_name,
            asset_placements,
            self.open_flower_count,
            pulse,
            progress=self.progress,
        )
        painter.restore()

        self.draw_floating_petals(painter)
        self.draw_sparkles(painter, grown_length)
