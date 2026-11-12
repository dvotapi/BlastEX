"""Общий генератор плана: паспорт на бурение (стр. 4, TASK-015 PR 3) и
графика проекта МВ (Г.1, Г.3, Г.4, TASK-018 PR 4).

Чистые функции раскладки и векторные элементы листа: точки снимка,
вид плана (масштаб, поворот, центр — `PlanView`), выбор масштаба (кратный
10 у паспорта, ряд масштабов у проекта МВ), линейка, стрелка «С». Паспорт
вызывает их с прежними параметрами — его PDF не меняется ни на байт (тест
хэшем в `tests/test_mass_blast_render_graphics.py`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from reportlab.graphics.shapes import Group, Polygon, Rect, String
from reportlab.graphics.shapes import Line as LineShape
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from scipy.spatial import cKDTree

GRAPHITE = HexColor("#2E3237")
MM_TO_PT = 72 / 25.4
BAR_STEPS_M = (5, 10, 20, 50, 100, 200, 500, 1000)
BAR_TARGET_MM = 40.0
# Ряд масштабов листов проекта МВ (TASK-018 §4) и масштаб, до которого план
# печатается «север вверх» (крупнее — поворот, если без него мельче).
SCALE_SERIES = (200, 250, 500, 1000, 2000, 5000)
ROTATE_FROM_SCALE = 500
ROTATION_STEP_DEG = 1.0

XY = tuple[float, float]
Line = tuple[XY, ...]


def point(value: Any) -> XY | None:
    """Точка снимка; без чисел или с NaN — None (такая точка не рисуется)."""

    if isinstance(value, Mapping):
        x, y = value.get("x"), value.get("y")
    elif isinstance(value, Sequence) and not isinstance(value, str) and len(value) >= 2:
        x, y = value[0], value[1]
    else:
        return None
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError):
        return None
    return (fx, fy) if math.isfinite(fx) and math.isfinite(fy) else None


def line(points: Iterable[Any]) -> list[XY]:
    return [p for p in (point(item) for item in points) if p is not None]


def bar(scale: int, steps: Sequence[int] = BAR_STEPS_M, target_mm: float = BAR_TARGET_MM) -> tuple[int, float]:
    """Длина линейки: шаг из ряда, ближайший к `target_mm` на бумаге; (метры, мм)."""

    def length(step: int) -> float:
        return step * 1000 / scale

    step = min(steps, key=lambda item: abs(length(item) - target_mm))
    return step, length(step)


def label_pt(points: list[XY], share: float, sizes: tuple[float, float]) -> float:
    """Кегль подписи — доля расстояния до ближайшей скважины на листе (мм → pt)."""

    if len(points) < 2:
        return sizes[1]
    distances, _ = cKDTree(points).query(points, k=2)
    size = share * float(np.median(distances[:, 1])) * MM_TO_PT
    return min(sizes[1], max(sizes[0], size))


def scale_multiple_of_10(width_m: float, height_m: float, usable_w: float, usable_h: float, minimum: int) -> int:
    """Знаменатель масштаба, кратный 10, при котором блок помещается (паспорт на бурение)."""

    need = max(width_m / usable_w, height_m / usable_h) * 1000
    # Округление на 1e-9 — чтобы ровно 663,0 не стало 670 из-за погрешности.
    return max(minimum, math.ceil(need / 10 - 1e-9) * 10)


@dataclass(frozen=True)
class PlanView:
    """Перевод координат объекта в миллиметры поля листа.

    Поворот — на `angle_deg` против часовой вокруг (`cx`, `cy`); центр
    повёрнутой рамки (`cu`, `cv`) встаёт в (`ox`, `oy`) поля. Без поворота
    формула та же, что у плана паспорта на бурение.
    """

    scale: int
    angle_deg: float
    cx: float
    cy: float
    ox: float
    oy: float
    cu: float = 0.0
    cv: float = 0.0

    @property
    def k(self) -> float:
        return 1000 / self.scale

    def rotated(self, p: XY) -> XY:
        dx, dy = p[0] - self.cx, p[1] - self.cy
        if not self.angle_deg:
            return dx, dy
        angle = math.radians(self.angle_deg)
        c, s = math.cos(angle), math.sin(angle)
        return dx * c - dy * s, dx * s + dy * c

    def xy(self, p: XY) -> XY:
        u, v = self.rotated(p)
        if self.angle_deg:
            u, v = u - self.cu, v - self.cv
        k = self.k
        return (self.ox + u * k, self.oy + v * k)

    def line(self, points: Iterable[XY]) -> Line:
        return tuple(self.xy(p) for p in points)

    @property
    def north(self) -> XY:
        """Направление на север на листе (единичный вектор)."""

        angle = math.radians(self.angle_deg)
        return (-math.sin(angle), math.cos(angle))


def _extent(points: np.ndarray, angle_deg: float) -> tuple[float, float, float, float]:
    angle = math.radians(angle_deg)
    c, s = math.cos(angle), math.sin(angle)
    u = points[:, 0] * c - points[:, 1] * s
    v = points[:, 0] * s + points[:, 1] * c
    return float(u.min()), float(u.max()), float(v.min()), float(v.max())


def fit_view(
    points: Sequence[XY],
    field_w: float,
    field_h: float,
    *,
    pad_mm: float,
    series: Sequence[int] = SCALE_SERIES,
    rotate_from: int | None = ROTATE_FROM_SCALE,
) -> PlanView:
    """Масштаб из ряда и поворот (TASK-018 §4).

    Самый крупный масштаб ряда, при котором блок помещается «север вверх»;
    если «север вверх» требует мельче `rotate_from` — поворот (0…179° шагом
    1°, угол с наибольшим запасом) в `rotate_from`; не помещается ни при каком
    угле — следующий масштаб ряда (сначала «север вверх», потом поворот).
    Не помещается и в самом мелком — самый мелкий с лучшим углом.
    """

    data = np.array([p for p in points], dtype=float).reshape(-1, 2)
    if not len(data):
        return PlanView(scale=series[0], angle_deg=0.0, cx=0.0, cy=0.0, ox=field_w / 2, oy=field_h / 2)
    x0, y0 = data.min(axis=0)
    x1, y1 = data.max(axis=0)
    cx, cy = (float(x0) + float(x1)) / 2, (float(y0) + float(y1)) / 2
    local = data - (cx, cy)
    usable_w, usable_h = field_w - 2 * pad_mm, field_h - 2 * pad_mm

    def need(angle: float) -> float:
        u0, u1, v0, v1 = _extent(local, angle)
        return max((u1 - u0) / usable_w, (v1 - v0) / usable_h) * 1000

    north = need(0.0)
    best = None

    def best_angle() -> float:
        nonlocal best
        if best is None:
            angles = np.arange(0.0, 180.0, ROTATION_STEP_DEG)
            best = float(min(angles, key=lambda angle: (round(need(float(angle)), 6), float(angle))))
        return best

    def view(scale: int, angle: float) -> PlanView:
        if not angle:
            return PlanView(scale=scale, angle_deg=0.0, cx=cx, cy=cy, ox=field_w / 2, oy=field_h / 2)
        u0, u1, v0, v1 = _extent(local, angle)
        return PlanView(scale=scale, angle_deg=angle, cx=cx, cy=cy, ox=field_w / 2, oy=field_h / 2,
                        cu=(u0 + u1) / 2, cv=(v0 + v1) / 2)

    eps = 1e-9
    for scale in series:
        if rotate_from is not None and scale > rotate_from:
            break
        if north <= scale + eps:
            return view(scale, 0.0)
    for scale in series:
        if rotate_from is not None and scale < rotate_from:
            continue
        if north <= scale + eps:
            return view(scale, 0.0)
        if rotate_from is not None and need(best_angle()) <= scale + eps:
            return view(scale, best_angle())
    return view(series[-1], best_angle() if rotate_from is not None else 0.0)


# --------------------------------------------------------------- элементы листа

def north_arrow(x: float, y: float, font: str) -> Group:
    """Стрелка «С» с вершиной в (x, y), pt (север вверх, план паспорта)."""

    w, h = 4 * mm, 9 * mm
    group = Group(
        Polygon([x, y, x - w, y - h * 0.55, x - w * 0.35, y - h * 0.55, x - w * 0.35, y - h,
                 x + w * 0.35, y - h, x + w * 0.35, y - h * 0.55, x + w, y - h * 0.55],
                fillColor=white, strokeColor=GRAPHITE, strokeWidth=0.6),
    )
    group.add(String(x, y - h - 4 * mm, "С", fontName=font, fontSize=10, fillColor=GRAPHITE, textAnchor="middle"))
    return group


def north_arrow_turned(cx: float, cy: float, north: XY, font: str, length: float = 9 * mm) -> Group:
    """Стрелка «С» по фактическому направлению на север, с центром в (cx, cy), pt."""

    nx, ny = north
    px, py = -ny, nx
    tip = (cx + nx * length / 2, cy + ny * length / 2)
    tail = (cx - nx * length / 2, cy - ny * length / 2)
    head = 0.45 * length
    w = 1.6 * mm
    base = (tip[0] - nx * head, tip[1] - ny * head)
    group = Group()
    group.add(Polygon([tip[0], tip[1], base[0] + px * w, base[1] + py * w, base[0] - px * w, base[1] - py * w],
                      fillColor=GRAPHITE, strokeColor=GRAPHITE, strokeWidth=0.4))
    group.add(LineShape(tail[0], tail[1], base[0], base[1], strokeColor=GRAPHITE, strokeWidth=1.0))
    label = (tip[0] + nx * 3.0 * mm, tip[1] + ny * 3.0 * mm - 3.3)
    group.add(String(label[0], label[1], "С", fontName=font, fontSize=10, fillColor=GRAPHITE, textAnchor="middle"))
    return group


def _bar_text(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value).replace(".", ",")


def scale_bar(bar_m: int, bar_mm: float, x: float, y: float, font: str) -> Group:
    """Линейка в две половины с подписями 0, середина, длина (pt)."""

    group = Group()
    length = bar_mm * mm
    half = length / 2
    for index, fill in enumerate((GRAPHITE, white)):
        group.add(Rect(x + index * half, y, half, 1.4 * mm, fillColor=fill, strokeColor=GRAPHITE, strokeWidth=0.4))
    for offset, text in ((0, "0"), (half, _bar_text(bar_m / 2)), (length, f"{bar_m} м")):
        group.add(String(x + offset, y + 2.2 * mm, text, fontName=font, fontSize=6.5, fillColor=GRAPHITE,
                         textAnchor="middle"))
    return group


__all__ = [
    "BAR_STEPS_M",
    "PlanView",
    "ROTATE_FROM_SCALE",
    "SCALE_SERIES",
    "bar",
    "fit_view",
    "label_pt",
    "line",
    "north_arrow",
    "north_arrow_turned",
    "point",
    "scale_bar",
    "scale_multiple_of_10",
]
