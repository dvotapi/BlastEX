"""Синтетические чертежи для тестов ситуации и СК (TASK-013, PR 4).

Координаты — «как МСК»: синтетический сдвиг (7 000 000; 500 000). Реальные
координаты заказчика и сдвиг фикстуры блока 66 сюда не попадают.
"""
from __future__ import annotations

import io

import ezdxf

X0, Y0 = 7_000_000.0, 500_000.0


def _bytes(doc) -> bytes:
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


def block_dxf(dx: float = 0.0, dy: float = 0.0, *, marker: float = 0.0) -> bytes:
    """Чертёж блока: контур, бровки с Z, отметки и ближняя ситуация (отвал).

    `marker` сдвигает одну отметку — так получается «другой файл» с тем же
    содержанием для проверки повторной загрузки.
    """

    x0, y0 = X0 + dx, Y0 + dy
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(x0, y0), (x0 + 40, y0), (x0 + 40, y0 + 30), (x0, y0 + 30)],
        close=True,
        dxfattribs={"layer": "блок 70"},
    )
    msp.add_polyline3d([(x0 - 5, y0 + 30, 420.5), (x0 + 45, y0 + 30, 421.0)], dxfattribs={"layer": "Горизонт +410"})
    msp.add_polyline3d([(x0 - 5, y0 + 34, 410.5), (x0 + 45, y0 + 34, 410.8)], dxfattribs={"layer": "Горизонт +410"})
    for index in range(5):
        msp.add_point((x0 + 5 + 7 * index, y0 + 10 + marker, 420.0 + 0.1 * index), dxfattribs={"layer": "Отметка"})
    msp.add_polyline3d(
        [(x0 + 60, y0, 421.5), (x0 + 80, y0 + 5, 421.8), (x0 + 90, y0 + 25, 422.0)],
        dxfattribs={"layer": "Отвал вскрышных пород"},
    )
    return _bytes(doc)


def situation_dxf(dx: float = 0.0, dy: float = 0.0, *, origin_outlier: bool = False, roads: int = 1) -> bytes:
    """«Положение горных работ»: дороги (2D), ЛЭП, склад, здания, контур карьера."""

    x0, y0 = X0 + dx, Y0 + dy
    doc = ezdxf.new("R2010")
    doc.layers.add("Автодорога", color=7)  # ACI 7 — «белый», на светлом плане невидим
    doc.layers.add("ВЛ-6кВ", color=1)
    msp = doc.modelspace()
    for index in range(roads):
        msp.add_lwpolyline(
            [(x0 - 200, y0 - 50 - 3 * index), (x0 + 100, y0 - 60 - 3 * index), (x0 + 400, y0 - 40 - 3 * index)],
            dxfattribs={"layer": "Автодорога"},
        )
    msp.add_line((x0 - 300, y0 + 200, 0.0), (x0 + 500, y0 + 220, 0.0), dxfattribs={"layer": "ВЛ-6кВ"})
    msp.add_lwpolyline(
        [(x0 + 150, y0 + 80), (x0 + 190, y0 + 80), (x0 + 190, y0 + 110), (x0 + 150, y0 + 110)],
        close=True,
        dxfattribs={"layer": "Склад негабарита"},
    )
    msp.add_lwpolyline(
        [(x0 - 20, y0 + 300), (x0 - 10, y0 + 300), (x0 - 10, y0 + 310), (x0 - 20, y0 + 310)],
        close=True,
        dxfattribs={"layer": "Здания"},
    )
    msp.add_lwpolyline(
        [(x0 - 400, y0 - 300), (x0 + 600, y0 - 300), (x0 + 600, y0 + 400), (x0 - 400, y0 + 400)],
        close=True,
        dxfattribs={"layer": "Граница карьера"},
    )
    if origin_outlier:
        msp.add_point((0.0, 0.0, 0.0), dxfattribs={"layer": "Мусор"})
    return _bytes(doc)
