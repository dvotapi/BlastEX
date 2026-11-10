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
from design.pattern import face_row_numbering_xy

# Соседи для направления рядов: не дальше этой доли от ближайшего расстояния.
_NEIGHBOUR_SPREAD = 1.5


def _lattice_azimuth(holes: list[Hole], contour: BlockContour) -> float:
    """Азимут рядов по самим скважинам — когда в параметрах сетки его нет.

    Направления на ближайших соседей основной сетки (по модулю 180°) дают
    два преобладающих направления решётки; ряды — то, что ближе к бровке
    (ряды идут вдоль неё). Нет бровки — самое частое направление.
    """

    points = np.array(
        [(h.collar.x, h.collar.y) for h in holes if row_family(h.kind) == "grid" and h.kind != FACE_TOE_KIND and h.source != "manual"],
        dtype=float,
    )
    if len(points) < 3:
        return 0.0
    distances, indices = cKDTree(points).query(points, k=min(5, len(points)))
    nearest = float(np.min(distances[:, 1]))
    votes: Counter[int] = Counter()
    for row, (dist_row, index_row) in enumerate(zip(distances, indices)):
        for distance, other in zip(dist_row[1:], index_row[1:]):
            if distance > nearest * _NEIGHBOUR_SPREAD:
                continue
            dx, dy = points[other] - points[row]
            votes[round(math.degrees(math.atan2(dx, dy)) % 180.0) % 180] += 1
    peaks: list[int] = []
    for angle, _count in votes.most_common():
        if all(min(abs(angle - p), 180 - abs(angle - p)) >= 20 for p in peaks):
            peaks.append(angle)
        if len(peaks) == 2:
            break
    crest = crest_azimuth_deg(contour)
    if crest is None or len(peaks) < 2:
        return float(peaks[0]) if peaks else 0.0
    return float(min(peaks, key=lambda p: min(abs(p - crest), 180 - abs(p - crest))))


def renumber_map(holes: list[Hole], contour: BlockContour, pattern_params: Mapping[str, Any]) -> dict[str, str]:
    """Старый номер → новый — только у скважин, номер которых меняется.

    Ручные скважины номер не меняют и в привязку ряда у бровки не входят;
    пара у откоса — номер своей вертикальной с «T» (вертикальная — по
    прежнему номеру пары без «T»). Нет `row_azimuth_deg` в параметрах —
    азимут рядов по самим скважинам (`_lattice_azimuth`).
    """

    params = pattern_params or {}
    if "row_azimuth_deg" in params:
        row_azimuth = float(params["row_azimuth_deg"])
    else:
        row_azimuth = _lattice_azimuth(holes, contour)
    row_dir, advance_dir = local_basis(row_azimuth)
    _origin, deep_dir = pattern_origin(contour, row_dir, advance_dir)
    # Как у генератора: столбцы — по построенным скважинам, без ручных.
    face_row = face_row_numbering_xy([h for h in holes if h.source != "manual"], row_dir, {})
    positions = [face_row.get(id(hole)) for hole in holes] if face_row else None
    numbered = number_by_position(holes, row_azimuth_deg=row_azimuth, positions=positions, deep_dir=deep_dir)
    return {old.id: new.id for old, new in zip(holes, numbered) if old.id != new.id}
