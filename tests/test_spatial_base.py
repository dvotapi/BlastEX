"""Физика пространственного прогноза считается базой своей модели."""
import unittest
from unittest.mock import patch

from api.schemas.design import BlastDesignSchema
from api.schemas.spatial import SpatialPredictRequest
from api.services import spatial_service
from api.services.fragmentation_settings import ResolvedSettings
from intelligence.spatial.prediction import apply_model
from intelligence.spatial.training import train_from_snapshot
from simulation.fragmentation import engine as fragmentation_engine
from simulation.fragmentation.base import SETTINGS_SOURCE_WORK_OBJECT
from simulation.fragmentation.cunningham import KuzRamSettings
from tests.calibration_fixtures import CURRENT_VERSION  # версия текущей базы — из реестра моделей движка
from tests.spatial_fixtures import multi_hole_design, synthetic_spatial_snapshot


def _physics_models(model):
    with patch.object(fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region) as spy:
        overlay = apply_model(multi_hole_design(), model=model)
    return {call.kwargs.get("model") for call in spy.call_args_list}, overlay


class SpatialBaseTests(unittest.TestCase):
    def test_without_model_current_base(self):
        models, overlay = _physics_models(None)

        self.assertEqual(models, {"kuzram"})
        self.assertEqual((overlay.physics_model, overlay.physics_model_version), ("kuzram", CURRENT_VERSION))
        self.assertEqual(overlay.base_label, "")

    def test_old_model_keeps_old_physics(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")

        models, overlay = _physics_models(model)

        self.assertEqual(models, {"kuzram_legacy"})
        self.assertIn("Старая база", overlay.base_label)

    def test_new_model_current_physics(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")
        model.baseline_model, model.baseline_model_version = "kuzram", CURRENT_VERSION

        models, overlay = _physics_models(model)

        self.assertEqual(models, {"kuzram"})
        self.assertEqual(overlay.base_label, f"База: Kuz-Ram {CURRENT_VERSION}")

    def test_unknown_base_falls_back_to_current_physics(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")
        model.baseline_model, model.baseline_model_version = "no_such_model", "9.0.0"

        models, overlay = _physics_models(model)

        self.assertEqual(models, {"kuzram"})
        self.assertEqual((overlay.physics_model, overlay.physics_model_version), ("kuzram", CURRENT_VERSION))
        self.assertIn("модель неизвестна", overlay.base_label)
        self.assertTrue(any("неизвестна" in item for item in overlay.warnings))


class SpatialServiceBaseTests(unittest.TestCase):
    def _request(self, **kwargs):
        return SpatialPredictRequest(design=BlastDesignSchema(**multi_hole_design().to_dict()), **kwargs)

    def _predict(self, model, resolved=None):
        with (
            patch.object(spatial_service, "load_model", return_value=model),
            patch.object(spatial_service, "resolve_kuzram_settings", return_value=resolved) as resolve,
            patch.object(fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region) as spy,
        ):
            response = spatial_service.predict_spatial("sp", self._request(model_id="m1" if model else ""))
        return response, resolve, spy

    def test_without_model_response_carries_current_base(self):
        resolved = ResolvedSettings(KuzRamSettings(), "defaults")

        response, resolve, _ = self._predict(None, resolved)

        resolve.assert_called_once()
        self.assertEqual(
            (response.physics_model, response.physics_model_version, response.base_label),
            ("kuzram", CURRENT_VERSION, ""),
        )

    def test_old_model_does_not_resolve_settings(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")

        response, resolve, spy = self._predict(model)

        resolve.assert_not_called()
        self.assertEqual({call.kwargs["model"] for call in spy.call_args_list}, {"kuzram_legacy"})
        self.assertEqual((response.physics_model, response.physics_model_version), ("kuzram_legacy", "1.0.0"))
        self.assertIn("Старая база", response.base_label)

    def test_new_model_gets_resolved_settings_and_their_warnings(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")
        model.baseline_model, model.baseline_model_version = "kuzram", CURRENT_VERSION
        settings = KuzRamSettings(rock_factor_correction=1.1)
        resolved = ResolvedSettings(
            settings, SETTINGS_SOURCE_WORK_OBJECT, "Карьер", ("Настройки объекта не прочитаны.",)
        )

        response, resolve, spy = self._predict(model, resolved)

        resolve.assert_called_once()
        self.assertEqual({call.kwargs["settings"] for call in spy.call_args_list}, {settings})
        self.assertEqual(response.base_label, f"База: Kuz-Ram {CURRENT_VERSION}")
        self.assertIn("Настройки объекта не прочитаны.", response.warnings)


if __name__ == "__main__":
    unittest.main()
