import unittest

from api.schemas.design import BlastDesignSchema, DesignCostRequest
from api.services.design_service import estimate_design_cost
from design.charging import apply_charge_rules
from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.pattern import generate_pattern
from design.timing import build_template_network
from Blast import ExplosiveProperties
from cost.v2.legacy_adapter import default_legacy_references

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
        result = estimate_design_cost(request, default_legacy_references())

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

    def test_square_grid_uses_spacing_for_burden(self):
        # У квадрата генератор строит с b = a: burden_b_m в параметрах не действует.
        from api.services.design_service import _design_to_hole_and_block

        design = _design()
        design.pattern_params = {**design.pattern_params, "pattern": "square", "burden_b_m": 3.0}
        hole, _, _ = _design_to_hole_and_block(design)
        self.assertEqual((hole.grid_a_m, hole.grid_b_m), (4.0, 4.0))
        # Без ключа и с неизвестным видом — тоже квадрат.
        for params in ({"spacing_a_m": 4.0, "burden_b_m": 3.0}, {"pattern": "hex", "spacing_a_m": 4.0, "burden_b_m": 3.0}):
            design.pattern_params = params
            self.assertEqual(_design_to_hole_and_block(design)[0].grid_b_m, 4.0)
        design.pattern_params = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.0}
        self.assertEqual(_design_to_hole_and_block(design)[0].grid_b_m, 3.0)

    def test_underdrilled_block_hands_off_with_zero_overdrill(self):
        # Блок по съёмке недобурен глубже проектного перебура (TASK-014, PR 5а):
        # перебур скважин отрицательный, в смету — 0, длина — фактическая.
        from api.services.design_service import _design_to_hole_and_block
        from design.survey.apply import apply_survey
        from design.survey.evaluate import SurveyTolerances, evaluate_survey
        from design.survey.match import SurveyMatch
        from design.survey.read import SurveyedPoint

        design = _design()
        matches = [
            SurveyMatch(
                hole.id,
                SurveyedPoint(
                    hole.id, hole.collar.x, hole.collar.y, hole.collar.z, hole.length_m - hole.subdrill_m - 0.5
                ),
                "name",
            )
            for hole in design.holes
        ]
        result = apply_survey(
            design, matches, evaluate_survey(design, matches, SurveyTolerances()), file_name="s.csv",
            file_sha256="", survey_date="2026-11-13", actor="", charge=None, now="",
        )
        design.holes = result.holes
        self.assertTrue(all(hole.subdrill_m < 0 for hole in design.holes))
        hole, _, _ = _design_to_hole_and_block(design)
        self.assertEqual(hole.overdrill_m, 0.0)
        self.assertAlmostEqual(hole.depth_m, sum(h.length_m for h in design.holes) / len(design.holes))
        request = DesignCostRequest(design=BlastDesignSchema(**design.to_dict()), scenario_id="drill_blast")
        self.assertGreater(estimate_design_cost(request, default_legacy_references()).total_amount_rub, 0.0)

    def test_empty_design_raises(self):
        design = BlastDesign(design_id="empty")
        request = DesignCostRequest(
            design=BlastDesignSchema(**design.to_dict()),
            scenario_id="drill_blast",
        )
        with self.assertRaises(Exception):
            estimate_design_cost(request, default_legacy_references())


if __name__ == "__main__":
    unittest.main()


class ChargeDiameterTransferTests(unittest.TestCase):
    def test_charge_diameter_is_hole_diameter(self):
        # В смету уходит диаметр заряда = диаметр скважины паспорта: он уже с
        # учётом разбуривания, коэффициент правил заряда не применяется.
        from api.services.design_service import _design_to_hole_and_block

        design = _design()
        design.charge_rules = {"hole_oversize_coeff": 1.2}
        hole, _, _ = _design_to_hole_and_block(design)
        expected = sum(h.diameter_mm for h in design.holes) / len(design.holes) / 1000.0
        self.assertAlmostEqual(hole.charge_diameter_m, expected, places=9)
