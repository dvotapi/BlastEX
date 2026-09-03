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


def test_every_repository_method_takes_organization_first() -> None:
    """Новый метод обязан принять организацию — иначе фильтр забудут."""

    for name, method in inspect.getmembers(PostgresEconomicsRepository, inspect.isfunction):
        if name.startswith("_") or name in NON_SCOPED_METHODS:
            continue
        parameters = list(inspect.signature(method).parameters)
        assert parameters[:2] == ["self", "organization_id"], (
            f"{name}: первым аргументом должен быть organization_id"
        )
