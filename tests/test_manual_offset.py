"""Сдвиг скважины от узла сетки (TASK-017, PR 2).

Сдвинутая на плане скважина сетки помнит узел (мировые координаты места,
куда её поставил генератор) и смещение от него в осях раскладки:
`manual: ["xy"]` и `manual_offset`. Ключи пишутся только у сдвинутой —
иначе у утверждённых паспортов сменился бы `designed_sha256`.
"""
from __future__ import annotations

from api.schemas.design import BlastDesignSchema
from design.lifecycle import designed_sha256
from design.models import BenchSurface, BlastDesign, BlockContour, Hole, ManualOffset, Point3

# `designed_sha256` паспорта `_design()` до TASK-017 PR 2: новые поля его не меняют.
UNMOVED_SHA256 = "1e5e5e1c0a7d8d81464854229b7ec1961395416e40dec4c08eddb7d29ee1c126"


def _hole(**changes) -> Hole:
    hole = Hole(
        id="1-1",
        row=0,
        col=0,
        collar=Point3(10.0, 10.0, 420.0),
        toe=Point3(10.0, 10.0, 409.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )
    for key, value in changes.items():
        setattr(hole, key, value)
    return hole


def _design(hole: Hole | None = None) -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(0.0, 0.0, 420.0), Point3(40.0, 0.0, 420.0), Point3(40.0, 20.0, 420.0)],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=410.0),
    )
    return BlastDesign(design_id="d-1", contour=contour, holes=[hole or _hole()])


def _through_api(design: BlastDesign) -> BlastDesign:
    return BlastDesign.from_dict(BlastDesignSchema(**design.to_dict()).model_dump())


def test_unmoved_hole_has_no_new_keys_and_keeps_its_hash():
    design = _design()
    again = _through_api(design)

    hole = again.to_dict()["holes"][0]
    assert "manual" not in hole
    assert "manual_offset" not in hole
    assert designed_sha256(design) == UNMOVED_SHA256
    assert designed_sha256(again) == UNMOVED_SHA256


def test_moved_hole_round_trips_through_the_api():
    offset = ManualOffset(node_x=10.0, node_y=10.0, along=0.75, across=-0.5)
    design = _design(_hole(manual=["xy"], manual_offset=offset))

    again = _through_api(design)

    data = again.to_dict()["holes"][0]
    assert data["manual"] == ["xy"]
    assert data["manual_offset"] == {"node_x": 10.0, "node_y": 10.0, "along": 0.75, "across": -0.5}
    assert again.holes[0].manual_offset == offset
    assert designed_sha256(again) == designed_sha256(design) != UNMOVED_SHA256



def test_design_subdrill_key_only_when_set_and_round_trips():
    """Проектный перебур (TASK-014): ключ — только у скважины, перебур которой сменила съёмка."""

    design = _design()
    assert "design_subdrill_m" not in design.to_dict()["holes"][0]
    assert designed_sha256(_through_api(design)) == UNMOVED_SHA256

    surveyed = _design(_hole(subdrill_m=0.5, design_subdrill_m=1.0))
    again = _through_api(surveyed)
    assert again.to_dict()["holes"][0]["design_subdrill_m"] == 1.0
    assert again.holes[0].design_subdrill_m == 1.0
    assert designed_sha256(again) == designed_sha256(surveyed)

# --- Перестроение сетки сохраняет сдвиги -----------------------------------

import math  # noqa: E402
from dataclasses import replace  # noqa: E402

import pytest  # noqa: E402

from design.geometry import layout_axes  # noqa: E402
from design.pattern import NODE_TOLERANCE_M, generate_pattern  # noqa: E402
from design.renumber import renumber_map  # noqa: E402

# Откос — южная сторона, ряды — с запада на восток (азимут 90°), «к откосу» — на юг.
PARAMS = {
    "pattern": "rectangular",
    "spacing_a_m": 5.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": 90.0,
    "angle_deg": 0.0,
    "subdrill_m": 1.0,
    "diameter_mm": 165.0,
    "offset_from_face_m": 2.0,
}


def _block(west: float = 0.0, east: float = 40.0) -> BlockContour:
    return BlockContour(
        vertices=[Point3(west, 0.0, 0.0), Point3(east, 0.0, 0.0), Point3(east, 30.0, 0.0), Point3(west, 30.0, 0.0)],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
    )


def _moved(hole: Hole, contour: BlockContour, along: float, across: float, params=PARAMS) -> Hole:
    """Скважина, сдвинутая на плане, как её сдвигает фронт: узел — где была."""
    ax, cx = layout_axes(contour, params["row_azimuth_deg"])
    dx, dy = along * ax[0] + across * cx[0], along * ax[1] + across * cx[1]
    return replace(
        hole,
        collar=Point3(hole.collar.x + dx, hole.collar.y + dy, hole.collar.z),
        toe=Point3(hole.toe.x + dx, hole.toe.y + dy, hole.toe.z),
        manual=["xy"],
        manual_offset=ManualOffset(node_x=hole.collar.x, node_y=hole.collar.y, along=along, across=across),
    )


def _by_id(holes: list[Hole]) -> dict[str, Hole]:
    return {hole.id: hole for hole in holes}


def _with(holes: list[Hole], moved: Hole) -> list[Hole]:
    return [moved if hole.id == moved.id else hole for hole in holes]


def _inner(holes: list[Hole]) -> Hole:
    # Скважина из середины блока: у неё узел есть при любом из контуров тестов.
    return min(holes, key=lambda h: math.hypot(h.collar.x - 20.0, h.collar.y - 14.0))


def test_axes_point_along_the_row_and_toward_the_face():
    along, across = layout_axes(_block(), 90.0)
    assert along == pytest.approx((1.0, 0.0))
    assert across == pytest.approx((0.0, -1.0))
    assert NODE_TOLERANCE_M == 0.05


def test_same_grid_keeps_the_shift_number_row_and_col():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    moved = _moved(node, contour, along=0.75, across=-0.5)
    warnings: list[str] = []

    again = generate_pattern(contour, PARAMS, _with(holes, moved), warnings=warnings)

    assert warnings == []
    assert len(again) == len(holes)
    hole = _by_id(again)[node.id]
    assert (hole.row, hole.col, hole.source) == (node.row, node.col, "generated")
    assert hole.manual == ["xy"]
    assert hole.manual_offset == ManualOffset(node.collar.x, node.collar.y, 0.75, -0.5)
    # «к откосу» — на юг: −0,5 к откосу — на 0,5 м вглубь (север).
    assert (hole.collar.x, hole.collar.y) == pytest.approx((node.collar.x + 0.75, node.collar.y + 0.5))
    assert hole.length_m == pytest.approx(node.length_m)
    unmoved = [h for h in again if h.id != node.id]
    assert all(not h.manual and h.manual_offset is None for h in unmoved)


def test_shift_follows_the_node_when_col_and_number_change():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    moved = _moved(node, contour, along=-1.25, across=0.0)
    # Блок шире на шаг a с обеих сторон: бровка с той же серединой — узлы те же,
    # но слева столбец добавился: номер и порядковый `col` сменились.
    wider = _block(west=-5.0, east=45.0)
    warnings: list[str] = []

    again = generate_pattern(wider, PARAMS, _with(holes, moved), warnings=warnings)

    assert warnings == []
    shifted = [h for h in again if h.manual_offset is not None]
    assert len(shifted) == 1
    hole = shifted[0]
    assert hole.id != node.id and hole.col != node.col
    assert (hole.manual_offset.node_x, hole.manual_offset.node_y) == pytest.approx((node.collar.x, node.collar.y))
    assert (hole.collar.x, hole.collar.y) == pytest.approx((node.collar.x - 1.25, node.collar.y))
    # Номер — по узлу: тот же, что у несдвинутой скважины в этом узле.
    plain = _by_id(generate_pattern(wider, PARAMS))
    assert plain[hole.id].collar.x == pytest.approx(node.collar.x)
    assert plain[hole.id].collar.y == pytest.approx(node.collar.y)


def test_grid_shift_by_a_whole_step_keeps_the_node():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    moved = _moved(node, contour, along=0.5, across=0.25)

    again = generate_pattern(contour, {**PARAMS, "grid_shift_along_m": 5.0}, _with(holes, moved))

    hole = _by_id(again)[node.id]
    assert hole.manual == ["xy"]
    assert (hole.collar.x, hole.collar.y) == pytest.approx((node.collar.x + 0.5, node.collar.y - 0.25))


@pytest.mark.parametrize("change", [{"spacing_a_m": 6.0}, {"grid_shift_along_m": 2.5}])
def test_lost_node_leaves_the_hole_as_manual_with_a_warning(change):
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    moved = _moved(node, contour, along=0.75, across=0.0)
    warnings: list[str] = []

    again = generate_pattern(contour, {**PARAMS, **change}, _with(holes, moved), warnings=warnings)

    manual = [h for h in again if h.source == "manual"]
    assert len(manual) == 1
    kept = manual[0]
    assert kept.id == "M-1" and kept.row == -1000
    assert (kept.collar.x, kept.collar.y) == (moved.collar.x, moved.collar.y)
    assert "xy" not in kept.manual and kept.manual_offset is None
    assert warnings == [
        f"Скважина {node.id} сдвинута вручную, узла сетки больше нет — оставлена как ручная (M-1)"
    ]
    assert all(h.manual_offset is None for h in again)


def test_lost_node_takes_the_next_free_manual_number():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    hand = replace(holes[0], id="M-1", row=-1000, source="manual")
    existing = [*_with(holes, _moved(node, contour, 0.75, 0.0)), hand]

    again = generate_pattern(contour, {**PARAMS, "spacing_a_m": 6.0}, existing)

    assert sorted(h.id for h in again if h.source == "manual") == ["M-1", "M-2"]


def test_without_a_contour_every_moved_hole_stays_manual():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    warnings: list[str] = []

    again = generate_pattern(contour, {**PARAMS, "spacing_a_m": 0.0}, _with(holes, _moved(node, contour, 1.0, 0.0)), warnings=warnings)

    assert [h.id for h in again] == ["M-1"]
    assert len(warnings) == 1


def test_one_new_node_goes_to_one_moved_hole_only():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    first = _moved(node, contour, 1.0, 0.0)
    # Вторая — тоже от этого узла (на 3 см), но дальше: ей узла не хватает.
    second = replace(
        _moved(node, contour, -1.0, 0.0),
        id="M-copy",
        manual_offset=ManualOffset(node.collar.x + 0.03, node.collar.y, -1.0, 0.0),
    )
    warnings: list[str] = []

    again = generate_pattern(contour, PARAMS, [*_with(holes, first), second], warnings=warnings)

    assert _by_id(again)[node.id].manual_offset.along == 1.0
    assert len(warnings) == 1 and "M-copy" in warnings[0]


def test_face_pair_and_its_vertical_both_keep_their_shift():
    contour = _block()
    params = {**PARAMS, "front_rows_mode": "pair", "front_rows_tilt_deg": 0.0, "offset_from_face_m": 4.0}
    holes = generate_pattern(contour, params)
    pair = next(h for h in holes if h.kind == "face_toe")
    vertical = _by_id(holes)[pair.id[:-1]]
    existing = _with(_with(holes, _moved(vertical, contour, 0.5, 0.0, params)), _moved(pair, contour, 0.5, 0.0, params))
    warnings: list[str] = []

    again = _by_id(generate_pattern(contour, params, existing, warnings=warnings))

    assert warnings == []
    assert again[pair.id].manual_offset is not None and again[vertical.id].manual_offset is not None
    assert again[pair.id].collar.x == pytest.approx(pair.collar.x + 0.5)


def test_renumber_counts_a_moved_hole_by_its_node():
    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    # Сдвиг на полшага вдоль — устье между эшелонами; номер — по узлу.
    existing = _with(holes, _moved(node, contour, 2.5, 0.0))

    assert renumber_map(existing, contour, PARAMS) == {}


def test_pattern_api_returns_the_moved_hole_and_the_warnings():
    from api.schemas.design import PatternGenerateRequest
    from api.services import design_service

    contour = _block()
    holes = generate_pattern(contour, PARAMS)
    node = _inner(holes)
    others = [h for h in holes if h.id != node.id][:1]
    existing = [_moved(node, contour, 0.75, 0.0), *others]

    def request(params):
        return PatternGenerateRequest(
            contour=contour.to_dict(), params=params, existing_holes=[h.to_dict() for h in existing]
        )

    kept = design_service.generate_pattern(request(PARAMS))
    lost = design_service.generate_pattern(request({**PARAMS, "spacing_a_m": 6.0}))

    assert kept.warnings == []
    moved = [h for h in kept.holes if h.manual_offset is not None]
    assert [h.id for h in moved] == [node.id] and moved[0].manual == ["xy"]
    assert lost.warnings == [
        f"Скважина {node.id} сдвинута вручную, узла сетки больше нет — оставлена как ручная (M-1)"
    ]
