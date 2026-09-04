"""Данные одной организации не видны другой.

Хранилище одно на всех: изоляция держится не на разных файлах, а на
`organization_id` в каждом запросе. Тест закрывает контракт репозитория —
и заодно проверяет, что новый метод не забыл принять организацию.
"""
from __future__ import annotations

import inspect

import pytest

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.models import EconomicScenario
from cost.v2.repository import (
    EconomicsRecordNotFound,
    InMemoryEconomicsRepository,
)


ORG_A = "org-a"
ORG_B = "org-b"

# Методы без организации: служебные и те, что работают с уже выбранной сессией.
NON_SCOPED_METHODS = {"session_factory"}


@pytest.fixture()
def repository() -> InMemoryEconomicsRepository:
    return InMemoryEconomicsRepository()


def _scenario(name: str) -> EconomicScenario:
    return EconomicScenario.from_dict(
        {"id": "", "name": name, "production_unit_code": "UNIT_1", "baseline_service_lines": []}
    )


def _passport(repository: InMemoryEconomicsRepository, organization_id: str):
    revision = repository.get_reference_snapshot(organization_id).revision_id
    return repository.save_technical_passport(
        organization_id,
        "tester",
        site_code="SITE",
        object_name="Блок",
        previous_passport_id=None,
        reference_revision_id=revision,
        formula_version="blast-geometry-v1",
        input_snapshot={},
        selected_variant={},
        block_snapshot={},
        physical={"rock_volume_m3": "1000"},
        lineage={},
    )


def test_reference_revisions_are_separate(repository) -> None:
    a = repository.get_reference_snapshot(ORG_A)
    b = repository.get_reference_snapshot(ORG_B)
    assert a.revision_id != b.revision_id

    repository.publish_references(ORG_A, "a@example.ru", a.revision_id, {}, "правка A")
    assert repository.get_reference_snapshot(ORG_B).revision_id == b.revision_id
    with pytest.raises(EconomicsRecordNotFound):
        repository.get_reference_snapshot(ORG_B, a.revision_id)


def test_scenarios_are_not_visible_across_organizations(repository) -> None:
    stored = repository.save_scenario(ORG_A, "a@example.ru", _scenario("Сценарий A"))

    assert [row.scenario.id for row in repository.list_scenarios(ORG_A)] == [stored.scenario.id]
    assert repository.list_scenarios(ORG_B) == ()
    with pytest.raises(EconomicsRecordNotFound):
        repository.get_scenario(ORG_B, stored.scenario.id)
    with pytest.raises(EconomicsRecordNotFound):
        repository.clone_scenario(ORG_B, "b@example.ru", stored.scenario.id)


def test_technical_passports_are_not_visible_across_organizations(repository) -> None:
    passport = _passport(repository, ORG_A)

    assert [row.id for row in repository.list_technical_passports(ORG_A)] == [passport.id]
    assert repository.list_technical_passports(ORG_B) == ()
    with pytest.raises(EconomicsRecordNotFound):
        repository.get_technical_passport(ORG_B, passport.id)


def test_calculation_runs_are_not_visible_across_organizations(repository) -> None:
    scenario = repository.save_scenario(ORG_A, "a@example.ru", _scenario("Сценарий A")).scenario
    run = repository.save_calculation_run(
        ORG_A, "a@example.ru", scenario, "REV", "cost-v2.1", {"totals": {}}
    )

    assert repository.get_calculation_run(ORG_A, run.id).id == run.id
    with pytest.raises(EconomicsRecordNotFound):
        repository.get_calculation_run(ORG_B, run.id)


def test_event_runs_require_own_passport(repository) -> None:
    passport = _passport(repository, ORG_A)

    with pytest.raises(EconomicsRecordNotFound):
        repository.save_event_calculation_run(
            ORG_B,
            "b@example.ru",
            reference_revision_id="REV",
            formula_version="cost-v2.1",
            technical_formula_version="blast-geometry-v1",
            technical_passport_id=passport.id,
            site_code="SITE",
            period="2026-09",
            input_snapshot={},
            result={},
        )


def test_legacy_workspace_and_scenarios_are_organization_scoped(repository) -> None:
    repository.import_legacy_workspace(
        ORG_A,
        "a@example.ru",
        team_name="Команда А",
        active_scenario_id="drilling",
        active_work_object_name="Карьер А",
    )
    repository.import_legacy_scenarios(
        ORG_A,
        "a@example.ru",
        {"drilling": {"labor_shifts_per_month": 7, "labor_assignment_records": [{"id": "la_1"}]}},
    )

    settings = repository.get_legacy_workspace(ORG_A)
    assert settings is not None
    assert settings.team_name == "Команда А"
    assert settings.active_scenario_id == "drilling"
    assert settings.active_work_object_name == "Карьер А"
    assert repository.get_legacy_workspace(ORG_B) is None

    scenario = repository.get_legacy_scenario(ORG_A, "drilling")
    assert scenario is not None
    assert scenario["labor_shifts_per_month"] == 7
    assert scenario["labor_assignment_records"] == [{"id": "la_1"}]
    assert repository.get_legacy_scenario(ORG_A, "blasting") is None
    assert repository.get_legacy_scenario(ORG_B, "drilling") is None


def test_legacy_workspace_is_overwritten_not_duplicated(repository) -> None:
    for name in ("Первое", "Второе"):
        repository.import_legacy_workspace(
            ORG_A, "a@example.ru", team_name=name, active_scenario_id="drill_blast", active_work_object_name="X"
        )
    assert repository.get_legacy_workspace(ORG_A).team_name == "Второе"
    repository.import_legacy_scenarios(ORG_A, "a", {"drill_blast": {"labor_shifts_per_month": 1}})
    repository.import_legacy_scenarios(ORG_A, "a", {"drill_blast": {"labor_shifts_per_month": 2}})
    assert repository.get_legacy_scenario(ORG_A, "drill_blast")["labor_shifts_per_month"] == 2


def test_public_links_are_organization_scoped_and_unique(repository) -> None:
    from cost.v2.repository import EconomicsRepositoryError, PublicLink

    link = PublicLink(section="sites", code="SITE_LOM", public_table="sites", public_id=1)
    saved = repository.save_public_link(ORG_A, "a@example.ru", link)
    assert saved.synced_at is not None
    assert [l.code for l in repository.list_public_links(ORG_A)] == ["SITE_LOM"]
    assert repository.list_public_links(ORG_B) == ()

    repository.save_public_link(ORG_A, "a@example.ru", PublicLink("sites", "SITE_LOM", "sites", 2))
    assert [l.public_id for l in repository.list_public_links(ORG_A)] == [2]
    with pytest.raises(EconomicsRepositoryError):
        repository.save_public_link(ORG_A, "a@example.ru", PublicLink("sites", "SITE_OTHER", "sites", 2))


def test_mirror_sections_are_organization_scoped(repository) -> None:
    repository.set_mirror_section(ORG_A, "a@example.ru", "rocks", True)
    assert repository.list_mirror_sections(ORG_A) == {"rocks": True}
    assert repository.list_mirror_sections(ORG_B) == {}
    repository.set_mirror_section(ORG_A, "a@example.ru", "rocks", False)
    assert repository.list_mirror_sections(ORG_A) == {"rocks": False}


def test_every_repository_method_takes_organization_first() -> None:
    """Новый метод обязан принять организацию — иначе фильтр забудут."""

    for name, method in inspect.getmembers(PostgresEconomicsRepository, inspect.isfunction):
        if name.startswith("_") or name in NON_SCOPED_METHODS:
            continue
        parameters = list(inspect.signature(method).parameters)
        assert parameters[:2] == ["self", "organization_id"], (
            f"{name}: первым аргументом должен быть organization_id"
        )
