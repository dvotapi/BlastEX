import unittest

from design.models import ROLE_DESIGNED, ROLE_MEASURED, ROLE_PREDICTED
from intelligence.datasets.targets import (
    TARGET_GROUPS,
    extract_fragmentation_targets,
    extract_targets,
    target_group_has_values,
)
from simulation.fragmentation.models import ModelProvenance
from tests.dataset_fixtures import closed_design


class DatasetTargetTests(unittest.TestCase):
    def test_extracts_all_target_groups_as_measured(self):
        result = closed_design().blast_result
        targets = extract_targets(result, fired_coverage=1.0)
        self.assertEqual(tuple(targets), TARGET_GROUPS)
        self.assertEqual(targets["FRAGMENTATION"]["role"], ROLE_MEASURED)
        self.assertAlmostEqual(targets["FRAGMENTATION"]["x50_mm"], 170.0)
        self.assertEqual(targets["FRAGMENTATION"]["predicted_role"], ROLE_PREDICTED)
        self.assertEqual(targets["VIBRATION"]["role"], ROLE_MEASURED)
        self.assertAlmostEqual(targets["VIBRATION"]["ppv_mm_s"], 4.8)
        self.assertAlmostEqual(targets["BLAST"]["muckpile_volume_m3"], 2100.0)
        self.assertEqual(targets["BLAST"]["toe_condition"], "minor")
        self.assertAlmostEqual(targets["PERFORMANCE"]["oversize_minus_designed_pct"], 1.0)
        self.assertEqual(targets["ECONOMICS"]["role"], ROLE_MEASURED)
        self.assertAlmostEqual(targets["ECONOMICS"]["total_amount_rub"], 1_900_000.0)
        self.assertEqual(targets["ECONOMICS"]["planned_role"], ROLE_DESIGNED)
        for name in TARGET_GROUPS:
            self.assertTrue(target_group_has_values(targets[name]), name)

    def test_empty_result_has_no_complete_groups(self):
        targets = extract_targets(None)
        self.assertFalse(any(target_group_has_values(group) for group in targets.values()))

    def test_fragmentation_targets_carry_model_of_stored_prediction(self):
        design = closed_design()
        design.blast_result.basis.predicted_fragmentation.provenance = ModelProvenance(
            model="kuzram", model_version="2.0.0"
        )

        group = extract_fragmentation_targets(design.blast_result)

        self.assertEqual(group["predicted_model"], "kuzram")
        self.assertEqual(group["predicted_model_version"], "2.0.0")

    def test_fragmentation_targets_without_prediction_have_empty_model(self):
        group = extract_fragmentation_targets(None)

        self.assertEqual(group["predicted_model"], "")
        self.assertEqual(group["predicted_model_version"], "")

    def test_model_of_prediction_does_not_fill_the_group(self):
        group = extract_fragmentation_targets(None)
        group["predicted_model"] = "kuzram"
        group["predicted_model_version"] = "2.0.0"

        self.assertFalse(target_group_has_values(group))


if __name__ == "__main__":
    unittest.main()
