"""Перенумерация скважин сохранённого проекта по правилу эшелонов.

Номера присваивает генератор сетки (`pattern._finish_pattern`). Проект,
построенный до нумерации по эшелонам (PR #167, 09.11.2026), хранит прежние
номера по рядам; перестраивать его сетку ради номеров не нужно (ручные правки
пропали бы). `renumber_map` повторяет генератор на готовых скважинах: то же
направление вглубь (`pattern_origin`), тот же ряд вдоль бровки на линии
ближайшего столбца (`pattern.face_row_numbering_xy`), та же
`numbering.number_by_position`. Скважины не двигаются — меняются только номера.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping

import numpy as np
from scipy.spatial import cKDTree

from design.geometry import crest_azimuth_deg, local_basis, pattern_origin
from design.models import FACE_TOE_KIND, BlockContour, Hole, row_family
from design.numbering import number_by_position
from design.pattern import face_row_numbering_xy, uses_back_layout

class RenumberConflict(ValueError):
    """Новые номера совпали бы у разных скважин (например, пара у откоса без
    своей вертикальной сохраняет номер, который правило отдаёт другой паре)."""


# Соседи для направления рядов: не дальше этой доли от ближайшего расстояния.
_NEIGHBOUR_SPREAD = 1.5


def _axial_gap(a: float, b: float) -> float:
    """Угол между двумя направлениями по модулю 180°."""
    gap = abs(a - b) % 180.0
    return min(gap, 180.0 - gap)


def _axial_mean(angles: list[float]) -> float:
    """Среднее направление по модулю 180° (через удвоенные углы)."""
    doubled = np.radians(np.asarray(angles, dtype=float) * 2.0)
    return float(math.degrees(math.atan2(np.sin(doubled).sum(), np.cos(doubled).sum())) / 2.0) % 180.0


def _lattice_azimuth(holes: list[Hole], contour: BlockContour) -> float:
    """Азимут рядов по самим скважинам — когда в параметрах сетки его нет.

    Направления решётки: на ближайших соседей основной сетки (по модулю 180°)
    и, у каждой скважины, на ближайшую соседку не по первому направлению —
    иначе у прямоугольной сетки с шагом вдоль ряда больше 1,5 ЛСП ряды не
    видны. Градусные корзины только находят направление, само оно — среднее
    точных углов (округление до градуса сдвинуло бы эшелон на 10 м на 7 см
    при допуске 5 см). Ряды — направление, ближайшее к бровке; нет бровки —
    самое частое.
    """

    points = np.array(
        [(h.collar.x, h.collar.y) for h in holes if row_family(h.kind) == "grid" and h.kind != FACE_TOE_KIND and h.source != "manual"],
        dtype=float,
    )
    if len(points) < 3:
        return 0.0
    distances, indices = cKDTree(points).query(points, k=min(9, len(points)))

    def angle(row: int, other: int) -> float:
        dx, dy = points[other] - points[row]
        return math.degrees(math.atan2(dx, dy)) % 180.0

    def peaks(angles: list[float]) -> list[tuple[float, int]]:
        """Направления (точные) и число голосов, по убыванию голосов, не ближе 20°."""
        bins = Counter(round(value) % 180 for value in angles)
        found: list[tuple[float, int]] = []
        for centre, _count in bins.most_common():
            if all(_axial_gap(centre, other) >= 20.0 for other, _ in found):
                near = [value for value in angles if _axial_gap(value, centre) <= 2.0]
                found.append((_axial_mean(near), len(near)))
        return found

    nearest = float(np.min(distances[:, 1]))
    close = [
        angle(row, other)
        for row in range(len(points))
        for distance, other in zip(distances[row, 1:], indices[row, 1:])
        if distance <= nearest * _NEIGHBOUR_SPREAD
    ]
    found = peaks(close)
    if not found:
        return 0.0
    first = found[0][0]
    # Второе направление решётки: у каждой скважины ближайшая соседка не по первому.
    second = []
    for row in range(len(points)):
        for other in indices[row, 1:]:
            value = angle(row, int(other))
            if _axial_gap(value, first) >= 20.0:
                second.append(value)
                break
    candidates = [direction for direction, count in found if count * 2 >= found[0][1]]
    candidates += [direction for direction, _ in peaks(second)[:1]]
    crest = crest_azimuth_deg(contour)
    if crest is None:
        return first
    return min(candidates, key=lambda direction: _axial_gap(direction, crest))


def renumber_map(holes: list[Hole], contour: BlockContour, pattern_params: Mapping[str, Any]) -> dict[str, str]:
    """Старый номер → новый — только у скважин, номер которых меняется.

    Ручные скважины номер не меняют и в привязку ряда у бровки не входят;
    пара у откоса — номер своей вертикальной с «T» (вертикальная — по
    прежнему номеру пары без «T»). Нет `row_azimuth_deg` в параметрах —
    азимут рядов по самим скважинам (`_lattice_azimuth`). Номер достался бы
    двум скважинам — `RenumberConflict`.
    """

    params = pattern_params or {}
    if "row_azimuth_deg" in params:
        row_azimuth = float(params["row_azimuth_deg"])
    else:
        row_azimuth = _lattice_azimuth(holes, contour)
    row_dir, advance_dir = local_basis(row_azimuth)
    _origin, deep_dir = pattern_origin(contour, row_dir, advance_dir)
    # Как у генератора: ряд вдоль бровки привязывается к столбцам, только когда
    # он построен («Первый ряд вдоль бровки», свободная поверхность есть, сетка
    # не «от тыла»); столбцы — по построенным скважинам, без ручных.
    face_row = (
        face_row_numbering_xy([h for h in holes if h.source != "manual"], row_dir, {})
        if params.get("first_row_follow_face") and contour.free_faces and not uses_back_layout(contour, params)
        else {}
    )
    positions = [face_row.get(id(hole)) for hole in holes] if face_row else None
    numbered = number_by_position(holes, row_azimuth_deg=row_azimuth, positions=positions, deep_dir=deep_dir)
    repeated = sorted(hole_id for hole_id, count in Counter(h.id for h in numbered).items() if count > 1)
    if repeated:
        raise RenumberConflict(
            "После перенумерации номер достался бы двум скважинам: "
            + ", ".join(repeated)
            + ". Обычно это наклонная у откоса («…T») без своей вертикальной — удалите её или верните вертикальную."
        )
    return {old.id: new.id for old, new in zip(holes, numbered) if old.id != new.id}
