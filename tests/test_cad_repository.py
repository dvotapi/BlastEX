"""Хранилище импорта чертежа: источники, сущности и шаблон слоёв объекта.

Один и тот же контракт проверяется на InMemory и на PostgreSQL. Postgres
включается переменной ``BLASTEX_TEST_DATABASE_URL`` (фикстура ``public_db``
применяет миграции Alembic), без неё эти параметры пропускаются.
"""
from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from design.spatial.cad.model import CadEntity
from design.spatial.cad.roles import TemplateEntry
from design.spatial.cad.repository import (
    CadSourceConflict,
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
        repository.update_roles(ORG_B, "src-1", {"769": ("ignore", "manual")}, {}, expected_revision=1)
    with pytest.raises(CadSourceNotFound):
        repository.replace_entities(ORG_B, "src-1", [], {}, {}, expected_revision=1)
    assert repository.list_entities(ORG_A, "src-1")[0].role == "block_contour"


def test_entities_are_filtered_by_role_and_handle(repository) -> None:
    repository.create_sources(ORG_A, [(_record(), _entities())])

    by_role = repository.list_entities(ORG_A, "src-1", roles={"spot_heights"})
    assert [item.handle for item in by_role] == ["51C", "61A"]
    by_handle = repository.list_entities(ORG_A, "src-1", handles={"769", "nope"})
    assert [item.handle for item in by_handle] == ["769"]
    both = repository.list_entities(ORG_A, "src-1", roles={"spot_heights"}, handles={"769", "61A"})
    assert [item.handle for item in both] == ["61A"]
    assert repository.list_entities(ORG_A, "src-1", roles=set()) == []
    assert repository.list_entities(ORG_B, "src-1", roles={"block_contour"}) == []


def test_area_basis_is_kept_on_the_site(repository) -> None:
    # Какую площадь маркшейдер объекта называет площадью блока (TASK-013, PR 2).
    assert repository.get_area_basis(ORG_A, "SITE_ZK") is None

    repository.set_area_basis(ORG_A, "SITE_ZK", "top", USER)
    repository.set_area_basis(ORG_A, "SITE_ZK", "bottom", USER)

    assert repository.get_area_basis(ORG_A, "SITE_ZK") == "bottom"
    assert repository.get_area_basis(ORG_A, "SITE_OTHER") is None
    assert repository.get_area_basis(ORG_B, "SITE_ZK") is None


def test_update_roles_changes_only_named_entities(repository) -> None:
    repository.create_sources(ORG_A, [(_record(), _entities())])

    repository.update_roles(ORG_A, "src-1", {"51C": ("ignore", "manual")}, {"layers": {"x": 1}}, expected_revision=1)

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

    repository.replace_entities(ORG_A, "src-1", scaled, {"scale": 0.001}, {"warnings": []}, expected_revision=1)

    source = repository.get_source(ORG_A, "src-1")
    assert source.params == {"scale": 0.001}
    assert [item.points for item in repository.list_entities(ORG_A, "src-1")] == [scaled[0].points]


def test_writes_with_a_stale_revision_are_refused(repository) -> None:
    """Две правки одного источника: вторая, прочитанная до первой, не затирает её."""

    repository.create_sources(ORG_A, [(_record(), _entities())])
    assert repository.get_source(ORG_A, "src-1").revision == 1

    repository.update_roles(ORG_A, "src-1", {"51C": ("ignore", "manual")}, {"first": True}, expected_revision=1)
    assert repository.get_source(ORG_A, "src-1").revision == 2

    with pytest.raises(CadSourceConflict):
        repository.update_roles(ORG_A, "src-1", {"769": ("ignore", "manual")}, {"second": True}, expected_revision=1)
    with pytest.raises(CadSourceConflict):
        repository.replace_entities(ORG_A, "src-1", [], {"scale": 2}, {"third": True}, expected_revision=1)

    source = repository.get_source(ORG_A, "src-1")
    assert (source.revision, source.summary, source.params) == (2, {"first": True}, {"scale": 1.0, "label_radius_m": 3.0})
    roles = {item.handle: item.role for item in repository.list_entities(ORG_A, "src-1")}
    assert roles["769"] == "block_contour"


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

        repository.update_roles(ORG_A, "src-1", {item.handle: ("ignore", "manual") for item in many}, {}, expected_revision=1)

        assert sum(1 for sql in statements if sql.lstrip().upper().startswith("UPDATE BLASTEX.CAD_ENTITIES")) == 1
        assert {item.role for item in repository.list_entities(ORG_A, "src-1")} == {"ignore"}
    finally:
        repository.engine.dispose()


def _site_record(
    source_id: str,
    *,
    site_code: str = "SITE_ZK",
    sha: str = "1" * 64,
    title: str = "Положение горных работ",
    day: int = 1,
    survey: date | None = date(2026, 9, 1),
) -> CadSourceRecord:
    return replace(
        _record(source_id, site_code),
        file_sha256=sha,
        title=title,
        survey_date=survey,
        uploaded_at=datetime(2026, 9, day, 10, 0, tzinfo=timezone.utc),
    )


def test_source_title_round_trip(repository) -> None:
    # Название источника (TASK-013, PR 4): серия ситуации держится на нём.
    repository.create_sources(ORG_A, [(_site_record("src-1"), [])])

    assert repository.get_source(ORG_A, "src-1").title == "Положение горных работ"


def test_find_source_by_sha_is_per_site_and_organization(repository) -> None:
    repository.create_sources(ORG_A, [(_site_record("src-1", sha="a" * 64), [])])

    assert repository.find_source_by_sha(ORG_A, "SITE_ZK", "a" * 64).id == "src-1"
    assert repository.find_source_by_sha(ORG_A, "SITE_OTHER", "a" * 64) is None
    assert repository.find_source_by_sha(ORG_B, "SITE_ZK", "a" * 64) is None
    assert repository.find_source_by_sha(ORG_A, "SITE_ZK", "b" * 64) is None


def test_site_sources_are_listed_newest_upload_first_without_file(repository) -> None:
    repository.create_sources(
        ORG_A,
        [
            (_site_record("old", sha="a" * 64, day=1), []),
            (_site_record("new", sha="b" * 64, day=5), []),
            (_site_record("other-site", site_code="SITE_OTHER", sha="c" * 64, day=9), []),
        ],
    )
    repository.create_sources(ORG_B, [(_site_record("foreign", sha="d" * 64, day=7), [])])

    listed = repository.list_site_sources(ORG_A, "SITE_ZK", limit=10)
    assert [item.id for item in listed] == ["new", "old"]
    assert all(item.file_data is None for item in listed)
    assert [item.id for item in repository.list_site_sources(ORG_A, "SITE_ZK", limit=1)] == ["new"]


def test_source_meta_update_checks_revision(repository) -> None:
    repository.create_sources(ORG_A, [(_site_record("src-1"), [])])

    repository.update_source_meta(
        ORG_A, "src-1", title="Положение работ", survey_date=date(2026, 10, 1), expected_revision=1
    )
    source = repository.get_source(ORG_A, "src-1")
    assert (source.title, source.survey_date, source.revision) == ("Положение работ", date(2026, 10, 1), 2)

    with pytest.raises(CadSourceConflict):
        repository.update_source_meta(ORG_A, "src-1", title="x", survey_date=None, expected_revision=1)
    with pytest.raises(CadSourceNotFound):
        repository.update_source_meta(ORG_B, "src-1", title="x", survey_date=None, expected_revision=2)


def test_deleted_source_is_gone_with_its_entities(repository) -> None:
    repository.create_sources(ORG_A, [(_site_record("src-1"), _entities())])

    with pytest.raises(CadSourceNotFound):
        repository.delete_source(ORG_B, "src-1")
    assert repository.get_source(ORG_A, "src-1") is not None

    repository.delete_source(ORG_A, "src-1")
    assert repository.get_source(ORG_A, "src-1") is None
    assert repository.list_entities(ORG_A, "src-1") == []
    with pytest.raises(CadSourceNotFound):
        repository.delete_source(ORG_A, "src-1")


def test_site_crs_does_not_touch_area_basis(repository) -> None:
    assert repository.get_site_crs(ORG_A, "SITE_ZK") is None

    repository.set_area_basis(ORG_A, "SITE_ZK", "top", USER)
    crs = {"name": "МСК-66 зона 1", "height_system": "Балтийская 1977", "epsg": None}
    repository.set_site_crs(ORG_A, "SITE_ZK", crs, USER)

    assert repository.get_site_crs(ORG_A, "SITE_ZK") == crs
    assert repository.get_area_basis(ORG_A, "SITE_ZK") == "top"
    assert repository.get_site_crs(ORG_B, "SITE_ZK") is None

    repository.set_area_basis(ORG_A, "SITE_ZK", "bottom", USER)
    assert repository.get_site_crs(ORG_A, "SITE_ZK") == crs

    repository.set_site_crs(ORG_A, "SITE_NEW", {"name": "МСК-66 зона 2", "height_system": "", "epsg": 0}, USER)
    assert repository.get_area_basis(ORG_A, "SITE_NEW") in (None, "mean")


def test_entities_are_counted_by_role_per_source(repository) -> None:
    repository.create_sources(
        ORG_A, [(_site_record("src-1", sha="a" * 64), _entities()), (_site_record("src-2", sha="b" * 64), [])]
    )

    counts = repository.count_entities_by_role(ORG_A, {"src-1", "src-2"}, "spot_heights")
    assert counts == {"src-1": 2}
    assert repository.count_entities_by_role(ORG_B, {"src-1"}, "spot_heights") == {}


def test_layer_kinds_live_in_the_template(repository) -> None:
    repository.add_missing_layer_roles(ORG_A, "SITE_ZK", {"Дороги": "situation"}, USER)

    repository.upsert_layer_kinds(ORG_A, "SITE_ZK", {"Дороги": "road", "Новый слой": "building"}, USER)
    template = repository.get_layer_template(ORG_A, "SITE_ZK")
    assert template["дороги"] == TemplateEntry("situation", False, "road")
    assert template["новый слой"].kind == "building"

    repository.upsert_layer_kinds(ORG_A, "SITE_ZK", {"Дороги": None}, USER)
    assert repository.get_layer_template(ORG_A, "SITE_ZK")["дороги"] == TemplateEntry("situation", False, None)
    assert repository.get_layer_template(ORG_B, "SITE_ZK") == {}


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
