"""План расположения скважин на стр. 4 паспорта на бурение (TASK-015, PR 3).

Чистая раскладка снимка ревизии (`context["holes"]`, `context["plan"]`) в
миллиметры поля листа: начало — левый нижний угол поля, север вверх, без
поворота. Масштаб — по размеру листа (решение владельца 09.11.2026): самый
крупный, кратный 10, при котором блок помещается в поле, но не крупнее
1:200. Отрисовка — `plan_drawing.py`. Перевод координат, масштаб, линейка и
кегль подписей — общий генератор плана `design/reporting/plan_sheet.py`
(им же рисуются Г.1, Г.3, Г.4 проекта МВ).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import shapely
from shapely.geometry import LineString

from design.reporting import plan_sheet
from design.reporting.drill import fmt
from design.reporting.plan_sheet import BAR_STEPS_M, MM_TO_PT, PlanView  # noqa: F401 — прежние имена модуля

PLAN_W_MM = 180.0
PLAN_H_MM = 228.0
PLAN_PAD_MM = 6.0
# Справа от самых восточных скважин — место под подписи (номер и глубина).
LABEL_RESERVE_MM = 8.0
MIN_SCALE = 200
MIN_HOLE_MM = 1.4
LABEL_PT = (3.5, 6.0)
# Кегль подписи — доля расстояния до ближайшей скважины на листе: номер и
# глубина справа от кружка не налезают на соседний.
LABEL_SHARE = 0.3
BAR_TARGET_MM = plan_sheet.BAR_TARGET_MM
NOTE_NO_PLAN = "Контур и бровки не сохранены в ревизии"

XY = tuple[float, float]
Line = tuple[XY, ...]


@dataclass(frozen=True)
class PlanHole:
    x: float
    y: float
    r: float
    number: str
    depth: str
    first_row: bool
    toe: XY | None


@dataclass(frozen=True)
class PlanSheet:
    scale: int
    holes: tuple[PlanHole, ...]
    contour: Line
    crest_top: tuple[Line, ...]
    crest_toe: tuple[Line, ...]
    toe_source: str | None
    situation: tuple[Line, ...]
    label_pt: float
    bar_m: int
    bar_mm: float
    note: str


def plan_scale(width_m: float, height_m: float, field_w_mm: float, field_h_mm: float) -> int:
    """Знаменатель масштаба: блок с отступом `PLAN_PAD_MM` и местом под подписи справа помещается в поле."""

    usable_w, usable_h = field_w_mm - 2 * PLAN_PAD_MM - LABEL_RESERVE_MM, field_h_mm - 2 * PLAN_PAD_MM
    return plan_sheet.scale_multiple_of_10(width_m, height_m, usable_w, usable_h, MIN_SCALE)


_point = plan_sheet.point
_line = plan_sheet.line


def _bar(scale: int) -> tuple[int, float]:
    return plan_sheet.bar(scale)


def _label_pt(points: list[XY]) -> float:
    return plan_sheet.label_pt(points, LABEL_SHARE, LABEL_PT)


def hole_circle_mm(summary: Mapping[str, Any], row: Mapping[str, Any]) -> float | None:
    """Ø кружка скважины (план PR 3, чертёж PR 4): диаметр инструмента из
    паспорта; нет — диаметр скважины (с разбуриванием); нет и его — None."""

    value = summary.get("bit_diameter_mm") or row.get("diameter_mm")
    return float(value) if value else None


def build_plan(context: Mapping[str, Any]) -> PlanSheet:
    """План из снимка ревизии; ревизия до PR 3 (нет `plan`) — только кружки по устьям."""

    plan = context.get("plan")
    geometry = plan or {}
    rows = list(context.get("holes") or ())
    contour = _line(geometry.get("contour") or ())
    crest_top = [line for line in (_line(item) for item in geometry.get("crest_top") or ()) if len(line) >= 2]
    crest_toe = [line for line in (_line(item) for item in geometry.get("crest_toe") or ()) if len(line) >= 2]
    collars = [_point(row.get("collar")) for row in rows]
    toes = [
        _point(row.get("toe")) if row.get("azimuth_deg") is not None else None
        for row in rows
    ]
    extent = [p for p in collars if p] + [p for p in toes if p] + contour
    extent += [p for line in (*crest_top, *crest_toe) for p in line]
    if extent:
        xs, ys = [p[0] for p in extent], [p[1] for p in extent]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    else:
        x0 = x1 = y0 = y1 = 0.0
    scale = plan_scale(x1 - x0, y1 - y0, PLAN_W_MM, PLAN_H_MM)
    view = PlanView(scale=scale, angle_deg=0.0, cx=(x0 + x1) / 2, cy=(y0 + y1) / 2,
                    ox=(PLAN_W_MM - LABEL_RESERVE_MM) / 2, oy=PLAN_H_MM / 2)
    sheet_xy = view.xy
    sheet_line = view.line

    summary = context.get("summary") or {}
    holes = []
    for row, collar, toe in zip(rows, collars, toes):
        if collar is None:
            continue
        diameter = hole_circle_mm(summary, row) or 0.0
        x, y = sheet_xy(collar)
        holes.append(
            PlanHole(
                x=x, y=y, r=max(float(diameter) / scale, MIN_HOLE_MM) / 2,
                number=str(row.get("number") or ""), depth=fmt.num(row.get("length_m"), 1),
                first_row=bool(row.get("first_row")), toe=sheet_xy(toe) if toe else None,
            )
        )
    situation: list[Line] = []
    for layer in geometry.get("situation") or ():
        for item in layer.get("lines") or ():
            line = [sheet_xy(p) for p in _line(item.get("points") or ())]
            if len(line) < 2:
                continue
            clipped = shapely.clip_by_rect(LineString(line), 0.0, 0.0, PLAN_W_MM, PLAN_H_MM)
            for part in getattr(clipped, "geoms", [clipped]):
                if not part.is_empty and part.geom_type == "LineString":
                    situation.append(tuple((float(px), float(py)) for px, py in part.coords))
    bar_m, bar_mm = _bar(scale)
    return PlanSheet(
        scale=scale,
        holes=tuple(holes),
        contour=sheet_line(contour) if len(contour) >= 3 else (),
        crest_top=tuple(sheet_line(line) for line in crest_top),
        crest_toe=tuple(sheet_line(line) for line in crest_toe),
        toe_source=geometry.get("toe_source") if crest_toe and isinstance(geometry.get("toe_source"), str) else None,
        situation=tuple(situation),
        label_pt=_label_pt([(h.x, h.y) for h in holes]),
        bar_m=bar_m,
        bar_mm=bar_mm,
        note="" if plan is not None else NOTE_NO_PLAN,
    )
