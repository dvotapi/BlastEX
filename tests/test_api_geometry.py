"""api.routers.blast: геометрия скважины/блока и SVG-схема заряда совпадают
с прямым вызовом cost.geometry, как это делал Streamlit-интерфейс."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cost.persistence as persistence
from api.routers.blast import post_blast_geometry, post_hole_scheme
from api.schemas.blast import BlastGeometryRequest
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY, DEFAULT_EXPLOSIVES
from cost.geometry import (
    calculate_block_geometry,
    calculate_hole_geometry,
    hole_geometry_table_rows,
    normalize_initiation_config,
)


class BlastGeometryEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(persistence, "data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _payload(self, **overrides) -> BlastGeometryRequest:
        base = dict(
            grid_a_m=6.0,
            grid_b_m=5.0,
            depth_m=11.0,
            overdrill_m=1.0,
            undercharge_m=3.1,
            crown_mm=152.0,
            hole_oversize_coeff=1.05,
            explosive_key=DEFAULT_EXPLOSIVE_KEY,
            block_volume_m3=30_000.0,
            additional_holes_pct=0.03,
        )
        base.update(overrides)
        return BlastGeometryRequest(**base)

    def test_geometry_matches_direct_calculation(self):
        payload = self._payload()
        response = post_blast_geometry(payload, team_id="default")

        explosive_item = next(i for i in DEFAULT_EXPLOSIVES if i.key == DEFAULT_EXPLOSIVE_KEY)
        initiation = normalize_initiation_config(
            intermediate_detonators_per_hole=1,
            nsi_per_hole=1,
            nsi_length_1_m=12.0,
            nsi_length_2_m=6.0,
            detonator_delay_ms=500,
        )
        expected_hole = calculate_hole_geometry(
            grid_a_m=6.0,
            grid_b_m=5.0,
            depth_m=11.0,
            overdrill_m=1.0,
            undercharge_m=3.1,
            crown_mm=152.0,
            hole_oversize_coeff=1.05,
            explosive=explosive_item.properties,
            explosive_label=explosive_item.label,
        )
        expected_block = calculate_block_geometry(
            block_volume_m3=30_000.0,
            hole=expected_hole,
            additional_holes_pct=0.03,
            initiation=initiation,
        )

        self.assertAlmostEqual(response.hole.charge_mass_kg, expected_hole.charge_mass_kg)
        self.assertAlmostEqual(response.hole.specific_q_kg_m3, expected_hole.specific_q_kg_m3)
        self.assertEqual(response.block.total_holes, expected_block.total_holes)
        self.assertEqual(response.label, explosive_item.label)
        self.assertEqual(
            response.hole_rows, hole_geometry_table_rows(expected_hole, initiation=initiation)
        )

    def test_contour_view_uses_per_meter_rows(self):
        response = post_blast_geometry(self._payload(view="contour"), team_id="default")
        labels = [row[0] for row in response.hole_rows]
        self.assertIn("Удельный расход, кг/п.м.", labels)

    def test_hole_scheme_returns_svg(self):
        response = post_hole_scheme(self._payload(), team_id="default")
        self.assertEqual(response.media_type, "image/svg+xml")
        self.assertGreater(len(response.body), 1000)
        self.assertIn(b"<svg", response.body)


if __name__ == "__main__":
    unittest.main()
