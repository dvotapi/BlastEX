"""Документы проекта МВ v2 и дня взрыва (TASK-018, PR 3) на блоке 66 против формы v0.11.

Рендер печатает только данные ревизии — значения сверяются в тестах PR 1–2;
здесь — состав комплекта, раскладка (63 / 73 скважины, лицевая страница
каждого документа, линия отреза талона), повторяемость байтов и вид:
титул — растром против эталонного PDF формы (стр. 5), первая страница
техрасчёта — против одобренного PNG (вёрстка LibreOffice эталона в 2 % не
повторяется, решение владельца В5).
"""
from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest

from design.mass_blast_layers import layer_seed, naryad_lines, naryad_totals
from design.reporting.mass_blast import frame
from design.reporting.mass_blast.layers import render_layer_document
from design.reporting.mass_blast.package import render_package
from design.reporting.mass_blast.param_table import paginate
from design.reporting.mass_blast.project import project_parts, render_project_document
from tests.mass_blast_block66 import context66, payload66

pdfium = pytest.importorskip("pypdfium2")

FIXTURES = Path(__file__).parent / "fixtures" / "mass_blast"
FORM_PDF = FIXTURES / "form_v0.11_block66.pdf"
GOLDEN = FIXTURES / "golden"
# Растр: 100 dpi, оттенки серого, размытие 1 px, разница больше 25 % яркости.
RASTER_DPI = 100
RASTER_THRESHOLD = 0.02

REQUISITES = {
    "project_no": "66-26",
    "project_date": "2026-10-12",
    "tp_basis": "типовой проект БВР ООО «Месторождение Жуков Камень» (в разработке) [№, ред., дата]",
    "customer_name": "ООО «Месторождение Жуков Камень»",
    "contractor_name": "ООО «Комплексные решения»",
    "customer_approver": {"position": "главный инженер", "name": "Литун А.К.", "is_head": True},
    "contractor_approver": {"position": "технический директор", "name": "Гизатуллин Р.Р.", "is_head": True},
    "made_by": {"position": "инженер-проектировщик", "name": "Плаксин А.И."},
    "checked_by": {"position": "исполнительный директор", "name": "Ипатов Д.Ю."},
    "agreements": [{"position": "маркшейдер", "name": "[Фамилия И. О.]"}, {"position": "геолог", "name": "[Фамилия И. О.]"}],
}
NOTIFICATION = {
    "recipient_position": "Руководителю Уральского управления Ростехнадзора", "recipient_name": "Таранову А.Н.",
    "salutation": "Уважаемый Андрей Николаевич!", "signer": "исполнительный директор Ипатов Д.Ю.",
}


@pytest.fixture(scope="module")
def context() -> dict:
    return context66(payload=payload66(requisites=REQUISITES))


@pytest.fixture(scope="module")
def project_pdf(context) -> bytes:
    return render_project_document(context, "project")


def _pages(pdf: bytes) -> list:
    document = pdfium.PdfDocument(pdf)
    return [document[index] for index in range(len(document))]


def _text(page) -> str:
    return page.get_textpage().get_text_range()


def _raster(source, index: int, dpi: int = RASTER_DPI):
    from PIL import ImageFilter

    document = pdfium.PdfDocument(source)
    image = document[index].render(scale=dpi / 72).to_pil().convert("L")
    return image.filter(ImageFilter.GaussianBlur(1))


def _difference(a, b) -> float:
    from PIL import ImageChops

    assert a.size == b.size
    diff = ImageChops.difference(a, b).point(lambda value: 255 if value > 64 else 0)
    return diff.histogram()[255] / (diff.width * diff.height)


def _layer_revision(context: dict, kind: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    seed = layer_seed(kind, context, notification=NOTIFICATION if kind == "NOTIFICATION" else None)
    view: dict = {}
    if kind == "NARYAD":
        view["lines"] = naryad_lines(seed, payload, {"primers": 2, "nsi": 3, "starters": 2})
        view["totals"] = naryad_totals(seed, view["lines"])
    if kind == "NOTIFICATION":
        view["addressee"] = NOTIFICATION
    return {"kind": kind, "seed": seed, "payload": payload, "view": view}


# --- раскладка комплекта ----------------------------------------------------

def test_table_pages_split_63_73():
    assert paginate(196) == [(0, 63), (63, 136), (136, 196)]
    assert paginate(197) == [(0, 63), (63, 136), (136, 197)]   # эталон: 63 + 73 + 61
    assert paginate(63) == [(0, 63)]
    assert paginate(0) == [(0, 0)]


def test_project_documents_and_blank_versos(context):
    parts = project_parts(context)
    counts = [frame.count_pages(part) for part in parts]
    assert [part.key for part in parts] == ["title", "techcalc:0", "table:0", "schedule"]
    # Как эталон v0.11: титул + «Состав проекта» 2, техрасчёт 2, таблица 3 (+ пустой оборот), распорядок 2.
    assert counts == [2, 2, 3, 2]
    slots = frame.plan_pages(parts, counts, duplex=True)
    assert len(slots) == 10
    blanks = [index for index, slot in enumerate(slots) if slot.page is None]
    assert blanks == [7]
    # Каждый документ начинается с лицевой (нечётной) страницы.
    starts = [index for index, slot in enumerate(slots) if slot.page == 0]
    assert all(index % 2 == 0 for index in starts)
    assert [slot.number for slot in slots] == [f"Стр. {n} из 10" for n in range(1, 11)]


def test_layer_numbering_is_own_and_blank_has_no_number(context):
    parts = project_parts(context)[:1]
    layer = frame.Part(key="layer", label="Талон-допуск", title="", story=lambda: [], numbering="own")
    slots = frame.plan_pages(parts + [layer], [2, 1], duplex=True)
    assert [slot.number for slot in slots] == ["Стр. 1 из 2", "Стр. 2 из 2", "Стр. 1 из 1", ""]


def test_project_pdf_pages_and_texts(project_pdf):
    pages = _pages(project_pdf)
    assert len(pages) == 10
    texts = [_text(page) for page in pages]
    assert "ПРОЕКТ МАССОВОГО ВЗРЫВА" in texts[0] and "№ 66-26" in texts[0]
    assert "Состав проекта" in texts[1] and "Г.5" in texts[1]
    techcalc = texts[2] + texts[3]
    for number in range(1, 18):
        if number in (10, 11, 12):
            continue
        assert f"{number}. " in techcalc or f"{number}." in techcalc, number
    assert "10–12." in techcalc
    # Совпадает с формой v0.11 (значения — данные PR 1–2): P, r_в, r_с.
    assert "18,24" in techcalc
    assert "Безопасное расстояние по остеклению (принято)" in techcalc and "50" in techcalc
    assert "Сейсмически безопасное расстояние (принято)" in techcalc and "100" in techcalc
    # Раздел 13 — с новой страницы.
    assert "13. " in texts[3] and "13. " not in texts[2]
    assert "ТАБЛИЦА ПАРАМЕТРОВ ВЗРЫВНЫХ РАБОТ" in texts[4]
    assert "Итого / среднее" in texts[6] and "скважин: 196" in texts[6]
    assert texts[7].strip().startswith("Страница оставлена пустой") or "Страница оставлена пустой" in texts[7]
    schedule = texts[8] + texts[9]
    assert "РАСПОРЯДОК ПРОВЕДЕНИЯ МАССОВОГО ВЗРЫВА" in schedule
    for marker in ("12:00", "13:00", "не ранее 13:15", "не ранее 13:30"):
        assert marker in schedule, marker
    for point in ("35.", "36.", "37."):
        assert point in schedule
    # Лист «Реквизиты» формы не печатается.
    assert not any("Реквизиты" in text for text in texts)


def test_composition_counts_sheets(project_pdf):
    text = _text(_pages(project_pdf)[1])
    assert "Технический расчёт" in text and "Таблица параметров взрывных работ" in text
    # Листов: техрасчёт 2, таблица 3, распорядок 2; графика (PR 4) — «—».
    tokens = text.split()
    assert tokens.count("—") >= 5


def test_common_entry_prints_diameter_once_per_page(project_pdf):
    # Стр. 1–2 таблицы — скважины 1–136 (на стр. 3 «144» — ещё и номер скважины).
    for index in (4, 5):
        assert _text(_pages(project_pdf)[index]).split().count("144") == 1


def test_project_pdf_is_byte_stable(context, project_pdf):
    assert render_project_document(copy.deepcopy(context), "project") == project_pdf


def test_single_documents_have_own_numbering(context):
    pdf = render_project_document(context, "parameter-table")
    pages = _pages(pdf)
    assert len(pages) == 3
    assert "Стр. 3 из 3" in _text(pages[2])
    with pytest.raises(ValueError):
        render_project_document(context, "graphics")


def test_draft_mark_on_every_page(context):
    pages = _pages(render_project_document(context, "schedule", draft=True))
    assert all("ЧЕРНОВИК" in _text(page) for page in pages)


def test_title_matches_form_raster(context):
    # Числа формы (197 скважин, 29 366 м³, 32 830 кг, 700 / 500 м) — данными:
    # рендер печатает контекст как есть, и сравнивается только вёрстка.
    data = copy.deepcopy(context)
    data["totals"]["block_volume_m3"] = 29366
    totals = data["blocks_v2"][0]["parameter_table"]["totals"]
    totals.update(hole_count=197, charge_kg=32830)
    data["zones"]["people"]["value"] = 700
    data["zones"]["mechanisms"]["value"] = 500
    ours = _raster(render_project_document(data, "title"), 0)
    form = _raster(str(FORM_PDF), 4)
    assert _difference(ours, form) <= RASTER_THRESHOLD


def test_techcalc_first_page_matches_golden(project_pdf):
    from PIL import Image, ImageFilter

    ours = _raster(project_pdf, 2)
    golden = Image.open(GOLDEN / "techcalc-1.png").convert("L").filter(ImageFilter.GaussianBlur(1))
    assert _difference(ours, golden) <= RASTER_THRESHOLD


# --- документы дня взрыва ---------------------------------------------------

@pytest.mark.parametrize("kind", ["READINESS_ACT", "NOTIFICATION", "NARYAD", "TALON", "ACCEPTANCE_ACT"])
def test_layer_documents_one_page(context, kind):
    pdf = render_layer_document(_layer_revision(context, kind))
    pages = _pages(pdf)
    assert len(pages) == 1
    width, height = pages[0].get_size()
    assert (width > height) == (kind == "NARYAD")
    assert "Стр. 1 из 1" in _text(pages[0])
    assert render_layer_document(_layer_revision(context, kind)) == pdf


def test_naryad_reserve_and_issue(context):
    revision = _layer_revision(context, "NARYAD", {"number": "66-26", "reserve": {}})
    text = _text(_pages(render_layer_document(revision))[0])
    assert "НАРЯД-ПУТЁВКА № 66-26" in text
    assert "Запас (добавлен менеджером, входит в «Выписано»)" in text
    assert "ПД 2 шт" in text
    # Возврат ВВ, изготовляемых на месте, не печатается.
    site = _layer_revision(context, "NARYAD", {"vv_site": True})
    site["view"]["vv_site"] = True
    assert "—" in _text(_pages(render_layer_document(site))[0])


def test_talon_cut_line_in_the_middle(context):
    pdf = render_layer_document(_layer_revision(context, "TALON"))
    page = _pages(pdf)[0]
    text = _text(page)
    assert text.count("ТАЛОН-ДОПУСК") == 2
    assert "Экземпляр 1 — представителю заказчика" in text
    assert "Экземпляр 2 — руководителю взрывных работ (в дело проекта)" in text
    assert "линия отреза" in text
    import numpy as np

    scale = 3
    image = np.asarray(page.render(scale=scale).to_pil().convert("RGB")).astype(int)
    height, width = image.shape[:2]
    margin = int(15 * 72 / 25.4 * scale)
    band = image[int(height * 0.3):int(height * 0.7), margin:width - margin]
    # Линия отреза — серая (#6B7075) пунктирная: строка, где серого больше всего.
    grey = (np.abs(band - np.array([0x6B, 0x70, 0x75])).max(axis=2) <= 16).sum(axis=1)
    row = int(grey.argmax())
    assert grey[row] > 0.4 * band.shape[1]
    y = (row + int(height * 0.3)) / scale
    height = height / scale
    assert abs(y - height / 2) <= 5 * 72 / 25.4


def test_acceptance_act_volume_left_blank(context):
    text = _text(_pages(render_layer_document(_layer_revision(context, "ACCEPTANCE_ACT")))[0])
    assert "приёмки выполненных работ блока № 66" in text
    assert "по проекту (маркшейдерский контур)" in text
    assert "Приложение № [№]" in text


# --- PACKAGE ----------------------------------------------------------------

def test_package_order_and_manifest(context):
    layers = [
        {"kind": kind, "revision_no": 1, "context": _layer_revision(context, kind)}
        for kind in ("TALON", "NARYAD", "READINESS_ACT", "ACCEPTANCE_ACT", "NOTIFICATION")
    ]
    data = render_package(context, layers, manifest={"revision_id": "rev-1"})
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    assert names == [
        "00_Комплект.pdf", "01_Титул.pdf", "02_Технический_расчёт.pdf", "03_Таблица_параметров.pdf",
        "04_Распорядок.pdf", "06_Акт_готовности_блока.pdf", "07_Уведомление.pdf", "08_Наряд-путёвка.pdf",
        "09_Талон-допуск.pdf", "10_Акт_приёмки_работ.pdf", "manifest.json",
    ]
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["revision_id"] == "rev-1"
    assert [item["name"] for item in manifest["files"]] == names[:-1]
    combined = _pages(archive.read("00_Комплект.pdf"))
    # Проект 10 страниц + 5 слоёв по одной странице и пустому обороту.
    assert len(combined) == 20
    assert "Стр. 10 из 10" in _text(combined[9])
    assert "Стр. 1 из 1" in _text(combined[10])
    assert render_package(context, layers, manifest={"revision_id": "rev-1"}) == data


def test_user_text_does_not_become_markup(context):
    data = copy.deepcopy(context)
    data["project"]["blast_time"] = '13:00<img src="http://example.test/x.png"/>'
    data["project"]["object_name"] = "Карьер <b>«Тест»</b> & Ко"
    pdf = render_project_document(data, "parameter-table")
    # Узкая графа переносит строку — сравнение без пробелов и переводов строк.
    text = "".join(_text(_pages(pdf)[0]).split())
    assert '13:00<imgsrc="http://example.test/x.png"/>' in text
    assert "Карьер<b>«Тест»</b>&Ко" in text


def test_long_hole_note_stays_in_its_cell(context):
    data = copy.deepcopy(context)
    rows = data["blocks_v2"][0]["parameter_table"]["rows"]
    rows[0]["note"] = "снизить заряд"
    rows[1]["note"] = "снизить заряд на 10 кг, забойка 3 м"
    long_note = "снизить заряд до 120 кг, увеличить забойку до 3,5 м, проверить ЛСПП после зачистки бровки экскаватором"
    rows[2]["note"] = long_note
    pages = _pages(render_project_document(data, "parameter-table"))
    assert len(pages) == 3   # строки 63 / 73 не сдвигаются
    tail = "".join(_text(pages[-1]).split())
    assert "".join(f"№ {rows[2]['hole_id']} — {long_note}".split()) in tail
    first = "".join(_text(pages[0]).split())
    assert "снизитьзаряд" in first and "…*" in first


def test_naryad_prints_every_block(context):
    revision = _layer_revision(context, "NARYAD")
    block = revision["seed"]["blocks"][0]
    revision["seed"]["blocks"] = [{**block, "code": f"Б{n}"} for n in range(1, 8)]
    text = _text(_pages(render_layer_document(revision))[0])
    assert all(f"Б{n}" in text for n in range(1, 8))


def test_acceptance_appendix_from_payload(context):
    revision = _layer_revision(context, "ACCEPTANCE_ACT", {"appendix_no": "7"})
    assert "Приложение № 7" in _text(_pages(render_layer_document(revision))[0])


def test_naryad_keeps_fractional_kilograms(context):
    revision = _layer_revision(context, "NARYAD")
    primer = next(line for line in revision["view"]["lines"] if line["kind"] == "primer")
    primer.update(unit_mass_kg=0.9, issue_qty=2.0, issue_kg=1.8)
    text = _text(_pages(render_layer_document(revision))[0])
    assert "1,8" in text and "0,900" in text


def test_long_common_note_keeps_63_rows_on_first_page(context):
    data = copy.deepcopy(context)
    data["blocks_v2"][0]["parameter_table"]["common_note"] = "отсев; " * 80
    pages = _pages(render_project_document(data, "parameter-table"))
    assert len(pages) == 3
    first, second = _text(pages[0]), _text(pages[1])
    assert "общее для всех скважин: см. под таблицей" in first
    assert "№ скв." in second   # заголовок таблицы — на каждой странице
    assert "Общее для всех скважин: отсев" in _text(pages[2])


def test_package_names_are_unique_for_blocks_with_one_code(context):
    data = copy.deepcopy(context)
    data["blocks"] = data["blocks"] * 2
    data["blocks_v2"] = data["blocks_v2"] * 2
    archive = zipfile.ZipFile(io.BytesIO(render_package(data, [], manifest={})))
    names = archive.namelist()
    assert len(names) == len(set(names))
    assert sum(1 for name in names if name.startswith("02_")) == 2


def test_objects_table_prints_the_governing_factor(context):
    data = copy.deepcopy(context)
    section = next(s for s in data["blocks_v2"][0]["technical_calculation"] if s["number"] == "17")
    section["objects"] = [{
        "name": "ЛЭП 6 кВ", "kind": "structures", "kind_label": "сооружения", "factor": "сейсмика",
        "distance_m": 420.0, "required_m": 500.0, "position": "В ЗОНЕ",
    }]
    text = "".join(_text(_pages(render_project_document(data, "technical-calculation"))[1]).split())
    assert "ЛЭП6кВ" in text and "сооружения" in text and "сейсмика" in text and "ВЗОНЕ" in text


def test_naryad_prints_warehouse_permit_and_transport(context):
    payload = {"warehouse": "Склад ВМ № 2", "permit": "Разрешение № 17-ВР от 01.10.2026", "vehicle": "Урал 4320 А123ВС",
               "driver": "Сидоров П.П."}
    text = "".join(_text(_pages(render_layer_document(_layer_revision(context, "NARYAD", payload)))[0]).split())
    for value in payload.values():
        assert "".join(value.split()) in text


def test_schedule_prints_both_shift_boundaries(context):
    text = "".join(_text(_pages(render_project_document(context, "schedule"))[0]).split())
    assert "10:00–17:00" in text and "12:00" in text


def test_naryad_and_consumption_show_delays(context):
    revision = _layer_revision(context, "NARYAD")
    surface = next(line for line in revision["view"]["lines"] if line["kind"] == "nsi_surface")
    text = _text(_pages(render_layer_document(revision))[0])
    assert f"{surface['name']}, {int(surface['delay_ms'])} мс" in text
    techcalc = _text(_pages(render_project_document(context, "technical-calculation"))[0])
    assert f"{surface['name']}, {int(surface['delay_ms'])} мс" in techcalc


def test_long_readiness_remarks_stay_in_the_box(context):
    remarks = "Бровка у скважин 11–16 подработана, требуется зачистка экскаватором. " * 14
    revision = _layer_revision(context, "READINESS_ACT", {"remarks": remarks[:1000]})
    pages = _pages(render_layer_document(revision))
    text = "".join("".join(_text(page).split()) for page in pages)
    assert "".join(remarks[:200].split()) in text
    # Условия готовности над рамкой не перекрыты: текст условий читается целиком.
    assert "Забоечныйматериалзавезённаблоквтребуемомобъёме" in text


def test_naryad_material_rows_grow_with_block_distribution(context):
    from reportlab.lib.units import mm

    from design.reporting.mass_blast.layers import _naryad_materials

    revision = _layer_revision(context, "NARYAD")
    block = revision["seed"]["blocks"][0]
    revision["seed"]["blocks"] = [{**block, "code": f"Б{n}"} for n in range(1, 8)]
    table = _naryad_materials(revision, frame.frame_width(True))[1]
    lines = len(revision["view"]["lines"])
    material_rows = table._argH[2:2 + lines]
    assert all(height > 4.4 * mm for height in material_rows)
    text = _text(_pages(render_layer_document(revision))[0])
    assert all(f"Блок Б{n}" in text for n in range(1, 8))


def test_title_summary_rows_do_not_overlap_with_many_blocks(context, monkeypatch):
    from design.reporting.mass_blast import title

    data = copy.deepcopy(context)
    data["blocks"] = [{**data["blocks"][0], "code": str(code)} for code in range(66, 73)]
    placed: list[tuple[str, float, float]] = []
    original = title._put

    def record(canvas, value, style, x, top, width, page_h):
        height = original(canvas, value, style, x, top, width, page_h)
        if style == "value":
            placed.append((value, top, height))
        return height

    monkeypatch.setattr(title, "_put", record)
    render_project_document(data, "title")
    assert placed[0][2] > title._S["value"].leading   # список блоков перенёсся
    for (_, top, height), (_, next_top, _) in zip(placed, placed[1:]):
        assert next_top >= top + height


def test_acceptance_keeps_fractional_volume(context):
    revision = _layer_revision(context, "ACCEPTANCE_ACT", {"accepted_volume_m3": 1234.5})
    assert "1 234,5" in _text(_pages(render_layer_document(revision))[0])


def test_consumption_keeps_fractional_kilograms(context):
    data = copy.deepcopy(context)
    section = next(s for s in data["blocks_v2"][0]["technical_calculation"] if s["number"] == "10–12")
    line = next(item for item in section["consumption"] if item["kind"] == "explosive")
    line.update(quantity=60.4, mass_kg=60.4)
    text = _text(_pages(render_project_document(data, "technical-calculation"))[0])
    assert text.count("60,4") >= 2


def test_naryad_keeps_fractional_kilogram_quantity(context):
    revision = _layer_revision(context, "NARYAD")
    explosive = next(line for line in revision["view"]["lines"] if line["kind"] == "explosive")
    explosive.update(issue_qty=60.4, issue_kg=60.4, unit_mass_kg=1.0)
    text = _text(_pages(render_layer_document(revision))[0])
    assert text.count("60,4") >= 2
