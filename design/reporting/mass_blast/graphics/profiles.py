"""Г.2 — поперечные профили через заряды (форма v0.7, TASK-018 §4).

Два разреза из `blocks_v2[i].graphics.sections`: уступ по отметкам устьев,
откос от подошвы до верхней бровки на линии разреза, в скважине — деки
конструкции заряда (забойка, ВВ, промежутки), боевики на своей глубине,
№ над устьем, «L / Q» справа, ЛСПП первого ряда, шкала отметок слева.
Масштаб — один на оба разреза, самый крупный из 1:200 / 1:250 / 1:500 /
1:1000, при котором оба помещаются; диаметр скважин — не в масштабе.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, PolyLine, String
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm

from design.reporting import plan_sheet
from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, GREY, RED, TINT, ZEBRA
from design.reporting.mass_blast.common import num, text
from design.reporting.mass_blast.graphics.sheet import FIELD_H_MM, FIELD_W_MM, STEMMING, arrow, legend_band

PROFILE_SCALES = (200, 250, 500, 1000)
PROFILE_H_MM = FIELD_H_MM / 2
TITLE_H_MM = 6.5
AXIS_W_MM = 16.0         # шкала отметок слева
RIGHT_W_MM = 30.0        # «подошва ≈ …» справа
HOLE_W_MM = 2.4          # ширина скважины на чертеже — не в масштабе
LEFT_RUN_M = 8.0         # подошва перед откосом
RIGHT_RUN_M = 4.0        # уступ за последней скважиной
BELOW_M = 1.5            # массив под подошвой
TOE_BELOW_M = 0.5        # под забоем самой глубокой скважины
ABOVE_MM = 4.5           # над устьем — номер скважины
LABEL_MM = 14.0          # «L 11,6 / 160 кг» справа от последней скважины
WATER = HexColor("#D6E9F8")
DECK_STYLE = {
    "explosive": dict(fillColor=TINT, strokeColor=RED),
    "stemming": dict(fillColor=STEMMING, strokeColor=GRAPHITE),
    "water": dict(fillColor=WATER, strokeColor=GRAPHITE),
    "air": dict(fillColor=white, strokeColor=GRAPHITE),
    "inert": dict(fillColor=HexColor("#ECEDEF"), strokeColor=GRAPHITE),
}


def _station(value: Any, default: float) -> float:
    return default if value is None else float(value)


def _extent(section: Mapping[str, Any]) -> tuple[float, float, float, float]:
    holes = section.get("holes") or ()
    toe = _station(section.get("toe_station_m"), 0.0)
    crest = _station(section.get("crest_station_m"), toe)
    stations = [float(h["station_m"]) for h in holes] + [float(h["toe_station_m"]) for h in holes]
    s0 = min([toe - LEFT_RUN_M, crest] + stations)
    s1 = max(stations + [crest]) + RIGHT_RUN_M
    floor = float(section.get("floor_z") or 0.0)
    bottom = min([floor - BELOW_M] + [float(h["toe_z"]) - TOE_BELOW_M for h in holes])
    top = max(float(h["collar_z"]) for h in holes) if holes else floor + 10
    return s0, s1, bottom, top


def profile_scale(sections: Sequence[Mapping[str, Any]]) -> int:
    """Масштаб разрезов: один на оба, самый крупный из ряда, при котором оба помещаются."""

    width = FIELD_W_MM - AXIS_W_MM - RIGHT_W_MM - LABEL_MM
    height = PROFILE_H_MM - TITLE_H_MM - ABOVE_MM - 1.5
    need = 0.0
    for section in sections:
        s0, s1, z0, z1 = _extent(section)
        need = max(need, (s1 - s0) / width * 1000, (z1 - z0) / height * 1000)
    for scale in PROFILE_SCALES:
        if need <= scale + 1e-9:
            return scale
    return PROFILE_SCALES[-1]


def _tick_step(scale: int) -> int:
    for step in (1, 2, 5, 10, 20):
        if step * 1000 / scale >= 4.0:
            return step
    return 50


def _axis_point(hole: Mapping[str, Any], depth: float) -> tuple[float, float]:
    length = float(hole.get("length_m") or 0.0) or 1.0
    share = min(1.0, max(0.0, depth / length))
    s = float(hole["station_m"]) + (float(hole["toe_station_m"]) - float(hole["station_m"])) * share
    z = float(hole["collar_z"]) + (float(hole["toe_z"]) - float(hole["collar_z"])) * share
    return s, z


def profile_drawing(section: Mapping[str, Any], scale: int) -> Drawing:
    d = Drawing(FIELD_W_MM * mm, PROFILE_H_MM * mm)
    holes = list(section.get("holes") or ())
    if not holes:
        return d
    k = 1000 / scale
    s0, _s1, z0, z1 = _extent(section)
    base_y = 1.0

    def xy(s: float, z: float) -> tuple[float, float]:
        return ((AXIS_W_MM + 2 + (s - s0) * k) * mm, (base_y + (z - z0) * k) * mm)

    floor = float(section.get("floor_z") or 0.0)
    toe = _station(section.get("toe_station_m"), 0.0)
    crest = _station(section.get("crest_station_m"), toe)
    first = holes[0]
    last = holes[-1]
    end = max(float(h["station_m"]) for h in holes) + RIGHT_RUN_M
    top = [(crest, float(first["collar_z"]))] + [(float(h["station_m"]), float(h["collar_z"])) for h in holes]
    top.append((end, float(last["collar_z"])))
    massif = top + [(end, z0), (toe - LEFT_RUN_M, z0), (toe - LEFT_RUN_M, floor), (toe, floor)]
    d.add(Polygon([v for s, z in massif for v in xy(s, z)], fillColor=ZEBRA, strokeColor=None))
    d.add(PolyLine([v for s, z in top for v in xy(s, z)], strokeColor=GRAPHITE, strokeWidth=0.9))
    d.add(PolyLine([v for s, z in ((toe - LEFT_RUN_M, floor), (toe, floor), (crest, float(first["collar_z"]))) for v in xy(s, z)],
                   strokeColor=GRAPHITE, strokeWidth=0.9))
    d.add(PolyLine([*xy(toe, floor), *xy(end, floor)], strokeColor=GRAPHITE, strokeWidth=0.5, strokeDashArray=[1.4 * mm, 1 * mm]))
    fx, fy = xy(end, floor)
    d.add(String(fx + 1.5 * mm, fy - 2, f"подошва ≈ {num(floor, 1)}", fontName=FONT, fontSize=5.5, fillColor=GREY))
    ax, ay = xy(toe - LEFT_RUN_M, floor)
    d.add(String(ax + 1 * mm, ay + 1.2 * mm, f"α = {num(section.get('face_angle_deg'), 0)}°", fontName=FONT, fontSize=5.5,
                 fillColor=GREY))
    half = HOLE_W_MM / 2 * mm
    for hole in holes:
        _hole(d, hole, xy, half)
    lspp = first.get("lspp_m")
    if lspp:
        # Ось скважины на уровне подошвы: глубина по оси, на которой отметка = подошва.
        drop = max(float(first["collar_z"]) - float(first["toe_z"]), 1e-6)
        axis_s, _ = _axis_point(first, (float(first["collar_z"]) - floor) / drop * float(first.get("length_m") or 0.0))
        y_dim = floor - 1.4
        (x0, y0), (x1, _y1) = xy(toe, y_dim), xy(axis_s, y_dim)
        d.add(arrow((x1 / mm, y0 / mm), (x0 / mm, y0 / mm), RED, width=0.5, head_mm=1.0))
        d.add(arrow((x0 / mm, y0 / mm), (x1 / mm, y0 / mm), RED, width=0.5, head_mm=1.0))
        d.add(String((x0 + x1) / 2, y0 - 7, f"W = {num(lspp, 2)}", fontName=FONT, fontSize=5.5, fillColor=RED,
                     textAnchor="middle"))
    step = _tick_step(scale)
    lo, hi = math.floor(z0 / step) * step, math.ceil(z1 / step) * step
    xa = AXIS_W_MM * mm
    d.add(Line(xa, xy(s0, max(lo, z0))[1], xa, xy(s0, min(hi, z1 + 1))[1], strokeColor=GRAPHITE, strokeWidth=0.5))
    z = lo
    while z <= hi:
        if z0 <= z <= z1 + 1:
            y = xy(s0, z)[1]
            d.add(Line(xa - 1.2 * mm, y, xa, y, strokeColor=GRAPHITE, strokeWidth=0.5))
            d.add(String(xa - 1.6 * mm, y - 1.8, f"{z:g}", fontName=FONT, fontSize=5, fillColor=GREY, textAnchor="end"))
        z += step
    title_y = (PROFILE_H_MM - 3.2) * mm
    name = text(section.get("name"))
    d.add(String(0, title_y, f"Разрез {name}–{name}", fontName=FONT_BOLD, fontSize=8.5, fillColor=GRAPHITE))
    source = "" if section.get("slope_source") == "contour" else "; откос — по ЛСПП и углу (бровки на разрезе нет)"
    d.add(String(0, title_y - 2.8 * mm, f"скважин в профиле {len(holes)}; отметки, м{source}", fontName=FONT, fontSize=5.5,
                 fillColor=GREY))
    return d


def _hole(d: Drawing, hole: Mapping[str, Any], xy, half: float) -> None:
    length = float(hole.get("length_m") or 0.0)
    if length <= 0:
        return

    def quad(a: float, b: float) -> list[float]:
        (sa, za), (sb, zb) = _axis_point(hole, a), _axis_point(hole, b)
        (xa, ya), (xb, yb) = xy(sa, za), xy(sb, zb)
        return [xa - half, ya, xa + half, ya, xb + half, yb, xb - half, yb]

    d.add(Polygon(quad(0.0, length), fillColor=white, strokeColor=GRAPHITE, strokeWidth=0.4))
    for deck in hole.get("decks") or ():
        style = DECK_STYLE.get(str(deck.get("kind")), dict(fillColor=STEMMING, strokeColor=GRAPHITE))
        a, b = float(deck.get("from_m") or 0.0), min(float(deck.get("to_m") or 0.0), length)
        if b <= a:
            continue
        d.add(Polygon(quad(a, b), strokeWidth=0.4, **style))
        if deck.get("kind") == "stemming":
            (sa, za), (sb, zb) = _axis_point(hole, a), _axis_point(hole, b)
            (xa, ya), (xb, yb) = xy(sa, za), xy(sb, zb)
            count = max(1, int(abs(ya - yb) / (1.3 * mm)))
            for index in range(count):
                t = (index + 0.5) / count
                x, y = xa + (xb - xa) * t, ya + (yb - ya) * t
                d.add(Circle(x + (half * 0.4 if index % 2 else -half * 0.4), y, 0.25, fillColor=GRAPHITE, strokeColor=None))
    for position in hole.get("primers_m") or ():
        a = max(0.0, float(position) - 0.25)
        b = min(length, float(position) + 0.25)
        d.add(Polygon(quad(a, b), fillColor=RED, strokeColor=RED, strokeWidth=0.3))
    cx, cy = xy(float(hole["station_m"]), float(hole["collar_z"]))
    first = bool(hole.get("first_row"))
    d.add(String(cx, cy + 1.6 * mm, text(hole.get("hole_id")), fontName=FONT_BOLD, fontSize=5.5,
                 fillColor=RED if first else GRAPHITE, textAnchor="middle"))
    mid_s, mid_z = _axis_point(hole, length * 0.55)
    mx, my = xy(mid_s, mid_z)
    d.add(String(mx + half + 1, my + 1, f"L {num(length, 1)}", fontName=FONT, fontSize=5, fillColor=GRAPHITE))
    if hole.get("charge_kg") is not None:
        d.add(String(mx + half + 1, my - 5.5, f"{num(hole.get('charge_kg'), 0)} кг", fontName=FONT, fontSize=5,
                     fillColor=GRAPHITE))


def g2_drawings(sections: Sequence[Mapping[str, Any]]) -> tuple[list[Drawing], Drawing, int]:
    """Разрезы (по одному Drawing на разрез), полоса легенды и масштаб."""

    scale = profile_scale(sections)
    drawings = [profile_drawing(section, scale) for section in sections]
    bar_m, bar_mm = plan_sheet.bar(scale, steps=(2, 5, 10, 20, 50, 100), target_mm=40.0)
    items = [
        ("box", {"fill": STEMMING}, "забойка"),
        ("box", {"fill": TINT, "stroke": RED}, "заряд ВВ"),
        ("box", {"fill": RED, "stroke": RED}, "промежуточный детонатор (боевик)"),
        ("box", {"fill": WATER}, "вода"),
        ("line", {"stroke": RED, "width": 0.5}, "W — ЛСПП первого ряда у подошвы, м"),
    ]
    notes = [("№ скважины — над устьем; справа — длина L, м, и масса заряда, кг (как в таблице параметров).", GREY)]
    if not sections:
        notes.insert(0, ("Разрезы не построены: в блоке меньше двух скважин.", RED))
    legend = legend_band(scale=scale, bar_m=bar_m, bar_mm=bar_mm, items=items, notes=notes, north=None,
                         scale_note="Диаметр скважин — не в масштабе. Печатать в масштабе 100 %")
    return drawings, legend, scale


__all__ = ["g2_drawings", "profile_scale"]
