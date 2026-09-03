"""Справочники Cost V1 по умолчанию, пропущенные через импорт в V2 и адаптер,
дают те же структуры и ту же смету, что и до переезда (спецификация §6)."""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from api.schemas.cost import (
    CostCalculateRequest,
    InitiationConfigSchema,
    ManualScenarioInputSchema,
    MaterialsAutoRequest,
)
from api.services.cost_service import calculate_cost, resolve_materials_auto
from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS, depreciation_assets_to_records
from cost.drilling_data import DEFAULT_DRILL_RIGS, DEFAULT_WORK_OBJECTS, drill_rigs_to_records, work_objects_to_records
from cost.explosive_data import DEFAULT_EXPLOSIVES, explosives_to_records
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import DEFAULT_LABOR_CATALOG, labor_catalog_to_records
from cost.rock_data import DEFAULT_ROCKS, rocks_to_records
from cost.v2.import_v1 import build_import_sections
from cost.v2.legacy_adapter import default_legacy_references, legacy_references_from_snapshot
from cost.v2.models import ReferenceSnapshot
from cost.v2.references import default_reference_snapshot, has_validation_errors, validate_reference_sections


@pytest.fixture()
def imported_snapshot(tmp_path) -> ReferenceSnapshot:
    team_dir = tmp_path / "data" / "teams" / "default"
    (team_dir / "scenarios").mkdir(parents=True)
    (team_dir / "references.json").write_text(
        json.dumps(
            {
                "work_object_records": work_objects_to_records(DEFAULT_WORK_OBJECTS),
                "drill_rig_records": drill_rigs_to_records(DEFAULT_DRILL_RIGS),
                "rock_records": rocks_to_records(DEFAULT_ROCKS),
                "explosive_records": explosives_to_records(DEFAULT_EXPLOSIVES),
                "depreciation_asset_records": depreciation_assets_to_records(DEFAULT_DEPRECIATION_ASSETS),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (team_dir / "settings.json").write_text(json.dumps({"active_scenario_id": "drill_blast"}), encoding="utf-8")
    (team_dir / "scenarios" / "drill_blast.json").write_text(
        json.dumps(
            {
                "cost_catalog_records": catalog_to_records(DEFAULT_CATALOG),
                "fixed_cost_records": fixed_costs_to_records(DEFAULT_FIXED_COSTS),
                "labor_catalog_records": labor_catalog_to_records(DEFAULT_LABOR_CATALOG),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sections, _ = build_import_sections(tmp_path, "default", default_reference_snapshot())
    assert not has_validation_errors(validate_reference_sections(sections))
    return ReferenceSnapshot(revision_id="IMPORTED", sections=sections)


def _plain(items):
    return [asdict(item) for item in items]


def test_structures_survive_import_and_adapter(imported_snapshot) -> None:
    legacy = legacy_references_from_snapshot(imported_snapshot)
    expected = default_legacy_references()

    assert not legacy.warnings, legacy.warnings
    assert _plain(legacy.work_objects) == _plain(expected.work_objects)
    assert _plain(legacy.drill_rigs) == _plain(expected.drill_rigs)
    assert _plain(legacy.rocks) == _plain(expected.rocks)
    assert _plain(legacy.explosives) == _plain(expected.explosives)
    assert _plain(legacy.catalog) == _plain(expected.catalog)
    assert _plain(legacy.fixed_costs) == _plain(expected.fixed_costs)
    assert _plain(legacy.labor_catalog) == _plain(expected.labor_catalog)
    for actual, wanted in zip(legacy.depreciation_assets, expected.depreciation_assets, strict=True):
        assert actual.name == wanted.name
        assert actual.depreciation_per_shift_rub == pytest.approx(wanted.depreciation_per_shift_rub)


def test_estimate_matches_to_the_kopeck(imported_snapshot) -> None:
    # Номенклатура материалов подбирается тем же сервисом, что и в реальном
    # запросе — иначе `run_materials_module` не запускается (нет
    # `materials_selection` ни в запросе, ни в `block_data`), и сценарий
    # «БВР» сверяет только бурение, ФОТ и постоянные затраты, минуя ветку
    # каталога `legacy.catalog`.
    selection = resolve_materials_auto(
        MaterialsAutoRequest(
            explosive_key=DEFAULT_EXPLOSIVES[0].key,
            initiation=InitiationConfigSchema(),
        ),
        default_legacy_references(),
    ).selection

    manual_input = ManualScenarioInputSchema(
        block_volume_m3=30_000,
        total_holes=150,
        drilling_footage_m=1_800,
        total_charge_mass_kg=24_000,
        production_volume_tons=0,
        explosive_key=DEFAULT_EXPLOSIVES[0].key,
    )
    request_without_selection = CostCalculateRequest(
        scenario_id="drill_blast",
        work_object_name=DEFAULT_WORK_OBJECTS[0].name,
        manual_input=manual_input,
    )
    request = request_without_selection.model_copy(update={"materials_selection": selection})

    without = calculate_cost(request_without_selection, default_legacy_references()).model_dump()
    before = calculate_cost(request, default_legacy_references()).model_dump()
    after = calculate_cost(request, legacy_references_from_snapshot(imported_snapshot)).model_dump()

    # Материалы действительно учтены: с подбором номенклатуры переменные
    # затраты (материалы + бурение) больше, чем без него.
    assert after["variable_total_rub"] > without["variable_total_rub"]
    assert after == before
