"""Отметки из подписей и единицы чертежа."""
from __future__ import annotations

import pytest

from design.spatial.cad.labels import attach_labels, parse_elevation
from design.spatial.cad.model import CadEntity
from design.spatial.cad.units import detect_units


def _point(handle: str, x: float, y: float, z: float = 0.0, layer: str = "Отметка") -> CadEntity:
    return CadEntity(handle=handle, layer=layer, kind="POINT", points=[(x, y, z)])


def _text(handle: str, x: float, y: float, text: str, layer: str = "Отметка") -> CadEntity:
    return CadEntity(handle=handle, layer=layer, kind="TEXT", points=[(x, y, 0.0)], text=text)


# --- подписи ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("410.84", 410.84),
        ("410,84", 410.84),
        (" +410 ", 410.0),
        ("+410.5", 410.5),
        ("-12.5", -12.5),
        ("66", None),
        ("-12", None),
        ("блок 66", None),
        ("410.84 м", None),
        ("", None),
    ],
)
def test_elevation_label_needs_a_fraction_or_an_explicit_plus(text, value):
    assert parse_elevation(text) == value


def test_zero_point_takes_the_nearby_label():
    point = _point("P1", 0, 0)
    label = _text("T1", 1.2, 1.6, "412.35")

    attach_labels([point, label], radius_m=3.0)

    assert point.points == [(0.0, 0.0, 412.35)]
    assert point.z_from_label is True
    assert point.label_handle == "T1"
    assert point.z_kind == "const"


def test_label_outside_the_radius_is_ignored_unless_the_radius_grows():
    point = _point("P1", 0, 0)
    label = _text("T1", 4.0, 0, "412.35")

    attach_labels([point, label], radius_m=3.0)
    assert point.z_from_label is False

    attach_labels([point, label], radius_m=5.0)
    assert point.z_from_label is True


def test_each_label_goes_to_one_point_the_nearest():
    far = _point("P1", 0, 0)
    near = _point("P2", 2.0, 0)
    label = _text("T1", 2.5, 0, "411.10")

    attach_labels([far, near, label], radius_m=3.0)

    assert near.points[0][2] == pytest.approx(411.10)
    assert far.z_from_label is False


def test_label_on_the_same_layer_wins_over_a_closer_foreign_one():
    point = _point("P1", 0, 0, layer="Отметка")
    own = _text("T1", 2.5, 0, "411.00", layer="Отметка")
    foreign = _text("T2", 1.0, 0, "999.00", layer="Горизонт +410")

    attach_labels([point, own, foreign], radius_m=3.0)

    assert point.label_handle == "T1"


def test_point_with_its_own_elevation_keeps_it():
    point = _point("P1", 0, 0, z=410.84)
    attach_labels([point, _text("T1", 0.2, 0.2, "999.99")], radius_m=3.0)

    assert point.points[0][2] == 410.84
    assert point.z_from_label is False


def test_label_without_a_point_creates_nothing():
    entities = [_text("T1", 0, 0, "410.84")]

    attach_labels(entities, radius_m=3.0)

    assert [item.kind for item in entities] == ["TEXT"]


# --- единицы ------------------------------------------------------------


def test_millimetre_units_with_metre_sized_extent_are_read_as_metres():
    scale, warnings = detect_units(4, (836.5, 678.3, 921.0, 865.1))

    assert scale is None
    assert [item.level for item in warnings] == ["info"]
    assert "миллиметр" in warnings[0].message and "метрах" in warnings[0].message


def test_huge_extent_suggests_the_millimetre_scale():
    scale, warnings = detect_units(4, (0.0, 0.0, 85_000.0, 187_000.0))

    assert scale == 0.001
    assert [item.level for item in warnings] == ["warning"]
    assert "0,001" in warnings[0].message


def test_missing_units_are_noted():
    scale, warnings = detect_units(None, (0.0, 0.0, 100.0, 100.0))

    assert scale is None
    assert [item.code for item in warnings] == ["units_missing"]


def test_metre_units_need_no_note():
    assert detect_units(6, (0.0, 0.0, 100.0, 100.0)) == (None, [])
