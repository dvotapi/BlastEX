import unittest

from intelligence.calibration.algorithms import (
    PLUGIN_ALGORITHMS,
    available_algorithms,
    get_algorithm,
)
from intelligence.calibration.features import residual_table, residual_value
from tests.calibration_fixtures import synthetic_snapshot


class ResidualValueTests(unittest.TestCase):
    def test_residual_is_measured_minus_baseline(self):
        self.assertAlmostEqual(residual_value(170.0, 150.0), 20.0)
        self.assertAlmostEqual(residual_value(4.0, 5.0), -1.0)

    def test_table_keeps_only_rows_with_baseline_and_measured(self):
        snapshot = synthetic_snapshot(n=8)
        snapshot.samples[0].targets["FRAGMENTATION"]["predicted_x50_mm"] = None
        table = residual_table(snapshot, "kuzram_residual")
        self.assertEqual(len(table.y), 7)
        self.assertEqual(len(table.feature_names), 19)
        self.assertIn("baseline", table.feature_names)
        self.assertAlmostEqual(table.y[0], residual_value(table.measured[0], table.baselines[0]))


class AlgorithmRegistryTests(unittest.TestCase):
    def test_builtin_forest_algorithms_are_available(self):
        names = {item["name"]: item for item in available_algorithms()}
        self.assertTrue(names["random_forest"]["available"])
        self.assertTrue(names["extra_trees"]["available"])
        self.assertEqual(names["random_forest"]["kind"], "builtin")
        for plugin in PLUGIN_ALGORITHMS:
            self.assertIn(plugin, names)
            self.assertEqual(names[plugin]["kind"], "plugin")

    def test_random_forest_fits_tiny_table(self):
        table = residual_table(synthetic_snapshot(n=6), "kuzram_residual")
        algo = get_algorithm("random_forest")
        import numpy as np

        estimator = algo.fit(np.asarray(table.X), np.asarray(table.y))
        preds = algo.predict(estimator, np.asarray(table.X))
        self.assertEqual(len(preds), 6)

    def test_extra_trees_alias(self):
        self.assertEqual(get_algorithm("et").name, "extra_trees")

    def test_unknown_algorithm_lists_available(self):
        with self.assertRaises(ValueError) as ctx:
            get_algorithm("neural_net")
        self.assertIn("random_forest", str(ctx.exception))

    def test_missing_boosting_plugin_explains_default(self):
        names = {item["name"]: item for item in available_algorithms()}
        if names["catboost"]["available"]:
            self.skipTest("catboost is installed in this environment")
        with self.assertRaises(ValueError) as ctx:
            get_algorithm("catboost")
        self.assertIn("Random Forest", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
