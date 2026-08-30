from __future__ import annotations

import json

from cost.v2.import_v1 import build_import_sections
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
