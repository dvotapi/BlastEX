"""BDX-018: recommend / list / promote API."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidRecommendationError
from api.schemas.design import BlastDesignSchema
from api.schemas.optimization import VariableBoundSchema
from api.schemas.recommendation import RecommendationPromoteRequest, RecommendationRequest
from api.schemas.scenarios import ScenarioParamsSchema
from api.services import recommendation_service
from design.persistence import save_design
from design.recommendation.types import PROFILE_KEYS, PROFILE_LOW_COST
from tests.scenario_fixtures import charged_design

TEAM_ID = "rec-api-team"


class RecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _plan(self):
        return save_design(TEAM_ID, charged_design("rec-api-design"))

    def test_recommend_lists_and_promotes(self):
        design = self._plan()
        payload = BlastDesignSchema(**design.to_dict())
        result = recommendation_service.run_recommendation(
            TEAM_ID,
            RecommendationRequest(
                design=payload,
                profile=PROFILE_LOW_COST,
                variables=[
                    VariableBoundSchema(name="diameter_mm", values=[152, 165]),
                    VariableBoundSchema(name="burden_b_m", values=[4.0]),
                    VariableBoundSchema(name="spacing_a_m", values=[5.0, 5.5]),
                ],
                target_x50_mm=200.0,
                max_candidates=8,
                persist=True,
            ),
        )
        self.assertEqual(result.profile, PROFILE_LOW_COST)
        self.assertFalse(result.auto_applied)
        self.assertFalse(result.approved)
        self.assertTrue(result.engineer_decides)
        self.assertGreaterEqual(result.evaluated, 3)
        self.assertIsNotNone(result.suggested)
        self.assertTrue(result.reasons)
        self.assertIn(result.profile, result.profile_picks)
        for item in result.suggested.scores:
            self.assertEqual(item.role, "predicted")
        self.assertIsNotNone(result.suggested.outcomes.oversize_pct)
        self.assertIsNotNone(result.suggested.outcomes.ppv_mm_s)
        self.assertIsNotNone(result.suggested.outcomes.x50_mm)
        self.assertIsNotNone(result.suggested.outcomes.total_predicted_cost_rub)

        listed = recommendation_service.list_plan_recommendations(TEAM_ID, design.design_id)
        self.assertEqual(len(listed.items), 1)
        self.assertEqual(listed.items[0].recommendation_id, result.recommendation_id)
        self.assertFalse(listed.auto_applied)
        loaded = recommendation_service.get_plan_recommendation(
            TEAM_ID, design.design_id, result.recommendation_id
        )
        self.assertEqual(loaded.recommendation_id, result.recommendation_id)
        self.assertEqual(loaded.suggested.candidate_id, result.suggested.candidate_id)

        promoted = recommendation_service.promote_recommendation(
            TEAM_ID,
            RecommendationPromoteRequest(
                design=payload,
                name="С рекомендации",
                params=ScenarioParamsSchema(**result.suggested.params.model_dump()),
            ),
        )
        self.assertEqual(promoted.name, "С рекомендации")
        self.assertFalse(promoted.modifies_design)

    def test_unknown_profile_is_rejected(self):
        design = self._plan()
        with self.assertRaises(InvalidRecommendationError):
            recommendation_service.run_recommendation(
                TEAM_ID,
                RecommendationRequest(
                    design=BlastDesignSchema(**design.to_dict()),
                    profile="SITE_TRANSFER",
                    variables=[VariableBoundSchema(name="diameter_mm", values=[152])],
                ),
            )

    def test_empty_design_is_rejected(self):
        from design.models import BlastDesign

        with self.assertRaises(InvalidRecommendationError):
            recommendation_service.run_recommendation(
                TEAM_ID,
                RecommendationRequest(
                    design=BlastDesignSchema(**BlastDesign(design_id="empty").to_dict()),
                    profile="BALANCED",
                ),
            )

    def test_known_profiles_are_accepted(self):
        self.assertEqual(
            set(PROFILE_KEYS),
            {"BALANCED", "LOW_COST", "FINE_FRAGMENTATION", "LOW_VIBRATION"},
        )


if __name__ == "__main__":
    unittest.main()
