"""Снимок берёт настройки модели активного объекта работ, если у прогноза нет своих."""
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from api.schemas.datasets import DatasetBuildRequest
from api.services import dataset_service
from cost.v2.repository import InMemoryEconomicsRepository
from design.persistence import save_design
from simulation.fragmentation.cunningham import KuzRamSettings
from tests.dataset_fixtures import closed_design

ORG = "org-ds"
OBJECT = "Карьер-1"


def _repository() -> InMemoryEconomicsRepository:
    repository = InMemoryEconomicsRepository()
    block = {**asdict(KuzRamSettings()), "rock_factor_correction": 1.4}
    repository.save_calc_inputs(ORG, "tester", OBJECT, {"version": 1, "kuzram": block})
    repository.import_legacy_workspace(
        ORG, "tester", team_name="Команда", active_scenario_id="drill_blast", active_work_object_name=OBJECT
    )
    return repository


class DatasetSettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        save_design(ORG, closed_design("ds-1"))

    def _frag(self, repository):
        snapshot = dataset_service.build_snapshot_for_team(
            ORG, DatasetBuildRequest(site_id="quarry-1", design_ids=["ds-1"]), repository=repository
        )
        return snapshot.samples[0].targets["FRAGMENTATION"]

    def test_active_work_object_settings(self):
        frag = self._frag(_repository())

        self.assertEqual(frag["baseline_settings"]["source"], "work_object")
        self.assertEqual(frag["baseline_settings"]["work_object_name"], OBJECT)
        self.assertEqual(frag["baseline_settings"]["values"]["rock_factor_correction"], 1.4)

    def test_without_repository_defaults(self):
        frag = self._frag(None)

        self.assertEqual(frag["baseline_settings"]["source"], "defaults")


if __name__ == "__main__":
    unittest.main()
