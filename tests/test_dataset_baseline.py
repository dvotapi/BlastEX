"""Строка снимка: сохранённый прогноз как есть и baseline текущей базы рядом."""
import unittest
from dataclasses import asdict
from unittest.mock import patch

from intelligence.datasets.baseline import fragmentation_baseline
from intelligence.datasets.builder import DatasetSnapshot, build_sample, build_snapshot
from intelligence.datasets.targets import target_group_has_values
from simulation.fragmentation import engine as fragmentation_engine
from simulation.fragmentation.base import settings_from_snapshot
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.engine import predict_design
from simulation.fragmentation.regions import ExplosiveSpec, RockSpec
from tests.dataset_fixtures import closed_design

ROCK = RockSpec(name="Гранит", density_t_m3=2.65, ucs_mpa=150.0, fissuring_ff=2.0)
EXPLOSIVE = ExplosiveSpec(name="АНФО", density_t_m3=0.82, power_mj_kg=3.8)
FALLBACK = KuzRamSettings(rock_factor_correction=0.8)
FALLBACK_SOURCE = {"source": "work_object", "work_object_name": "Карьер-2", "warnings": []}


def _site_x50(design, **kwargs) -> float:
    return predict_design(design, model="kuzram", **kwargs)["site"]["prediction"]["x50_mm"]


def _with_stored_inputs(design):
    """Сохранённый прогноз с входными величинами — как у панели «Кусковатость»."""
    site = predict_design(design, model="kuzram_legacy", default_rock=ROCK, default_explosive=EXPLOSIVE)["site"]
    design.blast_result.basis.predicted_fragmentation.provenance.inputs = dict(site["inputs"])
    return design


class RowTests(unittest.TestCase):
    def test_stored_prediction_kept_and_current_baseline_added(self):
        design = closed_design("b-1")

        frag = build_sample(design, site_id="quarry-1").targets["FRAGMENTATION"]

        self.assertEqual(frag["predicted_x50_mm"], 150.0)
        self.assertEqual((frag["predicted_model"], frag["predicted_model_version"]), ("kuzram", "1"))
        self.assertEqual((frag["baseline_model"], frag["baseline_model_version"]), ("kuzram", "2.0.0"))
        self.assertAlmostEqual(frag["baseline_x50_mm"], _site_x50(design), places=9)
        self.assertIn("умолчания", frag["baseline_warnings"][0])

    def test_rock_and_explosive_from_stored_inputs(self):
        design = _with_stored_inputs(closed_design("b-2"))

        result = fragmentation_baseline(design)

        self.assertAlmostEqual(
            result["baseline_x50_mm"], _site_x50(design, default_rock=ROCK, default_explosive=EXPLOSIVE), places=9
        )
        self.assertFalse(any("умолчания" in item for item in result["baseline_warnings"]))

    def test_zero_stored_inputs_fall_back_to_defaults(self):
        design = closed_design("b-3")
        design.blast_result.basis.predicted_fragmentation.provenance.inputs = {
            "rock_ucs_mpa": 0.0,
            "rock_density_t_m3": 0.0,
            "explosive_energy_mj_kg": 0.0,
        }

        result = fragmentation_baseline(design)

        self.assertAlmostEqual(result["baseline_x50_mm"], _site_x50(design), places=9)

    def test_settings_snapshot_of_stored_prediction_wins(self):
        design = closed_design("b-4")
        design.blast_result.basis.predicted_fragmentation.provenance.settings = {
            "source": "work_object",
            "work_object_name": "Карьер-1",
            "values": asdict(KuzRamSettings(rock_factor_correction=1.3)),
            "warnings": [],
        }

        result = fragmentation_baseline(design, fallback_settings=FALLBACK, fallback_source=FALLBACK_SOURCE)

        self.assertEqual(result["baseline_settings"]["values"]["rock_factor_correction"], 1.3)
        self.assertEqual(result["baseline_settings"]["work_object_name"], "Карьер-1")

    def test_fallback_settings_without_snapshot(self):
        result = fragmentation_baseline(
            closed_design("b-5"), fallback_settings=FALLBACK, fallback_source=FALLBACK_SOURCE
        )

        self.assertEqual(result["baseline_settings"]["values"]["rock_factor_correction"], 0.8)
        self.assertEqual(result["baseline_settings"]["work_object_name"], "Карьер-2")

    def test_engine_failure_keeps_row(self):
        design = closed_design("b-6")
        # Без дек движок оценивает заряд по диаметру; нулевой диаметр лишает его и этой оценки.
        design.loads = []
        design.holes[0].diameter_mm = 0.0

        frag = build_sample(design, site_id="quarry-1").targets["FRAGMENTATION"]

        self.assertIsNone(frag["baseline_x50_mm"])
        self.assertIn("не посчитан", frag["baseline_warnings"][-1])

    def test_string_fields_do_not_complete_group(self):
        group = {
            "predicted_model": "kuzram",
            "predicted_model_version": "2.0.0",
            "baseline_model": "kuzram",
            "baseline_model_version": "2.0.0",
            "baseline_x50_mm": 150.0,
            "baseline_settings": {"source": "defaults"},
            "baseline_warnings": ["x"],
        }
        self.assertFalse(target_group_has_values(group))

    def test_baseline_alone_does_not_fill_group_of_unmeasured_blast(self):
        design = closed_design("b-7")
        design.blast_result = None

        frag = build_sample(design, site_id="quarry-1").targets["FRAGMENTATION"]

        self.assertIsNotNone(frag["baseline_x50_mm"])
        self.assertIn("Сохранённого прогноза нет", frag["baseline_warnings"][0])
        self.assertFalse(target_group_has_values(frag))


class BrokenStoredDataTests(unittest.TestCase):
    """Плохие данные сохранённого прогноза не роняют строку и сборку снимка."""

    @staticmethod
    def _with_settings(design_id: str, settings: dict):
        design = closed_design(design_id)
        design.blast_result.basis.predicted_fragmentation.provenance.settings = settings
        return design

    def _frag(self, design, **kwargs) -> dict:
        return build_sample(design, site_id="quarry-1", **kwargs).targets["FRAGMENTATION"]

    def test_unknown_settings_key_falls_back_with_warning(self):
        design = self._with_settings(
            "x-1",
            {"source": "work_object", "work_object_name": "Карьер-1", "values": {"bogus": 1}, "warnings": []},
        )

        frag = self._frag(design, fallback_settings=FALLBACK, fallback_source=FALLBACK_SOURCE)

        self.assertIsNotNone(frag["baseline_x50_mm"])
        self.assertTrue(any("Снимок настроек сохранённого прогноза не прочитан" in w for w in frag["baseline_warnings"]))
        self.assertTrue(any("настройки объекта работ" in w for w in frag["baseline_warnings"]))
        self.assertEqual(frag["baseline_settings"]["values"]["rock_factor_correction"], 0.8)
        self.assertEqual(frag["baseline_settings"]["work_object_name"], "Карьер-2")

    def test_out_of_range_settings_value_falls_back_to_defaults(self):
        design = self._with_settings(
            "x-2",
            {"source": "work_object", "work_object_name": "Карьер-1", "values": {"joint_angle": 25}, "warnings": []},
        )

        frag = self._frag(design)

        self.assertIsNotNone(frag["baseline_x50_mm"])
        self.assertTrue(any("Снимок настроек сохранённого прогноза не прочитан" in w for w in frag["baseline_warnings"]))
        self.assertTrue(any("умолчания" in w for w in frag["baseline_warnings"]))
        self.assertEqual(frag["baseline_settings"]["source"], "defaults")
        self.assertAlmostEqual(frag["baseline_x50_mm"], _site_x50(design), places=9)

    def test_baseline_settings_returns_warning_instead_of_raising(self):
        from intelligence.datasets.baseline import baseline_settings

        design = self._with_settings("x-3", {"values": {"bogus": 1}})

        settings, source, warnings = baseline_settings(design, FALLBACK, FALLBACK_SOURCE)

        self.assertIs(settings, FALLBACK)
        self.assertEqual(source["work_object_name"], "Карьер-2")
        self.assertEqual(len(warnings), 1)

    def test_unreadable_inputs_fall_back_to_defaults_with_warning(self):
        design = closed_design("x-4")
        design.blast_result.basis.predicted_fragmentation.provenance.inputs = {"rock_ucs_mpa": "abc"}

        frag = self._frag(design)

        self.assertIsNotNone(frag["baseline_x50_mm"])
        self.assertAlmostEqual(frag["baseline_x50_mm"], _site_x50(design), places=9)
        self.assertTrue(any("Входные величины сохранённого прогноза не прочитаны" in w for w in frag["baseline_warnings"]))

    def test_broken_snapshot_does_not_break_dataset_snapshot(self):
        broken = self._with_settings("x-5", {"values": {"bogus": 1}})

        snapshot = build_snapshot(
            [broken, closed_design("x-6")], site_id="quarry-1", dataset_id="s", dataset_version=1
        )

        self.assertEqual(snapshot.sample_count, 2)

    def test_settings_are_read_once_per_sample(self):
        design = self._with_settings(
            "x-7", {"source": "work_object", "work_object_name": "Карьер-1", "values": {}, "warnings": []}
        )
        design.blast_result.basis.predicted_fragmentation.provenance.settings["values"] = asdict(
            KuzRamSettings(rock_factor_correction=1.3)
        )

        with patch("intelligence.datasets.baseline.settings_from_snapshot", wraps=settings_from_snapshot) as spy:
            self._frag(design)

        self.assertEqual(spy.call_count, 1)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_records_base(self):
        snapshot = build_snapshot([closed_design("s-1")], site_id="quarry-1", dataset_id="s", dataset_version=1)

        self.assertEqual(snapshot.fragmentation_base, {"model": "kuzram", "model_version": "2.0.0"})
        restored = DatasetSnapshot.from_dict(snapshot.to_dict())
        self.assertEqual(restored.fragmentation_base, snapshot.fragmentation_base)

    def test_old_snapshot_has_no_base(self):
        payload = build_snapshot([closed_design("s-2")], site_id="quarry-1", dataset_id="s", dataset_version=1).to_dict()
        payload.pop("fragmentation_base")

        self.assertEqual(DatasetSnapshot.from_dict(payload).fragmentation_base, {})

    def test_hole_physics_uses_current_model(self):
        with patch.object(
            fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region
        ) as spy:
            build_sample(closed_design("s-3"), site_id="quarry-1")

        self.assertTrue(spy.call_args_list)
        models = {call.kwargs.get("model", call.args[1] if len(call.args) > 1 else None) for call in spy.call_args_list}
        self.assertEqual(models, {"kuzram"})


if __name__ == "__main__":
    unittest.main()
