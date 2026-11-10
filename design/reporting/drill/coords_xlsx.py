"""Ведомость координат скважин — XLSX в формате маркшейдера (TASK-015, PR 5).

Формат — таблица маркшейдера блока 66 (решение владельца 10.11.2026): сверху
сводка, ниже ID, X, Y, Z, проектная глубина, перебур, высота уступа; справа —
Z забоя, угол β и азимут (у вертикальных пусто). X — восток, Y — север. ID —
номер скважины паспорта, номер из одних цифр пишется числом. Сводка — числами
из снимка (как в паспорте), а не формулами: файл читается и программами,
которые формулы не считают.

Повтор той же ревизии — те же байты: даты свойств документа — дата паспорта,
время записей zip постоянное (`archive.fixed_zip`).
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.writer.excel import ExcelWriter

from design.reporting.drill.archive import fixed_zip
from design.reporting.drill.coords import coords_header, coords_rows

__all__ = ["XLSX_HEADERS", "render_coords_xlsx"]

SHEET = "Координаты"
XLSX_HEADERS = (
    "ID", "X (восток)", "Y (север)", "Z", "Проектная глубина", "Перебур", "Высота уступа",
    "Z забоя", "Угол β, °", "Азимут, °",
)
FORMATS = ("@", "0.000", "0.000", "0.000", "0.0", "0.0", "0.0", "0.000", "0", "0")
WIDTHS = (10, 14, 14, 10, 12, 10, 10, 10, 9, 10)
# Даты свойств документа, когда у паспорта нет даты.
FALLBACK_DATE = datetime(2000, 1, 1)
HEAD_FILL = PatternFill("solid", fgColor="2E3237")


def _created(context: Mapping[str, Any]) -> datetime:
    text = str((context.get("passport") or {}).get("passport_date") or "")
    try:
        return datetime.fromisoformat(text[:10])
    except ValueError:
        return FALLBACK_DATE


def _summary_rows(summary: Mapping[str, Any]) -> list[tuple[str, float | int | None, str]]:
    count = summary.get("hole_count") or 0
    total = summary.get("total_length_m")
    return [
        ("Объём буровых работ, п. м", total, "0.0"),
        ("Количество скважин", count, "0"),
        ("Средняя глубина скважин, м", total / count if total is not None and count else None, "0.00"),
        ("Средняя высота уступа, м", summary.get("bench_height_avg_m"), "0.00"),
        ("Площадь блока, м²", summary.get("block_area_m2"), "0.0"),
        ("Объём блока, м³", summary.get("block_volume_m3"), "0"),
        ("Выход горной массы с 1 п. м, м³", summary.get("yield_m3_per_m"), "0.00"),
    ]


def _number_id(number: str) -> int | str:
    return int(number) if number.isascii() and number.isdigit() else number


def render_coords_xlsx(context: Mapping[str, Any], *, revision_no: int | None = None) -> bytes:
    header, crs = coords_header(context)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    sheet.append([f"Ведомость координат скважин · {header}" + (f" · ревизия {revision_no}" if revision_no else "")])
    sheet["A1"].font = Font(bold=True)
    sheet.append([f"{crs}. X — восток, Y — север; координаты в СК объекта без пересчёта."])
    sheet.append([])
    for label, value, number_format in _summary_rows(context.get("summary") or {}):
        sheet.append([label, None, None, None, value])
        row = sheet.max_row
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        sheet.cell(row, 5).number_format = number_format
    sheet.append([])
    sheet.append(list(XLSX_HEADERS))
    head_row = sheet.max_row
    for cell in sheet[head_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in coords_rows(context):
        sheet.append([
            _number_id(row.number), round(row.x, 3), round(row.y, 3), round(row.z_collar, 3), round(row.depth_m, 3),
            round(row.subdrill_m, 3), round(row.bench_m, 3), round(row.z_toe, 3),
            None if row.dip_deg is None else round(row.dip_deg),
            None if row.azimuth_deg is None else round(row.azimuth_deg) % 360,
        ])
        for cell, number_format in zip(sheet[sheet.max_row], FORMATS):
            if isinstance(cell.value, str):
                # Номер скважины — всегда текст: «=…» из ручного номера
                # openpyxl иначе записал бы формулой.
                cell.data_type = "s"
            else:
                cell.number_format = number_format if number_format != "@" else "General"
    for index, width in enumerate(WIDTHS):
        sheet.column_dimensions[chr(ord("A") + index)].width = width
    sheet.freeze_panes = sheet.cell(head_row + 1, 1)
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = f"{head_row}:{head_row}"

    created = _created(context)
    workbook.properties.creator = "BlastEX"
    workbook.properties.lastModifiedBy = "BlastEX"
    workbook.properties.title = "Ведомость координат скважин"
    workbook.properties.created = created
    workbook.properties.modified = created
    output = io.BytesIO()
    # Не `workbook.save`: он ставит «изменён» — текущее время, и байты
    # повторного выпуска расходились бы.
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        ExcelWriter(workbook, archive).save()
    return fixed_zip(output.getvalue())
