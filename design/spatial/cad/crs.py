"""Проверка системы координат чертежа по экстенту (TASK-013, PR 4).

СК объекта (например, «МСК-66 зона 1», высоты «Балтийская 1977») задаётся
один раз; следующие файлы её наследуют. Координаты не пересчитываются —
преобразований между СК нет. Проверяется только одно: лежит ли новый файл
рядом с прежними чертежами объекта. Дальше 5 км — другая система или
условные координаты, и инженер видит предупреждение.

Экстент для проверки — устойчивый: случайный объект у начала координат в
файле МСК (известная проблема PR 1) не должен давать ложной тревоги.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np

from design.spatial.cad.model import CadEntity

Extent = tuple[float, float, float, float]

# Дальше этого от прежних чертежей объекта — предупреждение о СК (§2).
CRS_FAR_M = 5000.0
# Процентили экстента: отбрасывают одиночные выбросы вроде точки в (0; 0).
ROBUST_PERCENTILE = 1.0
# Меньше вершин — процентили бессмысленны, берётся обычный габарит.
ROBUST_MIN_POINTS = 20


def robust_extent(points: np.ndarray) -> Extent | None:
    """Габарит без выбросов: процентили 1–99 % по X и Y (от 20 вершин)."""

    xy = np.asarray(points, dtype=float).reshape(-1, 2)
    if not len(xy):
        return None
    if len(xy) < ROBUST_MIN_POINTS:
        low, high = xy.min(axis=0), xy.max(axis=0)
    else:
        low = np.percentile(xy, ROBUST_PERCENTILE, axis=0)
        high = np.percentile(xy, 100.0 - ROBUST_PERCENTILE, axis=0)
    return (float(low[0]), float(low[1]), float(high[0]), float(high[1]))


def robust_extent_of(entities: Iterable[CadEntity]) -> Extent | None:
    """Устойчивый габарит всех вершин чертежа."""

    coords = [(point[0], point[1]) for entity in entities for point in entity.points]
    return robust_extent(np.array(coords, dtype=float)) if coords else None


def extent_distance_m(a: Sequence[float], b: Sequence[float]) -> float:
    """Расстояние между прямоугольниками в плане; 0, если они пересекаются."""

    dx = max(0.0, float(b[0]) - float(a[2]), float(a[0]) - float(b[2]))
    dy = max(0.0, float(b[1]) - float(a[3]), float(a[1]) - float(b[3]))
    return math.hypot(dx, dy)


def far_from_site(extent: Sequence[float] | None, site_extents: Iterable[Sequence[float] | None]) -> float | None:
    """Расстояние до ближайшего прежнего чертежа, если все дальше 5 км.

    Первый файл объекта (прежних экстентов нет) и файл без экстента не
    проверяются — ответ None.
    """

    if extent is None:
        return None
    distances = [extent_distance_m(extent, other) for other in site_extents if other is not None]
    if not distances:
        return None
    nearest = min(distances)
    return nearest if nearest > CRS_FAR_M else None
