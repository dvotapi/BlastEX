"""BDX-016: scenario files live beside the passport, not inside it."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design.persistence import designs_dir, save_design
from design.scenarios.persistence import list_scenarios, load_scenario, save_scenario, scenarios_dir
from design.scenarios.types import DesignScenario, ScenarioOutcomes, ScenarioParams
from tests.scenario_fixtures import charged_design

TEAM_ID = "scn-store-team"


class ScenarioPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_list_load_outside_designs(self):
        design = save_design(TEAM_ID, charged_design("store-design"))
        scenario = DesignScenario(
            scenario_id="",
            design_id=design.design_id,
            name="Сценарий A",
            params=ScenarioParams(diameter_mm=165.0),
            outcomes=ScenarioOutcomes(hole_count=8, diameter_mm=165.0),
        )
        saved = save_scenario(TEAM_ID, scenario)
        self.assertTrue(saved.scenario_id)
        listed = list_scenarios(TEAM_ID, design.design_id)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].name, "Сценарий A")
        loaded = load_scenario(TEAM_ID, design.design_id, saved.scenario_id)
        self.assertEqual(loaded.params.diameter_mm, 165.0)

        designs_folder = designs_dir(TEAM_ID)
        scenarios_folder = scenarios_dir(TEAM_ID, design.design_id)
        self.assertTrue(scenarios_folder.exists())
        self.assertNotEqual(designs_folder.resolve(), scenarios_folder.resolve())
        self.assertEqual(list(designs_folder.glob("*.json"))[0].read_text(encoding="utf-8").count("Сценарий A"), 0)


if __name__ == "__main__":
    unittest.main()
