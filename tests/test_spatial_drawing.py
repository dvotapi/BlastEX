"""Разбор чертежа блока (DXF/DWG) на полилинии для ручного выбора бровок."""
from __future__ import annotations

import io

import ezdxf
import pytest

from design.spatial.drawing import DrawingError, read_drawing


def _dxf_bytes(build, version: str = "R2010") -> bytes:
    doc = ezdxf.new(version)
    build(doc)
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


def _bench_drawing(doc) -> None:
    doc.layers.add("ВЕРХНЯЯ БРОВКА")
    doc.layers.add("НИЖНЯЯ БРОВКА")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 30), (0, 30)],
        close=True,
        dxfattribs={"layer": "ВЕРХНЯЯ БРОВКА", "elevation": 120.0},
    )
    msp.add_polyline3d(
        [(4, 4, 108.0), (36, 4, 108.0), (36, 26, 108.0), (4, 26, 108.0)],
        dxfattribs={"layer": "НИЖНЯЯ БРОВКА"},
    )


def test_reads_polylines_with_layer_and_elevation():
    scan = read_drawing(_dxf_bytes(_bench_drawing), "block.dxf")

    assert scan.source_format == "dxf"
    assert scan.converted_from == ""
    layers = {item.layer for item in scan.polylines}
    assert layers == {"ВЕРХНЯЯ БРОВКА", "НИЖНЯЯ БРОВКА"}

    crest = next(item for item in scan.polylines if item.layer == "ВЕРХНЯЯ БРОВКА")
    assert crest.closed is True
    assert len(crest.points) == 4
    assert crest.z_min == pytest.approx(120.0)
    assert crest.z_max == pytest.approx(120.0)
    assert crest.length_m == pytest.approx(140.0)
    assert crest.area_m2 == pytest.approx(1200.0)

    toe = next(item for item in scan.polylines if item.layer == "НИЖНЯЯ БРОВКА")
    assert toe.closed is False
    assert toe.z_min == pytest.approx(108.0)


def test_polylines_are_sorted_longest_first():
    def build(doc):
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (1, 0)], dxfattribs={"layer": "мелочь"})
        msp.add_lwpolyline([(0, 5), (100, 5)], dxfattribs={"layer": "длинная"})

    scan = read_drawing(_dxf_bytes(build), "block.dxf")
    assert [item.layer for item in scan.polylines] == ["длинная", "мелочь"]


def test_line_segments_are_joined_into_a_chain():
    """Съёмку часто отдают отрезками LINE — инженеру нужна одна бровка, не 200 линий."""

    def build(doc):
        msp = doc.modelspace()
        for a, b in [((0, 0, 5), (10, 0, 5)), ((10, 0, 5), (10, 10, 5)), ((10, 10, 5), (0, 10, 5))]:
            msp.add_line(a, b, dxfattribs={"layer": "бровка отрезками"})

    scan = read_drawing(_dxf_bytes(build), "block.dxf")
    chains = [item for item in scan.polylines if item.layer == "бровка отрезками"]
    assert len(chains) == 1
    assert len(chains[0].points) == 4
    assert chains[0].length_m == pytest.approx(30.0)


def test_arcs_and_circles_are_flattened():
    def build(doc):
        doc.modelspace().add_circle((0, 0), radius=10, dxfattribs={"layer": "кольцо"})

    scan = read_drawing(_dxf_bytes(build), "block.dxf")
    ring = next(item for item in scan.polylines if item.layer == "кольцо")
    assert ring.closed is True
    assert len(ring.points) > 8
    assert ring.length_m == pytest.approx(2 * 3.14159 * 10, rel=0.02)


def test_entities_inside_blocks_are_included():
    def build(doc):
        block = doc.blocks.new(name="УСТУП")
        block.add_lwpolyline([(0, 0), (20, 0), (20, 20)], dxfattribs={"layer": "бровка в блоке"})
        doc.modelspace().add_blockref("УСТУП", (100, 100))

    scan = read_drawing(_dxf_bytes(build), "block.dxf")
    inserted = next(item for item in scan.polylines if item.layer == "бровка в блоке")
    # Вставка сдвигает геометрию — точки должны прийти в мировых координатах.
    assert inserted.points[0].x == pytest.approx(100.0)
    assert inserted.points[0].y == pytest.approx(100.0)


def test_binary_dxf_is_supported():
    doc = ezdxf.new("R2010")
    _bench_drawing(doc)
    buffer = io.BytesIO()
    doc.write(buffer, fmt="bin")
    scan = read_drawing(buffer.getvalue(), "block.dxf")
    assert len(scan.polylines) == 2


def test_empty_file_is_rejected():
    with pytest.raises(DrawingError):
        read_drawing(b"", "block.dxf")


def test_drawing_without_polylines_is_rejected():
    def build(doc):
        doc.modelspace().add_text("просто подпись", dxfattribs={"layer": "текст"})

    with pytest.raises(DrawingError) as exc:
        read_drawing(_dxf_bytes(build), "block.dxf")
    assert "полилини" in str(exc.value).lower()


def test_dwg_without_converter_explains_how_to_proceed(monkeypatch):
    monkeypatch.setattr("design.spatial.dwg.find_converter", lambda: None)
    with pytest.raises(DrawingError) as exc:
        read_drawing(b"AC1032 binary payload", "block.dwg")
    assert "dxf" in str(exc.value).lower()


def test_dwg_goes_through_the_converter(monkeypatch):
    payload = _dxf_bytes(_bench_drawing)
    calls: list[tuple[bytes, str]] = []

    def fake_convert(data: bytes, filename: str) -> bytes:
        calls.append((data, filename))
        return payload

    monkeypatch.setattr("design.spatial.drawing.dwg_to_dxf", fake_convert)
    scan = read_drawing(b"AC1032 binary payload", "block.dwg")
    assert calls and calls[0][1] == "block.dwg"
    assert scan.source_format == "dxf"
    assert scan.converted_from == "dwg"
    assert len(scan.polylines) == 2
