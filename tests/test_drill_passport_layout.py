"""Раскладка PDF паспорта на бурение по форме v0.7 (TASK-015, PR 2)."""
from __future__ import annotations

from copy import deepcopy

import pytest

from design.reporting.drill.layout import build_layout
from tests.drill_passport_context import PAYLOAD_V07, context66, with_holes

NBSP = " "


@pytest.fixture(scope="module")
def layout66():
    return build_layout(context66())


def test_header_and_pages(layout66):
    assert layout66.header == "Паспорт на бурение № 66-26/Б · блок № 66 · гор. +410,0"
    assert layout66.page_count == 4
    assert layout66.blank_before_plan is False
    assert len(layout66.depth_pages) == 1


def test_title_page(layout66):
    title = layout66.title
    assert title.agreed == ("главный инженер", "ООО «Месторождение Жуков Камень»", "Литун А.К.")
    assert title.approved == ("технический директор", "ООО «Комплексные решения»", "Гизатуллин Р.Р.")
    assert title.passport_no == "66-26/Б"
    assert title.object_name == "Месторождение «Жуков Камень»"
    assert title.customer == "ООО «Месторождение Жуков Камень»"
    assert title.summary == (
        ("Блок / горизонт", "66 / +410,0 м"),
        ("Начало бурения", "06.10.2026"),
        ("Окончание бурения (план)", "12.10.2026"),
        ("Буровая установка", "JK830-2"),
        ("Диаметр инструмента, мм", "140"),
        ("Сетка скважин, м", "3,7 × 3,7"),
        ("Скважин, шт", "196"),
        ("Объём бурения, п. м", f"2{NBSP}280,5"),
    )
    assert title.approvals == ("маркшейдер [Фамилия И. О.]", "геолог [Фамилия И. О.]")
    assert len(title.acquaintance) == 8
    assert title.acquaintance[1] == ("Маланичев П.В.", "машинист буровой установки")
    assert title.acquaintance[4] == ("", "")
    assert title.basis == "Составлен на основании: ТП ВМ.09.01 ред. [ ]; проект МВ № 66-26"
    assert title.org_year == "ООО «Комплексные решения», 2026 г."


def test_safety_page(layout66):
    safety = layout66.safety
    assert len(safety.items) == 10
    assert safety.items[0].startswith("Работать только по утверждённому паспорту")
    assert safety.basis == "Основание: ФНП 505 пп. 989–991, 993; ФНП 494 п. 187."
    assert [label for label, _ in safety.work_order] == [
        "Подготовка площадки", "Вынос точек", "Порядок обуривания", "Въезд и перегон",
        "ЛЭП и кабели", "Соседние работы", "Приёмка блока",
    ]
    assert dict(safety.work_order)["ЛЭП и кабели"] == "нет"
    assert safety.s_text == "s = 2,0 м"


def test_depth_page(layout66):
    page = layout66.depth_pages[0]
    params = dict(page.params)
    assert params == {
        "Угол наклона скважин": "90° (вертикальные)",
        "Глубина скважин, м": "10,0 – 13,8",
        "Перебур: 1-й ряд / остальные, м": "1,5 / 1",
        "Средняя высота уступа, м": "10,5",
        "Площадь блока, м²": f"2{NBSP}790",
        "Объём блока, м³": f"29{NBSP}366",
        "Выход горной массы, м³/п. м": "12,88",
    }
    assert page.tolerances == "глубина ±0,3 м; положение устья ±0,3 м"
    assert page.technology.startswith("В раздробленных и обводнённых породах")
    assert [len(column) for column in page.columns] == [50, 50, 50, 46]
    first = page.columns[0][0]
    assert (first.number, first.depth, first.angle, first.azimuth, first.first_row) == ("1", "10,7", "", "", True)
    assert sum(cell.first_row for column in page.columns for cell in column) == 44
    assert page.total == f"Всего: 196 скв., 2{NBSP}280,5 п. м"
    assert page.compiled_by == "инженер-проектировщик Плаксин А.И."


def test_engineer_values_are_not_printed(layout66):
    text = repr(layout66)
    for banned in ("c_min", "ЛСПП", "W =", "Wпред", "5,14", "1,2 м"):
        assert banned not in text


@pytest.mark.parametrize(
    ("count", "pages", "blank", "total"),
    [(200, 1, False, 4), (201, 2, True, 6), (400, 2, True, 6), (401, 3, False, 6), (601, 4, True, 8)],
)
def test_more_than_200_holes(count, pages, blank, total):
    layout = build_layout(with_holes(context66(), count))
    assert len(layout.depth_pages) == pages
    assert layout.blank_before_plan is blank
    assert layout.page_count == total
    assert layout.depth_pages[0].params is not None
    assert all(page.params is None for page in layout.depth_pages[1:])
    assert all(page.total is None for page in layout.depth_pages[:-1])
    assert layout.depth_pages[-1].total.startswith(f"Всего: {count} скв.")
    numbers = [cell.number for page in layout.depth_pages for column in page.columns for cell in column]
    assert numbers == [str(n) for n in range(1, count + 1)]
    plan_page = 2 + pages + (1 if blank else 0) + 1
    assert plan_page % 2 == 0


def test_inclined_holes_show_angle_and_azimuth():
    context = context66()
    context["holes"][0].update(dip_deg=75.0, azimuth_deg=123.4)
    context["summary"].update(vertical_only=False, dip_min_deg=75.0, dip_max_deg=90.0)
    layout = build_layout(context)
    cell = layout.depth_pages[0].columns[0][0]
    assert (cell.angle, cell.azimuth) == ("75", "123")
    other = layout.depth_pages[0].columns[0][1]
    assert (other.angle, other.azimuth) == ("", "")
    assert dict(layout.depth_pages[0].params)["Угол наклона скважин"] == "75 – 90°"


def test_empty_payload_prints_dashes():
    context = context66({})
    context["summary"].update(block_area_m2=None, block_volume_m3=None, yield_m3_per_m=None,
                              grid_a_m=None, grid_b_m=None, bit_diameter_mm=None)
    layout = build_layout(context)
    summary = dict(layout.title.summary)
    assert summary["Блок / горизонт"] == "—"
    assert summary["Начало бурения"] == "—"
    assert summary["Буровая установка"] == "—"
    assert summary["Сетка скважин, м"] == "—"
    assert summary["Диаметр инструмента, мм"] == "—"
    params = dict(layout.depth_pages[0].params)
    assert params["Объём блока, м³"] == "—"
    assert params["Выход горной массы, м³/п. м"] == "—"
    assert layout.title.approvals == ()
    assert len(layout.title.acquaintance) == 9
    assert layout.header == "Паспорт на бурение № 66-26/Б"
    assert layout.depth_pages[0].tolerances == "глубина ±0,3 м; положение устья ±0,3 м"


def test_rig_number_and_many_people():
    payload = deepcopy(PAYLOAD_V07)
    payload["rig_number"] = "12"
    payload["personnel"] = [{"name": f"Иванов {n}", "position": "машинист"} for n in range(12)]
    payload["extra_approvals"] = ["маркшейдер Петров", ""]
    layout = build_layout(context66(payload))
    assert dict(layout.title.summary)["Буровая установка"] == "JK830-2 № 12"
    assert len(layout.title.acquaintance) == 12
    assert layout.title.approvals == ("маркшейдер Петров",)


def test_old_snapshot_without_profile_uses_default_texts():
    context = context66()
    del context["profile"]
    for key in ("grid_a_m", "grid_b_m", "bit_diameter_mm"):
        del context["summary"][key]
    layout = build_layout(context)
    assert len(layout.safety.items) == 10
    assert dict(layout.title.summary)["Диаметр инструмента, мм"] == "140"
