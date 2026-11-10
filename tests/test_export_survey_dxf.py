"""DXF скважин паспорта на бурение из снимка ревизии (TASK-015, PR 4, спека §4, §9)."""
from __future__ import annotations

import io
import math
from copy import deepcopy

import ezdxf
import pytest
from ezdxf.entities import Insert

from design.export_survey import HOLE_ATTRIBUTES, HOLE_LAYERS, holes_dxf
from tests.drill_passport_context import context66
from tests.test_drilling_passport import _block66_rows

def _read(data: bytes):
    return ezdxf.read(io.StringIO(data.decode("utf-8")))


def _dxf(context: dict | None = None) -> bytes:
    return holes_dxf(context if context is not None else context66(), revision_no=1)


@pytest.fixture(scope="module")
def doc():
    return _read(_dxf())


@pytest.fixture(scope="module")
def msp(doc):
    return doc.modelspace()


def _inserts(msp) -> dict[str, Insert]:
    return {ref.get_attrib_text("NUM"): ref for ref in msp.query('INSERT[layer=="BLX_HOLE"]')}


def test_header_r2010_metres_cp1251(doc):
    assert doc.dxfversion == "AC1024"
    assert doc.header["$INSUNITS"] == 6
    assert doc.header["$DWGCODEPAGE"] == "ANSI_1251"


def test_text_style_is_ttf_with_cyrillic(doc):
    # txt.shx не везде знает кириллицу — как у маркшейдера, TrueType Arial.
    assert doc.styles.get("Standard").dxf.font == "arial.ttf"


def test_layers(doc):
    names = {layer.dxf.name for layer in doc.layers}
    assert set(HOLE_LAYERS) <= names
    assert doc.layers.get("BLX_FIRST_ROW").color == 1
    assert all(doc.layers.get(name).dxf.linetype == "Continuous" for name in HOLE_LAYERS)


def test_196_points_and_inserts_on_hole_layer(msp):
    assert len(msp.query('POINT[layer=="BLX_HOLE"]')) == 196
    inserts = msp.query('INSERT[layer=="BLX_HOLE"]')
    assert len(inserts) == 196
    assert {ref.dxf.name for ref in inserts} == {"BLX_HOLE"}


def test_collars_equal_source_to_mm(msp):
    source = {str(row[0]): (float(row[1]), float(row[2]), float(row[3])) for row in _block66_rows()}
    points = list(msp.query('POINT[layer=="BLX_HOLE"]'))
    inserts = _inserts(msp)
    assert set(inserts) == set(source)
    for number, (x, y, z) in source.items():
        p = inserts[number].dxf.insert
        assert (abs(p.x - x), abs(p.y - y), abs(p.z - z)) <= (0.001, 0.001, 0.001)
    first = points[0].dxf.location
    assert (first.x, first.y, first.z) == pytest.approx((1472880.04, 593722.99, 419.21), abs=0.001)
    assert sorted((round(p.dxf.location.x, 3), round(p.dxf.location.y, 3)) for p in points) == sorted(
        (round(x, 3), round(y, 3)) for x, y, _ in source.values()
    )


def test_attributes_filled(msp):
    context = context66()
    inserts = _inserts(msp)
    for row in context["holes"]:
        ref = inserts[row["number"]]
        assert [attrib.dxf.tag for attrib in ref.attribs] == list(HOLE_ATTRIBUTES)
        assert ref.get_attrib_text("DEPTH") == f"{row['length_m']:.1f}"
        assert ref.get_attrib_text("ZCOL") == f"{row['collar']['z']:.2f}"
        assert all(attrib.is_invisible and attrib.dxf.layer == "BLX_HOLE" for attrib in ref.attribs)
    first = inserts["1"]
    assert [first.get_attrib_text(tag) for tag in HOLE_ATTRIBUTES] == ["1", "10.7", "", "", "419.21", "408.51"]


def test_circle_scale_is_bit_diameter(msp):
    for ref in msp.query('INSERT[layer=="BLX_HOLE"]'):
        assert (ref.dxf.xscale, ref.dxf.yscale) == pytest.approx((0.14, 0.14))


def test_block_is_unit_circle_with_attdefs(doc):
    block = doc.blocks.get("BLX_HOLE")
    circles = [e for e in block if e.dxftype() == "CIRCLE"]
    assert len(circles) == 1 and circles[0].dxf.radius == pytest.approx(0.5)
    assert [e.dxf.tag for e in block if e.dxftype() == "ATTDEF"] == list(HOLE_ATTRIBUTES)


def test_texts_num_and_depth(msp):
    numbers = list(msp.query('TEXT[layer=="BLX_HOLE_NUM"]'))
    depths = list(msp.query('TEXT[layer=="BLX_HOLE_DEPTH"]'))
    assert len(numbers) == len(depths) == 196
    assert all(text.dxf.height == pytest.approx(0.4) for text in [*numbers, *depths])
    assert numbers[0].dxf.text == "1" and depths[0].dxf.text == "10.7"
    # Номер — над устьем, глубина — под ним.
    collar = context66()["holes"][0]["collar"]
    assert numbers[0].dxf.align_point.y > collar["y"] > depths[0].dxf.align_point.y


def test_first_row_circles(msp):
    first = [row for row in context66()["holes"] if row["first_row"]]
    circles = list(msp.query('CIRCLE[layer=="BLX_FIRST_ROW"]'))
    assert len(circles) == len(first) > 0
    assert circles[0].dxf.radius == pytest.approx(0.07)


def test_contour_and_crests(msp):
    plan = context66()["plan"]
    contours = list(msp.query('LWPOLYLINE[layer=="BLX_CONTOUR"]'))
    assert len(contours) == 1 and contours[0].closed
    points = [tuple(p) for p in contours[0].get_points("xy")]
    assert len(points) == len(plan["contour"])
    for (x, y), (ex, ey) in zip(points, plan["contour"]):
        assert (x, y) == pytest.approx((ex, ey), abs=0.001)
    assert len(msp.query('LWPOLYLINE[layer=="BLX_CREST_TOP"]')) == len(plan["crest_top"]) > 0


def test_calculated_toe_line_goes_to_its_own_layer(msp):
    # У блока 66 линия подошвы — по углу откоса, а не снятая нижняя бровка.
    plan = context66()["plan"]
    assert plan["toe_source"] == "angle"
    assert len(msp.query('*[layer=="BLX_CREST_TOE"]')) == 0
    assert len(msp.query('LWPOLYLINE[layer=="BLX_TOE_LINE"]')) == len(plan["crest_toe"]) > 0
    assert "Линия подошвы — расчётная по углу откоса (слой BLX_TOE_LINE)" in _info(msp)


def test_surveyed_toe_goes_to_crest_toe_layer():
    context = context66()
    context["plan"]["toe_source"] = "survey"
    msp = _read(_dxf(context)).modelspace()
    assert len(msp.query('LWPOLYLINE[layer=="BLX_CREST_TOE"]')) == len(context["plan"]["crest_toe"])
    assert len(msp.query('*[layer=="BLX_TOE_LINE"]')) == 0
    assert "Линия подошвы" not in _info(msp)


def _with_inclined(context: dict) -> dict:
    result = deepcopy(context)
    row = result["holes"][5]
    dip, azimuth, length = 75.0, 120.0, row["length_m"]
    c = row["collar"]
    horizontal = length * math.cos(math.radians(dip))
    row.update(
        dip_deg=dip,
        azimuth_deg=azimuth,
        toe={
            "x": c["x"] + horizontal * math.sin(math.radians(azimuth)),
            "y": c["y"] + horizontal * math.cos(math.radians(azimuth)),
            "z": c["z"] - length * math.sin(math.radians(dip)),
        },
    )
    return result


def test_inclined_hole():
    context = _with_inclined(context66())
    row = context["holes"][5]
    msp = _read(_dxf(context)).modelspace()
    ref = _inserts(msp)[row["number"]]
    assert ref.get_attrib_text("ANGLE") == "75"
    assert ref.get_attrib_text("AZIM") == "120"
    assert ref.get_attrib_text("ZTOE") == f"{row['toe']['z']:.2f}"
    lines = list(msp.query('LINE[layer=="BLX_TOE"]'))
    toes = list(msp.query('POINT[layer=="BLX_TOE"]'))
    assert len(lines) == len(toes) == 1
    assert tuple(lines[0].dxf.end) == pytest.approx((row["toe"]["x"], row["toe"]["y"], row["toe"]["z"]), abs=0.001)
    assert tuple(lines[0].dxf.start) == pytest.approx(tuple(row["collar"].values()), abs=0.001)
    assert tuple(toes[0].dxf.location) == pytest.approx(tuple(lines[0].dxf.end), abs=0.001)


def test_vertical_holes_have_nothing_on_toe_layer(msp):
    assert len(msp.query('*[layer=="BLX_TOE"]')) == 0


def _info(msp) -> str:
    texts = list(msp.query('MTEXT[layer=="BLX_INFO"]'))
    assert len(texts) == 1
    return texts[0].plain_text()


def test_info_mtext():
    context = context66()
    context["crs"] = {"name": "МСК-66 зона 1", "epsg": None, "height_system": "Балтийская 1977"}
    text = _info(_read(_dxf(context)).modelspace())
    assert "Паспорт на бурение № 66-26/Б от 05.10.2026, ревизия 1" in text
    for part in ("Блок 66, горизонт +410,0 м", "МСК-66 зона 1", "Балтийская 1977"):
        assert part in text


def test_info_block_and_horizon_as_in_pdf():
    context = context66()
    context["passport"]["payload"].update(block="  66 ", horizon="+410,0 м")
    assert "Блок 66, горизонт +410,0 м\n" in _info(_read(_dxf(context)).modelspace()) + "\n"
    context["passport"]["payload"].update(block="   ", horizon="")
    assert "Блок" not in _info(_read(_dxf(context)).modelspace())


def test_guids_are_derived_from_revision():
    const = "{00000000-0000-0000-0000-000000000000}"
    context = context66()
    first = _read(_dxf(context)).header
    again = _read(_dxf(context)).header
    other = context66()
    other["holes"][0]["length_m"] = 12.0
    changed = _read(_dxf(other)).header
    assert const not in (first["$FINGERPRINTGUID"], first["$VERSIONGUID"])
    assert (first["$FINGERPRINTGUID"], first["$VERSIONGUID"]) == (again["$FINGERPRINTGUID"], again["$VERSIONGUID"])
    # Тот же паспорт — тот же отпечаток чертежа; другой снимок — другая версия.
    assert changed["$FINGERPRINTGUID"] == first["$FINGERPRINTGUID"]
    assert changed["$VERSIONGUID"] != first["$VERSIONGUID"]


def test_info_local_crs_is_marked_unset(msp):
    assert "СК не задана" in _info(msp)


def test_info_without_crs_in_revision():
    context = context66()
    context.pop("crs", None)
    assert "СК не сохранена в ревизии" in _info(_read(_dxf(context)).modelspace())


def test_revision_before_pr3():
    context = context66()
    context.pop("plan")
    context.pop("crs", None)
    context["summary"]["bit_diameter_mm"] = None
    for row in context["holes"]:
        row.pop("toe")
        row.pop("diameter_mm")
    msp = _read(_dxf(context)).modelspace()
    assert len(msp.query('POINT[layer=="BLX_HOLE"]')) == 196
    assert len(msp.query('LWPOLYLINE')) == 0
    ref = _inserts(msp)["1"]
    assert (ref.dxf.xscale, ref.get_attrib_text("ZTOE")) == (pytest.approx(0.14), "408.51")


def test_same_bytes():
    context = context66()
    assert _dxf(context) == _dxf(deepcopy(context))
