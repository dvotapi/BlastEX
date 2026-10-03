"""Артефакты помнят базу; файлы до PR 3 грузятся и меняют статус как раньше."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.services import calibration_service, spatial_service
from intelligence.calibration import persistence as calibration_store
from intelligence.calibration.training import train_from_snapshot
from intelligence.spatial import persistence as spatial_store
from intelligence.spatial.training import train_from_snapshot as train_spatial
from tests.calibration_fixtures import CURRENT_BASE_FIELDS, CURRENT_VERSION, synthetic_snapshot
from tests.spatial_fixtures import synthetic_spatial_snapshot

TEAM_ID = "artifact-base"
CURRENT = (CURRENT_BASE_FIELDS["baseline_model"], CURRENT_VERSION)


def _strip_base(path: Path, integrity_hash) -> None:
    """Файл как до PR 3: без полей базы, с пересчитанной контрольной суммой."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("baseline_model", None)
    data.pop("baseline_model_version", None)
    data["integrity_sha256"] = integrity_hash(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ArtifactBaseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calibration(self, model_id: str, base: tuple[str, str]):
        model = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id=model_id)
        model.baseline_model, model.baseline_model_version = base
        return calibration_store.save_model(TEAM_ID, model)

    def test_fields_round_trip(self):
        saved = self._calibration("cal-new", CURRENT)

        loaded = calibration_store.load_model(TEAM_ID, saved.model_id)

        self.assertEqual((loaded.baseline_model, loaded.baseline_model_version), CURRENT)

    def test_file_before_pr3_loads_and_changes_status(self):
        saved = self._calibration("cal-old", CURRENT)
        _strip_base(calibration_store.metadata_path(TEAM_ID, saved.model_id), calibration_store.integrity_hash)

        loaded = calibration_store.load_model(TEAM_ID, saved.model_id)
        promoted = calibration_store.set_status(TEAM_ID, saved.model_id, "production")

        self.assertEqual(loaded.baseline_model, "")
        self.assertEqual(promoted.status, "production")

    def test_labels_in_list_and_card(self):
        self._calibration("cal-new", CURRENT)
        self._calibration("cal-old", ("", ""))

        labels = {item.model_id: item.base_label for item in calibration_service.list_calibration_models(TEAM_ID).items}
        card = calibration_service.get_calibration_model(TEAM_ID, "cal-old")

        self.assertEqual(labels["cal-new"], f"База: Kuz-Ram {CURRENT_VERSION}")
        self.assertIn("Старая база", labels["cal-old"])
        self.assertIn("Старая база", card.base_label)

    def test_spatial_model_file_before_pr3(self):
        model = train_spatial(synthetic_spatial_snapshot(), team_id=TEAM_ID, model_id="sp-old")
        saved = spatial_store.save_model(TEAM_ID, model)
        _strip_base(spatial_store.metadata_path(TEAM_ID, saved.model_id), spatial_store.integrity_hash)

        loaded = spatial_store.load_model(TEAM_ID, saved.model_id)
        listed = spatial_service.list_spatial_models(TEAM_ID)

        self.assertEqual(loaded.baseline_model, "")
        self.assertIn("Старая база", listed.items[0].base_label)

    def test_unknown_base_in_file_does_not_break_list_and_card(self):
        """Чужой или испорченный файл с неизвестной моделью базы не роняет список и карточку."""
        saved = self._calibration("cal-foreign", ("no_such_model", "9.9.9"))

        listed = calibration_service.list_calibration_models(TEAM_ID).items
        card = calibration_service.get_calibration_model(TEAM_ID, saved.model_id)

        self.assertIn("модель неизвестна", listed[0].base_label)
        self.assertIn("модель неизвестна", card.base_label)


if __name__ == "__main__":
    unittest.main()
