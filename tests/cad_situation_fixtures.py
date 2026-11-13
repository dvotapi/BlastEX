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


def pit_plan_dxf(*, extra_layer: str = "") -> bytes:
    """План карьера (ситуация объекта): нужные слои и лишние, часть скрыта в чертеже.

    Видны: дорога, сооружения с подписями («ДСК» и отметка), уступ «Горизонт +410»
    с отметками, граница горного отвода, «Блок 48 факт» (чужой блок), сетка,
    «Отметки рельеф» (одни точки). Скрыты: «Блок 42 факт» (выключен), «КПП»
    (выключен — но объект на поверхности), «Склады_2023» (заморожен).
    """

    x0, y0 = X0, Y0
    doc = ezdxf.new("R2010")
    for name in ("Блок 42 факт 05_12_2023", "КПП"):
        doc.layers.add(name).off()
    doc.layers.add("Склады_2023").freeze()
    msp = doc.modelspace()
    msp.add_lwpolyline([(x0 - 300, y0 - 80), (x0 + 400, y0 - 60)], dxfattribs={"layer": "Дороги"})
    msp.add_lwpolyline([(x0 + 150, y0 + 150), (x0 + 190, y0 + 150), (x0 + 190, y0 + 180)], dxfattribs={"layer": "Сооружения"})
    msp.add_text("ДСК", dxfattribs={"layer": "Сооружения", "insert": (x0 + 160, y0 + 160)})
    msp.add_text("423.47", dxfattribs={"layer": "Сооружения", "insert": (x0 + 170, y0 + 170)})
    msp.add_lwpolyline([(x0 + 300, y0 + 300), (x0 + 310, y0 + 300), (x0 + 310, y0 + 310)], dxfattribs={"layer": "КПП"})
    msp.add_text("КПП", dxfattribs={"layer": "КПП", "insert": (x0 + 305, y0 + 305)})
    msp.add_polyline3d([(x0 - 50, y0, 420.5), (x0 + 50, y0 + 5, 420.8)], dxfattribs={"layer": "Горизонт +410"})
    msp.add_point((x0, y0 + 2, 420.6), dxfattribs={"layer": "Горизонт +410"})
    msp.add_text("420.60", dxfattribs={"layer": "Горизонт +410", "insert": (x0, y0 + 3)})
    msp.add_lwpolyline([(x0 - 500, y0 - 500), (x0 + 500, y0 - 500), (x0 + 500, y0 + 500)], dxfattribs={"layer": "Граница горного отвода"})
    msp.add_lwpolyline([(x0 + 10, y0 + 10), (x0 + 30, y0 + 10), (x0 + 30, y0 + 40)], close=True, dxfattribs={"layer": "Блок 48 факт 14.10.2024"})
    msp.add_lwpolyline([(x0 + 60, y0 + 10), (x0 + 80, y0 + 10)], dxfattribs={"layer": "Блок 42 факт 05_12_2023"})
    msp.add_lwpolyline([(x0 - 1000, y0), (x0 + 1000, y0)], dxfattribs={"layer": "Сетка координат_2000"})
    msp.add_lwpolyline([(x0 + 200, y0 - 200), (x0 + 260, y0 - 200)], dxfattribs={"layer": "Склады_2023"})
    for index in range(4):
        msp.add_point((x0 + 5 * index, y0 + 50, 421.0 + index), dxfattribs={"layer": "Отметки рельеф"})
    if extra_layer:
        msp.add_lwpolyline([(x0 + 100, y0 + 100), (x0 + 120, y0 + 100)], dxfattribs={"layer": extra_layer})
    return _bytes(doc)
