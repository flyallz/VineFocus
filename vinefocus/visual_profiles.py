"""花藤主题的构图规格。

集中维护四套植物的器官比例，以及静谧单株、侧边攀援、环屏生长三类路径。
本模块只生成 QPainterPath，不创建窗口，也不决定计时和开花业务。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath


PROFILE_METRICS: Dict[str, dict] = {
    "ivy": {
        "base_width": 2.5,
        "leaf_spacing": 88.0,
        "branch_spacing": 280.0,
        "bud_spacing": 310.0,
        "flower_spacing": 420.0,
        "leaf_scale": 0.82,
    },
    "cherry": {
        "base_width": 2.8,
        "leaf_spacing": 108.0,
        "branch_spacing": 250.0,
        "bud_spacing": 230.0,
        "flower_spacing": 285.0,
        "leaf_scale": 0.70,
    },
    "wisteria": {
        "base_width": 2.6,
        "leaf_spacing": 108.0,
        "branch_spacing": 300.0,
        "bud_spacing": 330.0,
        "flower_spacing": 9999.0,
        "leaf_scale": 0.76,
    },
    "glow": {
        "base_width": 2.2,
        "leaf_spacing": 102.0,
        "branch_spacing": 310.0,
        "bud_spacing": 345.0,
        "flower_spacing": 450.0,
        "leaf_scale": 0.74,
    },
}


def _curve(
    start: QPointF,
    segments: List[Tuple[QPointF, QPointF, QPointF]],
) -> QPainterPath:
    path = QPainterPath(start)
    for control_a, control_b, end in segments:
        path.cubicTo(control_a, control_b, end)
    return path


def _quiet_single(profile: str, w: float, h: float) -> List[Tuple[QPainterPath, str]]:
    """只在一个角落留下短小植株，是默认、最安静的桌面模式。"""
    if profile == "cherry":
        return [
            (
                _curve(
                    QPointF(-14.0, h * 0.20),
                    [
                        (QPointF(w * 0.035, h * 0.18), QPointF(w * 0.075, h * 0.10), QPointF(w * 0.125, h * 0.075)),
                        (QPointF(w * 0.165, h * 0.055), QPointF(w * 0.19, h * 0.085), QPointF(w * 0.225, h * 0.055)),
                    ],
                ),
                "wood",
            )
        ]
    if profile == "wisteria":
        return [
            (
                _curve(
                    QPointF(w + 12.0, h * 0.16),
                    [
                        (QPointF(w * 0.965, h * 0.14), QPointF(w * 0.955, h * 0.055), QPointF(w * 0.91, h * 0.07)),
                        (QPointF(w * 0.87, h * 0.085), QPointF(w * 0.865, h * 0.035), QPointF(w * 0.82, h * 0.055)),
                    ],
                ),
                "silk",
            )
        ]
    material = "luminous" if profile == "glow" else "green"
    return [
        (
            _curve(
                QPointF(-12.0, h - 18.0),
                [
                    (QPointF(w * 0.045, h * 0.93), QPointF(w * 0.04, h * 0.83), QPointF(w * 0.085, h * 0.79)),
                    (QPointF(w * 0.12, h * 0.75), QPointF(w * 0.095, h * 0.67), QPointF(w * 0.145, h * 0.62)),
                ],
            ),
            material,
        )
    ]


def _side_climb(profile: str, w: float, h: float) -> List[Tuple[QPainterPath, str]]:
    """沿固定宽度的屏幕边缘攀援；超宽屏也不会向内容区漂移。"""
    # Qt 坐标已经是逻辑像素。主藤只在约 16~72 px 的安全带内摆动，
    # 枝叶可以继续向内舒展，从而兼顾“贴边”和可见性。
    edge = min(56.0, max(40.0, w * 0.024))
    inner = edge + 16.0
    if profile == "wisteria":
        return [
            (
                _curve(
                    QPointF(w + 12.0, h * 0.82),
                    [
                        (QPointF(w - edge, h * 0.75), QPointF(w - 18.0, h * 0.61), QPointF(w - edge, h * 0.51)),
                        (QPointF(w - inner, h * 0.41), QPointF(w - 25.0, h * 0.28), QPointF(w - edge - 4.0, h * 0.18)),
                        (QPointF(w - inner, h * 0.11), QPointF(w - 28.0, h * 0.05), QPointF(w - edge, 14.0)),
                    ],
                ),
                "silk",
            )
        ]
    material = "wood" if profile == "cherry" else "luminous" if profile == "glow" else "green"
    return [
        (
            _curve(
                QPointF(-14.0, h * 0.92),
                [
                    (QPointF(edge, h * 0.84), QPointF(17.0, h * 0.69), QPointF(edge, h * 0.58)),
                    (QPointF(inner, h * 0.48), QPointF(24.0, h * 0.35), QPointF(edge + 4.0, h * 0.24)),
                    (QPointF(inner, h * 0.16), QPointF(26.0, h * 0.08), QPointF(edge, 14.0)),
                ],
            ),
            material,
        )
    ]


def _perimeter(profile: str, w: float, h: float) -> List[Tuple[QPainterPath, str]]:
    """带断点的环屏路径；保留产品原始特色，但不形成厚重相框。"""
    material = {
        "cherry": "wood",
        "wisteria": "silk",
        "glow": "luminous",
    }.get(profile, "green")

    top_left = _curve(
        QPointF(-14.0, h * 0.16),
        [
            (QPointF(w * 0.05, h * 0.12), QPointF(w * 0.07, 18.0), QPointF(w * 0.19, 28.0)),
            (QPointF(w * 0.28, 42.0), QPointF(w * 0.34, 10.0), QPointF(w * 0.43, 24.0)),
        ],
    )
    top_right = _curve(
        QPointF(w + 14.0, h * 0.15),
        [(QPointF(w * 0.95, 24.0), QPointF(w * 0.86, 44.0), QPointF(w * 0.74, 24.0))],
    )
    bottom_left = _curve(
        QPointF(-14.0, h * 0.88),
        [(QPointF(w * 0.09, h * 0.95), QPointF(w * 0.20, h - 13.0), QPointF(w * 0.32, h - 26.0))],
    )
    bottom_right = _curve(
        QPointF(w + 14.0, h * 0.88),
        [(QPointF(w * 0.94, h * 0.94), QPointF(w * 0.84, h - 14.0), QPointF(w * 0.72, h - 27.0))],
    )

    if profile == "wisteria":
        # 紫藤使用不对称的长短手势，避免四角镜像与直杆式花序。
        top_left = _curve(
            QPointF(-18.0, h * 0.24),
            [
                (QPointF(w * 0.04, h * 0.15), QPointF(w * 0.09, 20.0), QPointF(w * 0.20, 34.0)),
                (QPointF(w * 0.31, 56.0), QPointF(w * 0.37, 8.0), QPointF(w * 0.48, 25.0)),
            ],
        )
        top_right = _curve(
            QPointF(w + 15.0, h * 0.17),
            [(QPointF(w * 0.93, h * 0.10), QPointF(w * 0.86, 44.0), QPointF(w * 0.77, 26.0))],
        )

    return [(top_left, material), (top_right, material), (bottom_left, material), (bottom_right, material)]


def composition_paths(
    profile: str,
    width: float,
    height: float,
    layout: str = "静谧单株",
) -> List[Tuple[QPainterPath, str]]:
    """按窗口尺寸、植物主题和布局生成开放式攀附路径。"""
    w, h = max(800.0, width), max(500.0, height)
    if layout == "环屏生长":
        return _perimeter(profile, w, h)
    if layout == "侧边攀援":
        return _side_climb(profile, w, h)
    return _quiet_single(profile, w, h)
