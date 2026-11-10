"""Ведомость координат скважин для маркшейдера (TASK-015, PR 5, спека §5)."""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from design.reporting.drill.coords import (
    FIRST_PAGE_ROWS,
    PAGE_ROWS,
    CoordsRow,
    coords_header,
    coords_pages,
    coords_rows,
)
from design.reporting.drill.coords_pdf import render_coords_pdf
from tests.drill_passport_context import context66, with_holes


def _pdf_text(pdf: bytes, tmp_path: Path) -> str:
    if shutil.which("pdftotext") is None:
        pytest.skip("Нет pdftotext")
    path = tmp_path / "coords.pdf"
    path.write_bytes(pdf)
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True).stdout


def _pdf_info(pdf: bytes, tmp_path: Path) -> str:
    if shutil.which("pdfinfo") is None:
        pytest.skip("Нет pdfinfo")
    path = tmp_path / "coords.pdf"
    path.write_bytes(pdf)
    return subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True).stdout


def test_coords_rows_block66() -> None:
    rows = coords_rows(context66())
    assert len(rows) == 196
    first = rows[0]
    assert isinstance(first, CoordsRow)
    assert (first.number, first.row) == ("1", 1)
    assert (first.x, first.y, first.z_collar) == pytest.approx((1472880.04, 593722.99, 419.21), abs=0.005)
    assert (first.bench_m, first.depth_m, first.subdrill_m) == pytest.approx((9.2, 10.7, 1.5), abs=0.005)
    assert first.z_toe == pytest.approx(408.51, abs=0.005)
    assert first.dip_deg is None and first.azimuth_deg is None
    assert sum(1 for row in rows if row.row == 1) == 44
    assert {row.row for row in rows} == {1, 2}


def test_coords_header() -> None:
    header, crs = coords_header(context66())
    assert header == "Паспорт на бурение № 66-26/Б · блок № 66 · гор. +410,0"
    assert crs.startswith("СК не задана")
    context = context66()
    del context["crs"]
    assert coords_header(context)[1] == "СК не сохранена в ревизии"


def test_coords_pages_split() -> None:
    rows = coords_rows(with_holes(context66(), 401))
    pages = coords_pages(rows)
    assert len(pages[0]) == FIRST_PAGE_ROWS
    assert all(len(page) <= PAGE_ROWS for page in pages[1:])
    assert sum(len(page) for page in pages) == 401
    assert len(pages) == 1 + math.ceil((401 - FIRST_PAGE_ROWS) / PAGE_ROWS)


def test_coords_pdf_block66(tmp_path) -> None:
    pdf = render_coords_pdf(context66(), revision_no=1)
    assert pdf == render_coords_pdf(context66(), revision_no=1)
    info = _pdf_info(pdf, tmp_path)
    assert "841.89 x 595.276" in info or "842 x 595" in info
    pages = 1 + math.ceil((196 - FIRST_PAGE_ROWS) / PAGE_ROWS)
    assert f"Pages:           {pages}" in info
    text = _pdf_text(pdf, tmp_path)
    for needle in (
        "Ведомость координат скважин",
        "X (восток)",
        "Y (север)",
        "1472880.040",
        "593722.990",
        "419.210",
        "408.510",
        f"стр. 1 из {pages}",
        "Паспорт на бурение № 66-26/Б",
    ):
        assert needle in text, needle


def test_coords_pdf_many_holes(tmp_path) -> None:
    pdf = render_coords_pdf(with_holes(context66(), 401), revision_no=1)
    pages = 1 + math.ceil((401 - FIRST_PAGE_ROWS) / PAGE_ROWS)
    assert f"Pages:           {pages}" in _pdf_info(pdf, tmp_path)
    text = _pdf_text(pdf, tmp_path)
    # Шапка таблицы — на каждой странице.
    assert text.count("Глубина Ф") == pages
    assert f"стр. {pages} из {pages}" in text


def test_coords_pdf_old_revision(tmp_path) -> None:
    context = context66()
    del context["crs"]
    assert "СК не сохранена в ревизии" in _pdf_text(render_coords_pdf(context, revision_no=1), tmp_path)


def test_coords_pdf_inclined_angles(tmp_path) -> None:
    from tests.test_export_survey_stakeout import _inclined

    context = _inclined(context66())
    row = coords_rows(context)[100]
    assert (row.dip_deg, row.azimuth_deg) == (75.0, 120.0)
    text = _pdf_text(render_coords_pdf(context, revision_no=1), tmp_path)
    line = next(line for line in text.splitlines() if line.split()[:1] == [context["holes"][100]["number"]])
    assert line.split()[-2:] == ["75", "120"]


def test_coords_pages_are_not_shrunk(monkeypatch) -> None:
    """Строк на листе ровно столько, сколько помещается: лист не ужимается."""

    from reportlab.platypus import KeepInFrame

    scales: list[float] = []
    original = KeepInFrame.wrap

    def wrap(self, available_width, available_height):
        result = original(self, available_width, available_height)
        scales.append(getattr(self, "_scale", 1.0) or 1.0)
        return result

    monkeypatch.setattr(KeepInFrame, "wrap", wrap)
    render_coords_pdf(with_holes(context66(), 100), revision_no=1)
    assert scales and all(scale <= 1.0 for scale in scales)


# --- XLSX в формате маркшейдера ---------------------------------------------

import io
import zipfile

import openpyxl

from design.reporting.drill.coords_xlsx import XLSX_HEADERS, render_coords_xlsx


def _sheet(data: bytes):
    workbook = openpyxl.load_workbook(io.BytesIO(data))
    assert workbook.sheetnames == ["Координаты"]
    return workbook, workbook["Координаты"]


def _summary(sheet) -> dict[str, object]:
    values = {}
    for row in sheet.iter_rows(values_only=True):
        if row[0] == "ID":
            break
        if row[0]:
            values[row[0]] = row[4]
    return values


def _data_rows(sheet) -> list[tuple]:
    rows = list(sheet.iter_rows(values_only=True))
    start = next(index for index, row in enumerate(rows) if row[0] == "ID")
    assert tuple(rows[start][: len(XLSX_HEADERS)]) == XLSX_HEADERS
    return [row[: len(XLSX_HEADERS)] for row in rows[start + 1:] if row[0] is not None]


def test_coords_xlsx_block66() -> None:
    _, sheet = _sheet(render_coords_xlsx(context66(), revision_no=1))
    assert XLSX_HEADERS == (
        "ID", "X (восток)", "Y (север)", "Z", "Проектная глубина", "Перебур", "Высота уступа",
        "Z забоя", "Угол β, °", "Азимут, °",
    )
    summary = _summary(sheet)
    assert summary["Объём буровых работ, п. м"] == pytest.approx(2280.5)
    assert summary["Количество скважин"] == 196
    assert summary["Площадь блока, м²"] == pytest.approx(2790)
    assert summary["Объём блока, м³"] == pytest.approx(29366, abs=1)
    assert summary["Выход горной массы с 1 п. м, м³"] == pytest.approx(12.88, abs=0.01)
    rows = _data_rows(sheet)
    assert len(rows) == 196
    first = rows[0]
    assert first[0] == 1
    assert first[1:8] == pytest.approx((1472880.04, 593722.99, 419.21, 10.7, 1.5, 9.2, 408.51), abs=0.001)
    assert first[8:] == (None, None)
    for row in sheet.iter_rows():
        for cell in row:
            assert not (isinstance(cell.value, str) and cell.value.startswith("=")), cell.coordinate


def test_coords_xlsx_passport_numbers_stay_text() -> None:
    context = context66()
    context["holes"][0]["number"] = "1-01"
    rows = _data_rows(_sheet(render_coords_xlsx(context, revision_no=1))[1])
    assert rows[0][0] == "1-01"
    assert rows[1][0] == 2


def test_coords_xlsx_repeatable() -> None:
    data = render_coords_xlsx(context66(), revision_no=1)
    assert data == render_coords_xlsx(context66(), revision_no=1)
    workbook, _ = _sheet(data)
    assert workbook.properties.created.date().isoformat() == "2026-10-05"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_coords_xlsx_opens_in_libreoffice(tmp_path) -> None:
    import csv

    from tests.libreoffice import convert

    source = tmp_path / "coords.xlsx"
    source.write_bytes(render_coords_xlsx(context66(), revision_no=1))
    # Разделитель «,», UTF-8, значения ячеек, а не их вид; десятичный знак —
    # по локали LibreOffice, поэтому числа сравниваются после замены «,».
    target = "csv:Text - txt - csv (StarCalc):44,34,76,1,,1033,false,true,false"
    with convert(source, target, tmp_path).open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.reader(stream) if row and row[0].isdigit()]
    assert len(rows) == 196
    values = [float(value.replace(",", ".")) for value in rows[0][1:8]]
    assert rows[0][0] == "1"
    assert values == pytest.approx([1472880.04, 593722.99, 419.21, 10.7, 1.5, 9.2, 408.51], abs=0.001)
