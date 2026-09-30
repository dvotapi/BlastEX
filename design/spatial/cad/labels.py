"""Отметка точки из подписи рядом с ней.

Маркшейдер часто ставит точку или условный знак с Z = 0, а отметку пишет
текстом рядом. Такой точке достаётся ближайшая числовая подпись в радиусе
(по умолчанию 3 м), подпись своего слоя важнее чужой. Каждая подпись
достаётся одной точке. Числа без точки поверхностью не становятся: номер
блока или пикета рядом с линией — не отметка.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from design.spatial.cad.model import CadEntity, ZERO_Z_TOLERANCE_M

# Отметка: знак «+» или дробная часть обязательны — «66» это номер блока.
_ELEVATION = re.compile(r"^\s*([+-])?\s*(\d{1,5})(?:[.,](\d{1,3}))?\s*$")


def parse_elevation(text: str) -> float | None:
    match = _ELEVATION.match(text or "")
    if not match:
        return None
    sign, whole, fraction = match.groups()
    if fraction is None and sign != "+":
        return None
    value = float(f"{whole}.{fraction or 0}")
    return -value if sign == "-" else value


def attach_labels(entities: list[CadEntity], radius_m: float) -> None:
    """Проставляет Z из подписей точкам и знакам без отметки (на месте)."""

    # Знак, получивший отметку из собственного атрибута, в подбор не входит.
    candidates = [
        item
        for item in entities
        if item.geometry_type == "point" and not (item.z_from_label and not item.label_handle)
    ]
    # Повторный вызов (другой радиус) начинает с чистого листа.
    for item in candidates:
        if item.label_handle:
            x, y, _ = item.points[0]
            item.points = [(x, y, 0.0)]
            item.z_from_label = False
            item.label_handle = ""
    points = [item for item in candidates if abs(item.points[0][2]) <= ZERO_Z_TOLERANCE_M]

    labels: list[tuple[CadEntity, float]] = []
    for item in entities:
        if item.geometry_type == "text":
            value = parse_elevation(item.text)
            if value is not None:
                labels.append((item, value))
    if not points or not labels or radius_m <= 0:
        return

    cell = radius_m
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (label, _) in enumerate(labels):
        x, y, _ = label.points[0]
        grid[(math.floor(x / cell), math.floor(y / cell))].append(index)

    pairs: list[tuple[int, float, int, int]] = []
    for point_index, point in enumerate(points):
        x, y, _ = point.points[0]
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for label_index in grid.get((cx + dx, cy + dy), ()):
                    label = labels[label_index][0]
                    distance = math.dist((x, y), label.points[0][:2])
                    if distance <= radius_m:
                        foreign = 0 if label.layer == point.layer else 1
                        pairs.append((foreign, distance, point_index, label_index))

    pairs.sort()
    used_points: set[int] = set()
    used_labels: set[int] = set()
    for _, _, point_index, label_index in pairs:
        if point_index in used_points or label_index in used_labels:
            continue
        used_points.add(point_index)
        used_labels.add(label_index)
        point = points[point_index]
        label, value = labels[label_index]
        x, y, _ = point.points[0]
        point.points = [(x, y, value)]
        point.z_from_label = True
        point.label_handle = label.handle
