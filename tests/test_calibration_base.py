"""База калибровки: к какому прогнозу можно наложить поправку."""
import unittest

from intelligence.calibration.base import (
    CURRENT_BASE,
    LEGACY_BASE,
    FragmentationBase,
    artifact_base,
    base_label,
    compatible,
    prediction_base,
    refusal_reason,
    sample_baseline,
    snapshot_base,
    spatial_base_label,
    version_major,
)
from simulation.fragmentation.engine import FRAGMENTATION_MODELS
from simulation.fragmentation.models import is_old_model
from tests.calibration_fixtures import CURRENT_VERSION, PR2_VERSION

X50 = "kuzram_residual"
OVERSIZE = "oversize_residual"
PPV = "ppv_residual"
NEW_SWEBREC = FragmentationBase("swebrec", CURRENT_VERSION)


class PredictionBaseTests(unittest.TestCase):
    def test_current_and_legacy(self):
        self.assertEqual(CURRENT_BASE, FragmentationBase("kuzram", str(FRAGMENTATION_MODELS["kuzram"]["version"])))
        self.assertEqual(LEGACY_BASE, FragmentationBase("kuzram_legacy", "1.0.0"))

    def test_saved_before_pr2_is_legacy(self):
        for version in ("1.0.0", "1", ""):
            with self.subTest(version=version):
                self.assertEqual(prediction_base("kuzram", version), LEGACY_BASE)
        self.assertEqual(prediction_base("swebrec", "1.0.0"), FragmentationBase("swebrec_legacy", "1.0.0"))

    def test_new_and_aliases(self):
        self.assertEqual(prediction_base("Kuz-Ram", CURRENT_VERSION), CURRENT_BASE)
        self.assertEqual(prediction_base("swebrec_legacy", "1.0.0"), FragmentationBase("swebrec_legacy", "1.0.0"))

    def test_pr2_version_is_not_old_but_not_current_base(self):
        """Прогноз «kuzram 2.0.0» (PR 2, до учёта силы ВВ) — не старая модель, но другая база."""
        self.assertNotEqual(PR2_VERSION, CURRENT_VERSION)
        self.assertFalse(is_old_model("kuzram", PR2_VERSION))

        base = prediction_base("kuzram", PR2_VERSION)

        self.assertEqual(base, FragmentationBase("kuzram", PR2_VERSION))
        self.assertFalse(base.legacy)
        self.assertNotEqual(base, CURRENT_BASE)

    def test_unknown_model(self):
        with self.assertRaises(ValueError):
            prediction_base("abc", CURRENT_VERSION)

    def test_artifact_without_fields_is_legacy(self):
        self.assertEqual(artifact_base("", ""), LEGACY_BASE)
        self.assertEqual(artifact_base("kuzram", CURRENT_VERSION), CURRENT_BASE)

    def test_snapshot_base(self):
        self.assertIsNone(snapshot_base({}))
        self.assertEqual(snapshot_base({"model": "kuzram", "model_version": CURRENT_VERSION}), CURRENT_BASE)


class VersionMajorTests(unittest.TestCase):
    def test_version_major(self):
        cases = {"1.0.0": 1, "2": 2, "3.0.0": 3, "10.1": 10, "v2.0.0": None, "abc": None, "": None, "-1.0": None, "²": None}
        for version, expected in cases.items():
            with self.subTest(version=version):
                self.assertEqual(version_major(version), expected)

    def test_version_major_of_huge_number_is_not_recognized(self):
        self.assertIsNone(version_major("9" * 5000 + ".0"))


class CompatibilityTests(unittest.TestCase):
    def test_x50_fits_any_model_of_same_base(self):
        self.assertTrue(compatible(X50, CURRENT_BASE, NEW_SWEBREC))
        self.assertTrue(compatible(X50, LEGACY_BASE, FragmentationBase("kuznetsov_legacy", "1.0.0")))
        self.assertFalse(compatible(X50, LEGACY_BASE, CURRENT_BASE))
        self.assertFalse(compatible(X50, CURRENT_BASE, LEGACY_BASE))

    def test_x50_of_other_version_of_same_model_is_incompatible(self):
        """Поправка x50 текущей базы не накладывается на прогноз PR 2 (2.0.0): x50 там другой."""
        pr2 = FragmentationBase("kuzram", PR2_VERSION)

        self.assertFalse(compatible(X50, CURRENT_BASE, pr2))
        self.assertFalse(compatible(X50, pr2, CURRENT_BASE))
        self.assertFalse(compatible(OVERSIZE, CURRENT_BASE, pr2))
        self.assertTrue(compatible(X50, pr2, FragmentationBase("swebrec", PR2_VERSION)))

    def test_oversize_needs_same_model(self):
        self.assertTrue(compatible(OVERSIZE, CURRENT_BASE, CURRENT_BASE))
        self.assertFalse(compatible(OVERSIZE, CURRENT_BASE, NEW_SWEBREC))

    def test_ppv_always(self):
        self.assertTrue(compatible(PPV, CURRENT_BASE, LEGACY_BASE))
        self.assertEqual(refusal_reason(PPV, LEGACY_BASE, None), "")

    def test_refusal_names_both_bases(self):
        reason = refusal_reason(X50, LEGACY_BASE, CURRENT_BASE)

        self.assertIn("Kuz-Ram (старая) 1.0.0", reason)
        self.assertIn(f"Kuz-Ram {CURRENT_VERSION}", reason)
        self.assertIn("переобучить", reason)
        self.assertEqual(refusal_reason(X50, CURRENT_BASE, NEW_SWEBREC), "")

    def test_oversize_of_same_base_other_curve_is_refused_without_retrain_advice(self):
        """Негабарит учится всегда на kuzram: другая кривая той же базы — не повод переобучать."""
        reason = refusal_reason(OVERSIZE, CURRENT_BASE, NEW_SWEBREC)

        self.assertEqual(
            reason,
            f"Калибровка негабарита обучена на кривой «{CURRENT_BASE.label()}» "
            f"и к прогнозу «{NEW_SWEBREC.label()}» не применяется.",
        )

    def test_oversize_of_other_base_still_asks_to_retrain(self):
        reason = refusal_reason(OVERSIZE, LEGACY_BASE, CURRENT_BASE)

        self.assertIn("переобучить", reason)

    def test_unknown_prediction_base_is_refused(self):
        self.assertIn("Не указано", refusal_reason(OVERSIZE, CURRENT_BASE, None))


class SampleBaselineTests(unittest.TestCase):
    def test_new_row_gives_baseline_for_new_artifact(self):
        row = {
            "predicted_x50_mm": 120.0,
            "predicted_model": "kuzram",
            "predicted_model_version": "1.0.0",
            "baseline_x50_mm": 150.0,
            "baseline_model": "kuzram",
            "baseline_model_version": CURRENT_VERSION,
        }
        self.assertEqual(sample_baseline(row, X50, CURRENT_BASE), 150.0)
        self.assertEqual(sample_baseline(row, X50, LEGACY_BASE), 120.0)

    def test_old_row_is_legacy(self):
        row = {"predicted_x50_mm": 120.0, "predicted_oversize_pct": 4.0}
        self.assertEqual(sample_baseline(row, OVERSIZE, LEGACY_BASE), 4.0)
        self.assertIsNone(sample_baseline(row, X50, CURRENT_BASE))

    def test_new_prediction_is_not_old_baseline(self):
        for version in (PR2_VERSION, CURRENT_VERSION):
            with self.subTest(version=version):
                row = {"predicted_x50_mm": 120.0, "predicted_model": "kuzram", "predicted_model_version": version}
                self.assertIsNone(sample_baseline(row, X50, LEGACY_BASE))

    def test_stored_pr2_prediction_is_not_baseline_of_current_artifact(self):
        row = {"predicted_x50_mm": 120.0, "predicted_model": "kuzram", "predicted_model_version": PR2_VERSION}

        self.assertIsNone(sample_baseline(row, X50, CURRENT_BASE))


class LabelTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(base_label(X50, "kuzram", CURRENT_VERSION), f"База: Kuz-Ram {CURRENT_VERSION}")
        self.assertEqual(
            base_label(OVERSIZE, "", ""), "Старая база (Kuz-Ram (старая) 1.0.0) — только для старых моделей"
        )
        self.assertEqual(base_label(PPV, "", ""), "")
        self.assertEqual(spatial_base_label("kuzram", CURRENT_VERSION), f"База: Kuz-Ram {CURRENT_VERSION}")
        self.assertEqual(
            spatial_base_label("", ""), "Старая база (Kuz-Ram (старая) 1.0.0) — физика считается старой моделью"
        )

    def test_unknown_model_gives_neutral_label_not_error(self):
        """Список и карточка не падают из-за артефакта с неизвестной моделью базы."""
        expected = "База: no_such_model 2.0.0 — модель неизвестна"

        self.assertEqual(base_label(X50, "no_such_model", "2.0.0"), expected)
        self.assertEqual(spatial_base_label("no_such_model", "2.0.0"), expected)
        self.assertEqual(base_label(PPV, "no_such_model", "2.0.0"), "")
        with self.assertRaises(ValueError):
            artifact_base("no_such_model", "2.0.0")


if __name__ == "__main__":
    unittest.main()
