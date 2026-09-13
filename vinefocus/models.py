"""跨模块数据模型。

目前定义花藤节点数据，供路径生成与 QPainter 绘制共同使用。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF

@dataclass
class VineNode:
    point: QPointF
    distance: float
    angle: float
    side: int
    scale: float = 1.0
    variant: int = 0
    phase: float = 0.0
    reach: float = 0.0
    bend: float = 0.0
    # 花位仍按路径距离排序以保证生长裁切稳定；解锁顺序单独记录，避免
    # 环屏构图的前几次开花全部挤在第一段路径。
    unlock_rank: int = 0


# =========================
# 通用小组件
# =========================
