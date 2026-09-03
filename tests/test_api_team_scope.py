"""Справочники V1 читаются из опубликованной ревизии организации из сессии;
запись возможна только публикацией ревизии, PUT-маршрутов больше нет."""
import unittest

from fastapi import HTTPException

from api.routers import references as references_router
from api.security import require_reference_editor
from api.services.legacy_references import load_legacy_references
from cost.drilling_data import DEFAULT_WORK_OBJECTS
from cost.rock_data import DEFAULT_ROCKS
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


def _publish(repository: InMemoryEconomicsRepository, organization_id: str, section: str, items: list[ReferenceItem]) -> None:
    current = repository.get_reference_snapshot(organization_id)
    sections = dict(current.sections)
    sections[section] = tuple(items)
    repository.publish_references(organization_id, "tester", current.revision_id, sections, "test")


class TeamScopedReferencesTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryEconomicsRepository()

    def test_published_sites_are_isolated_per_organization(self):
        _publish(
            self.repository,
            "team_b",
            "sites",
            [ReferenceItem("SITE_TEST", "Тестовый карьер", {"mobilization_km": "42", "diesel_price_ton_rub": "90000"})],
        )

        team_a = references_router.list_work_objects(legacy=load_legacy_references(self.repository, "team_a"))
        self.assertEqual([o.name for o in team_a.items], [o.name for o in DEFAULT_WORK_OBJECTS])

        team_b = references_router.list_work_objects(legacy=load_legacy_references(self.repository, "team_b"))
        self.assertEqual([o.name for o in team_b.items], ["Тестовый карьер"])
        self.assertEqual(team_b.default_name, "Тестовый карьер")
        self.assertEqual(team_b.items[0].mobilization_km, 42.0)

    def test_rocks_come_from_published_revision(self):
        _publish(
            self.repository,
            "team_c",
            "rocks",
            [ReferenceItem("ROCK_TEST", DEFAULT_ROCKS[0].name, {"density_t_m3": "9.99", "ucs_mpa": "100", "fissuring_ff": "1"})],
        )
        result = references_router.list_rocks(legacy=load_legacy_references(self.repository, "team_c"))
        self.assertEqual(result.items[0].density_t_m3, 9.99)
        self.assertEqual(result.default_name, DEFAULT_ROCKS[0].name)

    def test_put_routes_are_gone(self):
        methods = {method for route in references_router.router.routes for method in getattr(route, "methods", set())}
        self.assertEqual(methods, {"GET"})


class ReferenceEditorGateTests(unittest.TestCase):
    def test_user_role_forbidden(self):
        with self.assertRaises(HTTPException) as error:
            require_reference_editor({"role": "user"})
        self.assertEqual(error.exception.status_code, 403)

    def test_admin_and_editor_and_service_allowed(self):
        for role in ("admin", "reference_editor", "service"):
            session = {"role": role}
            self.assertIs(require_reference_editor(session), session)
