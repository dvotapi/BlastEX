"""Формулы техрасчёта: запись mathtext (подмножество LaTeX) → векторные контуры в PDF.

Решение владельца 11.11.2026 (план PR 3, §2): формулы набираются как в эталоне
(`_генератор/render_formulas.py`: matplotlib mathtext, Computer Modern, кириллица
индексов — DejaVu Serif), но в PDF идут контурами глифов — без картинок, без
встроенных шрифтов и без JS. Повторяемо по байтам.

Здесь только общий вид формул формы (P, Q, q; r_разл; Q_э, r_в; r_с) —
подстановки и результаты печатаются строками из данных ревизии.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import matplotlib
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MplPath
from matplotlib.textpath import TextPath
from reportlab.platypus import Flowable

from design.reporting.brand import GRAPHITE


def _s(text: str) -> str:
    """Кириллический индекс прямым шрифтом."""

    return r"\mathrm{" + text + "}"


# Тексты формул — как в `render_formulas.py` эталона, но r_в — по ФНП 494
# (формулы 12–14: 65·∛Q_э² до 2 кг, 65·√Q_э до 1000, 200·∛Q_э до 5000 —
# решение В3 PR 1: где форма расходится с ФНП, считаем по ФНП).
FORMULAS: dict[str, list[str]] = {
    "4": [
        rf"$P=\dfrac{{\pi d^{{2}}}}{{4}}\,\Delta \qquad Q=P\,l_{{{_s('зар')}}} \qquad "
        rf"q=\dfrac{{Q_{{{_s('ВВ')}}}+Q_{{{_s('ПД')}}}}}{{V}}$",
    ],
    "13": [
        rf"$r_{{{_s('разл')}}}=1250\,\eta_{{{_s('з')}}}\sqrt{{\dfrac{{f}}{{1+\eta_{{{_s('заб')}}}}}\cdot\dfrac{{d}}{{a}}}}"
        rf" \qquad \eta_{{{_s('з')}}}=\dfrac{{l_{{{_s('зар')}}}}}{{L}} \qquad "
        rf"\eta_{{{_s('заб')}}}=\dfrac{{l_{{{_s('заб')}}}}}{{l_{{{_s('св')}}}}}$",
    ],
    "14": [
        rf"$Q_{{{_s('э')}}}=12\,P\,d\,K_{{{_s('з')}}}\,N \;\; (l_{{{_s('зар')}}}>12d) \qquad "
        rf"Q_{{{_s('э')}}}=P\,l_{{{_s('зар')}}}\,K_{{{_s('з')}}}\,N \;\; (l_{{{_s('зар')}}}\leq 12d)$",
        rf"$r_{{{_s('в')}}}=65\,\sqrt[3]{{Q_{{{_s('э')}}}^{{2}}}}\;\;(Q_{{{_s('э')}}}\leq 2) \qquad "
        rf"r_{{{_s('в')}}}=65\,\sqrt{{Q_{{{_s('э')}}}}}\;\;(2<Q_{{{_s('э')}}}<1000) \qquad "
        rf"r_{{{_s('в')}}}=200\,\sqrt[3]{{Q_{{{_s('э')}}}}}\;\;(1000\leq Q_{{{_s('э')}}}<5000)$",
    ],
    "15": [
        rf"$r_{{{_s('с')}}}=K_{{{_s('г')}}}\,K_{{{_s('с')}}}\,\alpha\,\dfrac{{\sqrt[3]{{Q}}}}{{\sqrt[4]{{N}}}}$",
    ],
}

_RC = {"mathtext.fontset": "cm", "font.family": "DejaVu Serif"}
# `rc_context` меняет глобальные настройки matplotlib: запросы API идут в
# нескольких потоках, поэтому набор формулы — под замком.
_LOCK = threading.Lock()


@lru_cache(maxsize=64)
def _outline(tex: str, size: float) -> tuple[tuple[tuple[int, tuple[float, ...]], ...], tuple[float, float, float, float]]:
    """Контуры формулы в пунктах: команды (код, точки) и рамка (x0, y0, x1, y1)."""

    with _LOCK, matplotlib.rc_context(_RC):
        path = TextPath((0, 0), tex, size=size, prop=FontProperties(family="DejaVu Serif"))
    commands: list[tuple[int, tuple[float, ...]]] = []
    current = (0.0, 0.0)
    for points, code in path.iter_segments(curves=True, simplify=False):
        if code == MplPath.MOVETO:
            current = (points[0], points[1])
            commands.append((1, (points[0], points[1])))
        elif code == MplPath.LINETO:
            current = (points[0], points[1])
            commands.append((2, (points[0], points[1])))
        elif code == MplPath.CURVE3:
            # Квадратичная Безье → кубическая.
            (qx, qy, x, y), (sx, sy) = points, current
            c1 = (sx + 2 / 3 * (qx - sx), sy + 2 / 3 * (qy - sy))
            c2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
            commands.append((3, (*c1, *c2, x, y)))
            current = (x, y)
        elif code == MplPath.CURVE4:
            commands.append((3, tuple(points)))
            current = (points[4], points[5])
        elif code == MplPath.CLOSEPOLY:
            commands.append((4, ()))
    extents = path.get_extents()
    return tuple(commands), (extents.x0, extents.y0, extents.x1, extents.y1)


class Formula(Flowable):
    """Формула как Flowable: ширина и высота — по рамке контуров."""

    def __init__(self, tex: str, size: float = 11.0, pad: float = 2.0) -> None:
        super().__init__()
        self.tex, self.size, self.pad = tex, size, pad
        self.commands, (self.x0, self.y0, self.x1, self.y1) = _outline(tex, size)

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        scale = self._scale(avail_width)
        return (self.x1 - self.x0) * scale, (self.y1 - self.y0) * scale + 2 * self.pad

    def _scale(self, avail_width: float) -> float:
        width = self.x1 - self.x0
        return min(1.0, avail_width / width) if width > 0 else 1.0

    def draw(self) -> None:
        canvas = self.canv
        scale = self._scale(getattr(self, "_avail_width", 1e9))
        canvas.saveState()
        canvas.translate(0, self.pad)
        canvas.scale(scale, scale)
        canvas.translate(-self.x0, -self.y0)
        canvas.setFillColor(GRAPHITE)
        path = canvas.beginPath()
        for code, points in self.commands:
            if code == 1:
                path.moveTo(*points)
            elif code == 2:
                path.lineTo(*points)
            elif code == 3:
                path.curveTo(*points)
            else:
                path.close()
        canvas.drawPath(path, stroke=0, fill=1, fillMode=0)
        canvas.restoreState()

    def wrapOn(self, canv, avail_width, avail_height):  # noqa: N802 — имя ReportLab
        self._avail_width = avail_width
        return super().wrapOn(canv, avail_width, avail_height)


def section_formulas(number: str, size: float = 11.0) -> list[Formula]:
    return [Formula(tex, size) for tex in FORMULAS.get(number, [])]
