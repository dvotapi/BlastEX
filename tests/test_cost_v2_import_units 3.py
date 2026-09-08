"""Импорт Cost V1: единицы измерения и слияние типов техники."""
from __future__ import annotations

import json

from cost.v2.import_v1 import build_import_sections
from cost.v2.models import ReferenceItem
from cost.v2.references import default_reference_snapshot, has_validation_errors, validate_reference_sections


def _team(tmp_path, *, catalog_unit: str) -> None:
    team_dir = tmp_path / "data" / "teams" / "north"
    (team_dir / "scenarios").mkdir(parents=True)
    (team_dir / "settings.json").write_text(
        json.dumps({"team_name": "Северный юнит", "active_scenario_id": "drill_blast"}), encoding="utf-8"
    )
    (team_dir / "references.json").write_text(
        json.dumps({"drill_rig_records": [{"name": "DML", "fuel_l_per_h": 65}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (team_dir / "scenarios" / "drill_blast.json").write_text(
        json.dumps(
            {"cost_catalog_records": [
                {"id": "det", "name": "Детонатор", "category": "SI", "unit": catalog_unit, "price": 700}
            ]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_known_unit_becomes_a_code(tmp_path) -> None:
    _team(tmp_path, catalog_unit="шт")
    sections, report = build_import_sections(tmp_path, "north", default_reference_snapshot())
    material = next(item for item in sections["materials"] if item.code.startswith("MAT_"))
    assert material.payload["unit"] == "PIECE"
    assert not any("не распознаны" in warning for warning in report.warnings)


def test_ambiguous_abbreviation_is_not_guessed(tmp_path) -> None:
    """«см» в номенклатуре — сантиметр; принять его за смену значит испортить данные."""

    _team(tmp_path, catalog_unit="см")
    sections, report = build_import_sections(tmp_path, "north", default_reference_snapshot())
    material = next(item for item in sections["materials"] if item.code.startswith("MAT_"))
    assert material.payload["unit"] is None
    assert any("см" in warning for warning in report.warnings)


def test_unknown_unit_is_reported_not_swallowed(tmp_path) -> None:
    _team(tmp_path, catalog_unit="компл")
    _, report = build_import_sections(tmp_path, "north", default_reference_snapshot())
    assert any("компл" in warning and "не распознаны" in warning for warning in report.warnings)


def test_import_keeps_hand_entered_equipment_types(tmp_path) -> None:
    """Импорт сценария не должен стирать типы техники с нормами и ТОиР."""

    _team(tmp_path, catalog_unit="шт")
    snapshot = default_reference_snapshot()
    manual = ReferenceItem(
        code="TYPE_SZM",
        name="СЗМ 12 т",
        payload={"kind": "SZM", "norm_shifts_per_month": 20, "maintenance_rub_per_shift": 750},
    )
    snapshot.sections["equipment_types"] = (manual,)

    sections, _ = build_import_sections(tmp_path, "north", snapshot)
    codes = {item.code for item in sections["equipment_types"]}
    assert "TYPE_SZM" in codes and "TYPE_DML" in codes
    kept = next(item for item in sections["equipment_types"] if item.code == "TYPE_SZM")
    assert kept.payload["maintenance_rub_per_shift"] == 750


def test_existing_type_wins_over_the_imported_one(tmp_path) -> None:
    _team(tmp_path, catalog_unit="шт")
    snapshot = default_reference_snapshot()
    snapshot.sections["equipment_types"] = (
        ReferenceItem(code="TYPE_DML", name="DML", payload={"kind": "DRILL_RIG", "norm_shifts_per_month": 40}),
    )
    sections, _ = build_import_sections(tmp_path, "north", snapshot)
    types = [item for item in sections["equipment_types"] if item.code == "TYPE_DML"]
    assert len(types) == 1
    assert types[0].payload["norm_shifts_per_month"] == 40


def test_imported_sections_pass_validation(tmp_path) -> None:
    _team(tmp_path, catalog_unit="шт")
    sections, _ = build_import_sections(tmp_path, "north", default_reference_snapshot())
    assert not has_validation_errors(validate_reference_sections(sections))
