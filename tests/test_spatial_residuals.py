"""BDX-022: residuals keep the unit of the named field; no silent conversion."""
import unittest

from intelligence.spatial.features import hole_rows_from_payload
from intelligence.spatial.residuals import residual_tables
from intelligence.spatial.types import (
    HOLE_FEATURE_NAMES,
    METRIC_X50,
    RESIDUAL_OVERSIZE,
    RESIDUAL_TOE,
    RESIDUAL_X50,
    ROLE_PREDICTED,
)
from tests.spatial_fixtures import synthetic_spatial_snapshot


class SpatialResidualTests(unittest.TestCase):
    def test_x50_residual_stays_millimetres(self):
        snapshot = synthetic_spatial_snapshot()
        rows = hole_rows_from_payload(snapshot.samples[0].holes)
        tables = residual_tables(rows, feature_names=list(HOLE_FEATURE_NAMES))
        table = tables[RESIDUAL_X50]
        self.assertEqual(table["unit"], "mm")
        self.assertEqual(table["role"], ROLE_PREDICTED)
        self.assertEqual(table["metric"], METRIC_X50)
        self.assertGreaterEqual(len(table["y"]), 6)
        self.assertTrue(all(abs(value) < 80.0 for value in table["y"]))

    def test_oversize_residual_stays_percent(self):
        snapshot = synthetic_spatial_snapshot()
        rows = hole_rows_from_payload(snapshot.samples[0].holes)
        tables = residual_tables(rows, feature_names=list(HOLE_FEATURE_NAMES))
        self.assertEqual(tables[RESIDUAL_OVERSIZE]["unit"], "%")
        self.assertEqual(tables[RESIDUAL_TOE]["unit"], "")

    def test_measured_minus_block_predicted_when_both_present(self):
        snapshot = synthetic_spatial_snapshot()
        rows = hole_rows_from_payload(snapshot.samples[0].holes)
        first = rows[0]
        tables = residual_tables(rows, feature_names=list(HOLE_FEATURE_NAMES))
        baseline = tables[RESIDUAL_X50]["block_predicted"]
        expected = float(first.measured[METRIC_X50]) - float(baseline)
        self.assertAlmostEqual(tables[RESIDUAL_X50]["y"][0], expected, places=5)
