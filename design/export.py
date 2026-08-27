"""Экспорт паспорта БВР: таблица скважин в CSV и печатная форма паспорта."""
from __future__ import annotations

import csv
import io

from design.models import BlastDesign
from design.reporting.html import passport_html

CSV_COLUMNS = [
    "id",
    "row",
    "col",
    "kind",
    "collar_x_m",
    "collar_y_m",
    "collar_z_m",
    "toe_x_m",
    "toe_y_m",
    "toe_z_m",
    "depth_m",
    "angle_deg",
    "azimuth_deg",
    "diameter_mm",
    "subdrill_m",
    "charge_mass_kg",
    "specific_q_kg_m3",
    "geology_intervals",
    "water_intervals",
]


def holes_csv(design: BlastDesign) -> str:
    """Таблица скважин паспорта в формате CSV (запятая, UTF-8 с BOM для Excel)."""
    loads_by_hole = {load.hole_id: load for load in design.loads}

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for hole in design.holes:
        load = loads_by_hole.get(hole.id)
        writer.writerow(
            [
                hole.id,
                hole.row,
                hole.col,
                hole.kind,
                round(hole.collar.x, 3),
                round(hole.collar.y, 3),
                round(hole.collar.z, 3),
                round(hole.toe.x, 3),
                round(hole.toe.y, 3),
                round(hole.toe.z, 3),
                round(hole.length_m, 2),
                round(hole.angle_deg, 1),
                round(hole.azimuth_deg, 1),
                hole.diameter_mm,
                hole.subdrill_m,
                round(load.total_charge_kg, 1) if load else "",
                round(load.specific_q_kg_m3, 3) if load else "",
                "; ".join(
                    f"{iv.from_m:.1f}-{iv.to_m:.1f} {iv.domain_name or iv.domain_id}"
                    for iv in hole.intervals
                ),
                "; ".join(
                    f"{iv.from_m:.1f}-{iv.to_m:.1f} {iv.condition}"
                    for iv in hole.water_intervals
                ),
            ]
        )
    return "﻿" + buffer.getvalue()


__all__ = ["CSV_COLUMNS", "holes_csv", "passport_html"]
