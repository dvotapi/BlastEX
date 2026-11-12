"""Рисунок типовой конструкции скважинного заряда (разд. 7 техрасчёта).

Символьная схема по `_генератор/draw_charge_column.py` эталона: уступ,
забойка, колонка ВВ, ПД (боевик) у дна, размеры H_у, l_пер, l_заб, l_зар, L, l_б.
Пропорции условные — значения печатаются в таблице рядом из данных
(`technical_calculation`, разд. 7, `constructions`).
"""
from __future__ import annotations

from reportlab.lib.colors import HexColor
from reportlab.platypus import Flowable

from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, GREY, LINE, RED, TINT, ZEBRA

STEMMING = HexColor("#D9DBDE")

# Координаты схемы (условные единицы; пропорции эталона, размеры разнесены,
# чтобы подписи помещались между размерными линиями).
X_MIN, X_MAX, Y_MIN, Y_MAX = -1.2, 11.0, -2.4, 12.2
TOP, FLOOR, SUB, STEM = 10.0, 0.0, 1.5, 3.0
HOLE_X, HOLE_W = 3.0, 1.0           # скважина
DIM_H_X, DIM_STEM_X = 0.6, 2.0      # H_у и l_пер; l_заб и l_зар (подписи слева от линии)
DIM_PRIMER_X, DIM_L_X = 4.45, 5.5   # l_б и L (подписи справа от линии)
BENCH_RIGHT = 6.8                   # правый край уступа; за ним — «верх / подошва уступа»
# Кегль подписей: мельче, чем текст расчёта, чтобы не наезжать на рисунок.
LABEL_SIZE, LABEL_SUB_SIZE, NOTE_SIZE = 5.6, 4.2, 4.3


class ChargeColumn(Flowable):
    """Схема колонки шириной `width` пунктов (высота — по пропорциям эталона)."""

    def __init__(self, width: float, *, double_primer: bool = False, side_labels: bool = True) -> None:
        super().__init__()
        self.side_labels = side_labels
        self.width = width
        self.k = width / (X_MAX - X_MIN)
        self.height = (Y_MAX - Y_MIN) * self.k
        self.double_primer = double_primer

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return self.width, self.height

    def _xy(self, x: float, y: float) -> tuple[float, float]:
        return (x - X_MIN) * self.k, (y - Y_MIN) * self.k

    def _rect(self, x: float, y: float, w: float, h: float, fill, stroke, width: float = 0.8) -> None:
        c = self.canv
        x0, y0 = self._xy(x, y)
        c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke)
            c.setLineWidth(width)
        c.rect(x0, y0, w * self.k, h * self.k, stroke=1 if stroke is not None else 0, fill=1)

    def _line(self, x1, y1, x2, y2, color, width=0.6, dash=None) -> None:
        c = self.canv
        c.setStrokeColor(color)
        c.setLineWidth(width)
        c.setDash(*dash) if dash else c.setDash()
        c.line(*self._xy(x1, y1), *self._xy(x2, y2))
        c.setDash()

    def _text(self, x, y, value, size=NOTE_SIZE, color=GREY, anchor="left", bold=False) -> None:
        c = self.canv
        c.setFillColor(color)
        c.setFont(FONT_BOLD if bold else FONT, size)
        px, py = self._xy(x, y)
        {"left": c.drawString, "right": c.drawRightString, "center": c.drawCentredString}[anchor](px, py - size * 0.35, value)

    def _label(self, x, y, base, sub, color) -> None:
        """Обозначение с подстрочным индексом («l» + «заб»), правый край — в `x`."""

        c = self.canv
        px, py = self._xy(x, y)
        w_base = c.stringWidth(base, FONT_BOLD, LABEL_SIZE)
        w_sub = c.stringWidth(sub, FONT_BOLD, LABEL_SUB_SIZE) if sub else 0
        self._label_at(px - w_base - w_sub, py, base, sub, color)

    def _label_at(self, px: float, py: float, base: str, sub: str, color) -> None:
        """Обозначение с индексом, левый край — `px`, середина по высоте — `py`."""

        c = self.canv
        c.setFillColor(color)
        c.setFont(FONT_BOLD, LABEL_SIZE)
        c.drawString(px, py - LABEL_SIZE * 0.35, base)
        if sub:
            c.setFont(FONT_BOLD, LABEL_SUB_SIZE)
            c.drawString(px + c.stringWidth(base, FONT_BOLD, LABEL_SIZE), py - LABEL_SIZE * 0.35 - 1.6, sub)

    def _dim(self, x, y1, y2, base, sub, color=GRAPHITE, label_left=True) -> None:
        c = self.canv
        self._line(x, y1, x, y2, color, 0.7)
        for y, sign in ((y1, 1 if y1 < y2 else -1), (y2, -1 if y1 < y2 else 1)):
            px, py = self._xy(x, y)
            c.setFillColor(color)
            path = c.beginPath()
            path.moveTo(px, py)
            path.lineTo(px - 1.3, py + sign * 2.6)
            path.lineTo(px + 1.3, py + sign * 2.6)
            path.close()
            c.drawPath(path, stroke=0, fill=1)
        mid = (y1 + y2) / 2
        if label_left:
            self._label(x - 0.15, mid, base, sub, color)
        else:
            px, py = self._xy(x + 0.15, mid)
            self._label_at(px, py, base, sub, color)

    def draw(self) -> None:
        bottom = FLOOR - SUB
        x0, w = HOLE_X, HOLE_W
        # массив уступа
        self._rect(0.2, FLOOR - 2.0, BENCH_RIGHT - 0.2, TOP - FLOOR + 2.0, ZEBRA, None)
        self._line(0.2, TOP, BENCH_RIGHT, TOP, GRAPHITE, 1.0)
        self._line(0.2, FLOOR, BENCH_RIGHT, FLOOR, GRAPHITE, 0.6, dash=(3, 2))
        if self.side_labels:
            self._text(BENCH_RIGHT + 0.1, FLOOR, "подошва уступа")
            self._text(BENCH_RIGHT + 0.1, TOP, "верх уступа")
        # колонка ВВ и забойка
        self._rect(x0, bottom, w, TOP - STEM - bottom, TINT, RED)
        self._rect(x0, TOP - STEM, w, STEM, STEMMING, GRAPHITE)
        for k in range(1, 6):
            yy = TOP - STEM + k * STEM / 6
            self._line(x0 + 0.2, yy, x0 + w - 0.2, yy, GREY, 0.4, dash=(0.6, 1.2))
        # ПД (боевик) и НСИ
        primer_y = bottom + 1.2
        self._rect(x0 + 0.25, primer_y - 0.3, w - 0.5, 0.6, RED, RED)
        if self.double_primer:
            self._rect(x0 + 0.25, primer_y + 2.6, w - 0.5, 0.6, RED, RED)
        self._line(x0 + w / 2, primer_y + 0.3, x0 + w / 2, TOP + 0.8, GRAPHITE, 0.7)
        self._text(x0 + w / 2 + 0.15, TOP + 1.0, "НСИ к поверхностной сети" if self.side_labels else "НСИ", color=GRAPHITE)
        # размеры: слева — H_у, l_пер, l_заб, l_зар; справа — l_б и L
        self._dim(DIM_STEM_X, TOP, TOP - STEM, "l", "заб")
        self._dim(DIM_STEM_X, TOP - STEM, bottom, "l", "зар", RED)
        self._dim(DIM_H_X, TOP, FLOOR, "H", "у")
        self._dim(DIM_H_X, FLOOR, bottom, "l", "пер")
        self._dim(DIM_L_X, TOP, bottom, "L", "", label_left=False)
        self._dim(DIM_PRIMER_X, primer_y, bottom, "l", "б", RED, label_left=False)
        self._line(x0, bottom, DIM_L_X + 0.2, bottom, LINE, 0.5)
        self._line(x0 + w, primer_y, DIM_PRIMER_X, primer_y, RED, 0.4, dash=(1, 1))
        # легенда: отступы — по ширине подписей, чтобы они не наезжали друг на друга
        if self.side_labels:
            c = self.canv
            px, py = self._xy(X_MIN + 0.1, -2.2)
            box = 0.5 * self.k
            for fill, stroke, label in ((TINT, RED, "ВВ"), (STEMMING, GRAPHITE, "забойка"), (RED, RED, "ПД (боевик)")):
                c.setFillColor(fill)
                c.setStrokeColor(stroke)
                c.setLineWidth(0.5)
                c.rect(px, py, box, box * 0.8, stroke=1, fill=1)
                c.setFillColor(GRAPHITE)
                c.setFont(FONT, NOTE_SIZE)
                c.drawString(px + box + 1.5, py + box * 0.4 - NOTE_SIZE * 0.35, label)
                px += box + 1.5 + c.stringWidth(label, FONT, NOTE_SIZE) + 4
