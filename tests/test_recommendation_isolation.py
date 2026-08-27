"""BDX-018: recommendation must not rewrite approved holes or loads."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schemas.design import BlastDesignSchema
from api.schemas.recommendation import RecommendationPromoteRequest, RecommendationRequest
from api.schemas.optimization import VariableBoundSchema
from api.schemas.scenarios import ScenarioParamsSchema
from api.services import recommendation_service
from design.persistence import designs_dir, load_design, save_design
from design.recommendation.persistence import recommendations_dir
from design.recommendation.types import PROFILE_BALANCED
from design.scenarios.engine import holes_loads_payload, revision_sha256
from tests.scenario_fixtures import charged_design

TEAM_ID = "rec-iso-team"


class RecommendationIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _saved(self):
        return save_design(TEAM_ID, charged_design("rec-iso-design"))

    def test_run_does_not_change_approved_holes_or_loads(self):
        saved = self._saved()
        holes_before = [hole.to_dict() for hole in saved.holes]
        loads_before = [load.to_dict() for load in saved.loads]
        disk_before = json.loads((designs_dir(TEAM_ID) / f"{saved.design_id}.json").read_text())
        source_hash = revision_sha256(saved)

        result = recommendation_service.run_recommendation(
            TEAM_ID,
            RecommendationRequest(
                design=BlastDesignSchema(**saved.to_dict()),
                profile=PROFILE_BALANCED,
                variables=[
                    VariableBoundSchema(name="diameter_mm", values=[152, 165]),
                    VariableBoundSchema(name="burden_b_m", values=[4.0, 4.5]),
                    VariableBoundSchema(name="spacing_a_m", values=[5.0]),
                ],
                target_x50_mm=200.0,
                max_candidates=6,
                persist=True,
            ),
        )
        self.assertTrue(result.approved_unchanged)
        self.assertFalse(result.modifies_design)
        self.assertFalse(result.replaces_design)
        self.assertFalse(result.auto_applied)
        self.assertFalse(result.approved)
        self.assertTrue(result.engineer_decides)
        self.assertEqual(result.source_revision_sha256, source_hash)
        self.assertEqual(result.applied_as, "recommendation_overlay")
        self.assertGreaterEqual(result.evaluated, 2)
        self.assertIsNotNone(result.suggested)

        reloaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual([hole.to_dict() for hole in reloaded.holes], holes_before)
        self.assertEqual([load.to_dict() for load in reloaded.loads], loads_before)
        self.assertEqual(holes_loads_payload(reloaded), {"holes": holes_before, "loads": loads_before})

        disk_after = json.loads((designs_dir(TEAM_ID) / f"{saved.design_id}.json").read_text())
        self.assertEqual(disk_after, disk_before)

        rec_file = recommendations_dir(TEAM_ID, saved.design_id) / f"{result.recommendation_id}.json"
        self.assertTrue(rec_file.exists())
        self.assertNotEqual(rec_file.parent.resolve(), designs_dir(TEAM_ID).resolve())
        stored = json.loads(rec_file.read_text())
        self.assertFalse(stored["auto_applied"])
        self.assertFalse(stored["approved"])

    def test_promote_creates_scenario_without_touching_design(self):
        saved = self._saved()
        before = holes_loads_payload(saved)
        created = recommendation_service.promote_recommendation(
            TEAM_ID,
            RecommendationPromoteRequest(
                design=BlastDesignSchema(**saved.to_dict()),
                name="Рекомендация LOW_COST",
                params=ScenarioParamsSchema(diameter_mm=165, burden_b_m=4.5, spacing_a_m=5.5),
            ),
        )
        self.assertTrue(created.approved_unchanged)
        self.assertFalse(created.modifies_design)
        self.assertEqual(created.applied_as, "scenario_overlay")
        reloaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(holes_loads_payload(reloaded), before)


if __name__ == "__main__":
    unittest.main()
