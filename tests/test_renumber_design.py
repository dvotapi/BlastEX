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
