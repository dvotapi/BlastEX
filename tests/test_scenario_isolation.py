"""BDX-016: creating overlays must not rewrite approved holes or loads."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schemas.design import BlastDesignSchema
from api.schemas.scenarios import ScenarioCompareRequest, ScenarioCreateRequest, ScenarioParamsSchema
from api.services import scenario_service
from design.persistence import designs_dir, load_design, save_design
from design.scenarios.engine import holes_loads_payload, revision_sha256
from design.scenarios.persistence import scenarios_dir
from tests.scenario_fixtures import charged_design

TEAM_ID = "scn-iso-team"


class ScenarioIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _saved(self):
        return save_design(TEAM_ID, charged_design("iso-design"))

    def test_create_does_not_change_approved_holes_or_loads(self):
        saved = self._saved()
        holes_before = [hole.to_dict() for hole in saved.holes]
        loads_before = [load.to_dict() for load in saved.loads]
        disk_before = json.loads((designs_dir(TEAM_ID) / f"{saved.design_id}.json").read_text())
        source_hash = revision_sha256(saved)

        created = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=BlastDesignSchema(**saved.to_dict()),
                name="Сценарий A",
                params=ScenarioParamsSchema(diameter_mm=165, spacing_a_m=6.0, burden_b_m=5.0, powder_factor_kg_m3=0.65),
            ),
        )
        self.assertTrue(created.approved_unchanged)
        self.assertFalse(created.modifies_design)
        self.assertEqual(created.approved_revision_sha256, source_hash)
        self.assertNotEqual(created.overlay_revision_sha256, source_hash)

        reloaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual([hole.to_dict() for hole in reloaded.holes], holes_before)
        self.assertEqual([load.to_dict() for load in reloaded.loads], loads_before)
        self.assertEqual(holes_loads_payload(reloaded), {"holes": holes_before, "loads": loads_before})

        disk_after = json.loads((designs_dir(TEAM_ID) / f"{saved.design_id}.json").read_text())
        self.assertEqual(disk_after["holes"], disk_before["holes"])
        self.assertEqual(disk_after["loads"], disk_before["loads"])
        self.assertEqual(disk_after, disk_before)

        scenario_file = scenarios_dir(TEAM_ID, saved.design_id) / f"{created.scenario_id}.json"
        self.assertTrue(scenario_file.exists())
        self.assertNotEqual(scenario_file.parent.resolve(), designs_dir(TEAM_ID).resolve())

    def test_two_scenarios_leave_approved_intact(self):
        saved = self._saved()
        before = holes_loads_payload(saved)
        scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=BlastDesignSchema(**saved.to_dict()),
                name="Сценарий A",
                params=ScenarioParamsSchema(diameter_mm=165, spacing_a_m=6.0, burden_b_m=5.0, powder_factor_kg_m3=0.65),
            ),
        )
        scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=BlastDesignSchema(**saved.to_dict()),
                name="Сценарий B",
                params=ScenarioParamsSchema(diameter_mm=165, spacing_a_m=6.5, burden_b_m=5.5, powder_factor_kg_m3=0.58),
            ),
        )
        compared = scenario_service.compare_plan_scenarios(
            TEAM_ID,
            ScenarioCompareRequest(design_id=saved.design_id, include_baseline=True),
        )
        self.assertTrue(compared.approved_unchanged)
        self.assertFalse(compared.modifies_design)
        self.assertFalse(compared.is_optimiser)
        reloaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(holes_loads_payload(reloaded), before)


if __name__ == "__main__":
    unittest.main()
