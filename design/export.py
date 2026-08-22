"""Экспорт паспорта БВР: таблица скважин в CSV и печатная форма паспорта."""
from __future__ import annotations

import csv
import html
import io
from typing import Any

from design.analysis import summary as run_summary
from design.geometry import polygon_area
from design.models import BlastDesign

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
            ]
        )
    return "﻿" + buffer.getvalue()


def _esc(value: Any) -> str:
    return html.escape(str(value))


def passport_html(design: BlastDesign) -> str:
    """Печатная форма паспорта БВР — самодостаточный HTML для просмотра/печати."""
    stats = run_summary(design)
    loads_by_hole = {load.hole_id: load for load in design.loads}

    rows = []
    for hole in design.holes:
        load = loads_by_hole.get(hole.id)
        rows.append(
            f"<tr>"
            f"<td>{_esc(hole.id)}</td>"
            f"<td>{_esc(hole.kind)}</td>"
            f"<td>{hole.collar.x:.2f}</td><td>{hole.collar.y:.2f}</td><td>{hole.collar.z:.2f}</td>"
            f"<td>{hole.length_m:.1f}</td>"
            f"<td>{hole.angle_deg:.0f}</td><td>{hole.azimuth_deg:.0f}</td>"
            f"<td>{hole.diameter_mm:.0f}</td>"
            f"<td>{f'{load.total_charge_kg:.1f}' if load else ''}</td>"
            f"<td>{f'{load.specific_q_kg_m3:.3f}' if load else ''}</td>"
            f"<td>{'да' if hole.enabled else 'нет'}</td>"
            f"</tr>"
        )

    area_m2 = polygon_area(design.contour.points_xy)

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Паспорт БВР — {_esc(design.name)}</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 24px; color: #17231d; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .subtitle {{ color: #6e7c75; font-size: 12px; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }}
  .grid div {{ border: 1px solid #dce4e0; border-radius: 8px; padding: 10px; }}
  .grid span {{ display: block; color: #78857f; font-size: 10px; margin-bottom: 4px; }}
  .grid strong {{ font-size: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 24px; }}
  th, td {{ border: 1px solid #e2e8e5; padding: 5px 7px; text-align: right; }}
  th {{ background: #f3f6f4; text-align: right; }}
  td:nth-child(1), td:nth-child(2), td:nth-child(12), th:nth-child(1), th:nth-child(2), th:nth-child(12) {{ text-align: left; }}
  .print-button {{ margin-bottom: 16px; padding: 8px 14px; border: 1px solid #2d7556; border-radius: 8px; background: #2d7556; color: #fff; font-weight: 700; cursor: pointer; }}
  @media print {{ .print-button {{ display: none; }} }}
</style>
</head>
<body>
  <button class="print-button" onclick="window.print()">Печать</button>
  <h1>Паспорт БВР — {_esc(design.name)}</h1>
  <div class="subtitle">
    Обновлён: {_esc(design.updated_at or "—")} · Порода: {_esc(design.rock_name or "—")} ·
    ВВ: {_esc(design.explosive_key or "—")} · Система инициирования: {_esc(design.network.system)}
  </div>

  <div class="grid">
    <div><span>Площадь блока</span><strong>{area_m2:.0f} м²</strong></div>
    <div><span>Объём блока</span><strong>{stats["block_volume_m3"]:.0f} м³</strong></div>
    <div><span>Рабочих скважин</span><strong>{stats["production_hole_count"]}</strong></div>
    <div><span>Контурных скважин</span><strong>{stats["contour_hole_count"]}</strong></div>
    <div><span>Погонаж бурения</span><strong>{stats["drilling_footage_m"]:.0f} м</strong></div>
    <div><span>Масса ВВ на блок</span><strong>{stats["total_charge_kg"]:.0f} кг</strong></div>
    <div><span>Средний уд. расход</span><strong>{stats["avg_specific_q_kg_m3"]:.3f} кг/м³</strong></div>
    <div><span>Скважин заряжено</span><strong>{stats["charged_hole_count"]} из {stats["hole_count"]}</strong></div>
    <div><span>Стартовых точек схемы</span><strong>{len(design.network.starters)}</strong></div>
    <div><span>Связей схемы</span><strong>{len(design.network.connectors)}</strong></div>
  </div>

  <table>
    <thead><tr>
      <th>ID</th><th>Тип</th><th>X, м</th><th>Y, м</th><th>Z устья, м</th>
      <th>Длина, м</th><th>Угол, °</th><th>Азимут, °</th><th>⌀, мм</th>
      <th>Заряд, кг</th><th>q, кг/м³</th><th>Активна</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</body></html>"""
