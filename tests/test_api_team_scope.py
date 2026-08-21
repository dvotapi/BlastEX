"""team_id для справочников берётся из сессии (api.security.current_team_id),
а не из query-параметра; запись доступна только admin/reference_editor/service."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import cost.persistence as persistence
from api.routers import references as references_router
from api.schemas.references import RockSchema, WorkObjectSchema
from api.security import require_reference_editor
from cost.drilling_data import DEFAULT_WORK_OBJECTS
from cost.rock_data import DEFAULT_ROCKS


class TeamScopedReferencesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_root = Path(self._tmp.name)
        patcher = patch.object(persistence, "data_root", return_value=tmp_root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_write_is_isolated_per_team(self):
        payload = [
            WorkObjectSchema(name="Тестовый карьер", mobilization_km=42.0, diesel_price_ton_rub=90_000.0)
        ]
        references_router.put_work_objects(payload, team_id="team_b", _editor={"role": "admin"})

        team_a = references_router.list_work_objects(team_id="team_a")
        self.assertEqual([o.name for o in team_a.items], [o.name for o in DEFAULT_WORK_OBJECTS])

        team_b = references_router.list_work_objects(team_id="team_b")
        self.assertEqual([o.name for o in team_b.items], ["Тестовый карьер"])

    def test_rocks_round_trip(self):
        edited = [
            RockSchema(name=DEFAULT_ROCKS[0].name, density_t_m3=9.99, ucs_mpa=100.0, fissuring_ff=1.0)
        ]
        result = references_router.put_rocks(edited, team_id="team_c", _editor={"role": "reference_editor"})
        self.assertEqual(result.items[0].density_t_m3, 9.99)
        reloaded = references_router.list_rocks(team_id="team_c")
        self.assertEqual(reloaded.items[0].density_t_m3, 9.99)


class ReferenceEditorGateTests(unittest.TestCase):
    def test_user_role_forbidden(self):
        with self.assertRaises(HTTPException) as error:
            require_reference_editor({"role": "user"})
        self.assertEqual(error.exception.status_code, 403)

    def test_admin_and_editor_and_service_allowed(self):
        for role in ("admin", "reference_editor", "service"):
            session = {"role": role}
            self.assertIs(require_reference_editor(session), session)


if __name__ == "__main__":
    unittest.main()
