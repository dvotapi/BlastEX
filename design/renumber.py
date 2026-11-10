"""Перенумерация скважин сохранённого проекта по правилу эшелонов.

Номера присваивает генератор сетки (`pattern._finish_pattern`). Проект,
построенный до нумерации по эшелонам (PR #167, 09.11.2026), хранит прежние
номера по рядам; перестраивать его сетку ради номеров не нужно (ручные правки
пропали бы). `renumber_map` повторяет генератор на готовых скважинах: то же
направление вглубь (`pattern_origin`), тот же ряд вдоль бровки на линии
ближайшего столбца (`pattern._face_row_numbering_xy`), та же
`numbering.number_by_position`. Скважины не двигаются — меняются только номера.
"""
from __future__ import annotations

from typing import Any, Mapping

from design.geometry import local_basis, pattern_origin
from design.models import BlockContour, Hole
from design.numbering import number_by_position
from design.pattern import _face_row_numbering_xy


def renumber_map(holes: list[Hole], contour: BlockContour, pattern_params: Mapping[str, Any]) -> dict[str, str]:
    """Старый номер → новый — только у скважин, номер которых меняется.

    Ручные скважины номер не меняют; пара у откоса — номер своей вертикальной
    с «T» (вертикальная — по прежнему номеру пары без «T»).
    """

    row_azimuth = float((pattern_params or {}).get("row_azimuth_deg", 0.0))
    row_dir, advance_dir = local_basis(row_azimuth)
    _origin, deep_dir = pattern_origin(contour, row_dir, advance_dir)
    face_row = _face_row_numbering_xy(holes, row_dir, {})
    positions = [face_row.get(id(hole)) for hole in holes] if face_row else None
    numbered = number_by_position(holes, row_azimuth_deg=row_azimuth, positions=positions, deep_dir=deep_dir)
    return {old.id: new.id for old, new in zip(holes, numbered) if old.id != new.id}
