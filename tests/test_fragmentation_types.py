"""Типы кусковатости: новые поля читаются из старых записей и не теряются."""
import unittest

from api.schemas.design import FragmentationInputsSchema, PredictedFragmentationSchema
from simulation.fragmentation.models import (
    FRAGMENTATION_MODEL_IDS,
    LEGACY_MODEL_SUFFIX,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)
from tests.test_fragmentation_kuzram import _inputs


class FragmentationTypesTests(unittest.TestCase):
    def test_six_model_ids(self):
        self.assertEqual(
            FRAGMENTATION_MODEL_IDS,
            ("kuznetsov", "kuzram", "swebrec", "kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy"),
        )
        self.assertEqual(LEGACY_MODEL_SUFFIX, "_legacy")

    def test_old_inputs_payload_reads_zero_lengths(self):
        payload = _inputs().to_dict()
        payload.pop("charge_length_m")
        payload.pop("hole_length_m")

        inputs = FragmentationInputs.from_dict(payload)

        self.assertEqual(inputs.charge_length_m, 0.0)
        self.assertEqual(inputs.hole_length_m, 0.0)

    def test_inputs_lengths_round_trip(self):
        inputs = _inputs(charge_length_m=8.0, hole_length_m=11.0)

        restored = FragmentationInputs.from_dict(inputs.to_dict())

        self.assertEqual(restored.charge_length_m, 8.0)
        self.assertEqual(restored.hole_length_m, 11.0)
        self.assertEqual(FragmentationInputsSchema(**inputs.to_dict()).charge_length_m, 8.0)

    def test_old_prediction_payload_reads_without_warnings_and_settings(self):
        payload = {
            "x20_mm": 50.0,
            "x50_mm": 150.0,
            "x80_mm": 300.0,
            "oversize_pct": 4.0,
            "powder_factor_kg_m3": 0.7,
            "provenance": {"model": "kuzram", "model_version": "1.0.0"},
        }

        prediction = PredictedFragmentation.from_dict(payload)

        self.assertEqual(prediction.warnings, [])
        self.assertEqual(prediction.provenance.settings, {})
        self.assertEqual(PredictedFragmentationSchema(**prediction.to_dict()).warnings, [])

    def test_prediction_warnings_and_settings_round_trip(self):
        snapshot = {
            "source": "work_object",
            "work_object_name": "Карьер-1",
            "values": {"rock_factor_correction": 1.3},
            "warnings": [],
        }
        prediction = PredictedFragmentation(
            x20_mm=50.0,
            x50_mm=150.0,
            x80_mm=300.0,
            oversize_pct=4.0,
            powder_factor_kg_m3=0.7,
            provenance=ModelProvenance(model="kuzram", model_version="2.0.0", settings=snapshot),
            warnings=["Длина заряда не задана."],
        )

        payload = prediction.to_dict()
        restored = PredictedFragmentation.from_dict(payload)
        schema = PredictedFragmentationSchema(**payload)

        self.assertEqual(restored.warnings, ["Длина заряда не задана."])
        self.assertEqual(restored.provenance.settings, snapshot)
        self.assertEqual(schema.warnings, ["Длина заряда не задана."])
        self.assertEqual(schema.provenance.settings["work_object_name"], "Карьер-1")


if __name__ == "__main__":
    unittest.main()
