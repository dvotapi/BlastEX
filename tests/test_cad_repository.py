"""Хранилище импорта чертежа: источники, сущности и шаблон слоёв объекта.

Один и тот же контракт проверяется на InMemory и на PostgreSQL. Postgres
включается переменной ``BLASTEX_TEST_DATABASE_URL`` (фикстура ``public_db``
применяет миграции Alembic), без неё эти параметры пропускаются.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from design.spatial.cad.model import CadEntity
from design.spatial.cad.roles import TemplateEntry
from design.spatial.cad.repository import (
    CadSourceNotFound,
    CadSourceRecord,
    InMemoryCadRepository,
    PostgresCadRepository,
)
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура

ORG_A = "org-a"
ORG_B = "org-b"
USER = "surveyor@example.ru"


@pytest.fixture(params=["memory", pytest.param("postgres", marks=requires_pg)])
def repository(request):
    if request.param == "memory":
        yield InMemoryCadRepository()
        return
    request.getfixturevalue("public_db")
    created = PostgresCadRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


def _record(source_id: str = "src-1", site_code: str = "SITE_ZK") -> CadSourceRecord:
    return CadSourceRecord(
        id=source_id,
        site_code=site_code,
        work_object_name="Жуков камень",
        file_name="блок 66.dwg",
        file_format="dwg",
        file_size=5,
        file_sha256="0" * 64,
        params={"scale": 1.0, "label_radius_m": 3.0},
        summary={"warnings": [], "layers": {}},
        uploaded_by=USER,
        uploaded_at=datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc),
        survey_date=date(2026, 9, 28),
        file_data=b"bytes",
    )


def _entities() -> list[CadEntity]:
    return [
        CadEntity(
            handle="769",
            layer="блок 66 вар 2",
            kind="LWPOLYLINE",
            points=[(0.0, 0.0, 419.8), (40.0, 0.0, 419.8), (40.0, 30.0, 419.8)],
            closed=True,
            closed_by_gap=True,
            color="#ff0000",
            role="block_contour",
            role_origin="auto",
        ),
        CadEntity(
            handle="51C",
            layer="Отметка",
            kind="POINT",
            points=[(2.5, 3.5, 410.839)],
            role="spot_heights",
            role_origin="auto",
        ),
        CadEntity(
            handle="61A",
            layer="Отметка",
            kind="TEXT",
            points=[(2.7, 3.6, 0.0)],
            text="410.84",
            text_height=0.4,
            role="spot_heights",
            role_origin="auto",
        ),
    ]


def test_source_round_trip_keeps_entities_in_order(repository) -> None:
    repository.create_sources(ORG_A, [(_record(), _entities())])

    source = repository.get_source(ORG_A, "src-1")
    assert source is not None
    assert (source.file_name, source.site_code, source.survey_date) == ("блок 66.dwg", "SITE_ZK", date(2026, 9, 28))
    assert source.file_data is None  # исходник только по запросу
    assert repository.get_source(ORG_A, "src-1", with_file=True).file_data == b"bytes"

    stored = repository.list_entities(ORG_A, "src-1")
    assert [item.handle for item in stored] == ["769", "51C", "61A"]
    contour, point, label = stored
    assert contour.points == [(0.0, 0.0, 419.8), (40.0, 0.0, 419.8), (40.0, 30.0, 419.8)]
    assert (contour.closed, contour.closed_by_gap, contour.color) == (True, True, "#ff0000")
    assert (point.role, point.role_origin) == ("spot_heights", "auto")
    assert (label.text, label.text_height) == ("410.84", 0.4)


def test_other_organization_sees_nothing(repository) -> None:
    repository.create_sources(ORG_A, [(_record(), _entities())])

    assert repository.get_source(ORG_B, "src-1") is None
    assert repository.list_entities(ORG_B, "src-1") == []
    with pytest.raises(CadSourceNotFound):
        repository.update_roles(ORG_B, "src-1", {"769": ("ignore", "manual")}, {})
    with pytest.raises(CadSourceNotFound):
        repository.replace_entities(ORG_B, "src-1", [], {}, {})
    assert repository.list_entities(ORG_A, "src-1")[0].role == "block_contour"


def test_update_roles_changes_only_named_entities(repository) -> None:
    repository.create_sources(ORG_A, [(_record(), _entities())])

    repository.update_roles(ORG_A, "src-1", {"51C": ("ignore", "manual")}, {"layers": {"x": 1}})

    roles = {item.handle: (item.role, item.role_origin) for item in repository.list_entities(ORG_A, "src-1")}
    assert roles == {
        "769": ("block_contour", "auto"),
        "51C": ("ignore", "manual"),
        "61A": ("spot_heights", "auto"),
    }
    assert repository.get_source(ORG_A, "src-1").summary == {"layers": {"x": 1}}


def test_replace_entities_swaps_geometry_params_and_summary(repository) -> None:
    repository.create_sources(ORG_A, [(_record(), _entities())])
    scaled = _entities()[:1]
    scaled[0].points = [(0.0, 0.0, 0.4), (0.04, 0.0, 0.4), (0.04, 0.03, 0.4)]

    repository.replace_entities(ORG_A, "src-1", scaled, {"scale": 0.001}, {"warnings": []})

    source = repository.get_source(ORG_A, "src-1")
    assert source.params == {"scale": 0.001}
    assert [item.points for item in repository.list_entities(ORG_A, "src-1")] == [scaled[0].points]


def test_layer_template_adds_missing_and_upserts(repository) -> None:
    repository.add_missing_layer_roles(ORG_A, "SITE_ZK", {"Горизонт +410": "crests_by_z", "Отвал": "situation"}, USER)
    repository.add_missing_layer_roles(ORG_A, "SITE_ZK", {" горизонт  +410": "ignore", "Отметка": "spot_heights"}, USER)

    assert repository.get_layer_template(ORG_A, "SITE_ZK") == {
        "горизонт +410": TemplateEntry("crests_by_z"),
        "отвал": TemplateEntry("situation"),
        "отметка": TemplateEntry("spot_heights"),
    }

    repository.upsert_layer_roles(ORG_A, "SITE_ZK", {"ОТВАЛ": "ignore"}, USER)

    # Ручная правка помечает роль подтверждённой.
    assert repository.get_layer_template(ORG_A, "SITE_ZK")["отвал"] == TemplateEntry("ignore", manual=True)
    assert repository.get_layer_template(ORG_A, "OTHER_SITE") == {}
    assert repository.get_layer_template(ORG_B, "SITE_ZK") == {}


def test_template_of_another_organization_is_untouched(repository) -> None:
    repository.upsert_layer_roles(ORG_A, "SITE_ZK", {"Отвал": "situation"}, USER)
    repository.upsert_layer_roles(ORG_B, "SITE_ZK", {"Отвал": "ignore"}, USER)

    assert repository.get_layer_template(ORG_A, "SITE_ZK") == {"отвал": TemplateEntry("situation", manual=True)}


@requires_pg
def test_several_sources_are_saved_together_or_not_at_all(public_db) -> None:
    repository = PostgresCadRepository(TEST_DATABASE_URL)
    broken = _entities()
    broken[1].handle = broken[0].handle  # нарушает первичный ключ (source_id, handle)
    try:
        with pytest.raises(Exception):
            repository.create_sources(ORG_A, [(_record("src-1"), _entities()), (_record("src-2"), broken)])
        assert repository.get_source(ORG_A, "src-1") is None
    finally:
        repository.engine.dispose()


@requires_pg
def test_role_update_is_one_statement_not_one_per_entity(public_db) -> None:
    from sqlalchemy import event

    repository = PostgresCadRepository(TEST_DATABASE_URL)
    many = [
        CadEntity(handle=f"P{index}", layer="Отметка", kind="POINT", points=[(index, 0.0, 410.0)], role="spot_heights", role_origin="auto")
        for index in range(60)
    ]
    try:
        repository.create_sources(ORG_A, [(_record(), many)])
        statements: list[str] = []
        event.listen(repository.engine, "before_cursor_execute", lambda *args: statements.append(args[2]))

        repository.update_roles(ORG_A, "src-1", {item.handle: ("ignore", "manual") for item in many}, {})

        assert sum(1 for sql in statements if sql.lstrip().upper().startswith("UPDATE BLASTEX.CAD_ENTITIES")) == 1
        assert {item.role for item in repository.list_entities(ORG_A, "src-1")} == {"ignore"}
    finally:
        repository.engine.dispose()


@requires_pg
def test_deleting_a_source_cascades_to_entities(public_db) -> None:
    repository = PostgresCadRepository(TEST_DATABASE_URL)
    try:
        repository.create_sources(ORG_A, [(_record(), _entities())])
        with repository.engine.begin() as connection:
            connection.execute(text("DELETE FROM blastex.cad_sources WHERE id = 'src-1'"))
            left = connection.execute(text("SELECT count(*) FROM blastex.cad_entities")).scalar_one()
        assert left == 0
    finally:
        repository.engine.dispose()


@pytest.mark.parametrize("implementation", [PostgresCadRepository, InMemoryCadRepository])
def test_every_repository_method_takes_organization_first(implementation) -> None:
    """Новый метод обязан принять организацию — иначе фильтр забудут."""

    for name, method in inspect.getmembers(implementation, inspect.isfunction):
        if name.startswith("_"):
            continue
        parameters = list(inspect.signature(method).parameters)
        assert parameters[:2] == ["self", "organization_id"], f"{name}: первым аргументом должен быть organization_id"
