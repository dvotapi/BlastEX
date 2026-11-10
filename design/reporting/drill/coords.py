"""Ведомость координат скважин для маркшейдера как данные (TASK-015, PR 5, §5).

Только из снимка ревизии: строки таблицы скважин паспорта в его порядке.
Рисуют её `coords_pdf` (альбомный лист по эталону v0.6, для поля) и
`coords_xlsx` (таблица в формате маркшейдера). Ряд — как в эталоне: 1 —
первый ряд паспорта (у бровки), 2 — остальные.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from design.reporting.drill.layout import crs_line, passport_header

__all__ = [
    "FIRST_PAGE_ROWS",
    "PAGE_ROWS",
    "CoordsRow",
    "coords_header",
    "coords_pages",
    "coords_rows",
]

# Строк на альбомном листе: на первом выше таблицы — заголовок и пояснение.
FIRST_PAGE_ROWS = 27
PAGE_ROWS = 32


@dataclass(frozen=True)
class CoordsRow:
    number: str
    row: int
    x: float
    y: float
    z_collar: float
    bench_m: float
    depth_m: float
    subdrill_m: float
    z_toe: float
    # Только у наклонных; у вертикальных — None (пустая графа).
    dip_deg: float | None
    azimuth_deg: float | None


def _point(value: Mapping[str, Any]) -> tuple[float, float, float]:
    return float(value["x"]), float(value["y"]), float(value["z"])


def _z_toe(row: Mapping[str, Any], z_collar: float) -> float:
    if row.get("toe"):
        return _point(row["toe"])[2]
    # Ревизия до PR 3: забой по длине и углу.
    dip = float(row.get("dip_deg") or 90.0)
    return z_collar - float(row["length_m"]) * math.sin(math.radians(dip))


def coords_rows(context: Mapping[str, Any]) -> list[CoordsRow]:
    rows: list[CoordsRow] = []
    for row in context.get("holes") or []:
        x, y, z = _point(row["collar"])
        inclined = row.get("azimuth_deg") is not None
        rows.append(
            CoordsRow(
                number=str(row["number"]),
                row=1 if row.get("first_row") else 2,
                x=x,
                y=y,
                z_collar=z,
                bench_m=float(row["bench_height_m"]),
                depth_m=float(row["length_m"]),
                subdrill_m=float(row["subdrill_m"]),
                z_toe=_z_toe(row, z),
                dip_deg=float(row["dip_deg"]) if inclined else None,
                azimuth_deg=float(row["azimuth_deg"]) if inclined else None,
            )
        )
    return rows


def coords_header(context: Mapping[str, Any]) -> tuple[str, str]:
    """Шапка листов (паспорт, блок, горизонт) и строка СК и системы высот."""

    return passport_header(context), crs_line(context.get("crs"))


def coords_pages(rows: list[CoordsRow]) -> list[list[CoordsRow]]:
    """Строки по листам: на первом — `FIRST_PAGE_ROWS`, дальше — `PAGE_ROWS`."""

    pages = [rows[:FIRST_PAGE_ROWS]]
    rest = rows[FIRST_PAGE_ROWS:]
    pages += [rest[start:start + PAGE_ROWS] for start in range(0, len(rest), PAGE_ROWS)]
    return pages
