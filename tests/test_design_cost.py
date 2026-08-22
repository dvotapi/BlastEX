import unittest

from api.schemas.design import BlastDesignSchema, DesignCostRequest
from api.services.design_service import estimate_design_cost
from design.charging import apply_charge_rules
from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.pattern import generate_pattern
from design.timing import build_template_network
from Blast import ExplosiveProperties

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


def _design() -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 16), (0, 16)]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )
    params = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 4.0, "offset_from_face_m": 0.0, "edge_margin_m": 0.0}
    holes = generate_pattern(contour, params)
    loads = apply_charge_rules(
        holes, {"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 4.0, "grid_b_m": 4.0}, EXPLOSIVE
    )
    network = build_template_network(holes, "row", {"system": "nonel"})
    return BlastDesign(
        design_id="test",
        name="Тест сметы",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params=params,
        charge_rules={"hole_oversize_coeff": 1.05},
        explosive_key="ПВВ Гранулит-РП",
    )


class DesignCostConversionTests(unittest.TestCase):
    def test_actual_totals_pass_through_to_cost_engine(self):
        design = _design()
        request = DesignCostRequest(
            design=BlastDesignSchema(**design.to_dict()),
            scenario_id="drill_blast",
        )
        result = estimate_design_cost(request)

        self.assertIsNotNone(result.block_geometry)
        # Реальные суммы, а не формульная оценка объём/выход.
        self.assertEqual(result.block_geometry.total_holes, len(design.holes))
        self.assertAlmostEqual(
            result.block_geometry.drilling_footage_m,
            sum(h.length_m for h in design.holes),
            places=2,
        )
        self.assertAlmostEqual(
            result.block_geometry.total_charge_mass_kg,
            sum(ld.total_charge_kg for ld in design.loads),
            places=2,
        )
        self.assertGreater(result.total_amount_rub, 0.0)
        self.assertIsNotNone(result.drilling_total_cost)

    def test_empty_design_raises(self):
        design = BlastDesign(design_id="empty")
        request = DesignCostRequest(
            design=BlastDesignSchema(**design.to_dict()),
            scenario_id="drill_blast",
        )
        with self.assertRaises(Exception):
            estimate_design_cost(request)


if __name__ == "__main__":
    unittest.main()
