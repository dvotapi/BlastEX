from __future__ import annotations

import json

from cost.v2.import_v1 import _code, build_import_sections
from cost.v2.references import (
    default_reference_snapshot,
    has_validation_errors,
    validate_reference_sections,
)


def test_v1_import_is_read_only_idempotent_and_requires_fixed_cost_review(tmp_path) -> None:
    team_dir = tmp_path / "data" / "teams" / "north"
    scenario_dir = team_dir / "scenarios"
    scenario_dir.mkdir(parents=True)
    source_files = {
        team_dir / "settings.json": {
            "team_name": "Северный юнит",
            "active_scenario_id": "drill_blast",
        },
        team_dir / "references.json": {
            "work_object_records": [{"name": "Карьер 1", "mobilization_km": 12}],
            "drill_rig_records": [
                {"name": "DML", "depreciation_per_shift_rub": 120_000, "fuel_l_per_h": 65}
            ],
            "explosive_records": [
                {"key": "emulsion", "name": "Эмульсия", "density_t_m3": 1.2}
            ],
        },
        scenario_dir / "drill_blast.json": {
            "cost_catalog_records": [
                {"id": "det", "name": "Детонатор", "category": "SI", "unit": "шт", "price": 700}
            ],
            "labor_catalog_records": [
                {"id": "driller", "name": "Машинист", "fixed_salary_monthly": 150_000}
            ],
            "fixed_cost_records": [
                {"id": "base", "name": "Содержание базы", "amount_rub": 1_000_000}
            ],
        },
    }
    for path, payload in source_files.items():
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = {path: path.read_bytes() for path in source_files}

    first, report = build_import_sections(tmp_path, "north", default_reference_snapshot())
    second, _ = build_import_sections(tmp_path, "north", default_reference_snapshot())

    assert first == second
    assert {path: path.read_bytes() for path in source_files} == before
    assert first["production_units"][0].name == "Северный юнит"
    assert first["sites"][0].payload["mobilization_km"] == 12
    assert any(item.payload.get("requires_cost_v2_classification") for item in first["cost_items"])
    assert any("Постоянные затраты V1" in warning for warning in report.warnings)
    assert not has_validation_errors(validate_reference_sections(first))


def test_import_merges_with_existing_records_and_keeps_rocks(tmp_path) -> None:
    from cost.v2.models import ReferenceItem, ReferenceSnapshot

    team_dir = tmp_path / "data" / "teams" / "north"
    (team_dir / "scenarios").mkdir(parents=True)
    (team_dir / "references.json").write_text(
        json.dumps(
            {
                "rock_records": [{"name": "Гранит", "density_t_m3": 2.65, "ucs_mpa": 150, "fissuring_ff": 2.0}],
                "work_object_records": [{"name": "Карьер 1", "mobilization_km": 12}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (team_dir / "settings.json").write_text(json.dumps({"active_scenario_id": "drill_blast"}), encoding="utf-8")
    (team_dir / "scenarios" / "drill_blast.json").write_text(
        json.dumps(
            {
                "fixed_cost_records": [{"id": "fc_21_storage", "section": "2.1", "name": "Хранение", "amount_rub": 10}],
                "labor_catalog_records": [{"id": "labor_master", "name": "Мастер", "fixed_salary_monthly": 1}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    current = default_reference_snapshot()
    sections = dict(current.sections)
    sections["positions"] = (ReferenceItem("POS_DRILLER", "Машинист БУ", {"category": "DIRECT", "operation_code": None}),)
    sections["production_units"] = (ReferenceItem("UNIT_1", "Юнит 1"),)
    sections["materials"] = (ReferenceItem("MAT_BIT", "Коронка", {"category": "TOOL"}),)
    current = ReferenceSnapshot(revision_id="R", sections=sections)

    result, _ = build_import_sections(tmp_path, "north", current)

    assert {item.code for item in result["positions"]} >= {"POS_DRILLER", "POSITION_LABOR_MASTER"}
    assert {item.code for item in result["production_units"]} == {"UNIT_1", "UNIT_NORTH"}
    assert {item.code for item in result["materials"]} >= {"MAT_BIT"}
    assert [item.name for item in result["rocks"]] == ["Гранит"]
    assert result["rocks"][0].payload["ucs_mpa"] == 150
    fixed = next(item for item in result["cost_items"] if item.payload.get("legacy_section") == "2.1")
    assert fixed.payload["legacy_ref"] == "fc_21_storage"


def test_code_transliteration() -> None:
    """Код записи собирается из русского названия однозначно и без мусора."""

    assert _code("Подъезд") == "POD_EZD"
    assert _code("Соль") == "SOL"
    assert _code("Ёлка") == "ELKA"
    assert _code("Май") == "MAY"
    assert _code("JK 830-3 буровой") == "JK_830_3_BUROVOY"
    assert _code("ъь") == "ITEM"
    assert len(_code("Очень длинное наименование " * 10)) == 64


def test_code_collision_between_different_records_is_reported(tmp_path) -> None:
    """Разные записи V1 с одинаковым кодом не должны исчезать молча."""

    team_dir = tmp_path / "data" / "teams" / "north"
    scenario_dir = team_dir / "scenarios"
    scenario_dir.mkdir(parents=True)
    (team_dir / "settings.json").write_text(
        json.dumps({"team_name": "Северный юнит", "active_scenario_id": "drill_blast"}),
        encoding="utf-8",
    )
    (scenario_dir / "drill_blast.json").write_text(
        json.dumps(
            {
                "cost_catalog_records": [
                    {"id": "Соль", "name": "Соль каменная", "unit": "кг", "price": 10},
                    {"id": "Соль!", "name": "Соль техническая", "unit": "кг", "price": 20},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    sections, report = build_import_sections(tmp_path, "north", default_reference_snapshot())

    codes = [item.code for item in sections["materials"]]
    assert codes == ["MAT_SOL", "MAT_SOL_2"]
    assert any("MAT_SOL" in warning and "код" in warning.lower() for warning in report.warnings)
