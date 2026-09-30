"""Авторазметка ролей слоёв и сущностей чертежа маркшейдера."""
from __future__ import annotations

import pytest

from design.spatial.cad.model import CadEntity
from design.spatial.cad.roles import RoleParams, TemplateEntry, assign_roles, layer_key


def _line(handle: str, layer: str, zs: list[float], closed: bool = False) -> CadEntity:
    points = [(float(index * 10), float(index % 2), z) for index, z in enumerate(zs)]
    return CadEntity(handle=handle, layer=layer, kind="POLYLINE3D", points=points, closed=closed)


def _ring(handle: str, layer: str, z: float = 419.8) -> CadEntity:
    return CadEntity(
        handle=handle,
        layer=layer,
        kind="LWPOLYLINE",
        points=[(0, 0, z), (40, 0, z), (40, 30, z), (0, 30, z)],
        closed=True,
        closed_by_gap=True,
    )


def _point(handle: str, layer: str, z: float) -> CadEntity:
    return CadEntity(handle=handle, layer=layer, kind="POINT", points=[(1.0, 1.0, z)])


def _text(handle: str, layer: str, text: str) -> CadEntity:
    return CadEntity(handle=handle, layer=layer, kind="TEXT", points=[(1.0, 1.0, 0.0)], text=text)


def _roles(entities: list[CadEntity]) -> dict[str, tuple[str, str]]:
    return {item.handle: (item.role, item.role_origin) for item in entities}


def _layers(result) -> dict[str, tuple[str, str]]:
    return {item.name: (item.role, item.origin) for item in result.layers}


def test_numbered_block_layer_with_a_closed_line_is_the_contour():
    entities = [_ring("C", "блок 66 вар 2"), _line("D", "блок 66 вар 2", [419.8, 419.8])]

    result = assign_roles(entities, {}, RoleParams())

    assert _layers(result)["блок 66 вар 2"] == ("block_contour", "auto")
    assert _roles(entities) == {"C": ("block_contour", "auto"), "D": ("design_line", "auto")}


def test_block_boundary_layer_without_a_number_is_the_contour():
    entities = [_ring("C", "граница блока")]

    assign_roles(entities, {}, RoleParams())

    assert entities[0].role == "block_contour"


def test_crest_layers_named_top_and_bottom_need_no_elevation():
    entities = [_line("T", "верхняя бровка", [0, 0]), _line("B", "Нижняя Бровка", [0, 0])]

    result = assign_roles(entities, {}, RoleParams())

    assert _roles(entities) == {"T": ("crest_top", "auto"), "B": ("crest_bottom", "auto")}
    assert _layers(result)["Нижняя Бровка"] == ("crest_bottom", "auto")


def test_bench_layer_splits_crests_by_z_around_the_floor_from_its_name():
    entities = [
        _line("L1", "Горизонт +410", [410.0, 411.7]),
        _line("L2", "Горизонт +410", [409.7, 413.6, 412.0]),
        _line("U1", "Горизонт +410", [419.5, 421.3]),
        _point("P", "Горизонт +410", 410.5),
        _text("T", "Горизонт +410", "410.50"),
    ]

    result = assign_roles(entities, {}, RoleParams())

    assert _layers(result)["Горизонт +410"] == ("crests_by_z", "auto")
    assert result.floor_z_m == pytest.approx(410.0)
    assert _roles(entities) == {
        "L1": ("crest_bottom", "z"),
        "L2": ("crest_bottom", "z"),
        "U1": ("crest_top", "z"),
        "P": ("spot_heights", "auto"),
        "T": ("spot_heights", "auto"),
    }
    assert any("410" in item.message and "Горизонт +410" in item.message for item in result.warnings)


def test_explicit_floor_moves_the_threshold():
    entities = [_line("A", "Горизонт +410", [416.0, 416.5]), _line("B", "Горизонт +410", [421.0, 421.5])]

    assign_roles(entities, {}, RoleParams(floor_z_m=412.0, bench_height_m=10.0))

    assert _roles(entities) == {"A": ("crest_bottom", "z"), "B": ("crest_top", "z")}


def test_without_a_floor_crests_split_at_the_largest_elevation_gap():
    entities = [
        _line("A", "бровки", [300.0, 301.0]),
        _line("B", "бровки", [300.5, 301.5]),
        _line("C", "бровки", [310.0, 311.0]),
    ]

    result = assign_roles(entities, {}, RoleParams())

    assert result.floor_z_m is None
    assert _roles(entities) == {"A": ("crest_bottom", "z"), "B": ("crest_bottom", "z"), "C": ("crest_top", "z")}


def test_crests_without_a_gap_stay_top_with_a_warning():
    entities = [_line("A", "бровки", [300.0, 301.0]), _line("B", "бровки", [300.5, 301.5])]

    result = assign_roles(entities, {}, RoleParams())

    assert {item.role for item in entities} == {"crest_top"}
    assert any(item.code == "crest_split" for item in result.warnings)


def test_contour_lines_are_not_bench_horizons():
    entities = [
        _line("H", "Горизонтали", [415.0, 415.0, 415.0]),
        _line("F", "Горизонтали", [415.0, 416.0]),
    ]

    result = assign_roles(entities, {}, RoleParams())

    assert _layers(result)["Горизонтали"] == ("contour_line", "auto")
    assert _roles(entities) == {"H": ("contour_line", "auto"), "F": ("feature_line", "auto")}


def test_survey_layer_gives_spot_heights_for_points_and_3d_lines():
    entities = [
        _point("P", "Отметка", 410.8),
        _line("S", "Съёмка", [410.0, 411.0, 412.0]),
        _line("K", "Съёмка", [0.0, 0.0]),
    ]

    assign_roles(entities, {}, RoleParams())

    assert _roles(entities) == {
        "P": ("spot_heights", "auto"),
        "S": ("spot_heights", "auto"),
        "K": ("feature_line", "auto"),
    }


def test_everything_else_is_situation_but_points_with_z_are_spot_heights():
    entities = [
        _line("D", "Отвал вскрышных пород", [421.5, 421.8]),
        _point("P", "ЛЭП", 425.0),
        _point("Z", "ЛЭП", 0.0),
    ]

    assign_roles(entities, {}, RoleParams())

    assert _roles(entities) == {
        "D": ("situation", "auto"),
        "P": ("spot_heights", "auto"),
        "Z": ("situation", "auto"),
    }


def test_layer_key_ignores_case_and_spacing():
    assert layer_key(" горизонт  +410 ") == layer_key("Горизонт +410") == "горизонт +410"


def test_site_template_wins_over_the_rules():
    entities = [
        _line("L", "  горизонт  +410 ", [410.5, 411.0]),
        _line("U", "  горизонт  +410 ", [420.5, 421.0]),
        _line("D", "Отвал вскрышных пород", [421.5, 421.8]),
    ]
    template = {"горизонт +410": "crests_by_z", "отвал вскрышных пород": "ignore"}

    result = assign_roles(entities, template, RoleParams())

    assert _layers(result) == {
        "  горизонт  +410 ": ("crests_by_z", "template"),
        "Отвал вскрышных пород": ("ignore", "template"),
    }
    assert _roles(entities) == {
        "L": ("crest_bottom", "z"),
        "U": ("crest_top", "z"),
        "D": ("ignore", "template"),
    }


def test_manual_roles_override_template_and_rules():
    entities = [
        _line("A", "Горизонт +410", [410.5, 411.0]),
        _line("B", "Горизонт +410", [420.5, 421.0]),
        _line("D", "Отвал вскрышных пород", [421.5, 421.8]),
    ]

    result = assign_roles(
        entities,
        {"отвал вскрышных пород": "ignore"},
        RoleParams(),
        manual_layers={"Отвал вскрышных пород": "situation"},
        manual_entities={"A": "feature_line"},
    )

    assert _layers(result)["Отвал вскрышных пород"] == ("situation", "manual")
    assert _roles(entities) == {
        "A": ("feature_line", "manual"),
        "B": ("crest_top", "z"),
        "D": ("situation", "manual"),
    }


def test_points_on_a_line_layer_get_a_point_role():
    entities = [_ring("C", "блок 66"), _point("P", "блок 66", 419.0), _point("Q", "блок 66", 0.0)]

    assign_roles(entities, {}, RoleParams())

    assert _roles(entities)["P"] == ("spot_heights", "auto")
    assert _roles(entities)["Q"] == ("situation", "auto")


def test_unknown_template_role_is_ignored():
    entities = [_line("D", "Отвал", [421.5, 421.8])]

    result = assign_roles(entities, {"отвал": "no_such_role"}, RoleParams())

    assert _layers(result)["Отвал"] == ("situation", "auto")


def test_unconfirmed_template_role_treats_points_like_the_rules_do():
    """Шаблон, пополненный догадкой «авто», не должен менять роли при повторном импорте."""

    entities = [_line("R", "Дорога", [412.0, 412.5]), _point("P", "Дорога", 412.3)]

    assign_roles(entities, {"дорога": TemplateEntry("situation")}, RoleParams())

    assert _roles(entities) == {"R": ("situation", "template"), "P": ("spot_heights", "template")}


def test_confirmed_template_situation_keeps_points_out_of_the_surface():
    entities = [_line("R", "ЛЭП", [412.0, 412.5]), _point("P", "ЛЭП", 425.0)]

    assign_roles(entities, {"лэп": TemplateEntry("situation", manual=True)}, RoleParams())

    assert _roles(entities)["P"] == ("situation", "template")


def _flat(handle: str, layer: str) -> CadEntity:
    return CadEntity(handle=handle, layer=layer, kind="POLYLINE2D", points=[(0.0, 0.0, 0.0), (20.0, 5.0, 0.0)])


@pytest.mark.parametrize("layer", ["Горизонт +410", "бровки"])
def test_lines_without_elevation_are_not_crests(layer):
    """Линия на Z = 0 на слое бровок — не нижняя бровка: иначе уступ 420 м «построится»."""

    entities = [_line("L", layer, [410.0, 411.0]), _line("U", layer, [420.0, 421.0]), _flat("F", layer)]

    result = assign_roles(entities, {}, RoleParams())

    assert _roles(entities) == {"L": ("crest_bottom", "z"), "U": ("crest_top", "z"), "F": ("feature_line", "auto")}
    assert any(item.code == "crest_without_z" and layer in item.message for item in result.warnings)


def test_block_layer_of_open_lines_gives_design_lines():
    """Контур, присланный открытыми участками, — проектные линии, а не ситуация (§1, §2)."""

    entities = [_line("A", "блок 67", [419.8, 419.8]), _line("B", "блок 67", [419.8, 419.8])]

    result = assign_roles(entities, {}, RoleParams())

    assert _layers(result)["блок 67"] == ("design_line", "auto")
    assert _roles(entities) == {"A": ("design_line", "auto"), "B": ("design_line", "auto")}
