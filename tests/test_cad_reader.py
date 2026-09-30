"""Чтение чертежа маркшейдера: все сущности DXF/DWG с геометрией и видом Z."""
from __future__ import annotations

import io
import math
from pathlib import Path

import ezdxf
import pytest

from design.spatial.cad import reader
from design.spatial.cad.model import CadEntity
from design.spatial.cad.reader import CadReadError, ReadOptions, read_cad


def _dxf_bytes(build, version: str = "R2010") -> bytes:
    doc = ezdxf.new(version)
    build(doc)
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


def _only(entities: list[CadEntity], kind: str) -> CadEntity:
    found = [item for item in entities if item.kind == kind]
    assert len(found) == 1, [item.kind for item in entities]
    return found[0]


def _radial_deviation(entity: CadEntity, cx: float, cy: float, radius: float) -> float:
    """Наибольшее отклонение вершин и середин хорд от окружности."""

    worst = 0.0
    points = entity.points
    pairs = list(zip(points, points[1:]))
    if entity.closed:
        pairs.append((points[-1], points[0]))
    for (ax, ay, _), (bx, by, _) in pairs:
        for x, y in ((ax, ay), ((ax + bx) / 2, (ay + by) / 2)):
            worst = max(worst, abs(math.hypot(x - cx, y - cy) - radius))
    return worst


# --- линии ---------------------------------------------------------------


def test_lwpolyline_elevation_gives_constant_z():
    def build(doc):
        doc.modelspace().add_lwpolyline(
            [(0, 0), (30, 0), (30, 20)], dxfattribs={"layer": "бровка", "elevation": 420.0}
        )

    entity = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "LWPOLYLINE")

    assert entity.layer == "бровка"
    assert entity.z_kind == "const"
    assert entity.z_min == entity.z_max == pytest.approx(420.0)
    assert entity.vertex_count == 3
    assert entity.length_m == pytest.approx(50.0)
    assert entity.handle


def test_lwpolyline_bulge_is_flattened_within_the_sagitta():
    def build(doc):
        # Полуокружность радиусом 5 м с центром в (5; 0).
        doc.modelspace().add_lwpolyline([(0, 0, 0, 0, 1), (10, 0, 0, 0, 0)], format="xyseb")

    entity = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "LWPOLYLINE")

    assert entity.vertex_count > 10
    assert _radial_deviation(entity, 5.0, 0.0, 5.0) <= reader.CURVE_SAGITTA_M + 1e-6


def test_polylines_distinguish_3d_and_2d():
    def build(doc):
        msp = doc.modelspace()
        msp.add_polyline3d([(0, 0, 410.0), (10, 0, 411.5), (20, 5, 412.0)])
        msp.add_polyline2d([(0, 50), (10, 50), (20, 55)])

    entities = read_cad(_dxf_bytes(build), "a.dxf").entities

    three_d = _only(entities, "POLYLINE3D")
    assert three_d.z_kind == "variable"
    assert (three_d.z_min, three_d.z_max) == pytest.approx((410.0, 412.0))
    assert _only(entities, "POLYLINE2D").z_kind == "zero"


def test_lines_stay_separate_entities_with_their_handles():
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((0, 0, 5), (10, 0, 5))
        msp.add_line((10, 0, 5), (10, 10, 5))

    lines = [item for item in read_cad(_dxf_bytes(build), "a.dxf").entities if item.kind == "LINE"]

    assert len(lines) == 2
    assert len({item.handle for item in lines}) == 2
    assert all(item.z_kind == "const" for item in lines)


def test_arc_and_circle_deviate_at_most_the_sagitta():
    def build(doc):
        msp = doc.modelspace()
        msp.add_arc((100, 100), radius=40, start_angle=0, end_angle=120)
        msp.add_circle((0, 0), radius=12)

    entities = read_cad(_dxf_bytes(build), "a.dxf").entities

    arc = _only(entities, "ARC")
    circle = _only(entities, "CIRCLE")
    assert not arc.closed
    assert circle.closed
    assert _radial_deviation(arc, 100, 100, 40) <= reader.CURVE_SAGITTA_M + 1e-6
    assert _radial_deviation(circle, 0, 0, 12) <= reader.CURVE_SAGITTA_M + 1e-6


def test_ellipse_and_spline_become_lines():
    def build(doc):
        msp = doc.modelspace()
        msp.add_ellipse((0, 0), major_axis=(20, 0), ratio=0.5)
        msp.add_spline([(0, 0, 400), (10, 8, 401), (20, 0, 402), (30, 8, 403)])

    entities = read_cad(_dxf_bytes(build), "a.dxf").entities

    ellipse = _only(entities, "ELLIPSE")
    spline = _only(entities, "SPLINE")
    assert ellipse.closed and ellipse.vertex_count > 20
    assert spline.vertex_count > 4
    assert spline.z_kind == "variable"


# --- замкнутость и дубли ------------------------------------------------


@pytest.mark.parametrize(
    ("points", "closed_flag", "closed", "by_gap"),
    [
        ([(0, 0), (40, 0), (40, 30), (0, 30)], True, True, False),
        ([(0, 0), (40, 0), (40, 30), (0, 30), (0, 0)], False, True, True),
        ([(0, 0), (40, 0), (40, 30), (0, 30), (0, 0.4)], False, True, True),
        ([(0, 0), (40, 0), (40, 30), (0, 30), (0, 0.6)], False, False, False),
        # Разрыв 0,4 м при длине линии 5 м — больше 5 % длины: это не замыкание.
        ([(0, 0), (2, 0), (2, 1.2), (0, 0.4)], False, False, False),
    ],
)
def test_closure_by_flag_or_by_gap(points, closed_flag, closed, by_gap):
    def build(doc):
        doc.modelspace().add_lwpolyline(points, close=closed_flag)

    entity = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "LWPOLYLINE")

    assert entity.closed is closed
    assert entity.closed_by_gap is by_gap


def test_duplicate_vertices_are_removed():
    def build(doc):
        doc.modelspace().add_lwpolyline(
            [(0, 0), (10, 0), (10, 0.0005), (10, 10), (0, 10), (0, 0)]
        )

    entity = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "LWPOLYLINE")

    assert entity.vertex_count == 4
    assert entity.closed and entity.closed_by_gap
    assert entity.area_m2 == pytest.approx(100.0)


def test_degenerate_line_is_skipped_with_a_note():
    def build(doc):
        msp = doc.modelspace()
        msp.add_line((5, 5, 0), (5, 5, 0))
        msp.add_point((0, 0, 100))

    drawing = read_cad(_dxf_bytes(build), "a.dxf")

    assert [item.kind for item in drawing.entities] == ["POINT"]
    assert any(item.code == "degenerate" for item in drawing.warnings)


# --- точки, знаки, подписи ----------------------------------------------


def test_points_keep_their_elevation():
    def build(doc):
        msp = doc.modelspace()
        msp.add_point((1, 2, 412.5), dxfattribs={"layer": "Отметка"})
        msp.add_point((3, 4, 0))

    points = [item for item in read_cad(_dxf_bytes(build), "a.dxf").entities if item.kind == "POINT"]

    assert [item.z_kind for item in points] == ["const", "zero"]
    assert points[0].points == [(1.0, 2.0, 412.5)]


def _sign_block(doc) -> None:
    block = doc.blocks.new("ОТМЕТКА")
    block.add_circle((0, 0), radius=0.5)
    block.add_attdef("Z", (0.6, 0), dxfattribs={"height": 0.4})


def test_sign_insert_takes_elevation_from_its_attribute():
    def build(doc):
        _sign_block(doc)
        insert = doc.modelspace().add_blockref("ОТМЕТКА", (100, 200, 0), dxfattribs={"layer": "Отметки"})
        insert.add_attrib("Z", "412.35", (100.6, 200))

    sign = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "INSERT")

    assert sign.points == [(100.0, 200.0, pytest.approx(412.35))]
    assert sign.z_from_label is True
    assert sign.layer == "Отметки"


def test_sign_insert_without_attribute_keeps_its_z():
    def build(doc):
        block = doc.blocks.new("КРЕСТ")
        block.add_line((-0.5, 0), (0.5, 0))
        block.add_line((0, -0.5), (0, 0.5))
        doc.modelspace().add_blockref("КРЕСТ", (7, 8, 415.0))

    sign = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "INSERT")

    assert sign.points == [(7.0, 8.0, 415.0)]
    assert sign.z_kind == "const"
    assert sign.z_from_label is False


def test_large_block_insert_is_expanded_in_world_coordinates():
    def build(doc):
        block = doc.blocks.new("СКЛАД")
        block.add_lwpolyline([(0, 0), (20, 0), (20, 10)])
        doc.modelspace().add_blockref(
            "СКЛАД",
            (1000, 500),
            dxfattribs={"layer": "Ситуация", "rotation": 30, "xscale": 2, "yscale": -2},
        )

    data = _dxf_bytes(build)
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    insert = next(iter(doc.modelspace().query("INSERT")))
    expected = [
        (round(v.x, 6), round(v.y, 6))
        for virtual in insert.virtual_entities()
        for v in virtual.vertices_in_wcs()
    ]

    lines = [item for item in read_cad(data, "a.dxf").entities if item.geometry_type == "line"]

    assert len(lines) == 1
    assert lines[0].handle.startswith(f"{insert.dxf.handle}/")
    assert lines[0].layer == "Ситуация"  # слой «0» внутри блока берёт слой вставки
    assert [(round(x, 6), round(y, 6)) for x, y, _ in lines[0].points] == expected


def test_lwpolyline_with_negative_extrusion_is_mirrored_into_wcs():
    def build(doc):
        doc.modelspace().add_lwpolyline([(10, 0), (20, 5)], dxfattribs={"extrusion": (0, 0, -1)})

    entity = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "LWPOLYLINE")

    assert [(round(x, 6), round(y, 6)) for x, y, _ in entity.points] == [(-10.0, 0.0), (-20.0, 5.0)]


def test_text_and_mtext_are_read():
    def build(doc):
        msp = doc.modelspace()
        msp.add_text("410.84", dxfattribs={"insert": (5, 6, 0), "height": 0.4, "layer": "Отметка"})
        msp.add_mtext("Блок 66\\PВар 2", dxfattribs={"insert": (50, 60, 0)})

    entities = read_cad(_dxf_bytes(build), "a.dxf").entities

    text = _only(entities, "TEXT")
    mtext = _only(entities, "MTEXT")
    assert (text.text, text.points[0][:2]) == ("410.84", (5.0, 6.0))
    assert mtext.text == "Блок 66\nВар 2"
    assert text.geometry_type == mtext.geometry_type == "text"


def test_a_survey_file_without_lines_is_accepted():
    def build(doc):
        msp = doc.modelspace()
        msp.add_point((0, 0, 410.2))
        msp.add_text("410.20", dxfattribs={"insert": (0.3, 0.3)})

    drawing = read_cad(_dxf_bytes(build), "survey.dxf")

    assert sorted(item.kind for item in drawing.entities) == ["POINT", "TEXT"]


def test_unsupported_entities_are_named_in_a_note():
    def build(doc):
        msp = doc.modelspace()
        hatch = msp.add_hatch()
        hatch.paths.add_polyline_path([(0, 0), (1, 0), (1, 1)], is_closed=True)
        msp.add_point((0, 0, 400))

    drawing = read_cad(_dxf_bytes(build), "a.dxf")

    note = next(item for item in drawing.warnings if item.code == "skipped")
    assert "HATCH" in note.message


# --- ошибки, форматы, лимиты --------------------------------------------


def test_empty_file_is_rejected():
    with pytest.raises(CadReadError, match="пустой"):
        read_cad(b"   ", "a.dxf")


def test_garbage_is_rejected_with_a_readable_message():
    with pytest.raises(CadReadError, match="Не удалось прочитать DXF"):
        read_cad(b"this is not a drawing at all", "a.dxf")


def test_binary_dxf_is_read(tmp_path: Path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_point((1, 1, 401))
    path = tmp_path / "bin.dxf"
    doc.saveas(path, fmt="bin")

    drawing = read_cad(path.read_bytes(), "bin.dxf")

    assert [item.kind for item in drawing.entities] == ["POINT"]


def test_too_many_entities_is_an_error_not_a_truncation(monkeypatch):
    monkeypatch.setattr(reader, "MAX_ENTITIES", 10)

    def build(doc):
        for index in range(11):
            doc.modelspace().add_point((index, 0, 400))

    with pytest.raises(CadReadError) as exc:
        read_cad(_dxf_bytes(build), "a.dxf")
    # Предел проверяется по ходу чтения: раскрытие огромного блока не успеет съесть память.
    assert "больше 10 объектов" in str(exc.value)


def test_too_many_vertices_is_an_error(monkeypatch):
    monkeypatch.setattr(reader, "MAX_VERTICES", 5)

    def build(doc):
        doc.modelspace().add_lwpolyline([(index, index % 2) for index in range(6)])

    with pytest.raises(CadReadError, match="вершин"):
        read_cad(_dxf_bytes(build), "a.dxf")


def test_scale_multiplies_all_coordinates():
    def build(doc):
        doc.modelspace().add_polyline3d([(1000, 2000, 410000), (5000, 2000, 411000)])

    entity = _only(
        read_cad(_dxf_bytes(build), "mm.dxf", ReadOptions(scale=0.001)).entities, "POLYLINE3D"
    )

    assert entity.points[0] == pytest.approx((1.0, 2.0, 410.0))
    assert entity.length_m == pytest.approx(4.0)


def test_colors_resolve_through_the_layer_table():
    def build(doc):
        doc.layers.add("Зелёный", color=3)
        msp = doc.modelspace()
        msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "Зелёный"})
        msp.add_line((0, 1), (1, 1), dxfattribs={"layer": "Зелёный", "color": 1})
        msp.add_line((0, 2), (1, 2), dxfattribs={"true_color": ezdxf.colors.rgb2int((10, 20, 30))})

    drawing = read_cad(_dxf_bytes(build), "a.dxf")

    assert [item.color for item in drawing.entities] == ["#00ff00", "#ff0000", "#0a141e"]
    assert drawing.layers["Зелёный"] == "#00ff00"


# --- DWG ----------------------------------------------------------------


def _point_dxf() -> bytes:
    return _dxf_bytes(lambda doc: doc.modelspace().add_point((1, 2, 400)))


def test_dwg_is_read_from_the_full_dxf(monkeypatch):
    calls: list[bool] = []

    def fake(data, filename, *, minimal=False):
        calls.append(minimal)
        return _point_dxf()

    monkeypatch.setattr(reader, "dwg_to_dxf", fake)

    drawing = read_cad(b"AC1032 dwg bytes", "block.dwg")

    assert calls == [False]
    assert drawing.source_format == "dwg"
    assert drawing.minimal_dxf is False


def test_dwg_falls_back_to_the_minimal_dxf_with_a_warning(monkeypatch):
    calls: list[bool] = []

    def fake(data, filename, *, minimal=False):
        calls.append(minimal)
        return _point_dxf() if minimal else b"0\nSECTION\n2\nBROKEN\n"

    monkeypatch.setattr(reader, "dwg_to_dxf", fake)

    drawing = read_cad(b"AC1032 dwg bytes", "block.dwg")

    assert calls == [False, True]
    assert drawing.minimal_dxf is True
    assert any(item.code == "minimal_dxf" for item in drawing.warnings)
    assert [item.kind for item in drawing.entities] == ["POINT"]


def test_missing_dwg_converter_asks_for_dxf(monkeypatch):
    monkeypatch.delenv("BLASTEX_DWG_CONVERTER", raising=False)
    monkeypatch.setattr("design.spatial.dwg.shutil.which", lambda name: None)

    with pytest.raises(CadReadError, match="DXF"):
        read_cad(b"AC1032 dwg bytes", "block.dwg")


def test_duplicate_handles_get_a_suffix_and_a_note():
    """LibreDWG и битые выгрузки дают повторяющиеся handle — хранилищу нужны уникальные."""

    def build(doc):
        msp = doc.modelspace()
        msp.add_point((0, 0, 400))
        msp.add_point((5, 5, 401))

    text = _dxf_bytes(build).decode("utf-8")
    doc = ezdxf.read(io.StringIO(text))
    first, second = (entity.dxf.handle for entity in doc.modelspace())
    duplicated = text.replace(f"\n  5\n{second}\n", f"\n  5\n{first}\n", 1)

    drawing = read_cad(duplicated.encode("utf-8"), "a.dxf")

    assert [item.handle for item in drawing.entities] == [first, f"{first}~2"]
    assert any(item.code == "duplicate_handles" for item in drawing.warnings)


def test_broken_curve_is_skipped_with_a_note_and_the_rest_is_read():
    def build(doc):
        msp = doc.modelspace()
        spline = msp.add_spline([(0, 0), (10, 5), (20, 0), (30, 5)])
        spline.control_points = [(0, 0, 0), (10, 5, 0)]  # степень 3 и две точки — битый сплайн
        msp.add_point((1, 1, 405))

    drawing = read_cad(_dxf_bytes(build), "a.dxf")

    assert [item.kind for item in drawing.entities] == ["POINT"]
    note = next(item for item in drawing.warnings if item.code == "skipped")
    assert "SPLINE (повреждён) × 1" in note.message


def test_curve_tolerances_are_in_metres_after_scaling():
    """Окружность 10 м в миллиметровом чертеже спрямляется так же, как в метровом."""

    def metres(doc):
        doc.modelspace().add_circle((0, 0), radius=10)

    def millimetres(doc):
        doc.modelspace().add_circle((0, 0), radius=10_000)

    in_metres = _only(read_cad(_dxf_bytes(metres), "m.dxf").entities, "CIRCLE")
    in_mm = _only(read_cad(_dxf_bytes(millimetres), "mm.dxf", ReadOptions(scale=0.001)).entities, "CIRCLE")

    assert abs(in_mm.vertex_count - in_metres.vertex_count) <= 2


def test_sign_size_is_measured_in_metres_after_scaling():
    """Знак 3 м в миллиметровом чертеже — знак, а не объект в линиях."""

    def build(doc):
        block = doc.blocks.new("ЗНАК")
        block.add_circle((0, 0), radius=1500)
        doc.modelspace().add_blockref("ЗНАК", (100_000, 200_000, 415_000))

    sign = _only(read_cad(_dxf_bytes(build), "mm.dxf", ReadOptions(scale=0.001)).entities, "INSERT")

    assert sign.points == [pytest.approx((100.0, 200.0, 415.0))]


def test_minsert_expands_every_copy():
    def build(doc):
        block = doc.blocks.new("СКЛАД")
        block.add_lwpolyline([(0, 0), (20, 0), (20, 10)])
        doc.modelspace().add_blockref(
            "СКЛАД", (0, 0), dxfattribs={"column_count": 3, "column_spacing": 50}
        )

    lines = [item for item in read_cad(_dxf_bytes(build), "a.dxf").entities if item.geometry_type == "line"]

    assert sorted(round(item.points[0][0]) for item in lines) == [0, 50, 100]
    assert len({item.handle for item in lines}) == 3


def test_back_and_forth_line_is_not_closed():
    def build(doc):
        doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (0, 0)])

    entity = _only(read_cad(_dxf_bytes(build), "a.dxf").entities, "LWPOLYLINE")

    assert entity.closed is False
    assert entity.area_m2 == 0


def test_drawing_of_only_unsupported_entities_names_them():
    def build(doc):
        hatch = doc.modelspace().add_hatch()
        hatch.paths.add_polyline_path([(0, 0), (1, 0), (1, 1)], is_closed=True)

    with pytest.raises(CadReadError, match="HATCH"):
        read_cad(_dxf_bytes(build), "a.dxf")
