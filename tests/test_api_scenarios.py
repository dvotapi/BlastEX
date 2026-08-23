"""BDX-016: create / list / compare design-scenario API."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidDesignScenarioError
from api.schemas.design import BlastDesignSchema
from api.schemas.scenarios import ScenarioCompareRequest, ScenarioCreateRequest, ScenarioParamsSchema
from api.services import scenario_service
from design.persistence import save_design
from tests.scenario_fixtures import charged_design

TEAM_ID = "scn-api-team"


class ScenarioApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _plan(self):
        return save_design(TEAM_ID, charged_design("api-design"))

    def test_create_list_compare_two_alternatives(self):
        design = self._plan()
        payload = BlastDesignSchema(**design.to_dict())
        first = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=payload,
                name="Сценарий A",
                params=ScenarioParamsSchema(
                    diameter_mm=165,
                    spacing_a_m=6.0,
                    burden_b_m=5.0,
                    powder_factor_kg_m3=0.65,
                ),
            ),
        )
        second = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=payload,
                name="Сценарий B",
                params=ScenarioParamsSchema(
                    diameter_mm=165,
                    spacing_a_m=6.5,
                    burden_b_m=5.5,
                    powder_factor_kg_m3=0.58,
                ),
            ),
        )
        self.assertEqual(first.params.spacing_a_m, 6.0)
        self.assertEqual(second.params.spacing_a_m, 6.5)
        self.assertGreater(first.outcomes.drilling_metres, 0.0)
        self.assertGreater(first.outcomes.explosive_mass_kg, 0.0)
        self.assertIsNotNone(first.outcomes.x50_mm)
        self.assertIsNotNone(first.outcomes.x80_mm)
        self.assertIsNotNone(first.outcomes.oversize_pct)
        self.assertIsNotNone(first.outcomes.mic_kg)
        self.assertIsNotNone(first.outcomes.ppv_mm_s)
        self.assertIsNotNone(first.outcomes.direct_cost_rub)
        self.assertIsNotNone(first.outcomes.total_predicted_cost_rub)
        self.assertGreater(first.outcomes.total_predicted_cost_rub, 0.0)
        self.assertAlmostEqual(first.outcomes.powder_factor_kg_m3, 0.65, places=2)
        self.assertAlmostEqual(second.outcomes.powder_factor_kg_m3, 0.58, places=2)

        listed = scenario_service.list_plan_scenarios(TEAM_ID, design.design_id)
        self.assertEqual(len(listed.items), 2)
        self.assertEqual({item.name for item in listed.items}, {"Сценарий A", "Сценарий B"})
        loaded = scenario_service.get_plan_scenario(TEAM_ID, design.design_id, first.scenario_id)
        self.assertEqual(loaded.name, "Сценарий A")

        table = scenario_service.compare_plan_scenarios(
            TEAM_ID,
            ScenarioCompareRequest(
                design_id=design.design_id,
                scenario_ids=[first.scenario_id, second.scenario_id],
                include_baseline=True,
            ),
        )
        names = [column.name for column in table.scenarios]
        self.assertEqual(names[0], "Утверждённый проект")
        self.assertIn("Сценарий A", names)
        self.assertIn("Сценарий B", names)
        keys = [row.key for row in table.rows]
        for required in (
            "drilling_metres",
            "explosive_mass_kg",
            "x50_mm",
            "x80_mm",
            "oversize_pct",
            "mic_kg",
            "ppv_mm_s",
            "direct_cost_rub",
            "total_predicted_cost_rub",
        ):
            self.assertIn(required, keys)
        self.assertFalse(table.is_optimiser)
        self.assertTrue(table.approved_unchanged)

    def test_empty_design_is_rejected(self):
        from design.models import BlastDesign

        with self.assertRaises(InvalidDesignScenarioError):
            scenario_service.create_scenario(
                TEAM_ID,
                ScenarioCreateRequest(
                    design=BlastDesignSchema(**BlastDesign(design_id="empty").to_dict()),
                    name="Пустой",
                ),
            )

    def test_production_outcome_overlay_is_reused(self):
        from api.schemas.outcomes import OutcomeStatusRequest, OutcomeTrainRequest
        from api.services import outcome_service
        from design.persistence import load_design
        from intelligence.datasets.persistence import save_snapshot
        from tests.outcome_fixtures import synthetic_outcome_snapshot

        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot())
        trained = outcome_service.train_outcome(
            TEAM_ID,
            OutcomeTrainRequest(
                dataset_id=snapshot.dataset_id,
                model_type="fragmentation",
                site_id="quarry-1",
            ),
        )
        outcome_service.update_status(
            TEAM_ID, trained.model_id, OutcomeStatusRequest(status="production")
        )
        design = self._plan()
        holes_before = [hole.to_dict() for hole in design.holes]
        created = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=BlastDesignSchema(**design.to_dict()),
                name="С ML-оверлеем",
                params=ScenarioParamsSchema(
                    diameter_mm=165,
                    spacing_a_m=6.0,
                    burden_b_m=5.0,
                    site_id="quarry-1",
                    use_production_overlays=True,
                ),
            ),
        )
        self.assertTrue(created.outcomes.ml_overlay_applied)
        self.assertEqual(created.outcomes.fragmentation_source, "ml_overlay")
        self.assertIsNotNone(created.outcomes.x50_engineering_mm)
        self.assertIsNotNone(created.outcomes.x50_mm)
        reloaded = load_design(TEAM_ID, design.design_id)
        self.assertEqual([hole.to_dict() for hole in reloaded.holes], holes_before)


if __name__ == "__main__":
    unittest.main()
