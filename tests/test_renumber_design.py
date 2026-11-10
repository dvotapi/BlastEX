"""Перенумерация скважин сохранённого проекта по правилу эшелонов (доработки 10.11.2026).

Сетку, построенную до нумерации по эшелонам (PR #167), перестраивать не нужно:
`renumber_map` даёт новые номера по тому же правилу, что генератор, не двигая
скважины. Проверка: сетка генератора с перемешанными номерами получает от
перенумерации ровно номера генератора.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from design.renumber import renumber_map
from design.pattern import generate_pattern
from tests.test_block67_back_layout import _contour as block67_contour
from tests.test_echelon_numbering import BASE, _rect

CASES = {
    "блок 67, ряд вдоль изогнутой бровки": (
        block67_contour, {**BASE, "row_azimuth_deg": 0.0, "first_row_follow_face": True},
    ),
    "блок 67, обычный": (block67_contour, {**BASE, "row_azimuth_deg": 0.0}),
    "блок 67, от тыла": (block67_contour, {**BASE, "row_azimuth_deg": 0.0, "layout_anchor": "back", "back_offset_m": 2.0}),
    "прямоугольник, бровка с юга": (lambda: _rect([[0, 1]]), BASE),
    "прямоугольник, пара у откоса": (lambda: _rect([[0, 1]]), {**BASE, "front_rows_mode": "pair"}),
}


def _scrambled(holes):
    """Номера «по старому»: подряд в обратном порядке, пары — с суффиксом своей вертикальной."""
    ids = [hole.id for hole in holes]
    renamed = {old: f"X{index}" for index, old in enumerate(reversed(ids)) if not old.endswith("T")}
    out = []
    for hole in holes:
        if hole.id.endswith("T") and hole.id[:-1] in renamed:
            out.append(replace(hole, id=renamed[hole.id[:-1]] + "T"))
        else:
            out.append(replace(hole, id=renamed.get(hole.id, hole.id)))
    return out


@pytest.mark.parametrize("name", list(CASES))
def test_renumber_restores_generator_numbers(name):
    contour_of, params = CASES[name]
    contour = contour_of()
    generated = generate_pattern(contour, params)
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, params)
    renumbered = [mapping.get(hole.id, hole.id) for hole in scrambled]
    assert renumbered == [hole.id for hole in generated]


def test_renumber_of_correct_numbers_is_empty():
    contour = block67_contour()
    params = {**BASE, "row_azimuth_deg": 0.0, "first_row_follow_face": True}
    assert renumber_map(generate_pattern(contour, params), contour, params) == {}


def test_manual_holes_keep_numbers():
    contour = _rect([[0, 1]])
    holes = generate_pattern(contour, BASE)
    manual = replace(holes[0], id="M-1", source="manual")
    mapping = renumber_map(_scrambled(holes[1:]) + [manual], contour, BASE)
    assert "M-1" not in mapping


def test_mapping_is_a_permutation_without_duplicates():
    contour = block67_contour()
    params = {**BASE, "row_azimuth_deg": 0.0}
    scrambled = _scrambled(generate_pattern(contour, params))
    mapping = renumber_map(scrambled, contour, params)
    result = [mapping.get(hole.id, hole.id) for hole in scrambled]
    assert len(set(result)) == len(result)


# --- POST /design/holes/renumber ------------------------------------------

def _client():
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routers import design as design_router

    os.environ["BLASTEX_API_KEY"] = "test-api-key"
    os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
    app = FastAPI()
    app.include_router(design_router.router, prefix="/api/v1")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def test_renumber_route_returns_mapping():
    contour = _rect([[0, 1]])
    generated = generate_pattern(contour, BASE)
    scrambled = _scrambled(generated)
    response = _client().post(
        "/api/v1/design/holes/renumber",
        json={"holes": [h.to_dict() for h in scrambled], "contour": contour.to_dict(), "params": BASE},
    )
    assert response.status_code == 200, response.text
    mapping = response.json()["mapping"]
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


def test_renumber_route_empty_holes_is_422():
    contour = _rect([[0, 1]])
    response = _client().post("/api/v1/design/holes/renumber", json={"holes": [], "contour": contour.to_dict(), "params": {}})
    assert response.status_code == 422


# --- правки по /code-review PR #172 ---------------------------------------

def test_manual_hole_between_columns_does_not_shift_echelons():
    """Ручная скважина не становится «столбцом» для ряда вдоль бровки."""
    contour = block67_contour()
    params = {**BASE, "row_azimuth_deg": 0.0, "first_row_follow_face": True}
    generated = generate_pattern(contour, params)
    # Ряд вдоль бровки (row 0) стоит не на столбцах; ручная скважина в глубине
    # блока на линии одной из них (вдоль ряда — ось y при азимуте 0°).
    face = next(h for h in generated if h.row == 0)
    deep = max((h for h in generated if h.row != 0), key=lambda h: h.collar.x)
    middle = replace(deep, id="M-1", source="manual", row=3,
                     collar=replace(deep.collar, y=face.collar.y + 0.01),
                     toe=replace(deep.toe, y=face.collar.y + 0.01))
    scrambled = _scrambled(generated) + [middle]
    mapping = renumber_map(scrambled, contour, params)
    assert [mapping.get(h.id, h.id) for h in scrambled[:-1]] == [h.id for h in generated]


def test_missing_row_azimuth_is_inferred_from_holes():
    """Нет `row_azimuth_deg` (сетка импортирована или расставлена вручную) —
    направление рядов — по самим скважинам, ближе к бровке."""
    contour = _rect([[0, 1]])
    generated = generate_pattern(contour, BASE)
    assert BASE["row_azimuth_deg"] == 90.0
    params = {key: value for key, value in BASE.items() if key != "row_azimuth_deg"}
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, params)
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


def test_generator_and_renumber_share_face_row_rule():
    from design import pattern

    assert pattern.face_row_numbering_xy is not None


# --- правки по ревью Codex PR #172 -----------------------------------------

def test_staggered_grid_without_face_row_keeps_generator_numbers():
    """Привязка ряда у бровки к столбцам — только при «ряде вдоль бровки», как у генератора."""
    contour = _rect([[0, 1]], height=7.0)
    params = {**BASE, "pattern": "staggered"}
    generated = generate_pattern(contour, params)
    assert renumber_map(generated, contour, params) == {}
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, params)
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


def _without_azimuth(params):
    return {key: value for key, value in params.items() if key != "row_azimuth_deg"}


def test_inferred_azimuth_keeps_sub_degree_precision():
    """Сетка под 89,6° без сохранённого азимута: округление до градуса сдвинуло бы
    эшелоны на 7 см на 10 м — больше допуска эшелона 5 см (ревью Codex PR #172)."""
    contour = _rect([[0, 1]], width=80.0, height=60.0)
    params = {**BASE, "spacing_a_m": 10.0, "burden_b_m": 10.0, "row_azimuth_deg": 89.6}
    generated = generate_pattern(contour, params)
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, _without_azimuth(params))
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


def test_inferred_azimuth_of_rectangular_grid_with_wide_rows():
    """Шаг вдоль ряда 8 м, ЛСП 3 м: соседи вдоль ряда дальше 1,5 ближайшего
    расстояния, но ряды всё равно — вдоль бровки (ревью Codex PR #172)."""
    contour = _rect([[0, 1]], width=60.0, height=20.0)
    params = {**BASE, "pattern": "rectangular", "spacing_a_m": 8.0, "burden_b_m": 3.0}
    generated = generate_pattern(contour, params)
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, _without_azimuth(params))
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


def test_orphan_face_pair_collision_is_rejected():
    """Вертикальную удалили, её пара осталась: перенумерация не должна дать
    другой скважине тот же номер (ревью Codex PR #172)."""
    from design.renumber import RenumberConflict

    contour = _rect([[0, 1]])
    params = {**BASE, "front_rows_mode": "pair"}
    generated = generate_pattern(contour, params)
    pairs = [h for h in generated if h.id.endswith("T")]
    assert len(pairs) >= 2
    orphan, kept = pairs[0], pairs[1]
    vertical = orphan.id[:-1]
    # Вертикальную сироты удалили; «старые» номера: сирота — номер, который
    # по правилу достанется паре `kept`, остальные — перемешаны.
    holes = [h for h in generated if h.id not in (vertical, orphan.id)]
    scrambled = _scrambled(holes) + [replace(orphan, id=kept.id)]
    with pytest.raises(RenumberConflict, match=kept.id):
        renumber_map(scrambled, contour, params)


def test_renumber_route_conflict_is_422():
    contour = _rect([[0, 1]])
    params = {**BASE, "front_rows_mode": "pair"}
    generated = generate_pattern(contour, params)
    pairs = [h for h in generated if h.id.endswith("T")]
    orphan, kept = pairs[0], pairs[1]
    holes = [h for h in generated if h.id not in (orphan.id[:-1], orphan.id)]
    scrambled = _scrambled(holes) + [replace(orphan, id=kept.id)]
    response = _client().post(
        "/api/v1/design/holes/renumber",
        json={"holes": [h.to_dict() for h in scrambled], "contour": contour.to_dict(), "params": params},
    )
    assert response.status_code == 422
    assert kept.id in response.json()["detail"]


def test_back_layout_with_face_row_flag_keeps_generator_numbers():
    """«От тыла» с оставшейся галочкой «Первый ряд вдоль бровки»: генератор ряд
    у бровки не строит — и перенумерация его не привязывает (ревью Codex PR #172)."""
    contour = block67_contour()
    params = {**BASE, "layout_anchor": "back", "back_offset_m": 2.0, "first_row_follow_face": True}
    generated = generate_pattern(contour, params)
    assert renumber_map(generated, contour, params) == {}
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, params)
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


def test_satellites_do_not_split_face_row_echelons():
    """Сателлиты генератор добавляет после привязки ряда у бровки — и
    перенумерация не берёт их в столбцы (ревью Codex PR #172)."""
    contour = block67_contour()
    params = {**BASE, "row_azimuth_deg": 0.0, "first_row_follow_face": True, "satellite_holes": True}
    generated = generate_pattern(contour, params)
    assert any(h.kind == "satellite" for h in generated)
    assert renumber_map(generated, contour, params) == {}


def test_inferred_azimuth_of_staggered_grid_with_wide_rows():
    """Шахматка 8 × 3 м: ближайшие соседки — по диагоналям, ряд (8 м) дальше;
    ряды всё равно вдоль бровки (ревью Codex PR #172)."""
    contour = _rect([[0, 1]], width=100.0, height=80.0)
    params = {**BASE, "pattern": "staggered", "spacing_a_m": 8.0, "burden_b_m": 3.0}
    generated = generate_pattern(contour, params)
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, _without_azimuth(params))
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]


@pytest.mark.parametrize("kind", ["buffer", "contour", "presplit", "trim"])
def test_inferred_azimuth_of_wall_kind_main_grid(kind):
    """Основная сетка стеночного вида без сохранённого азимута: направление —
    по её же скважинам, а не 0° (ревью Codex PR #172)."""
    contour = _rect([[0, 1]], width=24.0, height=15.0)
    params = {**BASE, "default_kind": kind}
    generated = generate_pattern(contour, params)
    assert all(h.kind == kind for h in generated)
    scrambled = _scrambled(generated)
    mapping = renumber_map(scrambled, contour, _without_azimuth(params))
    assert [mapping.get(h.id, h.id) for h in scrambled] == [h.id for h in generated]
