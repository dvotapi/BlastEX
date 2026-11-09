"""Схема установки буровой установки на первом ряду (стр. 2 паспорта).

Вектор ReportLab по образцу `_генератор/draw_rig_simple.py` и
`jk830_side.py` (перенесена геометрия, не код matplotlib): уступ, JK830-2 с
поднятой мачтой, скважина первого ряда, призма возможного обрушения и
единственный размер «s» от верхней бровки до переднего края гусениц. Схема,
не чертёж: чисел нет, число s печатается справа от схемы.

Координаты — метры, x — к бровке (бровка в 0), y — вверх (верх уступа в 0).
"""
from __future__ import annotations

import math

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib.colors import HexColor

GRAPHITE = HexColor("#2E3237")
RED = HexColor("#B71C1C")
TINT = HexColor("#FCEDEE")
GREY = HexColor("#6B7075")
MID = HexColor("#5A5F66")
LIGHT = HexColor("#9EA2A8")
ORANGE = HexColor("#C8641E")
YELLOW = HexColor("#E3A21A")
GLASS = HexColor("#D6E4EE")
DUST = HexColor("#B85A1A")
MAST = HexColor("#7A7F86")
CASSETTE = HexColor("#B5B9BE")
GROUND = HexColor("#ECEDEF")

# Схематичный уступ (не масштаб блока): H 10 м, α 75°, γ 65°.
BENCH_H = 10.0
ALPHA_DEG = 75.0
GAMMA_DEG = 65.0
S_DRAWN = 3.2   # опора станка за призмой
E_DRAWN = 1.5   # вылет оси скважины за передний край гусениц
MAST_H = 8.3

X_MIN, X_MAX = -9.3, 5.6
Y_MIN, Y_MAX = -BENCH_H - 1.7, 9.4
# Толщины линий генератора заданы для рисунка шириной 6,4 дюйма.
_SOURCE_WIDTH_PT = 6.4 * 72


class _Canvas:
    """Перевод метров схемы в пункты рисунка."""

    def __init__(self, width_pt: float, height_pt: float, font: str, bold_font: str) -> None:
        self.drawing = Drawing(width_pt, height_pt)
        self.k = min(width_pt / (X_MAX - X_MIN), height_pt / (Y_MAX - Y_MIN))
        self.ox = (width_pt - self.k * (X_MAX - X_MIN)) / 2
        self.oy = (height_pt - self.k * (Y_MAX - Y_MIN)) / 2
        self.lw_k = width_pt / _SOURCE_WIDTH_PT
        self.font, self.bold_font = font, bold_font

    def p(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + (x - X_MIN) * self.k, self.oy + (y - Y_MIN) * self.k

    def polygon(self, points, fill, stroke=GRAPHITE, width=0.9, dash=None) -> None:
        flat = [c for x, y in points for c in self.p(x, y)]
        self.drawing.add(
            Polygon(flat, fillColor=fill, strokeColor=stroke, strokeWidth=width * self.lw_k,
                    strokeDashArray=dash, strokeLineJoin=1)
        )

    def rect(self, x, y, w, h, fill, stroke=GRAPHITE, width=0.9, radius=0.0) -> None:
        x0, y0 = self.p(x, y)
        self.drawing.add(
            Rect(x0, y0, w * self.k, h * self.k, rx=radius * self.k, ry=radius * self.k,
                 fillColor=fill, strokeColor=stroke, strokeWidth=width * self.lw_k)
        )

    def circle(self, x, y, r, fill, stroke=GRAPHITE, width=0.6) -> None:
        cx, cy = self.p(x, y)
        self.drawing.add(Circle(cx, cy, r * self.k, fillColor=fill, strokeColor=stroke, strokeWidth=width * self.lw_k))

    def line(self, x1, y1, x2, y2, color=GRAPHITE, width=0.9, cap=0) -> None:
        a, b = self.p(x1, y1), self.p(x2, y2)
        self.drawing.add(Line(*a, *b, strokeColor=color, strokeWidth=width * self.lw_k, strokeLineCap=cap))

    def text(self, x, y, lines, size, color, anchor="start", bold=False, valign="center") -> None:
        """Строки текста; `size` — кегль генератора, переводится в пункты рисунка."""

        size_pt = size * self.lw_k
        lines = lines if isinstance(lines, (list, tuple)) else [lines]
        leading = size_pt * 1.15
        x0, y0 = self.p(x, y)
        block = leading * len(lines)
        if valign == "center":
            top = y0 + block / 2
        elif valign == "top":
            top = y0
        else:  # bottom
            top = y0 + block
        for index, line in enumerate(lines):
            baseline = top - leading * (index + 1) + (leading - size_pt * 0.75) / 2 + size_pt * 0.05
            self.drawing.add(
                String(x0, baseline, line, fontName=self.bold_font if bold else self.font,
                       fontSize=size_pt, fillColor=color, textAnchor=anchor)
            )

    def arrow_head(self, tip: tuple[float, float], back: tuple[float, float], color, size: float) -> None:
        (tx, ty), (bx, by) = self.p(*tip), self.p(*back)
        length = math.hypot(tx - bx, ty - by) or 1.0
        ux, uy = (tx - bx) / length, (ty - by) / length
        h = size * self.lw_k
        base = (tx - ux * h, ty - uy * h)
        left = (base[0] - uy * h * 0.35, base[1] + ux * h * 0.35)
        right = (base[0] + uy * h * 0.35, base[1] - ux * h * 0.35)
        self.drawing.add(Polygon([tx, ty, *left, *right], fillColor=color, strokeColor=color, strokeWidth=0))


def _jk830(c: _Canvas, hole_x: float, e: float, mast_h: float, lw: float = 1.0) -> None:
    """Силуэт JK830-2 сбоку, мачта поднята; ось скважины — x = hole_x."""

    def X(x: float) -> float:
        return hole_x + x

    tf = -e            # передний край гусеницы
    tr = tf - 4.2      # задний край гусеницы

    def poly(points, fill, width=lw):
        c.polygon([(X(a), b) for a, b in points], fill, width=width)

    # гусеничный ход
    c.rect(X(tr), 0.0, tf - tr, 0.76, GRAPHITE, width=lw, radius=0.36)
    c.rect(X(tr + 0.12), 0.12, tf - tr - 0.24, 0.52, MID, width=0.5, radius=0.25)
    for cx in (tr + 0.4, tf - 0.4):
        c.circle(X(cx), 0.38, 0.27, LIGHT)
        c.circle(X(cx), 0.38, 0.07, GRAPHITE, stroke=GRAPHITE)
    for i in range(5):
        c.circle(X(tr + 0.9 + i * (tf - tr - 1.8) / 4), 0.2, 0.11, LIGHT, width=0.5)
    # рама и платформа
    poly([(tr + 0.4, 0.76), (tf - 0.2, 0.76), (tf - 0.35, 1.02), (tr + 0.55, 1.02)], MID)
    # силовой блок с радиатором
    bx0, bx1 = tr - 0.45, tf - 1.45
    poly([(bx0, 1.02), (bx1, 1.02), (bx1, 2.55), (bx0 + 0.25, 2.55), (bx0, 2.3)], ORANGE)
    c.line(X(bx0 + 0.05), 1.25, X(bx1), 1.25, width=0.5)
    for i in range(7):
        y = 1.45 + i * 0.13
        c.line(X(bx0 + 0.15), y, X(bx0 + 0.95), y, width=0.6)
    for x in (bx0 + 1.1, bx0 + 2.15):
        c.rect(X(x), 1.4, 0.85, 0.95, None, width=0.5)
    poly([(bx0 + 0.35, 2.55), (bx0 + 1.15, 2.55), (bx0 + 1.1, 3.05), (bx0 + 0.4, 3.05)], DUST)
    c.rect(X(bx1 - 0.6), 2.55, 0.09, 0.45, GRAPHITE)
    # кабина
    c0, c1 = tf - 1.45, tf - 0.15
    poly([(c0, 1.02), (c1, 1.02), (c1, 2.4), (c1 - 0.25, 2.95), (c0, 2.95)], YELLOW)
    poly([(c0 + 0.12, 1.85), (c1 - 0.1, 1.85), (c1 - 0.1, 2.35), (c1 - 0.3, 2.82), (c0 + 0.12, 2.82)], GLASS, width=0.6)
    c.line(X(c0 + 0.62), 1.1, X(c0 + 0.62), 2.82, width=0.6)
    # стрела и цилиндры
    pivot = (tf - 0.1, 1.35)
    mx = -0.42
    cradle = (mx - 0.1, 2.05)
    poly([(pivot[0], pivot[1] - 0.18), (cradle[0], cradle[1] - 0.2), (cradle[0], cradle[1] + 0.18),
          (pivot[0], pivot[1] + 0.2)], YELLOW)
    mid = ((pivot[0] + cradle[0]) / 2, (pivot[1] + cradle[1]) / 2 - 0.15)
    c.line(X(tf - 0.35), 0.95, X(mid[0]), mid[1], width=2.6, cap=1)
    c.circle(X(pivot[0]), pivot[1], 0.08, GRAPHITE, stroke=GRAPHITE)
    c.line(X(cradle[0] - 0.1), cradle[1] + 0.15, X(mx - 0.12), 3.3, width=2.0, cap=1)
    # мачта, оголовок, кассета штанг
    top = mast_h
    poly([(mx - 0.17, 0.42), (mx + 0.17, 0.42), (mx + 0.17, top), (mx - 0.17, top)], MAST)
    for x in (mx - 0.1, mx + 0.1):
        c.line(X(x), 0.5, X(x), top - 0.05, width=0.45)
    c.rect(X(mx - 0.22), top, 0.44, 0.22, GRAPHITE)
    poly([(mx - 0.55, 1.6), (mx - 0.2, 1.6), (mx - 0.2, top - 2.2), (mx - 0.55, top - 2.2)], CASSETTE, width=0.6)
    for x in (mx - 0.47, mx - 0.38, mx - 0.29):
        c.line(X(x), 1.65, X(x), top - 2.25, width=0.5)
    # штанга и вращатель
    head = top - 1.6
    c.line(X(0), 0.0, X(0), head, width=1.8)
    poly([(mx - 0.1, head), (0.22, head), (0.22, head + 0.75), (mx - 0.1, head + 0.75)], YELLOW)
    c.rect(X(-0.06), head + 0.75, 0.12, 0.3, GRAPHITE)
    # люнет и пылеуловитель
    poly([(mx - 0.1, 0.55), (0.2, 0.55), (0.2, 0.85), (mx - 0.1, 0.85)], GRAPHITE)
    poly([(-0.32, 0.0), (0.32, 0.0), (0.2, 0.42), (-0.2, 0.42)], DUST)


def drawing(width_pt: float, height_pt: float, *, font: str = "Helvetica", bold_font: str = "Helvetica-Bold") -> Drawing:
    """Схема установки станка на первом ряду с единственным размером «s»."""

    c = _Canvas(width_pt, height_pt, font, bold_font)
    h = BENCH_H
    toe = h / math.tan(math.radians(ALPHA_DEG))
    prism = toe - h / math.tan(math.radians(GAMMA_DEG))
    hole = -S_DRAWN + E_DRAWN
    # уступ
    c.polygon([(-11, 0), (0, 0), (toe, -h), (6, -h), (6, -h - 1.6), (-11, -h - 1.6)], GROUND, width=1.6)
    # призма возможного обрушения: светлая заливка, красный пунктир
    c.polygon([(prism, 0), (0, 0), (toe, -h)], TINT, stroke=RED, width=1.0, dash=[3, 2])
    c.text(2.2, -3.2, ["призма", "возможного", "обрушения"], 11, RED)
    c.line(0.25, -2.2, 2.1, -3.0, color=RED, width=0.7)
    # станок и скважина первого ряда
    _jk830(c, hole_x=hole, e=E_DRAWN, mast_h=MAST_H)
    c.line(hole, 0, hole, -h - 1.0, color=RED, width=2.6)
    c.text(hole - 0.35, -6.5, ["скважина", "1-го ряда"], 11, RED, anchor="end")
    # единственный размер — s от бровки до опоры станка
    y = -0.9
    c.line(-S_DRAWN, 0.0, -S_DRAWN, y - 0.3, color=RED, width=0.9)
    c.line(0, 0.0, 0, y - 0.3, color=RED, width=0.9)
    c.line(-S_DRAWN + 0.3, y, -0.3, y, color=RED, width=1.6)
    c.arrow_head((-S_DRAWN, y), (0, y), RED, 9)
    c.arrow_head((0, y), (-S_DRAWN, y), RED, 9)
    c.text((-S_DRAWN + hole) / 2, y - 0.2, "s", 22, RED, anchor="middle", bold=True, valign="top")
    c.text(0.15, 0.25, "верхняя бровка", 10.5, GREY, valign="bottom")
    c.text(toe + 0.3, -h + 0.25, "нижняя бровка", 10.5, GREY, valign="bottom")
    return c.drawing


__all__ = ["drawing"]
