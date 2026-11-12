"""«Графика» Г.1–Г.5 проекта МВ (TASK-018, PR 4): раскладка, масштаб, поворот, PDF.

Вид листов — растром против одобренных владельцем PNG блока 66
(`tests/fixtures/mass_blast/golden/g1.png … g5.png`, решение В10): страницы
формы v0.11 с нашими данными несравнимы (196 / 197 скважин, сеть проекта
вместо сети «по геометрии», зона 900 / 700 м). Обновить эталоны —
`BLASTEX_UPDATE_GOLDEN=1 pytest tests/test_mass_blast_render_graphics.py`.
"""
from __future__ import annotations

import copy
import math
import os
import random
from pathlib import Path

import pytest
from reportlab.graphics.shapes import Rect
from reportlab.lib.units import mm

from design.reporting import plan_sheet
from design.reporting.drill import plan as drill_plan
from design.reporting.mass_blast.graphics import graphics_part, plans, profiles, situation
from design.reporting.mass_blast.graphics.sheet import FIELD_H_MM, FIELD_PAD_MM, FIELD_W_MM, legend_band
from design.reporting.mass_blast.project import project_parts, render_project_document
from design.reporting.plan_sheet import PlanView, fit_view
from design.trunk_network import build_trunk_chains_network
from tests.mass_blast_block66 import context66, design66, payload66

pdfium = pytest.importorskip("pypdfium2")

GOLDEN = Path(__file__).parent / "fixtures" / "mass_blast" / "golden"
RASTER_DPI = 100
RASTER_THRESHOLD = 0.02
REQUISITES = {
    "project_no": "66-26",
    "made_by": {"position": "инженер-проектировщик", "name": "Плаксин А.И."},
    "surveyor_name": "[Фамилия И. О.]",
}


def _design66():
    design = design66()
    design.network, _warnings = build_trunk_chains_network(design.holes, {"system": "nonel"})
    return design


def _situation_and_points(design):
    """Условная ситуация и точки Г.5 вокруг блока 66 (для вида листа, не данные карьера)."""

    xs = [hole.collar.x for hole in design.holes]
    ys = [hole.collar.y for hole in design.holes]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    layers = [
        {"name": "Дорога на отвал", "kind": "road",
         "lines": [{"points": [[cx - 1500, cy - 700], [cx - 300, cy - 350], [cx + 400, cy - 600], [cx + 1600, cy - 400]], "closed": False}]},
        {"name": "ЛЭП 6 кВ", "kind": "power_line",
         "lines": [{"points": [[cx + 700, cy - 1500], [cx + 750, cy + 1500]], "closed": False}]},
        {"name": "Промплощадка ДСК", "kind": "building",
         "lines": [{"points": [[cx - 1000, cy + 600], [cx - 880, cy + 600], [cx - 880, cy + 700], [cx - 1000, cy + 700]], "closed": True}]},
    ]
    points = [
        {"kind": "guard_post", "ref": str(number), "x": cx + 1000 * math.cos(math.radians(angle)), "y": cy + 1000 * math.sin(math.radians(angle))}
        for number, angle in zip(range(1, 6), (200, 280, 330, 20, 120))
    ]
    points += [
        {"kind": "blast_station", "x": cx - 1050, "y": cy - 650, "label": "у дороги на отвал, за КПП"},
        {"kind": "shelter", "x": cx - 1080, "y": cy - 600},
        {"kind": "gather", "x": cx - 1100, "y": cy - 700},
    ]
    return layers, points


@pytest.fixture(scope="module")
def context():
    design = _design66()
    layers, points = _situation_and_points(design)
    return context66(design, payload=payload66(requisites=REQUISITES, layout_points=points),
                     situation_layers=layers, has_situation_refs=True)


@pytest.fixture(scope="module")
def pdf(context) -> bytes:
    return render_project_document(context, "graphics")


def _pages(data: bytes) -> list:
    document = pdfium.PdfDocument(data)
    return [document[index] for index in range(len(document))]


def _text(page) -> str:
    return page.get_textpage().get_text_range()


# --- масштаб и поворот --------------------------------------------------------

def _rect(width: float, height: float, angle: float = 0.0, origin=(1000.0, 2000.0)) -> list[tuple[float, float]]:
    a = math.radians(angle)
    corners = [(-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2), (-width / 2, height / 2)]
    return [(origin[0] + x * math.cos(a) - y * math.sin(a), origin[1] + x * math.sin(a) + y * math.cos(a)) for x, y in corners]


def _fits(view: PlanView, points) -> bool:
    sheet = [view.xy(p) for p in points]
    return all(-1e-6 <= x <= FIELD_W_MM + 1e-6 and -1e-6 <= y <= FIELD_H_MM + 1e-6 for x, y in sheet)


def test_small_block_is_north_up_at_finest_scale():
    points = _rect(40, 20)
    view = fit_view(points, FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM)
    assert (view.scale, view.angle_deg) == (200, 0.0)
    assert _fits(view, points)


def test_north_up_while_it_fits_500():
    # «Север вверх» помещается в 1:500 — поворота нет, хотя повёрнутый влез бы в 1:250.
    points = _rect(66, 4, angle=40)
    assert fit_view(points, FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM, series=(250,), rotate_from=250).angle_deg != 0.0
    view = fit_view(points, FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM)
    assert (view.scale, view.angle_deg) == (500, 0.0)


def test_long_diagonal_block_is_rotated_at_500():
    points = _rect(120, 15, angle=45)
    view = fit_view(points, FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM)
    assert view.scale == 500 and view.angle_deg != 0.0
    assert _fits(view, points)
    north = view.north
    assert math.hypot(*north) == pytest.approx(1.0)


def test_too_big_goes_to_next_scale_north_up_first():
    points = _rect(400, 300)
    view = fit_view(points, FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM)
    assert (view.scale, view.angle_deg) == (5000, 0.0)
    huge = _rect(5000, 5000)
    assert fit_view(huge, FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM).scale == 5000


def test_plan_view_without_rotation_is_drill_formula():
    """Паспорт на бурение печатается прежними байтами: перевод координат без поворота — та же формула."""

    rng = random.Random(7)
    for _ in range(200):
        x0, y0 = rng.uniform(-1e6, 1e6), rng.uniform(-1e6, 1e6)
        cx, cy, scale = x0 + rng.uniform(-50, 50), y0 + rng.uniform(-50, 50), rng.choice([200, 330, 670, 1000])
        k = 1000 / scale
        view = PlanView(scale=scale, angle_deg=0.0, cx=cx, cy=cy, ox=86.0, oy=114.0)
        assert view.xy((x0, y0)) == (86.0 + (x0 - cx) * k, 114.0 + (y0 - cy) * k)
    for width, height in ((10.0, 10.0), (663.0 * 0.156, 30.0), (120.0, 230.0), (0.0, 0.0)):
        usable_w = drill_plan.PLAN_W_MM - 2 * drill_plan.PLAN_PAD_MM - drill_plan.LABEL_RESERVE_MM
        usable_h = drill_plan.PLAN_H_MM - 2 * drill_plan.PLAN_PAD_MM
        need = max(width / usable_w, height / usable_h) * 1000
        old = max(drill_plan.MIN_SCALE, math.ceil(need / 10 - 1e-9) * 10)
        assert drill_plan.plan_scale(width, height, drill_plan.PLAN_W_MM, drill_plan.PLAN_H_MM) == old


def test_block66_plan_is_rotated_at_500_with_first_row_down(context):
    graphics = context["blocks_v2"][0]["graphics"]
    view = plans.block_view(graphics)
    # Как эталон: 1:500 с поворотом, первый ряд — внизу листа.
    assert view.scale == 500 and view.angle_deg != 0.0
    holes = [(hole, (hole["x"], hole["y"])) for hole in graphics["holes"]]
    first = [view.xy(p)[1] for hole, p in holes if hole["first_row"]]
    every = [view.xy(p)[1] for _hole, p in holes]
    assert sum(first) / len(first) < sum(every) / len(every)
    assert _fits(view, plans._points(graphics))


def test_scale_bar_length_matches_scale():
    for scale in plan_sheet.SCALE_SERIES:
        bar_m, bar_mm = plan_sheet.bar(scale)
        assert bar_mm == pytest.approx(bar_m * 1000 / scale)
        drawing = legend_band(scale=scale, bar_m=bar_m, bar_mm=bar_mm, items=[], notes=[])
        halves = [shape for shape in drawing.contents for shape in getattr(shape, "contents", []) if isinstance(shape, Rect)]
        assert sum(rect.width for rect in halves) == pytest.approx(bar_mm * mm)


def test_profile_and_situation_scales(context):
    sections = context["blocks_v2"][0]["graphics"]["sections"]
    assert profiles.profile_scale(sections) == 250
    # Зона для людей 900 м: круг ≈ 1,9 км — в 1:10 000 не помещается (решение В4: ряд Г.5 до 1:25 000).
    assert situation.situation_view(context["graphics"]).scale == 25000
    small = copy.deepcopy(context["graphics"])
    small["zones"] = [zone for zone in small["zones"] if zone["kind"] == "buildings"]
    small["points"], small["objects"] = [], []
    assert situation.situation_view(small).scale in (5000, 10000)   # кольцо зоны для зданий — целиком


# --- документ «Графика» -------------------------------------------------------

def test_graphics_pdf_pages_titles_and_signatures(pdf):
    pages = _pages(pdf)
    assert len(pages) == 5
    assert all(page.get_size() == pytest.approx((841.89, 595.28), abs=0.1) for page in pages)
    texts = [_text(page) for page in pages]
    assert "Приложение Г.1. Схема расположения скважин (по маркшейдерской съёмке), М 1:500" in texts[0]
    assert "Приложение Г.2. Поперечные профили через заряды, М 1:250" in texts[1]
    assert "Приложение Г.3. Схема заряжания, забойки и отвода оборудования, М 1:500" in texts[2]
    assert "Приложение Г.4. Схема взрывной сети с интервалами замедления, М 1:500" in texts[3]
    assert "Приложение Г.5." in texts[4] and "М 1:25 000" in texts[4]
    assert "Съёмку выполнил:" in texts[0] and "маркшейдер [Фамилия И. О.]" in texts[0]
    assert all("Составил:" in text and "Плаксин А.И." in text for text in texts[1:])
    assert "Разрез А–А" in texts[1] and "Разрез Б–Б" in texts[1]
    assert "СТАРТ" in texts[3] and "в окне 8 мс" in texts[3]
    assert "Посты охраны" in texts[4] and "Ситуации карьера нет" not in texts[4]
    assert "Взрывная станция" in texts[4] and "у дороги на отвал, за КПП" in texts[4]
    assert "Опорная скважина № 1" in texts[0]
    assert [f"Стр. {n} из 5" in text for n, text in enumerate(texts, start=1)] == [True] * 5


def test_graphics_pdf_prints_actual_size_and_is_stable(context, pdf):
    assert b"/PrintScaling /None" in pdf
    assert render_project_document(copy.deepcopy(context), "graphics") == pdf
    # Документы без графики признака не несут.
    assert b"/PrintScaling" not in render_project_document(context, "schedule")


def test_multi_block_sheets_per_block(context):
    data = copy.deepcopy(context)
    second = copy.deepcopy(data["blocks_v2"][0])
    second["code"] = "67"
    data["blocks_v2"].append(second)
    part = graphics_part(data)
    assert part is not None
    titles = part.page_titles or ()
    assert len(titles) == 9
    assert [title.split(".")[1].strip()[0] for title in titles] == ["1", "1", "2", "2", "3", "3", "4", "4", "5"]
    assert titles[0].endswith("· блок 66") and titles[1].endswith("· блок 67") and "блок" not in titles[-1].split(",")[-1]
    keys = [item.key for item in project_parts(data, ("graphics",))]
    assert keys == ["graphics"]


def _raster(source: bytes, index: int):
    from PIL import ImageFilter

    image = pdfium.PdfDocument(source)[index].render(scale=RASTER_DPI / 72).to_pil().convert("L")
    return image.filter(ImageFilter.GaussianBlur(1))


@pytest.mark.parametrize("index", range(5))
def test_sheets_match_approved_png(pdf, index):
    from PIL import Image, ImageChops

    path = GOLDEN / f"g{index + 1}.png"
    image = _raster(pdf, index)
    if os.environ.get("BLASTEX_UPDATE_GOLDEN") == "1":
        image.save(path)
    golden = Image.open(path).convert("L")
    assert golden.size == image.size
    diff = ImageChops.difference(golden, image).point(lambda value: 255 if value > 64 else 0)
    share = diff.histogram()[255] / (diff.width * diff.height)
    assert share <= RASTER_THRESHOLD, f"Г.{index + 1}: {share:.2%} пикселей отличаются"


def test_long_signature_and_crowded_legend_keep_one_page_per_sheet(context):
    from reportlab.graphics.shapes import String

    data = copy.deepcopy(context)
    data["requisites"]["made_by"] = {"position": "ведущий " * 25, "name": "Фамилия-Длинная " * 12}
    network = data["blocks_v2"][0]["graphics"]["network"]
    network["groups"] = [{"label": f"НСИ «Искра-П» длинное название марки № {n} — {n * 17} мс", "count": n} for n in range(40)]
    pages = _pages(render_project_document(data, "graphics"))
    assert len(pages) == 5
    _field, legend = plans.g4_drawings(data["blocks_v2"][0]["graphics"], plans.block_view(data["blocks_v2"][0]["graphics"]))

    def strings(shape):
        for item in getattr(shape, "contents", []):
            yield from strings(item)
        if isinstance(shape, String):
            yield shape

    assert min(item.y for item in strings(legend)) >= 0          # ничего не легло на подпись
    assert any(item.text.startswith("также: ") for item in strings(legend))   # лишние группы — строкой


def test_sheet_overflow_is_an_error(context):
    from design.reporting.mass_blast import frame

    part = graphics_part(context)
    assert part is not None
    part.page_titles = part.page_titles[:4]
    with pytest.raises(RuntimeError, match="не поместился"):
        frame.count_pages(part)


def test_section_lines_stay_inside_field():
    from reportlab.graphics.shapes import PolyLine

    from design.models import Hole, Point3
    from design.mass_blast_graphics import block_graphics

    design = _design66()
    # Блок 50 × 28 м: скважины до краёв, линия разреза (+7 м) вышла бы за поле.
    design.holes = [
        Hole(id=str(n), row=0, col=0, collar=Point3(1000 + x, 2000 + y, 400.0), toe=Point3(1000 + x, 2000 + y, 388.0),
             diameter_mm=144.0, subdrill_m=1.5)
        for n, (x, y) in enumerate(((x, y) for x in range(2, 50, 4) for y in range(2, 27, 4)), start=1)
    ]
    design.loads, design.contour = [], design.contour.__class__(
        vertices=[Point3(1000 + x, 2000 + y, 0) for x, y in ((0, 0), (50, 0), (50, 28), (0, 28))], free_faces=[[0, 1]])
    graphics, _ = block_graphics(design, [])
    view = plans.block_view(graphics)
    field, _legend = plans.g1_drawings(graphics, view)

    def shapes(shape):
        for item in getattr(shape, "contents", []):
            yield from shapes(item)
        yield shape

    for shape in shapes(field):
        if isinstance(shape, PolyLine):
            xs, ys = shape.points[0::2], shape.points[1::2]
            assert min(xs) >= -0.01 and max(xs) <= FIELD_W_MM * mm + 0.01
            assert min(ys) >= -0.01 and max(ys) <= FIELD_H_MM * mm + 0.01


def test_situation_view_includes_the_largest_zone(context):
    graphics = copy.deepcopy(context["graphics"])
    graphics["points"], graphics["objects"] = [], []
    people = next(zone for zone in graphics["zones"] if zone["kind"] == "people")
    cx = sum(x for x, _y in people["rings"][0]) / len(people["rings"][0])
    cy = sum(y for _x, y in people["rings"][0]) / len(people["rings"][0])
    # Зона для людей мала (150 м), зона для зданий — 1,2 км: масштаб — по большему кольцу.
    people["rings"] = [[[cx + 150 * math.cos(a / 10), cy + 150 * math.sin(a / 10)] for a in range(63)]]
    buildings = next(zone for zone in graphics["zones"] if zone["kind"] == "buildings")
    buildings["rings"] = [[[cx + 1200 * math.cos(a / 10), cy + 1200 * math.sin(a / 10)] for a in range(63)]]
    view = situation.situation_view(graphics)
    ring = [view.xy(tuple(p)) for p in buildings["rings"][0]]
    assert all(0 <= x <= situation.MAP_W_MM and 0 <= y <= situation.MAP_H_MM for x, y in ring)


def test_szm_routes_fit_the_shared_view():
    from design.mass_blast_graphics import block_graphics
    from design.models import BlockContour, Hole, Point3

    design = _design66()
    # 7 колонок шагом 10 м: последняя заходка — на полшага (5 м) за крайней колонкой, за контуром.
    design.holes = [
        Hole(id=str(n), row=0, col=0, collar=Point3(1000 + x, 2000 + y, 400.0), toe=Point3(1000 + x, 2000 + y, 388.0),
             diameter_mm=144.0, subdrill_m=1.5)
        for n, (x, y) in enumerate(((x, y) for x in range(2, 63, 10) for y in (2, 7, 12)), start=1)
    ]
    design.loads, design.network.surface_connectors, design.network.connectors = [], [], []
    design.pattern_params = {"pattern": "square", "spacing_a_m": 10.0}
    design.contour = BlockContour(vertices=[Point3(1000 + x, 2000 + y, 0) for x, y in ((0, 0), (64, 0), (64, 15), (0, 15))],
                                  free_faces=[[0, 1]])
    graphics, _ = block_graphics(design, [])
    assert len(graphics["szm"]["passes"]) == 4
    view = plans.block_view(graphics)
    for item in graphics["szm"]["passes"]:
        for point in item["points"]:
            x, y = view.xy(tuple(point))
            assert 0 <= x <= FIELD_W_MM and 0 <= y <= FIELD_H_MM


def test_situation_that_does_not_fit_says_so(context):
    data = copy.deepcopy(context)
    graphics = data["graphics"]
    # Второй блок за 6 км: в 1:25 000 охват не помещается — лист говорит об этом, блоки не лезут на таблицы.
    far = [[x + 6000.0, y] for x, y in graphics["outlines"][0]]
    graphics["outlines"].append(far)
    view = situation.situation_view(graphics)
    assert view.scale == 25000 and not view.fits
    text = _text(_pages(render_project_document(data, "graphics"))[4])
    assert "не помещается в масштаб 1:25 000" in text
    drawing = situation.map_drawing(data, view)
    from reportlab.graphics.shapes import Polygon

    for shape in drawing.contents:
        if isinstance(shape, Polygon):
            xs = shape.points[0::2]
            assert max(xs) <= situation.MAP_W_MM * mm + 0.01


def test_fit_view_marks_overflow():
    assert fit_view(_rect(40, 20), FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM).fits
    assert not fit_view(_rect(5000, 5000), FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM).fits
