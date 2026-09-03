from copy import deepcopy

import pytest

from cost.v2.models import EconomicScenario, ReferenceItem
from cost.v2.references import validate_reference_sections
from cost.v2.repository import InMemoryEconomicsRepository, ReferenceRevisionConflict


def test_reference_publish_is_revisioned_and_conflict_safe() -> None:
    repository = InMemoryEconomicsRepository()
    first = repository.get_reference_snapshot("org")
    sections = deepcopy(first.sections)
    sections["production_units"] = (ReferenceItem("UNIT_1", "Юнит 1"),)
    second = repository.publish_references("org", "editor", first.revision_id, sections, "test")
    assert second.revision_id != first.revision_id
    assert repository.get_reference_snapshot("org", first.revision_id).sections["production_units"] == ()
    with pytest.raises(ReferenceRevisionConflict):
        repository.publish_references("org", "editor", first.revision_id, sections)


def test_default_reference_snapshot_has_no_validation_errors() -> None:
    repository = InMemoryEconomicsRepository()
    snapshot = repository.get_reference_snapshot("org")
    issues = validate_reference_sections(snapshot.sections)
    assert not [issue for issue in issues if issue.level == "error"]


def test_scenario_and_calculation_run_are_organization_scoped() -> None:
    repository = InMemoryEconomicsRepository()
    scenario = EconomicScenario.from_dict(
        {"id": "S1", "name": "Сценарий", "production_unit_code": "UNIT"}
    )
    stored = repository.save_scenario("org-a", "user", scenario)
    assert stored.scenario.id == "S1"
    with pytest.raises(Exception):
        repository.get_scenario("org-b", "S1")
    run = repository.save_calculation_run(
        "org-a", "user", scenario, "R1", "v1", {"ok": True}
    )
    assert repository.get_calculation_run("org-a", run.id).result == {"ok": True}


def test_in_memory_legacy_scenario_has_the_same_shape_as_postgresql() -> None:
    """Форма записи сценария не должна зависеть от того, где он хранится."""

    repository = InMemoryEconomicsRepository()
    repository.import_legacy_scenarios(
        "org", "user", {"drill_blast": {"scenario_id": "drill_blast", "labor_shifts_per_month": 7}}
    )
    stored = repository.get_legacy_scenario("org", "drill_blast")
    assert stored is not None
    assert stored["labor_assignment_records"] == []
    assert stored["drilling_calculator_input"] == {}
    assert stored["scenario_phase_overrides"] == {}
    assert stored["labor_shifts_per_month"] == 7
    assert stored["reference_revision_id"] is None
