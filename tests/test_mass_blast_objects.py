"""Охраняемые объекты проекта МВ v2 (TASK-018, PR 2, §6 плана; решение В1)."""
from __future__ import annotations

import pytest

from design.mass_blast_objects import ObjectZones, assess_project_objects, situation_candidates

BLOCK = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 30.0)], [])]
ZONES = ObjectZones(
    people_m=300.0, mechanisms_m=200.0, seismic_m=100.0, seismic_raw_m=86.0, airblast_m=50.0,
    buildings_m=100.0, k_ground=5.0, k_structure=2.0,
)


def _layer(name: str, kind: str, points, closed: bool = False) -> dict:
    return {"name": name, "kind": kind, "lines": [{"points": [list(p) + [0.0] for p in points], "closed": closed}]}


LAYERS = [
    _layer("Здания ДСК", "building", [(150, 0), (160, 0), (160, 10), (150, 10)], closed=True),
    _layer("ЛЭП 6 кВ", "power_line", [(0, 120), (100, 120)]),
    _layer("Дорога", "road", [(-400, 0), (-400, 30)]),
    _layer("Склад", "stockpile", [(60, 0), (70, 0)]),
    _layer("Прочее", "other", [(55, 0), (56, 0)]),
]


def test_candidates_by_kind_and_distance_from_contour():
    candidates = situation_candidates(LAYERS, BLOCK)
    by_name = {item["name"]: item for item in candidates}
    assert set(by_name) == {"Здания ДСК", "ЛЭП 6 кВ", "Дорога"}  # склады и «прочее» не охраняемые
    assert by_name["Здания ДСК"]["distance_m"] == pytest.approx(100.0)
    assert by_name["Здания ДСК"]["kind"] == "buildings"
    assert by_name["ЛЭП 6 кВ"]["distance_m"] == pytest.approx(90.0)
    assert by_name["ЛЭП 6 кВ"]["kind"] == "structures"
    assert by_name["Дорога"]["key"] == "SITUATION:Дорога"


def test_without_contour_distance_from_collars():
    candidates = situation_candidates(LAYERS[:1], [([], [(140.0, 5.0)])])
    assert candidates[0]["distance_m"] == pytest.approx(10.0)


def test_same_layer_in_two_versions_is_one_object():
    older = _layer("ЛЭП 6 кВ", "power_line", [(0, 200), (100, 200)])
    candidates = situation_candidates([older, LAYERS[1]], BLOCK)
    assert [item["distance_m"] for item in candidates] == [pytest.approx(90.0)]


def test_only_objects_within_the_largest_zone_are_listed():
    rows, _ = assess_project_objects(situation_candidates(LAYERS, BLOCK), [], ZONES)
    assert {row.name for row in rows} == {"Здания ДСК", "ЛЭП 6 кВ"}  # дорога в 400 м дальше 300 м


def test_assessment_and_annotations_survive_recalculation():
    notes = [{"source": "SITUATION", "key": "SITUATION:ЛЭП 6 кВ", "measures": "отключение на время взрыва"}]
    rows, _ = assess_project_objects(situation_candidates(LAYERS, BLOCK), notes, ZONES)
    line = next(row for row in rows if row.name == "ЛЭП 6 кВ")
    # Сооружения — max(механизмы, сейсмика) = 200 м: 90 м — в зоне, с мероприятиями.
    assert line.required_m == 200 and line.position == "В ЗОНЕ" and line.measures == "отключение на время взрыва"
    building = next(row for row in rows if row.name == "Здания ДСК")
    assert building.required_m == 100 and building.position == "вне зоны"


def test_own_ground_and_structure_coefficients():
    """K_г, K_с объекта: r_с пересчитывается пропорционально и снова вверх до 50 м (В9 PR 1)."""

    notes = [{"source": "SITUATION", "key": "SITUATION:Здания ДСК", "k_ground": 8, "k_structure": 2}]
    rows, _ = assess_project_objects(situation_candidates(LAYERS, BLOCK), notes, ZONES)
    building = next(row for row in rows if row.name == "Здания ДСК")
    # 86·(8·2)/(5·2) = 137,6 → 150 м: здание в 100 м — в зоне.
    assert building.required_m == 150 and building.factor == "сейсмика" and building.position == "В ЗОНЕ"


def test_manual_objects_and_incomplete_entries():
    entries = [
        {"source": "MANUAL", "name": "Вахтовый посёлок", "kind": "people", "distance_m": 1200},
        {"source": "MANUAL", "name": "", "kind": "people", "distance_m": 10},
        {"source": "MANUAL", "name": "Кран", "kind": "", "distance_m": 10},
    ]
    rows, issues = assess_project_objects([], entries, ZONES)
    assert [(row.name, row.position) for row in rows] == [("Вахтовый посёлок", "вне зоны")]
    assert {issue.code for issue in issues} == {"object_incomplete", "object_kind_unknown"}


def test_smaller_own_coefficients_lower_the_required_distance():
    """Меньшие K_г·K_с объекта уменьшают r_с: расчётная зона для зданий их не перекрывает."""

    notes = [{"source": "SITUATION", "key": "SITUATION:Здания ДСК", "k_ground": 5, "k_structure": 1}]
    zones = ObjectZones(
        people_m=300.0, mechanisms_m=200.0, seismic_m=200.0, seismic_raw_m=172.0, airblast_m=50.0,
        buildings_m=200.0, k_ground=5.0, k_structure=2.0,
    )
    rows, _ = assess_project_objects(situation_candidates(LAYERS, BLOCK), notes, zones)
    building = next(row for row in rows if row.name == "Здания ДСК")
    # 172·(5·1)/(5·2) = 86 → 100 м: здание в 100 м — вне зоны, фактор — сейсмика.
    assert building.required_m == 100 and building.factor == "сейсмика" and building.position == "вне зоны"
    manual = ObjectZones(**{**zones.__dict__, "buildings_m": 400.0, "buildings_manual": True})
    rows, _ = assess_project_objects(situation_candidates(LAYERS, BLOCK), notes, manual)
    building = next(row for row in rows if row.name == "Здания ДСК")
    assert building.required_m == 400 and building.factor == "принято проектом"


def test_contourless_block_keeps_its_collars():
    """Блок без контура в проекте с другим блоком с контуром: расстояние — и от его устьев."""

    line = [_layer("ЛЭП у второго блока", "power_line", [(1000, -10), (1000, 10)])]
    candidates = situation_candidates(line, [BLOCK[0], ([], [(1000.0, 0.0)])])
    assert candidates[0]["distance_m"] == pytest.approx(0.0)


def test_object_with_bigger_own_coefficients_is_not_dropped():
    """Свои K_г·K_с объекта больше — его зона шире зон проекта: объект в список не теряется."""

    far = [_layer("Посёлок", "building", [(400, 0), (410, 0), (410, 10), (400, 10)], closed=True)]
    zones = ObjectZones(
        people_m=200.0, mechanisms_m=150.0, seismic_m=100.0, seismic_raw_m=100.0, airblast_m=50.0,
        buildings_m=100.0, k_ground=5.0, k_structure=2.0,
    )
    notes = [{"source": "SITUATION", "key": "SITUATION:Посёлок", "k_ground": 20, "sensitive": True}]
    rows, issues = assess_project_objects(situation_candidates(far, BLOCK), notes, zones)
    # 100·(20·2)/(5·2) = 400 м; посёлок в 350 м — в зоне, нужны эксперты (п. 808).
    assert rows[0].required_m == 400 and rows[0].position == "В ЗОНЕ"
    assert "expert_required" in {issue.code for issue in issues}
    rows, issues = assess_project_objects(situation_candidates(far, BLOCK), [], zones)
    assert rows == [] and issues == []
